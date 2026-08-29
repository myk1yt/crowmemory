#!/usr/bin/env python3
"""
crow_mcp_server.py — Crow Memory MCP server (stdio, SSE, Streamable HTTP, and Dual transport).
Migrated to MCP Python SDK 2.1.1 (FastMCP / MCPServer API).

Exposes 10 tools:
  - crow_recall
  - crow_ingest
  - crow_evolve_propose
  - crow_diagnostics
  - crow_check_drift
  - crow_ingest_from_build
  - crow_get_user_bias
  - crow_manage_prompt
  - crow_manage_backup
  - crow_project_info

Exposes 2 prompts:
  - crow_memory_bias
  - crow_evolved_rules

Exposes 3 REST routes:
  - GET  /health
  - POST /ingest
  - GET  /recall

Usage:
    python crow_mcp_server.py
    python crow_mcp_server.py --state ./memory/crow.bin
    python crow_mcp_server.py --transport dual --port 9020 --http-port 9021
"""

import asyncio
import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Annotated

# Fix Windows cp949 encoding issues with Unicode characters
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.mcpserver import MCPServer

from crow_core import CrowMemory
import crow_i18n


# ---------------------------------------------------------------------------
# Init & Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = "./memory/crow.bin"


# ---------------------------------------------------------------------------
# Business Logic Handlers (reused across MCP tools and REST endpoints)
# ---------------------------------------------------------------------------

