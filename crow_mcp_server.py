#!/usr/bin/env python3
"""
crow_mcp_server.py — Crow Memory MCP server (stdio, SSE, Streamable HTTP, and Dual transport).
Migrated to MCP Python SDK 2.1.1 (FastMCP / MCPServer API).

Exposes 3 tools (AD-5 consolidation, REQ-009):
  - crow_recall   (absorbs crow_get_user_bias via format="bias_block")
  - crow_ingest   (absorbs crow_ingest_from_build via exit_code)
  - crow_admin    (absorbs crow_diagnostics, crow_check_drift, crow_manage_prompt,
                   crow_manage_backup, crow_evolve_propose, crow_project_info)

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

Environment:
    CROW_STATE_TAG  — when set (e.g. "myk1yt"), the default state path becomes
                      memory/crow-{tag}.bin (AD-8.2). value_bank/recall_stats
                      live in the same directory (crow_core derives memory_dir
                      from the state file's directory).
"""

import asyncio
import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Annotated

# Fix Windows cp949 encoding issues with Unicode characters and pythonw (None stdout/stderr)
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    elif getattr(sys.stdout, "encoding", None) != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    elif getattr(sys.stderr, "encoding", None) != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.mcpserver import MCPServer

from crow_core import CrowMemory, DOMAINS
import crow_i18n


# ---------------------------------------------------------------------------
# Init & Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = "./memory/crow.bin"


def resolve_state_path(default_path: str) -> str:
    """AD-8.2 (REQ-012): honor the CROW_STATE_TAG environment variable.

    When CROW_STATE_TAG is set (e.g. "myk1yt"), the state path
    `memory/crow.bin` becomes `memory/crow-{tag}.bin`. All sibling data files
    (value_bank.json, recall_stats.json, system_prompt.md) resolve through
    crow_core's memory_dir, which is derived from the state file's DIRECTORY.
    With an unset tag, the path is returned unchanged.
    """
    tag = os.environ.get("CROW_STATE_TAG", "").strip()
    if not tag:
        return default_path
    p = Path(default_path)
    return str(p.with_name(f"{p.stem}-{tag}{p.suffix}"))


# ---------------------------------------------------------------------------
# Business Logic Handlers (reused across MCP tools and REST endpoints)
# ---------------------------------------------------------------------------

def _recall(crow: CrowMemory, args: dict) -> list:
    # AD-5: format="bias_block" absorbs crow_get_user_bias
    if args.get("format", "hint") == "bias_block":
        block = crow.get_user_bias_block(args.get("query", ""), None)
        return [{"type": "text", "text": block}]

    query = args.get("query", "")
    register = args.get("register")
    domain = args.get("domain", "all")
    top_k = max(1, min(5, int(args.get("top_k", 2))))
    project = args.get("project")
    strict_project = bool(args.get("strict_project", False))

    # AD-3 (REQ-004): register=all/unset → recall_multi over the domain's
    # registers. Global eff_sim merge, no per-register fillers, stats tracked
    # only for hit registers (handled inside recall_multi).
    if register in (None, "", "all"):
        result = crow.recall_multi(
            query,
            DOMAINS.get(domain, DOMAINS["all"]),
            top_k,
            project=project,
            strict_project=strict_project,
        )
        return _ok(result)

    result = crow.recall(
        query,
        register,
        top_k,
        project=project,
        strict_project=strict_project,
    )
    return _ok(result)


def _ingest(crow: CrowMemory, args: dict) -> list:
    # AD-5 L209 polarity resolution: explicit polarity wins → exit_code auto
    # map (ingest_from_build logic) → error requiring one of the two.
    polarity = args.get("polarity")
    exit_code = args.get("exit_code")
    if polarity is not None:
        pol = float(polarity)
    elif exit_code is not None:
        if int(exit_code) == 0:
            pol = 0.5 if bool(args.get("user_edited", False)) else 1.5
        else:
            pol = -1.0 if bool(args.get("user_edited", False)) else -0.5
    else:
        return _error("polarity or exit_code is required")

    # crow_core.ingest handles the scrub gate and rejects
    # empty_after_sanitize — its response JSON is passed through as-is.
    result = crow.ingest(
        args.get("key", ""),
        args.get("value", ""),
        pol,
        args.get("register", "style"),
        project=args.get("project"),
    )
    return _ok(result)


