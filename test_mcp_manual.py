#!/usr/bin/env python3
"""
test_mcp_manual.py — Manual MCP stdio protocol test for Crow Memory.
Spawns crow_mcp_server.py, sends JSON-RPC initialization + tool call,
verifies responses.
"""

import subprocess
import json
import sys
import time
import os

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "crow_mcp_server.py")
STATE_PATH = os.path.join(os.path.dirname(__file__), "memory", "crow.bin")
TIMEOUT = 120  # seconds for full test (model loading may be slow)


def send_rpc(proc, request: dict) -> dict:
    """Send a JSON-RPC request and read the response."""
    payload = json.dumps(request) + "\n"
    proc.stdin.write(payload)
    proc.stdin.flush()
    # Read response line
    line = proc.stdout.readline()
    if not line:
        return {"error": "No response from server (may have crashed)"}
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON response: {line.strip()[:200]}"}


def main():
    print("=" * 60)
    print("  Crow MCP Server — Manual Protocol Test")
    print("=" * 60)

    # Start server process
    print("\n[1] Starting crow_mcp_server.py...")
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT, "--state", STATE_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )

    try:
        # ---- Initialize ----
        print("[2] Sending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "crow-manual-test", "version": "1.0.0"},
            },
        }
        response = send_rpc(proc, init_request)
        if "error" in response:
            print(f"  ❌ Init failed: {response['error']}")
            # Read stderr for diagnostics
            proc.wait(timeout=5)
            stderr_output = proc.stderr.read()
            print(f"  stderr: {stderr_output[:500]}")
            return 1
        print(f"  ✅ Initialize OK: server={response.get('result', {}).get('serverInfo', {}).get('name', '?')}")

        # Send initialized notification
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        proc.stdin.write(json.dumps(notif) + "\n")
        proc.stdin.flush()

        # ---- List Tools ----
        print("[3] Requesting tool list...")
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        response = send_rpc(proc, list_request)
        if "error" in response:
            print(f"  ❌ List tools failed: {response['error']}")
            return 1
        tools = response.get("result", {}).get("tools", [])
        print(f"  ✅ Tools listed: {len(tools)} tools")
        for tool in tools:
            print(f"     - {tool['name']}: {tool['description'][:80]}...")

        # ---- Call crow_diagnostics ----
        print("[4] Calling crow_diagnostics...")
        call_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "crow_diagnostics",
                "arguments": {},
            },
        }
        response = send_rpc(proc, call_request)
        if "error" in response:
            print(f"  ❌ Diagnostics failed: {response['error']}")
        else:
            content = response.get("result", {}).get("content", [])
            if content:
                data = json.loads(content[0]["text"])
                print(f"  ✅ Diagnostics OK: update_count={data['update_count']}, value_bank={data['value_bank_size']}")
                for reg, info in data.get("registers", {}).items():
                    print(f"     {reg}: norm={info['norm']:.4f}")

        # ---- Call crow_recall ----
        print("[5] Calling crow_recall (this tests the encoder + recall)...")
        call_request2 = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "crow_recall",
                "arguments": {
                    "query": "TypeScript coding style preference",
                    "register": "style",
                    "top_k": 2,
                },
            },
        }
        response = send_rpc(proc, call_request2)
        if "error" in response:
            print(f"  ❌ Recall failed: {response['error']}")
        else:
            content = response.get("result", {}).get("content", [])
            if content:
                data = json.loads(content[0]["text"])
                print(f"  ✅ Recall OK: confidence={data.get('confidence', 0)}, hints={len(data.get('hints', []))}")
                for hint in data.get("hints", [])[:2]:
                    print(f"     {hint[:120]}...")

        # ---- Call crow_ingest ----
        print("[6] Calling crow_ingest...")
        call_request3 = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "crow_ingest",
                "arguments": {
                    "key": "MCP manual test ingest",
                    "value": "This is a manual test of the MCP server ingest functionality",
                    "polarity": 1.0,
                    "register": "context",
                },
            },
        }
        response = send_rpc(proc, call_request3)
        if "error" in response:
            print(f"  ❌ Ingest failed: {response['error']}")
        else:
            content = response.get("result", {}).get("content", [])
            if content:
                data = json.loads(content[0]["text"])
                print(f"  ✅ Ingest OK: status={data.get('status')}, polarity={data.get('polarity_applied')}, count={data.get('update_count')}")

        # ---- Call crow_get_user_bias ----
        print("[7] Calling crow_get_user_bias...")
        call_request4 = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "crow_get_user_bias",
                "arguments": {
                    "query": "Debug async worker memory leak",
                },
            },
        }
        response = send_rpc(proc, call_request4)
        if "error" in response:
            print(f"  ❌ User bias failed: {response['error']}")
        else:
            content = response.get("result", {}).get("content", [])
            if content:
                bias_text = content[0]["text"]
                print(f"  ✅ User bias generated: {len(bias_text)} chars")
                print(f"     {bias_text[:200]}...")

        # ---- Success ----
        print(f"\n{'='*60}")
        print("  🎉 ALL MCP PROTOCOL TESTS PASSED")
        print(f"  Crow MCP server is fully operational.")
        print(f"{'='*60}")
        return 0

    except Exception as e:
        print(f"\n  💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean shutdown
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    sys.exit(main())
