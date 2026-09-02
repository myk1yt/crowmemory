# Code Mode Task Report — Batch B: crow_core.py Recall/Ingest Precision Fixes
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-01 23:47 KST

## Task Summary
Implement Batch B (all core-side recall/ingest precision fixes) in [`crow_core.py`](../../../crow_core.py) per AD-2/AD-3/AD-4/AD-6/AD-7 and AD-1 wiring from the architect report, consuming Batch A's [`crow_sanitize.py`](../../../crow_sanitize.py). Deliverable: fabricated-fallback removal, env-configurable cutoffs, boost cap, project tagging, `recall_multi`, sha256 cache key, per-register NEG_DAMPEN, ingest scrub gate, and `tests/test_recall_precision.py` (41 tests, zero fail).

## Actions Taken

Changed functions (all line refs are post-edit [`crow_core.py`](../../../crow_core.py)):

1. **Module imports (L16, L29-31)** — added `math`; added `from crow_sanitize import scrub_text, scrub_display`.
2. **Constants (L105-117)** — REQ-002: `SIM_CUTOFF` (env `CROW_SIM_CUTOFF`, default 0.35), `CROSS_PROJECT_CUTOFF` (env, default 0.42), `PROJECT_BOOST` (env, default 1.05) — read once at import. REQ-011: `NEG_DAMPEN_DEFAULT = 0.6`, `NEG_DAMPEN_BY_REGISTER = {"bug": 1.0, "life_avoid": 1.0}`, legacy `NEG_DAMPEN` kept as alias (grep confirmed no other consumers in crow_core.py/crow_mcp_server.py, alias kept for safety).
3. **[`encode()`](../../../crow_core.py:247) (L252-254)** — REQ-010: cache key `truncated[:200]` → `hashlib.sha256(truncated.encode("utf-8")).hexdigest()`. Cache size/eviction unchanged.
4. **[`recall()`](../../../crow_core.py:281) (L281-306)** — NEW signature `recall(query, register, top_k=2, project=None, strict_project=False)`. Consumes `_nearest_hints` dict results; formats strings with `scrub_display` (REQ-006/AD-1 display scrub); `_track_recall` only when ≥1 hint (REQ-001/AD-3c — empty recall no longer pollutes stats with fabricated text). Returns strings for backward compat.
5. **[`recall_multi()`](../../../crow_core.py:316) (L316-394, NEW)** — AD-3: queries each register, merges ALL accepted candidates globally by `eff_sim` desc, slices top_k; zero-hint registers contribute nothing and are NOT tracked (`registers_hit` only); merged confidence = hint-count-weighted mean over hit registers (not ÷8). Returns `{"hints": [dict...], "confidence": float, "registers_hit": [...]}`.
6. **[`_accept()`](../../../crow_core.py:397) (L397-424, NEW)** — AD-2 L127-136 + AD-4: boost `min(1.0 + 0.12*ln(importance+1), 1.15)` (REQ-003 cap); same-project ×`PROJECT_BOOST` within cap; cross-project cutoff `CROSS_PROJECT_CUTOFF`; untagged entry (`entry.get("project")` None/missing) always global-eligible at base cutoff; `strict_project` hard-filters cross-project; **backdoor removed** — `sim >= SIM_CUTOFF` always required (old `importance > 5.0 and sim > 0.15` deleted).
7. **[`_nearest_hints()`](../../../crow_core.py:426) (L426-460)** — REQ-001: both fabricated `f"Crow recalls a faint {register} bias..."` sites deleted; no candidates → `[]`, no accepted → `[]`. Now returns `list[dict]` with `{"text", "sim", "eff_sim"}`, sorted by eff_sim, sliced top_k; routes through `_accept` with project/strict_project.
8. **[`ingest()`](../../../crow_core.py:466) (L466-510)** — AD-1 gate: `key = scrub_text(key); value = scrub_text(value)` BEFORE encode; empty post-scrub value → `{"status": "rejected", "reason": "empty_after_sanitize"}` WITHOUT touching S matrix / update_count / value_bank (S *= lam, delta, _append_value_bank, _persist all skipped). REQ-011: `dampen = NEG_DAMPEN_BY_REGISTER.get(register, NEG_DAMPEN_DEFAULT)` when `polarity < 0`. New `project: str|None = None` param passed through to `_append_value_bank`.
9. **[`_append_value_bank()`](../../../crow_core.py:572) (L572-574, L597+)** — new `project: Optional[str] = None` param; entry gains `"project": project` (backward-compat: readers use `entry.get("project")`, absent/None = global).
10. **Tests — [`tests/test_recall_precision.py`](../../../tests/test_recall_precision.py) (-created)** — plain unittest, no sentence_transformers dependency: `FakeEncoder` (sha256-seeded deterministic vectors) injected as `cm._encoder`, registry dims shrunk in `setUpClass`/restored in `tearDownClass`. 41 tests across 8 classes: CutoffTests (0.34 rejected/0.36 accepted, backdoor gone, defaults), NoFabricatedFallbackTests (empty bank, no-accepted, empty-register recall, arch full-path, bias block), BoostCapTests (importance=1e6 ≤ ×1.15, uncapped normal, same-project cap), ProjectAcceptTests (9 acceptance-matrix cases, legacy no-field entry, ingested tag persisted), RecallMultiTests (eff_sim merge order, zero-hint register skipped + stats hygiene, global top_k slice, weighted confidence, no-hit empty), EncodeCacheKeyTests (200-char prefix collision → distinct vectors, repeat = 1 encode call), NegativeDampenTests (bug/life_avoid −1.0, style/arch −0.6, constants+alias), IngestScrubGateTests (noise rejected, nothing touched, scrubbed value clean in hints incl. emoji removal, key scrubbed), EnvOverrideTests (reimport with env vars set).

