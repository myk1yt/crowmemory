#!/usr/bin/env python3
"""scripts/purge_search_debris.py — value_bank search-log debris purge (User
Decision [2026-09-02 07:18]).

Post-activation recall smoke test showed `life_context` returning debris like
"Search: translationMode → 0 AST + 0 line matches" instead of real memories.
Root cause: past sessions ingested VibeZoo search logs as memories;
accumulated importance let them survive the migrate scrub (scrub_text has no
rule for these prefixes).

Debris patterns (an entry is debris when EITHER its key OR its value matches,
checked against the STRIPPED text, case-sensitive):

    1. startswith("Search: ")          e.g. "Search: translationMode → 0 AST
                                          + 0 line matches"
    2. startswith("Web search success") or startswith("Web search failed")
                                       e.g. "Web search success: CTranslate2
                                          M2M-100..."
    3. --pattern REGEX (repeatable, default empty) — extra prefix regexes for
       future debris classes; matched with re.match against the stripped
       text. Kept deliberately simple: a pattern is a PREFIX regex.

Pipeline (the scripts/migrate_value_bank.py / merge_value_bank.py patterns):

    load value_bank JSON (utf-8)
      -> classify every entry (pure computation, no I/O — the SAME plan
         drives dry-run printing and the apply pass so dry-run numbers are
         honest)
      -> dry-run DEFAULT: print matched count + per-register breakdown +
         up to 20 example entries, ZERO writes
      -> --apply: timestamped backup BEFORE any write -> atomic write of the
         filtered list (tmp + os.replace) -> final count

    * Idempotent: a second run matches 0 entries and writes nothing.
    * crow.bin / weight matrix are NEVER touched — residual traces of purged
      entries in crow.bin decay naturally via the core's lambda decay.
    * Non-dict (malformed) entries are passed through untouched, never
      destroyed.
    * A live server holding value_bank in memory only rewrites on
      ingest/persist, so a dry-run read is safe. VP sequences the apply
      around a server restart so the in-memory copy cannot overwrite the
      purge.

Usage:
    .venv\\Scripts\\python.exe scripts/purge_search_debris.py
        # DRY-RUN (safe default) on memory/value_bank.json.
    .venv\\Scripts\\python.exe scripts/purge_search_debris.py --apply
        # Real purge: backup -> atomic write.

Exit codes: 0 = success (incl. clean dry-run / nothing-matched apply),
1 = error. All error paths carry PURGE/<function>/NNN codes.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

EXAMPLE_TRUNC = 80
DEFAULT_EXAMPLES = 20

# Built-in debris prefixes (case-sensitive, checked after str.strip()).
_PREFIXES = ("Search: ", "Web search success", "Web search failed")


# ---------------------------------------------------------------------------
# I/O (mirrors crow_core serialization exactly; kept standalone — the purge
# needs no encoder/vectors, so no crow_core/numpy import)
# ---------------------------------------------------------------------------

def load_value_bank(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"value_bank root is {type(data).__name__}, expected list "
            f"(PURGE/load/001)")
    return data


def save_value_bank_atomic(path: str, entries: list) -> None:
    """Atomic write mirroring crow_core._save_value_bank: tmp + os.replace,
    json.dump(ensure_ascii=False, indent=2), Windows retry (PURGE/save/001)."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    for attempt in range(3):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(0.05 * (2 ** attempt))
            else:
                raise


