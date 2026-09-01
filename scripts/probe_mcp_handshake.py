# -*- coding: utf-8 -*-
"""One-shot MCP handshake probe against the live dual-port server."""
import json
import urllib.request

URL = "http://127.0.0.1:9021/mcp"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "vp-diag", "version": "1.0"},
    },
}
TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


def post(payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        try:
            return {"status": resp.status, "session": resp.headers.get("Mcp-Session-Id"), "json": json.loads(text)}
        except json.JSONDecodeError:
            return {"raw": text[:400]}


def main() -> None:
    init = post(INIT)
    print("initialize =>", json.dumps(init, ensure_ascii=False)[:400])
    session = init.get("session")
    if session:
        # include session header for tools/list
        body = json.dumps(TOOLS).encode()
        req = urllib.request.Request(
            URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Mcp-Session-Id": session,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        data = json.loads(text)
        names = [t.get("name") for t in data.get("result", {}).get("tools", [])]
        print("tools/list =>", len(names), names)


if __name__ == "__main__":
    main()