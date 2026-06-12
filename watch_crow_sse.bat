@echo off
REM Crow SSE Server Watchdog
REM Polls port 9020 every 30 seconds.
REM If the server is not running, starts it automatically via start_crow_sse.bat.
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "LOG_FILE=%~dp0sse_server.log"
set "PORT=9020"

echo [%date% %time%] [INFO] [Watchdog] Started. Polling port %PORT% every 30s. >> "%LOG_FILE%"

:loop
timeout /t 30 /nobreak >nul

REM Check if server is listening on port 9020
netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [%date% %time%] [WARN] [Watchdog] Server is down on port %PORT%. Starting... >> "%LOG_FILE%"
    call "%~dp0start_crow_sse.bat"
) else (
    echo [%date% %time%] [INFO] [Watchdog] Server is running on port %PORT%. >> "%LOG_FILE%"
)
goto loop

endlocal
