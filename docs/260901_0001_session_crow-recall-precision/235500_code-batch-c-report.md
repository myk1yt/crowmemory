# Code Mode Task Report — Batch C: MCP Tool Consolidation 10→3 + i18n
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-02 08:55 KST

## Task Summary
Implement AD-5 (REQ-009) in [`crow_mcp_server.py`](../../../crow_mcp_server.py): replace the 10 MCP tools with exactly 3 (`crow_recall` / `crow_ingest` / `crow_admin`) per the architect's JSONC schemas, wire `recall_multi` (REQ-004 fix from Batch B) into the tool dispatch and REST `/recall`, add AD-8.2 `CROW_STATE_TAG` state-path resolution, replace `_BASE_TOOL_DEFINITIONS` in [`crow_i18n.py`](../../../crow_i18n.py), update [`i18n/en.json`](../../../i18n/en.json) + [`i18n/ko.json`](../../../i18n/ko.json) tool keys (remove the 7 dead tools), and verify with new [`tests/test_tool_schema.py`](../../../tests/test_tool_schema.py) (56 tests).

## Actions Taken

### 1. crow_mcp_server.py — 3 tools (AD-5 exact schemas)
- **`crow_recall`** ([L244-L314](../../../crow_mcp_server.py:244)): params `query` (required), `register` (8+all), `domain` (code/life/all, default all), `top_k` (1-5 via `ge=1, le=5`, default 2), `format` (hint/bias_block, default hint), `project`, `strict_project` (default false).
  - [`_recall()`](../../../crow_mcp_server.py:83) rewritten: `format=bias_block` → [`crow.get_user_bias_block(query, None)`](../../../crow_core.py:1095); `register` in (None, "", "all") → [`crow.recall_multi(query, DOMAINS[domain], top_k, project, strict_project)`](../../../crow_core.py:316) (global eff_sim merge, no per-register fillers, no stats pollution — all inside Batch B's `recall_multi`); single register → [`crow.recall(query, register, top_k, project, strict_project)`](../../../crow_core.py:281). `top_k` clamped 1-5.
- **`crow_ingest`** ([L316-L382](../../../crow_mcp_server.py:316)): params `key`, `value`, `register` (required), `polarity` (now OPTIONAL), `exit_code`, `user_edited` (default false), `project`.
  - [`_ingest()`](../../../crow_mcp_server.py:120) polarity resolution per AD-5 L209: explicit polarity wins → else exit_code auto-map ({0: +0.5 edited/+1.5 else, nonzero: −1.0 edited/−0.5 else}) → else `_error("polarity or exit_code is required")`. Response from [`crow.ingest()`](../../../crow_core.py:466) passed through as-is (Batch B scrub gate + `empty_after_sanitize` rejection already core-side; scrubbing NOT duplicated).
- **`crow_admin`** ([L384-L429](../../../crow_mcp_server.py:384)): params `action` (enum 6) + `args` (object passthrough). [`_admin()`](../../../crow_mcp_server.py:139) dispatch table per AD-5 L222-229: diagnostics→`_diagnostics`, drift→`_drift`, prompt→`_manage_prompt`, backup→`_manage_backup`, evolve→`_evolve`, project_info→`_project_info` — all handlers reused verbatim. Unknown action → `_error`.
- **Deleted** the 7 old `@mcp.tool` functions (crow_evolve_propose, crow_diagnostics, crow_check_drift, crow_ingest_from_build, crow_get_user_bias, crow_manage_prompt, crow_manage_backup, crow_project_info) and their now-unused `_ingest_build`/`_user_bias` bridge helpers; all `_handler` functions kept for `crow_admin`.
- Also deleted the old `_recall` domain-loop pattern (`top_k // len(registers)` per-register slicing + register-order merge + confidence ÷8 — the exact REQ-004 pollution bug).
- Module docstring + server version bumped 1.4.5 → 1.5.0; server instructions updated to describe 3 tools.

### 2. REST parity (AD-5 L231)
- `/health` untouched.
- [`/recall`](../../../crow_mcp_server.py:494): register=all → `recall_multi(query, DOMAINS["all"], limit, project, strict_project)`; accepts optional `project` + `strict_project` query params; single register → `crow.recall` with project params; limit clamped 1-20.
- [`/ingest`](../../../crow_mcp_server.py:477): accepts optional `project` in JSON body; no duplicate scrubbing (core gate applies).

### 3. CROW_STATE_TAG resolution (AD-8.2)
- New [`resolve_state_path(default_path)`](../../../crow_mcp_server.py:78): tag set → `crow-{tag}.bin` (whitespace-only treated as unset); unset → path unchanged. Wired into `main()` before `Path(...).resolve()`.
- **VERIFIED:** [`crow_core.CrowMemory.__init__`](../../../crow_core.py:153) sets `self.memory_dir = os.path.dirname(path)`, and `_load_value_bank`/`_save_value_bank`/`_load_recall_stats`/`_save_recall_stats`/`get_system_prompt`/`append_system_prompt` all resolve via `memory_dir` → sibling data files (value_bank.json, recall_stats.json, system_prompt.md) automatically follow the tag-resolved state path. No crow_core changes needed. Confirmed by test `test_memory_dir_derives_from_state_dir`.

### 4. crow_i18n.py
- [`_BASE_TOOL_DEFINITIONS`](../../../crow_i18n.py:43) replaced with the 3-tool schema set matching AD-5 exactly (recall: register/domain/top_k/format/project/strict_project; ingest: polarity optional + exit_code/user_edited/project; admin: action enum 6 + args object). [`get_tool_definitions()`](../../../crow_i18n.py:371) API unchanged — still deepcopies + overlays `tools.{name}.description` and `tools.{name}.parameters.{param}` from locale JSON.

### 5. i18n/en.json + ko.json
- `tools` section replaced: `crow_recall.*` (updated description + new `format`/`project`/`strict_project` param descriptions), `crow_ingest.*` (updated + `exit_code`/`user_edited`/`project`, polarity marked optional), `crow_admin.*` (description + action/args). All 7 obsolete tool key blocks removed. Other 34 locales untouched (English fallback per `get_text` chain).

### 6. tests/test_tool_schema.py (new, 56 tests)
- ToolRegistrationTests: `create_server()` registers exactly 3 tools; names == {crow_recall, crow_ingest, crow_admin}; all 8 old names gone.
- CrowRecallTests: single-register path returns hints; register omitted / "all" / domain=all all route to `recall_multi` (spy-verified); domain=code scopes registers; single register does NOT use multi; project/strict_project forwarded; `format=bias_block` returns `[User Bias` text; top_k clamped to 5.
- CrowIngestTests: explicit polarity; exit_code=0 → +1.5; exit_code=0+user_edited → +0.5; exit_code=1 (bug, undamped) → −0.5; explicit polarity wins over exit_code; neither → error JSON; unknown register passed through; pure-noise → `rejected`/`empty_after_sanitize`; project tag lands in value_bank entry; AD-7 damping sanity (arch −2.0 → −1.2).
- CrowAdminTests: all 6 actions dispatch to real handlers; unknown action → error JSON; dispatch reuses the exact module handler functions (spy on `cms._diagnostics` etc.).
- RestRouteTests: /recall all-register uses `recall_multi` with project/strict_project forwarding; /ingest accepts project.
- I18nSchemaTests: en defs → 3 tools; recall/ingest/admin schema params; ko.json keys present; obsolete keys removed from en+ko; server ↔ i18n schema sets identical.
- StatePathTests: `CROW_STATE_TAG=myk1yt` → `memory/crow-myk1yt.bin`; unset / whitespace-only → unchanged; memory_dir follows state dir.
- ServerCoreWiringTests: recall_multi present; ingest/recall accept project params; `DOMAINS` importable.

## Result
✅ SUCCESS — all verification commands pass (Python via project `.venv`):

```
python tests\test_tool_schema.py -v    → Ran 56 tests in 0.418s — OK
python tests\test_recall_precision.py → Ran 41 tests in 0.115s — OK (regression clean)
python tests\test_sanitize.py         → Ran 55 tests in 0.003s — OK (regression clean)
python -c "import crow_mcp_server; import crow_i18n" → import OK
python scripts\final_verify.py        → ALL VERIFICATIONS COMPLETE
    step 5: get_tool_definitions(en) = 3 tools: ['crow_recall','crow_ingest','crow_admin']
    step 2: all 36 i18n JSON files valid (edits were apply_diff on exact JSON blocks)
```

**final_verify.py check:** it does NOT hardcode a 10-tool expectation — step 5 prints the count/names dynamically. No modification needed, no mismatch to report.

## Issues Discovered
- **Live server holds the old 10-tool schema:** PID 10640 is running pre-Batch-C `crow_mcp_server.py` (its `crow.bin` lock triggered during my first test run). The running server must be restarted (e.g. `start_crow_sse.bat`) to pick up the 3-tool schema; agents with cached tool lists will get "unknown tool" for the 7 removed names until then (anticipated by AD-5 §Risks).
- **Test iteration record (2 iterations, all test-side, zero implementation fixes):** first run had 15 failures — root causes: (1) PID lock correctly rejected a second `CrowMemory` on the same path within one process (fixture now uses a fresh subdirectory per server instance); (2) my initial ingest tests didn't align the S matrix so FakeEncoder random vectors missed the 0.35 cutoff — reused Batch B's `align_S` fixture pattern; (3) two of my assertions contradicted correct AD-7 behavior (arch −2.0 → −1.2 damping) and the real bias-block header (`[User Bias -- retrieved from Crow Memory]`); (4) my noise string `ㅋ >.< ㅋㅋ` was wrong — Batch B's `>.< ㅋㅋㅋ` scrubs to empty.
- **`crow_mcp_server-myk1yt.py` is now stale:** it was byte-identical to the pre-edit server. Per the task constraints I did not touch it — the AD-8 Option B thin-shim conversion is Batch E scope.

## Next Step Recommendations
- VP: dispatch Batch D (value_bank migration script) — benefits from the verified `entry.get("project")` backward-compat.
- VP: Batch E should include the `-myk1yt` server shim + AGENTS.md tool table update (docs batch per AD-5 L233 decision).
- Operational: restart the live SSE/dual server to activate the 3-tool schema (PID 10640 lock observed during testing).

## Affected File List
- **Modified:** `crow_mcp_server.py` (651 → 634 lines: 10 tools → 3, `_recall`/`_ingest` rewritten, `_admin` added, `resolve_state_path` added, REST routes updated)
- **Modified:** `crow_i18n.py` (only `_BASE_TOOL_DEFINITIONS` replaced, L43-200 area; public API untouched)
- **Modified:** `i18n/en.json`, `i18n/ko.json` (tools section: 3 tools, 7 obsolete key blocks removed)
- **Created:** `tests/test_tool_schema.py` (56 tests)
- **Untouched per constraint:** crow_core.py, crow_sanitize.py, AGENTS.md, all `-myk1yt` files, scripts/final_verify.py, other 34 i18n locales