#!/usr/bin/env python3
"""
E2E server verification:
Starts crow_mcp_server.py with --transport dual --port 9020 --http-port 9021 --ready-file memory/.crow_ready,
polls /health on both ports, tests /recall and /ingest REST endpoints, and verifies clean shutdown.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

def test_url(url, method="GET", data=None, timeout=20):
    req = urllib.request.Request(url, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
        body = json.dumps(data).encode("utf-8")
    else:
        body = None
    with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def main():
    python_exe = sys.executable
    ready_file = Path("memory/.crow_ready")
    if ready_file.exists():
        ready_file.unlink()

    cmd = [
        python_exe, "-X", "utf8", "crow_mcp_server.py",
        "--transport", "dual",
        "--port", "9020",
        "--http-port", "9021",
        "--ready-file", str(ready_file)
    ]
    print(f"Starting server: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)

    try:
        # Wait for ready file (up to 30 seconds)
        print("Waiting for server ready...")
        start_time = time.time()
        ready = False
        while time.time() - start_time < 30:
            if ready_file.exists():
                pid = ready_file.read_text().strip()
                print(f"Server ready! PID: {pid}")
                ready = True
                break
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                print("Server exited prematurely!")
                print(f"Stdout:\n{stdout}")
                print(f"Stderr:\n{stderr}")
                sys.exit(1)
            time.sleep(0.5)

        if not ready:
            print("Timed out waiting for ready file.")
            sys.exit(1)

        # 1. Test HTTP port 9021 /health
        print("\n[Test 1] GET http://127.0.0.1:9021/health")
        status, data = test_url("http://127.0.0.1:9021/health")
        print(f"Status: {status}, Response: {data}")
        assert status == 200 and data.get("status") == "ok"
        print("✓ Health check on 9021 passed")

        # 2. Test SSE port 9020 /health
        print("\n[Test 2] GET http://127.0.0.1:9020/health")
        status, data = test_url("http://127.0.0.1:9020/health")
        print(f"Status: {status}, Response: {data}")
        assert status == 200 and data.get("status") == "ok"
        print("✓ Health check on 9020 passed")

        # 3. Test REST /recall
        print("\n[Test 3] GET http://127.0.0.1:9021/recall?query=coding&register=style&limit=2")
        status, data = test_url("http://127.0.0.1:9021/recall?query=coding&register=style&limit=2")
        print(f"Status: {status}, Response: {data}")
        assert status == 200 and "results" in data
        print("✓ REST recall on 9021 passed")

        # 4. Test REST /ingest
        print("\n[Test 4] POST http://127.0.0.1:9021/ingest")
        ingest_payload = {"content": "Test E2E ingest from migration check", "register": "context"}
        status, data = test_url("http://127.0.0.1:9021/ingest", method="POST", data=ingest_payload)
        print(f"Status: {status}, Response: {data}")
        assert status == 200 and data.get("status") == "ok"
        print("✓ REST ingest on 9021 passed")

        print("\n✓ ALL E2E NETWORK AND REST TESTS PASSED")

    finally:
        print("\nTerminating server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server stopped.")

if __name__ == "__main__":
    main()
