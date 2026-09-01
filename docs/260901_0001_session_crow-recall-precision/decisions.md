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