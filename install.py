#!/usr/bin/env python3
"""
Crow Memory — Cross-platform installer for Zoo Code, Roo Code, Cline, and Kimi Code.
Run: python install.py
"""

import os
import sys
import json
import subprocess
from pathlib import Path
import shutil

CROW_DIR = Path(__file__).parent.resolve()
MEMORY_DIR = CROW_DIR / "memory"

# Paths for global configs
ZOO_SETTINGS = Path(os.environ.get("APPDATA", os.path.expanduser("~/.config"))) / "Code" / "User" / "globalStorage" / "zoocodeorganization.zoo-code" / "settings"
KIMI_MCP_DIR = Path.home() / ".kimi"
ROO_MCP_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~/.config"))) / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings"

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
step.total = 5

def ok():
    print(f"\033[92mDone.\033[0m")

def main():
    print("\033[96m============================================\033[0m")
    print(f"\033[96m  Crow Memory Installer\033[0m")
    print("\033[96m============================================\033[0m")
    print()

    # Step 1: pip install
    step.count += 1; step("Installing Python dependencies")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(CROW_DIR / "requirements.txt"), "--quiet"],
                   capture_output=True)
    ok()

    # Step 2: Initialize crow.bin
    step.count += 1; step("Initializing crow.bin and system prompt")
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(CROW_DIR))
    from crow_core import CrowMemory
    crow = CrowMemory(str(MEMORY_DIR / "crow.bin"))
    crow.persist()

    prompt_template = CROW_DIR / "system_prompt.example.md"
    prompt_target = MEMORY_DIR / "system_prompt.md"
    if prompt_template.exists() and not prompt_target.exists():
        shutil.copy2(str(prompt_template), str(prompt_target))
    ok()

    # Step 3: Global MCP Configs (KIMI Code, Roo Code, Cline)
    step.count += 1; step("Configuring Global MCP settings (Kimi 9021, Roo/Zoo 9020)")
    
    # Configure KIMI CODE (HTTP transport on 9021)
    KIMI_MCP_DIR.mkdir(parents=True, exist_ok=True)
    kimi_mcp_file = KIMI_MCP_DIR / "mcp.json"
    kimi_cfg = {"mcpServers": {}}
    if kimi_mcp_file.exists():
        try:
            with open(kimi_mcp_file, "r") as f: kimi_cfg = json.load(f)
        except: pass
    if "mcpServers" not in kimi_cfg: kimi_cfg["mcpServers"] = {}
    kimi_cfg["mcpServers"]["crow_memory"] = {"transport": "http", "url": "http://127.0.0.1:9021/"}
    with open(kimi_mcp_file, "w") as f: json.dump(kimi_cfg, f, indent=2)

    # Configure ROO CODE / CLINE (SSE transport on 9020)
    if ROO_MCP_DIR.parent.exists():
        ROO_MCP_DIR.mkdir(parents=True, exist_ok=True)
        roo_mcp_file = ROO_MCP_DIR / "cline_mcp_settings.json"
        roo_cfg = {"mcpServers": {}}
        if roo_mcp_file.exists():
            try:
                with open(roo_mcp_file, "r") as f: roo_cfg = json.load(f)
            except: pass
        if "mcpServers" not in roo_cfg: roo_cfg["mcpServers"] = {}
        roo_cfg["mcpServers"]["crow_memory"] = {"command": "python", "args": [str(CROW_DIR / "crow_mcp_server.py"), "--transport", "stdio", "--state", str(MEMORY_DIR / "crow.bin")]}
        # We also recommend dual mode SSE for background server via tasks.json
        with open(roo_mcp_file, "w") as f: json.dump(roo_cfg, f, indent=2)
    ok()

    # Step 4: Custom mode for Zoo Code
    step.count += 1; step("Configuring Zoo Code auto-activation mode")
    mode_path = ZOO_SETTINGS / "custom_modes.yaml"
    if ZOO_SETTINGS.parent.exists():
        ZOO_SETTINGS.mkdir(parents=True, exist_ok=True)
        if mode_path.exists():
            import yaml as _yaml
            try:
                with open(mode_path, "r", encoding="utf-8") as f:
                    existing = _yaml.safe_load(f) or {}
            except Exception:
                existing = {}
            new_mode = _yaml.safe_load(YAML_MODE) or {}
            existing_modes = existing.get("customModes", [])
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
    step.count += 1; step("Starting Crow SSE server + auto-start")
    bat_path = CROW_DIR / "start_crow_sse.bat"

    subprocess.Popen(
        [str(bat_path)],
        cwd=str(CROW_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if os.name == "nt":
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.exists():
            bat_dst = startup_dir / "Crow_Memory_SSE.bat"
            shutil.copy2(str(bat_path), str(bat_dst))
            print(f"\n  [Auto-start] Registered in Startup: {bat_dst}")
    ok()

    print()
    print(f"\033[92m============================================\033[0m")
    print(f"\033[92m  Crow Memory installation complete!\033[0m")
    print(f"\033[92m============================================\033[0m")
    print()
    print(f"  SSE server running on http://127.0.0.1:9020/sse (HTTP on 9021)")
    print()
    print(f"  Next steps:")
    print(f"  1. Restart your IDE (Zoo Code / Kimi Code / Roo Code)")
    print(f"  2. For Zoo Code: Switch mode to 'Orchestrator + Crow'")
    print(f"  3. Server auto-starts with Windows (registered in Startup)")
    print()

if __name__ == "__main__":
    main()
