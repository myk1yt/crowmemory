# Code Task Report — `-myk1yt` 파일 전면 정리 (best-of-both 병합 후 삭제)

**Mode:** code · **Date:** 2026-09-02 (KST) · **Report Folder:** `docs/260901_0001_session_crow-recall-precision/`

## Task Summary
워크스페이스의 모든 `-myk1yt` 파일을 전수 인벤토리화하고 원본과 일일 대조하여, 사본이 우위인 내용을 원본에 병합한 뒤 사본을 휴지통으로 삭제했다. 원본이 항상 최신으로 끝나도록 보장했으며, `memory/*-myk1yt.*` 데이터 아카이브와 `.git_corrupted_bak260830/`은 보존했다.

## Step 1 — 전수 인벤토리 (전체 워크스페이스 grep `-myk1yt`)

| 분류 | 파일 | 처리 |
|------|------|------|
| (A) 원본-사본 쌍 | 12쌍 (아래 대조표) | 대조 → 병합/동일확인 → 삭제 |
| (D) 보존 | `memory/crow-myk1yt.bin`, `value_bank-myk1yt.json`, `recall_stats-myk1yt.json` + 4개 `.bak.merge-*` 백업 | **보존 (역사 아카이브)** |
| (D) 보존 | `.git_corrupted_bak260830/` 내부 전체 | **보존 (조사만 — 내부에 -myk1yt 파일명 없음 확인)** |
| (D) 보존 | docs/ 세션 보고서·feedbacks·plans 내부 참조 | **보존 (과거 기록, 수정 금지)** |
| (C) 참조-무해 | `scripts/migrate_value_bank.py`, `scripts/merge_value_bank.py`의 `--state-tag myk1yt` / `value_bank-myk1yt.json` 플래그 도움말 | **보존 — 기능적 유틸리티** (아카이브 대상 스크립트, 테스트가 이를 참조: test_migrate 27, test_merge 33) |
| (C) 참조-무해 | `crow_mcp_server.py` docstring의 `CROW_STATE_TAG` 예시 `myk1yt` | **보존 — 코드 예시일 뿐** |
| (C) 참조-무해 | `tests/test_tool_schema.py`, `test_migrate.py`, `test_merge.py`의 `myk1yt` | **보존 — 테스트 픽스처** |
| (C) 참조-무해 | README/CHANGELOG의 `github.com/myk1yt` 공개 URL, 사용자 이메일 | **보존 — 공개 계정 정보 (이전 보안 감사 무해 확정)** |
| .zoo/.roo/.vscode/.github | grep 결과 0건 | **수정 불요** |

## Step 2-3 — 쌍별 대조 및 병합 결과

| 쌍 | 대조 결과 | 조치 |
|----|----------|------|
| `start_crow_sse.bat` vs `-myk1yt.bat` | 사본에만 태그-제거 이력 주석 + Phase 2 이중 lock 정리가 있었음 (원본은 venv-python 선호·/health 엔드포인트로 이미 우위) | 사본 내용을 원본에 통합 → **바이트 동일 확인 후 삭제** |
| `requirements.txt` vs `-myk1yt.txt` | 사본에만 `einops>=0.7.0` + `mcp==2.1.1` 핀 (원본은 `mcp>=1.0.0`) | einops/mcp 핀을 원본에 병합 → **바이트 동일 확인 후 삭제** |
| `CHANGELOG.md` vs `-myk1yt.md` | 사본에만 `[1.4.5] — 2026-08-30` 항목 존재 (원본 누락) | 1.4.5 항목을 원본에 병합 → **동일 확인 후 삭제** |
| `.gitignore` vs `-myk1yt.gitignore` | 사본에만 `memory/` 전체 제외, `.git_corrupted_bak*/`, 로컬 docs 제외 규칙 존재 | 3개 규칙을 원본에 병합 (배치 순서만 사본과 다름 — 의미 동일) → **삭제** |
| `docs/PROJECT_CONTEXT.md` vs `-myk1yt.md` | 사본에만 최신 자동시작 다이어그램(Startup 폴더 활성 경로), SDK 2.1.1 표, 상세 모듈 설명 존재 | 전량 원본에 병합 + 실측 정정(`Crow_Memory.vbs` — `-myk1yt` 문서의 `Crow_Memory_SSE.bat`는 실패한 Task Scheduler 방식을 서술한 부정확한 표기였음) → **삭제** |
| `docs/CROW_MEMORY_AUTOSTART_DESIGN.md` vs `-myk1yt.md` | 사본에만 Current Status 헤더, /health·/mcp 엔드포인트 표, §6 구현 노트 존재 | 전량 원본에 병합 (§6.1은 실측상 실존 런처 `Crow_Memory.vbs`로 정정) → **삭제** |
| `README.md` vs `-myk1yt.md` | 바이트 동일 (163640 세션에서 동기화됨) | 사본 삭제만 |
| `CROW_MEMORY_ARCHITECTURE.md` vs `-myk1yt.md` | 바이트 동일 | 사본 삭제 + §12를 "통합 완료"로 갱신 |
| `AGENTS.md` vs `-myk1yt.md` | 바이트 동일 | 사본 삭제만 |
| `scripts/run_elevated.bat` vs `-myk1yt.bat` | 바이트 동일 (원본이 이미 %~dp0 기반 최신) | 사본 삭제만 |
| `crow_core-myk1yt.py` / `crow_mcp_server-myk1yt.py` (shims) | shim — 원본보다 나은 논리 없음 (재수출 shim) | 전체 워크스페이스 grep으로 **import하는 코드 0건** 확인 후 삭제 |