Untouched per constraint: register λ values, EMA update math (`S *= lam; S += outer(...)`), `_persist`, FAISS methods, drift/stats/backup/evolve/project-info, `crow_core-myk1yt.py`.

## Result
✅ SUCCESS — all verification commands pass (Python via project `.venv`):

```
python tests\test_recall_precision.py -v → Ran 41 tests in 0.121s — OK
python tests\test_sanitize.py            → Ran 55 tests in 0.002s — OK (regression clean)
python -c "import crow_core"            → import OK — SIM_CUTOFF 0.35 CROSS 0.42 BOOST 1.05
```

## Issues Discovered
- **Test fixture bug (2 iterations, both test-side, zero spec violations):** `_faiss_search` normalizes the residual before sim computation (direction cosine), so scaling the stored vector by 0.2 did NOT produce sim=0.20 — first fixture attempt still yielded sim=1.00. Fixed by constructing the residual direction via explicit orthogonal complement with cosine exactly 0.20 (`query_vec_toward`).
- Note for Batch C: `crow_mcp_server.py::_recall` still uses the old `recall()` loop pattern (top_k//8). It composes fine with the new `recall()` signature (new params are keyword-with-default), but Batch C should switch it to [`recall_multi()`](../../../crow_core.py:316) per AD-3/AD-5. Same for REST `/recall`.
- Note: `recall()` now skips `_track_recall` on zero-hint results — server-side drift/evolve consumers rely on stats only from real hits, which is the intended AD-3c behavior.

## Next Step Recommendations
- VP: dispatch Batch C (server + i18n) — wire `_recall`/`/recall` to `recall_multi(query, registers, top_k, project, strict_project)` and route `/ingest` through the (already core-enforced) scrub gate; surface `project`/`strict_project` tool params per AD-5.
- Batch D migration script benefits: `entry.get("project")` backward-compat verified by test.

## Affected File List
- **Modified:** `crow_core.py` (944 → 1189 lines)
- **Created:** `tests/test_recall_precision.py` (41 tests)
