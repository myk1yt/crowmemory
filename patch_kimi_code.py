#!/usr/bin/env python3
"""
patch_kimi_code.py — Eternal Crow Memory patch for Kimi Code CLI.

Run this script after every Kimi Code CLI update to restore auto-ingest:
    python patch_kimi_code.py

To restore original system.md:
    python patch_kimi_code.py --restore
"""

import sys
import shutil
import argparse
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

CROW_DIR = Path(__file__).parent.resolve()

# Auto-detect Kimi Code CLI installation path
KIMI_AGENT_DIR = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "Code"
    / "User"
    / "globalStorage"
    / "moonshot-ai.kimi-code"
    / "bin"
    / "kimi"
    / "_internal"
    / "kimi_cli"
    / "agents"
    / "default"
)

SYSTEM_MD = KIMI_AGENT_DIR / "system.md"
BACKUP_MD = KIMI_AGENT_DIR / "system.md.crow_backup"

# The auto-ingest Crow Memory section (matches the patched version)
CROW_SECTION = """# Crow Memory (Auto-Activation)

You have access to **Crow Memory**, an external synaptic memory system connected via MCP.
It stores the user's coding style, bug intuition, architectural preferences, and personal context as compressed weight matrices.

**UNIVERSAL RECALL (MANDATORY): Before EVERY response — whether coding, writing, editing, or conversation — call `crow_recall(domain="all")` to retrieve the user's coding style, bug intuition, architectural preferences, personal taste, life philosophy, and current context.** `domain="all"` (the default) queries all **8 registers** (style, bug, arch, context, life_pref, life_avoid, life_phil, life_context) in a single call. Use the returned hints to personalize your response. Never skip this step.

**AUTO-INGEST (MANDATORY): After EVERY response, evaluate what the user revealed — a preference, a philosophy, a frustration, a pattern, a correction, ongoing plans, or explicit decision. Call `crow_ingest` with the appropriate register, a concise key/value summary, and appropriate polarity.** Do NOT wait for the user to say "remember this." For code work, also call `crow_ingest_from_build`.

**POLARITY GUIDE** (auto-determined, no user command needed):
- User likes / prefers something → +1.5 (`life_pref` / `style`)
- User reveals philosophy / values → +2.0 (`life_phil`)
- User corrects you / rewrites your work → -1.0 (`bug` / `style`)
- User shares ongoing context / plans → +1.5 (`life_context` / `context`)
- User explicitly says "remember" / "never forget" → +2.0 / -2.0
- User shows frustration / avoidance → -0.5 (`life_avoid` / `bug`)

Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia."""

# ── Functions ──────────────────────────────────────────────────────────────


def ensure_backup():
    """Create a backup of the original system.md if not already backed up."""
    if not BACKUP_MD.exists():
        if SYSTEM_MD.exists():
            shutil.copy2(SYSTEM_MD, BACKUP_MD)
            print(f"  [Backup] Created: {BACKUP_MD}")
        else:
            print(f"  [Error] system.md not found at: {SYSTEM_MD}")
            sys.exit(1)


def is_already_patched(content: str) -> bool:
    """Check if system.md already contains the auto-ingest patch."""
    return "AUTO-INGEST (PROACTIVE MEMORY):" in content


def apply_patch():
    """Replace the Crow Memory section with the auto-ingest version."""
    ensure_backup()

    content = SYSTEM_MD.read_text(encoding="utf-8")

    if is_already_patched(content):
        print("  [Skip] Already patched. No changes needed.")
        return

    # Find the Crow Memory section boundaries
    start_marker = "# Crow Memory (Auto-Activation)"
    end_marker = "Crow is not a database"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        # Clean installation — no existing Crow section. Append to end.
        print("  [Info] No existing Crow section found. Appending to end of system.md...")
        new_content = content.rstrip() + "\n\n" + CROW_SECTION + "\n"
        SYSTEM_MD.write_text(new_content, encoding="utf-8")
        print("  [Done] Crow Memory section appended successfully.")
        print(f"  [Path] {SYSTEM_MD}")
        return

    # end_marker includes the line itself, so advance to end of that line
    end_idx = content.find("\n", end_idx)
    if end_idx == -1:
        end_idx = len(content)

    new_content = content[:start_idx] + CROW_SECTION + content[end_idx:]
    SYSTEM_MD.write_text(new_content, encoding="utf-8")
    print("  [Done] Auto-ingest patch applied successfully.")
    print(f"  [Path] {SYSTEM_MD}")


def restore_backup():
    """Restore the original system.md from backup."""
    if not BACKUP_MD.exists():
        print("  [Error] No backup found to restore.")
        sys.exit(1)

    shutil.copy2(BACKUP_MD, SYSTEM_MD)
    print("  [Done] Original system.md restored from backup.")
    print(f"  [Path] {SYSTEM_MD}")


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Eternal Crow Memory patch for Kimi Code CLI"
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore original system.md from backup",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Crow Memory — Kimi Code CLI Patch Tool")
    print("=" * 60)
    print()

    if not SYSTEM_MD.exists():
        print(f"  [Error] Kimi Code CLI not found at expected path:")
        print(f"  {SYSTEM_MD}")
        print()
        print("  The installation path may have changed with an update.")
        print("  Please locate system.md manually and update KIMI_AGENT_DIR.")
        sys.exit(1)

    if args.restore:
        restore_backup()
    else:
        apply_patch()

    print()
    print("  Tip: Run this script after every Kimi Code CLI update.")
    print("       python patch_kimi_code.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
