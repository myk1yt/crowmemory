# Crow Memory — Project Journal

> *"Crow remembers not the code, but the hand that wrote it."*

---

## 2026-05-24 — 프로젝트 시작

### 초기화

- **프로젝트명:** Crow Memory (까마귀 메모리)
- **목표:** Zoo Code + MCP 호환 LLM에 연결되는 외부 시냅스 기억 장치 구축
- **메모리 파일명:** [`crow.bin`](memory/crow.bin) (원래 문서의 `state.bin`에서 변경)
- **아키텍처 문서:** [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md) v1.0 기준

### 아키텍처 문서 변경사항

- 문서 내 모든 `state.bin` 참조를 `crow.bin`으로 변경 완료
- 변경 위치: Executive Summary, Two-Brain Doctrine 표, Fixed-Size Immortality 섹션, Topology 다이어그램, Component Responsibilities 표, Memory Core 헤더, CrowState 코드 예제, Backup 디렉토리 구조, CLI 실행 예제, Appendix C 코드, evolve 트리거 설명, 로드맵, Appendix B Neural Density 설명

### 구현 계획 (4단계)

| Phase | 범위 | 핵심 산출물 |
|---|---|---|
| **Phase 0** | 프로토타입 | `CrowMemory` 클래스, 인코더, MCP 서버 뼈대 |
| **Phase 1** | Zoo Code 훅 | 빌드 후크 → 자동 ingest, `[User Bias]` 프롬프트 주입 |
| **Phase 2** | 피드백 루프 | 편집 거리 추적, value_bank + FAISS |
| **Phase 3** | 진화 | `evolve_propose`, HITL UI, `system_prompt.md` 연동 |
| **Phase 4** | 견고화 | 드리프트 감지, 백업, 멀티 프로젝트 격리 |

### 다음 작업

- [ ] Phase 0: [`crow_mcp_server.py`](crow_mcp_server.py) 구현 시작
- [ ] Phase 0: [`memory/`](memory/) 디렉토리 생성 및 [`crow.bin`](memory/crow.bin) 초기화

---

---

## 2026-05-24 — Phase 0 완료: 프로토타입 구현

### 작업 내용

#### 핵심 파일 생성
- **[`crow_core.py`](crow_core.py)**: CrowMemory 클래스 (591줄)
  - 4레지스터 (`style`, `bug`, `arch`, `context`) — 각각 고유 차원과 λ 감쇠율
  - EMA Hebbian 업데이트: `S_{t+1} = λS_t + (1-λ)·polarity·k·v^T`
  - 스펙트럴 클리핑 (1000회 업데이트마다 SVD, σ_max ≤ 2.0)
  - L2 정규화된 nearest-neighbor hint 검색
  - value_bank 순환 버퍼 (최대 500개, JSON 영속화)
  - recall_stats 추적 (evolve 프로토콜용, 7일간 보존)
  - 드리프트 감지 (연속 저신뢰도 감시)
  - 원자적 저장 (tmp → rename)
  - 스펙트럴 리셋 및 레지스터 아카이브 유지보수 기능

- **[`crow_mcp_server.py`](crow_mcp_server.py)**: MCP stdio 서버 (5개 도구 노출)
  - `crow_recall`: 시냅스 읽기
  - `crow_ingest`: 시냅스 쓰기
  - `crow_evolve_propose`: 프롬프트 변이 제안
  - `crow_diagnostics`: 메모리 상태 진단
  - `crow_check_drift`: 드리프트 감지

- **[`requirements.txt`](requirements.txt)**: 의존성 명세
- **[`test_crow.py`](test_crow.py)**: 6개 테스트 스위트

#### 테스트 결과 (6/6 통과)

