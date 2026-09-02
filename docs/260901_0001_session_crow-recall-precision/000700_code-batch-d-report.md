# Code Mode Task Report — Batch D: Legacy value_bank Migration Script (REQ-007)
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-02 09:07 KST

## Task Summary
Create [`scripts/migrate_value_bank.py`](scripts/migrate_value_bank.py) — a one-time, offline migration that scrubs kaomoji/emoji/jamo noise from the ~500 legacy [`value_bank`](crow_core.py:625) entries, drops pure-noise entries, re-encodes value vectors of text-changed entries through [`CrowMemory.encode`](crow_core.py:247) (read-only), backs up before write, and writes atomically — plus [`tests/test_migrate.py`](tests/test_migrate.py) (26 tests). Dry-run is the safe default; `--apply` is REQUIRED for any write.

## Actions Taken

### 1. Verification-first filename derivation (NOT hardcoded from spec)
Task said "VERIFY actual filename derivation from crow_core before hardcoding". Verified facts:
- [`_load_value_bank`](crow_core.py:625) / [`_save_value_bank`](crow_core.py:633) **ALWAYS** use `os.path.join(memory_dir, "value_bank.json")` — the value_bank filename is **never tag-suffixed by current code**. `CROW_STATE_TAG` (AD-8.2) only renames the crow.bin stem via [`resolve_state_path`](crow_mcp_server.py:71); siblings resolve through `memory_dir` (dirname, [`crow_core.py:153`](crow_core.py:153)).
- **Live data finding:** BOTH `memory/value_bank-myk1yt.json` (4,214,241 B) AND `memory/value_bank.json` (4,237,358 B) exist, both at the 500-entry cap, **both modified 2026-09-02 08:14** — the `-myk1yt` suffixed set is a legacy naming artifact (lock file is `crow.bin-myk1yt.lock`, i.e. the old suffixing scheme). The two running MCP servers (PIDs 9824, 14640, verified via Win32_Process CommandLine) use untagged `--state memory/crow.bin`, meaning the ACTIVE server writes `value_bank.json`; the `-myk1yt` value_bank is a stale snapshot under the new code.
- **Resolution:** [`resolve_value_bank_path`](scripts/migrate_value_bank.py:66) prefers the tagged sibling when it exists (architect-designated live set), falls back to `value_bank.json`, and prints a `MIGRATE/resolve/002` NOTE when both exist so VP can decide which set(s) to apply. This divergence from current-code derivation is explicit in the script docstring and flagged in this report (see Issues).

### 2. Script behavior (architect L51-59 + L296-299)
- **Flags:** `--state-tag`, `--memory-dir` (default `memory`), `--value-bank` (explicit path bypass), `--state` (explicit crow.bin), `--apply` (required for write), `--dry-run` (explicit), `--no-reencode`, `--examples`.
- **Dry-run is the default** — zero file changes; prints entries scanned / would-scrub (with ≤N truncated-80-char before/after examples) / would-drop / would-reencode.
- **Scrub:** [`scrub_text`](crow_sanitize.py:84) on key AND value. Value → `""` post-scrub ⇒ entry DROPPED, reported as `dropped_noise` (per AD-1 edge rule; matches the Batch B ingest gate so garbage never re-enters).
- **Re-encode:** value-changed entries only, via [`CrowMemory.encode`](crow_core.py:247) on a **temp copy** of crow.bin (read-only: no ingest, no `_persist`, real lock file never touched — safe while the live server runs). Vector truncated to the **original entry's vector dim** (ingest parity, [`crow_core.py:487`](crow_core.py:487)). Pre-scan avoids loading sentence_transformers entirely when nothing needs re-encoding (clean bank ⇒ zero-cost success ⇒ `--apply` idempotency holds without any encoder).
- **`--no-reencode`:** text-only pass, vectors stay STALE — documented in flag help, startup banner, and this report. Caveat: a later full run will NOT fix vectors of entries already text-scrubbed by a `--no-reencode` pass (their text no longer changes), so finish in one full pass unless stale vectors are accepted.
- **Backup:** timestamped `value_bank(-tag).json.bak.migrate-<ts>-<pid>` copy via `shutil.copy2` BEFORE any write.
- **Atomic write:** tmp + `os.replace` with Windows retry, mirroring [`_save_value_bank`](crow_core.py:633) / [`_persist`](crow_core.py:786) (utf-8, `ensure_ascii=False`, `indent=2`).
- **Idempotent:** scrub_text is idempotent + only changed entries re-encoded ⇒ second run reports `nothing to migrate` and writes NOTHING (verified: no second backup).
- **FAISS — verified against actual code:** [`_faiss_indexes`](crow_core.py:197) is **process-memory only**, never persisted, never built at load; [`_faiss_search`](crow_core.py:865) has a numpy fallback. Therefore NO persisted index exists to rebuild — the script documents that the running server reloads the scrubbed file on next restart. This matches the "check crow_core, pick what matches actual code, document" instruction.
- **Exit codes:** 0 success/clean dry-run, 1 error. All error paths carry `MIGRATE/<function>/NNN` codes.

