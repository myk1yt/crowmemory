#!/usr/bin/env python3
"""scripts/migrate_value_bank.py — Batch D: one-time legacy value_bank migration (REQ-007).

One-time, OFFLINE cleanup of the ~500 legacy value_bank entries whose text
(AND vectors) were stored before the Batch A/B ingest scrub gate existed.
Per architect report §1.2 (L51-59) + Batch D plan (L295-299):

    load value_bank JSON
      -> scrub_text(key), scrub_text(value) per entry     (crow_sanitize)
      -> drop entries whose value scrubs to ""             (pure noise)
      -> re-encode vectors of value-changed entries        (CrowMemory.encode)
      -> backup BEFORE any write, then atomic write        (tmp + os.replace)

Usage:
    .venv\\Scripts\\python.exe scripts/migrate_value_bank.py --state-tag myk1yt
        # DRY-RUN (safe default): report only, zero file changes.
    .venv\\Scripts\\python.exe scripts/migrate_value_bank.py --state-tag myk1yt --apply
        # Real migration. Requires the real encoder (sentence_transformers,
        # nomic-ai/nomic-embed-text-v1.5) unless --no-reencode is given.
    .venv\\Scripts\\python.exe scripts/migrate_value_bank.py --state-tag myk1yt --apply --no-reencode
        # Scrub text only; vectors stay STALE (partial fix). Entries cleaned
        # this way are never re-encoded by a later run (their text no longer
        # changes), so finish the job in one pass unless you accept stale vectors.

Filename derivation — VERIFIED against crow_core.py (do not assume tags apply):
    * CrowMemory.__init__ sets memory_dir = dirname(state_path)  (crow_core.py:153)
    * _load_value_bank/_save_value_bank ALWAYS use
      os.path.join(memory_dir, "value_bank.json")                (crow_core.py:626,634)
    * CROW_STATE_TAG only renames the crow.bin stem (crow-myk1yt.bin); the
      value_bank filename itself is NEVER tagged by current code.
    * The live data set memory/value_bank-myk1yt.json is a LEGACY naming
      artifact. When --state-tag is given, this script prefers the tagged
      sibling value_bank-<tag>.json if it exists (the architect-designated
      live set), falling back to value_bank.json, and prints a NOTE when
      both exist so the other set can be migrated explicitly via --value-bank.

FAISS — VERIFIED against crow_core.py:
    * _faiss_indexes is PROCESS-MEMORY ONLY (crow_core.py:197), never
      persisted, never built at load; _faiss_search falls back to a numpy
      scan when no index exists (crow_core.py:879-887).
    * Therefore the migration does NOT need to rebuild any persisted index.
      The running MCP server picks up the scrubbed value_bank file the next
      time it restarts (its in-memory bank is reloaded from disk).

Encoder — READ-ONLY usage:
    * Re-encoding needs the REAL embeddings + the projection matrices
      (proj_W/proj_b) stored in crow.bin. This script imports crow_core and
      instantiates CrowMemory on a TEMP COPY of the state file:
        - never calls ingest() or _persist() (crow.bin is never written),
        - never touches the real lock file (safe while the server runs),
        - projects through the same proj_W/proj_b the live entries were
          encoded with.
    * Vectors are truncated to the ORIGINAL entry's vector dim, matching
      ingest()'s `encode(value)[:value_dim]` per-register truncation
      (crow_core.py:487).

Idempotency: scrub_text is idempotent and only value-changed entries are
re-encoded, so a second run finds zero changes and writes nothing.

Exit codes: 0 = success (including clean dry-run), 1 = error.
MIGRATE/<function>/NNN codes annotate every error path.
"""

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

# Project root importable when run as `python scripts/migrate_value_bank.py`
# or imported from tests.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import crow_core  # noqa: E402  (numpy + safetensors; sentence_transformers stays lazy)
from crow_sanitize import scrub_text  # noqa: E402

