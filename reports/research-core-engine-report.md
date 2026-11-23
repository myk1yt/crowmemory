# Crow Memory 심층 아키텍처 평가 및 개선 보고서

> **대상 워크스페이스**: `D:\OneDrive\Projects\Crow Memory` (v1.5.0)  
> **조사 방법론**: 전체 코어/서버/유틸리티/테스트 코드 정밀 분석 + 실운영 상태(`memory/crow.bin`, `memory/value_bank.json`, `memory/recall_stats.json`) 수치 실측  
> **목적**: LLM 코딩 어시스턴트의 실전 운용 관점에서 Crow Memory의 구조 매핑, 잘된 설계 3가지, 실전 부족점 3가지, 그리고 즉시 구현 가능한 개선안 3가지 제시

---

## 1. Crow Memory 전체 아키텍처 매핑

### 1.1 프로젝트 토폴로지 및 모듈 역할

| 모듈 / 파일 | 역할 | 핵심 심볼 & 라인 |
|---|---|---|
| [`crow_core.py`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py) | 핵심 시냅스 메모리 엔진 (`CrowMemory`, 1,117줄) | `REGISTERS` (`#L120-L131`), `DOMAINS` (`#L134-L139`), `encode` (`#L247-L266`), `recall` (`#L281-L314`), `recall_multi` (`#L316-L399`), `_accept` (`#L405-L432`), `_nearest_hints` (`#L434-L468`), `ingest` (`#L474-L515`), `_maybe_clip` (`#L517-L531`), `evolve_propose` (`#L537-L574`), `_append_value_bank` (`#L580-L631`), `_track_recall` (`#L663-L721`), `check_drift` (`#L742-L758`), `recover_from_drift` (`#L1023-L1066`) |
| [`crow_mcp_server.py`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py) | MCP Python SDK 2.1.1 서버 (689줄) | `resolve_state_path` (`#L71-L84`), `_recall`/`_ingest`/`_admin` (`#L91-L238`), `create_server` (`#L252-L531`: 3 Tools, 2 Prompts, 3 REST Routes), `_run_dual_port` (`#L590-L608`) |
| [`crow_sanitize.py`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_sanitize.py) | stdlib 전용 보수적 입력 정화기 및 프로젝트 슬러그 (132줄) | `scrub_text` (`#L84-L103`), `scrub_display` (`#L116`), `project_slug` (`#L119-L132`) |
| [`crow_i18n.py`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_i18n.py) | 36개 언어 지역화 및 MCP 스키마 미러 (424줄) | `SUPPORTED_LOCALES` (`#L32-L37`), `_BASE_TOOL_DEFINITIONS` (`#L43-L150`) |
| [`backup_manager.py`](file:///D:/OneDrive/Projects/Crow%20Memory/backup_manager.py) | 백업 생성/로테이션/복구 CLI (87줄) | `cmd_create`, `cmd_rotate`, `cmd_list`, `cmd_recover` (`#L20-L54`) |
| [`start_crow_sse.bat`](file:///D:/OneDrive/Projects/Crow%20Memory/start_crow_sse.bat) | Windows 백그라운드 데몬 런처 + `/health` 폴링 (126줄) | Dual-mode 실행 (`#L74`), Health check (`#L88`) |
| [`scripts/`](file:///D:/OneDrive/Projects/Crow%20Memory/scripts/migrate_value_bank.py) | 오프라인 유지보수 스크립트 (`migrate_value_bank.py`, `merge_value_bank.py`, `purge_search_debris.py`) | dry-run 기본, `--apply` 시 백업 후 원자적 저장 |
| [`tests/`](file:///D:/OneDrive/Projects/Crow%20Memory/tests/test_recall_precision.py) | 6개 스위트 231개 단위 테스트 (`FakeEncoder` 기반) | `test_recall_precision.py`, `test_tool_schema.py`, `test_sanitize.py`, `test_merge.py`, `test_migrate.py`, `test_purge_debris.py` |

### 1.2 핵심 수학 및 데이터 흐름

```
[LLM Query]
   │
   ▼ crow_recall(query, register="all", domain="all", top_k=2, project, strict_project)
[encode(query[:2000])]  ──▶ SHA-256 LRU Cache (max 1024)
   │                        nomic-embed-text-v1.5 (768d) -> proj_W @ vec + proj_b (4096d, L2-norm, float16)
   ▼
[Register Projection]   ──▶ r = S_f32.T @ q_f32[:key_dim]
   │                        confidence = min(||r||_2 / (||S||_F + 1e-8), 1.0)
   ▼
[_nearest_hints()]      ──▶ _faiss_search(r, register, top_k)  [현재 런타임에선 NumPy scan 폴백]
   │                        _accept(): sim >= SIM_CUTOFF(0.35), strict_project 필터,
   │                                   cross-project cutoff(0.42),
   │                                   boost = min(1 + 0.12*ln(imp+1), 1.15) (*1.05 if same project, cap 1.15)
   ▼
[recall_multi()]        ──▶ 전 레지스터 후보를 eff_sim 내림차순 병합 -> [:top_k] 슬라이스
                            scrub_display(text)[:200] 반환 + _track_recall() 기록
```

1. **8개 레지스터 구조** ([`crow_core.py#L120-L139`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L120-L139)):
   - `code` 도메인: `style` `(4096×4096, λ=0.9999)`, `bug` `(2048×2048, λ=0.9995)`, `arch` `(2048×2048, λ=0.9995)`, `context` `(2048×4096, λ=0.9500)`
   - `life` 도메인: `life_pref` `(4096×4096, λ=0.9999)`, `life_avoid` `(2048×2048, λ=0.9995)`, `life_phil` `(2048×2048, λ=0.9995)`, `life_context` `(2048×4096, λ=0.9500)`
2. **Hebbian EMA 학습 규칙** ([`crow_core.py#L487-L505`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L487-L505)):
   - `polarity`를 `[-2.0, 2.0]`로 클리핑 후 음수면 `NEG_DAMPEN_BY_REGISTER` 적용(`bug`/`life_avoid` = `1.0`, 그 외 `0.6`).
   - $S \leftarrow \lambda S + \text{float16}\big((1 - \lambda) \cdot \text{polarity} \cdot k[:d_k] v[:d_v]^T\big)$
   - `update_count % 1000 == 0`마다 SVD 특이값 클리핑(`[-2.0, 2.0]`, [`_maybe_clip`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L517-L531)).
3. **보조 텍스트 저장소 (`value_bank.json`, 최대 500개)** ([`crow_core.py#L580-L631`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L580-L631)):
   - `(register, key[:500])` 일치 시 재적재로 간주하여 `importance += abs(polarity)`, `ingest_count += 1` 누적.
   - 500개 초과 시 `min(importance)` 항목을 축출.
4. **기억 통계 및 프롬프트 진화 (`recall_stats.json`, `evolve_propose`)** ([`crow_core.py#L537-L574`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L537-L574), [`#L663-L721`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L663-L721)):
   - `md5(query)`를 키로 `occurrences`, `avg_confidence`, `last_hints`를 기록하고, 매칭된 `value_bank` 항목의 `importance`에 `+0.1 * confidence`를 가산.
   - `occurrences >= 3` 및 `avg_confidence >= 0.85`인 기록이 있으면 `RULE: ...` 프롬프트 변이를 제안.

---

## 2. 잘된 부분 3가지 (Strengths)

### ① 이중 도메인 8-레지스터 시맨틱 격리 + 비대칭 망각률($\lambda$) 및 레지스터별 음수 감쇠(`AD-7`)
- **근거 코드**: [`crow_core.py#L111-L141`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L111-L141), [`crow_core.py#L316-L399`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L316-L399), [`crow_core.py#L489-L502`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L489-L502)
- **설계적 강점**:
  - 단일 벡터 스토어에 "코딩 스타일", "일회성 디버깅 컨텍스트", "개인 철학"을 섞지 않고 **도메인(`code`/`life`) × 시간척도($\lambda \in \{0.9999, 0.9995, 0.9500\}$)** 로 물리적 행렬을 분리한 점은 LLM 페르소나 유지에 매우 유효합니다.
  - 특히 v1.5.0의 `NEG_DAMPEN_BY_REGISTER = {"bug": 1.0, "life_avoid": 1.0}` (`#L115`)는 일반 선호(`0.6` 감쇠)와 달리 **실패·회피 신호가 약화되지 않도록 도메인 의미론과 감쇠 계수를 일치**시킨 정교한 설계입니다.
  - `recall_multi()` (`#L316-L399`)가 레지스터 순서 편향이나 빈 레지스터 필러("faint bias") 없이 전체 후보를 `eff_sim` 기준으로 전역 병합하고, 실제로 히트한 레지스터만 `recall_stats`에 기록(`#L372-L380`)하도록 개선한 점도 우수합니다.

### ② LLM 친화적 MCP 3-Tool 통합(`AD-5`) + 보수적 정화 게이트(`AD-1`) + 단일 파일 메타데이터 프로젝트 스코핑(`AD-4`)
- **근거 코드**: [`crow_mcp_server.py#L91-L238`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L91-L238), [`crow_mcp_server.py#L274-L433`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L274-L433), [`crow_sanitize.py#L19-L132`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_sanitize.py#L19-L132), [`crow_core.py#L405-L432`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L405-L432)
- **설계적 강점**:
  - 10개였던 MCP 도구를 `crow_recall` (`format="bias_block"` 흡수), `crow_ingest` (`exit_code` 빌드 훅 자동 극성 흡수), `crow_admin` (`action` 디스패치) 3개로 압축해 LLM의 **툴 선택 오류율과 시스템 프롬프트 스키마 토큰 소모를 대폭 줄였습니다**.
  - `crow_sanitize.py`는 stdlib(`re`, `os`)만으로 이모지·자모(`ㄱ-ㅎㅏ-ㅣ`)·이모티콘을 제거하되 `C++`, `...`, `127.0.0.1`, 한글 음절(`가-힣`), 식별자(`snake_case`)를 보호하며, 정화 후 빈 문자열이면 `empty_after_sanitize`로 거부하여(`crow_core.py#L484-L485`) 무의미한 임베딩 오염을 차단합니다.
  - 물리적 파일 분할 대신 `_accept()` (`#L405-L432`)에서 `SIM_CUTOFF(0.35)`, `CROSS_PROJECT_CUTOFF(0.42)`, `PROJECT_BOOST(1.05)`, 총 부스트 상한 `×1.15`, `strict_project` 하드 필터를 결합해 **전역 자아(Global Brain)와 프로젝트 격리를 단일 저장소에서 공존**시킨 점도 실용적입니다.

### ③ 멀티 클라이언트 직렬화(Dual-Mode HTTP/SSE) + PID 생존 검사 락 + Windows/OneDrive 원자적 영속화
- **근거 코드**: [`crow_mcp_server.py#L43-L53`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L43-L53), [`crow_mcp_server.py#L590-L608`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L590-L608), [`crow_core.py#L42-L94`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L42-L94), [`crow_core.py#L172-L188`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L172-L188), [`crow_core.py#L794-L815`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L794-L815)
- **설계적 강점**:
  - 하나의 Python 프로세스 안에서 SSE(`9020`), Streamable HTTP(`9021`), REST(`/health`, `/ingest`, `/recall`)를 동시 서빙하여 Zoo Code·Kimi Code·CLI 훅이 단일 `crow.bin`을 경합 없이 공유합니다.
  - `_acquire_file_lock`은 Windows `ctypes.windll.kernel32.OpenProcess`/`GetExitCodeProcess`와 POSIX `os.kill(pid, 0)`로 **좀비 락과 실제 실행 중 프로세스를 구분**하며, `_persist`는 `.tmp` 저장 후 `os.replace` 및 OneDrive 파일 락을 고려한 3회 지수 백오프 재시도와 손상 시 `.bak.*` 자동 복구(`#L172-L184`)를 제공합니다.
  - Windows `cp949` 인코딩 붕괴를 막는 UTF-8 래핑(`crow_mcp_server.py#L43-L53`) 역시 한국어 환경 실전 운영에서 매우 중요한 디테일입니다.

---

## 3. AI 실전 사용에 있어 부족한 면 3가지 (Deficiencies — 코드 및 실운영 데이터 실측 기반)

> 아래 3가지 문제는 단순 추론이 아니라 현재 워크스페이스의 실제 운영 파일(`memory/crow.bin`, `memory/value_bank.json`, `memory/recall_stats.json`)을 직접 계측하여 확인한 현상입니다.

### ① Rank-1 스펙트럼 붕괴 + `float16` 언더플로로 인한 연상 회상 기능 상실
- **근거 코드**: [`crow_core.py#L211-L214`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L211-L214), [`#L259-L262`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L259-L262), [`#L300-L302`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L300-L302), [`#L497-L502`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L497-L502), [`#L517-L531`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L517-L531), [`#L537-L557`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L537-L557)
- **실측 데이터 및 수학적 원인**:
  1. **`float16` 언더플로(Zeroing)**: `style` / `life_pref`는 `dim=4096×4096`, `λ=0.9999`입니다. 단위 벡터 외적의 전형적 원소 크기는 $1/4096 \approx 2.44 \times 10^{-4}$이고, `(1-λ)=1e-4`를 곱하면 `delta` 원소는 **`2.44e-8`** 입니다. IEEE-754 `float16`의 최소 양의 비정규수(subnormal)는 $2^{-24} \approx 5.96 \times 10^{-8}$(반올림 한계 $2^{-25} \approx 2.98 \times 10^{-8}$)이므로, **`delta.astype(np.float16)` 시 대부분의 원소가 정확히 `0.0`으로 소멸**합니다 (`style_S` `max_abs=1.38e-5`, `life_pref_S` `max_abs=1.28e-5`).
  2. **Rank-1 스펙트럼 붕괴(96~99.4% 에너지 집중)**: `nomic-embed-text-v1.5` 문장 임베딩은 중심화(centering)되지 않은 양의 원뿔(anisotropic cone)에 분포하고, 동일 키 반복 적재 시 `S`에 대한 중복 억제/직교화가 없으며, `_maybe_clip`은 `MAX_SV = 2.0` 이상일 때만 작동합니다(실제 최대 특이값은 `0.00085 ~ 0.5096`이므로 **단 한 번도 클리핑이 발동하지 않음**). 실측 결과 8개 중 7개 레지스터가 사실상 Rank-1 행렬로 붕괴했습니다:
     - `bug_S`: $s_0 = 0.06964, s_1 = 0.00279$ (**$s_0$ 에너지 비율 99.4%**)
     - `arch_S`: $s_0 = 0.10055, s_1 = 0.00512$ (**99.0%**)
     - `context_S`: $s_0 = 0.50961, s_1 = 0.03283$ (**98.1%**)
     - `life_context_S`: $s_0 = 0.40534, s_1 = 0.04563$ (**97.6%**)
     - `life_pref_S`: $s_0 = 0.00379, s_1 = 0.00035$ (**96.8%**), `life_phil_S`: **96.4%**, `style_S`: **96.0%**
  3. **쿼리 무관 동일 힌트 반환 현상**: $S \approx s_0 u_0 v_0^T$이므로 어떤 쿼리 $q$를 넣어도 $r = S^T q \approx s_0 (u_0^T q) v_0$는 항상 $\pm v_0$ 방향만 가리킵니다(무작위 5개 쿼리 간 `r` 쌍별 코사인 유사도 최대 `+0.994` / `-0.994`). 실제 [`memory/recall_stats.json`](file:///D:/OneDrive/Projects/Crow%20Memory/memory/recall_stats.json) 계측 결과:
     - `style`: 서로 다른 **83개 쿼리 중 82개**가 동일한 단일 힌트(`Fix-1 구현 실측...`)만 반환
     - `bug`: **83/83개 전부** 동일 힌트(`Fix pattern that generalizes...`)만 반환
     - `arch`: **82/82개 전부** 동일 힌트(`Session completed 8 commits...`)만 반환
     - `life_phil`: **82/82개 전부** 동일 힌트(`Owner decisions...`)만 반환
     - `life_pref`: **147/147개 전부** 동일 힌트(`User strongly corrected...`) 반환
  4. **`confidence` 기하학적 붕괴 및 `evolve_propose` 불발**: `confidence = ||r||_2 / ||S||_F`는 직교 패턴 $K$개가 정상 저장될수록 $1/\sqrt{K}$로 감소합니다(예: 100개 패턴이면 완벽 일치도 `0.10`). 이로 인해 [`check_drift`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L742-L758)는 현재 **`452`건의 저신뢰 레코드(`avg_conf < 0.5`)로 상시 Drift Alert 상태**이며, 반대로 `evolve_propose()`는 `md5(query)` 정확 문자열 일치(`occ >= 3`)를 요구하므로 자연어 쿼리가 매번 달라지는 LLM 환경에서 **총 724개 쿼리 해시 중 `occ >= 3`이 0건(`max_occ = 1`)**으로 진화 파이프라인이 전혀 작동하지 못하고 있습니다.

### ② 극성(Polarity) 의미론 역전 및 "중요도 래칫(Importance Ratchet)"으로 인한 신규 기억 즉시 증발
- **근거 코드**: [`crow_core.py#L444-L468`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L444-L468), [`#L487-L507`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L487-L507), [`#L580-L631`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L580-L631), [`#L677-L689`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L677-L689), [`#L845-L895`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L845-L895)
- **실측 데이터 및 작동 결함**:
  1. **신규 기억 즉시 축출(New-Memory Death Spiral)**: `_track_recall()`은 조회될 때마다 `vb_entry["importance"] += 0.1 * confidence`를 시간 감쇠 없이 무한 누적합니다(`#L688`). 여기에 Rank-1 편향이 겹치며 소수 항목의 `importance`가 최대 **`339.39`**까지 치솟았습니다(`Whiteboard state: analyzed 8 commands` x280회). 현재 `memory/value_bank.json`(500/500 포화)의 **최소 `importance`는 `1.6866`**(`importance <= 1.5`인 항목 **0개**, 중앙값 `7.50`)입니다. 그런데 `_append_value_bank()` (`#L615-L624`)는 새 항목을 `importance = abs(polarity)`로 먼저 append한 뒤 `min(importance)`를 pop하므로, **`|polarity| <= 1.5`인 모든 신규 기억(`exit_code` 자동 적재 `+1.5/+0.5/-0.5/-1.0` 및 기본 `1.0` 전부)은 저장된 그 밀리초에 즉시 축출되어 삭제**됩니다!
  2. **음수 극성(`polarity < 0`) 기억의 자기은폐 및 역강화 버그**: `value_bank` 엔트리 스키마(`#L603-L614`)에는 **`polarity` 부호가 저장되지 않고** 오직 `+v` 벡터와 `abs(polarity)`만 저장됩니다. LLM이 문서(`AGENTS.md`, `crow_ingest` 스키마) 지침대로 실수·안티패턴을 `polarity = -1.0`이나 `exit_code = 1`로 저장하면, 행렬 $S$는 $-v$를 학습해 회상 벡터 $r \approx -v$를 만듭니다. 이후 `_faiss_search` (`#L893`)는 `(+v) · (-v) = -1.0 < SIM_CUTOFF(0.35)`를 산출하므로 **부정 교훈(안티패턴)이 스스로를 검색 결과에서 은폐**합니다. 반대로 기존 잘못된 기억을 교정하려고 같은 `key`에 `polarity = -1.5`를 넣으면 `#L595`가 `importance += abs(-1.5)`를 실행해 **오히려 나쁜 기억의 생존력(`importance`)을 +1.5 올려주는 역전 버그**가 발생합니다.
  3. **필터링 전 `top_k` 절단 및 FAISS 미연동/인덱스 비동기화**: `_nearest_hints()` (`#L444`)는 `_accept()`로 `strict_project`나 `CROSS_PROJECT_CUTOFF`를 검사하기 전에 `_faiss_search(r, register, top_k=2)`로 단 2개만 먼저 뽑아옵니다. 상위 2개가 타 프로젝트 기억이면 `strict_project=True`일 때 **3순위에 같은 프로젝트의 완벽한 기억이 있어도 `[]`를 반환**합니다. 또한 `build_faiss_index()`는 서버 런타임 어디에서도 호출되지 않는 사문화된 코드이며, `_append_value_bank()` (`#L625`)의 축출 시 타 레지스터 항목이 pop되어도 현재 `register`의 캐시만 무효화하는 결함이 있습니다.

### ③ 과도한 매-턴 호출 오버헤드, 200자 강제 절단, 그리고 인과·상태 구조 부재
- **근거 코드**: [`memory/system_prompt.md#L11-L24`](file:///D:/OneDrive/Projects/Crow%20Memory/memory/system_prompt.md#L11-L24), [`crow_mcp_server.py#L279`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L279), [`crow_core.py#L308`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L308), [`crow_core.py#L363`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L363), [`crow_core.py#L1047-L1057`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L1047-L1057)
- **실전 LLM 에이전트 관점의 문제**:
  1. **매 응답 강제 호출("BEFORE/AFTER every response")로 인한 턴 세금 및 잡음 양산**: `system_prompt.md#L11-L17`과 `crow_recall` 설명(`#L279`)은 단순 파일 수정이나 git 확인에도 매 턴 `crow_recall` + `crow_ingest`를 강제합니다. 이는 10턴 작업 시 20회의 추가 MCP 왕복 지연과 컨텍스트 토큰을 소모할 뿐만 아니라, 에이전트가 의무를 채우기 위해 `Whiteboard state` (280회), `Dep analysis: 0 files` (110회), `[CHECKPOINT]` 요약(20건), `k => v` 테스트 잔해(20회) 같은 운영 잡음을 `value_bank`에 쏟아붓게 만듭니다.
  2. **87.8% 기억의 200자 중도 절단(`[:200]`)**: `value_bank`는 `value`를 1000자까지 저장(`#L605`)하지만, 실제 반환 시 `recall()`(`#L308`)과 `recall_multi()`(`#L363`) 모두 `[:200]`으로 자릅니다. 실측 결과 **500건 중 439건(87.8%)이 200자를 초과**하여, 실제 반환문은 `"...나머지=fal (sim=0.79)"`처럼 핵심 해결책이 적힌 뒷부분이 잘린 반쪽 문장으로 LLM에 전달됩니다.
  3. **상태/인과 메타데이터 부재 및 파괴적 Drift 복구**: 기억이 평면적 `(key, value)` 문자열이라 `active` vs `superseded`(폐기된 구버전 결정) 구분이나 `원인 -> 해결책`, `적용 범위(언어/파일 패턴)`를 표현할 수 없습니다. 게다가 `recover_from_drift()` (`#L1048-L1053`)는 발동 시 30일 넘은 `value_bank` 항목을 레지스터 구분 없이 일괄 삭제해 `style`·`life_phil` 같은 장기 규칙까지 파괴합니다.

---

## 4. 구체적 개선안 3가지 (Architectural & Code Specs)

아래 3가지 개선안은 기존 Crow Memory의 철학(**"고정 크기 시냅스 가소성 + 창조적 망각 + 로컬 초저지연"**)을 훼손하지 않으면서, 실측된 결함을 근본적으로 해결하도록 설계되었습니다.

---

### 개선안 1: 시냅스 연산 정상화 — 중심화(Centering) + 스케일드 FP16 누적 + 하이브리드(`S^T q` + Key) 스코어링

#### A. AI 에이전트 행동·추론에 미치는 실전 영향
- **진짜 맥락 연상 복구**: Rank-1 붕괴가 해소되어, LLM이 Rust FFI 코드를 다룰 때는 Rust/FRB 직관을, UI 작업을 할 때는 폰트·레이아웃 습관을 정확히 회상합니다.
- **신뢰도 신호 정상화**: `confidence`가 더 이상 $1/\sqrt{K}$로 0 수렴하지 않으므로, 에이전트가 "이 힌트를 얼마나 강하게 믿고 따라야 하는지"를 정량적으로 판단할 수 있습니다.

#### B. 구체적 아키텍처 및 코드 스펙 (Schema Version 2)

1. **`crow.bin` 텐서 스키마 확장 (`_init_blank`, `crow_core.py`)**:
   - 기존 `{reg}_S` (`float16`)를 유지하여 140MB 고정 크기를 보존하되, 각 레지스터별로 **온라인 평균 벡터**와 **동적 지수 스케일**을 추가합니다:
     ```python
     # Per-register additions in crow.bin (float32, total ~250 KB)
     f"{reg}_mu_k": np.zeros(d_k, dtype=np.float32)
     f"{reg}_mu_v": np.zeros(d_v, dtype=np.float32)
     f"{reg}_scale": np.array(1.0, dtype=np.float32)
     "schema_version": np.array(2, dtype=np.int64)
     ```
   - 런타임 메모리에는 `self._S_f32: dict[str, np.ndarray]`를 두고 로드 시 `self.data[f"{reg}_S"].astype(np.float32) * float(self.data[f"{reg}_scale"])`로 복원하며, `_persist()` 시 `scale = max(float(np.max(np.abs(S_f32))) / 16.0, 1e-12)`로 정규화하여 `(S_f32 / scale).astype(np.float16)`로 저장합니다. **이 방식은 `2.44e-8` 크기의 `(1-λ)` 업데이트도 `float16` 언더플로 없이 100% 정밀도로 누적**합니다.

2. **중심화 + 재적재 쿨다운 + Rank-1 에너지 상한 (`ingest`, `crow_core.py`)**:
   - **중심화(Mean-Centering)**: 임베딩 원뿔 편향 제거를 위해 `mu_k`, `mu_v`를 EMA($\beta=0.02$)로 갱신하고 중심화·정규화된 $k_c, v_c$를 사용합니다:
     ```python
     def _center_unit(vec: np.ndarray, mu: np.ndarray) -> np.ndarray:
         c = vec.astype(np.float32) - mu
         n = float(np.linalg.norm(c))
         return c / n if n > 1e-8 else vec.astype(np.float32)
     ```
   - **동일 키 폭주 방지**: `_append_value_bank`에서 동일 `(register, key)`가 최근 300초 내 이미 적재되었거나 `ingest_count >= 5`인 경우, `S`에는 감쇠/가중치를 $1 / \sqrt{\text{ingest\_count}}$로 스케일 다운하여 봇성 반복 적재(`cnt=280`)가 행렬을 Rank-1로 장악하는 현상을 차단합니다.
   - **소프트 스펙트럼 균등화(`_equalize_spectrum`)**: `update_count % 250 == 0`마다 power iteration(10회)으로 최대 특이값 $s_0, u_0, v_0$를 추정하고, 에너지 비율 $s_0^2 / \|S\|_F^2 > 0.35$이면 $S \leftarrow S - (s_0 - s_{\text{target}}) u_0 v_0^T$ ($s_{\text{target}} = \sqrt{0.35} \|S\|_F$)로 **과도한 Rank-1 주성분만 감쇠**시켜 다중 패턴 다양성을 보호합니다.

3. **직접 벡터화된 하이브리드 회상 (`_nearest_hints` + `_score_candidates`)**:
   - `value_bank` 엔트리에 `key_vector_b64` 필드를 추가 저장합니다(기존 엔트리는 서버 기동 시 지연 마이그레이션 또는 `vector_b64` 단독 폴백).
   - `_nearest_hints()`에서 `top_k` 사전 슬라이싱을 폐기하고, 해당 레지스터의 전체 후보(최대 500개이므로 NumPy 행렬곱 `< 0.2ms`)에 대해 **시냅스 연상 점수 + 직접 키 유사도**를 결합한 뒤 `_accept()`를 통과시킵니다:
     ```python
     # sim_syn: cos(S_f32.T @ q_c, v_i), sim_key: cos(q, k_i)
     # S가 비어 있거나 cold-start일 때는 alpha -> 0.0으로 자동 폴백
     s_energy = float(np.linalg.norm(S_f32))
     alpha = 0.45 * min(s_energy / 0.1, 1.0)
     raw_sim = alpha * sim_syn + (1.0 - alpha) * sim_key
     ```
   - `confidence`는 `||r||/||S||_F` 대신 **상위 수락 힌트의 보정 유사도 최댓값(`round(min(top_eff_sim, 1.0), 4)`)** 으로 재정의합니다.

---

### 개선안 2: 부호 있는 극성 수명주기(Signed Polarity) + 시간 감쇠 기반 축출 (고착화 및 망각 버그 해결)

#### A. AI 에이전트 행동·추론에 미치는 실전 영향
- **최신 경험의 즉시 반영**: `importance`가 시간에 따라 감쇠하므로, 어제 발견한 신규 버그나 새 프로젝트 규칙이 과거의 고착된 기록(`importance=339`)에 밀려 즉시 증발하지 않습니다.
- **실수 회피 능력 복구**: `polarity < 0`으로 기록된 안티패턴이 검색에서 숨지 않고 `[AVOID]` 경고 태그로 명확히 노출되어, LLM이 과거에 실패했던 패턴을 반복하지 않게 됩니다.

#### B. 구체적 아키텍처 및 코드 스펙

1. **`value_bank.json` 스키마 확장 (하위 호환 유지)**:
   ```jsonc
   {
     "id": "sha256_12char",
     "key": "...",
     "value": "...",
     "key_vector_b64": "...",
     "vector_b64": "...",
     "register": "bug",
     "timestamp": 1781037147.0,
     "last_recalled_at": 1781039000.0,
     "recall_count": 2,
     "importance": 1.5,          // base positive magnitude
     "polarity_net": -1.5,       // NEW: signed polarity sum (default +importance if absent)
     "ingest_count": 1,
     "project": "crow-memory",
     "status": "active",         // NEW: "active" | "superseded" | "archived"
     "supersedes": null          // NEW: optional id/key of replaced entry
   }
   ```

2. **음수 극성(`polarity < 0`) 이원화 처리 (`ingest`, `_accept`)**:
   - **신규 안티패턴 저장(`existing is None` and `polarity < 0`)**:
     - `S`에는 오히려 양의 연상 강도 `+abs(polarity) * (1 - lam) * k_c v_c^T` (또는 `bug`/`life_avoid`에서는 양의 연상 링크)로 기록하여 유사 상황 질문 시 해당 벡터가 강하게 활성화되도록 하고, `value_bank`에는 `polarity_net = polarity` (음수)로 기록합니다.
     - 출력 시 `polarity_net < 0`인 힌트는 자동으로 `"[bug:AVOID] ..."` 또는 `stance: "avoid"` 필드로 마킹해 LLM이 "따라야 할 선호"와 "피해야 할 금기"를 혼동하지 않게 합니다.
   - **기존 기억 교정/부정 피드백(`existing is not None` and `polarity < 0`)**:
     - `existing["polarity_net"] += polarity`
     - `existing["importance"] = max(0.05, existing["importance"] + polarity)` (기존 `+ abs(polarity)` 버그 제거)
     - `polarity_net <= -1.0`이면 `existing["status"] = "superseded"`로 전환해 일반 추천에서 제외합니다.

3. **반감기 감쇠 유효 중요도(`_effective_importance`) + 신규 기억 보호 축출**:
   - 레지스터별 반감기(`HALF_LIFE_DAYS = {"context": 7, "life_context": 7, "bug": 60, "arch": 60, "life_avoid": 60, "style": 180, "life_pref": 180, "life_phil": 180}`)를 정의합니다:
     ```python
     def _effective_importance(entry: dict, now: float) -> float:
         reg = entry.get("register", "context")
         half_life = HALF_LIFE_DAYS.get(reg, 60.0)
         ref_ts = max(entry.get("last_recalled_at", 0.0), entry.get("timestamp", 0.0))
         age_days = max(0.0, (now - ref_ts) / 86400.0)
         decay = math.exp(-math.log(2.0) * age_days / half_life)
         base = float(entry.get("importance", 1.0))
         return min(base, 25.0) * decay  # cap runaway importance at 25.0
     ```
   - `_track_recall()`의 회상 보너스 누적은 1시간 내 동일 엔트리 재가산을 막고 상한을 `+0.05`씩 최대 `25.0`으로 제한합니다.
   - `_append_value_bank()`에서 `VALUE_BANK_MAX` 초과 시 **방금 추가된 신규 엔트리(`idx = len - 1`)를 제외한 기존 엔트리들 중 `_effective_importance` 최솟값**을 축출하며, `crow_sanitize` 또는 `ingest` 게이트에서 `[CHECKPOINT]`, `Whiteboard state:`, `Dep analysis:` 같은 일시 로그성 패턴은 자동 `ttl_days=3` 태그 또는 `context` 레지스터 강제 라우팅으로 장기 레지스터 오염을 방지합니다.

---

### 개선안 3: 엔트리 기반 의미 진화(`evolve_propose` 정상화) + 200자 절단 해소 + 작업 경계형 에이전트 프로토콜

#### A. AI 에이전트 행동·추론에 미치는 실전 영향
- **프롬프트 진화 실질 작동**: 동일한 문장이 아니더라도 유사한 상황에서 반복적으로 도움을 준 기억이 자동으로 `system_prompt.md` 후보로 승격되어, 시간이 지날수록 MCP 호출 없이도 에이전트의 기본 체질이 사용자에 최적화됩니다.
- **완전한 문맥 전달 및 지연 시간 절감**: 200자에서 잘린 불완전한 힌트 대신 온전한 규칙·해결책을 받아 오류율이 줄고, 매 응답 호출 강제를 해제해 작업 턴당 2회의 불필요한 MCP 왕복 비용을 제거합니다.

#### B. 구체적 아키텍처 및 코드 스펙

1. **`recall_stats`를 `md5(query)`에서 `entry_id` 중심으로 재설계 (`_track_recall`, `evolve_propose`)**:
   - 기존 `md5(query)` 버킷 대신 **`entry_hits[entry_id]`**를 추적합니다:
     ```python
     # recall_stats.json v2 structure
     "entry_hits": {
       entry_id: {
         "register": reg,
         "occurrences": int,
         "distinct_query_hashes": list[str],  # capped at 50 (deduped)
         "session_buckets": list[int],        # int(timestamp // 3600), tracks distinct hours
         "sim_sum": float,
         "last_seen": float,
       }
     }
     ```
   - `evolve_propose(min_confidence=0.55, min_sessions=3)`는 서로 다른 시간대(`len(session_buckets) >= 3`) 및 서로 다른 쿼리(`len(distinct_query_hashes) >= 3`)에서 `avg_sim >= 0.55`로 반복 히트된 `status == "active"` 엔트리를 선택(이미 `system_prompt.md`에 반영된 항목은 제외)하여 제안합니다.

2. **200자 강제 절단 해제 및 구조화된 힌트 포맷 (`recall`, `recall_multi`)**:
   - 절단 길이를 `200`에서 `500`으로 상향하고 문장/공백 경계에서 자르는 `_smart_truncate(text, limit=500)` 헬퍼를 도입합니다.
   - `recall_multi()` 반환 스키마를 확장하여 LLM이 우선순위와 유효성을 즉각 판별할 수 있게 합니다:
     ```python
     {
       "id": entry_id,
       "register": register,
       "stance": "avoid" if polarity_net < 0 else "prefer",
       "key": entry["key"][:120],
       "text": _smart_truncate(scrub_display(entry["value"]), 500),
       "project": entry.get("project"),
       "sim": round(float(h["sim"]), 4),
       "eff_sim": round(float(h["eff_sim"]), 4),
       "age_days": round((now - entry["timestamp"]) / 86400.0, 1),
     }
     ```

3. **비파괴적 Drift 복구(`recover_from_drift`) 및 에이전트 룰 개정 (`system_prompt.example.md`, `AGENTS.md`)**:
   - `check_drift()` 조건을 `low_confidence_record_count` 대신 **최근 20회 `recall`의 평균 `top1_sim < 0.35` 또는 `s0_energy > 0.75`** 로 변경합니다.
   - `recover_from_drift()` (`crow_core.py#L1047-L1057`)에서 **"30일 초과 `value_bank` 일괄 삭제" 코드를 제거**하고, 대신 `value_bank`의 `status == "active"` 항목들로부터 $S$ 행렬을 깨끗하게 재투영하는 `rebuild_matrices_from_bank()`를 실행하도록 교체합니다.
   - `system_prompt.example.md`와 `AGENTS.md`의 "매 응답 전후 무조건 호출" 규칙을 **이벤트 기반 4-트리거 규칙**으로 개정합니다:
     1) **세션 시작** (1회 `crow_recall(domain="all", project=...)`),
     2) **도메인/모듈 전환 또는 새로운 에러 직면 시** (`crow_recall(register="bug|arch")`),
     3) **빌드/테스트 결과·사용자 교정 피드백 발생 시** (`crow_ingest(..., polarity/exit_code)`),
     4) **세션 종료 시 핵심 교훈 1~2건 압축 저장** (운영 체크포인트·단순 검색 로그 저장 금지).

---

## 5. 구현 우선순위 로드맵 (다른 AI 코딩 에이전트용 실행 순서)

| 순서 | 대상 파일 | 작업 내용 | 검증 기준 |
|---|---|---|---|
| **1단계 (P0)** | `crow_core.py` | 개선안 2 (`_effective_importance`, `polarity_net` 저장/차감, 신규 항목 축출 보호, `strict_project` 전 전수 후보 스코어링) | `importance >= 1.7` 포화 상태에서도 신규 `polarity=1.0` 적재 후 생존 확인; 음수 극성 회상 테스트 통과 |
| **2단계 (P0)** | `crow_core.py` | 개선안 1 (`mu_k`/`mu_v` 중심화, scaled-FP16 누적, 중복 키 쿨다운, `s0` 에너지 상한, `sim_syn + sim_key` 하이브리드 스코어) + `scripts/rebuild_matrices.py`로 기존 500개 엔트리에서 `crow.bin` 재구축 | 서로 다른 5개 쿼리에서 서로 다른 `hints` 반환 및 `s0_energy < 0.45` 확인 |
| **3단계 (P1)** | `crow_core.py`, `crow_mcp_server.py`, `system_prompt.example.md`, `AGENTS.md` | 개선안 3 (`entry_hits` 기반 `evolve_propose`, `_smart_truncate(500)`, 비파괴적 `recover_from_drift`, 이벤트 기반 4-트리거 룰) + 기존 231개 + 신규 단위 테스트 통과 | `evolve_propose()`가 3개 이상 세션/쿼리 히트 시 정상 제안 생성; `pytest`/unittest 100% PASS |
