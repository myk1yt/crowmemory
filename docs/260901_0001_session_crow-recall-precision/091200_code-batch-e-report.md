# Code Mode Task Report — Batch E: Fork Shims + CROW_STATE_TAG Bat + AGENTS.md Tool Table
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-02 09:12 KST

## Task Summary
Implement AD-8.1 fork shims (convert `crow_core-myk1yt.py` / `crow_mcp_server-myk1yt.py` to thin re-export shims delegating to the canonical modules), AD-8.2 `CROW_STATE_TAG=myk1yt` in `start_crow_sse-myk1yt.bat`, and the AD-5 L233 AGENTS.md update (10-tool table → 3-tool table matching the Batch C server schemas), then smoke-verify all of it without launching a server.

## Actions Taken

### 1. `crow_core-myk1yt.py` → thin re-export shim (AD-8.1)
- 944-line stale duplicate (differed from `crow_core.py` only in docstring version per AD-8 audit) → 53-line shim.
- Module docstring explains deprecation + AD-8 rationale + usage paths (the hyphenated filename is NOT importable via `import`; usable via direct execution / `runpy.run_path` / `importlib`).
- `from crow_core import *` + explicit re-imports of the full public surface verified against `crow_core.py` (which defines no `__all__`): `CrowMemory`, `REGISTERS`, `DOMAINS`, `CODE_REGISTERS`, `LIFE_REGISTERS`, `DIM`, `EMBED_DIM`, `MAX_SV`, `VALUE_BANK_MAX`, `SIM_CUTOFF`, `CROSS_PROJECT_CUTOFF`, `PROJECT_BOOST`, `NEG_DAMPEN`, `NEG_DAMPEN_DEFAULT`, `NEG_DAMPEN_BY_REGISTER`.
- `__deprecated_shim__ = True` module marker.
- `__main__` block: prints deprecation note + re-export proof, exits 0. No import-time side effects (no CrowMemory instantiation, no lock, no server start).

### 2. `crow_mcp_server-myk1yt.py` → thin re-export shim + runpy delegation (AD-8.1)
- 651-line stale pre-Batch-C duplicate (10-tool schema) → 68-line shim.
- `from crow_mcp_server import *` + explicit re-exports verified against `crow_mcp_server.py`: `DEFAULT_STATE_PATH`, `resolve_state_path`, `create_server`, `main`, and all admin-dispatch/handler/bridge names (`_recall`, `_ingest`, `_admin`, `_evolve`, `_diagnostics`, `_drift`, `_manage_prompt`, `_manage_backup`, `_project_info`, `_ok`, `_error`, `_write_ready_file`, `_remove_ready_file`).
- `__deprecated_shim__ = True` marker.
- `__main__` delegates via `runpy.run_module("crow_mcp_server", run_name="__main__", alter_sys=False)` — argv passes through untouched, so the canonical server's own `__main__` handling (Windows UTF-8 reconfigure, `WindowsSelectorEventLoopPolicy`, `asyncio.run(main())`) and full CLI surface (`--state/--transport/--port/--http-port/--host/--ready-file`) work. Import is side-effect free.

### 3. `start_crow_sse-myk1yt.bat` → `CROW_STATE_TAG=myk1yt` (AD-8.2)
- Added `set "CROW_STATE_TAG=myk1yt"` in the env-var block (after `PYTHONUTF8=1`) with an explanatory REM. Nothing else changed — the bat was already verified to launch canonical `crow_mcp_server.py` with `--state memory\crow.bin --transport dual --port 9020 --http-port 9021` (line 64); `resolve_state_path` rewrites the state path at server startup.
- With the tag: state resolves to `memory\crow-myk1yt.bin` — the user's live historical synaptic state (user intent: "crow를 언제나 global로" / never lose `-myk1yt` data). The non-suffixed `start_crow_sse.bat` leaves the tag unset → plain `crow.bin` stays usable for a fresh instance.

### 4. `AGENTS.md` — 3-tool table + behavioral section updates (AD-5 L233)
- AVAILABLE TOOLS: 10-tool table → 3-tool table (`crow_recall` / `crow_ingest` / `crow_admin`), parameter lists read directly from the Batch C schemas in `crow_mcp_server.py` (`crow_recall` L244: query/register/domain/top_k/format/project/strict_project; `crow_ingest` L316: polarity-optional + exit_code/user_edited/project; `crow_admin` L384: 6-action enum + args passthrough). Absorbed tool names noted inline (`crow_get_user_bias` → `format="bias_block"`, `crow_ingest_from_build` → `exit_code`, admin actions absorb the other 5).
- SESSION START: `domain="user"`/`domain="project"` (nonexistent values — actual enum is `code`/`life`/`all`) → corrected to `domain="life"` for personal context, `domain="code"` for project context.
- DURING SESSION: `crow_diagnostics` → `crow_admin` `action="diagnostics"`; `crow_check_drift` → `crow_admin` `action="drift"`.
- REGISTER REFERENCE table verified accurate against `crow_core.py` `REGISTERS`/`DOMAINS` (8 registers, 4 code + 4 life) — unchanged.
- MCP setup section: verified it does NOT mention tool count — unchanged. Doc structure/language (English) preserved.