def _admin(crow: CrowMemory, args: dict) -> list:
    """AD-5 L222-229 dispatch table — reuses existing handlers verbatim."""
    action = args.get("action")
    sub_args = dict(args.get("args") or {})
    handlers = {
        "diagnostics": _diagnostics,
        "drift": _drift,
        "prompt": _manage_prompt,
        "backup": _manage_backup,
        "evolve": _evolve,
        "project_info": _project_info,
    }
    handler = handlers.get(action)
    if handler is None:
        return _error(f"Unknown admin action: {action}")
    return handler(crow, sub_args)


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
        version="1.5.0",
        instructions=(
            "Crow Memory — External synaptic memory for AI coding agents. "
            "Stores your coding style, bug intuition, and architectural "
            "preferences as compressed weight matrices in crow.bin. "
            "3 tools: crow_recall (before every response), crow_ingest "
            "(after build/test results or user feedback), crow_admin "
            "(diagnostics/drift/prompt/backup/evolve/project_info)."
        ),
    )

    crow = CrowMemory(state_path)
    crow.prewarm_encoder()

    # -----------------------------------------------------------------------
    # 3 MCP Tools (AD-5: consolidation 10 → 3)
    # -----------------------------------------------------------------------

    @mcp.tool(
        name="crow_recall",
        description=(
            "Recall user-specific coding style, bug intuition, architectural "
            "preference, or personal context from the Crow synaptic memory. "
            "Call this BEFORE every response to align with user's inductive bias. "
            "By default (register=all or omitted, domain=all), queries all 8 "
            "registers and merges results globally by effective similarity."
        ),
    )
    async def crow_recall(
        query: Annotated[str, Field(description="Natural language description of the current task.")],
        register: Annotated[
            str | None,
            Field(
                description=(
                    "Which register. Use 'all' (or omit) to query every register "
                    "in the selected domain. Code: style/bug/arch/context. "
                    "Life: life_pref/life_avoid/life_phil/life_context."
                )
            ),
        ] = None,
        domain: Annotated[
            str,
            Field(
                description=(
                    "Domain filter used when register is 'all' or omitted. "
                    "'code' = style/bug/arch/context, "
                    "'life' = life_pref/life_avoid/life_phil/life_context, "
                    "'all' = all 8 registers (default)."
                )
            ),
        ] = "all",
        top_k: Annotated[int, Field(description="Number of hints (1-5).", ge=1, le=5)] = 2,
        format: Annotated[
            str,
            Field(
                description=(
                    "Output format. 'hint' returns JSON hints (default); "
                    "'bias_block' returns the [User Bias] text block for "
                    "system prompt injection."
                )
            ),
        ] = "hint",
        project: Annotated[
            str | None,
            Field(
                description=(
                    "Project tag used to boost same-project hints and "
                    "filter/penalize cross-project ones."
                )
            ),
        ] = None,
        strict_project: Annotated[
            bool,
            Field(description="When true, hard-filters cross-project hints out of the results."),
        ] = False,
    ) -> str:
        args = {
            "query": query,
            "register": register,
            "domain": domain,
            "top_k": top_k,
            "format": format,
            "project": project,
            "strict_project": strict_project,
        }
        res = _recall(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_ingest",
        description=(
            "Ingest a coding experience into Crow's long-term synaptic memory. "
            "Call AFTER build/test results or user explicit feedback. Provide "
            "either an explicit polarity or a build exit_code for automatic "
            "polarity mapping. Content is sanitized first; pure-noise input "
            "is rejected without touching the memory."
        ),
    )
    async def crow_ingest(
        key: Annotated[str, Field(description="Abstract description of the situation.")],
        value: Annotated[str, Field(description="Code pattern or decision applied.")],
        register: Annotated[
            str,
            Field(
                description="Register: style, bug, arch, context, life_pref, life_avoid, life_phil, life_context."
            ),
        ],
        polarity: Annotated[
            float | None,
            Field(
                description=(
                    "Reinforcement strength [-2.0, 2.0]. Optional if exit_code "
                    "is given; explicit polarity wins when both are provided."
                )
            ),
        ] = None,
        exit_code: Annotated[
            int | None,
            Field(
                description=(
                    "Build exit code (0 = success). Maps automatically to "
                    "polarity (+1.5/+0.5 on success, -0.5/-1.0 on failure) "
                    "unless an explicit polarity is given."
                )
            ),
        ] = None,
        user_edited: Annotated[
            bool,
            Field(description="Whether the user edited the AI's output. Adjusts the exit_code-derived polarity."),
        ] = False,
        project: Annotated[
            str | None,
            Field(description="Project tag stored with the memory entry for later project-aware recall."),
        ] = None,
    ) -> str:
        args = {
            "key": key,
            "value": value,
            "register": register,
            "polarity": polarity,
            "exit_code": exit_code,
            "user_edited": user_edited,
            "project": project,
        }
        res = _ingest(crow, args)
        return res[0]["text"]

    @mcp.tool(
        name="crow_admin",
        description=(
            "Crow administrative operations in one tool. Actions: diagnostics "
            "(memory stats), drift (drift check), prompt (read/append/stats "
            "system_prompt.md), backup (create/rotate/list/recover), evolve "
            "(propose prompt mutations), project_info (list/create project "
            "instances)."
        ),
    )
    async def crow_admin(
        action: Annotated[
            str,
            Field(description="Which admin operation: diagnostics, drift, prompt, backup, evolve, or project_info."),
        ],
        args: Annotated[
            dict | None,
            Field(
                description=(
                    "Action-specific arguments, e.g. {\"threshold\": 0.5} for "
                    "drift, {\"action\": \"append\", \"rule\": \"...\"} for "
                    "prompt, {\"action\": \"create\", \"tag\": \"daily\"} for "
                    "backup, {\"min_confidence\": 0.85} for evolve, "
                    "{\"action\": \"create\", \"project_name\": \"myapp\"} for "
                    "project_info."
                )
            ),
        ] = None,
    ) -> str:
        res = _admin(crow, {"action": action, "args": args or {}})
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
            "version": "1.5.0",
            "entries": stats.get("value_bank_size", 0) + stats.get("update_count", 0),
        })

    @mcp.custom_route("/ingest", methods=["POST"])
    async def rest_ingest(request: Request) -> JSONResponse:
        try:
            body_bytes = await request.body()
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            content = data.get("content", "")
            register = data.get("register", "context")
            project = data.get("project")
            # crow_core.ingest applies the scrub gate (AD-1) — do not
            # duplicate sanitization here.
            result = crow.ingest(
                key=content[:200],
                value=content,
                polarity=1.0,
                register=register,
                project=project,
            )
            return JSONResponse({"status": "ok", "message": result})
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @mcp.custom_route("/recall", methods=["GET"])
    async def rest_recall(request: Request) -> JSONResponse:
        try:
            query = request.query_params.get("query", "")
            register = request.query_params.get("register", "all")
            limit = min(max(int(request.query_params.get("limit", "5")), 1), 20)
            project = request.query_params.get("project") or None
            strict_project = request.query_params.get("strict_project", "false").lower() in ("1", "true", "yes")

            if register == "all":
                result = crow.recall_multi(
                    query,
                    DOMAINS.get("all", list(DOMAINS["code"]) + list(DOMAINS["life"])),
                    limit,
                    project=project,
                    strict_project=strict_project,
                )
                results = [
                    {"content": h.get("text", ""), "score": h.get("eff_sim", 0.0)}
                    for h in result.get("hints", [])
                ]
            else:
                r = crow.recall(query, register, top_k=limit,
                                project=project, strict_project=strict_project)
                results = [{"content": h, "score": r.get("confidence", 0.0)}
                           for h in r.get("hints", [])]

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
        help=f"Path to crow.bin (default: {DEFAULT_STATE_PATH}). CROW_STATE_TAG env "
             f"overrides the filename stem (AD-8.2): crow.bin -> crow-<tag>.bin",
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

    state_path = str(Path(resolve_state_path(args.state)).resolve())
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
