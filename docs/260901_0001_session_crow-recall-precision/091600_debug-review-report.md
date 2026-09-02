# 🔍 P5 Debug Technical Review — Recall Precision Implementation (Batches A–E)
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** debug (verification/audit — no code modified) | **Time:** 2026-09-02 09:16 KST
**Scope:** git 0310557..031058 → committed work across `crow_sanitize.py`, `crow_core.py`, `crow_mcp_server.py`, `crow_i18n.py`, `i18n/en.json`, `i18n/ko.json`, `scripts/migrate_value_bank.py`, shims, bat, `AGENTS.md`, tests.

---

## Executive Summary

**No 🔴 critical defects found.** The core math (`_accept` cutoff/boost/project logic, `recall_multi` merge, ingest gate ordering, NEG_DAMPEN placement), backward compatibility, cross-batch seams, and the full 178/178 test suite all verify correct. Two genuine defects found, both moderate/minor:

- 🟡 **F1** — REQ-006 display-scrub is missing on the `recall_multi` (register=all) path — the **default** MCP recall path returns unsanitized legacy text.
- 🟡 **F2** — migration script's encoder temp-state dirs are never cleaned up (docstring claims they are).

---

## Findings

### 🟡 F1 — REQ-006 display-time scrub missing on `recall_multi` path (default path)
- **File:Line:** [`crow_core.py:352-358`](crow_core.py:352) (`recall_multi` merged-hint construction) and [`crow_core.py:454`](crow_core.py:454) (`_nearest_hints` returns `entry["value"][:200]` raw); exposed at [`crow_mcp_server.py:107-115`](crow_mcp_server.py:107) (`_recall` all-register path `_ok(result)` passthrough) and [`crow_mcp_server.py:517-520`](crow_mcp_server.py:517) (REST `/recall` all path, `h.get("text")` raw).
- **Evidence:** The single-register path scrubs at render time — [`recall()`](crow_core.py:308) formats `scrub_display(str(h['text']))`. `recall_multi` applies `scrub_display` **only** to the `_track_recall` stats strings ([`crow_core.py:368`](crow_core.py:368)), never to the `{"text": str(h["text"])}` dicts it returns. The MCP tool `crow_recall` **defaults to register=all** → `recall_multi` → the raw stored `value_bank` text goes back to the LLM verbatim, kaomoji included, for all un-migrated legacy entries.
- **Requirement violated:** REQ-006 ("apply same sanitizer to hint output so legacy value_bank entries... render clean"). Tests only cover scrub-on-display for the single-register path (`test_scrubbed_value_clean_in_hints`); the multi path has no scrub assertion.
- **Secondary inconsistency:** the two paths return different hint payload shapes — single: `"[register] text (sim=x.xx)"` strings; multi: `{"register","text","sim","eff_sim"}` dicts (dict `text` also lacks the register prefix and sim suffix). API-contract divergence between `crow.recall` and `crow.recall_multi` for identical callers.
- **Root cause:** REQ-006 was implemented as string formatting inside `recall()` only; `recall_multi` (Batch B, new code) was written returning internal dicts and the render-scrub hook was never carried over.
- **Impact:** Legacy garbage remains visible in the most-used recall path until value_bank migration `--apply` runs (currently NOT run — Batch D left it as a user decision point). Post-migration self-heals for scrubbed entries, but future-ingested text is scrubbed at gate anyway; the residual exposure is legacy-only. Still a real req violation on the default path.
- **Recommended fix route:** `code` — apply `scrub_display` to the returned dict `text` in `recall_multi` (or format dicts consistently at the server layer), plus one test asserting no kaomoji in `recall_multi` output for a legacy-style entry.

