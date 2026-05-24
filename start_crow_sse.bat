@echo off
REM Crow Memory SSE Server — Manual start reference script
REM NOTE: install.py / install.ps1 now generate a Startup bat with absolute paths.
REM Use this script only for manual testing from the project directory.
cd /d "%~dp0"
start /b python crow_mcp_server.py --state ./memory/crow.bin --transport sse --port 9020 > sse_server.log 2>&1
