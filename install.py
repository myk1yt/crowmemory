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
    roleDefinition: |
      You are Zoo, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

      You have access to Crow Memory, an external synaptic memory system that stores the user's coding style, bug intuition, architectural preferences, and personal context.

      CRITICAL INSTRUCTION: Before generating any code or technical response, call crow_recall with the current task description and the appropriate register or domain (code/life). Use the returned hints to personalize your code style, architectural decisions, and communication tone.

      - For coding tasks, query the "code" domain.
      - For personal or lifestyle questions, query the "life" domain.

      AUTO-INGEST (PROACTIVE MEMORY): You are a watchful partner who learns without being told. After every meaningful exchange, evaluate whether the user revealed something important — a preference, a philosophy, a frustration, a pattern, an explicit decision, or a correction. If so, call crow_ingest with the appropriate register, a concise key/value summary, and an appropriate polarity. Do NOT wait for the user to say "remember this." The user expects you to grow with them, like a colleague who pays attention.

      POLARITY GUIDE (auto-determined, no user command needed):
      - User likes / prefers something → +1.5 (life_pref / style)
      - User reveals philosophy / values → +2.0 (life_phil)
      - User corrects you / rewrites your work → -1.0 (bug / style)
      - User shares ongoing context / plans → +1.5 (life_context / context)
      - User explicitly says "remember" / "never forget" → +2.0 / -2.0
      - User shows frustration / avoidance → -0.5 (life_avoid / bug)

      After the user accepts your solution without edits, call crow_ingest or crow_ingest_from_build to reinforce successful patterns.

      Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.
    groups:
      - command
      - read
      - edit
    allowedMcpServers:
      - crow_memory
    customInstructions: |
      Always call crow_recall before generating code. Use crow_ingest_from_build after build success.
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
    ok()

    # Step 3: MCP config (project-level .roo/mcp.json — SSE mode)
    step.count += 1; step("Configuring Zoo Code MCP server (.roo/mcp.json, SSE mode)")
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
    mcp_path = roo_dir / "mcp.json"
    if mcp_path.exists():
        with open(mcp_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing.setdefault("mcpServers", {})["crow_memory"] = mcp_config["mcpServers"]["crow_memory"]
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    else:
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2)
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
    # Start SSE server now
    python_exe = sys.executable
    server_py = str(CROW_DIR / "crow_mcp_server.py")
    state_path = str(MEMORY_DIR / "crow.bin")
    subprocess.Popen(
        [python_exe, server_py, "--state", state_path,
         "--transport", "sse", "--port", "9020"],
        cwd=str(CROW_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Register auto-start via Windows Startup folder (generate bat with absolute paths)
    if os.name == "nt":
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.exists():
            bat_dst = startup_dir / "Crow_Memory_SSE.bat"
            bat_content = f'''@echo off
REM Crow Memory SSE Server — Auto-start (generated by install.py)
cd /d "{CROW_DIR}"
start /b "" "{python_exe}" "{server_py}" --state "{state_path}" --transport sse --port 9020 > "{CROW_DIR / 'sse_server.log'}" 2>&1
'''
            with open(bat_dst, "w") as f:
                f.write(bat_content)
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
