#!/usr/bin/env python3
"""crow_mcp_stdio.py - thin stdio MCP server for Crow Memory v2.

JSON-RPC 2.0 over newline-delimited stdin/stdout, stdlib only. One CrowDB
instance per process, opened on first use and closed on exit. Serves the same
3 tools and 2 prompts as the v1.5 HTTP server (names, JSON-Schema enums and
semantics preserved), backed by the serverless SQLite engine instead of a
daemon.

Protocol: 2025-03-26. Server identity: crow-memory / 2.0.0.
"""

import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from crow_db import CrowDB
except ImportError:  # core not installed yet - handshake still works, tools report it
    CrowDB = None

try:
    from crow_text import _smart_truncate
except ImportError:
    _smart_truncate = None

PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "crow-memory"
SERVER_VERSION = "2.0.0"

MIN_TOP_K = 1
MAX_TOP_K = 5
RULE_MAX_CHARS = 400
PENDING_RULE_MAX_CHARS = 200        # per-line clip in [Unreviewed Model Suggestions]
PENDING_RULE_MAX_LINES = 5          # max pending [model] lines rendered
MAX_FRAME_BYTES = 8 * 1024 * 1024   # single stdin line cap (SEC-4)
_DATED_RULE_RE = re.compile(r"^- \d{4}-\d{2}-\d{2} ")

INSTRUCTIONS = (
    "Crow Memory - External synaptic memory for AI coding agents. "
    "3 tools: crow_recall (before every response), crow_ingest "
    "(after build/test results or user feedback), crow_admin "
    "(diagnostics/drift/prompt/backup/evolve/project_info)."
)

# Tool schemas mirror crow_i18n._BASE_TOOL_DEFINITIONS (v1.5 parity).
TOOLS = [
    {
        "name": "crow_recall",
        "description": (
            "Recall user-specific coding style, bug intuition, architectural "
            "preference, or personal context from the Crow synaptic memory. "
            "Call this BEFORE every response to align with user's inductive bias. "
            "By default (register=all or omitted, domain=all), queries all 8 "
            "registers and merges results globally by effective similarity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language description of the current task."},
                "register": {
                    "type": "string",
                    "enum": [
                        "style",
                        "bug",
                        "arch",
                        "context",
                        "life_pref",
                        "life_avoid",
                        "life_phil",
                        "life_context",
                        "all",
                    ],
                    "description": (
                        "Which register. Use 'all' (or omit) to query every register in the selected domain. "
                        "Code: style/bug/arch/context. Life: life_pref/life_avoid/life_phil/life_context."
                    ),
                },
                "domain": {
                    "type": "string",
                    "enum": ["code", "life", "all"],
                    "default": "all",
                    "description": (
                        "Domain filter used when register is 'all' or omitted. 'code' = style/bug/arch/context, "
                        "'life' = life_pref/life_avoid/life_phil/life_context, 'all' = all 8 registers (default)."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Number of hints (1-5).",
                },
                "format": {
                    "type": "string",
                    "enum": ["hint", "bias_block"],
                    "default": "hint",
                    "description": (
                        "Output format. 'hint' returns JSON hints (default); 'bias_block' returns the "
                        "[User Bias] text block for system prompt injection."
                    ),
                },
                "project": {
                    "type": "string",
                    "description": "Project tag used to boost same-project hints and filter/penalize cross-project ones.",
                },
                "strict_project": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, hard-filters cross-project hints out of the results.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "crow_ingest",
        "description": (
            "Ingest a coding experience into Crow's long-term synaptic memory. "
            "Call AFTER build/test results or user explicit feedback. Provide "
            "either an explicit polarity or a build exit_code for automatic "
            "polarity mapping. Content is sanitized first; pure-noise input "
            "is rejected without touching the memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Abstract description of the situation."},
                "value": {"type": "string", "description": "Code pattern or decision applied."},
                "register": {
                    "type": "string",
                    "enum": [
                        "style",
                        "bug",
                        "arch",
                        "context",
                        "life_pref",
                        "life_avoid",
                        "life_phil",
                        "life_context",
                    ],
                },
                "polarity": {
                    "type": "number",
                    "description": (
                        "Reinforcement strength [-2.0, 2.0]. Optional if exit_code is given; "
                        "explicit polarity wins when both are provided."
                    ),
                },
                "exit_code": {
                    "type": "integer",
                    "description": (
                        "Build exit code (0 = success). Maps automatically to polarity "
                        "(+1.5/+0.5 on success, -0.5/-1.0 on failure) unless an explicit polarity is given."
                    ),
                },
                "user_edited": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether the user edited the AI's output. Adjusts the exit_code-derived polarity.",
                },
                "project": {
                    "type": "string",
                    "description": "Project tag stored with the memory entry for later project-aware recall.",
                },
            },
            "required": ["key", "value", "register"],
        },
    },
    {
        "name": "crow_admin",
        "description": (
            "Crow administrative operations in one tool. Actions: diagnostics "
            "(memory stats), drift (drift check), prompt (read/append/approve/"
            "stats system_prompt.md), backup (create/rotate/list/recover), "
            "evolve (propose prompt mutations), project_info (list/create "
            "project instances), delete (remove one memory entry), purge "
            "(remove superseded/archived entries). Token-gated: 'prompt "
            "approve' and 'purge' with args.confirm_all=true refuse unless the "
            "human-held CROW_ADMIN_TOKEN environment variable is set and its "
            "value is passed as args.token; a model cannot supply that token, "
            "so it must not call these two."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["diagnostics", "drift", "prompt", "backup",
                             "evolve", "project_info", "delete", "purge"],
                    "description": (
                        "Which admin operation: diagnostics, drift, prompt, backup, evolve, "
                        "project_info, delete, or purge."
                    ),
                },
                "args": {
                    "type": "object",
                    "description": (
                        "Action-specific arguments, e.g. {\"threshold\": 0.5} for drift, "
                        "{\"action\": \"append\", \"rule\": \"...\"} for prompt, "
                        "{\"action\": \"create\", \"tag\": \"daily\"} for backup, "
                        "{\"min_confidence\": 0.85} for evolve, "
                        "{\"action\": \"create\", \"project_name\": \"myapp\"} for project_info. "
                        "Token-gated actions also take {\"token\": \"<CROW_ADMIN_TOKEN>\"}: "
                        "prompt approve, and purge with confirm_all=true."
                    ),
                },
            },
            "required": ["action"],
        },
    },
]

