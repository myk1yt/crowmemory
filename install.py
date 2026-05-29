#!/usr/bin/env python3
"""
Crow Memory — Cross-platform installer for Zoo Code.
Run: python install.py
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# i18n — Internationalization
# ---------------------------------------------------------------------------
try:
    from crow_i18n import detect_locale, get_installer_messages, get_text
    _I18N_LOCALE = detect_locale()
    _I18N_MSGS = get_installer_messages(_I18N_LOCALE)
    _I18N_AVAILABLE = True
except ImportError:
    _I18N_AVAILABLE = False
    _I18N_MSGS = None

_FALLBACK_MSGS = {
    "banner_title": "Crow Memory Installer for Zoo Code",
    "step_1_install_deps": "Installing Python dependencies",
    "step_2_init_crow": "Initializing crow.bin",
    "step_3_vscode_tasks": "Creating .vscode/tasks.json (auto-start SSE on folder open)",
    "step_4_custom_mode": "Creating Zoo Code auto-activation mode",
    "step_5_start_server": "Starting Crow SSE server + auto-start",
    "step_done": "Done.",
    "complete_title": "Crow Memory installation complete!",
    "sse_running": "SSE server running on http://127.0.0.1:9020/sse",
    "next_steps_label": "Next steps:",
    "next_steps": [
        "1. Restart Zoo Code",
        '2. Switch mode to "Orchestrator + Crow"',
        "3. Crow auto-activates \u2014 no manual setup needed",
        "4. SSE server auto-starts with Windows (registered in Startup)",
    ],
}

if _I18N_AVAILABLE:
    MSGS = _I18N_MSGS
else:
    MSGS = _FALLBACK_MSGS

CROW_DIR = Path(__file__).parent.resolve()
MEMORY_DIR = CROW_DIR / "memory"
ZOO_SETTINGS = Path(os.environ.get("APPDATA", os.path.expanduser("~/.config"))) / "Code" / "User" / "globalStorage" / "zoocodeorganization.zoo-code" / "settings"

YAML_MODE = """customModes:
  - slug: orchestrator-crow
    name: "Orchestrator + Crow"
    roleDefinition: |
      You are Zoo, a strategic workflow orchestrator who coordinates complex tasks by delegating them to appropriate specialized modes.

      ## CROW MEMORY INTEGRATION

      ### SESSION START (MANDATORY)
      At the beginning of every conversation session (i.e., your very first response to the user), you MUST call `crow_recall` to retrieve context about the user:
      - Call `crow_recall` with `domain="user"` to understand the user's personality, preferences, working style, and past interactions.
      - Call `crow_recall` with `domain="project"` to understand the current project context and recent activities.
      - Incorporate the recalled information into your understanding before proceeding with the task.

      ### SESSION END (MANDATORY)
      At the very end of the conversation session (i.e., your final response when the task is complete and you are about to call attempt_completion), you MUST call `crow_ingest` to save the session's key outcomes:
      - Summarize what was accomplished, key decisions made, and any important context for future sessions.
      - Call `crow_ingest` with the summary before your final `attempt_completion`.

      ### DURING SESSION (OPTIONAL)
      During the conversation, you may call `crow_recall` or `crow_ingest` as needed. Use your judgment.

      ## REGULAR ORCHESTRATOR BEHAVIOR
      All standard orchestrator mode capabilities remain intact.
    groups:
      - read
      - command
      - edit
      - browse
      - mcp
    allowedMcpServers:
      - crow_memory