EXAMPLE_TRUNC = 80


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_value_bank_path(memory_dir: str, state_tag: str = "",
                            explicit: str = None) -> tuple[str, str]:
    """Resolve the value_bank JSON file to migrate.

    Returns (path, note) where note is None or a human-readable caution.
    Raises FileNotFoundError when nothing exists (MIGRATE/resolve/001).
    """
    if explicit:
        if not os.path.isfile(explicit):
            raise FileNotFoundError(
                f"value_bank not found: {explicit} (MIGRATE/resolve/001)")
        return explicit, None

    plain = os.path.join(memory_dir, "value_bank.json")
    if state_tag:
        tagged = os.path.join(memory_dir, f"value_bank-{state_tag}.json")
        if os.path.isfile(tagged):
            note = None
            if os.path.isfile(plain):
                note = (f"NOTE: both {tagged} and {plain} exist. Using the "
                        f"-{state_tag} set; migrate the untagged set too with "
                        f"--value-bank {plain} (MIGRATE/resolve/002).")
            return tagged, note
        if os.path.isfile(plain):
            return plain, (f"NOTE: {tagged} not found, using {plain} "
                           f"(MIGRATE/resolve/003).")
        raise FileNotFoundError(
            f"no value_bank in {memory_dir} (looked for {tagged} and {plain}) "
            f"(MIGRATE/resolve/001)")
    if os.path.isfile(plain):
        return plain, None
    raise FileNotFoundError(
        f"value_bank not found: {plain} (MIGRATE/resolve/001)")


def resolve_state_path(memory_dir: str, state_tag: str = "",
                       explicit: str = None) -> str:
    """Resolve the crow.bin state file used for the encoder's projection.

    Mirrors crow_mcp_server.resolve_state_path (AD-8.2): tag -> crow-<tag>.bin
    when it exists, else crow.bin. Raises FileNotFoundError when missing —
    a blank state would silently produce garbage projection vectors
    (MIGRATE/resolve/004).
    """
    if explicit:
        if not os.path.isfile(explicit):
            raise FileNotFoundError(
                f"state file not found: {explicit} (MIGRATE/resolve/004)")
        return explicit
    plain = os.path.join(memory_dir, "crow.bin")
    if state_tag:
        tagged = os.path.join(memory_dir, f"crow-{state_tag}.bin")
        if os.path.isfile(tagged):
            return tagged
    if os.path.isfile(plain):
        return plain
    raise FileNotFoundError(
        f"state file not found (needed for re-encode projection): {plain} "
        f"(MIGRATE/resolve/004)")


# ---------------------------------------------------------------------------
# I/O (mirrors crow_core serialization exactly)
# ---------------------------------------------------------------------------

def load_value_bank(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"value_bank root is {type(data).__name__}, expected list "
            f"(MIGRATE/load/001)")
    return data


def save_value_bank_atomic(path: str, entries: list) -> None:
    """Atomic write mirroring crow_core._save_value_bank: tmp + os.replace,
    json.dump(ensure_ascii=False, indent=2), Windows retry (MIGRATE/save/001)."""
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
    bak_path = f"{path}.bak.migrate-{ts}-{os.getpid()}"
    shutil.copy2(path, bak_path)
    return bak_path


# ---------------------------------------------------------------------------
# Encoder (real path: CrowMemory on a temp copy — read-only)
# ---------------------------------------------------------------------------

def build_real_encode_fn(state_path: str):
    """Return crow.encode built from a TEMP COPY of the state file.

    Read-only guarantees: the real crow.bin and its lock file are never
    touched; no ingest/_persist is ever called on the instance; the temp
    copy is removed at process exit. Requires sentence_transformers at
    first encode (crow_core lazy-loads the model) (MIGRATE/encoder/001).
    """
    tmp_dir = tempfile.mkdtemp(prefix="crow_migrate_state_")
    tmp_state = os.path.join(tmp_dir, os.path.basename(state_path))
    shutil.copy2(state_path, tmp_state)
    crow = crow_core.CrowMemory(tmp_state)  # never persisted, never ingests
    return crow.encode


