# 🧠 Crow Memory — 프로젝트 컨텍스트 문서

> **버전:** v1.5.0 | **라이선스:** MIT | **저장소:** [myk1yt/crowmemory](https://github.com/myk1yt/crowmemory)
> **최종 갱신:** 2026-11-24 | **문서 목적:** 인간 및 AI를 위한 온보딩 가이드

## 0. v1.5.0 Serverless (현재 기본 경로)

v1.5.0은 **데몬 없는(serverless)** 구조입니다. MCP 서버를 띄우지 않고, 에디터의 라이프사이클 훅이 짧은 CLI 프로세스를 호출해 로컬 SQLite 파일(`~/.crow-memory/crow.db`)을 읽고 씁니다.

| 항목 | v1.5.0 (현재) | v1.5 (레거시) |
|------|-------------|---------------|
| 실행 구조 | 훅 → `core/crow_cli.py` → SQLite | 상주 MCP 서버 (SSE + Streamable HTTP) |
| 상주 프로세스 / 포트 | 없음 (0개 상주, 포트 없음) | `9020` / `9021`, Task Scheduler |
| 의존성 | Python 3.11+ 표준 라이브러리만 | torch, faiss, sentence-transformers, uvicorn, mcp |
| 데이터 | `~/.crow-memory/crow.db` | `memory/crow.bin` + `value_bank.json` |
| 설치 | `python scripts/install_plugin.py` | `install.py` / `install.ps1` |
| 회상 점수 | `0.5 × 토큰 코사인 + 0.5 × BM25` × 반감기 감쇠 × 중요도 | 행렬 투영 + FAISS 최근접 |

### 0.1 설치 (5분 이내)

```bash
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
python scripts/install_plugin.py            # 전체 도구, 또는 --tools kimi-code
```

- `core/` 6개 모듈을 `~/.crow-memory/core/`로 복사하고 `bin/` 심(shim)을 만듭니다.
- 선택한 도구의 어댑터를 배포합니다: Antigravity(`~/.gemini/config/plugins/crow-memory/`), Kimi Code(`~/.kimi-code/`), Claude Code(`~/.claude/plugins/crow-memory/`), Cursor(`~/.cursor/`), Cline(`~/.clinerules`), Codex(`~/.codex/AGENTS.md`), Zoo Code(`~/.zoo/AGENTS.md`). 레거시 `plugins/crow_memory/`(밑줄) 디렉터리가 남아 있으면 설치기는 NOTE만 출력하고 삭제하지 않습니다.
- 기존 v1.5 `memory/value_bank.json`을 `crow.db`로 이관하고 `memory/system_prompt.md`를 `<CROW_HOME>/system_prompt.md`로 바이트 단위 그대로 시드합니다 (기존 파일은 `--force-prompt` 없이는 덮어쓰지 않음). 검증값: `processed=488, inserted=486, merged=2, skipped_junk=12`.
- 덮어쓴 파일은 `*.bak.<timestamp>`로 보존하며, 삭제는 하지 않습니다.

### 0.2 훅 4트리거

| 트리거 | 명령 | 동작 |
|---|---|---|
| SessionStart | `crow_cli.py hook session-start --format text` | 2단 `[User Bias]` 블록 출력 |
| UserPromptSubmit | `hook pre-invocation` | 프롬프트 해시 기준 1회 주입 |
| PostToolUse(Shell) | `hook post-tool` | 빌드/테스트 결과 자동 기록 (+1.0 / -0.5) |
| 세션 종료(수동) | `ingest --key ... --register arch` | 핵심 결과 수동 저장 |

### 0.3 CLI

`hook`, `recall`, `ingest`, `admin`, `migrate`, `serve-stdio` (인자 표는 README "CLI Reference" 참조).

### 0.4 데이터 위치

`~/.crow-memory/` 아래에 `crow.db`, `core/`, `bin/`, `backups/`, `system_prompt.md`, `.last_inject.json`, `.last_ingest.json`이 있습니다.

### 0.5 검토와 철회

모델이 쓴 규칙은 신뢰하지 않습니다. `admin --action prompt --args '{"action":"append",...}'`는 내용을 정화하고 한 줄로 평탄화한 뒤 400자로 제한해 `system_prompt.md`의 `[Unreviewed Model Suggestions]` 구역에 넣습니다. 사람이 `admin prompt approve`를 실행해야 검토된 규칙이 됩니다. 잘못 저장된 기억은 `admin --action delete`(단건) 또는 `admin --action purge`(조건 일괄)로 같은 CLI에서 제거합니다. 주입되는 바이어스 블록은 "과거 세션의 참고 맥락"으로만 렌더링되며 새 지시가 아닙니다.

> ⚠️ 1장부터 10장까지는 **v1.5.0-mcp 서버 방식**을 설명합니다. v1.5.0만 사용한다면 0장만 읽어도 됩니다.

## 1. 프로젝트 정체성

**Crow Memory**는 LLM 기반 AI 코딩 어시스턴트를 위한 **외부 시냅틱 메모리 시스템**입니다. MCP(Model Context Protocol) 서버로 구현되어, AI 에이전트가 세션 간에 사용자 선호도, 아키텍처 결정, 버그 패턴 등을 기억하고 회상할 수 있게 합니다.

> *"까마귀는 코드를 기억하지 않지만, 그 코드를 작성한 손을 기억한다."*

### 핵심 가치 제안
- **세션 간 기억 유지**: 코딩 스타일, 아키텍처 선호, 버그 인사이트를 영구 저장
- **MCP 표준 기반**: 모든 MCP 호환 AI 코딩 도구(Zoo Code, Kimi Code 등)와 통합
- **자가 진화**: 통계적 패턴 감지 → `[Unreviewed Model Suggestions]`에 보관 → 사람이 `admin prompt approve`로 승격 → 시스템 프롬프트 규칙화
- **96개 언어 지원**: 완전한 국제화(i18n)

## 2. 디렉토리 구조

> v1.5.0의 실제 코드는 `core/`(6개 모듈), `adapters/`(도구별 훅/스킬), `scripts/install_plugin.py`입니다. 아래 트리는 v1.5 서버 기준입니다.

```
Crow Memory/
├── .github/                  # GitHub 메타데이터
├── .vscode/                  # VS Code 자동화
├── .zoo/                     # Zoo Code 설정 템플릿
├── i18n/                     # 96개 언어 번역 JSON
├── Logo/                     # 로고 이미지
├── memory/                   # 메모리 저장소 (git 제외)
│   ├── crow.bin              # ~140MB 고정 크기 가중치 행렬 (활성)
│   ├── value_bank.json       # 중요도 기반 우선순위 큐 (현재 428 항목, 최대 500개)
│   ├── recall_stats.json     # 회상 통계
│   ├── system_prompt.md      # HITL 승인 규칙
│   ├── crow-myk1yt.bin       # 역사 아카이브 (서버가 읽지 않음)
│   └── *-myk1yt.json         # 역사 아카이브
├── scripts/                  # 검증 유틸리티
├── system_prompt.example/    # 프롬프트 템플릿
├── crow_core.py              # 핵심 엔진
├── crow_sanitize.py          # 입력 정화 (kaomoji/emoji/jamo-run)
├── crow_mcp_server.py        # MCP 서버 (3 도구 + REST)
├── crow_i18n.py              # 국제화 (432줄)
├── install.py / install.ps1  # 설치 스크립트
├── start_crow_sse.bat        # 서버 시작
└── requirements.txt          # Python 의존성
```

## 3. 기술 스택

> 아래 표는 **v1.5 레거시** 스택입니다. v1.5.0은 Python 3.11+ 표준 라이브러리(`sqlite3`, `json`, `re`, `math`, `argparse`)만 사용하며 `pip install`이 필요 없습니다.

| 계층 | 기술 | 버전 |
|------|------|------|
| 언어 | Python | 3.10+ |
| 수치 연산 | NumPy | >=1.25.0 |
| 딥러닝 | PyTorch | >=2.0.0 |
| 직렬화 | safetensors | >=0.4.0 |
| 임베딩 | sentence-transformers | >=2.7.0 |
| 벡터 검색 | faiss-cpu | >=1.7.4 |
| 프로토콜 | mcp | ==2.1.1 (MCPServer high-level API) |
| 웹 서버 | uvicorn | >=0.29.0 |

## 4. 진입점

| 파일 | 역할 |
|------|------|
| crow_mcp_server.py | 메인 서버 진입점 |
| start_crow_sse.bat | Windows SSE 서버 시작 |
| install.py / install.ps1 | 설치 진입점 |
| scripts/final_verify.py | 8단계 검증 |
| backup_manager.py | CLI 백업 관리 |

## 5. 아키텍처

> 아래 다이어그램은 **v1.5 레거시**(상주 MCP 서버) 구조입니다. v1.5.0 구조는 `CROW_MEMORY_ARCHITECTURE.md`의 "v1.5.0 Serverless Architecture" 장을 참조하세요.

```
AI Coding Agent (MCP Client)
        |
        | MCP Protocol (stdio/SSE/HTTP)
        |
crow_mcp_server.py (MCP Server)
        |
        | 3개 도구 + 2개 프롬프트
        |
crow_core.py (Core Engine: CrowMemory Class) + crow_sanitize.py (입력 정화)
        |
        | 8개 레지스터 (style/bug/arch/context/life_*)
        |
crow_i18n.py (96개 언어 번역)
        |
        v
memory/ (영속 저장소: crow.bin + value_bank.json + recall_stats.json + system_prompt.md)
```

### 5.1 Windows 자동 시작 (v1.5 레거시, v2에서는 불필요)

Windows 로그온 시 Crow Memory MCP 서버가 자동으로 시작됩니다. 두 가지 등록 경로가 존재하며, 현재 실제 활성 경로는 **Startup 폴더**입니다.

```
Windows 로그온
    │
    ├─ [활성] Startup 폴더
    │  %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Crow_Memory_SSE.bat
    │  → start_crow_sse.bat 호출 (venv Python 우선 로직 포함)
    │
    ├─ [비활성] Task Scheduler: CrowMemoryAuto
    │  ※ 2026-08-30 세션에서 등록 시도 → 액세스 거부 (Access Denied)
    │  → Startup 폴더 폴백이 실질적 자동 시작 경로
    │
    ▼
start_crow_sse.bat
    │  Phase 0: venv Python 우선 탐지 (PYTHON_EXE 로직)
    │  Phase 1: 중복 실행 방지 (netstat port 9020/9021)
    │  Phase 2: 스테일 lock/ready 정리
    │  Phase 3: Python 서버 시작 (detached, hidden window)
    │  Phase 4: Health Check (최대 12회, exponential backoff)
    │
    ▼
crow_mcp_server.py (port 9020 + 9021)
    │  mcp.sse_app() + mcp.streamable_http_app()
    │  → asyncio.gather로 동시 실행
    │
    ▼
MCP 클라이언트 연결
    │  Zoo/Roo Code → SSE (port 9020)
    │  Kimi Code → HTTP (port 9021/mcp)
    │  글로벌 MCP 등록: Zoo Code mcp_settings.json (crow-memory, global:true)
```

- **등록 경로 1 (활성)**: Startup 폴더 — `Crow_Memory_SSE.bat`이 로그온 시 자동 실행
- **등록 경로 2 (시도됨)**: Task Scheduler (`CrowMemoryAuto`) — `schtasks /create /sc onlogon`으로 등록 시도했으나 액세스 거부
- **venv Python 우선 로직**: `start_crow_sse.bat` 내 `PYTHON_EXE` 변수로 `.venv/Scripts/python.exe` 탐지 후 없으면 시스템 Python 폴백
- **글로벌 MCP 등록**: Zoo Code의 `mcp_settings.json`에 `crow-memory` 서버 등록 (global: true)

### 데이터 흐름
1. 세션 시작 → crow_recall → [User Bias] 블록 생성
2. 작업 수행 → 바이어스 반영 응답
3. 피드백 수집 → 빌드 결과/사용자 피드백
4. 경험 저장 → crow_ingest → Hebbian EMA 업데이트
5. 진화 → crow_admin(action="evolve") → 모델 제안은 `[Unreviewed Model Suggestions]`에 적재 → 사람이 `admin prompt approve`로 승인해야 `system_prompt.md` 규칙으로 승격

## 6. 핵심 모듈

### core/crow_db.py — v1.5.0 엔진 (현재)
- SQLite WAL + FTS5. 8개 레지스터, 부호 있는 `polarity_net`, 반감기 실효 중요도, 유예 보호(1시간) + 레지스터 쿼터(15), 시맨틱 업서트(토큰 코사인 0.90), 2단 바이어스 블록
- API: `recall()`, `ingest()`, `bias_block()`, `admin()`(diagnostics / drift / prompt / backup / evolve / project_info / delete / purge), `rebuild_from_bank()`, `stats()`
- 점수: `0.5×토큰 코사인 + 0.5×BM25` → 반감기 감쇠 → 중요도(최대 ×1.15) → 프로젝트 보정, `SIM_CUTOFF` 0.35
- 프롬프트: append는 정화·단일행·400자 제한 후 `[Unreviewed Model Suggestions]`에 적재하고, `prompt approve`로만 승격

### core/crow_cli.py — CLI + 훅 어댑터 (현재)
- `hook session-start|pre-invocation|post-tool` (`--format agy|claude|kimi|cursor|text`), `recall`, `ingest`, `admin`, `migrate`, `serve-stdio`
- 훅은 항상 exit 0이며 빈 stdin/깨진 JSON을 견딤

### core/crow_mcp_stdio.py — 선택형 stdio MCP (현재)
- stdlib JSON-RPC 2.0 (프로토콜 `2025-03-26`), 도구 3개(`crow_recall`/`crow_ingest`/`crow_admin`) + 프롬프트 2개, 데몬·포트 없음

### core/migrate_from_v1.py — v1.5 이관 (현재)
- `value_bank.json` → `crow.db`, `system_prompt.md` 바이트 단위 복사(기존 파일은 `--force-prompt` 전까지 보존)
- 모듈 CLI는 `--dry-run`/`--apply` 중 하나가 필수

### crow_core.py — CrowMemory Class (v1.5 레거시)
- 8개 레지스터: style(4096x4096), bug(2048x2048), arch(2048x2048), context(2048x4096), life_pref(4096x4096), life_avoid(2048x2048), life_phil(2048x2048), life_context(2048x4096)
- 핵심 메서드: encode(), recall(), recall_multi(), ingest(), evolve_propose(), check_drift(), recover_from_drift(), for_project(), get_user_bias_block()
- 업데이트: Hebbian EMA S = λ*S + (1-λ)*polarity*k*v^T
- 정규화: 1000회마다 SVD 스펙트럴 클리핑
- 회상 정밀도 (v1.5.0-mcp): SIM_CUTOFF 0.35 (env CROW_SIM_CUTOFF/CROW_SIM_CUTOFF_CROSS_PROJECT/CROW_PROJECT_BOOST), importance 부스트 ×1.15 cap, 백도어 제거, 프로젝트 태깅 부스트, NEG_DAMPEN_BY_REGISTER (bug/life_avoid=1.0, 기본 0.6)
- ingest 스크럽 게이트: crow_sanitize.py로 정화 후 빈 텍스트면 rejected (empty_after_sanitize)
- encode 캐시 키: sha256 (구 200자 prefix 충돌 해소)

### crow_sanitize.py — 입력 정화 (v1.5.0-mcp 신규)
- scrub_text() / scrub_display() / project_slug()
- kaomoji·emoji·jamo-run 정화, C++ 코드/URL/식별자/한글 보호

### crow_mcp_server.py — MCP Server (SDK 2.1.1, v1.5.0-mcp)
- 3개 MCP 도구 (AD-5 통합, `@mcp.tool()` 타입힌트 자동 스키마): crow_recall (format="bias_block"으로 get_user_bias 흡수), crow_ingest (exit_code로 build-result 흡수, polarity 선택적), crow_admin (diagnostics/drift/prompt/backup/evolve/project_info 6-action dispatch)
- 2개 MCP 프롬프트 (`@mcp.prompt()`): crow_memory_bias, crow_evolved_rules
- 3개 REST 라우트 (`@mcp.custom_route()`): GET /health, POST /ingest, GET /recall (project/strict_project 파라미터 지원)
- 4개 전송 모드: stdio, SSE(port 9020), Streamable HTTP(port 9021, path `/mcp`), dual(기본값)
- dual 모드: `mcp.sse_app()` + `mcp.streamable_http_app()` → uvicorn 2개 `asyncio.gather`
- resolve_state_path(): CROW_STATE_TAG 지원 (현재 미사용 — 활성 state는 memory/crow.bin)

### crow_i18n.py (432줄) — 국제화
- 96개 언어 지원
- 주요 함수: detect_locale(), get_text(), get_tool_definitions(), get_installer_messages()
- 번역 JSON 구조: _meta, server, tools, installer

## 7. 데이터 저장소

| 파일 | 포맷 | 크기 | 설명 |
|------|------|------|------|
| memory/crow.bin | safetensors | ~140MB 고정 | 8개 가중치 행렬 + 프로젝션 |
| memory/value_bank.json | JSON | 428 항목 (최대 500개) | 중요도 기반 우선순위 큐, 항목별 project 필드 (null=global) |
| memory/recall_stats.json | JSON | 레지스터당 1000개 | TTL: 30일 하드, 7일 소프트 |
| memory/crow-myk1yt.bin 외 -myk1yt.* | safetensors/JSON | — | 역사 아카이브 (서버가 읽지 않음) |
| memory/system_prompt.md | Markdown | 가변 | HITL 승인 규칙 |

## 8. 알려진 이슈

### 크리티컬
1. 파일 잠금의 플랫폼 의존성 (crow_core.py:38-90) — portalocker 도입 검토
2. SVD O(n³) 복잡도 (crow_core.py:347-361) — Randomized SVD 검토
3. FAISS 인덱스 무효화 패턴 (crow_core.py:428-456) — 증분 인덱스 검토
4. ~~Startup 폴더 경쟁 상태~~ ✅ **v1.5.0-mcp에서 해결** — Windows Task Scheduler(AtLogon)로 마이그레이션하여 VS Code보다 먼저 서버 시작 보장

### 중간
5. ~~임베딩 캐시 충돌 가능성 (truncated[:200] 키)~~ ✅ **v1.5.0-mcp에서 해결** — sha256 캐시 키
6. 원자적이지 않은 3파일 순차 저장
7. Windows cp949 인코딩 이슈

## 9. 개발 환경 설정

### 9.1 v1.5.0 (현재, 저장소 루트에서 실행)

```bash
# 설치 (표준 라이브러리만 사용, pip install 불필요)
python scripts/install_plugin.py --tools generic

# 검증 (임시 홈을 지정하면 실제 메모리를 건드리지 않습니다)
export CROW_HOME="$HOME/.crow-memory-smoke"
python core/crow_cli.py ingest --key "smoke" --value "v1.5.0 cli works" --register arch --polarity 1.0
python core/crow_cli.py recall --query "smoke" --domain code --top-k 1
python core/crow_cli.py admin --action diagnostics
echo '{"invocationNum":1,"lastUserInput":"hello"}' | python core/crow_cli.py hook pre-invocation --format text
```

### 9.2 v1.5 레거시

```bash
pip install -r requirements.txt
python -c "from crow_core import CrowMemory; CrowMemory()"
python crow_mcp_server.py --transport dual

# 유지보수 스크립트 (dry-run 기본, --apply로 실제 적용)
python scripts/migrate_value_bank.py        # 레거시 value_bank 정화
python scripts/merge_value_bank.py          # value_bank 병합
python scripts/purge_search_debris.py       # 검색 로그 잔해 제거

# 테스트 (231개, v1.5 엔진 대상)
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 10. 관련 문서

| 문서 | 위치 |
|------|------|
| 상세 아키텍처 | CROW_MEMORY_ARCHITECTURE.md |
| 에이전트 통합 | AGENTS.md |
| 버전 히스토리 | CHANGELOG.md |
| 프로젝트 개요 | README.md |
| 라이선스 | LICENSE |

---

> 이 문서는 docs/PROJECT_CONTEXT.md에 위치하며, 프로젝트 구조 변경 시 함께 갱신되어야 합니다.
