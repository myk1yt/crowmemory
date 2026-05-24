@echo off
REM Crow Memory SSE Server — Auto-start script
REM Place this in Windows Startup folder for auto-launch on boot
cd /d "%~dp0"
start /b python crow_mcp_server.py --state ./memory/crow.bin --transport sse --port 9020 > sse_server.log 2>&1
