# ❓ P6 Final Ask Audit — Crow Memory Recall Precision (REQ-001~REQ-012)

**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** ask (Full Audit) | **Time:** 2026-09-02 09:33 KST
**Audit baseline:** HEAD `4ec561b` (commits `0310557..4ec561b`, 7 commits), requirement-checklist.md, decisions.md, 233400_architect-report.md (AD-1~AD-8)
**Method:** independent code spot-verification against working tree (not trusting reports). Every REQ verified with file/line evidence read directly this audit.

---

# [1. Philosophy & UX/UI Diagnostics]

User's four verbatim intents, checked against the shipped behavior:

1. **"기억을 recall할때 잡음이 많이 딸려온다"** — addressed on three layers: no more fabricated filler hints (REQ-001), higher acceptance floor 0.35 with the low-sim backdoor deleted (REQ-002), and kaomoji/jamo/emoji scrubbing at ingest + display + migration (REQ-005/006/007). The F1 defect (default `recall_multi` path returning raw legacy text) was found in P5 and fixed before this audit; the regression test `test_legacy_kaomoji_value_scrubbed_in_multi_hints` exists in the tree. One honesty note: **legacy noise already in the bank remains until migration `--apply` runs** — the code is ready, the data cleanup is a pending user decision (see §3). This is the correct sequencing, not a failure.
2. **"A워크스페이스에서 C워크스페이스의 기억을 꺼낸다"** — workspace-aware recall delivered as metadata tagging (same-project boost ×1.05 within the ×1.15 cap, cross-project stricter cutoff 0.42, optional `strict_project` hard filter). Untagged entries stay globally eligible — matches the "always global" decision exactly.
3. **"나는 crow를 언제나 global로 사용할거야"** — single global store preserved. One wrinkle, flagged as an inquiry in §3: the pre-existing `project_info` admin action still creates physically isolated `memory/project_<name>/` directories, which contradicts the global-only philosophy. It is legacy surface, not session-introduced, but its continued advertisement in AGENTS.md is a doc-level inconsistency worth resolving.
4. **"도구가 너무 많다, 줄여라"** — 10 → 3 tools confirmed in server schema, i18n base definitions, and AGENTS.md. No capability lost: `format="bias_block"` absorbs `crow_get_user_bias`, `exit_code` absorbs `crow_ingest_from_build`, `crow_admin` action-dispatch absorbs the 6 admin tools.

UX-facing gap (informational, not blocking): the two hint payload shapes differ between `recall()` (formatted strings) and `recall_multi()` (dicts with `eff_sim`). The debug review flagged this; the P5 fix unified content (both scrubbed, both 200-truncated) but kept dict shape for the REST consumer. Callers see consistent *content* on both paths, which is what the LLM actually reads. Acceptable.

---

# [2. 1:1 Cross-Validation Results — Requirement Verdict Table]