| 테스트 | 결과 | 핵심 지표 |
|---|---|---|
| Test 1: Initialize | ✅ | 4레지스터 모두 0-노름, update_count=0 |
| Test 2: Ingest 5 experiences | ✅ | 모든 레지스터 비영점 도달, context 노름 0.0352 |
| Test 3: Recall hints | ✅ | sim=0.67~1.00, 올바른 힌트 반환 |
| Test 4: Evolve proposal | ✅ | HITL 승인 필요 플래그 정상 |
| Test 5: Drift detection | ✅ | 정상 상태에서 오탐 없음 |
| Test 6: Persistence round-trip | ✅ | 재로딩 후 update_count·value_bank 보존 |

#### Recall 품질 예시
- `"Fix memory leak in React PDF worker"` → `[bug] Always use explicit cleanup in useEffect... (sim=0.67)` ✓
- `"Design a binary format reader"` → `[arch] Always validate magic bytes in first 8 bytes... (sim=0.71)` ✓
- `"What is the user currently working on?"` → `[context] User is building a book viewer application... (sim=1.00)` ✓

### 결정 사항

1. **`crow.bin` 파일명**: `state.bin` 대신 `crow.bin` 사용 (사용자 요청)
2. **`lambda_map` 분리**: safetensors가 `object` dtype을 지원하지 않아, λ 값은 코드 상수(`REGISTERS`)에서 관리
3. **MCP SDK**: `mcp` 1.27.1 사용 — API가 아키텍처 문서의 예상과 달라 `@server.call_tool()` 데코레이터 패턴으로 적용
4. **인코더**: `nomic-ai/nomic-embed-text-v1.5` / `nomic-bert-2048` — 최초 로딩 시 자동 다운로드, 이후 캐시 사용
5. **recalled vector 정규화**: EMA의 (1-λ) 스케일링으로 인해 recalled vector의 크기가 매우 작아질 수 있어, nearest-neighbor 검색 전 L2 정규화 추가

### 다음 단계

- [x] Phase 0 프로토타입 완료
- [x] 실제 `crow.bin` 초기화 및 Zoo Code MCP 연결 설정
- [x] Phase 1-4 통합 구현

---

## 2026-05-24 — Phase 1-4 통합 구현 완료

### 작업 내용

#### Phase 1: 빌드 후크 + User Bias 주입
- [`crow_core.py`](crow_core.py) `ingest_from_build()`: 빌드 종료 코드와 사용자 편집 여부로 polarity 자동 결정
  - Build success + accept → +1.5
  - Build success + edit → +0.5
  - Build fail + rewrite → -1.0 → -0.6 (dampened)
  - Explicit override: +2.0 / -2.0
- [`crow_core.py`](crow_core.py) `get_user_bias_block()`: 모든 레지스터 쿼리 → `[User Bias]` 블록 생성
- [`crow_mcp_server.py`](crow_mcp_server.py) `crow_ingest_from_build`, `crow_get_user_bias` 도구 추가

#### Phase 2: FAISS 가속 + value_bank 강화
- [`crow_core.py`](crow_core.py) `build_faiss_index()` / `build_all_faiss_indexes()`: FAISS IndexFlatIP 구축
- [`crow_core.py`](crow_core.py) `_faiss_search()`: FAISS 우선, numpy 폴백 검색
- FAISS 미설치 시 자동으로 numpy 브루트포스 검색으로 전환

#### Phase 3: 시스템 프롬프트 진화 + HITL 패널
- [`memory/system_prompt.md`](memory/system_prompt.md): 진화된 규칙 저장소
- [`crow_core.py`](crow_core.py) `get_system_prompt()` / `append_system_prompt()` / `prompt_stats()`: 프롬프트 관리
  - 규칙 추가 시 자동 백업
  - HTML 주석에 채택 타임스탬프 기록
- [`hitl_panel.html`](hitl_panel.html): HITL 승인 웹 UI
  - Zoo Code 웹뷰에서 `postMessage`로 통신
  - 승인/거절/편집 기능
  - 신뢰도 시각화 바
- [`crow_mcp_server.py`](crow_mcp_server.py) `crow_manage_prompt` 도구 추가

