#!/usr/bin/env python3
"""
crow_mcp_server.py — Crow Memory MCP stdio server (complete).
Exposes 9 tools: recall, ingest, evolve_propose, diagnostics, check_drift,
ingest_from_build, get_user_bias, manage_prompt, manage_backup.

Usage:
    python crow_mcp_server.py
    python crow_mcp_server.py --state ./memory/crow.bin
"""

import asyncio
import argparse
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

from crow_core import CrowMemory

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = "./memory/crow.bin"

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "crow_recall",
        "description": (
            "Recall user-specific coding style, bug intuition, or architectural "
            "preference from the Crow synaptic memory. Call this BEFORE generating "
            "code to align with user's inductive bias."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language description of the current task."},
                "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"], "description": "Which register. Code: style/bug/arch/context. Life: life_pref/life_avoid/life_phil/life_context."},
                "top_k": {"type": "integer", "default": 2, "description": "Number of hints (1-3)."},
                "domain": {"type": "string", "enum": ["code", "life", "all"], "default": "all", "description": "Domain filter shortcut."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "crow_ingest",
        "description": (
            "Ingest a coding experience into Crow's long-term synaptic memory. "
            "Call AFTER build/test results or user explicit feedback."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Abstract description of the situation."},
                "value": {"type": "string", "description": "Code pattern or decision applied."},
                "polarity": {"type": "number", "description": "Reinforcement strength [-2.0, 2.0]."},
                "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"]},
            },
            "required": ["key", "value", "polarity", "register"],
        },
    },
    {
        "name": "crow_evolve_propose",
        "description": (
            "Analyze recent memory patterns and propose a permanent system prompt mutation. "
            "Returns a suggestion only; human approval is required for adoption."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_confidence": {"type": "number", "default": 0.85},
                "min_occurrences": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "crow_diagnostics",
        "description": "Return diagnostic information about the Crow memory state.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "crow_check_drift",
        "description": "Check if recent recalls show signs of memory drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "default": 0.5},
                "consecutive_calls": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "crow_ingest_from_build",
        "description": (
            "Auto-determine polarity from build exit code and user edit status, "
            "then ingest the experience. Use this after npm run build completes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Abstract description."},
                "value": {"type": "string", "description": "Code pattern applied."},
                "exit_code": {"type": "integer", "description": "Build exit code (0 = success)."},
                "user_edited": {"type": "boolean", "default": False},
                "register": {"type": "string", "enum": ["style", "bug", "arch", "context"], "default": "arch"},
                "explicit_polarity": {"type": "number", "description": "Override auto-polarity."},
            },
            "required": ["key", "value", "exit_code"],
        },
    },
    {
        "name": "crow_get_user_bias",
        "description": (
            "Generate the [User Bias] block for injection into the system prompt. "
            "Queries all registers and formats hints for prompt prepending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Current task description."},
                "registers": {"type": "array", "items": {"type": "string"}, "description": "Registers to query (default: all)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "crow_manage_prompt",
        "description": (
            "Read or append to the system_prompt.md file. "
            "Use 'read' to view current prompt, 'append' to adopt an evolved rule."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "append", "stats"]},
                "rule": {"type": "string", "description": "Rule text (required for append action)."},
                "auto_backup": {"type": "boolean", "default": True},
            },
            "required": ["action"],
        },
    },
    {
        "name": "crow_manage_backup",
        "description": (
            "Manage Crow memory backups. Create, rotate, list, or recover."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "rotate", "list", "recover"]},
                "tag": {"type": "string", "default": "daily", "enum": ["daily", "weekly", "manual"]},
                "max_daily": {"type": "integer", "default": 7},
                "max_weekly": {"type": "integer", "default": 4},
            },
            "required": ["action"],
        },
    },
    {
        "name": "crow_project_info",
        "description": "List or create project-isolated Crow memory instances.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create"]},
                "project_name": {"type": "string", "description": "Project name (required for create)."},
            },
            "required": ["action"],
        },
    },
]

# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------