| REQ | Verdict | Evidence (independently read this audit) |
|---|---|---|
| REQ-001 no fabricated fallbacks | ✅ | Grep of crow_core.py: "faint"/"recalls a" appears ONLY in AD-2 docstrings. [`_nearest_hints()`](../../../crow_core.py) returns `[]` on no candidates (L448) and only appends accepted hints (L460-465). |
| REQ-002 cutoff 0.35 env-config, backdoor removed | ✅ | [`SIM_CUTOFF = float(os.environ.get("CROW_SIM_CUTOFF", "0.35"))`](../../../crow_core.py) L106. [`_accept()`](../../../crow_core.py) L432: `sim >= SIM_CUTOFF and eff > cutoff` — raw-sim floor is unconditional; old `importance>5.0 and sim>0.15` clause is gone. Tests `test_sim_034_rejected`, `test_backdoor_gone_high_importance_low_sim` exist. |
| REQ-003 boost cap ×1.15 | ✅ | L423: `min(1.0 + 0.12*log(max(importance,0.1)+1.0), 1.15)`. `test_importance_1e6_boost_capped` exists. |
| REQ-004 domain=all aggregation | ✅ | [`recall_multi()`](../../../crow_core.py) L316-399: empty registers skipped (L353-354), global sort by `eff_sim` (L368), stats only for hit registers (L372-380), weighted confidence (L383-393). Server [`_recall()`](../../../crow_mcp_server.py) L107-115 routes all/unset to `recall_multi`. Old `top_k // 8` loop gone. |
| REQ-005 ingest-gate scrub | ✅ | [`ingest()`](../../../crow_core.py) L482-485: `scrub_text(key/value)` BEFORE encode; empty→`{"status":"rejected","reason":"empty_after_sanitize"}` before any S-matrix/persist mutation. [`crow_sanitize.py`](../../../crow_sanitize.py) rules protect C++ (L73-74 excludes `+`), preserve `...` (4+ dots → 3), protect IPs/version strings via `(?<![\w.])` boundaries. |
| REQ-006 recall display scrub (F1 fix) | ✅ | Single path: L308 `scrub_display(str(h['text']))[:200]`. Multi path (F1 fix verified): L363 `"text": scrub_display(str(h["text"]))[:200]` — identical expression. Regression test `test_legacy_kaomoji_value_scrubbed_in_multi_hints` at test_recall_precision.py:371. |
| REQ-007 migration script | ✅ | [`scripts/migrate_value_bank.py`](../../../scripts/migrate_value_bank.py): dry-run is default (`--apply` store_true, L322; mutual exclusion L338-341); backup before write ([`backup_file()`](../../../scripts/migrate_value_bank.py) L184-189); atomic tmp+replace ([`save_value_bank_atomic()`](../../../scripts/migrate_value_bank.py) L167-181); idempotency via pre-scan pass (L371-373). F2 temp-dir leak fixed with atexit+eager cleanup (L207-225). **Open item: `--apply` not yet run on live data — user decision, see §3.** |
| REQ-008 project tagging, global store | ✅ | `_accept` L419-429: strict filter, same-project boost within cap, cross-project cutoff, untagged=global (tuple-membership guard). `_append_value_bank` writes `"project": project` field (L613). Tool params `project`/`strict_project` wired through `_recall`/`_ingest`. `project_slug()` in crow_sanitize.py:119. S matrix untouched. |
| REQ-009 10→3 tools | ✅ | crow_mcp_server.py: exactly 3 `@mcp.tool` registrations (`crow_recall` L274, `crow_ingest` L344, `crow_admin` L403) + 2 prompts (not tools). [`_admin()`](../../../crow_mcp_server.py) dispatch covers all 6 former admin tools. crow_i18n `_BASE_TOOL_DEFINITIONS` has 3 entries; test `test_exactly_three_tools` exists. AGENTS.md tool table updated (L68-71). **One residual inconsistency: `project_info` semantics, see §3.** |
| REQ-010 sha256 cache key | ✅ | [`encode()`](../../../crow_core.py) L255: `hashlib.sha256(truncated.encode("utf-8")).hexdigest()` — full-text hash, 200-char-prefix collision eliminated; bounded 1024-entry LRU intact. |
| REQ-011 per-register NEG_DAMPEN | ✅ | Constants L114-117: `NEG_DAMPEN_BY_REGISTER = {"bug": 1.0, "life_avoid": 1.0}` + backward-compat alias. [`ingest()`](../../../crow_core.py) L489-491: dampen applied after clip, only when polarity < 0. |
| REQ-012 fork strategy | ✅ | AD-8 Option B implemented: [`crow_core-myk1yt.py`](../../../crow_core-myk1yt.py) is a 53-line re-export shim (L26-47, `__deprecated_shim__`); [`crow_mcp_server-myk1yt.py`](../../../crow_mcp_server-myk1yt.py) runpy-delegates with argv passthrough; [`start_crow_sse-myk1yt.bat:21`](../../../start_crow_sse-myk1yt.bat) sets `CROW_STATE_TAG=myk1yt`; [`resolve_state_path()`](../../../crow_mcp_server.py) L71-84 rewrites the .bin path. value_bank caveat loudly documented in bat REM (L16-20) and Batch E report. |

**Requirement verdicts: 12/12 ✅. Zero ❌, zero 🔶.**

