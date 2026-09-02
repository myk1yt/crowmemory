# 💻 P5 Code Task Report — F1 + F2 Debug-Review Defect Fixes

**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-02 09:26 KST
**Source:** 091600_debug-review-report.md (F1, F2 — F3–F6 untouched per instructions)

---

## Task Summary

Fixed the two genuine defects from the P5 debug review: F1 (REQ-006 display-scrub missing on the default `recall_multi` path) and F2 (migration temp-dir leak + false docstring). Added one regression test per defect. Full suite 180/180.

## Actions Taken

### F1 — display-scrub on the default recall path ([`crow_core.py:358-364`](../../../crow_core.py))
- **Root cause (1 sentence):** REQ-006 was implemented as string formatting inside `recall()` only; `recall_multi()` (Batch B, new code) returned internal dicts with raw `str(h["text"])` and the render-scrub hook was never carried over.
- **Fix:** `recall_multi`'s merged-hint `"text"` now uses the exact same expression as `recall()` — `scrub_display(str(h["text"]))[:200]` — so both paths surface byte-identical cleaned content. Docstring updated (F1 comment REQ-006).
- **Shape decision (constraint-driven):** the hint **dict shape is kept** (`{"register","text","sim","eff_sim"}`) because the REST consumer [`crow_mcp_server.py:517-518`](../../../crow_mcp_server.py) reads `h.get("text")`/`h.get("eff_sim")` and `crow_mcp_server.py` is outside the allowed edit scope (crow_core.py, migrate script, 2 test files only). Payload-shape unification was therefore applied at the **content level** (scrubbed + 200-truncated, exactly matching `recall()`'s public strings), verified by a cross-path assertion in the regression test.
- The stats loop at [`crow_core.py:375-379`](../../../crow_core.py) re-scrubs the now-already-scrubbed text — safe because `scrub_text` is idempotent (test-verified in `test_sanitize.py`).
- **Regression test:** `test_legacy_kaomoji_value_scrubbed_in_multi_hints` in [`tests/test_recall_precision.py:373-403`](../../../tests/test_recall_precision.py) — legacy entry injected straight into the bank (bypassing the ingest gate) with `>.< ㅋㅋㅋ` in the value; asserts the multi-path hint text contains no kaomoji, equals `scrub_display(...)[:200]`, and matches the single-path hint content.

### F2 — migration temp-dir leak ([`scripts/migrate_value_bank.py:195-231`](../../../scripts/migrate_value_bank.py))
- **Root cause (1 sentence):** the docstring described an intended `atexit`/context cleanup that was never implemented; `mkdtemp` + `copy2` of the multi-MB state file leaked a `crow_migrate_state_*` dir under `%TEMP%` on every re-encode run.
- **Fix:** three-layer cleanup in `build_real_encode_fn`:
  1. `atexit.register(_cleanup_temp_state_dir, tmp_dir)` immediately after `mkdtemp` (covers early returns/crashes),
  2. try/except around `CrowMemory(tmp_state)` construction — on exception, eager cleanup + re-raise,
  3. eager `_cleanup_temp_state_dir(tmp_dir)` right after successful construction — safe because `CrowMemory.__init__` loads state + value_bank fully into RAM ([`crow_core.py:163-201`](../../../crow_core.py)); `encode()` only reads in-memory `proj_W`/`proj_b`.
- New helper `_cleanup_temp_state_dir()` — `rmtree(ignore_errors=True)`, idempotent.
- **Docstring corrected:** now states "removed eagerly right after construction ... with an atexit fallback for early returns (MIGRATE/encoder/002)" — the false "removed at process exit" claim is gone.
- Added `atexit` to the imports.
- **Regression test:** `test_temp_state_dir_removed_after_build` in [`tests/test_migrate.py:466-506`](../../../tests/test_migrate.py) — builds a REAL safetensors state via `CrowMemory._persist()`, runs `build_real_encode_fn`, asserts (a) no `crow_migrate_state_*` dir remains in `%TEMP%`, (b) the returned encode fn still works after cleanup, (c) the docstring no longer contains the false claim, (d) the cleanup helper is safe on nonexistent paths. Uses a class-level `CrowMemory.encoder` property patch with a raw-`EMBED_DIM` fake (the internal CrowMemory instance is not reachable for instance-level injection).

## Result — ✅ Success (evidence)

```
tests\test_recall_precision.py  → Ran 42 tests  OK (41 + 1 new F1 test)
tests\test_migrate.py            → Ran 27 tests  OK (26 + 1 new F2 test)
tests\test_tool_schema.py        → Ran 56 tests  OK (regression, unchanged)
tests\test_sanitize.py           → Ran 55 tests  OK (regression, unchanged)
TOTAL: 180/180 ✅ (exactly the expected 178 + 2 new)
```

All via `.venv\Scripts\python.exe tests/<name>.py` per constraint. No test touches real `memory/` (all fixtures in `tempfile.mkdtemp()` dirs).

## Issues Discovered (during work)

1. **Test-infra gotcha (fixed in-test):** `build_real_encode_fn` constructs its own internal `CrowMemory`, so instance-level encoder injection cannot reach it — the first test run triggered a real `SentenceTransformer` download attempt (unauthenticated HF Hub request, ~20s). Fixed by patching the `CrowMemory.encoder` class-level property; the correct fake must emit raw `EMBED_DIM`-length vectors (pre-projection), unlike the module-level `FakeEncoder` which mimics post-projection `DIM` output. Worth knowing for any future test that exercises the real encode path.
2. **F4 residual (pre-existing, dismissed by review — noting only):** `_track_recall`'s popularity boost compares raw stored value vs (now doubly) scrubbed hint text; legacy kaomoji entries still won't match for the `+0.1*confidence` increment until migration `--apply` runs. Unchanged behavior; self-resolves post-migration. Not touched (out of scope).

## Next Step Recommendations

1. VP: commit (files: `crow_core.py`, `scripts/migrate_value_bank.py`, `tests/test_recall_precision.py`, `tests/test_migrate.py`).
2. F1 fix means the default recall path is now clean **pre-migration** — the review's recommendation "land before restart/migration-apply" is satisfied; server restart + migration `--apply` remain the standing operational decision items.

## Affected File List

- `crow_core.py` — `recall_multi()` docstring + merged-hint text scrub (L326-331, L352-364)
- `scripts/migrate_value_bank.py` — `atexit` import; `build_real_encode_fn` cleanup + docstring; new `_cleanup_temp_state_dir` (L65, L195-231)
- `tests/test_recall_precision.py` — new `test_legacy_kaomoji_value_scrubbed_in_multi_hints` (L373-403)
- `tests/test_migrate.py` — new `EncoderTempDirTests` class with `test_temp_state_dir_removed_after_build` (L451-506)