# ---------------------------------------------------------------------------
# Migration core
# ---------------------------------------------------------------------------

def _decode_dim(b64: str):
    """Original vector length (float16 element count), or None if unusable."""
    if not b64:
        return None
    try:
        return len(crow_core.CrowMemory._decode_vector(b64))
    except Exception:
        return None


def _trunc(s: str, n: int = EXAMPLE_TRUNC) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


def migrate_entries(entries: list, encode_fn=None, reencode: bool = True,
                    max_examples: int = 5) -> tuple[list, dict]:
    """Scrub every entry; drop pure-noise; re-encode value-changed entries.

    encode_fn(text) -> np.ndarray; the result is truncated to the entry's
    ORIGINAL vector dim so dims always match (ingest parity, crow_core.py:487).
    When encode_fn is None (dry-run), vectors are untouched and the reencode
    counter reports WOULD-be re-encodes.
    """
    res = {
        "scanned": 0, "scrubbed": 0, "dropped_noise": 0,
        "reencoded": 0, "reencode_skipped": 0, "malformed": 0,
        "examples": [],
    }
    out: list = []
    for e in entries:
        res["scanned"] += 1
        if not isinstance(e, dict):
            res["malformed"] += 1
            out.append(e)  # never destroy unknown structures
            continue
        key = e.get("key") or ""
        value = e.get("value") or ""
        new_key = scrub_text(key)
        new_value = scrub_text(value)
        if not new_value:
            res["dropped_noise"] += 1
            continue
        ne = dict(e)  # preserve every other field (timestamp, importance, ...)
        text_changed = (new_key != key) or (new_value != value)
        if text_changed:
            res["scrubbed"] += 1
            if len(res["examples"]) < max_examples:
                res["examples"].append({
                    "before_key": _trunc(key), "after_key": _trunc(new_key),
                    "before_value": _trunc(value), "after_value": _trunc(new_value),
                })
        ne["key"] = new_key
        ne["value"] = new_value
        if new_value != value and reencode:
            # Mirror apply behavior exactly so dry-run counts are honest:
            # only entries with a decodable stored vector can be re-encoded.
            dim = _decode_dim(ne.get("vector_b64"))
            if dim is None:
                res["reencode_skipped"] += 1
            elif encode_fn is None:
                res["reencoded"] += 1  # dry-run: would re-encode
            else:
                vec = np.asarray(encode_fn(new_value))[:dim]
                if len(vec) != dim:
                    res["reencode_skipped"] += 1
                else:
                    ne["vector_b64"] = crow_core.CrowMemory._encode_vector(vec)
                    res["reencoded"] += 1
        out.append(ne)
    return out, res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None, encode_fn=None) -> int:
    parser = argparse.ArgumentParser(
        description="One-time legacy value_bank migration (REQ-007). "
                    "Dry-run is the DEFAULT; --apply is required for any write.")
    parser.add_argument("--state-tag", default="",
                        help="e.g. myk1yt -> prefer memory/value_bank-myk1yt.json "
                             "and memory/crow-myk1yt.bin (projection source)")
    parser.add_argument("--memory-dir", default="memory",
                        help="memory directory (default: memory)")
    parser.add_argument("--value-bank", default=None,
                        help="explicit value_bank JSON path (bypasses tag resolution)")
    parser.add_argument("--state", default=None,
                        help="explicit crow.bin path for the re-encode projection")
    parser.add_argument("--apply", action="store_true",
                        help="REQUIRED for any write. Without it: dry-run only.")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit dry-run (same as omitting --apply)")
    parser.add_argument("--no-reencode", action="store_true",
                        help="scrub text only, leave vectors stale (fast, partial)")
    parser.add_argument("--examples", type=int, default=5,
                        help="max before/after examples to print (default 5)")
    args = parser.parse_args(argv)

    # cp949-proof console output (project history of Windows encoding issues)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive "
              "(MIGRATE/main/001)")
        return 1
    applying = args.apply
    reencode = not args.no_reencode

    try:
        vb_path, note = resolve_value_bank_path(
            args.memory_dir, args.state_tag, args.value_bank)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1
    if note:
        print(note)

    try:
        entries = load_value_bank(vb_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load value_bank: {exc} (MIGRATE/main/002)")
        return 1

    mode = "APPLY" if applying else "DRY-RUN"
    print(f"[{mode}] value_bank: {vb_path}")
    if args.no_reencode:
        print("  --no-reencode: text scrubbed only; vectors stay STALE "
              "(partial fix).")

    enc = encode_fn
    # Pass 1 — pre-scan WITHOUT the encoder. Decides whether the heavy
    # sentence_transformers load is needed at all: an already-clean bank
    # (or one with no decodable vectors) stays a zero-cost success, which
    # also preserves --apply idempotency without any encoder present.
    _, pre = migrate_entries(entries, None, reencode=reencode,
                             max_examples=max(0, args.examples))
    if applying and reencode and enc is None and pre["reencoded"] > 0:
        try:
            state_path = resolve_state_path(
                args.memory_dir, args.state_tag, args.state)
            enc = build_real_encode_fn(state_path)
            print(f"  encoder: CrowMemory.encode on temp copy of {state_path} "
                  f"(read-only; real crow.bin untouched)")
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            print(f"ERROR: encoder unavailable: {exc} (MIGRATE/main/003). "
                  f"Use --no-reencode for a text-only pass, or free the "
                  f"state file.")
            return 1

    if not applying:
        new_entries, res = None, pre
    else:
        # Pass 2 — real migration (encoder present only when needed).
        new_entries, res = migrate_entries(
            entries, enc, reencode=reencode, max_examples=max(0, args.examples))

    lbl_scrub = "scrubbed        " if applying else "would-scrub     "
    lbl_drop = "dropped_noise   " if applying else "would-drop      "
    lbl_re = "re-encoded      " if applying else "would-reencode  "
    print(f"  entries scanned : {res['scanned']}")
    print(f"  {lbl_scrub}: {res['scrubbed']}")
    for ex in res["examples"]:
        print(f"    e.g. key   : {_trunc(ex['before_key'])}")
        print(f"         ->    : {_trunc(ex['after_key'])}")
        print(f"         value : {_trunc(ex['before_value'])}")
        print(f"         ->    : {_trunc(ex['after_value'])}")
    print(f"  {lbl_drop}: {res['dropped_noise']}")
    print(f"  {lbl_re}: {res['reencoded']}"
          + (f"  (skipped: {res['reencode_skipped']})"
             if res["reencode_skipped"] else ""))
    if res["malformed"]:
        print(f"  malformed kept  : {res['malformed']} (non-dict entries passed through)")

    if not applying:
        print("  no files modified (dry-run).")
        print("  FAISS: indexes are in-memory only in crow_core; the running "
              "server reloads this file on next restart.")
        return 0

    changed = res["scrubbed"] + res["dropped_noise"]
    if changed == 0:
        print("  nothing to migrate — file left untouched (idempotent).")
        return 0

    try:
        bak_path = backup_file(vb_path)
        save_value_bank_atomic(vb_path, new_entries)
    except OSError as exc:
        print(f"ERROR: write failed after backup: {exc} (MIGRATE/main/004)")
        return 1
    print(f"  backup          : {bak_path}")
    print(f"  written         : {vb_path} "
          f"({res['scanned']} -> {len(new_entries)} entries)")
    print("  FAISS: no persisted index exists to rebuild (crow_core keeps "
          "them in process memory only). Restart the MCP server so it "
          "reloads the scrubbed value_bank.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))