## Step 4 — 삭제 목록 (전부 Recycle Bin, 영구삭제 0건)

**git tracked (git rm --cached 후 휴지통):** `AGENTS-myk1yt.md`, `CHANGELOG-myk1yt.md`, `CROW_MEMORY_ARCHITECTURE-myk1yt.md`, `README-myk1yt.md`, `crow_core-myk1yt.py`, `crow_mcp_server-myk1yt.py`, `docs/PROJECT_CONTEXT-myk1yt.md`, `start_crow_sse-myk1yt.bat` (8)

**untracked (휴지통만):** `requirements-myk1yt.txt`, `scripts/run_elevated-myk1yt.bat`, `-myk1yt.gitignore`, `docs/CROW_MEMORY_AUTOSTART_DESIGN-myk1yt.md` (4)

**부산물 정리:** `__pycache__/crow_core-myk1yt.cpython-311.pyc`, `__pycache__/crow_mcp_server-myk1yt.cpython-311.pyc`, `sse_server-myk1yt.log` (3) — 휴지통 처리.

**보존 확인 (삭제 시점 기준):** `memory/` 아카이브 7개 + 백업 4개, `.git_corrupted_bak260830/` 전체, docs/ 과거 기록 전체 — 무손상.

## Step 5 — 참조 정리 결과

| 파일 | 변경 |
|------|------|
| `README.md` | Fork Files 섹션 → "전면 병합·삭제 완료, memory 아카이브만 보존" 표로 갱신 |
| `CROW_MEMORY_ARCHITECTURE.md` §12.1/§12.2 | shim 설명 → 통합 완료 서술로 갱신; `start_crow_sse-myk1yt.bat` 링크 제거 |
| `docs/PROJECT_CONTEXT.md` | 디렉토리 구조에서 shim 2행 제거, `resolve_state_path` 주석 정리 |
| `install.py` / `install.ps1` / `watch_crow_sse.bat` / `test.bat` / `scripts/register_crow_task.ps1` | `-myk1yt` 참조 0건 — 실측(findstr) 확인, 수정 불요 |
| `.zoo/` `.roo/` `.vscode/` `.github/` | `-myk1yt` 참조 0건 — 조사만 수행, 수정 불요 |

## Step 6 — 검증 결과

| 항목 | 명령 | 결과 |
|------|------|------|
| 테스트 회귀 | `.venv\Scripts\python.exe -m unittest tests.test_sanitize tests.test_recall_precision tests.test_tool_schema` | **Ran 153 tests — OK** (55+42+56) |
| 모듈 import | `python -c "import crow_core, crow_mcp_server"` | **IMPORT OK** |
| grep 잔여 | 전체 재스캔 (파일명) | **7건 = memory/ 아카이브 + 백업 파일뿐** (허용 대상) |
| git status | 의도된 변경만 (D 8 + M 8 + untracked 사전 존재) | ✅ 의도된 변경만 |
| bat 실행 | **실행 금지 준수** — 서버 구동 중 (포트 충돌 방지), 내용 정적 검증만 수행 | ✅ |
| 원본 최신 증명 | 4개 병합 쌍은 `git diff --no-index --quiet`로 **바이트 동일** 확인, 6개 쌍은 원본이 이미 최신 | ✅ |

## Issues Discovered
1. `docs/CROW_MEMORY_AUTOSTART_DESIGN-myk1yt.md`·`docs/PROJECT_CONTEXT-myk1yt.md`의 Startup 폴더 기술이 `Crow_Memory_SSE.bat`이었으나 실측(`dir %APPDATA%\...\Startup`) 결과 실존 런처는 `Crow_Memory.vbs`임 — 병합 시 사실로 정정함 (사본의 부정확한 정보를 그대로 이식하지 않음).
2. `crow_mcp_server_v1_bak.py`는 이번 작업 대상 아님 (사전 존재 untracked, -myk1yt 아님) — 별도 판단 필요 시 VP 보고.
3. `scripts/migrate_value_bank.py`·`scripts/merge_value_bank.py`의 `myk1yt` 참조는 아카이브 조작 유틸리티 기능이므로 유지 (삭제 시 테스트 60건 실패 초래).

## Next Step Recommendations
- VP: 커밋 (Sub-mode는 git commit 금지 규정 준수 — 스테이징만 수행됨: `D` 8건은 이미 staged, 나머지는 working tree 변경).
- 커밋 시 권장: `chore(cleanup): merge -myk1yt fork copies into originals and remove duplicates`.
- 참고: `.gitignore`가 이제 `memory/` 전체를 커버하므로 memory 데이터는 push 대상에서 완전히 제외됨.

## Affected File List
- **Modified:** `.gitignore`, `CHANGELOG.md`, `README.md`, `CROW_MEMORY_ARCHITECTURE.md`, `docs/PROJECT_CONTEXT.md`, `docs/CROW_MEMORY_AUTOSTART_DESIGN.md`, `requirements.txt`, `start_crow_sse.bat` (병합), `scripts/run_elevated.bat` (사전 세션 변경, 검증만)
- **Deleted (Recycle Bin):** 12개 `-myk1yt` 사본 + 부산물 3개
- **Preserved:** `memory/*-myk1yt.*` (7), `.git_corrupted_bak260830/`, docs/ 과거 기록 전체