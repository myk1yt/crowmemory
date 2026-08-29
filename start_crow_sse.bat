@echo off
REM Crow Memory SSE Server - Robust auto-start
REM Launches server FULLY DETACHED from VS Code so it survives IDE restarts.
REM Checks port, cleans stale locks, polls health endpoint with backoff.
REM Supports automatic retry (max 2 attempts).
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

REM Prefer project virtualenv Python when present (dependencies live there)
set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

REM =====================================================================
REM Phase 1: 중복 실행 방지 - 포트가 이미 LISTEN 중이면 종료
REM =====================================================================
echo [%date% %time%] [INFO] Checking port %PORT%... >> "%LOG_FILE%"
netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [%date% %time%] [INFO] Crow SSE server already running on port %PORT%. Exiting. >> "%LOG_FILE%"
    exit /b 0
)
echo [%date% %time%] [INFO] Port %PORT% is free. >> "%LOG_FILE%"

REM =====================================================================
REM Phase 2: 스테일 상태 정리 - 이전 세션의 잔여 파일을 무조건 삭제
REM =====================================================================
if exist "%LOCK_FILE%" (
    echo [%date% %time%] [INFO] Removing stale lock file: %LOCK_FILE% >> "%LOG_FILE%"
    del "%LOCK_FILE%" 2>nul
) else (
    echo [%date% %time%] [INFO] No stale lock file found. >> "%LOG_FILE%"
)
if exist "%READY_FILE%" (
    echo [%date% %time%] [INFO] Removing stale ready file: %READY_FILE% >> "%LOG_FILE%"
    del "%READY_FILE%" 2>nul
) else (
    echo [%date% %time%] [INFO] No stale ready file found. >> "%LOG_FILE%"
)

REM =====================================================================
REM Phase 3: 서버 시작 (최대 2회 재시도)
REM =====================================================================
set "RETRY_COUNT=0"

:retry_start
set /a RETRY_COUNT+=1
echo [%date% %time%] [INFO] Starting Crow Memory SSE server (attempt !RETRY_COUNT!/2) on port %PORT%... >> "%LOG_FILE%"

REM 혹시 모를 좀비 프로세스 정리 (포트를 점유한 프로세스 kill)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo [%date% %time%] [WARN] Killing zombie process on port %PORT%: PID %%a >> "%LOG_FILE%"
    taskkill /PID %%a /F 2>nul
)

REM 파이썬 서버 시작 (detached, hidden window) — venv Python 우선
echo [%date% %time%] [INFO] Launching: "%PYTHON_EXE%" -X utf8 crow_mcp_server.py --state %STATE_PATH% --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file %READY_FILE% >> "%LOG_FILE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '-X utf8 \"%~dp0crow_mcp_server.py\" --state \"%STATE_PATH%\" --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file \"%READY_FILE%\"' -WindowStyle Hidden -PassThru; Write-Output (\"[%date% %time%] [INFO] Launched server PID: \" + $p.Id)" >> "%LOG_FILE%" 2>&1

REM =====================================================================
REM Phase 4: Health Check 대기 (backoff: 2s -> 2s -> 3s -> 5s...)
REM =====================================================================
set "MAX_ATTEMPTS=12"
set "ATTEMPT=0"
set "READY=0"
echo [%date% %time%] [INFO] Waiting for server health endpoint (max %MAX_ATTEMPTS% checks)... >> "%LOG_FILE%"

:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! gtr !MAX_ATTEMPTS! goto :wait_done

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1

if !ERRORLEVEL! equ 0 (
    set "READY=1"
    goto :wait_done
)

REM Backoff: 1s -> 1s -> 2s -> 3s (after attempt 4+)
if !ATTEMPT! leq 2 set "SLEEP=1000"
if !ATTEMPT! equ 3 set "SLEEP=2000"
if !ATTEMPT! geq 4 set "SLEEP=3000"

REM Sleep (try PowerShell first, fallback to timeout)
powershell -NoProfile -Command "Start-Sleep -Milliseconds !SLEEP!" 2>nul
if !ERRORLEVEL! neq 0 (
    set /a TIMEOUT_SEC=!SLEEP! + 999
    set /a TIMEOUT_SEC=!TIMEOUT_SEC! / 1000
    timeout /t !TIMEOUT_SEC! /nobreak >nul
)

goto :wait_loop

:wait_done
if "!READY!" equ "1" (
    echo [%date% %time%] [OK] Crow SSE server ready [attempt !RETRY_COUNT!/2, health check !ATTEMPT!/!MAX_ATTEMPTS!] >> "%LOG_FILE%"
    exit /b 0
) else (
    echo [%date% %time%] [WARN] Server health check failed on attempt !RETRY_COUNT!/2 [!ATTEMPT! checks] >> "%LOG_FILE%"
    if !RETRY_COUNT! lss 2 (
        echo [%date% %time%] [INFO] Retrying in 5 seconds [retry !RETRY_COUNT!/2]... >> "%LOG_FILE%"
        timeout /t 5 /nobreak >nul
        goto :retry_start
    ) else (
        echo [%date% %time%] [ERROR] Failed to start Crow SSE server after 2 attempts. >> "%LOG_FILE%"
        exit /b 1
    )
)

endlocal
