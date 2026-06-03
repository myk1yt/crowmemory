@echo off
REM Crow Memory SSE Server — Robust auto-start
REM Launches server FULLY DETACHED from VS Code so it survives IDE restarts.
REM Checks port, cleans stale locks, polls health endpoint with backoff.
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PORT=9020"
set "HTTP_PORT=9021"
set "LOG_FILE=%~dp0sse_server.log"
set "LOCK_FILE=%~dp0memory\crow.bin.lock"
set "STATE_PATH=%~dp0memory\crow.bin"
set "READY_FILE=%~dp0memory\.crow_ready"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] Crow SSE server already running on port %PORT%. Skipping. >> "%LOG_FILE%"
    exit /b 0
)

if exist "%LOCK_FILE%" (
    set /p STALE_PID=<"%LOCK_FILE%"
    tasklist /fi "PID eq !STALE_PID!" 2>nul | findstr "!STALE_PID!" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [%date% %time%] Removing stale lock (PID !STALE_PID! dead). >> "%LOG_FILE%"
        del "%LOCK_FILE%" 2>nul
    ) else (
        echo [%date% %time%] Lock held by live PID !STALE_PID!. Aborting. >> "%LOG_FILE%"
        exit /b 1
    )
)

if exist "%READY_FILE%" del "%READY_FILE%" 2>nul

echo [%date% %time%] Starting Crow Memory SSE server (detached) on port %PORT%... >> "%LOG_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath 'python' -ArgumentList '-X utf8 \"%~dp0crow_mcp_server.py\" --state \"%STATE_PATH%\" --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file \"%READY_FILE%\"' -WindowStyle Hidden -PassThru; ^
   Write-Output $p.Id" >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Waiting for server to become ready... >> "%LOG_FILE%"
set "ATTEMPT=0"
set "MAX_ATTEMPTS=30"
set "READY=0"

:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! gtr !MAX_ATTEMPTS! goto :wait_done

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/sse' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1

if !ERRORLEVEL! equ 0 (
    set "READY=1"
    goto :wait_done
)

if !ATTEMPT! leq 1 set "SLEEP=500"
if !ATTEMPT! equ 2 set "SLEEP=1000"
if !ATTEMPT! equ 3 set "SLEEP=2000"
if !ATTEMPT! equ 4 set "SLEEP=4000"
if !ATTEMPT! geq 5 set "SLEEP=8000"

powershell -NoProfile -Command "Start-Sleep -Milliseconds !SLEEP!" 2>nul
if !ERRORLEVEL! neq 0 (
    set /a TIMEOUT_SEC=(!SLEEP! + 999) / 1000
    timeout /t !TIMEOUT_SEC! /nobreak >nul
)

goto :wait_loop

:wait_done
if "!READY!" equ "1" (
    echo [%date% %time%] Crow SSE server ready (attempt !ATTEMPT!). >> "%LOG_FILE%"
) else (
    echo [%date% %time%] WARNING: Server did not become ready. Check sse_server.log. >> "%LOG_FILE%"
)
endlocal
