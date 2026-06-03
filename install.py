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

    # Step 3: Global MCP Configs (Kimi Code, Roo Code, Cline)
    step.count += 1; step("Configuring Global MCP settings (Kimi 9021, Roo/Zoo 9020)")
    
    # Configure KIMI CODE (HTTP transport on 9021)
    KIMI_MCP_DIR = Path.home() / ".kimi"
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
    ROO_MCP_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~/.config"))) / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings"
    if ROO_MCP_DIR.parent.exists():
        ROO_MCP_DIR.mkdir(parents=True, exist_ok=True)
        roo_mcp_file = ROO_MCP_DIR / "cline_mcp_settings.json"
        roo_cfg = {"mcpServers": {}}
        if roo_mcp_file.exists():
            try:
                with open(roo_mcp_file, "r") as f: roo_cfg = json.load(f)
            except: pass
        if "mcpServers" not in roo_cfg: roo_cfg["mcpServers"] = {}
        roo_cfg["mcpServers"]["crow_memory"] = {"url": "http://127.0.0.1:9020/sse"}
        with open(roo_mcp_file, "w") as f: json.dump(roo_cfg, f, indent=2)
    ok()

    # Step 4: Custom mode (merge with existing modes if present)
    step.count += 1; step(MSGS.get("step_4_custom_mode", "Configuring Zoo Code auto-activation mode"))
    import yaml as _yaml
    new_mode_dict = _yaml.safe_load(YAML_MODE) or {}
    
    for settings_dir in [ZOO_SETTINGS, ROO_MCP_DIR]:
        if not settings_dir.parent.exists(): continue
        settings_dir.mkdir(parents=True, exist_ok=True)
        mode_path = settings_dir / "cline_custom_modes.json"
        
        existing = {}
        if mode_path.exists():
            try:
                with open(mode_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
                
        existing_modes = existing.get("customModes", [])
        existing_modes = [m for m in existing_modes if m.get("slug") not in ("orchestrator-crow", "code-crow")]
        existing_modes.extend(new_mode_dict.get("customModes", []))
        existing["customModes"] = existing_modes
        
        with open(mode_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    ok()

    # Step 5: Start SSE server + auto-start registration
    step.count += 1; step(MSGS.get("step_5_start_server", "Starting Crow SSE server + auto-start"))
    bat_path = CROW_DIR / "start_crow_sse.bat"

    if os.name == "nt":
        subprocess.Popen(
            [str(bat_path)],
            cwd=str(CROW_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.exists():
            import shutil
            bat_dst = startup_dir / "Crow_Memory_SSE.bat"
            shutil.copy2(str(bat_path), str(bat_dst))
            print(f"\n  [Auto-start] Registered in Startup: {bat_dst}")
    ok()

    print()
    print(f"\033[92m============================================\033[0m")
    print(f"\033[92m  {MSGS.get('complete_title', 'Crow Memory installation complete!')}\033[0m")
    print(f"\033[92m============================================\033[0m")
    print()
    print(f"  {MSGS.get('sse_running', 'SSE server running on http://127.0.0.1:9020/sse (HTTP on 9021)')}")
    print()
    print(f"  {MSGS.get('next_steps_label', 'Next steps:')}")
    for step_item in MSGS.get("next_steps", [
        "1. Restart your IDE (Zoo Code / Kimi Code / Roo Code)",
        "2. For Zoo Code: Switch mode to 'Orchestrator + Crow'",
        "3. Server auto-starts with Windows (registered in Startup)"
    ]):
        print(f"  {step_item}")
    print()

if __name__ == "__main__":
    main()