#### Phase 4: 백업 + 드리프트 복구 + 멀티 프로젝트
- [`backup_manager.py`](backup_manager.py): CLI 백업 관리 유틸리티 (create/rotate/list/recover)
- [`crow_core.py`](crow_core.py) `create_backup()` / `rotate_backups()` / `list_backups()`: 백업 순환
- [`crow_core.py`](crow_core.py) `recover_from_drift()`: 드리프트 자동 복구
  - 모든 레지스터 스펙트럴 리셋
  - 오래된 recall_stats 정리
  - 30일 이상 된 value_bank 항목 제거
- [`crow_core.py`](crow_core.py) `for_project()` / `list_projects()`: 프로젝트별 메모리 격리
- Windows `PermissionError` 대응: `_persist()` 재시도 + fallback 메커니즘

#### 통합 테스트 결과

| Phase | 테스트 | 결과 |
|---|---|---|
| Phase 0 | Core engine (6 tests) | ✅ 6/6 |
| Phase 1 | Build hook (6 tests) | ✅ 6/6 |
| Phase 2 | FAISS (2 tests) | ✅ 2/2 |
| Phase 3 | Prompt evolution (6 tests) | ✅ 6/6 |
| Phase 4 | Backup (4 tests) | ✅ 4/4 |
| Phase 4 | Drift (2 tests) | ✅ 2/2 |
| Phase 4 | Multi-project (4 tests) | ✅ 4/4 |
| MCP | Configuration (7 tests) | ✅ 7/7 |
| **총계** | **37 tests** | **✅ 37/37** |

### 결정 사항

1. **Windows `os.replace` 문제**: 파일 락으로 인한 `PermissionError` 발생. 3회 재시도 + `shutil.copy2` fallback 적용
2. **FAISS 선택적 사용**: `faiss-cpu` 설치 시 자동 가속, 미설치 시 numpy 폴백 (Zero-dependency fallback)
3. **프로젝트 격리 방식**: `memory/project_{name}/crow.bin` 하위 디렉토리 구조
4. **HITL 패널**: Zoo Code `postMessage` API와 연동되는 독립 HTML 파일로 구현

### 현재 파일 구조

```
crowsmemory/
├── CROW_MEMORY_ARCHITECTURE.md  # 설계 문서 (v1.0, 수정됨)
├── journal.md                    # 프로젝트 기록
├── requirements.txt              # Python 의존성
├── crow_core.py                  # 핵심 엔진 (~650줄)
├── crow_mcp_server.py            # MCP stdio 서버 (10개 도구)
├── backup_manager.py             # CLI 백업 관리자
├── test_crow.py                  # Phase 0 단위 테스트
├── test_integration.py           # 통합 테스트 (37개)
├── hitl_panel.html               # HITL 승인 웹 UI
├── mcp_config.json               # Zoo Code MCP 연결 설정
└── memory/
    ├── crow.bin                  # 활성 메모리 (초기화 완료)
    ├── value_bank.json           # 경험 순환 버퍼
    ├── recall_stats.json         # 리콜 통계
    └── system_prompt.md          # 진화된 프롬프트 규칙
```

### Zoo Code MCP 연결 방법

[`mcp_config.json`](mcp_config.json)을 Zoo Code의 MCP 설정에 추가:

