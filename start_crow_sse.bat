@echo off
REM Crow Memory SSE Server — Robust auto-start script
REM Features:
REM   1. Checks if server is already running on port 9020
REM   2. Cleans up stale lock files before starting
REM   3. Starts server in background and logs output
REM
REM Can be called from VS Code tasks.json (folderOpen) or Windows Startup.
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PORT=9020"
set "LOG_FILE=%~dp0sse_server.log"
set "LOCK_FILE=%~dp0memory\crow.bin.lock"
set "STATE_PATH=%~dp0memory\crow.bin"

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

REM ---- Start SSE server in background ----
echo [%date% %time%] Starting Crow Memory SSE server on port %PORT%... >> "%LOG_FILE%"
start /b "" python "%~dp0crow_mcp_server.py" --state "%STATE_PATH%" --transport sse --port %PORT% >> "%LOG_FILE%" 2>&1

REM ---- Wait a moment and verify it started ----
timeout /t 3 /nobreak >nul
netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] Crow SSE server started successfully. >> "%LOG_FILE%"
) else (
    echo [%date% %time%] WARNING: Server may not have started. Check sse_server.log for errors. >> "%LOG_FILE%"
)

endlocal
