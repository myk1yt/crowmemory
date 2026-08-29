import asyncio
import sys
from pathlib import Path
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))
import crow_mcp_server

mcp, crow = crow_mcp_server.create_server("./memory/crow.bin")
app = mcp.streamable_http_app(json_response=True)
client = TestClient(app)

print("1. Testing GET /health")
res = client.get("/health")
print("Status:", res.status_code, "Body:", res.json())

print("\n2. Testing GET /recall")
res = client.get("/recall?query=coding&register=style&limit=2")
print("Status:", res.status_code, "Body:", res.json())

print("\n3. Testing POST /ingest")
res = client.post("/ingest", json={"content": "test item", "register": "context"})
print("Status:", res.status_code, "Body:", res.json())