```json
{
  "mcpServers": {
    "crow_memory": {
      "command": "python",
      "args": ["crow_mcp_server.py", "--state", "./memory/crow.bin"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

연결 후 사용 가능한 10개 MCP 도구:
1. `crow_recall` — 기억 읽기
2. `crow_ingest` — 기억 쓰기
3. `crow_evolve_propose` — 프롬프트 변이 제안
4. `crow_diagnostics` — 상태 진단
5. `crow_check_drift` — 드리프트 감지
6. `crow_ingest_from_build` — 빌드 결과 자동 평가
7. `crow_get_user_bias` — `[User Bias]` 블록 생성
8. `crow_manage_prompt` — 시스템 프롬프트 관리
9. `crow_manage_backup` — 백업 관리
10. `crow_project_info` — 프로젝트 격리 관리

### 다음 단계

- [x] 모든 Phase 구현 완료
- [x] MCP 서버 Zoo Code 연결 설정 완료
- [x] 통합 테스트 37/37 통과
- [x] Zoo Code에서 실제 MCP 연결 및 라이브 테스트

---

## 2026-05-25 — 문서 범용화 (DeepSeek 참조 제거)

### 작업 내용

- **[`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md)**: 문서 전체에서 특정 LLM 모델명("DeepSeek V4 Pro", "DeepSeek V4", "V4")을 범용 표현("LLM", "the LLM agent", "the agent")으로 교체 (총 15곳)
  - Executive Summary, Two-Brain Doctrine, Prompt Evolution, Topology 다이어그램, Component Responsibilities, Protocol Alpha/Beta/Gamma, MCP Tool Schema, Agent Loop, Boundedness, Roadmap
  - 버전 1.0 → 1.1, 날짜 갱신
- **[`journal.md`](journal.md)**: "DeepSeek V4 Pro에 연결되는" → "MCP 호환 LLM에 연결되는"으로 변경
- **[`crow_core.py`](crow_core.py)**: docstring 수정 (4-register → 8-register)
- **[`CHANGELOG.md`](CHANGELOG.md)**: v1.1.1 항목 추가

### 결정 사항

- Crow Memory는 특정 LLM 제공자에 종속되지 않는 범용 시스템임을 명확히 함
- README.md의 "Claude, GPT, DeepSeek, Gemini, etc." 표현은 이미 범용적이므로 유지
- 아키텍처 문서 내 모델명을 "the LLM" / "the agent"로 통일

### 다음 단계

- [x] GitHub 업로드 (v1.1.1)

---

## 2026-05-25 — v1.2.0: 코드 리뷰 기반 전면 개선

### 작업 내용

#### 1순위 — 데이터 무결성
- **파일 잠금**: `crow.bin.lock` + PID 체크 방식의 어드바이저리 락 추가. 동시 프로세스 접근 시 경고 후 거부.
- **손상 복구**: `crow.bin` `ValueError` 발생 시 가장 최근 `.bak.*` 백업에서 자동 복구 시도. 백업 없으면 명시적 `RuntimeError`.
- **`start_crow_sse.bat` 버그 수정**: `install.py`/`install.ps1`이 절대경로를 하드코딩한 배치 파일을 동적 생성하도록 변경.

#### 2순위 — 문서 동기화
- **`CROW_MEMORY_ARCHITECTURE.md`**: 8레지스터(코드4+라이프4) 전체 반영 — Physical Spec, Register Table, Tool Schema enum, Appendix C 코드. 버전 1.1→1.2.
- **`CrowMemory` 클래스 docstring**: "4 semantic registers" → "8 semantic registers".

#### 3순위 — 성능
- **인코더 프리웜**: `CrowMemory.prewarm_encoder()` — 백그라운드 스레드로 SentenceTransformer 사전 로딩.
- **임베딩 LRU 캐시**: `encode()`에 1024엔트리 캐시 추가.

#### 4순위 — 안정성
- **SVD 클리핑 폴백**: `LinAlgError` 발생 시 요소별 노름 클리핑으로 대체.
- **`hash()` → `hashlib.md5()`**: `_track_recall()`의 쿼리 해시를 이식 가능하게 변경.
- **`check_drift()` 파라미터명**: `consecutive_calls` → `min_low_confidence_count`.

#### 5순위 — 설치 경험
- **`install.ps1`**: 단계 번호 `[1/5]`~`[5/5]`로 통일.
- **`custom_modes.yaml` 병합**: 기존 사용자 모드 보존.
- **`patch_kimi_code.py`**: 신규 설치 append 모드 + `ORIGINAL_CROW_MARKER` dead code 제거.

