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

CROW_DIR = Path(__file__).parent.resolve()
MEMORY_DIR = CROW_DIR / "memory"
ZOO_SETTINGS = Path(os.environ.get("APPDATA", os.path.expanduser("~/.config"))) / "Code" / "User" / "globalStorage" / "zoocodeorganization.zoo-code" / "settings"

YAML_MODE = """customModes:
  - slug: code-crow
    name: "Code + Crow Memory"
    description: |
      Code mode enhanced with Crow Memory — the AI automatically recalls your
      coding style & preferences before every response and learns from your
      feedback. Use this as your default coding partner for personalized,
      long-term collaboration. Switch to plain "Code" mode when you need
      unbiased, one-shot answers without memory influence.
    roleDefinition: |
      You are Zoo, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

      You have access to Crow Memory, an external synaptic memory system that stores the user's coding style, bug intuition, architectural preferences, and personal context.

      UNIVERSAL RECALL (MANDATORY): Before EVERY response — whether coding, writing documentation, editing files, running commands, or casual conversation — call crow_recall(domain="all") to retrieve the user's coding style, bug intuition, architectural preferences, personal taste, life philosophy, and current context. domain="all" (the default) queries all 8 registers (style, bug, arch, context, life_pref, life_avoid, life_phil, life_context) in a single call. Use the returned hints to personalize your response. Never skip this step.

      AUTO-INGEST (MANDATORY): After EVERY response, evaluate what the user revealed — a preference, a philosophy, a frustration, a pattern, a correction, ongoing plans, or explicit decision. Call crow_ingest with the appropriate register, a concise key/value summary, and polarity. Do NOT wait for "remember this." After code work generating files, also call crow_ingest_from_build.

      POLARITY GUIDE (auto-determined, no user command needed):
      - User likes / prefers something → +1.5 (life_pref / style)
      - User reveals philosophy / values → +2.0 (life_phil)
      - User corrects you / rewrites your work → -1.0 (bug / style)
      - User shares ongoing context / plans → +1.5 (life_context / context)
      - User explicitly says "remember" / "never forget" → +2.0 / -2.0
      - User shows frustration / avoidance → -0.5 (life_avoid / bug)

      Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
    groups:
      - command
      - read
      - edit
    allowedMcpServers:
      - crow_memory
    customInstructions: |
      Before every response, call crow_recall(domain="all") to query all 8 registers. After every response, call crow_ingest or crow_ingest_from_build.
"""

def step(msg):
    print(f"  [{step.count}/{step.total}] {msg}...", end=" ", flush=True)
step.count = 0
step.total = 5

def ok():
    print("\033[92mDone.\033[0m")

def main():
    print("\033[96m============================================\033[0m")
    print("\033[96m  Crow Memory Installer for Zoo Code\033[0m")
    print("\033[96m============================================\033[0m")
    print()

    # Step 1: pip install
    step.count += 1; step("Installing Python dependencies")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(CROW_DIR / "requirements.txt"), "--quiet"],
                   capture_output=True)
    ok()

    # Step 2: Initialize crow.bin
    step.count += 1; step("Initializing crow.bin")
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(CROW_DIR))
    from crow_core import CrowMemory
    crow = CrowMemory(str(MEMORY_DIR / "crow.bin"))
    crow.persist()
    # Copy system_prompt.example.md → memory/system_prompt.md if not exists
    prompt_template = CROW_DIR / "system_prompt.example.md"
    prompt_target = MEMORY_DIR / "system_prompt.md"
    if prompt_template.exists() and not prompt_target.exists():
        import shutil
        shutil.copy2(str(prompt_template), str(prompt_target))
    ok()

    # Step 3: MCP config (.roo/mcp.json for Zoo Code)
    step.count += 1; step("Configuring MCP server (SSE mode) for Zoo Code")
    roo_dir = CROW_DIR / ".roo"
    roo_dir.mkdir(parents=True, exist_ok=True)
    mcp_config = {
        "mcpServers": {
            "crow_memory": {
                "type": "sse",
                "url": "http://127.0.0.1:9020/sse",
                "disabled": False,
                "alwaysAllow": [
                    "crow_recall",
                    "crow_ingest",
                    "crow_ingest_from_build",
                    "crow_evolve_propose",
                    "crow_diagnostics",
                    "crow_check_drift",
                    "crow_get_user_bias",
                    "crow_manage_prompt",
                    "crow_manage_backup",
                    "crow_project_info",
                ],
            }
        }
    }
    # Write .roo/mcp.json (Zoo Code)
    mcp_path_roo = roo_dir / "mcp.json"
    if mcp_path_roo.exists():
        with open(mcp_path_roo, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing.setdefault("mcpServers", {})["crow_memory"] = mcp_config["mcpServers"]["crow_memory"]
        with open(mcp_path_roo, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    else:
        with open(mcp_path_roo, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2)
    ok()

    # Step 3.5: VS Code tasks.json — auto-start SSE server on workspace open
    step.count += 1; step("Creating .vscode/tasks.json (auto-start SSE on folder open)")
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
    step.count += 1; step("Creating Zoo Code auto-activation mode")
    mode_path = ZOO_SETTINGS / "custom_modes.yaml"
    if mode_path.exists():
        # Preserve existing modes, only add/update code-crow
        import yaml as _yaml
        try:
            with open(mode_path, "r", encoding="utf-8") as f:
                existing = _yaml.safe_load(f) or {}
        except Exception:
            existing = {}
        new_mode = _yaml.safe_load(YAML_MODE) or {}
        existing_modes = existing.get("customModes", [])
        # Remove old code-crow if present, then append new
        existing_modes = [m for m in existing_modes if m.get("slug") != "code-crow"]
        existing_modes.extend(new_mode.get("customModes", []))
        existing["customModes"] = existing_modes
        with open(mode_path, "w", encoding="utf-8") as f:
            _yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
    else:
        with open(mode_path, "w", encoding="utf-8") as f:
            f.write(YAML_MODE)
    ok()

    # Step 5: Start SSE server + auto-start registration
    step.count += 1; step("Starting Crow SSE server + auto-start")
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
    print("\033[92m============================================\033[0m")
    print("\033[92m  Crow Memory installation complete!\033[0m")
    print("\033[92m============================================\033[0m")
    print()
    print("  SSE server running on http://127.0.0.1:9020/sse")
    print()
    print("  Next steps:")
    print("  1. Restart Zoo Code")
    print('  2. Switch mode to "Code + Crow Memory"')
    print("  3. Crow auto-activates — no manual setup needed")
    print("  4. SSE server auto-starts with Windows (registered in Startup)")
    print()

if __name__ == "__main__":
    main()