def _recall(crow: CrowMemory, args: dict) -> list:
    domain = args.get("domain", "all")
    register = args.get("register")
    top_k = max(1, min(5, int(args.get("top_k", 2))))

    # "all" register → force domain-based multi-register query
    if register == "all":
        register = None

    # If domain specified without register, query all registers in domain
    if domain and not register:
        from crow_core import DOMAINS
        all_hints = []
        total_conf = 0.0
        registers = DOMAINS.get(domain, DOMAINS["all"])
        for reg in registers:
            r = crow.recall(args.get("query", ""), reg, max(1, top_k // len(registers)))
            all_hints.extend(r.get("hints", []))
            total_conf += r.get("confidence", 0)
        avg_conf = round(total_conf / len(registers), 4) if registers else 0.0
        result = {"hints": all_hints[:top_k], "confidence": avg_conf, "domain": domain}
        return _ok(result)

    result = crow.recall(
        args.get("query", ""),
        register or "style",
        top_k,
    )
    return _ok(result)


def _ingest(crow: CrowMemory, args: dict) -> list:
    result = crow.ingest(
        args.get("key", ""),
        args.get("value", ""),
        float(args.get("polarity", 0.0)),
        args.get("register", "style"),
    )
    return _ok(result)


def _evolve(crow: CrowMemory, args: dict) -> list:
    result = crow.evolve_propose(
        float(args.get("min_confidence", 0.85)),
        int(args.get("min_occurrences", 3)),
    )
    return _ok(result)


def _diagnostics(crow: CrowMemory, _args: dict) -> list:
    result = crow.stats()
    result["prompt"] = crow.prompt_stats()
    return _ok(result)


def _drift(crow: CrowMemory, args: dict) -> list:
    result = crow.check_drift(
        float(args.get("threshold", 0.5)),
        int(args.get("min_low_confidence_count", 5)),
    )
    return _ok(result)


def _ingest_build(crow: CrowMemory, args: dict) -> list:
    result = crow.ingest_from_build(
        key=args.get("key", ""),
        value=args.get("value", ""),
        exit_code=int(args.get("exit_code", 1)),
        user_edited=bool(args.get("user_edited", False)),
        register=args.get("register", "arch"),
        explicit_polarity=args.get("explicit_polarity"),
    )
    return _ok(result)


def _user_bias(crow: CrowMemory, args: dict) -> list:
    registers = args.get("registers")
    block = crow.get_user_bias_block(args.get("query", ""), registers)
    return [{"type": "text", "text": block}]


def _manage_prompt(crow: CrowMemory, args: dict) -> list:
    action = args.get("action", "read")
    if action == "read":
        prompt = crow.get_system_prompt()
        return [{"type": "text", "text": prompt}]
    elif action == "append":
        rule = args.get("rule", "")
        auto_backup = bool(args.get("auto_backup", True))
        result = crow.append_system_prompt(rule, auto_backup)
        return _ok(result)
    elif action == "stats":
        return _ok(crow.prompt_stats())
    return _error(f"Unknown prompt action: {action}")


def _manage_backup(crow: CrowMemory, args: dict) -> list:
    action = args.get("action", "list")
    if action == "create":
        path = crow.create_backup(args.get("tag", "daily"))
        return _ok({"backup_path": path})
    elif action == "rotate":
        result = crow.rotate_backups(
            int(args.get("max_daily", 7)),
            int(args.get("max_weekly", 4)),
        )
        return _ok(result)
    elif action == "list":
        return _ok({"backups": crow.list_backups()})
    elif action == "recover":
        return _ok(crow.recover_from_drift())
    return _error(f"Unknown backup action: {action}")


def _project_info(crow: CrowMemory, args: dict) -> list:
    action = args.get("action", "list")
    if action == "list":
        return _ok({"projects": crow.list_projects()})
    elif action == "create":
        name = args.get("project_name", "")
        if not name:
            return _error("project_name is required for create action")
        _ = CrowMemory.for_project(name)
        return _ok({"created": name})
    return _error(f"Unknown project action: {action}")


def _ok(data) -> list:
    return [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]


def _error(message: str) -> list:
    return [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}]


# ---------------------------------------------------------------------------
# Server Factory (MCP 2.1.1 MCPServer)
# ---------------------------------------------------------------------------

def create_server(state_path: str) -> tuple[MCPServer, CrowMemory]:
    """Create MCP server and return (mcp, crow) tuple."""
    mcp = MCPServer(
        name="crow_memory",
        version="1.4.5",
        instructions=(
            "Crow Memory — External synaptic memory for AI coding agents. "
            "Stores your coding style, bug intuition, and architectural "
            "preferences as compressed weight matrices in crow.bin."
        ),
    )

    crow = CrowMemory(state_path)
    crow.prewarm_encoder()

    # -----------------------------------------------------------------------
    # 10 MCP Tools
    # -----------------------------------------------------------------------

    @mcp.tool(
        name="crow_recall",
        description=(
            "Recall user-specific coding style, bug intuition, architectural "
            "preference, or personal context from the Crow synaptic memory. "
            "Call this BEFORE every response to align with user's inductive bias. "
            "By default (no register, domain=all), queries all 8 registers."
        ),
    )
    async def crow_recall(
        query: Annotated[str, Field(description="Natural language description of the current task.")],
        register: Annotated[
            str | None,
            Field(
                description=(
                    "Which register. Use 'all' to query every register (same as domain=all). "
                    "Code: style/bug/arch/context. Life: life_pref/life_avoid/life_phil/life_context."
                )
            ),
        ] = None,
        top_k: Annotated[int, Field(description="Number of hints (1-3).", ge=1, le=5)] = 2,
        domain: Annotated[
            str,
            Field(
                description=(
                    "Domain filter shortcut. 'code' = style/bug/arch/context, "
                    "'life' = life_pref/life_avoid/life_phil/life_context, "
                    "'all' = all 8 registers (default)."
                )
            ),
        ] = "all",
    ) -> str:
        args = {"query": query, "register": register, "top_k": top_k, "domain": domain}
        res = _recall(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_ingest",
        description=(
            "Ingest a coding experience into Crow's long-term synaptic memory. "
            "Call AFTER build/test results or user explicit feedback."
        ),
    )
    async def crow_ingest(
        key: Annotated[str, Field(description="Abstract description of the situation.")],
        value: Annotated[str, Field(description="Code pattern or decision applied.")],
        polarity: Annotated[float, Field(description="Reinforcement strength [-2.0, 2.0].")],
        register: Annotated[
            str,
            Field(
                description="Register: style, bug, arch, context, life_pref, life_avoid, life_phil, life_context."
            ),
        ],
    ) -> str:
        args = {"key": key, "value": value, "polarity": polarity, "register": register}
        res = _ingest(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_evolve_propose",
        description=(
            "Analyze recent memory patterns and propose a permanent system prompt mutation. "
            "Returns a suggestion only; human approval is required for adoption."
        ),
    )
    async def crow_evolve_propose(
        min_confidence: Annotated[float, Field(description="Minimum confidence threshold.")] = 0.85,
        min_occurrences: Annotated[int, Field(description="Minimum occurrence count.")] = 3,
    ) -> str:
        args = {"min_confidence": min_confidence, "min_occurrences": min_occurrences}
        res = _evolve(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_diagnostics",
        description="Return diagnostic information about the Crow memory state (register norms, sparsity, update count, value bank size, prompt stats).",
    )
    async def crow_diagnostics() -> str:
        res = _diagnostics(crow, {})
        return res[0]["text"]

    @mcp.tool(
        name="crow_check_drift",
        description="Check if recent recalls show signs of memory drift.",
    )
    async def crow_check_drift(
        threshold: Annotated[float, Field(description="Cosine distance threshold for low-confidence recall.")] = 0.5,
        min_low_confidence_count: Annotated[int, Field(description="Minimum consecutive low-confidence queries to trigger drift warning.")] = 5,
    ) -> str:
        args = {"threshold": threshold, "min_low_confidence_count": min_low_confidence_count}
        res = _drift(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_ingest_from_build",
        description=(
            "Auto-determine polarity from build exit code and user edit status, "
            "then ingest the experience. Use this after npm run build completes."
        ),
    )
    async def crow_ingest_from_build(
        key: Annotated[str, Field(description="Abstract description.")],
        value: Annotated[str, Field(description="Code pattern applied.")],
        exit_code: Annotated[int, Field(description="Build exit code (0 = success).")],
        user_edited: Annotated[bool, Field(description="Whether the user edited the code after generation.")] = False,
        register: Annotated[str, Field(description="Register: style, bug, arch, context.")] = "arch",
        explicit_polarity: Annotated[float | None, Field(description="Override auto-polarity.")] = None,
    ) -> str:
        args = {
            "key": key,
            "value": value,
            "exit_code": exit_code,
            "user_edited": user_edited,
            "register": register,
            "explicit_polarity": explicit_polarity,
        }
        res = _ingest_build(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_get_user_bias",
        description=(
            "Generate the [User Bias] block for injection into the system prompt. "
            "Queries all registers and formats hints for prompt prepending."
        ),
    )
    async def crow_get_user_bias(
        query: Annotated[str, Field(description="Current task description.")],
        registers: Annotated[list[str] | None, Field(description="Registers to query (default: all).")] = None,
    ) -> str:
        args = {"query": query, "registers": registers}
        res = _user_bias(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_manage_prompt",
        description=(
            "Read, append to, or get statistics about the system_prompt.md file. "
            "Use 'read' to view current prompt, 'append' to adopt an evolved rule, 'stats' for metrics."
        ),
    )
    async def crow_manage_prompt(
        action: Annotated[str, Field(description="Action to perform: 'read', 'append', or 'stats'.")],
        rule: Annotated[str | None, Field(description="Rule text (required for append action).")] = None,
        auto_backup: Annotated[bool, Field(description="Whether to auto-backup system_prompt.md before append.")] = True,
    ) -> str:
        args = {"action": action, "rule": rule, "auto_backup": auto_backup}
        res = _manage_prompt(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_manage_backup",
        description="Manage Crow memory backups. Create, rotate, list, or recover from drift.",
    )
    async def crow_manage_backup(
        action: Annotated[str, Field(description="Action to perform: 'create', 'rotate', 'list', or 'recover'.")],
        tag: Annotated[str, Field(description="Backup tag: 'daily', 'weekly', or 'manual'.")] = "daily",
        max_daily: Annotated[int, Field(description="Maximum daily backups to keep during rotation.")] = 7,
        max_weekly: Annotated[int, Field(description="Maximum weekly backups to keep during rotation.")] = 4,
    ) -> str:
        args = {"action": action, "tag": tag, "max_daily": max_daily, "max_weekly": max_weekly}
        res = _manage_backup(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_project_info",
        description="List or create project-isolated Crow memory instances.",
    )
    async def crow_project_info(
        action: Annotated[str, Field(description="Action to perform: 'list' or 'create'.")],
        project_name: Annotated[str | None, Field(description="Project name (required for create).")] = None,
    ) -> str:
        args = {"action": action, "project_name": project_name}
        res = _project_info(crow, args)
        return res[0]["text"]

    # -----------------------------------------------------------------------
    # 2 MCP Prompts
    # -----------------------------------------------------------------------

    @mcp.prompt(
        name="crow_memory_bias",
        description="Auto-injected Crow Memory bias block. Contains your coding style, preferences, and evolved rules. The host should load this at session start.",
    )
    async def crow_memory_bias() -> str:
        bias = crow.get_user_bias_block("General context and preferences")
        evolved = crow.get_system_prompt()
        rules = [line for line in evolved.split("\n") if line.startswith("RULE:")]
        rules_text = "\n".join(f"- {r}" for r in rules[-10:]) if rules else "- No evolved rules yet."
        return (
            "=== Crow Memory — Auto-Injected Context ===\n\n"
            "[Permanent Evolved Rules]\n"
            f"{rules_text}\n\n"
            "[Recent Memory Hints]\n"
            f"{bias}\n\n"
            "The above context represents your learned preferences and style. "
            "Use it to guide your responses. To learn more, call crow_recall with "
            "a specific query and register (style/bug/arch/context/life_pref/life_avoid/life_phil/life_context)."
        )

    @mcp.prompt(
        name="crow_evolved_rules",
        description="Permanent evolved rules from Crow's system_prompt.md. These are statistically significant patterns approved via HITL.",
    )
    async def crow_evolved_rules() -> str:
        return crow.get_system_prompt()

    # -----------------------------------------------------------------------
    # 3 REST Routes
    # -----------------------------------------------------------------------

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        stats = crow.stats()
        return JSONResponse({
            "status": "ok",
            "version": "1.4.5",
            "entries": stats.get("value_bank_size", 0) + stats.get("update_count", 0),
        })

    @mcp.custom_route("/ingest", methods=["POST"])
    async def rest_ingest(request: Request) -> JSONResponse:
        try:
            body_bytes = await request.body()
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            content = data.get("content", "")
            register = data.get("register", "context")
            result = crow.ingest(
                key=content[:200],
                value=content,
                polarity=1.0,
                register=register,
            )
            return JSONResponse({"status": "ok", "message": result})
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @mcp.custom_route("/recall", methods=["GET"])
    async def rest_recall(request: Request) -> JSONResponse:
        try:
            query = request.query_params.get("query", "")
            register = request.query_params.get("register", "all")
            limit = min(int(request.query_params.get("limit", "5")), 20)

            if register == "all":
                from crow_core import DOMAINS
                all_hints = []
                for reg in DOMAINS.get("all", []):
                    r = crow.recall(query, reg, max(1, limit // len(DOMAINS.get("all", [reg]))))
                    for hint in r.get("hints", []):
                        all_hints.append({"content": hint, "score": r.get("confidence", 0.0)})
                results = all_hints[:limit]
            else:
                r = crow.recall(query, register, top_k=limit)
                results = [{"content": h, "score": r.get("confidence", 0.0)} for h in r.get("hints", [])]

            return JSONResponse({"results": results, "count": len(results)})
        except Exception as e:
            return JSONResponse({"results": [], "count": 0, "error": str(e)})

    return mcp, crow


# ---------------------------------------------------------------------------
# Ready File Helpers
# ---------------------------------------------------------------------------

_ready_file_path: str | None = None


def _write_ready_file():
    """Create a .crow_ready marker file so external scripts know the server is listening."""
    global _ready_file_path
    if _ready_file_path:
        try:
            Path(_ready_file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(_ready_file_path).write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass


def _remove_ready_file():
    """Remove the ready marker file on shutdown."""
    global _ready_file_path
    if _ready_file_path:
        try:
            Path(_ready_file_path).unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Transport Runners
# ---------------------------------------------------------------------------

async def _run_sse(mcp: MCPServer, host: str, port: int):
    """Run Crow MCP server over SSE (HTTP) transport with REST API."""
    import uvicorn

    app = mcp.sse_app(host=host)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    http_server = uvicorn.Server(config)
    print(f"Crow Memory MCP SSE server listening on http://{host}:{port}/sse")
    _write_ready_file()
    await http_server.serve()


async def _run_streamable_http(mcp: MCPServer, host: str, port: int):
    """Run Crow MCP server over Streamable HTTP transport."""
    import uvicorn

    app = mcp.streamable_http_app(host=host, json_response=True)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    http_server = uvicorn.Server(config)
    print(f"Crow Memory MCP Streamable HTTP server listening on http://{host}:{port}/mcp")
    _write_ready_file()
    await http_server.serve()


async def _run_dual_port(mcp: MCPServer, host: str, sse_port: int, http_port: int):
    """Run Crow MCP server with SSE and Streamable HTTP on separate ports."""
    import uvicorn

    sse_app = mcp.sse_app(host=host)
    http_app = mcp.streamable_http_app(host=host, json_response=True)

    sse_config = uvicorn.Config(sse_app, host=host, port=sse_port, log_level="warning")
    http_config = uvicorn.Config(http_app, host=host, port=http_port, log_level="warning")

    sse_server = uvicorn.Server(sse_config)
    http_server = uvicorn.Server(http_config)

    print(f"Crow Memory MCP SSE server listening on http://{host}:{sse_port}/sse")
    print(f"Crow Memory MCP Streamable HTTP server listening on http://{host}:{http_port}/mcp")
    _write_ready_file()

    await asyncio.gather(sse_server.serve(), http_server.serve())


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

async def main():
    global _ready_file_path

    parser = argparse.ArgumentParser(description="Crow Memory MCP Server")
    parser.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help=f"Path to crow.bin (default: {DEFAULT_STATE_PATH})",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http", "dual"],
        default="dual",
        help="Transport protocol (default: dual)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9020,
        help="Port for SSE transport (default: 9020)",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=9021,
        help="Port for Streamable HTTP transport (default: 9021)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for network transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--ready-file",
        default=None,
        help="Path to a ready marker file created when server starts listening (default: none)",
    )
    args = parser.parse_args()

    _ready_file_path = args.ready_file

    # Remove stale ready file from any previous crashed instance
    if _ready_file_path:
        try:
            Path(_ready_file_path).unlink(missing_ok=True)
        except OSError:
            pass

    state_path = str(Path(args.state).resolve())
    mcp, crow = create_server(state_path)

    # Register cleanup on shutdown
    import atexit
    atexit.register(_remove_ready_file)

    if args.transport == "sse":
        await _run_sse(mcp, args.host, args.port)
    elif args.transport == "streamable-http":
        await _run_streamable_http(mcp, args.host, args.http_port)
    elif args.transport == "dual":
        await _run_dual_port(mcp, args.host, args.port, args.http_port)
    else:
        print("Crow Memory MCP server running on stdio")
        await mcp.run_stdio_async()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
