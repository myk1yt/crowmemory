# 🧠 Crow Memory — 프로젝트 컨텍스트 문서

> **버전:** v1.5.1 | **라이선스:** MIT | **저장소:** [myk1yt/crowmemory](https://github.com/myk1yt/crowmemory)
> **최종 갱신:** 2026-06-21 | **문서 목적:** 인간 및 AI를 위한 온보딩 가이드

## 1. 프로젝트 정체성

**Crow Memory**는 LLM 기반 AI 코딩 어시스턴트를 위한 **외부 시냅틱 메모리 시스템**입니다. MCP(Model Context Protocol) 서버로 구현되어, AI 에이전트가 세션 간에 사용자 선호도, 아키텍처 결정, 버그 패턴 등을 기억하고 회상할 수 있게 합니다.

> *"까마귀는 코드를 기억하지 않지만, 그 코드를 작성한 손을 기억한다."*

### 핵심 가치 제안
- **세션 간 기억 유지**: 코딩 스타일, 아키텍처 선호, 버그 인사이트를 영구 저장
- **MCP 표준 기반**: 모든 MCP 호환 AI 코딩 도구(Zoo Code, Kimi Code 등)와 통합
- **자가 진화**: 통계적 패턴 감지 → HITL 승인 → 시스템 프롬프트 영구 규칙화
- **36개 언어 지원**: 완전한 국제화(i18n)

## 2. 디렉토리 구조

```
Crow Memory/
├── .github/                  # GitHub 메타데이터
├── .vscode/                  # VS Code 자동화
├── .zoo/                     # Zoo Code 설정 템플릿
├── i18n/                     # 36개 언어 번역 JSON
├── Logo/                     # 로고 이미지
├── memory/                   # 메모리 저장소 (git 제외)
│   ├── crow.bin              # ~140MB 고정 크기 가중치 행렬
│   ├── value_bank.json       # 순환 버퍼 (최대 500개)
│   ├── recall_stats.json     # 회상 통계
│   └── system_prompt.md      # HITL 승인 규칙
├── scripts/                  # 검증 유틸리티
├── system_prompt.example/    # 프롬프트 템플릿
├── crow_core.py              # 핵심 엔진 (944줄)
├── crow_mcp_server.py        # MCP 서버 (823줄)
├── crow_i18n.py              # 국제화 (473줄)
├── install.py / install.ps1  # 설치 스크립트
├── start_crow_sse.bat        # 서버 시작
└── requirements.txt          # Python 의존성
```

## 3. 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| 언어 | Python | 3.10+ |
| 수치 연산 | NumPy | >=1.25.0 |
| 딥러닝 | PyTorch | >=2.0.0 |
| 직렬화 | safetensors | >=0.4.0 |
| 임베딩 | sentence-transformers | >=2.7.0 |
| 벡터 검색 | faiss-cpu | >=1.7.4 |
| 프로토콜 | mcp | >=1.0.0 |
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

```
AI Coding Agent (MCP Client)
        |
        | MCP Protocol (stdio/SSE/HTTP)
        |
crow_mcp_server.py (MCP Server)
        |
        | 10개 도구 + 2개 프롬프트
        |
crow_core.py (Core Engine: CrowMemory Class)
        |
        | 8개 레지스터 (style/bug/arch/context/life_*)
        |
crow_i18n.py (36개 언어 번역)
        |
        v
memory/ (영속 저장소: crow.bin + value_bank.json + recall_stats.json + system_prompt.md)
```

### 5.1 Windows 자동 시작 (v1.5.0+)

Windows 로그온 시 Crow Memory MCP 서버가 자동으로 시작되도록 Windows Task Scheduler에 등록됩니다.

```
Windows 로그온
    │
    ▼
Task Scheduler: CrowMemoryAuto
    │  트리거: AtLogon (30초 지연)
    │  실행: cmd /c "start_crow_sse.bat"
    │  재시작: 3분 간격, 최대 3회
    │
    ▼
start_crow_sse.bat
    │  Phase 1: 중복 실행 방지 (netstat)
    │  Phase 2: 스테일 lock/ready 정리
    │  Phase 3: Python 서버 시작 (detached)
    │  Phase 4: Health Check (최대 12회, ~55초)
    │
    ▼
crow_mcp_server.py (port 9020 + 9021)
    │
    ▼
VS Code Global MCP → 연결 성공
```

- 등록 방식: `install.ps1` 또는 `install.py` 실행 시 `schtasks.exe /create`로 자동 등록 (관리자 권한 불필요)
- 폴백: Task Scheduler 등록 실패 시 Startup 폴더에 10초 지연 래퍼 등록
- 마이그레이션: 설치 시 기존 Startup 폴더의 `Crow_Memory_SSE.bat` 자동 제거

### 데이터 흐름
1. 세션 시작 → crow_recall → [User Bias] 블록 생성
2. 작업 수행 → 바이어스 반영 응답
3. 피드백 수집 → 빌드 결과/사용자 피드백
4. 경험 저장 → crow_ingest → Hebbian EMA 업데이트
5. 진화 → crow_evolve_propose → HITL 승인 → system_prompt.md 규칙 추가

## 6. 핵심 모듈

### crow_core.py (944줄) — CrowMemory Class
- 8개 레지스터: style(4096x4096), bug(2048x2048), arch(2048x2048), context(2048x4096), life_pref(4096x4096), life_avoid(2048x2048), life_phil(2048x2048), life_context(2048x4096)
- 핵심 메서드: encode(), recall(), ingest(), evolve_propose(), check_drift(), recover_from_drift(), for_project(), get_user_bias_block()
- 업데이트: Hebbian EMA S = λ*S + (1-λ)*polarity*k*v^T
- 정규화: 1000회마다 SVD 스펙트럴 클리핑

### crow_mcp_server.py (823줄) — MCP Server
- 10개 MCP 도구: crow_recall, crow_ingest, crow_evolve_propose, crow_diagnostics, crow_check_drift, crow_ingest_from_build, crow_get_user_bias, crow_manage_prompt, crow_manage_backup, crow_project_info
- 2개 MCP 프롬프트: crow_memory_bias, crow_evolved_rules
- 4개 전송 모드: stdio, sse(port 9020), streamable-http(port 9021), dual(기본값)
- REST API (v1.4.3+): GET /health, POST /ingest, GET /recall

### crow_i18n.py (473줄) — 국제화
- 36개 언어 지원
- 주요 함수: detect_locale(), get_text(), get_tool_definitions(), get_installer_messages()
- 번역 JSON 구조: _meta, server, tools, installer

## 7. 데이터 저장소

| 파일 | 포맷 | 크기 | 설명 |
|------|------|------|------|
| memory/crow.bin | safetensors | ~140MB 고정 | 8개 가중치 행렬 + 프로젝션 |
| memory/value_bank.json | JSON | 최대 500개 | 중요도 기반 순환 버퍼 |
| memory/recall_stats.json | JSON | 레지스터당 1000개 | TTL: 30일 하드, 7일 소프트 |
| memory/system_prompt.md | Markdown | 가변 | HITL 승인 규칙 |

## 8. 알려진 이슈

### 크리티컬
1. 파일 잠금의 플랫폼 의존성 (crow_core.py:38-90) — portalocker 도입 검토
2. SVD O(n³) 복잡도 (crow_core.py:347-361) — Randomized SVD 검토
3. FAISS 인덱스 무효화 패턴 (crow_core.py:428-456) — 증분 인덱스 검토
4. ~~Startup 폴더 경쟁 상태~~ ✅ **v1.5.0에서 해결** — Windows Task Scheduler(AtLogon)로 마이그레이션하여 VS Code보다 먼저 서버 시작 보장

### 중간
5. 임베딩 캐시 충돌 가능성 (truncated[:200] 키)
6. 원자적이지 않은 3파일 순차 저장
7. Windows cp949 인코딩 이슈

## 9. 개발 환경 설정

```bash
pip install -r requirements.txt
python -c "from crow_core import CrowMemory; CrowMemory()"
python crow_mcp_server.py --transport dual
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
