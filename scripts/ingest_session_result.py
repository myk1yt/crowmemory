# -*- coding: utf-8 -*-
"""Store session bug-fix outcome into Crow Memory via REST API."""
import json
import urllib.request

payload = {
    "key": "Crow SSE hang fix - launcher health check + client config sync (v1.4.5)",
    "value": (
        "Symptom: server LISTENING + HTTP /mcp OK but other-session MCP clients "
        "report connection errors. Two stacked defects: (1) stale manually-launched "
        "server process SSE-hung (endpoint event never sent) while HTTP app stayed "
        "healthy; (2) bat launcher health check hit '/' which 404s under MCP SDK "
        "2.x, so the official launcher kept failing and a stale system-python "
        "server lingered. Fix: taskkill stale PID; bat health check now /health; "
        "Zoo global crow-memory switched SSE 9020 -> streamable-http 9021/mcp. "
        "Verification: SSE first line 'data: /messages/...' now arrives in <1s; "
        "/mcp handshake + tools/list 10 tools OK. Lesson: with every SDK transport "
        "migration, update launcher health-check path AND client configs together."
    ),
    "polarity": 1.0,
    "register": "bug",
}

req = urllib.request.Request(
    "http://127.0.0.1:9021/ingest",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as resp:
    print("HTTP", resp.status)
    print(resp.read().decode("utf-8", errors="replace")[:300])