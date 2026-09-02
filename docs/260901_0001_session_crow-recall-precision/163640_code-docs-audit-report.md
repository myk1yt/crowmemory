# Code Mode Task Report — 프로젝트 문서 전수 최신화 (v1.5.0)

**Mode:** 💻 Code
**Date:** 2026-09-02 (163640 KST)
**Task:** README/ARCHITECTURE/CHANGELOG 등 전 문서를 실제 코드 상태(커밋 0310557..ef5233d, v1.5.0)에 맞춰 전수 최신화

---

## Task Summary

전 문서를 스캔하여 구버전 내용을 목록화한 뒤, ground truth(실제 코드)에 맞춰 사실 정정 중심으로 갱신하고, 재스캔으로 잔여 불일치 0을 확인했다. 문서(.md)만 수정 — 코드/JSON/bat은 일절 수정하지 않았다.

## Ground Truth 확인 (Phase 1 — 코드 대조)

| 항목 | 코드 근거 |
|------|----------|
| 서버 버전 1.5.0 | `crow_mcp_server.py:256` (`version="1.5.0"`) |
| 3-tool 스키마 | `crow_mcp_server.py` crow_recall(L284: format/bias_block/project/strict_project), crow_ingest(L354: polarity 선택적 + exit_code/user_edited/project), crow_admin(L413: 6-action) |
| SIM_CUTOFF 0.35 | `crow_core.py:106` (`CROW_SIM_CUTOFF`), CROSS_PROJECT_CUTOFF 0.42(L107), PROJECT_BOOST 1.05(L109) |
| importance 부스트 ×1.15 cap | `crow_core.py:412-425` (`min(boost * PROJECT_BOOST, 1.15)`) |
| 백도어 제거 | `crow_core.py:417` 주석 + `L432` (`sim >= SIM_CUTOFF` 항상 요구) |
| recall_multi() | `crow_core.py:316` (글로벌 eff_sim 병합) |
| NEG_DAMPEN_BY_REGISTER | `crow_core.py:114-117` (bug/life_avoid=1.0, 기본 0.6) |
| sha256 캐시 키 | `crow_core.py:255` |
| 스크럽 게이트 | `crow_core.py:484-485` (`empty_after_sanitize`) |
| value_bank project 필드 | `crow_core.py:613` (`project`: None/absent=global) |
| CROW_STATE_TAG | `crow_mcp_server.py:71-80` (`resolve_state_path`) — 현재 미사용 |
| bat 태그 제거 | `start_crow_sse-myk1yt.bat` REVISED 2026-09-02 주석 확인 — 일반 bat과 동일 동작 |
| 231 테스트 | findstr 실측: sanitize 55 + tool_schema 56 + recall_precision 42 + merge 33 + migrate 27 + purge_debris 18 = 231 |
| shim 재수출 | `crow_core-myk1yt.py` / `crow_mcp_server-myk1yt.py` (`__deprecated_shim__` 위임) |

## Actions Taken (Phase 2)

| 파일 | 수정 내용 |
|------|----------|
| `README.md` | 도구 섹션 "10 MCP Tools + 1 Script + 2 Prompts" → "3 MCP Tools + 2 Prompts (AD-5)" 재작성(파라미터 실측 기반); 프로젝트 태깅/스크럽 소개 블록; 유지보수 스크립트 3종 표(dry-run/--apply); Fork Files & Data Layout 표(shim+아카이브+CROW_STATE_TAG); 231 테스트 섹션; installer "10→3 Crow tools"; Verify 예시 crow_admin(action="diagnostics"); Sharing Policy에 crow_sanitize.py 추가; REST 예시 version 1.5.0 + project 필드; footer v1.5.0 |
| `README-myk1yt.md` | 본체와 동일하게 전부 동기화 (copy 원칙, 구조 동일함 확인) |
| `CROW_MEMORY_ARCHITECTURE.md` | 헤더 v1.5.0/2026-09-02; §4.1 recall 흐름에 sha256 캐시·SIM_CUTOFF·importance cap·project 태깅·recall_multi 반영; §4.2 ingest 의사코드에 스크럽 게이트+project 필드; §5 도구 스키마를 실제 3-tool JSON으로 전면 교체 + 상수 표 추가(SIM_CUTOFF/PROJECT_BOOST/NEG_DAMPEN_BY_REGISTER); §6.1 Step7 crow_admin(action="evolve"); §7.1 표 갱신; §7.3 NEG_DAMPEN_BY_REGISTER; §8 로드맵 도구명 갱신 + Phase4 프로젝트 격리 → 태깅 방식 정정; Appendix C에 SDK 2.1.1 노트 + crow_admin 예시; 신규 §12 (Fork Files & State Tagging) + §13 (Version History) |
| `CROW_MEMORY_ARCHITECTURE-myk1yt.md` | 본체와 전면 동기화 (copy — 본체가 SDK 노트·버전 히스토리까지 흡수하여 구조 차이 해소) |
| `CHANGELOG.md` | [1.5.0] — 2026-09-02 항목 추가 (유저 관점 "you can now" 문체: 잡음 사라진 recall, 프로젝트 태깅, 버그 교훈 완전 보존, 3-tool 통합, dry-run 스크립트, sha256 캐시, 부스트 cap) |
| `CHANGELOG-myk1yt.md` | 동일 [1.5.0] 항목 추가 (1.4.5 위) |
| `docs/PROJECT_CONTEXT.md` | 헤더 v1.5.0; 디렉토리 구조에 crow_sanitize.py + shim + 아카이브 표기; value_bank 428 항목; §5 다이어그램 3개 도구; 데이터 흐름 crow_admin(action="evolve"); 모듈 섹션 전면 갱신(정밀도 상수/스크럽 게이트/sha256); 데이터 저장소에 project 필드 + 아카이브 행; 알려진 이슈 #5 해결 표시; 개발 환경에 스크립트/테스트 명령 |
| `docs/PROJECT_CONTEXT-myk1yt.md` | 본체와 동일 정정 + 이 파일 고유의 Startup 폴더/SDK 섹션은 구조 존중 후 사실만 유지 |
| `docs/CROW_MEMORY_AUTOSTART_DESIGN.md` | **수정 불요** — 재스캔에서 구버전 도구 언급 0건 확인 (설계 문서, 사실 오류 없음) |
| `docs/CROW_MEMORY_AUTOSTART_DESIGN-myk1yt.md` | **수정 불요** — 동일 |
| `system_prompt.example.md` + `en.md` + `ko.md` | RULE 2의 `crow_ingest_from_build` 참조 → `passing exit_code to crow_ingest`로 정정 (3개 파일 동일) |
| `AGENTS.md` | Batch E 갱신본 검증 → 불일치 1건만 수정: backup action 설명에 `list` 누락 (서버 `_manage_backup`은 create/rotate/list/recover) + project_info를 "project-tagged"로 정정 |
| `AGENTS-myk1yt.md` | **구버전 10-tool 표 발견** → 본체와 전면 동기화 (copy) |
| `custom_modes.example.yaml` | 스캔만 — 구버전 도구 언급 0건 (crow_recall/crow_ingest만 언급, 정상) |

