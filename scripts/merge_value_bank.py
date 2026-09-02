#!/usr/bin/env python3
"""scripts/merge_value_bank.py — Global value_bank merge (User Decision A).

Merges the two legacy value_bank sets into ONE global set per the user
decision recorded in docs/260901_0001_session_crow-recall-precision/
decisions.md ([2026-09-02 06:28] "merge both value_bank sets into one
global set"). This closes the Batch E caveat (MIGRATE/resolve/002).

    primary   memory/value_bank.json        (merge TARGET — the file the live
                                             untagged servers actually write)
    secondary memory/value_bank-myk1yt.json (merge SOURCE — stale snapshot
                                             from the old tag-suffixing
                                             scheme; left UNTOUCHED on disk
                                             so the user keeps the original)

Pipeline:
    scrub BOTH sets (crow_sanitize.scrub_text; pure-noise entries dropped
    with counts — the Batch D migrate pattern)
      -> dedup against primary:
           exact dup  : same (register, key) AND same scrubbed value
                        -> keep primary, MERGE metadata (core re-ingest
                           accumulation)
           key dup    : same (register, key), different scrubbed value
                        -> keep primary text/vector, merge metadata
           near dup   : vector cosine >= --near-threshold (default 0.90,
                        same register, stored vectors)
                        -> keep primary, NO metadata merge (near-copies of
                           the same history must not double-count)
           otherwise  : unique -> migrate into primary (project field
                        preserved, all other fields preserved)
      -> re-encode entries whose scrubbed value text changed
         (CrowMemory.encode on a TEMP COPY of the state file — read-only,
          the scripts/migrate_value_bank.py F2 pattern; vector truncated to
          the entry's ORIGINAL dim, ingest parity crow_core.py:487)
      -> enforce the crow_core VALUE_BANK_MAX cap with the core's OWN rule
      -> backup BOTH files, atomic-write primary, secondary untouched

Core semantics mirrored EXACTLY (verified against crow_core.py, do not
guess — this is the merge equivalent of `_append_value_bank`):
  * dedup identity is (register, key[:500])               (crow_core.py:583,588)
  * duplicate re-ingest accumulates:
        importance   = existing.get("importance", 1.0) + abs(polarity)
        ingest_count = existing.get("ingest_count", 1) + 1 (per event)
        timestamp    = time.time()  (newest wins)          (crow_core.py:595-597)
    The merge therefore SUMS importance/ingest_count across the two sides
    and takes the NEWEST timestamp. `_append_value_bank` never touches
    `project` on re-ingest — primary's project wins for duplicates too.
  * cap eviction (crow_core.py:617-624): the core DOES prune —
        while len(bank) > VALUE_BANK_MAX:
            pop the entry with the LOWEST importance (default 0),
            first-minimal wins
    NOT oldest-timestamp. The merge mirrors this exactly, applies it only
    when the merged count exceeds the cap, and REPORTS every pruned entry.

Idempotency (task rule): when the secondary set is fully contained in the
primary (every surviving secondary entry is an exact/key dup or a near-dup
AND the primary needs no scrub/noise-drop), the script reports
"already merged" and writes NOTHING — a second run can never re-accumulate
metadata. Consequence (documented policy): a pass where the secondary
contributes ONLY duplicates performs no metadata sums at all, so shared
ingest history is never double-counted.

FAISS: indexes are process-memory only in crow_core (crow_core.py:197);
nothing persisted to rebuild. The running server reloads the merged file
on next restart (VP sequences the apply around a server restart).

Usage:
    .venv\\Scripts\\python.exe scripts/merge_value_bank.py
        # DRY-RUN (safe default): report only, zero file changes.
    .venv\\Scripts\\python.exe scripts/merge_value_bank.py --apply
        # Real merge. Requires the real encoder (sentence_transformers)
        # unless --no-reencode is given.

Exit codes: 0 = success (incl. clean dry-run / already-merged), 1 = error.
All error paths carry MERGE/<function>/NNN codes.
"""

import argparse
import atexit
import json
import os
import shutil
import sys
import time

import numpy as np

