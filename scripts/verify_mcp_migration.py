#!/usr/bin/env python3
"""
Verification script for MCP SDK 2.1.1 migration.
Tests tool registration, prompt registration, custom routes, and mock calls.
"""
import asyncio
import json
import sys
from pathlib import Path

# Fix Windows cp949 encoding issues
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))
import crow_mcp_server

async def main():
    print("=== Testing create_server ===")
    mcp, crow = crow_mcp_server.create_server("./memory/crow.bin")
    print(f"Server Name: {mcp.name}, Version: {mcp.version}")

    # 1. Check Tools
    tools = await mcp.list_tools()
    print(f"\n[Tools] Registered: {len(tools)} tools (Expected: 10)")
    tool_names = [t.name for t in tools]
    print(f"Tool names: {tool_names}")
    expected_tools = [
        "crow_recall",
        "crow_ingest",
        "crow_evolve_propose",
        "crow_diagnostics",
        "crow_check_drift",
        "crow_ingest_from_build",
        "crow_get_user_bias",
        "crow_manage_prompt",
        "crow_manage_backup",
        "crow_project_info",
    ]
    for et in expected_tools:
        assert et in tool_names, f"Missing tool: {et}"
    print("✓ All 10 tools registered successfully")

    # 2. Check Prompts
    prompts = await mcp.list_prompts()
    print(f"\n[Prompts] Registered: {len(prompts)} prompts (Expected: 2)")
    prompt_names = [p.name for p in prompts]
    print(f"Prompt names: {prompt_names}")
    expected_prompts = ["crow_memory_bias", "crow_evolved_rules"]
    for ep in expected_prompts:
        assert ep in prompt_names, f"Missing prompt: {ep}"
    print("✓ All 2 prompts registered successfully")

    # 3. Check Custom Routes
    routes = mcp._custom_starlette_routes
    print(f"\n[Custom Routes] Registered: {len(routes)} routes (Expected: 3)")
    route_paths = [r.path for r in routes]
    print(f"Route paths: {route_paths}")
    expected_routes = ["/health", "/ingest", "/recall"]
    for er in expected_routes:
        assert er in route_paths, f"Missing route: {er}"
    print("✓ All 3 custom routes registered successfully")

    # 4. Call Tools directly via mcp.call_tool
    print("\n[Tool Execution Tests]")
    diag_res = await mcp.call_tool("crow_diagnostics", {})
    print(f"crow_diagnostics response: {diag_res}")

    recall_res = await mcp.call_tool("crow_recall", {"query": "python coding style", "top_k": 2})
    print(f"crow_recall response: {recall_res}")

    bias_res = await mcp.call_tool("crow_get_user_bias", {"query": "test query"})
    print(f"crow_get_user_bias response: {bias_res}")

    # 5. Call Prompts directly via mcp.get_prompt
    print("\n[Prompt Execution Tests]")
    p1 = await mcp.get_prompt("crow_memory_bias")
    print(f"crow_memory_bias messages count: {len(p1.messages)}")
    p2 = await mcp.get_prompt("crow_evolved_rules")
    print(f"crow_evolved_rules messages count: {len(p2.messages)}")

    print("\n✓ ALL VERIFICATION CHECKS PASSED")

if __name__ == "__main__":
    asyncio.run(main())