def backup_file(path: str) -> str:
    """Timestamped copy BEFORE any write (no-data-loss rule)."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak_path = f"{path}.bak.purge-{ts}-{os.getpid()}"
    shutil.copy2(path, bak_path)
    return bak_path


def _trunc(s: str, n: int = EXAMPLE_TRUNC) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Classification (deterministic; identical for dry-run and apply)
# ---------------------------------------------------------------------------

def compile_extra_patterns(patterns) -> list:
    """Compile the --pattern regex list; raise ValueError with a traceable
    code on a bad regex (PURGE/compile/001)."""
    compiled = []
    for p in patterns or []:
        try:
            compiled.append(re.compile(p))
        except re.error as exc:
            raise ValueError(
                f"invalid --pattern regex {p!r}: {exc} (PURGE/compile/001)")
    return compiled


def is_debris(entry, extra_patterns=None) -> bool:
    """True when the entry's key OR value starts with a built-in debris
    prefix, or matches an extra prefix regex (case-sensitive, after strip)."""
    if not isinstance(entry, dict):
        return False
    for field in ("key", "value"):
        text = entry.get(field)
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if any(stripped.startswith(p) for p in _PREFIXES):
            return True
        for rx in extra_patterns or ():
            if rx.match(stripped):
                return True
    return False


def plan_purge(entries: list, extra_patterns=None, max_examples: int = 20):
    """Classify every entry. Pure computation, no I/O.

    Returns (kept, removed, stats) where stats holds:
      scanned, removed, malformed_kept, per_register (removal counts by
      register), examples (list of (register, truncated_key) tuples).
    Non-dict entries are always KEPT (never destroyed).
    """
    extra_patterns = extra_patterns or []
    stats = {"scanned": 0, "removed": 0, "malformed_kept": 0,
             "per_register": {}, "examples": []}
    kept: list = []
    removed: list = []
    for e in entries:
        stats["scanned"] += 1
        if not isinstance(e, dict):
            stats["malformed_kept"] += 1
            kept.append(e)
            continue
        if is_debris(e, extra_patterns):
            stats["removed"] += 1
            reg = e.get("register") if isinstance(e.get("register"), str) \
                else "-"
            stats["per_register"][reg] = stats["per_register"].get(reg, 0) + 1
            if len(stats["examples"]) < max_examples:
                stats["examples"].append(
                    (reg, _trunc(str(e.get("key") or ""))))
            removed.append(e)
        else:
            kept.append(e)
    return kept, removed, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge VibeZoo search-log debris entries from the live "
                    "value_bank (User Decision [2026-09-02 07:18]). Dry-run "
                    "is the DEFAULT; --apply is required for any write.")
    parser.add_argument("--value-bank", default=os.path.join("memory",
                                                             "value_bank.json"),
                        help="value_bank JSON path (default: "
                             "memory/value_bank.json)")
    parser.add_argument("--apply", action="store_true",
                        help="REQUIRED for any write. Without it: dry-run.")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit dry-run (same as omitting --apply)")
    parser.add_argument("--pattern", action="append", default=[],
                        metavar="REGEX",
                        help="extra prefix regex for future debris classes "
                             "(repeatable, default: none)")
    parser.add_argument("--examples", type=int, default=DEFAULT_EXAMPLES,
                        help=f"max example entries to print (default "
                             f"{DEFAULT_EXAMPLES})")
    args = parser.parse_args(argv)

    # cp949-proof console output (project history of Windows encoding issues)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive "
              "(PURGE/main/001)")
        return 1
    applying = args.apply

    vb_path = args.value_bank
    if not os.path.isfile(vb_path):
        print(f"ERROR: value_bank not found: {vb_path} (PURGE/resolve/001)")
        return 1

    try:
        extra_patterns = compile_extra_patterns(args.pattern)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    try:
        entries = load_value_bank(vb_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load value_bank: {exc} (PURGE/main/002)")
        return 1

    mode = "APPLY" if applying else "DRY-RUN"
    print(f"[{mode}] value_bank: {vb_path}")
    if extra_patterns:
        for rx in extra_patterns:
            print(f"  extra debris pattern: {rx.pattern!r}")

    kept, removed, stats = plan_purge(
        entries, extra_patterns, max_examples=max(0, args.examples))

    lbl = "removed" if applying else "would-remove"
    print(f"  entries scanned : {stats['scanned']}")
    print(f"  {lbl:<15}: {stats['removed']}")
    if stats["per_register"]:
        print("  per-register breakdown:")
        for reg in sorted(stats["per_register"]):
            print(f"    {reg:<14}: {stats['per_register'][reg]}")
    for reg, key in stats["examples"]:
        print(f"    e.g. [{reg}] {key}")
    if len(removed) > len(stats["examples"]):
        print(f"    ... and {len(removed) - len(stats['examples'])} more")
    if stats["malformed_kept"]:
        print(f"  malformed kept  : {stats['malformed_kept']} "
              f"(non-dict entries passed through, never destroyed)")
    print(f"  final count     : {len(kept)} "
          f"({stats['scanned']} - {stats['removed']})")

    if not applying:
        print("  no files modified (dry-run).")
        print("  NOTE: a live server holds value_bank in memory; VP "
              "sequences the apply right after a server restart.")
        return 0

    if stats["removed"] == 0:
        print("  nothing to purge — file left untouched (idempotent).")
        return 0

    try:
        bak_path = backup_file(vb_path)
        save_value_bank_atomic(vb_path, kept)
    except OSError as exc:
        print(f"ERROR: write failed after backup: {exc} (PURGE/main/003)")
        return 1
    print(f"  backup          : {bak_path}")
    print(f"  written         : {vb_path} "
          f"({stats['scanned']} -> {len(kept)} entries)")
    print("  crow.bin / weight matrix untouched — residual traces decay "
          "via lambda naturally.")
    print("  Restart the MCP server so it reloads the purged value_bank.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))