PROMPTS = [
    {
        "name": "crow_memory_bias",
        "description": (
            "Auto-injected Crow Memory bias block. Contains your coding style, preferences, and evolved rules. "
            "The host should load this at session start."
        ),
        "arguments": [],
    },
    {
        "name": "crow_evolved_rules",
        "description": (
            "Permanent evolved rules from Crow's system_prompt.md: permanent "
            "rules (human-promoted via CROW_ADMIN_TOKEN) plus unreviewed model "
            "suggestions."
        ),
        "arguments": [],
    },
]


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _ToolError(Exception):
    """Tool-level failure reported as MCP content with isError=true."""


def _home() -> Path:
    raw = os.environ.get("CROW_HOME", "").strip()
    if raw:
        return Path(os.path.expanduser(raw))
    return Path.home() / ".crow-memory"


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _text_item(text) -> dict:
    return {"type": "text", "text": text if isinstance(text, str) else _compact(text)}


def _json_item(value) -> dict:
    return _text_item(_compact(value))


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    if _smart_truncate is not None:
        try:
            return _smart_truncate(flat, limit)
        except Exception:
            pass
    return flat if len(flat) <= limit else flat[: max(1, limit - 3)].rstrip() + "..."


def _prompt_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("prompt", "content", "text", "prompt_text", "system_prompt", "value"):
            nested = result.get(key)
            if isinstance(nested, str):
                return nested
    return ""