#### 6순위 — 문서화
- **`crow_mcp_server.py`**: docstring "9 tools" → "10 tools", `prewarm_encoder()` 호출 추가.
- **`CHANGELOG.md`**: v1.2.0 항목 추가.

### 결정 사항

- 파일 잠금은 플랫폼 독립적 lockfile+PID 방식 채택 (Windows `OpenProcess`, Unix `os.kill`).
- `_persist()` 증분 저장은 복잡도 대비 이득이 적어 이번 릴리스에서는 보류.
- FAISS 인덱스 백그라운드 재구축도 numpy 폴백이 있으므로 보류.

### 다음 단계

- [x] GitHub 업로드 (v1.2.0)

---

## 2026-05-25 — v1.2.1: 교차 검증 기반 잔여 문제 해결

### 작업 내용

#### 치명적 수정
- **락 획득 실패 시 예외 발생**: `_acquire_file_lock()`이 `False` 반환 시 `RuntimeError`로 진행 차단.
- **`requirements.txt`**: 누락된 `uvicorn`(SSE 필수)과 `PyYAML`(install.py custom_modes merge) 추가.

#### 캐시 개선
- **진짜 LRU 캐시**: `_encode_cache`를 클래스 변수(dict, FIFO) → 인스턴스 변수(`OrderedDict`, `move_to_end()`)로 변경.
- **인코딩 입력 제한**: `text[:2000]` truncate로 긴 입력의 메모리 부담 완화.

#### 성능 최적화
- **`_track_recall()` 지연 pruning**: 7일 TTL 정리 + JSON 저장을 1시간에 한 번만 수행.
- **레지스터당 최대 1000엔트리 제한**: stats 무한 성장 방지.

#### 잔여 버그
- **`spectral_reset()` SVD 폴백**: `_maybe_clip`과 동일하게 요소별 노름 클리핑 적용.

#### 문서 동기화
- **아키텍처 문서 §2.2**: "4 weight matrices" → "8 weight matrices"
- **아키텍처 문서 §7.2**: "5 consecutive calls" → 실제 `min_low_confidence_count` 동작 설명
- **README Single-Client Setup**: SSE 모드가 기본임을 명시

### 결정 사항

- `check_drift` 증분 카운트, `_persist` 비동기화, FAISS 백그라운드 재구축은 복잡도 대비 이득이 적어 v1.3+로 보류.
- `build_faiss_index` 예외 처리는 이미 `except ImportError`로 감싸져 있어 추가 수정 불필요.

### 다음 단계

- [x] GitHub 업로드 (v1.2.1)

---

## 2026-05-25 — v1.3.0: Kimi Code AGENTS.md 공식 지원 + 크로스 에디터 통합

### 작업 내용

#### Kimi Code 아키텍처 전환
- **`AGENTS.md` → 공식 Kimi Code CLI 메커니즘**: `patch_kimi_code.py`로 `system.md`를 해킹하던 방식에서, Kimi Code CLI가 `${KIMI_AGENTS_MD}`로 자동 주입하는 `AGENTS.md` 방식으로 전환. 업데이트 내구성 확보.
- **`~/.kimi/mcp.json` 생성**: Kimi Code CLI 표준 MCP 설정 위치에 Crow SSE 엔드포인트 등록. 프로젝트 무관하게 항상 연결됨.
- **`custom_modes.yaml` Kimi Code 경로 제거**: Kimi Code CLI는 `custom_modes.yaml`을 지원하지 않음이 확인됨. Zoo Code 전용.
- **`patch_kimi_code.py` → optional fallback**: AGENTS.md가 1차 메커니즘, patch는 구버전 CLI용 fallback으로 유지.

#### 설치 스크립트 업데이트
- `install.py` / `install.ps1` Step 4.5: AGENTS.md + ~/.kimi/mcp.json 생성
- Step total: 6 → 7

