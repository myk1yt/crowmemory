# Code Mode Task Report — Global value_bank Merge Tool (User Decision A)

**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-02 15:42 KST
**Authority:** decisions.md [2026-09-02 06:28] — "merge both value_bank sets into one global set". Closes the Batch E caveat (MIGRATE/resolve/002).

## Task Summary
Created [`scripts/merge_value_bank.py`](scripts/merge_value_bank.py) — merges `memory/value_bank.json` (primary/TARGET, live-written) + `memory/value_bank-myk1yt.json` (secondary/SOURCE, stale snapshot) into ONE global set, with scrub, exact/near dedup, re-encode, backup, atomic write, and dry-run-by-default — plus [`tests/test_merge.py`](tests/test_merge.py) (33 tests). `--apply` NOT run on live data per task instruction; dry-run numbers below are the user decision point.

## Core semantics verified BEFORE coding (read crow_core, not the spec)
- Dedup identity is **(register, key[:500])** — NOT key+value ([`crow_core.py:588`](../../crow_core.py:588))
- Re-ingest accumulation: `importance += abs(polarity)`, `ingest_count += 1`, `timestamp = time.time()` (newest wins); `project` NEVER merged on re-ingest ([`crow_core.py:592-597`](../../crow_core.py:592))
- **The core DOES prune at the cap** ([`crow_core.py:617-624`](../../crow_core.py:617)): importance-based eviction (lowest first, default 0, first-minimal wins) — NOT oldest-timestamp. The merge mirrors this rule exactly and reports every pruned entry.

## Script behavior
- Flags: `--primary` (default `memory/value_bank.json`), `--secondary` (default `memory/value_bank-myk1yt.json`), `--apply` (required for write; dry-run default), `--no-reencode`, `--near-threshold` (default 0.90), `--memory-dir`, `--state`/`--state-tag`, `--examples`, `--dry-run`
- Dedup classes: exact dup (register+key, same scrubbed value → keep primary, merge metadata per core accumulation), key dup (same identity, different value → keep primary text/vector, merge metadata), near dup (stored-vector cosine ≥ threshold, same register+dim → keep primary, NO metadata merge), unique → migrate (project field + all fields preserved)
- Scrub both sets via [`scrub_text`](../../crow_sanitize.py:84); pure-noise entries dropped with counts; malformed non-dict entries passed through untouched (both sets)
- Re-encode text-changed entries via [`build_real_encode_fn`](scripts/migrate_value_bank.py:196) (CrowMemory.encode on a TEMP copy of crow.bin — read-only, real lock file untouched; F2 cleanup pattern); vector truncated to original entry dim (ingest parity, [`crow_core.py:487`](../../crow_core.py:487))
- Cap: applies the core's exact eviction rule when merged count > 500; prints every pruned key with importance
- Backups of BOTH files before write (`.bak.merge-<ts>-<pid>`); atomic write for primary; secondary left untouched on disk (documented in flag help + output)
- Idempotency (task rule #7): secondary fully contained in primary AND primary needs no scrub → "zero changes, nothing to do", no write, no metadata re-accumulation. Documented consequence: a dup-only secondary never triggers metadata sums (prevents double-counting shared ingest history)
- Deterministic plan drives BOTH dry-run and apply → dry-run numbers are honest (pre-scan avoids loading sentence_transformers when nothing needs re-encoding)
- Exit codes 0/1; all error paths carry `MERGE/<function>/NNN` codes

## Test iteration record (2 iterations)
1. **Run 1 — 8 failures.** Root causes: (a) my script's cap summary checked `len(merged) > cap` post-prune — always false, so the EXCEEDED branch never printed (real defect, fixed: check `pruned`); (b) FakeEncoder lacked `__call__` (script calls `encode_fn(text)` like `build_real_encode_fn`'s bound method); (c) 3 test-fixture bugs (missing fixture write; wrong eviction-floor expectation in the cap-parity test; dup-only secondary correctly hit the already-merged no-op so metadata was never summed — the task's own idempotency rule).
2. **Run 2 — 33/33 OK.** No script changes needed beyond (a).

## Result
✅ SUCCESS — all verification commands pass (`.venv\Scripts\python.exe`, Windows):

```
python tests\test_merge.py -v          → Ran 33 tests — OK
python tests\test_migrate.py           → Ran 27 tests — OK (regression clean)
python tests\test_recall_precision.py → Ran 42 tests — OK (regression clean)
python tests\test_tool_schema.py       → Ran 56 tests — OK (regression clean)
python tests\test_sanitize.py          → Ran 55 tests — OK (regression clean)
python scripts\merge_value_bank.py    → REAL dry-run, exit 0, no files modified
```

## REAL dry-run on live data (NO apply — user decision point)
- **primary** `memory/value_bank.json`: 500 scanned · would-scrub 10 · would-drop 0 · malformed 0
- **secondary** `memory/value_bank-myk1yt.json`: 500 scanned · would-scrub 9 · would-drop 1 (pure noise) · malformed 0
- **exact dup**: 473 → keep primary, merge metadata (importance/ingest_count summed, timestamp newest)
- **key dup**: 0 · **near dup (cos ≥ 0.90)**: 0
- **unique secondary → migrate**: 26
- **would-reencode**: 10
- **final merged count: 500** (500 surviving + 26 unique − 26 pruned)
- **Cap plan**: merged set holds 526 → would-prune 26 lowest-importance entries per the core rule. All 26 are importance=1.0 entries (first-minimal wins): mostly `life_context` web-search/search-noise keys ("Search: validate_hymt2_output → 0 AST + 0 line matches" etc.) and a few `context` entries. Full list printed by the dry-run; 10 shown + 16 more.

Interpretation: the `-myk1yt` set is indeed a near-complete past copy of the other (473/500 identical); only 26 unique entries survive, and the cap then evicts the 26 globally-least-important entries — the pruned set is dominated by low-value search-log noise, which is the desired outcome.

## Issues Discovered
1. 🔶 **Live server writes observed DURING the session**: `value_bank.json` is now 4,238,260 B vs 4,237,358 B recorded in the Batch D report — the running MCP server ingested during this session (expected, Batch D issue #2). My dry-run wrote nothing (test-verified bytes+mtime unchanged). **The `--apply` must be sequenced around a server restart by VP**, or a server in-memory `_value_bank` will overwrite the merged file on its next `_persist`.
2. 🔶 The 26 pruned entries are chosen at the apply moment; since the live server keeps ingesting, the exact prune set may differ slightly if apply is delayed. The dry-run above is the plan as of 15:42 KST.
3. 🟢 Dup metadata sums (473 entries) are part of the apply: primary's duplicate entries will gain the secondary's importance/ingest_count — mirrored core re-ingest semantics, documented in script + tests.
4. 🟢 `--no-reencode` caveat inherited from Batch D: entries scrubbed text-only can never be vector-fixed by a later run.

## Next Step Recommendations (VP)
1. Present the dry-run numbers to the user for `--apply` approval.
2. On approval: stop the MCP servers → run `.venv\Scripts\python.exe scripts\merge_value_bank.py --apply` → verify exit 0 + backups → restart the SSE server (reloads merged bank).
3. Optionally re-run the Batch D migration with `--apply` on the merged file afterwards if the user wants the 10 would-scrub entries cleaned in the same window (or rely on the merge's own scrub, which already covers those).

## Affected File List
- **Created:** `scripts/merge_value_bank.py`, `tests/test_merge.py`
- **Untouched per constraint:** crow_core.py, crow_sanitize.py, crow_mcp_server.py, all live `memory/` data (live-file size drift traced to the running server, not this script; dry-run verified no-write)