def create_server(state_path: str) -> Server:
    server = Server(
        name="crow_memory",
        version="1.1.1",
        instructions=(
            "Crow Memory — External synaptic memory for AI coding agents. "
            "Stores your coding style, bug intuition, and architectural "
            "preferences as compressed weight matrices in crow.bin."
        ),
    )

    crow = CrowMemory(state_path)

    @server.list_tools()
    async def handle_list_tools() -> list:
        from mcp.types import Tool
        return [Tool(**td) for td in TOOL_DEFINITIONS]

    # ---- MCP Prompts (auto-loaded by host at session start) ----

    @server.list_prompts()
    async def handle_list_prompts() -> list:
        from mcp.types import Prompt
        return [
            Prompt(
                name="crow_memory_bias",
                description="Auto-injected Crow Memory bias block. Contains your coding style, preferences, and evolved rules. The host should load this at session start.",
                arguments=[],
            ),
            Prompt(
                name="crow_evolved_rules",
                description="Permanent evolved rules from Crow's system_prompt.md. These are statistically significant patterns approved via HITL.",
                arguments=[],
            ),
        ]

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict):
        if name == "crow_memory_bias":
            bias = crow.get_user_bias_block("General context and preferences")
            evolved = crow.get_system_prompt()
            rules = [l for l in evolved.split("\n") if l.startswith("RULE:")]
            rules_text = "\n".join(f"- {r}" for r in rules[-10:]) if rules else "- No evolved rules yet."
            return [
                {"type": "text", "text": (
                    "=== Crow Memory — Auto-Injected Context ===\n\n"
                    "[Permanent Evolved Rules]\n"
                    f"{rules_text}\n\n"
                    "[Recent Memory Hints]\n"
                    f"{bias}\n\n"
                    "The above context represents your learned preferences and style. "
                    "Use it to guide your responses. To learn more, call crow_recall with "
                    "a specific query and register (style/bug/arch/context/life_pref/life_avoid/life_phil/life_context)."
                )},
            ]
        elif name == "crow_evolved_rules":
            prompt = crow.get_system_prompt()
            return [{"type": "text", "text": prompt}]
        return _error(f"Unknown prompt: {name}")

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        try:
            handlers = {
                "crow_recall":             _recall,
                "crow_ingest":             _ingest,
                "crow_evolve_propose":     _evolve,
                "crow_diagnostics":        _diagnostics,
                "crow_check_drift":        _drift,
                "crow_ingest_from_build":  _ingest_build,
                "crow_get_user_bias":      _user_bias,
                "crow_manage_prompt":      _manage_prompt,
                "crow_manage_backup":      _manage_backup,
                "crow_project_info":       _project_info,
            }
            handler = handlers.get(name)
            if handler is None:
                return _error(f"Unknown tool: {name}")
            return handler(crow, arguments)
        except Exception as exc:
            return _error(f"Tool error [{name}]: {exc}")

    return server


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _recall(crow: CrowMemory, args: dict) -> list:
    domain = args.get("domain")
    register = args.get("register")
    top_k = max(1, min(5, args.get("top_k", 2)))

    # If domain specified without register, query all registers in domain
    if domain and not register:
        from crow_core import DOMAINS
        all_hints = []
        total_conf = 0.0
        registers = DOMAINS.get(domain, ["style"])
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
        int(args.get("consecutive_calls", 5)),
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
    return [{"type": "text", "text": json.dumps({"error": message})}]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Crow Memory MCP Server")
    parser.add_argument("--state", default=DEFAULT_STATE_PATH,
                        help=f"Path to crow.bin (default: {DEFAULT_STATE_PATH})")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport protocol (default: stdio)")
    parser.add_argument("--port", type=int, default=9020,
                        help="Port for SSE transport (default: 9020)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host for SSE transport (default: 127.0.0.1)")
    args = parser.parse_args()

    state_path = str(Path(args.state).resolve())
    server = create_server(state_path)

    if args.transport == "sse":
        await _run_sse(server, args.host, args.port)
    else:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )


async def _run_sse(server, host: str, port: int):
    """Run Crow MCP server over SSE (HTTP) transport."""
    from mcp.server.sse import SseServerTransport
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            return
        if scope["path"] == "/sse":
            async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
                await server.run(
                    read_stream, write_stream,
                    server.create_initialization_options(),
                )
        elif scope["path"].startswith("/messages/"):
            await sse.handle_post_message(scope, receive, send)
        else:
            # Health check / root
            body = b"Crow Memory MCP SSE Server"
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })

    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="warning",
    )
    http_server = uvicorn.Server(config)
    print(f"Crow Memory MCP SSE server listening on http://{host}:{port}/sse")
    await http_server.serve()


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