### 🟡 F2 — `build_real_encode_fn` leaks temp state dirs (docstring claims otherwise)
- **File:Line:** [`scripts/migrate_value_bank.py:203-207`](scripts/migrate_value_bank.py:203)
- **Evidence:** `tmp_dir = tempfile.mkdtemp(prefix="crow_migrate_state_")` then `shutil.copy2(state_path, tmp_state)` — no `atexit` / `finally` / `tempfile.TemporaryDirectory` cleanup is ever registered. The docstring (L199-201) states "the temp copy is removed at process exit" — **false**. Each `--apply`-with-reencode run leaves a full copy of `crow.bin` (multi-MB, contains the entire synaptic state) under `%TEMP%\crow_migrate_state_*` permanently.
- **Root cause:** docstring written for an intended cleanup that was never implemented.
- **Impact:** unbounded %TEMP% growth + synaptic-state copies lingering on disk (mild data-exposure/space concern given repeated runs are plausible during this migration's decision window).
- **Recommended fix route:** `code` — switch to `tempfile.TemporaryDirectory` context or register `atexit.register(shutil.rmtree, tmp_dir, ignore_errors=True)`.

### 🟢 F3 — Tagged bat cleans the wrong stale lock file
- **File:Line:** [`start_crow_sse-myk1yt.bat:11`](start_crow_sse-myk1yt.bat:11) (`LOCK_FILE=...\memory\crow.bin.lock`) vs tag-rewritten state `memory\crow-myk1yt.bin` → real lock would be `crow-myk1yt.bin.lock`.
- **Evidence:** Phase-2 stale-lock cleanup (L41-46) deletes `%LOCK_FILE%` (untagged) only. With the tag active, a stale tagged lock is never removed by this bat.
- **Mitigation:** [`_acquire_file_lock`](crow_core.py:42-83) self-heals stale locks (PID liveness check + remove), so the practical impact is near-zero.
- **Recommended fix route:** `code-light` — set `LOCK_FILE` conditionally on tag, or skip (self-healed). Cosmetic.

### 🟢 F4 — Importance-boost matching silently fails for un-migrated legacy entries
- **File:Line:** [`crow_core.py:677-680`](crow_core.py:677) (`_track_recall` popularity boost compares `vb_entry["value"][:200] == hint_text[:200]`).
- **Evidence:** `hint_text` is **scrubbed** (`scrub_display` applied in `recall()` L308 / `recall_multi` L368) but the stored legacy `value` is **raw** — entries containing kaomoji never match, so their `importance` never receives the `+0.1*confidence` recall increment.
- **Impact:** legacy noisy entries lose a small popularity signal until migration `--apply` scrubs the bank (then values match again). Self-resolving; no action needed beyond completing the migration.

### 🟢 F5 — Sanitizer false positive on standalone `0.0`
- **File:Line:** [`crow_sanitize.py:54`](crow_sanitize.py:54) (`_KAOMOJI_UVU_RE = (?<![\w.])[oOuU0][vVwW.][oOuU0](?![\w.])`).
- **Evidence:** `scrub_text("score was 0.0")` → `"score was"` (the `0.0` matches the `0.0`-style face pattern). Version strings (`v0.0.1`), IPs (`127.0.0.1`), and decimal contexts with adjacent digits (`0.90`, `3.14`) are correctly protected by the `\w`/`.` lookarounds — only the isolated literal `0.0` is eaten.
- **Impact:** rare in natural-language memory values; harmless token loss. Accept as designed trade-off or add `(?<!\d)`/`(?!.\d)` digit guard.
- **Recommended fix route:** dismiss (or a 1-line lookahead tweak if it ever bites).

### 🟢 F6 — `registers_hit` vs stats-tracking semantic wrinkle
- **File:Line:** [`crow_core.py:364-372, 390`](crow_core.py:364).
- **Evidence:** a register with accepted hints that are all crowded out of the global `top_k` slice still appears in `registers_hit` (from `hit_confidences`) but gets no `_track_recall` entry (stats only track registers with hints in `top`). Cosmetic inconsistency between the two reported notions of "hit"; no correctness impact (weighted confidence handles w=0 correctly, no div-by-zero since `top` is non-empty whenever `hit_confidences` is non-empty — verified: `weights` sum ≥ 1).
- **Recommended fix route:** dismiss or document.

---

## Verification Matrix (what was checked and PASSED)

### 1. Logic correctness
| Check | Verdict | Evidence |
|---|---|---|
| `_accept()` same-project boost ×1.05 within ×1.15 total cap | ✅ | [`crow_core.py:415-417`](crow_core.py:415): `min(1.0+0.12·ln(max(imp,0.1)+1), 1.15)`, then `min(boost*PROJECT_BOOST, 1.15)`. At importance→1e6, raw boost alone hits the 1.15 cap before project boost — test `test_importance_1e6_boost_capped` passes. |
| Cross-project cutoff 0.42 (base+0.07, env-overridable) | ✅ | [`crow_core.py:107-108`](crow_core.py:107); applied at [`crow_core.py:420-421`](crow_core.py:420) only when `query_project and entry_project not in (None, query_project)`. |
| Edge: `entry_project=None` + `query_project` set → base cutoff, NOT cross | ✅ | `None in (None, qp)` → tuple membership true → cross-branch skipped; boost branch `None == qp` false → no boost. Exactly per AD-4 "untagged=global". Covered by `test_untagged_entry_is_global` + `test_untagged_entry_eligible_without_query_project`. |
| Strict filter: only active when query_project set; untagged/same survive | ✅ | [`crow_core.py:411-413`](crow_core.py:411) guard `strict_project and query_project and ...`; 6 dedicated tests pass. Ignored without query_project (sensible — nothing is "cross" then). |
| Backdoor removed: raw sim always ≥ SIM_CUTOFF (0.35) | ✅ | [`crow_core.py:424`](crow_core.py:424) `sim >= SIM_CUTOFF and eff > cutoff`; old `importance>5.0 and sim>0.15` gone (grep-clean). `test_backdoor_gone_high_importance_low_sim` ✓ |
| Boundary 0.34 reject / 0.36 accept | ✅ | `test_sim_034_rejected` / `test_sim_036_accepted` pass. |
| `recall_multi` merge by eff_sim, global top_k slice | ✅ | [`crow_core.py:360-361`](crow_core.py:360) sort + `merged[:max(1, top_k)]`; per-register `_nearest_hints` pre-slice is then globally re-ranked — old fixed-register-order merge gone. |
| No division-by-zero on empty registers_hit | ✅ | [`crow_core.py:375-385`](crow_core.py:375): `merged_confidence=0.0` when `hit_confidences` empty; when non-empty, `top` non-empty ⇒ `sum(weights) ≥ 1`. `test_no_hits_returns_empty_and_zero_confidence` ✓ |
| Stats skipped for empty registers (no ÷8 pollution, no filler queries) | ✅ | [`crow_core.py:349-351`](crow_core.py:349) `continue` before `hit_confidences[register] = ...`; `_track_recall` only for hit registers L364-372. `test_registers_with_zero_hints_skipped` ✓ |
| Ingest gate: scrub BEFORE encode; rejected-empty touches nothing | ✅ | [`crow_core.py:474-477`](crow_core.py:474): early return at `if not value:` sits **before** `encode()`, `S *= lam`, delta, `update_count`, `_append_value_bank`, `_persist` (all at L479-500). `test_rejection_touches_nothing` (asserts update_count/S/value_bank/FAISS unchanged) ✓ |
| Polarity resolution: explicit > exit_code > error; auto-map {0: +1.5/+0.5, nonzero: −0.5/−1.0} | ✅ | [`crow_mcp_server.py:130-140`](crow_mcp_server.py:130) — byte-for-byte the same mapping as the original [`ingest_from_build()`](crow_core.py:908-911) (success 1.5 else 0.5; failure −1.0-edited else −0.5). Explicit-wins + neither-errors tests ✓. Note: `ingest_from_build` still exists in core (used by other callers) — semantics preserved, no divergence. |
| NEG_DAMPEN: bug/life_avoid = 1.0; applied AFTER clip, only when polarity < 0 | ✅ | [`crow_core.py:479-483`](crow_core.py:479): `np.clip(polarity, -2, 2)` first, then `if polarity < 0: dampen = NEG_DAMPEN_BY_REGISTER.get(register, NEG_DAMPEN_DEFAULT)`. Constants at L114-117 with legacy alias. Damping tests (bug=−1.0, arch −2.0→−1.2) ✓ |
| Sanitizer rule order dependencies | ✅ | Emoji → jamo → 3 kaomoji class/literal patterns → punctuation → whitespace ([`crow_sanitize.py:93-103`](crow_sanitize.py:93)). Order is safe: jamo runs removed before kaomoji boundaries re-evaluate; `._.` handled by explicit literals after the underscore-class patterns; whitespace-normalize last prevents adjacent-glyph re-fusion. Idempotency verified (`test_scrub_text_idempotent`). |
| Catastrophic backtracking risk | ✅ clean | All 8 patterns are single-character-class runs or fixed-length alternations — **no nested quantifiers**, no `(a+)+` shapes. Empirically verified against adversarial 100-200KB inputs: worst case **0.023s** (200KB `a.·a.` alternating dots). Linear-time. |
| Unicode ranges: lone jamo ㄱ-ㅎㅏ-ㅣ (U+3131-3163 compat jamo) vs composed 가-힣 (U+AC00-D7A3) | ✅ | [`crow_sanitize.py:33`](crow_sanitize.py:33) `[ㄱ-ㅎㅏ-ㅣ~^]{2,}` — ranges are the Compatibility Jamo block only; composed syllables 가-힣 are disjoint (U+AC00+). Korean prose untouched (test-verified); single embedded ㅋ survives (matches require ≥2). One made-up-word edge: a real Korean word that happens to end in two consecutive lone jamo characters doesn't exist (jamo-only sequences are not valid orthography). |

### 2. Concurrency / state safety
| Check | Verdict | Evidence |
|---|---|---|
| `_persist` atomicity intact | ✅ | [`crow_core.py:786-806`](crow_core.py:786): tmp + `os.replace` + 3-attempt backoff + remove/rename + copy2 fallback — untouched by Batches B–E. Same pattern mirrored in [`migrate_value_bank.py:166-180`](scripts/migrate_value_bank.py:166). |
| Encode cache: bounded LRU (1024) + sha256 full-text keys | ✅ | [`crow_core.py:245-266`](crow_core.py:245): `_encode_cache_max = 1024`, `popitem(last=False)` eviction, `hashlib.sha256(truncated.encode("utf-8")).hexdigest()`. 200-char-prefix collision test ✓ |
| Windows lock interplay with migration temp-copy read | ✅ | [`migrate_value_bank.py:195-207`](scripts/migrate_value_bank.py:195): `CrowMemory(tmp_state)` — lock acquired on the **temp copy's** path, never the real `crow.bin.lock`; no ingest/_persist calls on the instance; `shutil.copy2` of a file replaced atomically by the live server is safe. (Residual: temp dir leak — F2 above.) |

### 3. Backward compatibility
| Check | Verdict | Evidence |
|---|---|---|
| Old value_bank entries without `project` — all reads use `.get()` | ✅ | [`crow_core.py:448, 447`](crow_core.py:447) (`entry.get("project")`, `entry.get("importance", 1.0)`); migration [`migrate_value_bank.py:250-257`](scripts/migrate_value_bank.py:250) uses `e.get(...)` and preserves unknown fields via `dict(e)`. Tests: `test_legacy_entry_without_project_field_reads_global`, `test_other_fields_preserved` ✓ |
| Old clients calling removed tools → clean MCP error, not crash | ✅ (by construction) | The 7 old tool names are simply absent from the FastMCP registry; unknown-tool calls return the standard JSON-RPC `-32602` protocol error at the dispatch layer (framework guarantee, not a code path that can crash). Known limitation already documented in AD-5 §Risks (cached tool lists see "unknown tool" until refresh + server restart). |
| REST routes unchanged shape | ✅ | `/health` untouched shape ([`crow_mcp_server.py:470-477`](crow_mcp_server.py:470)); `/ingest` keeps `{"status","message"}` + optional `project` (L479-498); `/recall` keeps `{"results","count"}` + optional `project`/`strict_project` (L500-529). Swap: `/recall` all-path now emits `eff_sim` scores (doc'd semantic, additive). |
| AGENTS.md vs actual server enum | ✅ | [`AGENTS.md:71`](AGENTS.md:71) lists the same 6 actions — diagnostics/drift/prompt/backup/evolve/project_info — as the server dispatch table ([`crow_mcp_server.py:158-165`](crow_mcp_server.py:158)) and i18n enum ([`crow_i18n.py:141`](crow_i18n.py:141)). `crow_get_user_bias`→`format="bias_block"` and `crow_ingest_from_build`→`exit_code` absorption notes match the Batch C schemas. `domain` values corrected to real enum (code/life/all). |

### 4. Cross-batch seams
| Check | Verdict | Evidence |
|---|---|---|
| `crow_mcp_server-myk1yt.py` runpy delegation argv passthrough | ✅ | [`crow_mcp_server-myk1yt.py:53-61`](crow_mcp_server-myk1yt.py:53): `runpy.run_module("crow_mcp_server", run_name="__main__", alter_sys=False)` — `alter_sys=False` leaves `sys.argv` untouched, so `--state/--transport/--port/--http-port/--host/--ready-file` all reach the canonical `argparse`; canonical `__main__` block handles Windows UTF-8 + event-loop policy. Import side-effect free (no `main()` call at import). Smoke-verified in Batch E (`--help` exits cleanly). |
| `crow_core-myk1yt.py` shim re-export surface | ✅ | [`crow_core-myk1yt.py:31-47`](crow_core-myk1yt.py:31): all 16 named exports verified present in canonical `crow_core` (constants + `CrowMemory`); `__deprecated_shim__` marker; no import-time side effects. |
| `start_crow_sse-myk1yt.bat` tag placement + quoting | ✅ | [`start_crow_sse-myk1yt.bat:21`](start_crow_sse-myk1yt.bat:21): `set "CROW_STATE_TAG=myk1yt"` in the env block — **before** the Phase-3 Python launch (L70) — with correct `set "VAR=val"` quoting; inherited by the `Start-Process` child. REM lines `%`-free. (Lock-cleanup mismatch: F3.) |
| `resolve_state_path` tag → `crow-myk1yt.bin` | ✅ | [`crow_mcp_server.py:71-84`](crow_mcp_server.py:71) stem-suffix rewrite; whitespace-only tag treated as unset (test-verified); `memory/crow-myk1yt.bin` exists on disk. Known-tag-not-applied-to-value_bank caveat already loudly documented in Batch E report — VP decision item, not a code defect per scope. |

### 5. Full suite re-run (by me, this review)
```
tests\test_sanitize.py          → Ran 55 tests — OK
tests\test_recall_precision.py  → Ran 41 tests — OK
tests\test_tool_schema.py       → Ran 56 tests — OK
tests\test_migrate.py            → Ran 26 tests — OK
TOTAL: 178/178 ✅ (matches the claimed count exactly)
```

### 6. Live-data safety
| Check | Verdict | Evidence |
|---|---|---|
| No test writes to real `memory/` | ✅ | All `CrowMemory` fixtures instantiate in `tempfile.mkdtemp()` dirs (`crow_precision_*`, `crow_schema_*`, `crow_state_*`, `crow_migrate_*`); grep found no test path targeting the project's `memory/` — the only `memory/` string hits are pure path-string assertions on `resolve_state_path` ([`tests/test_tool_schema.py:607-625`](tests/test_tool_schema.py:607)). Test-run confirmed: no lock contention with the live server occurred. |
| Migration still dry-run default | ✅ | [`migrate_value_bank.py:304-307`](scripts/migrate_value_bank.py:304): `--apply` is `store_true` (default False); `--apply --dry-run` mutually exclusive (MIGRATE/main/001). No regression — my own re-run of the suite included dry-run default checks. |

---

## Test-env issues encountered (rule: fix & report)
None. All four suites ran clean on the first invocation via `.venv\Scripts\python.exe` (`(env was originally clean) → (no fix needed)`).

## Recommended dispositions for VP
1. **F1 (REQ-006 multi-path scrub)** — route a small `code` task (scrub_display in `recall_multi` return + 1 regression test). Should land **before** the server restart/migration-apply so the default path is clean even pre-migration.
2. **F2 (temp-dir leak)** — fold into the same `code` task (`atexit` rmtree, ~3 lines).
3. F3–F6 — dismiss or bundle opportunistically; none block the restart + migration-apply decision.
4. Operational items already flagged by Batches C/D/E stand (server restart required to activate 3-tool schema; migration `--apply` is a user decision point; both banks should be applied if option (a) is chosen).