## Result (Phase 3 — 재스캔 검증)

### 구버전 징후 키워드 재스캔

패턴: `crow_diagnostics|crow_check_drift|crow_ingest_from_build|crow_get_user_bias|crow_manage_prompt|crow_manage_backup|crow_project_info|crow_evolve_propose` — 히트 23건 중 검토 결과:

| 위치 | 판정 |
|------|------|
| CHANGELOG.md / CHANGELOG-myk1yt.md 구버전 항목 (1.0.0/1.2.0 등) | ✅ OK — 역사 기록, 절대 수정 금지 영역 |
| AGENTS.md / ARCHITECTURE.md "absorbs crow_get_user_bias/ingest_from_build" | ✅ OK — 흡수 관계 명시 (정당한 언급) |
| docs/ 세션 보고서·체크리스트 (260830, 260901) | ✅ OK — 세션 이력 아카이브 |
| memory/system_prompt.md | ⚠️ 예외 — **런타임 개인 데이터** (git 제외, Sharing Policy "❌ No"). 문서가 아님. 서버가 `crow_admin(action="prompt")`으로 관리하므로 수동 수정 대상 아님. 다음 evolve 세션에서 자연 갱신 예정 |
| AGENTS-myk1yt.md | ❌ → ✅ 수정됨 (본체 동기화) |

패턴 `0\.28|importance > 5|physical isolation|isolated project memory` — 히트 전부 CHANGELOG 역사 항목(1.3.3 기록) 또는 세션 보고서. 현행 문서 잔여 0건.

패턴 `10 MCP Tools|10개 MCP|10 Crow|all 10|10 tools|10 도구` — 히트 전부 CHANGELOG 역사 항목 + 세션 보고서. custom_modes.example.yaml: 0건.

### 스키마 대조 스팟체크 (crow_mcp_server.py 실측)

| 문서 항목 | 서버 실측 | 일치 |
|-----------|-----------|------|
| crow_recall: query/register/domain/top_k(1-5)/format(hint\|bias_block)/project/strict_project | L284-341 | ✅ |
| crow_ingest: key/value/register 필수, polarity 선택적, exit_code 자동 매핑(+1.5/+0.5/-0.5/-1.0), user_edited, project | L354-398, L127-140 | ✅ |
| crow_admin: 6-action enum + args passthrough | L403-433, _admin L154-169 | ✅ |
| backup 하위: create/rotate/list/recover | _manage_backup L209-224 | ✅ (AGENTS.md list 누락 수정 반영) |
| i18n 베이스 정의 | crow_i18n.py format/strict_project/exit_code/args | ✅ |

## Issues Discovered

1. **memory/system_prompt.md**에 구버전 도구 참조(`crow_ingest_from_build`) 잔존 — 런타임 개인 데이터로 스코프 밖 처리. HITL 승인 규칙이므로 수동 수정 금지 원칙상 그대로 둠. (예시 템플릿 3종은 모두 정정 완료)
2. `project_info` admin action이 물리 격리 디렉토리를 생성하는 legacy surface는 기존 감사(093300)에서 이미 플래그된 사항 — 코드 영역이라 본 작업 스코프 밖.

## Next Step Recommendations

- 다음 세션에서 `memory/system_prompt.md`의 RULE 2를 HITL 승인 경로로 갱신 권장 (`crow_admin(action="prompt", args={action:"append"})`).
- `project_info` 물리 격리를 태깅 방식으로 전환할지 코드 레벨 결정 필요 (기존 감사 권고 이월).

## Affected File List

- README.md, README-myk1yt.md
- CROW_MEMORY_ARCHITECTURE.md, CROW_MEMORY_ARCHITECTURE-myk1yt.md
- CHANGELOG.md, CHANGELOG-myk1yt.md
- docs/PROJECT_CONTEXT.md, docs/PROJECT_CONTEXT-myk1yt.md
- system_prompt.example.md, system_prompt.example/en.md, system_prompt.example/ko.md
- AGENTS.md, AGENTS-myk1yt.md
- (검증만, 무수정) docs/CROW_MEMORY_AUTOSTART_DESIGN.md(-myk1yt), custom_modes.example.yaml