### Process audit (cross-checks)
- **Silently dropped requirements:** none. All 12 REQs map to shipped code + tests.
- **Scope creep:** none detected in the 7-commit range per quality-gate changed-file classification (29 files, all traceable to AD-1~AD-8 batches).
- **Anti-lazy-coding:** no stubs found in spot-checked deliverables; the one false docstring claim (F2 "removed at process exit") was caught by debug review and corrected with a regression test. Test evidence: 180/180 claimed by two independent executors (P5 debug re-run + quality gate) at the same HEAD; key regression tests spot-verified to exist in-tree. Evidence freshness: quality gate ran at HEAD `4ec561b`; no commits since.
- **Chain integrity:** P3 design (AD-1~AD-8) → batches A-E → P5 debug found F1/F2 → P5 fix → quality gate PASS → this audit. F1/F2 fixes verified in code, not just reported.

---

# [3. Inquiries for VP & User]

### USER DECISION PENDING (correctly deferred — NOT requirement failures)

1. **Migration `--apply` on live data.** The script, tests, backup, and idempotency are all verified ready; the dry-run numbers are reported (myk1yt set: 500 scanned / 9 scrub / 1 drop; untagged set: 10 scrub / 0 drop). Running `--apply` rewrites live value_bank files — irreversible-without-backup class action, correctly held for the user. **Recommendation: approve `--apply --state-tag myk1yt` (the 500-entry live set) during an ingest-quiet window, after the server restart below, so new writes land in the post-scrub format.**
2. **value_bank filename not tag-suffixed.** Tag isolates only `crow-myk1yt.bin`; `value_bank.json`/`recall_stats.json` resolve through `memory_dir` unsuffixed. Batch E documented options: **(a) accept merge** — treat both banks as one global bank going forward, keep `-myk1yt.json` as historical backup — or **(b) future tag-suffixed data files** requiring an architect decision + migration of the 500-entry bank. My judgment as CPO: **option (a) aligns with the user's "always global" philosophy**; option (b) reintroduces the physical-separation complexity the user already rejected. Present (a) as recommendation, let the user decide.
3. **Live server restart.** The running server (old 10-tool code, untagged crow.bin) activates none of this work until restarted via `start_crow_sse-myk1yt.bat`. Restart is a user action. Note the known consequence: agents with cached old tool lists will see "unknown tool" until their instructions refresh (documented in AD-5 §Risks).

### Inquiry — one trade-off worth a user decision (not blocking)

4. **`project_info` admin action contradicts the global-only philosophy.** [`_project_info`](../../../crow_mcp_server.py) → [`CrowMemory.for_project()`](../../../crow_core.py) still creates physically isolated `memory/project_<name>/` directories, and [`AGENTS.md:71`](../../../AGENTS.md) advertises it as "project-isolated memory instances". This is pre-existing v1 surface (REQ-009 preserved it verbatim per AD-5's "reuses existing handlers" rule), so it is NOT a session defect — but with REQ-008 tagging now the sanctioned mechanism, keeping a physical-isolation backdoor invites exactly the fragmentation the user rejected. **Option A:** deprecate `project_info` now (remove from enum + AGENTS.md; `for_project` stays in core as dead code for API compat). **Option B:** leave as-is with a doc note. I recommend A as a small follow-up; it does not gate this session.

---

# [4. Final Verdict]

**PASS ✅ — phase may advance to P7.**

All 12 requirements are implemented, tested, and verified against the actual code at HEAD `4ec561b`. Zero ❌, zero 🔶. The two genuine defects found mid-flight (F1 default-path scrub, F2 temp-dir leak) were fixed with regression tests before this audit and independently re-verified. User intent is faithfully preserved on all four verbatim anchors: noise removal works end-to-end (ingest gate + display scrub + migration tooling), workspace awareness is metadata-only on a single global store, and the tool surface is exactly 3.

The three open items (migration `--apply`, value_bank merge decision, server restart) are operational user decisions, correctly deferred, and do not constitute requirement failures — the deliverable is the verified capability, which is complete.

**Advance to P7 with the user-facing decision list from §3.**

---

## Affected File List (audit artifact)
- Created: `docs/260901_0001_session_crow-recall-precision/093300_ask-final-audit-report.md`
