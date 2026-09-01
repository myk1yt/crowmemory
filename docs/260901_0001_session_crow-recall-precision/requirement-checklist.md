# Requirement Checklist
## Task: Crow Memory Recall Precision Improvement (잡음 제거 + 프로젝트 인식 + 툴 축소)
## Date: 260901
## Session Folder: docs/260901_0001_session_crow-recall-precision/

## Context (from P1 brainstorm, user-approved)
- User: "기억을 recall할때 잡음이 많이 딸려온다" — noise includes irrelevant hints AND kaomoji/symbol garbage (">.<", "ㅋㅋㅋ" etc.)
- User: "A워크스페이스에서 C워크스페이스의 기억을 꺼낸다" — wants workspace-aware recall
- User: "Crow는 언제나 global로 사용할 것" (DECISION: NO physical isolation; single global crow.bin + project tagging)
- User: "도구가 너무 많다, 줄여라" — 10 MCP tools → 3

## Requirements
- [ ] [REQ-001] Recall 잡음 — remove fabricated fallback hints ("Crow recalls a faint..."). Return empty hints when no match; confidence=0 is the signal. Affects crow_core.py `_nearest_hints()` (L308-310) and empty-candidates path (L288-289)
- [ ] [REQ-002] Recall 컷오프 상향: base 0.28 → 0.35 (configurable via env var, e.g. CROW_SIM_CUTOFF). Remove the importance backdoor (`importance > 5.0 and sim > 0.15`) — minimum acceptable sim must not fall below base cutoff
- [ ] [REQ-003] Importance boost cap: `1.0 + 0.12*log(...)` is unbounded (×1.36+ at importance 20). Cap at ×1.15
- [ ] [REQ-004] domain=all aggregation fix in crow_mcp_server.py `_recall()` (L85-96): (a) skip registers with no matching hints instead of counting fallback fillers, (b) merge hints globally similarity-ranked before slicing top_k (current: fixed register order), (c) avoid polluting recall_stats/drift with 8 forced per-register queries per call
- [ ] [REQ-005] Kaomoji/symbol sanitization at ingest gate: scrub key+value BEFORE encode — symbol runs (>.<, ^^, 0v0, etc.), lone Korean jamo laughter (ㅋㅋ/ㅠㅠ/ㅎㅎ), repeated punctuation (≥3), emoji; whitespace normalization. Must NOT damage legitimate tokens (C++, "...", code identifiers). Values are natural-language descriptions, not code
- [ ] [REQ-006] Recall display-time scrub: apply same sanitizer to hint output so legacy value_bank entries (already stored with kaomoji) render clean
- [ ] [REQ-007] One-time value_bank migration script: clean existing ~500 entries' text, re-encode vectors, rebuild FAISS index (fixes embedding-space pollution of legacy memories)
- [ ] [REQ-008] Project tagging (user decision: global-only storage, NO physical isolation): optional `project` param on crow_recall/crow_ingest; value_bank entries tagged with project slug (untagged=null=global). Recall: same-project entries get similarity boost (within cap), cross-project entries face stricter cutoff; strict-filter mode optional param. Weight matrix S stays global/unchanged
- [ ] [REQ-009] Tool consolidation 10→3: `crow_recall` (absorbs crow_get_user_bias via format param), `crow_ingest` (absorbs crow_ingest_from_build via optional exit_code/user_edited params → auto-polarity), `crow_admin` (action-dispatch absorbing: diagnostics, check_drift, manage_prompt, manage_backup, evolve_propose, project_info)
- [ ] [REQ-010] Encode cache key collision fix: cache key currently = first 200 chars (crow_core.py L236) — replace with hash of full truncated text
- [ ] [REQ-011] NEG_DAMPEN per-register: global 0.6 damping contradicts purpose of `bug`/`life_avoid` registers (failure-memory registers). Register-aware damping (avoid-type registers = 1.0)
- [ ] [REQ-012] Fork strategy: `crow_core-myk1yt.py` / `crow_mcp_server-myk1yt.py` duplicates exist and active state file is `memory/crow-myk1yt.bin`. P3 must decide: unify fork (single source + parameterized path) or dual-file sync, and specify which file(s) receive implementation

## Out of Scope
- Physical per-workspace crow.bin isolation (user rejected — global memory always)
- Register decay λ values, VALUE_BANK_MAX, top_k defaults (evaluated as appropriate)

## User Decisions (recorded in decisions.md)
1. Crow stays global — tagging not splitting
2. Kaomoji/symbol garbage explicitly in noise scope