def _error_response(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


class CrowStdioServer:
    def __init__(self) -> None:
        self.db = None
        self.db_error = ""
        try:
            if CrowDB is None:
                raise RuntimeError("crow_db is not importable (run the installer)")
            self.db = CrowDB(_home())
        except Exception as exc:
            self.db_error = "%s: %s" % (type(exc).__name__, exc)

    def close(self) -> None:
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None

    def _require_db(self):
        if self.db is None:
            raise _RpcError(-32603, "CrowDB unavailable: %s" % (self.db_error or "not initialised"))
        return self.db

    # -- request dispatch ---------------------------------------------------

    def handle(self, message):
        if isinstance(message, list):
            return _error_response(None, -32600, "Invalid Request: batches are not supported")
        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request")

        notification = "id" not in message
        msg_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return None if notification else _error_response(msg_id, -32600, "Invalid Request")

        params = message.get("params")
        if not isinstance(params, dict):
            params = {}

        try:
            result = self._dispatch(method, params)
        except _RpcError as exc:
            return None if notification else _error_response(msg_id, exc.code, exc.message)
        except Exception as exc:
            return (
                None
                if notification
                else _error_response(msg_id, -32603, "Internal error: %s: %s" % (type(exc).__name__, exc))
            )

        if notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: str, params: dict):
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method in ("notifications/initialized", "notifications/cancelled"):
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self._tools_call(params)
        if method == "prompts/list":
            return {"prompts": PROMPTS}
        if method == "prompts/get":
            return self._prompts_get(params)
        raise _RpcError(-32601, "Method not found: %s" % method)

    def _initialize(self, _params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }

    # -- tools --------------------------------------------------------------

    def _tools_call(self, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _RpcError(-32602, "tools/call requires a tool name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise _RpcError(-32602, "arguments must be an object")

        handlers = {
            "crow_recall": self._tool_recall,
            "crow_ingest": self._tool_ingest,
            "crow_admin": self._tool_admin,
        }
        handler = handlers.get(name)
        if handler is None:
            raise _RpcError(-32602, "Unknown tool: %s" % name)

        try:
            content = handler(self._require_db(), arguments)
        except _ToolError as exc:
            return {"content": [_json_item({"error": str(exc)})], "isError": True}
        except _RpcError:
            raise
        except Exception as exc:
            return {"content": [_json_item({"error": "%s: %s" % (type(exc).__name__, exc)})], "isError": True}
        return {"content": content, "isError": False}

    def _tool_recall(self, db, arguments: dict) -> list:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise _ToolError("query is required")

        register = arguments.get("register") or "all"
        domain = arguments.get("domain") or "all"
        top_k = arguments.get("top_k", 2)
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = 2
        top_k = max(MIN_TOP_K, min(MAX_TOP_K, top_k))
        project = arguments.get("project")
        strict_project = bool(arguments.get("strict_project", False))

        if arguments.get("format", "hint") == "bias_block":
            block = db.bias_block(
                query=query,
                domain=domain,
                project=project,
                strict_project=strict_project,
                top_k=top_k,
            )
            return [_text_item(block if isinstance(block, str) else _compact(block))]

        hints = db.recall(
            query=query,
            register=register,
            domain=domain,
            top_k=top_k,
            fmt="hint",
            project=project,
            strict_project=strict_project,
            track_stats=True,
        )
        return [_json_item(hints)]

    def _tool_ingest(self, db, arguments: dict) -> list:
        key = arguments.get("key")
        value = arguments.get("value")
        register = arguments.get("register")
        if not isinstance(key, str) or not isinstance(value, str) or not isinstance(register, str):
            raise _ToolError("key, value and register are required")

        polarity = arguments.get("polarity")
        if polarity is not None:
            try:
                polarity = float(polarity)
            except (TypeError, ValueError):
                raise _ToolError("polarity must be a number") from None

        exit_code = arguments.get("exit_code")
        if exit_code is not None:
            try:
                exit_code = int(exit_code)
            except (TypeError, ValueError):
                raise _ToolError("exit_code must be an integer") from None

        result = db.ingest(
            key,
            value,
            register,
            polarity=polarity,
            exit_code=exit_code,
            user_edited=bool(arguments.get("user_edited", False)),
            project=arguments.get("project"),
        )
        return [_json_item(result)]

    def _tool_admin(self, db, arguments: dict) -> list:
        action = arguments.get("action")
        if not isinstance(action, str) or not action:
            raise _ToolError("action is required")
        extra = arguments.get("args")
        if extra is None:
            extra = {}
        if not isinstance(extra, dict):
            raise _ToolError("args must be an object")
        return [_json_item(db.admin(action, extra))]

    # -- prompts ------------------------------------------------------------

    def _prompts_get(self, params: dict) -> dict:
        name = params.get("name")
        if name == "crow_memory_bias":
            description = PROMPTS[0]["description"]
            text = self._bias_prompt()
        elif name == "crow_evolved_rules":
            description = PROMPTS[1]["description"]
            text = self._evolved_rules()
        else:
            raise _RpcError(-32602, "Unknown prompt: %s" % (name,))
        return {
            "description": description,
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }

    def _raw_prompt_text(self) -> str:
        db = self._require_db()
        try:
            return _prompt_text(db.admin("prompt", {"action": "read"}))
        except Exception:
            return ""

    def _evolved_rules(self) -> str:
        # Unreviewed [model] suggestions never surface as standing rules.
        return "\n".join(line for line in self._raw_prompt_text().splitlines()
                         if "[model]" not in line)

    def _bias_prompt(self) -> str:
        standing, pending = [], []
        for line in self._raw_prompt_text().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            bucket = pending if "[model]" in stripped else standing
            if stripped.startswith("RULE:"):
                bucket.append(stripped)
            elif _DATED_RULE_RE.match(stripped):
                bucket.append(stripped[2:].strip())
        if standing:
            rules_text = "\n".join("- " + _clip(rule, RULE_MAX_CHARS)
                                   for rule in standing[-10:])
        else:
            rules_text = "- No evolved rules yet."

        db = self._require_db()
        try:
            bias = db.bias_block("General context and preferences")
        except Exception:
            bias = ""
        if not isinstance(bias, str):
            bias = _compact(bias)

        pending_section = ""
        if pending:
            pending_section = (
                "\n[Unreviewed Model Suggestions]\n"
                + "\n".join("- " + _clip(rule, PENDING_RULE_MAX_CHARS)
                            for rule in pending[-PENDING_RULE_MAX_LINES:])
            )

        return (
            "=== Crow Memory - Auto-Injected Context ===\n\n"
            "[Permanent Evolved Rules]\n"
            f"{rules_text}"
            f"{pending_section}\n\n"
            "[Recent Memory Hints]\n"
            f"{bias}\n\n"
            "The above context represents your learned preferences and style. "
            "Use it to guide your responses. To learn more, call crow_recall with "
            "a specific query and register (style/bug/arch/context/life_pref/life_avoid/life_phil/life_context)."
        )


def _write_message(writer, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if writer is not None:
        writer.write(data.encode("utf-8") + b"\n")
        writer.flush()
    else:
        sys.stdout.write(data + "\n")
        sys.stdout.flush()


def _safe_write(writer, payload: dict) -> bool:
    try:
        _write_message(writer, payload)
        return True
    except (OSError, ValueError):
        return False


def _read_line(reader, limit: int):
    """One stdin line capped at limit bytes/chars; None at EOF.

    Returns (text, oversized): oversized=True means the raw frame exceeded
    limit and was drained up to its newline (or EOF).
    """
    try:
        if reader is not None:
            raw = reader.readline(limit + 1)
        else:
            raw = sys.stdin.readline(limit + 1)
    except (OSError, ValueError):
        return None, False
    if not raw:
        return None, False
    newline = b"\n" if isinstance(raw, bytes) else "\n"
    oversized = len(raw) > limit and not raw.endswith(newline)
    if oversized:
        while True:
            try:
                chunk = (reader.readline(limit) if reader is not None
                         else sys.stdin.readline(limit))
            except (OSError, ValueError):
                break
            if not chunk or chunk.endswith(newline):
                break
    line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    return line, oversized


def _pump(server: CrowStdioServer) -> None:
    reader = getattr(sys.stdin, "buffer", None)
    writer = getattr(sys.stdout, "buffer", None)

    while True:
        line, oversized = _read_line(reader, MAX_FRAME_BYTES)
        if line is None:
            break
        if oversized:
            # one hostile frame must never kill the server (SEC-4)
            if not _safe_write(writer, _error_response(
                    None, -32700, "Parse error: message too large")):
                break
            continue
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except (ValueError, TypeError, RecursionError, MemoryError,
                UnicodeDecodeError):
            if not _safe_write(writer, _error_response(None, -32700,
                                                       "Parse error")):
                break
            continue
        try:
            response = server.handle(message)
        except (ValueError, TypeError, RecursionError, MemoryError):
            if not _safe_write(writer, _error_response(None, -32700,
                                                       "Parse error")):
                break
            continue
        if response is not None and not _safe_write(writer, response):
            break


def serve() -> int:
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    server = CrowStdioServer()
    try:
        _pump(server)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