### 3. tests/test_migrate.py (26 tests, plain unittest)
FakeEncoder pattern from `tests/test_recall_precision.py` (deterministic sha256-seeded vectors, mimics post-projection DIM output); no real encoder, no real memory dir (per-test temp dirs). Coverage: dry-run no changes (bytes + mtime + no stray files), dry-run default, count/example output, flag exclusivity, missing file error; apply: kaomoji cleaned (`>.<`/`ㅋㅋㅋ` fixtures), pure-noise dropped with count, backup created (and holds ORIGINAL content), idempotent second run, `--no-reencode` stale vectors, other fields preserved (timestamp/importance/ingest_count/project/unknown future fields), malformed non-dict entries passed through, exit 0; vectors: dim matches original (incl. odd dim 17), vector changes when text changes, clean entry vector untouched, re-encoded vector == fake-encode(scrubbed_value)[:dim] bit-exact, corrupt b64 skipped not crashed; core counts + scrub idempotence; state-tag: tagged sibling preferred + both-exist NOTE, fallback to plain, untagged resolution, FileNotFoundError, `crow-<tag>.bin` preference matches server AD-8.2 derivation, full tagged-pipeline dry-run.

## Test iteration record (2 iterations, 1 script fix + test alignment)
1. **Run 1 — 10 failures.** Root causes: (a) my script built the encoder before knowing whether anything needed re-encoding ⇒ apply on a clean bank failed with "state file not found" (real defect — broke `--apply` idempotency). Fixed with a pre-scan pass: heavy encoder loads ONLY when `pre["reencoded"] > 0`. (b) My test FakeEncoder returned `EMBED_DIM`-length vectors, but `crow.encode` output (post-projection) is DIM-length — test-side alignment, not a script issue.
2. **Run 2 — 26/26 OK.** No further changes.

## Result
✅ SUCCESS — all verification commands pass (`.venv\Scripts\python.exe`, Windows):

```
python tests\test_migrate.py -v         → Ran 26 tests — OK
python tests\test_sanitize.py           → Ran 55 tests — OK (regression clean)
python tests\test_recall_precision.py   → Ran 41 tests — OK (regression clean)
python scripts\migrate_value_bank.py --state-tag myk1yt      → REAL dry-run, exit 0
python scripts\migrate_value_bank.py --value-bank memory\value_bank.json → REAL dry-run, exit 0
```

## REAL dry-run against live data (NO apply, decision point for VP)
**`memory/value_bank-myk1yt.json`** (`--state-tag myk1yt`):
- entries scanned: **500** · would-scrub: **9** · would-drop: **1** (pure noise) · would-reencode: **8**
- Examples: `5❌,7🔶` → `5,7` (emoji scrub); `>.<`/jamo runs removed from several values; one entry's value scrubs entirely to `""` (pure garbage).

**`memory/value_bank.json`** (untagged set — the file the LIVE servers actually write):
- entries scanned: **500** · would-scrub: **10** · would-drop: **0** · would-reencode: **9**

Both dry-runs left the files untouched (bytes + mtime 08:14 unchanged — verified). `--apply` NOT run per task instruction; **user decision point**.

## Issues Discovered
1. 🔶 **Live-set ambiguity (IMPORTANT for VP):** current code (`crow_core.py:626`) writes only `value_bank.json`; the running servers (untagged `crow.bin`) make the untagged set the ACTIVE one. The `-myk1yt` value_bank is a stale snapshot despite the architect designating it "live" (REQ-012 audit predates Batch C). The untagged set would LOSE future writes if only the tagged set is migrated. **Recommendation: apply to BOTH sets** (`--state-tag myk1yt` then `--value-bank memory\value_bank.json`), or reconcile the tag scheme in Batch E.
2. 🔶 Both live sets are actively receiving ingests (mtime 08:14 today) — the migration should be run during a server restart window or right after one to avoid a server in-memory `_value_bank` overwriting the migrated file on its next `_persist` (server reloads value_bank only at startup).
3. 🟢 `--no-reencode` entries can never be vector-fixed by later runs (text already clean) — documented in flag help.
4. 🟢 Pre-existing unrelated working-tree modifications observed (`scripts/run_elevated.bat`, `start_crow_sse.bat` — not touched by this batch).

## Next Step Recommendations
- VP: present the dry-run numbers to the user; if approved, run `--apply` on both sets, then restart the SSE server so it reloads the scrubbed banks.
- Batch E should resolve the tagged/untagged live-set divergence (issue 1).

## Affected File List
- **Created:** `scripts/migrate_value_bank.py`, `tests/test_migrate.py`
- **Untouched per constraint:** crow_core.py, crow_sanitize.py, crow_mcp_server.py, all live `memory/` data (verified byte+mtime unchanged), all other existing files