### 5. Smoke verification (architect L306 adapted — no server launch per constraint)
Live servers (PIDs 9824/14640) hold ports 9020/9021, so the bat's launch path was NOT executed; instead the env resolution and every delegation path was verified in isolation:
- `python crow_core-myk1yt.py` → deprecation note + `CrowMemory=crow_core, REGISTERS=8, SIM_CUTOFF=0.35`, exit 0.
- `python crow_mcp_server-myk1yt.py --help` → canonical argparse help (safe exit, no server), proving argv passthrough.
- `runpy.run_path` import of both shims (non-`__main__` run_name) → no side effects; `__deprecated_shim__=True`; `create_server`/`resolve_state_path`/`CrowMemory` all resolve to their canonical modules.
- `set CROW_STATE_TAG=myk1yt && python -c "...resolve_state_path('./memory/crow.bin')"` → `memory\crow-myk1yt.bin`; derived data paths printed: `memory\value_bank.json`, `memory\recall_stats.json` (see caveat).
- Regressions: `tests/test_tool_schema.py` 56 OK + `tests/test_recall_precision.py` 41 OK + `tests/test_sanitize.py` 55 OK — 152/152, shims break nothing.

## ⚠️ LOUD CAVEAT — tag isolation does NOT extend to value_bank/recall_stats (decision point for VP)
**Confirmed empirically** (not just from Batch D report): with `CROW_STATE_TAG=myk1yt`, the state file resolves to `memory\crow-myk1yt.bin`, but `memory_dir` is only the *dirname* ([`crow_core.py:153`](../../../crow_core.py:153)), and `_load_value_bank`/`_save_value_bank`/`_load_recall_stats`/`_save_recall_stats` hardcode **unsuffixed** `value_bank.json` / `recall_stats.json` inside `memory_dir` ([`crow_core.py:625`](../../../crow_core.py:625)). So:
- The tagged bat isolates **only the .bin** (synaptic weight matrices + projections).
- A server launched via the tagged bat **reads and writes `memory/value_bank.json`** — the same file the currently-running untagged servers write — NOT `memory/value_bank-myk1yt.json`. The `-myk1yt` value_bank (500 entries, the user's live historical snapshot per REQ-012) would go **stale** and its future entries would land in the unsuffixed file.
- This matches Batch D decision point MIGRATE/resolve/002: the `-myk1yt` suffix on the json files is a manual artifact of past copies, not current-code behavior.

**Per task instruction I did NOT touch crow_core filename logic (new scope, needs architect decision). Options to record:**
- **(a) Accept merge:** treat the two value_bank sets as conceptually one global bank going forward (`memory/value_bank.json`); the `-myk1yt.json` snapshot remains as a historical backup. Cheapest; consistent with the user's "always global" intent.
- **(b) Future work:** tag-suffixed data files in `crow_core` (e.g. `value_bank-{tag}.json`), which would truly isolate instance data. Requires an architect decision + migration of the existing 500-entry `-myk1yt` bank.
Either way, **the live servers must be restarted (via the tagged bat) to pick up the 3-tool schema AND the tagged state path — until then nothing changes at runtime** (they still run the old 10-tool code on untagged `crow.bin`, per Batch C/D findings).

## Result
✅ SUCCESS — all verification commands pass (`.venv\Scripts\python.exe`, Windows cmd):

```
python crow_core-myk1yt.py                → deprecation note, re-export proof, exit 0
python crow_mcp_server-myk1yt.py --help   → canonical argparse help, exit 0
runpy.run_path (both shims)               → import OK, side-effect free, canonical modules
CROW_STATE_TAG=myk1yt resolve_state_path  → memory\crow-myk1yt.bin (value_bank → memory\value_bank.json ← caveat)
python tests\test_tool_schema.py          → Ran 56 tests — OK
python tests\test_recall_precision.py     → Ran 41 tests — OK
python tests\test_sanitize.py             → Ran 55 tests — OK
```

## Issues Discovered
1. 🔴 **value_bank/recall_stats are NOT tag-isolated** (detailed above) — the single most important follow-up decision. Restart + either option (a) or (b) is required; until then the `-myk1yt` value_bank receives no new writes under the tagged bat.
2. 🟡 Live servers (PIDs 9824/14640) still run the pre-Batch-C 10-tool code on untagged `crow.bin` — a restart via `start_crow_sse-myk1yt.bat` activates the 3-tool schema + tagged state; agents with cached old tool lists will see "unknown tool" until refreshed (anticipated by AD-5 §Risks).
3. 🟢 No code anywhere imports the hyphenated filenames (grep: only docs references) — the shims' real value is direct-execution/`runpy` compat, which is what was verified.
4. 🟢 The REM line in the bat was kept `%`-free (batch parses REM content; `%%`-style artifacts avoided).

## Next Step Recommendations
- VP: present the value_bank caveat (options a/b) to the user for decision; record in decisions.md.
- VP: schedule server restart during an ingest-quiet window (Batch D issue 2) so the tagged bat + 3-tool schema + migrated banks all activate coherently.
- If option (b) is chosen: route to architect for a tag-suffixed data-file design before any crow_core edit.

## Affected File List
- **Modified:** `crow_core-myk1yt.py` (944 → 53 lines, shim), `crow_mcp_server-myk1yt.py` (651 → 68 lines, shim), `start_crow_sse-myk1yt.bat` (+`CROW_STATE_TAG=myk1yt` + REM), `AGENTS.md` (3-tool table + section fixes)
- **Untouched per constraint:** `crow_core.py`, `crow_mcp_server.py`, all `memory/` data, all other files