@echo off
REM Crow Memory SSE Server — Robust auto-start script
REM Features:
REM   1. Checks if server is already running on port 9020
REM   2. Cleans up stale lock files before starting
REM   3. Launches server fully DETACHED from VS Code (survives VS Code restart)
REM   4. Polls health endpoint with backoff to confirm readiness
REM
REM Called from VS Code tasks.json (folderOpen) or Windows Startup.
setlocal enabledelayedexpansion

chcp 65001 >nul
cd /d "%~dp0"

set "PORT=9020"
set "HTTP_PORT=9021"
set "LOG_FILE=%~dp0sse_server.log"
set "LOCK_FILE=%~dp0memory\crow.bin.lock"
set "STATE_PATH=%~dp0memory\crow.bin"
set "READY_FILE=%~dp0memory\.crow_ready"
set "PYTHONIOENCODING=utf-8"

REM ---- Check if already running on port 9020 ----
netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] Crow SSE server is already running on port %PORT%. Skipping start. >> "%LOG_FILE%"
    exit /b 0
)

REM ---- Clean up stale lock file (PID no longer alive) ----
if exist "%LOCK_FILE%" (
    set /p STALE_PID=<"%LOCK_FILE%"
    tasklist /fi "PID eq !STALE_PID!" 2>nul | findstr "!STALE_PID!" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [%date% %time%] Removing stale lock file (PID !STALE_PID! is dead). >> "%LOG_FILE%"
        del "%LOCK_FILE%" 2>nul
    ) else (
        echo [%date% %time%] Lock held by live PID !STALE_PID!. Aborting start. >> "%LOG_FILE%"
        exit /b 1
    )
)

REM ---- Remove stale ready file from previous run ----
if exist "%READY_FILE%" del "%READY_FILE%" 2>nul

REM ---- Start SSE server FULLY DETACHED from VS Code ----
REM    Uses PowerShell Start-Process -WindowStyle Hidden to create a process
REM    that is NOT a child of this cmd.exe. The server will survive VS Code close.
echo [%date% %time%] Starting Crow Memory SSE server (detached) on port %PORT%... >> "%LOG_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath 'python' -ArgumentList '\"%~dp0crow_mcp_server.py\" --state \"%STATE_PATH%\" --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file \"%READY_FILE%\"' -WindowStyle Hidden -PassThru; ^
   Write-Output $p.Id" >> "%LOG_FILE%" 2>&1

REM ---- Poll health endpoint with exponential backoff (max 30s) ----
echo [%date% %time%] Waiting for server to become ready... >> "%LOG_FILE%"
set "ATTEMPT=0"
set "MAX_ATTEMPTS=30"
set "READY=0"

:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! gtr !MAX_ATTEMPTS! goto :wait_done

REM Try curl-like check via PowerShell (no external deps)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/sse' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1

if !ERRORLEVEL! equ 0 (
    set "READY=1"
    goto :wait_done
)

REM Exponential backoff: 0.5s, 1s, 2s, 4s, 8s... capped at 8s
if !ATTEMPT! leq 1 set "SLEEP=0.5"
if !ATTEMPT! equ 2 set "SLEEP=1"
if !ATTEMPT! equ 3 set "SLEEP=2"
if !ATTEMPT! equ 4 set "SLEEP=4"
if !ATTEMPT! geq 5 set "SLEEP=8"

REM Use PowerShell for sub-second sleep
powershell -NoProfile -Command "Start-Sleep -Milliseconds !SLEEP!000" 2>nul
REM Fallback if powershell fails: use ping-based delay (1s granularity)
if !ERRORLEVEL! neq 0 timeout /t !SLEEP! /nobreak >nul

goto :wait_loop

:wait_done
if "!READY!" equ "1" (
    echo [%date% %time%] Crow SSE server ready (attempt !ATTEMPT!). >> "%LOG_FILE%"
) else (
    echo [%date% %time%] WARNING: Server did not become ready within !MAX_ATTEMPTS! attempts. MCP client may fail to connect. Check sse_server.log. >> "%LOG_FILE%"
)

endlocal