# Project root importable when run as `python scripts/merge_value_bank.py`
# or imported from tests.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import crow_core  # noqa: E402  (numpy + safetensors; sentence_transformers lazy)
from crow_sanitize import scrub_text  # noqa: E402
from scripts.migrate_value_bank import (  # noqa: E402  (Batch D machinery)
    build_real_encode_fn, resolve_state_path, save_value_bank_atomic,
    load_value_bank, _decode_dim, _trunc,
)

EXAMPLE_TRUNC = 80


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def backup_file(path: str) -> str:
    """Timestamped copy BEFORE any write (no-data-loss rule)."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak_path = f"{path}.bak.merge-{ts}-{os.getpid()}"
    shutil.copy2(path, bak_path)
    return bak_path


def _decode_vec(b64):
    """Stored vector -> np.float32 array, or None when unusable."""
    if not b64 or not isinstance(b64, str):
        return None
    try:
        v = crow_core.CrowMemory._decode_vector(b64)
        return v if v.size else None
    except Exception:
        return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------------------------------------------------------------------------
# Scrub (Batch D pattern, applied to BOTH sets)
# ---------------------------------------------------------------------------

def scrub_set(entries: list, max_examples: int = 5):
    """Scrub every dict entry's key+value; drop pure-noise entries.

    Returns (pairs, passthrough, stats) where pairs is a list of
    (scrubbed_entry, original_value) tuples — the original value is kept so
    the re-encode pass can tell which entries need a new vector. Non-dict
    (malformed) entries are passed through untouched, never destroyed.
    """
    res = {"scanned": 0, "scrubbed": 0, "dropped_noise": 0, "malformed": 0,
           "examples": []}
    pairs: list = []
    passthrough: list = []
    for e in entries:
        res["scanned"] += 1
        if not isinstance(e, dict):
            res["malformed"] += 1
            passthrough.append(e)
            continue
        key = e.get("key") or ""
        value = e.get("value") or ""
        new_key = scrub_text(key)
        new_value = scrub_text(value)
        if not new_value:
            res["dropped_noise"] += 1
            continue
        if new_key != key or new_value != value:
            res["scrubbed"] += 1
            if len(res["examples"]) < max_examples:
                res["examples"].append({
                    "before_key": _trunc(key), "after_key": _trunc(new_key),
                    "before_value": _trunc(value),
                    "after_value": _trunc(new_value),
                })
        ne = dict(e)  # preserve every other field (timestamp, project, ...)
        ne["key"] = new_key
        ne["value"] = new_value
        pairs.append((ne, value))
    return pairs, passthrough, res


# ---------------------------------------------------------------------------
# Near-dup index (vectorized cosine per register+dim group)
# ---------------------------------------------------------------------------

def _build_reg_matrices(p_pairs, max_examples: int = 5):
    """Group primary vectors by (register, dim) into normalized matrices."""
    groups: dict = {}
    for i, (e, _) in enumerate(p_pairs):
        v = _decode_vec(e.get("vector_b64"))
        if v is None:
            continue
        groups.setdefault((e.get("register"), int(v.size)), []).append((i, v))
    out = {}
    for key, items in groups.items():
        M = np.vstack([v for _, v in items])
        norms = np.linalg.norm(M, axis=1)
        norms[norms == 0.0] = 1.0  # zero-norm guard: keep row zeroed
        out[key] = ([idx for idx, _ in items], M / norms[:, None])
    return out


def _find_near_dup(s_entry, s_vec, reg_matrices, threshold):
    """Return the primary index of the best cosine match >= threshold."""
    if s_vec is None:
        return None
    key = (s_entry.get("register"), int(s_vec.size))
    if key not in reg_matrices:
        return None
    idxs, Mn = reg_matrices[key]
    n = float(np.linalg.norm(s_vec))
    if n == 0.0:
        return None
    sims = Mn @ (s_vec / n)
    j = int(np.argmax(sims))
    if float(sims[j]) >= threshold:
        return idxs[j]
    return None


# ---------------------------------------------------------------------------
# Plan (deterministic; identical for dry-run and apply)
# ---------------------------------------------------------------------------

def plan_merge(primary_raw: list, secondary_raw: list,
               near_threshold: float = 0.90, max_examples: int = 5) -> dict:
    """Classify every surviving secondary entry against the primary.

    Pure computation, no I/O, no encoder — the SAME plan drives dry-run
    printing and the apply pass so dry-run numbers are honest.
    """
    p_pairs, p_extra, p_stats = scrub_set(primary_raw, max_examples)
    s_pairs, s_extra, s_stats = scrub_set(secondary_raw, max_examples)

    # (register, key) index of primary — the core dedup identity
    # (crow_core.py:588: entry.get("register") == register and
    #  entry.get("key") == key_trunc).
    p_index: dict = {}
    for i, (e, _) in enumerate(p_pairs):
        p_index.setdefault((e.get("register"), e.get("key")), i)

    reg_matrices = _build_reg_matrices(p_pairs)

    dup_meta: dict = {}   # primary idx -> merged metadata
    uniques: list = []    # (entry, orig_value) pairs to migrate
    near_examples: list = []
    exact_dup = key_dup = near_dup = 0

    for e, _orig in s_pairs:
        idx = p_index.get((e.get("register"), e.get("key")))
        if idx is not None:
            p_entry = p_pairs[idx][0]
            same_value = (e.get("value") == p_entry.get("value"))
            if same_value:
                exact_dup += 1
            else:
                key_dup += 1
            # Core re-ingest accumulation (crow_core.py:595-597):
            #   importance += abs(polarity)  (secondary's importance IS its
            #   stored abs(polarity) contribution)
            #   ingest_count += 1 per ingest event (sum the two histories)
            #   timestamp = newest
            meta = dup_meta.get(idx)
            s_imp = e.get("importance", 1.0)
            s_cnt = e.get("ingest_count", 1)
            s_ts = e.get("timestamp", 0.0)
            if meta is None:
                p_imp = p_entry.get("importance", 1.0)
                p_cnt = p_entry.get("ingest_count", 1)
                p_ts = p_entry.get("timestamp", 0.0)
                meta = {"importance": p_imp + s_imp,
                        "ingest_count": p_cnt + s_cnt,
                        "timestamp": max(p_ts, s_ts),
                        "same_value": same_value}
            else:  # several secondary entries collapse onto one primary
                meta["importance"] += s_imp
                meta["ingest_count"] += s_cnt
                meta["timestamp"] = max(meta["timestamp"], s_ts)
            dup_meta[idx] = meta
            continue

        near_idx = _find_near_dup(e, _decode_vec(e.get("vector_b64")),
                                  reg_matrices, near_threshold)
        if near_idx is not None:
            near_dup += 1
            if len(near_examples) < max_examples:
                near_examples.append(
                    (e.get("key") or "", p_pairs[near_idx][0].get("key") or ""))
            continue

        uniques.append((e, _orig))

    p_changes = p_stats["scrubbed"] + p_stats["dropped_noise"] \
        + p_stats["malformed"]
    # Idempotency guard (task rule #7): secondary fully contained in primary
    # AND primary needs no scrub/noise-drop/malformed-passthrough -> the
    # merge contributes nothing; a second run must write nothing.
    already_merged = (not uniques and not s_extra and p_changes == 0)

    return {
        "p_pairs": p_pairs, "p_extra": p_extra, "p_stats": p_stats,
        "s_pairs": s_pairs, "s_extra": s_extra, "s_stats": s_stats,
        "dup_meta": dup_meta, "uniques": uniques,
        "exact_dup": exact_dup, "key_dup": key_dup, "near_dup": near_dup,
        "near_examples": near_examples,
        "already_merged": already_merged,
        "changes": bool(uniques or s_extra or p_changes),
    }


# ---------------------------------------------------------------------------
# Assemble (apply the plan; re-encode text-changed entries)
# ---------------------------------------------------------------------------

def _reencode_entry(entry: dict, encode_fn, reencode: bool, stats: dict):
    """Re-encode entry's vector when its value text changed (in-place on the
    dict). Mirrors migrate_value_bank.migrate_entries: only entries with a
    decodable stored vector can be re-encoded; the new vector is truncated
    to the ORIGINAL dim (ingest parity, crow_core.py:487)."""
    if not reencode:
        return
    dim = _decode_dim(entry.get("vector_b64"))
    if dim is None:
        stats["reencode_skipped"] += 1
        return
    if encode_fn is None:
        stats["reencoded"] += 1  # dry-run: would re-encode
        return
    vec = np.asarray(encode_fn(entry["value"]))[:dim]
    if len(vec) != dim:
        stats["reencode_skipped"] += 1
        return
    entry["vector_b64"] = crow_core.CrowMemory._encode_vector(vec)
    stats["reencoded"] += 1


def assemble(plan: dict, encode_fn=None, reencode: bool = True,
             cap: int = 500, max_prune_report: int = 10) -> tuple:
    """Build the final merged list from the plan.

    Order: primary entries (original order, metadata merged) + primary
    malformed passthrough + secondary malformed passthrough + migrated
    unique secondary entries (core append semantics). With encode_fn=None
    the vectors of text-changed entries are left as-is and counted as
    would-reencode (dry-run honesty).
    """
    stats = {"reencoded": 0, "reencode_skipped": 0}
    out: list = []

    for i, (e, orig_value) in enumerate(plan["p_pairs"]):
        ne = dict(e)
        meta = plan["dup_meta"].get(i)
        if meta:
            # core re-ingest accumulation, mirrored (crow_core.py:592-597).
            # `project` is deliberately NOT touched — the core never merges
            # project on re-ingest; primary's project wins.
            ne["importance"] = meta["importance"]
            ne["ingest_count"] = meta["ingest_count"]
            ne["timestamp"] = meta["timestamp"]
        out.append(ne)
        if ne["value"] != orig_value:
            _reencode_entry(ne, encode_fn, reencode, stats)

    out.extend(plan["p_extra"])   # malformed primary, never destroyed
    out.extend(plan["s_extra"])   # malformed secondary, preserved

    for e, orig_value in plan["uniques"]:
        ne = dict(e)  # project field and every other field preserved
        out.append(ne)
        if ne["value"] != orig_value:
            _reencode_entry(ne, encode_fn, reencode, stats)

    # Cap enforcement — mirror crow_core.py:617-624 EXACTLY:
    #   while len(bank) > VALUE_BANK_MAX:
    #       pop the entry with the LOWEST importance (default 0),
    #       first-minimal wins (min() returns the first minimal index).
    pruned: list = []
    while len(out) > cap:
        min_idx = min(
            range(len(out)),
            key=lambda i: out[i].get("importance", 0)
            if isinstance(out[i], dict) else 0,
        )
        victim = out.pop(min_idx)
        pruned.append(victim if isinstance(victim, dict)
                      else {"key": "<malformed>", "register": "-",
                            "importance": 0})

    pruned_report = [
        {"key": _trunc(v.get("key") or ""),
         "register": v.get("register"),
         "importance": v.get("importance", 0)}
        for v in pruned[:max_prune_report]
    ]
    return out, stats, pruned, pruned_report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None, encode_fn=None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge the two value_bank sets into ONE global set "
                    "(User Decision A). Dry-run is the DEFAULT; --apply is "
                    "required for any write. The secondary file is NEVER "
                    "modified — only backed up so the apply is reversible.")
    parser.add_argument("--primary", default=None,
                        help="merge TARGET value_bank JSON (default: "
                             "<memory-dir>/value_bank.json — the file the "
                             "live servers write)")
    parser.add_argument("--secondary", default=None,
                        help="merge SOURCE value_bank JSON (default: "
                             "<memory-dir>/value_bank-myk1yt.json — the "
                             "stale legacy snapshot)")
    parser.add_argument("--memory-dir", default="memory",
                        help="memory directory (default: memory)")
    parser.add_argument("--state", default=None,
                        help="explicit crow.bin path for the re-encode "
                             "projection")
    parser.add_argument("--state-tag", default="",
                        help="state tag for projection resolution (e.g. "
                             "myk1yt -> prefer memory/crow-myk1yt.bin)")
    parser.add_argument("--apply", action="store_true",
                        help="REQUIRED for any write. Without it: dry-run.")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit dry-run (same as omitting --apply)")
    parser.add_argument("--no-reencode", action="store_true",
                        help="scrub/merge text only, leave vectors stale "
                             "(fast, partial fix)")
    parser.add_argument("--near-threshold", type=float, default=0.90,
                        help="near-duplicate vector cosine threshold "
                             "(default 0.90)")
    parser.add_argument("--examples", type=int, default=5,
                        help="max scrub/near-dup examples to print (default 5)")
    args = parser.parse_args(argv)

    # cp949-proof console output (project history of Windows encoding issues)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive "
              "(MERGE/main/001)")
        return 1
    applying = args.apply
    reencode = not args.no_reencode

    primary_path = args.primary or os.path.join(args.memory_dir,
                                               "value_bank.json")
    secondary_path = args.secondary or os.path.join(args.memory_dir,
                                                   "value_bank-myk1yt.json")
    if not os.path.isfile(primary_path):
        print(f"ERROR: primary value_bank not found: {primary_path} "
              f"(MERGE/resolve/001)")
        return 1
    if not os.path.isfile(secondary_path):
        print(f"ERROR: secondary value_bank not found: {secondary_path} "
              f"(MERGE/resolve/002)")
        return 1
    if os.path.normcase(os.path.abspath(primary_path)) == \
            os.path.normcase(os.path.abspath(secondary_path)):
        print("ERROR: --primary and --secondary must be different files "
              "(MERGE/resolve/003)")
        return 1

    try:
        primary_raw = load_value_bank(primary_path)
        secondary_raw = load_value_bank(secondary_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load value_bank: {exc} (MERGE/main/002)")
        return 1

    mode = "APPLY" if applying else "DRY-RUN"
    print(f"[{mode}] primary  : {primary_path}")
    print(f"[{mode}] secondary: {secondary_path} (never modified)")
    if args.no_reencode:
        print("  --no-reencode: text scrub/merge only; changed vectors stay "
              "STALE (partial fix).")
    print(f"  near-dup threshold: cosine >= {args.near_threshold}")

    plan = plan_merge(primary_raw, secondary_raw,
                      near_threshold=args.near_threshold,
                      max_examples=max(0, args.examples))

    cap = crow_core.VALUE_BANK_MAX
    # Deterministic assembly drives BOTH modes: with encode_fn=None the
    # re-encode counters report would-be values, vectors untouched.
    merged, enc_stats, pruned, pruned_report = assemble(
        plan, None, reencode=reencode, cap=cap)

    p, s = plan["p_stats"], plan["s_stats"]
    lbl = "" if applying else "would-"
    print(f"  primary  : {p['scanned']} scanned, {lbl}scrub {p['scrubbed']}, "
          f"{lbl}drop-noise {p['dropped_noise']}, malformed {p['malformed']}")
    print(f"  secondary: {s['scanned']} scanned, {lbl}scrub {s['scrubbed']}, "
          f"{lbl}drop-noise {s['dropped_noise']}, malformed {s['malformed']}")
    for tag, st in (("primary", p), ("secondary", s)):
        for ex in st["examples"]:
            print(f"    e.g. {tag} key   : {ex['before_key']}")
            print(f"              ->    : {ex['after_key']}")
            print(f"         {tag} value : {ex['before_value']}")
            print(f"              ->    : {ex['after_value']}")
    print(f"  exact dup (register+key, same value): {plan['exact_dup']} "
          f"-> keep primary, merge metadata "
          f"(importance summed, ingest_count summed, timestamp newest)")
    print(f"  key dup  (register+key, diff value): {plan['key_dup']} "
          f"-> keep primary text/vector, merge metadata")
    print(f"  near dup (cosine >= {args.near_threshold}): "
          f"{plan['near_dup']} -> keep primary (no metadata merge)")
    for s_key, p_key in plan["near_examples"]:
        print(f"    e.g. secondary {_trunc(s_key)} ~ primary {_trunc(p_key)}")
    print(f"  unique secondary entries: {len(plan['uniques'])} -> "
          f"{lbl}migrate into primary")
    print(f"  {lbl}reencode: {enc_stats['reencoded']}"
          + (f"  (skipped: {enc_stats['reencode_skipped']})"
             if enc_stats["reencode_skipped"] else ""))
    print(f"  final merged count: {len(merged)} "
          f"(primary {p['scanned'] - p['dropped_noise']} surviving "
          f"+ unique {len(plan['uniques'])}"
          + (f" - pruned {len(pruned)}" if pruned else "") + ")")

    if pruned:
        print(f"  cap: VALUE_BANK_MAX={cap} EXCEEDED — merged set holds "
              f"{len(merged) + len(pruned)} entries -> "
              f"{'pruned' if applying else 'would-prune'} "
              f"{len(pruned)} lowest-importance entries "
              f"(core rule crow_core.py:617-624, importance-based "
              f"eviction, first-minimal wins):")
        for v in pruned_report:
            print(f"    pruned: [{v['register']}] {_trunc(v['key'])} "
                  f"(importance={v['importance']})")
        if len(pruned) > len(pruned_report):
            print(f"    ... and {len(pruned) - len(pruned_report)} more")
    else:
        print(f"  cap: VALUE_BANK_MAX={cap} — within cap, no pruning.")

    if plan["already_merged"]:
        print("  already merged — secondary fully contained in primary; "
              "zero changes, nothing to do (idempotent).")
        if not applying:
            print("  no files modified (dry-run).")
        return 0

    if not applying:
        print("  no files modified (dry-run).")
        print("  FAISS: no persisted index exists (crow_core keeps them in "
              "process memory only). On --apply, restart the MCP server so "
              "it reloads the merged value_bank.")
        return 0

    if not plan["changes"]:
        # Only duplicate metadata deltas — guarded by the idempotency rule
        # above; unreachable in practice, kept as a safety net.
        print("  nothing to merge — primary left untouched.")
        return 0

    # Apply: build the real encoder ONLY when something needs re-encoding
    # (pre-scan keeps an already-clean merge a zero-cost success).
    enc = encode_fn
    if reencode and enc is None and enc_stats["reencoded"] > 0:
        try:
            state_path = resolve_state_path(
                args.memory_dir, args.state_tag, args.state)
            enc = build_real_encode_fn(state_path)
            print(f"  encoder: CrowMemory.encode on temp copy of {state_path} "
                  f"(read-only; real crow.bin untouched)")
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            print(f"ERROR: encoder unavailable: {exc} (MERGE/main/003). "
                  f"Use --no-reencode for a text-only pass, or free the "
                  f"state file.")
            return 1

    merged, enc_stats, pruned, pruned_report = assemble(
        plan, enc, reencode=reencode, cap=cap)
    if enc_stats["reencoded"]:
        print(f"  re-encoded: {enc_stats['reencoded']}"
              + (f"  (skipped: {enc_stats['reencode_skipped']})"
                 if enc_stats["reencode_skipped"] else ""))

    try:
        primary_bak = backup_file(primary_path)
        secondary_bak = backup_file(secondary_path)
        save_value_bank_atomic(primary_path, merged)
    except OSError as exc:
        print(f"ERROR: write failed after backup: {exc} (MERGE/main/004)")
        return 1
    print(f"  backup primary  : {primary_bak}")
    print(f"  backup secondary: {secondary_bak}")
    print(f"  written         : {primary_path} "
          f"({plan['p_stats']['scanned']} -> {len(merged)} entries)")
    print("  secondary file  : left untouched (original preserved)")
    if pruned:
        print(f"  pruned {len(pruned)} entries (cap {cap}):")
        for v in pruned_report:
            print(f"    pruned: [{v['register']}] {_trunc(v['key'])} "
                  f"(importance={v['importance']})")
    print("  FAISS: no persisted index exists to rebuild. Restart the MCP "
          "server so it reloads the merged value_bank.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))