#### 문서 최신화
- README: 4-layer auto-activation 표 (Zoo Code / Kimi Code 구분)
- CHANGELOG: v1.3.0 항목
- CROW_MEMORY_ARCHITECTURE: AGENTS.md 레이어 추가

### 결과
- `git clone` → `install` → VS Code 열기 → **Zoo Code + Kimi Code 양쪽 즉시 Crow 사용 가능**
- Kimi Code: AGENTS.md 자동 주입 + ~/.kimi/mcp.json SSE 연결
- Zoo Code: custom_modes.yaml + .roo/mcp.json SSE 연결
- 양쪽 모두 하나의 crow.bin 공유

---

## 2026-05-25 — SSE 자동 시작 인프라 구축 및 GitHub 편의성 강화

### 작업 내용

#### 근본 문제 진단
- **SSE 서버가 VS Code 재시작 시 자동으로 켜지지 않는 문제**: `install.py`/`install.ps1`의 자동 시작 메커니즘이 Windows Startup 폴더에만 의존하고 있었음. Startup은 Windows 부팅 시에만 트리거되므로, VS Code를 껐다 켜는 일반적인 워크플로우에서는 SSE 서버가 시작되지 않았음.
- **`mcp_config.json`이 stdio에서 SSE로 변경된 후 연결 두절**: config는 SSE인데 서버는 죽어있는 상태.

#### 핵심 수정
- **`.vscode/tasks.json` 생성**: `runOn: folderOpen` 태스크로 워크스페이스 열 때 [`start_crow_sse.bat`](start_crow_sse.bat) 자동 실행. Zoo Code, Kimi Code 모든 VS Code 기반 에디터에서 동작.
- **`start_crow_sse.bat` 전면 개선**:
  - 포트 9020 중복 실행 감지 (이미 실행 중이면 건너뜀)
  - Stale lock 파일 자동 정리 (PID 생존 확인 후 삭제)
  - 시작 후 3초 대기 → 포트 리스닝 검증
- **`install.py` / `install.ps1` 업데이트**:
  - Step 3.5 추가: `.vscode/tasks.json` 자동 생성
  - Step 3 확장: `.roo/mcp.json` + `mcp_config.json` 둘 다 생성 (크로스 에디터 지원)
  - Step 5: robust bat 생성 + Startup 폴더에 복사 (단일 소스)
  - Step total: 5 → 6

#### GitHub 편의성 강화
- **`.gitignore` 수정**: `.vscode/tasks.json`과 `.roo/mcp.json`을 공유하도록 변경. 클론 후 별도 설정 없이 즉시 SSE 서버 자동 시작.
- **`README.md` 전면 개편**: SSE-first 아키텍처로 문서 재작성, Multi-Client 다이어그램 추가, Troubleshooting에 SSE 관련 항목 추가.
- **`CHANGELOG.md`**: [Unreleased] 항목 추가.
- **`CROW_MEMORY_ARCHITECTURE.md`**: 토폴로지 다이어그램 SSE 반영, Component 표 업데이트.

### 결과
- `git clone` → `install.ps1` → VS Code 열기 → **즉시 Crow 사용 가능**
- Kimi Code + Zoo Code 양쪽에서 하나의 `crow.bin` 공유 (SSE 서버가 직렬화)
- Stale lock, 중복 실행, 포트 충돌 등 엣지 케이스 자동 처리

### 결정 사항
- SSE 모드를 유일한 기본값으로 확정. stdio는 단일 클라이언트 고급 사용자용 옵션으로만 유지.
- `.vscode/tasks.json`을 Git에 포함시키기로 결정 (제로컨피그 철학).
- Startup `.bat`은 `start_crow_sse.bat`의 복사본으로 통일 (코드 중복 제거).

---

## 기록 템플릿

```markdown
## YYYY-MM-DD — 제목

### 작업 내용
- 항목 1
- 항목 2

### 결정 사항
- 결정 1 (이유)

### 다음 단계
- [ ] 할 일 1
- [ ] 할 일 2
```