"""

def step(msg):
    print(f"  [{step.count}/{step.total}] {msg}...", end=" ", flush=True)
step.count = 0
step.total = 4

def ok():
    done_msg = MSGS.get("step_done", "Done.")
    print(f"\033[92m{done_msg}\033[0m")

def main():
    print("\033[96m============================================\033[0m")
    print(f"\033[96m  {MSGS['banner_title']}\033[0m")
    print("\033[96m============================================\033[0m")
    print()

    # Step 1: pip install
    step.count += 1; step(MSGS["step_1_install_deps"])
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(CROW_DIR / "requirements.txt"), "--quiet"],
                   capture_output=True)
    ok()

    # Step 2: Initialize crow.bin
    step.count += 1; step(MSGS["step_2_init_crow"])
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(CROW_DIR))
    from crow_core import CrowMemory
    crow = CrowMemory(str(MEMORY_DIR / "crow.bin"))
    crow.persist()
    # Copy system_prompt.example/{locale}.md → memory/system_prompt.md if not exists
    if _I18N_AVAILABLE:
        locale_code = detect_locale()
        prompt_template = CROW_DIR / "system_prompt.example" / f"{locale_code}.md"
        if not prompt_template.exists():
            prompt_template = CROW_DIR / "system_prompt.example" / "en.md"
    else:
        prompt_template = CROW_DIR / "system_prompt.example.md"
    prompt_target = MEMORY_DIR / "system_prompt.md"
    if prompt_template.exists() and not prompt_target.exists():
        import shutil
        shutil.copy2(str(prompt_template), str(prompt_target))
    ok()

    # Step 3: VS Code tasks.json — auto-start SSE server on workspace open
    step.count += 1; step(MSGS["step_3_vscode_tasks"])
    vscode_dir = CROW_DIR / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    tasks_config = {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "Crow SSE Server — Auto Start",
                "detail": "Starts the Crow Memory SSE server on port 9020 when this workspace is opened. Zoo Code connects via SSE to share crow.bin.",
                "type": "shell",
                "command": f'cmd /c "{CROW_DIR}\\start_crow_sse.bat"',
                "isBackground": True,
                "problemMatcher": [],
                "runOptions": {"runOn": "folderOpen"},
                "presentation": {
                    "reveal": "silent",
                    "panel": "dedicated",
                    "showReuseMessage": False,
                    "clear": True,
                },
            },
            {
                "label": "Crow SSE Server — Stop",
                "detail": "Stops the Crow Memory SSE server.",
                "type": "shell",
                "command": 'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9020.*LISTENING\') do @taskkill /PID %a /F 2>nul',
                "problemMatcher": [],
                "presentation": {"reveal": "always", "panel": "dedicated"},
            },
        ],
    }
    tasks_path = vscode_dir / "tasks.json"
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(tasks_config, f, indent=2)
    ok()

    # Step 4: Custom mode (merge with existing modes if present)
    step.count += 1; step(MSGS["step_4_custom_mode"])
    mode_path = ZOO_SETTINGS / "custom_modes.yaml"
    if mode_path.exists():
        # Preserve existing modes, only add/update orchestrator-crow
        import yaml as _yaml
        try:
            with open(mode_path, "r", encoding="utf-8") as f:
                existing = _yaml.safe_load(f) or {}
        except Exception:
            existing = {}
        new_mode = _yaml.safe_load(YAML_MODE) or {}
        existing_modes = existing.get("customModes", [])
        # Remove old orchestrator-crow if present, then append new
        existing_modes = [m for m in existing_modes if m.get("slug") not in ("orchestrator-crow", "code-crow")]
        existing_modes.extend(new_mode.get("customModes", []))
        existing["customModes"] = existing_modes
        with open(mode_path, "w", encoding="utf-8") as f:
            _yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
    else:
        with open(mode_path, "w", encoding="utf-8") as f:
            f.write(YAML_MODE)
    ok()

    # Step 5: Start SSE server + auto-start registration
    step.count += 1; step(MSGS["step_5_start_server"])
    python_exe = sys.executable
    server_py = str(CROW_DIR / "crow_mcp_server.py")
    state_path = str(MEMORY_DIR / "crow.bin")

    # Generate robust start_crow_sse.bat (absolute paths, port check, stale lock cleanup)
    bat_path = CROW_DIR / "start_crow_sse.bat"
    bat_content = f'''@echo off
REM Crow Memory SSE Server — Robust auto-start (generated by install.py)
REM Launches server FULLY DETACHED from VS Code so it survives IDE restarts.
REM Checks port, cleans stale locks, polls health endpoint with backoff.
setlocal enabledelayedexpansion
cd /d "{CROW_DIR}"
set "PORT=9020"
set "HTTP_PORT=9021"
set "LOG_FILE={CROW_DIR / 'sse_server.log'}"
set "LOCK_FILE={MEMORY_DIR / 'crow.bin.lock'}"
set "STATE_PATH={state_path}"
set "READY_FILE={MEMORY_DIR / '.crow_ready'}"
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
  "$p = Start-Process -FilePath '{python_exe}' -ArgumentList '-X utf8 \\"{server_py}\\" --state \\"%STATE_PATH%\\" --transport dual --port %PORT% --http-port %HTTP_PORT% --ready-file \\"%READY_FILE%\\"' -WindowStyle Hidden -PassThru; ^
   Write-Output $p.Id" >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Waiting for server to become ready... >> "%LOG_FILE%"
set "ATTEMPT=0"
set "MAX_ATTEMPTS=30"
set "READY=0"

:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! gtr !MAX_ATTEMPTS! goto :wait_done

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try {{ $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/sse' -TimeoutSec 2 -UseBasicParsing; exit 0 }} catch {{ exit 1 }}" >nul 2>&1

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
'''
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Start SSE server now using the robust bat
    subprocess.Popen(
        [str(bat_path)],
        cwd=str(CROW_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Register auto-start via Windows Startup folder (copy the robust bat)
    if os.name == "nt":
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.exists():
            import shutil
            bat_dst = startup_dir / "Crow_Memory_SSE.bat"
            shutil.copy2(str(bat_path), str(bat_dst))
            print(f"\n  [Auto-start] Registered in Startup: {bat_dst}")
    ok()

    print()
    print(f"\033[92m============================================\033[0m")
    print(f"\033[92m  {MSGS['complete_title']}\033[0m")
    print(f"\033[92m============================================\033[0m")
    print()
    print(f"  {MSGS['sse_running']}")
    print()
    print(f"  {MSGS['next_steps_label']}")
    for step_item in MSGS["next_steps"]:
        print(f"  {step_item}")
    print()

if __name__ == "__main__":
    main()
