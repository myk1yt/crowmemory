# User Decisions
## Session: crow-recall-precision (260901)

## [2026-09-01 23:29] — Crow는 언제나 global로 사용
- "나는 crow를 언제나 global로 사용할거야" → [ACTION: REJECTED physical per-workspace isolation]
- Design changed to: single global crow.bin + project **tagging** in value_bank metadata (boost same-project, stricter cutoff for cross-project, optional strict filter). No file separation.

## [2026-09-01 23:30] — 잡음의 범위에 kaomoji/기호 포함
- "내가 말하는 잡음에는 >.< 뭐 이런 이상한 기호들도 포함이야" → [ACTION: SCOPE ADDED — REQ-005/006/007]
- Sanitization required at ingest gate (before encode, to protect embedding space), recall display scrub, and one-time legacy value_bank migration.

## [2026-09-01 23:27] — 3개 개선사항 진행 승인
- "좋아 이 3개에 대해 엄격한 분석을 통해 수정해보도록 하자" → [ACTION: APPROVED — full pipeline P3→P7]
- Scope: recall noise removal, workspace-aware recall (revised to global+tagging), tool consolidation 10→3.

## [2026-09-02 06:28] — value_bank 병합 수용 (Option A)
- "(a) 병합 수용 — 두 value_bank를 하나로 합치고 global로 사용" → [ACTION: APPROVED — merge both value_bank sets into one global set]
- Rationale: consistent with "crow는 언제나 global". CROW_STATE_TAG keeps managing the .bin only; value_bank filename stays unsuffixed (option (b) tag-suffix development REJECTED for now).
- Note: "레거시기억 정화는 뭐야? 기존 레거시 기억은 그대로 사용하되, 잡음이 사라지도록 하는거야?" — user confirmed understanding: migration preserves memories, removes noise only.

## [2026-09-02 07:08] — VP CORRECTION: live state is crow.bin, NOT crow-myk1yt.bin
- User question "왜 crow.bin이 아니고 crow-myk1yt.bin이야?" triggered re-verification → [ACTION: CORRECTED — CROW_STATE_TAG removed from start_crow_sse-myk1yt.bat]
- Evidence (file mtimes): memory/crow.bin modified 2026-09-02 15:53 (continuously updated by live server); crow-myk1yt.bin modified 2026-08-31 05:02 (stale snapshot). The Batch E / REQ-012 claim "active state file is crow-myk1yt.bin" was WRONG — the entire -myk1yt set (bin + value_bank + recall_stats) is a dead copy.
- Consequence: had the tagged bat been run, the server would have adopted the stale 08-31 snapshot as active state, diverging from live memory. Fix: tag setting removed; LOCK_FILE corrected to crow.bin.lock; server continues on crow.bin unchanged.
- Corrected activation sequence: (1) stop server → (2) merge_value_bank.py --apply (merges the dead copy's 26 unique entries into the live bank, scrub included) → (3) restart via start_crow_sse-myk1yt.bat (now untagged, identical behavior to start_crow_sse.bat).
- The -myk1yt data files are retained untouched as historical archive. CROW_STATE_TAG remains a supported feature for future intentional isolation.

## [2026-09-02 07:18] — "Search:" 로그 잔해 기억 일괄 정리 승인
- User: "지금 진행 — Search: 패턴 기억 일괄 정리" → [ACTION: APPROVED — purge search-log debris entries from value_bank]
- Trigger: post-activation recall smoke test showed life_context returning "Search: translationMode → 0 AST matches" debris instead of actual life memories. Root cause: past sessions ingested VibeZoo search logs as memories; accumulated importance let them survive cap eviction. Evidence: merge dry-run pruned 26 entries all of this pattern.
- Scope: remove entries whose text matches search-log debris patterns (e.g. key/value starting "Search:", "Web search success:") from the live value_bank.json; backup first; dry-run default; --apply gated. The weight matrix S is NOT touched (residual trace decays via λ).

## [2026-09-02 07:41] — -myk1yt 파일 전면 정리 + 원본 최신화 우선
- User: "start_crow_sse-myk1yt.bat이 start_crow_sse.bat보다 최신인데? 최신의 파일들이 -myk1yt여선 안 되니 직접 일일히 대조해서, 원본파일의 최신화를 유지하면서 -myk1yt 파일들을 정리하도록 해" → [ACTION: APPROVED — best-of-both merge into originals, then remove -myk1yt files; memory/*-myk1yt data preserved as archive]
- CRITICAL constraint surfaced by user: originals must end up NEWER-or-equal in content vs their -myk1yt counterparts. Where -myk1yt carries improvements (e.g. start_crow_sse-myk1yt.bat's LOCK_FILE fix, venv-python preference), merge them INTO the original before deleting the copy.
- In scope: -myk1yt docs (6), code shims (2), bats (start_crow_sse-myk1yt.bat, scripts/run_elevated-myk1yt.bat), requirements-myk1yt.txt, -myk1yt.gitignore + dangling reference cleanup (install scripts, docs describing fork shims).
- Preserved: memory/crow-myk1yt.bin, value_bank-myk1yt.json, recall_stats-myk1yt.json (historical archive).