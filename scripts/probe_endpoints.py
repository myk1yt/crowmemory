# -*- coding: utf-8 -*-
"""Endpoint probe for Crow Memory MCP connectivity diagnosis.

Measures raw HTTP/SSE responses for:
- GET  http://127.0.0.1:9020/sse   (SSE stream handshake)
- GET  http://127.0.0.1:9020/      (SSE app root)
- GET  http://127.0.0.1:9021/      (HTTP app root)
- POST http://127.0.0.1:9021/      (HTTP root POST)
- GET  http://127.0.0.1:9021/mcp   (HTTP MCP endpoint GET)
- POST http://127.0.0.1:9021/mcp   (no-body POST, expect 4xx not 404)

Read-only diagnostics. No server state is modified (no initialize sent).
"""
import http.client
import json
import socket

HOST, SSE_PORT, HTTP_PORT = "127.0.0.1", 9020, 9021
TIMEOUT = 4


def probe(port, method, path, headers=None, body=None, read_bytes=512):
    conn = http.client.HTTPConnection(HOST, port, timeout=TIMEOUT)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = b""
        try:
            data = resp.read(read_bytes)
        except socket.timeout:
            data = b"<timeout while reading body>"
        return {
            "status": resp.status,
            "reason": resp.reason,
            "headers": dict(resp.getheaders()),
            "body_preview": data.decode("utf-8", "replace")[:300],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sse_probe():
    """GET /sse with event-stream accept; read first events then close."""
    conn = http.client.HTTPConnection(HOST, SSE_PORT, timeout=TIMEOUT)
    try:
        conn.request("GET", "/sse", headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        ctype = resp.getheader("Content-Type", "")
        chunk = b""
        try:
            chunk = resp.read(512)
        except socket.timeout:
            chunk = b"<timeout waiting for first event>"
        return {
            "status": resp.status,
            "content_type": ctype,
            "first_bytes": chunk.decode("utf-8", "replace")[:400],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


results = {
    "SSE 9020 GET /sse": sse_probe(),
    "SSE 9020 GET /": probe(SSE_PORT, "GET", "/"),
    "HTTP 9021 GET /": probe(HTTP_PORT, "GET", "/"),
    "HTTP 9021 POST /": probe(
        HTTP_PORT, "POST", "/",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        body=b"{}",
    ),
    "HTTP 9021 GET /mcp": probe(HTTP_PORT, "GET", "/mcp"),
    "HTTP 9021 POST /mcp (empty)": probe(
        HTTP_PORT, "POST", "/mcp",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        body=b"{}",
    ),
    "HTTP 9021 GET /sse (wrong-port sanity)": probe(HTTP_PORT, "GET", "/sse"),
}

print(json.dumps(results, indent=2, ensure_ascii=False))
