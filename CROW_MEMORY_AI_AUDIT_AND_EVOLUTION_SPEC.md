# 🐦‍⬛ Crow Memory 심층 아키텍처 감사 및 차세대 AI 에이전트 메모리·플러그인 진화 명세서

> **대상 프로젝트**: `D:\OneDrive\Projects\Crow Memory` (v1.5.0 기준)  
> **문서 성격**: 타 AI 코딩 에이전트(Antigravity, Kimi Code, Claude Code, Cursor 등)가 즉시 읽고 코드 수정·마이그레이션·플러그인 패키징을 수행할 수 있는 **종합 감사 보고서 겸 구현 명세서(Implementation Spec)**  
> **분석 방법론**: 전체 소스코드 정밀 해부 + 라이브 운영 데이터(`memory/crow.bin`, `memory/value_bank.json`, `memory/recall_stats.json`, `memory/system_prompt.md`) 실측 계측 + 대상 AI 코딩 도구별 플러그인/훅 규격 검증

---

## 목차
1. [Executive Summary 및 현재 아키텍처 실측 진단](#제1장-executive-summary-및-현재-아키텍처-실측-진단)
2. [LLM 에이전트 관점에서 본 잘된 부분 3가지 (Strengths)](#제2장-llm-에이전트-관점에서-본-잘된-부분-3가지-strengths)
3. [AI 실전 사용에 있어 부족한 면 3가지 (Weaknesses — 실측 근거)](#제3장-ai-실전-사용에-있어-부족한-면-3가지-weaknesses--실측-근거)
4. [코어 엔진 & LLM 인지 개선안 3가지 + AI 에이전트에 미치는 실질적 영향](#제4장-코어-엔진--llm-인지-개선안-3가지--ai-에이전트에-미치는-실질적-영향)
5. [파이썬 서버 없는 '무서버(Serverless) 플러그인 & 경량 아키텍처' 전환 심층 설계](#제5장-파이썬-서버-없는-무서버serverless-플러그인--경량-아키텍처-전환-심층-설계)
6. [최종 권장안 (Recommended Master Strategy) 및 AI 에이전트용 실행 로드맵](#제6장-최종-권장안-recommended-master-strategy-및-ai-에이전트용-실행-로드맵)

---

## 제1장. Executive Summary 및 현재 아키텍처 실측 진단

### 1.1 설계 철학 요약
Crow Memory는 단순한 무한 RAG(Retrieval-Augmented Generation) 벡터 DB가 아니라, **인간의 시냅스 가소성과 망각 곡선을 모사한 외장형 귀납적 편향(Inductive Bias) 메모리**로 설계되었습니다.
- **이중 도메인 8-레지스터**: 작업 도메인(`code`: `style`, `bug`, `arch`, `context`)과 개인 철학 도메인(`life`: `life_pref`, `life_avoid`, `life_phil`, `life_context`)을 분리.
- **비대칭 지수 이동 평균(EMA) 감쇠**: 장기 철학($\lambda = 0.9999$)과 단기 작업 맥락($\lambda = 0.9500$)에 서로 다른 망각 속도를 부여.
- **하이브리드 저장 구조**: `4096×4096` / `2048×4096` Hebbian 연상 행렬(`memory/crow.bin`)과 최대 500개 슬롯의 보조 텍스트 뱅크(`memory/value_bank.json`) 결합.

### 1.2 코드베이스 토폴로지 및 라이브 데이터 실측 텔레메트리

| 모듈 / 아티팩트 | 역할 / 경로 | 실측 규모 및 핵심 심볼 |
|---|---|---|
| 코어 엔진 | `crow_core.py` (1,117 lines) | `CrowMemory` (`#L148-L1117`), `REGISTERS` (`#L120-L131`), `ingest` (`#L474-L515`), `recall` (`#L281-L314`), `recall_multi` (`#L316-L399`), `_accept` (`#L405-L432`), `_append_value_bank` (`#L580-L631`), `evolve_propose` (`#L537-L574`) |
| MCP 서버 | `crow_mcp_server.py` (689 lines) | MCP SDK 2.1.1 dual-mode(SSE `9020` + Streamable HTTP `9021` + REST `/health`, `/ingest`, `/recall`), 3개 도구(`#L274-L433`), 2개 프롬프트(`#L439-L464`) |
| 정화기 | `crow_sanitize.py` (132 lines) | 순수 stdlib(`os`, `re`), `scrub_text` (`#L84-L103`), `scrub_display` (`#L116`), `project_slug` (`#L119-L132`) |
| 지역화/스키마 | `crow_i18n.py` (424 lines) | 36개 언어 지원, `_BASE_TOOL_DEFINITIONS` (`#L43-L150`, `enum` 포함 — 단 `crow_mcp_server.py`에서 미연결) |
| 시냅스 행렬 | `memory/crow.bin` | **`140,518,352` bytes (~134 MiB)** `safetensors` (`float16`), `nomic-embed-text-v1.5` 768d → 랜덤 가우시안 `proj_W` 4096d 투영 |
| 텍스트 뱅크 | `memory/value_bank.json` | **`4,082,781` bytes (~3.89 MiB)**, **500/500건 포화**, 200자 초과 **439건(87.8%, 평균 378.6자)**, 텍스트 실데이터는 `<250 KB`(나머지는 `vector_b64`) |
| 회상 통계 | `memory/recall_stats.json` | 724개 `md5(query)` 버킷 기록, **`max_occ = 1` (`evolve_propose` 후보 0건)**, **452건 저신뢰(`avg_conf < 0.5`) 상시 Drift 경고** |
| 영구 규칙 | `memory/system_prompt.md` | `2,034` bytes (24 lines) — 단, **L14에 v1.5.0에서 삭제된 레거시 도구 `crow_ingest_from_build` 지시가 잔존** |

> **핵심 진단 결론**: Crow Memory의 **거시적 인지 철학(8-레지스터, 비대칭 망각, 부정 감쇠 예외, 3-Tool 압축, 글로벌+프로젝트 스코핑)**은 LLM 에이전트 설계 관점에서 매우 탁월합니다. 그러나 **구현 계층의 수치 연산(`float16` 언더플로, 비중심화 Rank-1 붕괴), 부호 소실(`polarity < 0` 회상 불가), 무감쇠 중요도 누적(신규 기억 즉시 축출)**이 겹쳐 실전에서는 심각한 인지 마비 상태에 빠져 있으며, **무거운 PyTorch 로딩 + 단일 파일 락(`crow.bin.lock`)** 때문에 번거로운 데몬 서버를 띄워야 하는 운영 마찰을 겪고 있습니다.

---

## 제2장. LLM 에이전트 관점에서 본 잘된 부분 3가지 (Strengths)

### 1. 이중 도메인 8-레지스터 비대칭 망각 곡선($\lambda$)과 실패 신호 보호(`AD-7`)
- **근거 코드**: `crow_core.py#L111-L141` (`REGISTERS`, `DOMAINS`, `NEG_DAMPEN_BY_REGISTER`), `crow_core.py#L489-L502`, `crow_core.py#L316-L399` (`recall_multi`), `crow_sanitize.py#L25-L117`
- **설계 메커니즘**:
  - `code` 도메인(`style`, `bug`, `arch`, `context`)과 `life` 도메인(`life_pref`, `life_avoid`, `life_phil`, `life_context`)을 분리하고, 장기 정체성(`style`, `life_pref`: $\lambda = 0.9999$, 반감기 ~6,930회)과 단기 작업 맥락(`context`, `life_context`: $\lambda = 0.9500$, 반감기 ~14회)의 망각 속도를 비대칭화했습니다.
  - v1.5.0에서 도입된 `NEG_DAMPEN_BY_REGISTER = {"bug": 1.0, "life_avoid": 1.0}` (`#L115`)은 일반 선호가 부정 피드백 시 `0.6`으로 감쇠되는 것과 달리, **실패·금지 신호는 약화 없이 온전한 강도(`1.0`)로 학습**되도록 도메인 의미론을 수식에 일치시켰습니다.
  - `crow_sanitize.py`는 외부 패키지 없이 stdlib(`os`, `re`)만으로 이모지·자모(`ㅋㅋㅋ`)·카모지를 제거하되 `C++`, `...`, `127.0.0.1`, `snake_case`, 한글 음절(`가-힣`)은 정밀 보존하여 임베딩 오염을 방어합니다.
- **LLM 에이전트에 주는 이점**: 한 세션에서 임시 디버깅 맥락을 수십 번 기록해도 사용자의 근본적인 코딩 스타일이나 인생 철학 행렬이 덮어써지지 않고, 코드 식별자 손상 없이 깔끔한 의미 벡터를 유지합니다.

### 2. AD-5(10→3) MCP 도구 통합과 무환각(`No-Fallback`) `recall_multi` 설계
- **근거 코드**: `crow_mcp_server.py#L91-L238`, `#L274-L433`, `crow_core.py#L316-L399` (`recall_multi`), `#L434-L468` (`_nearest_hints`)
- **설계 메커니즘**:
  - 기존 10개에 달하던 도구를 **`crow_recall`**(`format="bias_block"` 통합), **`crow_ingest`**(`exit_code` 자동 극성 매핑 통합), **`crow_admin`**(`action` 디스패치) 3개로 압축했습니다. 실제 MCP 라이브 스키마 측정 결과 전체 3개 도구 정의는 **5,253 chars (~1,313 tokens)**로 매우 경제적입니다.
  - 기본 호출(`register=None/"all"`, `domain="all"`) 시 `recall_multi()`가 8개 레지스터 후보를 단일 `eff_sim` 순위로 전역 병합하며, 유사도가 `SIM_CUTOFF = 0.35` 미만이면 억지 폴백 텍스트 대신 빈 배열 `[]`을 반환합니다(AD-2 / REQ-001).
- **LLM 에이전트에 주는 이점**:
  - 수십 개의 IDE/파일시스템 도구를 함께 쓰는 코딩 에이전트의 **Tool Selection 오류율과 프롬프트 어텐션 분산을 최소화**합니다.
  - 에이전트가 "이 규칙이 `style`에 있을까 `arch`에 있을까" 추측하며 3~4번 중복 호출할 필요 없이 1회 호출로 최상위 편향을 획득하며, 무관한 기억이 억지로 주입되어 다음 토큰 생성을 오염시키는 **컨텍스트 환각(Context Poisoning)** 을 차단합니다.

### 3. 단일 글로벌 기억 유지 + 메타데이터 기반 프로젝트 스코핑 + 결정론적 `exit_code` 매핑
- **근거 코드**: `crow_core.py#L405-L433` (`_accept`), `crow_core.py#L901-L920` (`ingest_from_build`), `crow_mcp_server.py#L127-L140`, `docs/260901_0001_session_crow-recall-precision/decisions.md#L4-L7`
- **설계 메커니즘**:
  - 프로젝트별로 DB 파일을 쪼개지 않고 단일 글로벌 저장소 위에서 `project` 메타데이터만으로 동일 프로젝트 기억은 `PROJECT_BOOST = 1.05` 배율(총 부스트 캡 `×1.15`), 타 프로젝트 기억은 `CROSS_PROJECT_CUTOFF = 0.42` 상향 컷오프(또는 `strict_project=True` 격리)를 적용합니다.
  - `crow_ingest`는 `exit_code`와 `user_edited`만으로 `+1.5 / +0.5 / -0.5 / -1.0` 극성을 결정론적으로 산정합니다.
- **LLM 에이전트에 주는 이점**: 새 레포지토리를 열더라도 사용자의 전역 철학(`project=None`)이 즉시 이어지는 동시에 프로젝트 특화 결정이 우선 노출되며, LLM마다 들쭉날쭉하게 매기는 주관적 `polarity` 편차를 줄입니다.

---

## 제3장. AI 실전 사용에 있어 부족한 면 3가지 (Weaknesses — 실측 근거)

> 아래 모든 결함은 추정이 아니라 현재 워크스페이스 `memory/` 폴더의 실데이터(`crow.bin`, `value_bank.json`, `recall_stats.json`, `system_prompt.md`)를 직접 계측하고 코드를 역추적하여 증명한 내용입니다.

### 1. 시냅스 행렬의 Rank-1 스펙트럼 붕괴(96~99.4%), `float16` 언더플로, 그리고 음수 극성 회상 불가 역설(Sign Inversion Paradox)
- **근거 코드**: `crow_core.py#L211-L214`, `#L259-L262`, `#L298-L302`, `#L432`, `#L493-L507`, `#L517-L531`, `#L603-L614`, `#L876-L895`
- **실측 데이터 및 수학적 원인 3가지**:
  1. **`float16` 비정규수 언더플로(Subnormal Zeroing)**:
     `style`·`life_pref` 레지스터는 `4096×4096`, $\lambda = 0.9999$입니다. L2 정규화된 4096차원 단위 벡터 외적($k v^T$)의 전형적 원소 크기는 $\sim 1/4096 \approx 2.44 \times 10^{-4}$이고, 여기에 $(1-\lambda) = 10^{-4}$를 곱하면 업데이트 원소 `delta` 크기는 **`2.44e-8`** 입니다. IEEE-754 `float16`의 최소 양의 비정규수는 $2^{-24} \approx 5.96 \times 10^{-8}$(반올림 한계 $2.98 \times 10^{-8}$)이므로 **`delta.astype(np.float16)` 변환 순간 대부분의 가중치 변화량이 정확히 `0.0`으로 증발**합니다 (`style_S` `max_abs=1.38e-5`, `life_pref_S` `max_abs=1.28e-5`).
  2. **Rank-1 스펙트럼 붕괴 (8개 중 7개 레지스터 마비)**:
     `nomic-embed-text-v1.5` 임베딩은 평균 중심화(Mean-Centering)가 안 된 양수 원뿔(anisotropic cone)에 몰려 있으며, 동일 키 반복 적재(`ingest_count` 최대 280회)를 억제하는 장치가 없고, `_maybe_clip()`(`#L517-L531`)은 `MAX_SV = 2.0` 이상일 때만 작동합니다(실제 최대 특이값은 `0.00085 ~ 0.5096`이므로 **지금까지 단 한 번도 작동하지 않음**). 그 결과 7개 레지스터 에너지의 **96.0% ~ 99.4%**가 단 1개의 특이값 $s_0$에 몰렸습니다:
     - `bug_S`: $s_0 = 0.06964, s_1 = 0.00279$ (**$s_0$ 에너지 비율 99.4%**)
     - `arch_S`: $s_0 = 0.10055, s_1 = 0.00512$ (**99.0%**)
     - `context_S`: $s_0 = 0.50961, s_1 = 0.03283$ (**98.1%**)
     - `life_context_S`: **97.6%**, `life_pref_S`: **96.8%**, `life_phil_S`: **96.4%**, `style_S`: **96.0%**
     - 이로 인해 $S \approx s_0 u_0 v_0^T$가 되어 **어떤 쿼리 $q$를 넣어도 회상 벡터 $r = S^T q$가 항상 $\pm v_0$ 한 방향만 가리킵니다**. 실제 `memory/recall_stats.json` 실측 결과:
       - `style`: 서로 다른 **83개 쿼리 중 82개**가 동일한 단일 힌트만 반환
       - `bug`: **83/83개 전부** 동일 힌트만 반환
       - `arch`: **82/82개 전부** 동일 힌트만 반환
       - `life_phil`: **82/82개 전부** 동일 힌트만 반환
       - `life_pref`: **147/147개 전부** 동일 힌트만 반환
  3. **음수 극성 회상 불가 역설(Sign Inversion Paradox)**:
     `ingest()`에 음수 `polarity`(예: `-1.5`, `-2.0`, 또는 `exit_code=1`일 때 `-0.5/-1.0`)를 입력하면 행렬 $S$에는 $-k v^T$ 방향이 더해져 회상 시 $r \approx -v$가 나옵니다. 그런데 `_append_value_bank()` (`#L603-L614`)는 **`polarity`의 부호를 버리고 양수 벡터 `+v`(`vector_b64`)와 `importance = abs(polarity)`만 저장**합니다. 결국 `_faiss_search()`(`#L893`)에서 `(+v) · (-v) ≈ -1.0`이 계산되어 `_accept()`의 `sim >= 0.35` 게이트에서 **100% 탈락**합니다. 즉, **"절대 하지 마라" 또는 "빌드 실패"로 기록된 기억은 설계 구조상 절대 회상될 수 없습니다.** 반대로 기존 잘못된 기억을 교정하려고 같은 `key`에 `polarity=-1.5`를 넣으면 `#L595`가 `importance += abs(-1.5)`를 실행해 **오히려 나쁜 기억의 생존력(`importance`)을 올려주는 역전 버그**가 발생합니다.

### 2. "중요도 래칫(Importance Ratchet)"으로 인한 신규 기억 즉시 증발, 87.8% 텍스트 절단(`[:200]`), 글로벌 500슬롯 편향
- **근거 코드**: `crow_core.py#L103`, `#L308`, `#L363`, `#L444`, `#L462`, `#L595`, `#L615-L624`, `#L679-L689`
- **실측 데이터 및 작동 결함**:
  1. **신규 기억 즉시 축출(New-Memory Death Spiral)**:
     `_track_recall()` (`#L688`)과 `_append_value_bank()` (`#L595`)는 감쇠 없이 `importance`를 계속 누적만 합니다. 위 Rank-1 붕괴와 맞물려 라이브 `memory/value_bank.json`(500/500 포화)의 **최소 `importance`는 이미 `1.6866`**(중앙값 `7.50`, 최대 `339.39`, `<= 1.5`인 항목 **0개**)까지 치솟았습니다. 그런데 `#L615-L624`는 새 기억을 `importance = abs(polarity)`로 먼저 넣은 뒤 전체에서 최솟값을 `pop`하므로, **`|polarity| <= 1.5`인 모든 신규 기억(`exit_code` 자동 적재 및 기본 `1.0` 전부)은 저장된 그 밀리초에 즉시 삭제(Evict)** 됩니다!
  2. **87.8% 기억의 200자 중도 절단**:
     저장 시 `value`는 1,000자까지 허용(`#L605`)하면서, 회상 경로 3곳(`#L308`, `#L363`, `#L462`) 모두 `[:200]`으로 자릅니다. 라이브 `value_bank.json` 500건 전수 실측 결과 **439건(87.8%, 평균 378.6자)**이 200자를 초과해, 정작 뒷부분에 적힌 예외 조건·해결책이 잘린 채 `"...나머지=fal (sim=0.79)"` 형태로 LLM에 전달됩니다.
  3. **글로벌 500슬롯 독식 & Pre-filter 누락**:
     8개 레지스터가 단일 500슬롯을 공유해 현재 `arch(188)/context(141)/bug(115)`가 **88.8%**를 차지하고 `life_avoid(4건)`·`life_phil(11건)`은 고갈 상태입니다. 또한 `_nearest_hints()` L444는 `_accept()` 프로젝트 필터를 돌리기 전에 `_faiss_search`에서 딱 `top_k`개만 먼저 잘라오므로, `strict_project=True`일 때 상위 `top_k`개가 타 프로젝트 기억이면 **후순위에 해당 프로젝트 기억이 있어도 `[]`를 반환**합니다.

### 3. 수동적 프롬프트 순응 의존, Stale Tool Trap, `evolve` 불발 및 스키마/데이터 파편화
- **근거 코드**: `memory/system_prompt.md#L11-L24`, `crow_mcp_server.py#L93-L95`, `#L286-L430`, `crow_core.py#L537-L574`, `#L1047-L1057`, `#L1103-L1117`, `crow_sanitize.py#L119-L132`, `hitl_panel.html#L100-L195`
- **실전 LLM 운용 결함**:
  1. **매 응답 강제 호출("BEFORE/AFTER every response")과 Stale Tool Trap**:
     `memory/system_prompt.md#L11-L17`이 매 턴 앞뒤로 `crow_recall` + `crow_ingest`를 강제하여 10턴 작업 시 불필요한 20회 왕복 지연과 운영 잡음(`Whiteboard state` 280회, `Dep analysis: 0 files` 110회, `[CHECKPOINT]` 20건, 테스트 잔해 `'k'` 20건)을 양산합니다. 게다가 `install.py#L128`이 기존 `system_prompt.md`를 덮어쓰지 않아 **라이브 `memory/system_prompt.md#L14`에 v1.5.0에서 이미 삭제된 `crow_ingest_from_build`를 호출하라는 죽은 지시어가 남아 있습니다.**
  2. **`format="bias_block"` 파라미터 무시 & 통계 오염**:
     `crow_mcp_server.py#L93-L95`의 `bias_block` 경로가 `domain`, `project`, `strict_project`, `top_k`를 전부 무시하고 `get_user_bias_block()`을 부르며, 그 내부가 `self.recall()`을 8번 루프 호출해 `"General context and preferences"`라는 고정 문자열이 `recall_stats.json` 8개 레지스터를 `82~83`건씩 균등 오염시켰습니다.
  3. **`evolve_propose` 불발(0건) 및 스키마/슬러그 드리프트**:
     `evolve_propose()`(`#L537-L574`)는 `md5(query)` 문자열 완전 일치(`occ >= 3`)에 의존합니다. 자연어 쿼리가 매번 조금씩 바뀌는 LLM 특성상 **총 724개 쿼리 해시 중 `max_occ = 1`로 승격 후보가 0건**입니다. 또한 `crow_mcp_server.py`가 `Literal[...]` 대신 `str`만 사용해 실제 MCP JSON Schema에 `"enum"` 제약이 생성되지 않으며, `project_slug()`가 미연결되어 `ZooChat`/`zoochat`, `Surinoon`/`surinoon`이 분리 저장되어 있고, `recover_from_drift()`(`#L1047-L1057`)는 발동 시 30일 지난 기억을 레지스터 구분 없이 일괄 삭제하는 파괴적 로직을 갖고 있습니다.

---

## 제4장. 코어 엔진 & LLM 인지 개선안 3가지 + AI 에이전트에 미치는 실질적 영향

### 개선안 1: 시냅스 연산 정상화 — Scaled-FP16 + 온라인 평균 중심화 + 양방향 극성 보존 & 하이브리드 스코어링

#### A. AI 에이전트 행동 및 추론에 미치는 실질적 영향
- **진짜 맥락 연상 부활**: Rank-1 붕괴(96~99.4% 단일 방향 고착)가 해소되어, Rust FFI 작업 시엔 FFI 직관을, UI 작업 시엔 디자인 원칙을 정확히 회상합니다.
- **실패 학습 및 금지 가드레일(`Negative Constraint Attention`) 활성화**: `polarity < 0`으로 기록한 빌드 실패·금지 패턴이 더 이상 `sim < 0`으로 탈락하지 않고 `[AVOID]` 태그가 붙은 하드 가드레일로 주입되어, LLM이 과거에 실패한 접근법을 다시 시도하는 루프를 차단합니다.
- **신뢰도 지표 정상화**: `confidence`가 패턴 개수에 반비례해 0으로 수렴하던 현상이 사라져, 에이전트가 힌트의 채택 강도를 정확히 판단합니다.

#### B. 구체적 구현 명세 (다른 AI 에이전트 지시용)
1. **`crow.bin` Schema Version 2 확장 (`crow_core.py` `_init_blank`, `_load`, `_persist`)**:
   - 레지스터별로 온라인 평균 벡터(`{reg}_mu_k`, `{reg}_mu_v`, `float32`)와 동적 지수 스케일(`{reg}_scale`, `float32`)을 추가합니다(총 추가 용량 ~250 KB).
   - 로드 시: `S_f32[reg] = data[f"{reg}_S"].astype(np.float32) * float(data[f"{reg}_scale"])`
   - 저장 시: `scale = max(float(np.max(np.abs(S_f32[reg]))) / 16.0, 1e-12)`로 정규화 후 `(S_f32[reg] / scale).astype(np.float16)`로 저장. **이제 `2.44e-8` 크기의 `(1-λ)` 미세 업데이트도 `float16` 언더플로 없이 100% 보존됩니다.**
2. **온라인 중심화 + 재적재 쿨다운 + 소프트 스펙트럼 균등화 (`ingest`, `_equalize_spectrum`)**:
   - `mu_k`, `mu_v`를 EMA($\beta = 0.02$)로 갱신하고 중심화·L2 정규화 함수 `_center_unit(vec, mu)`를 적용합니다.
   - 동일 `(register, key)`가 300초 내 재적재되거나 `ingest_count >= 5`이면 `S` 업데이트 가중치를 $1/\sqrt{\text{ingest\_count}}$로 감쇠해 반복 적재 독점을 차단합니다.
   - `update_count % 250 == 0`마다 10회 power iteration으로 최대 특이값 $s_0, u_0, v_0$를 구하고, 에너지 비율 $s_0^2 / \|S\|_F^2 > 0.35$이면 $S \leftarrow S - (s_0 - \sqrt{0.35}\|S\|_F) u_0 v_0^T$로 과도한 Rank-1 주성분만 감쇠합니다.
3. **양방향 극성(`polarity_net`) 저장 및 하이브리드 전수 스코어링 (`_append_value_bank`, `_nearest_hints`)**:
   - `value_bank` 스키마에 `key_vector_b64`, `polarity_net`(부호 유지 합계), `status` (`"active" | "superseded" | "archived"`), `supersedes` 필드를 추가합니다(미존재 시 `+importance`, `"active"`로 하위 호환).
   - **신규 음수 기억(`existing is None and polarity < 0`)**: $S$에는 `+abs(polarity)` 강도로 연상 링크를 기록(또는 `bug`/`life_avoid` 양의 연상)하되 `value_bank`에 `polarity_net = polarity` (음수)로 저장해, 회상 시 `r`과 `-r` 양쪽 방향 중 강한 매칭을 포착하고 출력 포맷에 `[AVOID]` 접두어(또는 `stance: "avoid"`)를 부여합니다.
   - **기존 기억 부정 교정(`existing is not None and polarity < 0`)**: `existing["polarity_net"] += polarity`, `existing["importance"] = max(0.05, existing["importance"] + polarity)` (기존 `+abs(polarity)` 버그 제거). `polarity_net <= -1.0`이면 `status = "superseded"`로 전환합니다.
   - **`_nearest_hints` 오버페치 및 하이브리드 결합**: `top_k` 사전 슬라이싱(`#L444`)을 폐기하고 레지스터 내 `status == "active"` 전체 후보(최대 500개이므로 NumPy 연산 `<0.2ms`)에 대해 아래 식을 산출한 뒤 `_accept()`를 통과시킵니다:
     ```python
     s_energy = float(np.linalg.norm(S_f32))
     alpha = 0.45 * min(s_energy / 0.1, 1.0)
     # 음수 기억의 경우 S 방향(-r)과 키 유사도(sim_key) 모두 고려
     raw_sim = alpha * sim_syn + (1.0 - alpha) * sim_key
     ```

---

### 개선안 2: 시간 감쇠 유효 중요도 + 레지스터 쿼터 보호 + Semantic Upsert & 500자 스마트 절단

#### A. AI 에이전트 행동 및 추론에 미치는 실질적 영향
- **신규 학습 기억의 생존 보장**: 방금 해결한 치명적 버그나 새로운 아키텍처 합의가 과거의 `importance=339` 고인물 기록에 밀려 저장 즉시 삭제되던 현상이 사라집니다.
- **완전한 문맥 전달(87.8% 절단 해소)**: 200자 제한으로 핵심 해결책·예외 조건이 잘려 나가던 현상이 사라져, 에이전트가 한 번의 회상만으로 정확한 지침을 실행합니다.
- **메모리 에코(Echo) 제거**: 같은 원칙을 다르게 표현한 중복 기억들이 `top_k=2~5` 슬롯을 도배하지 않고 서로 다른 유용한 관점을 제공합니다.

#### B. 구체적 구현 명세
1. **반감기 감쇠 유효 중요도(`_effective_importance`) & 신규 기억 보호 실드**:
   - 레지스터별 반감기(`HALF_LIFE_DAYS = {"context": 7, "life_context": 7, "bug": 60, "arch": 60, "life_avoid": 60, "style": 180, "life_pref": 180, "life_phil": 180}`)를 적용하고 `importance` 상한을 `25.0`으로 캡핑합니다:
     ```python
     def _effective_importance(entry: dict, now: float) -> float:
         reg = entry.get("register", "context")
         half_life = HALF_LIFE_DAYS.get(reg, 60.0)
         ref_ts = max(entry.get("last_recalled_at", 0.0), entry.get("timestamp", 0.0))
         age_days = max(0.0, (now - ref_ts) / 86400.0)
         decay = math.exp(-math.log(2.0) * age_days / half_life)
         return min(float(entry.get("importance", 1.0)), 25.0) * decay
     ```
   - `_track_recall`은 동일 엔트리에 대해 1시간 쿨다운으로 `+0.05`씩만 가산합니다.
   - 축출(Eviction) 시 **방금 추가된 신규 엔트리 보호(Grace Shield)** + **레지스터 최소 쿼터(`MIN_PER_REGISTER = 15`) 보호**를 적용해 `life_phil`/`life_avoid` 고갈을 막습니다.
2. **코사인 유사도 기반 Semantic Upsert (`sim >= 0.90`)**:
   - `_append_value_bank`에서 동일 레지스터·동일 부호 내에 `vector` 코사인 유사도가 `0.90` 이상인 기존 활성 엔트리가 존재하면 새 슬롯을 만들지 않고 기존 엔트리에 병합(`ingest_count += 1`, `importance` 갱신, 더 구체적인 설명으로 업데이트)합니다.
   - `[CHECKPOINT]`, `Whiteboard state:`, `Dep analysis:` 등 일시적 작업 로그는 장기 레지스터 유입을 차단하거나 `ttl_days=3`의 `context`로 강제 라우팅합니다.
3. **500자 스마트 문장 경계 절단 (`_smart_truncate`)**:
   - `recall()`, `recall_multi()`, `_nearest_hints()`의 `[:200]` 하드 절단을 환경변수 `CROW_HINT_MAX_CHARS`(기본 `500`, 최소 `450`) 기반 `_smart_truncate(text, limit=500)`로 교체해 문장/공백 경계에서 자연스럽게 자릅니다.

---

### 개선안 3: 2-Tier Proactive Bias + `entry_id` 기반 `evolve_propose` + 엄격 스키마(`Literal`) & 비파괴 복구

#### A. AI 에이전트 행동 및 추론에 미치는 실질적 영향
- **추상 철학 상시 도달**: 에이전트가 아주 구체적인 버그 수정("Fix SQLite busy error")을 수행할 때도 컨텍스트 최상단에 사용자의 불변 철학(`life_phil`, `life_avoid`, `arch` 핵심)이 2-Tier로 고정 배치되므로, 세부 작업 중 큰 방향성을 잃지 않습니다.
- **실질적 규칙 자가 진화 & 도구 호출 오류 제로화**: `evolve_propose`가 실제로 작동해 반복 참조되는 패턴을 `system_prompt.md` 영구 규칙으로 승격시키며, JSON Schema `enum` 복원으로 LLM의 파라미터 오타가 원천 차단됩니다.

#### B. 구체적 구현 명세
1. **Stale Rule 자동 치유 + 2-Tier `bias_block` (`get_core_bias_summary`, `get_user_bias_block`)**:
   - 라이브 `memory/system_prompt.md#L14`의 `crow_ingest_from_build` 지시어를 제거하고, `get_system_prompt()` 로드 시 레거시 도구명을 자동 치환/경고합니다.
   - `format="bias_block"` 및 `crow_memory_bias` 프롬프트에서 `domain`, `project`, `strict_project`, `top_k` 파라미터를 정상 전달하고 **`track_stats=False`**로 조회해 통계 오염을 중단합니다.
   - 출력 구조를 **[Tier 1: Core Principles (Always-On — `life_phil`, `life_avoid`, `arch` 상위 중요도)]** + **[Tier 2: Task-Specific Recall (동적 쿼리 매칭)]** 로 이원화합니다.
2. **`entry_id` 중심 `evolve_propose` & 비파괴적 `recover_from_drift`**:
   - `recall_stats.json`을 `md5(query)` 대신 `entry_hits[entry_id]` (`distinct_query_hashes`, `session_buckets`, `sim_sum`) 구조로 변경하여 서로 다른 세션·질문에서 `avg_sim >= 0.55`, `hits >= 3`을 달성한 엔트리 상위 3건을 진화 후보로 제안합니다.
   - `check_drift()` 조건을 최근 20회 `recall`의 `avg(top1_sim) < 0.35` 또는 `s0_energy > 0.75`로 현실화하고, `recover_from_drift()` (`#L1047-L1057`)의 **30일 경과 기억 일괄 삭제 로직을 제거**한 뒤 `value_bank` 활성 항목들로부터 행렬 $S$를 깨끗하게 재투영하는 `rebuild_matrices_from_bank()`로 교체합니다.
3. **엄격 MCP 스키마(`Literal`) & `project_slug` 배선 & 이벤트 기반 4-트리거 규약**:
   - `crow_mcp_server.py`의 `register`, `domain`, `format`, `action`에 `typing.Literal[...]`을 적용해 JSON Schema `"enum"`을 생성하고 `tests/test_tool_schema.py`로 `crow_i18n`과 일치 여부를 검증합니다.
   - `_recall`/`_ingest` 입구에서 `crow_sanitize.project_slug()`를 강제 호출해 `ZooChat`/`zoochat` 파편화를 통일합니다.
   - 매 턴 강제 호출 규칙을 **① 세션 시작 1회, ② 도메인 전환/신규 에러 시, ③ 빌드 실패·사용자 교정 시(`exit_code`), ④ 세션 종료 핵심 압축 1~2건**의 4-트리거 규약으로 경량화합니다.

---

## 제5장. 파이썬 서버 없는 '무서버(Serverless) 플러그인 & 경량 아키텍처' 전환 심층 설계

> 사용자 추가 요청: *"mcp 형태가 아니면 kimi code나 antigravity나 또 다른 도구에 더 쉬운 plugin 형태로 사용할 수 있는 방법이 있는지, 지금의 파이썬 방식은 서버를 띄워야 하고 그게 좀 복잡하다."*

### 5.1 왜 기존 파이썬 방식은 서버를 띄워야 했고 복잡했는가? (2대 근본 원인)
현재 `start_crow_sse.bat`, Task Scheduler(`CrowMemoryAuto`), 듀얼 포트(`SSE :9020` + `Streamable HTTP :9021`), 좀비 PID 킬러 등이 필요했던 이유는 단순한 취향이 아니라 **`crow_core.py`의 두 가지 구조적 제약** 때문이었습니다:

1. **거대한 ML 콜드 스타트 (`torch` + `nomic-embed-text-v1.5` + `134 MiB crow.bin`)**:
   - `requirements.txt#L1-L10`은 `torch>=2.0.0`, `sentence-transformers>=2.7.0`, `faiss-cpu`, `uvicorn` 등을 요구합니다.
   - 매번 새 프로세스를 띄우면 모델 로딩과 `140.5 MB` `crow.bin` 역직렬화에만 **수 초 이상** 걸리므로, 턴마다 CLI로 실행할 수 없어 메모리에 상주시킬 수밖에 없었습니다.
2. **단일 프로세스 배타적 파일 락 (`crow.bin.lock`)**:
   - `crow_core.py#L42-L83`, `#L157-L161`은 `crow.bin` 동시 쓰기 손상을 막기 위해 OS PID 파일 락을 겁니다.
   - 실제로 v1.4.0에서는 **`stdio` MCP** 방식이었으나(`CHANGELOG.md#L92`), IDE 창이나 CLI를 2개 이상 동시에 열면 두 번째 프로세스가 `crow.bin.lock` 충돌(`RuntimeError`)로 죽어버려 v1.4.1부터 어쩔 수 없이 싱글톤 HTTP 데몬으로 전환했습니다.
3. **클라이언트 간 프로토콜 파편화**:
   - Kimi Code는 MCP SSE `event: endpoint` 핸드셰이크를 인식 못 하는 버그가 있어 `Streamable HTTP(:9021)`가 필요했고(`AGENTS.md#L9`), 반대로 Antigravity는 레거시 HTTP+SSE를 공식 폐기하고 **`Stdio`와 `Streamable HTTP`만 지원**하며, 그사이 좀비 프로세스나 포트 점유 오류(`scripts/ingest_session_result.py#L9-L18`)가 빈번히 발생했습니다.

---

### 5.2 무서버(Zero-Daemon) 플러그인 전환 3가지 아키텍처 비교

| 비교 항목 | 옵션 A: Pure Hook + CLI + Skill (Zero-MCP) | 옵션 B: 클라이언트 자동 관리 `stdio` MCP + SQLite WAL | **옵션 C (★최종 권장): SQLite WAL 코어 + Lifecycle Hooks + 얇은 `stdio` 선택 하이브리드** |
|---|---|---|---|
| **서버 기동 필요 여부** | **없음 (0개 프로세스 상주)** | **수동 기동 없음** (AI 도구가 자동 스폰/종료) | **수동 기동 없음** (상주 데몬·포트·Task Scheduler 완전 폐기) |
| **콜드 스타트 속도** | `< 15ms` (Python stdlib `sqlite3`만 사용) | `< 50ms` (또는 ONNX 적용 시 ~300ms) | **`< 15ms`** (핫패스 순수 stdlib; 오프라인 배치로 `crow.bin` 동기화 선택 가능) |
| **다중 창 동시 실행** | 100% 안전 (SQLite WAL + `busy_timeout=5000`) | 100% 안전 (SQLite WAL) | **100% 안전** (Antigravity + Kimi + Claude + Cursor 동시 실행 무충돌) |
| **LLM 기억 호출 누락** | **원천 차단** (훅이 매 세션/턴 자동 주입·수집) | 여전히 LLM이 `crow_recall` 호출을 까먹을 수 있음 | **원천 차단** (훅이 자동 주입/빌드 수집 + 필요 시 CLI/`stdio` 심층 검색) |
| **컨텍스트 토큰 비용** | **최소** (MCP 스키마 1,313 토큰 절약) | 1,313 토큰 유지 | MCP 생략 시 0 토큰 / `stdio` 활성화 시 3개 도구 제공 |
| **외부 패키지 의존성** | **0개 (`pip install` 불필요)** | 0개 (순수 stdlib JSON-RPC `stdio` 구현 시) | **0개 (Python 3.11+ 기본 내장 `sqlite3`, `json`, `re`, `math`만 사용)** |

#### ★ 왜 옵션 C가 압도적인 해결책인가?
실측 결과 `value_bank.json`(4.08 MB)에서 `vector_b64` 덩어리를 제외한 **실제 500건의 텍스트 지식 크기는 `< 250 KB`** 에 불과합니다.
- **핫패스(실시간 코딩 중 회상/저장)**를 Python 기본 내장 **`sqlite3` (WAL 모드 + FTS5 BM25 전문 검색 + `crow_sanitize.py` + 8-레지스터 EMA 감쇠 수식)** 로 옮기면 **`torch`도, `140MB crow.bin`도, 백그라운드 서버도, `.venv`도 전혀 없이 `< 15ms` 만에 동작**합니다.
- 게다가 Crow의 핵심 수식인 비대칭 망각률($\lambda$), `NEG_DAMPEN_BY_REGISTER`, `PROJECT_BOOST(×1.05)`, 반감기 감쇠, `[AVOID]` 극성 가드레일을 SQL + Python `math`로 100% 동일하게 재현할 수 있습니다:
  $$\text{score} = \text{BM25\_norm} \times \lambda^{\Delta t} \times \min\big(1 + 0.12 \ln(\text{eff\_imp} + 1),\, 1.15\big) \times \text{project\_boost}$$
- 만약 의미적 벡터 연상이 꼭 필요한 사용자를 위해서는, 백그라운드 데몬 없이도 **`crow sync` 오프라인 배치 명령**이나 경량 `onnxruntime` 23MB 임베딩으로 확장할 수 있는 통로를 열어둡니다.

---

### 5.3 AI 코딩 도구별 즉시 적용 가능한 플러그인 구현 명세 (복사·구현용 풀 스펙)

#### 제안 저장소 통합 디렉터리 구조 (`v2.0 Serverless`)
```text
crow-memory/
├── core/
│   ├── crow_db.py             # 순수 stdlib SQLite WAL + FTS5 + 8-레지스터 감쇠/극성 엔진
│   ├── crow_sanitize.py       # 기존 stdlib 입력 정화기 + project_slug()
│   ├── crow_cli.py            # 통합 CLI & 훅 어댑터 (--format agy|claude|kimi|cursor|text)
│   ├── crow_mcp_stdio.py      # [선택] 순수 stdlib JSON-RPC 2.0 stdio MCP 서버 (~120줄)
│   └── migrate_from_v1.py     # 기존 value_bank.json + recall_stats.json + system_prompt.md -> ~/.crow-memory/crow.db 이관기
├── adapters/
│   ├── antigravity/           # ~/.gemini/config/plugins/crow_memory/ 로 배포
│   │   ├── plugin.json
│   │   ├── hooks.json         # ★ Antigravity는 반드시 플러그인 루트에 위치해야 함
│   │   ├── mcp_config.json    # [선택] stdio MCP 자동 스폰 설정
│   │   ├── rules/AGENTS.md
│   │   └── skills/crow-memory/SKILL.md
│   ├── kimi-code/             # ~/.kimi-code/ 배포용
│   │   ├── hooks.toml.snippet # ~/.kimi-code/config.toml [[hooks]] 추가분
│   │   ├── mcp.json.snippet   # ~/.kimi-code/mcp.json (http -> stdio 교체)
│   │   └── skills/crow-memory/SKILL.md
│   ├── claude-code/           # Claude Code 플러그인 배포용
│   │   ├── .claude-plugin/plugin.json
│   │   ├── hooks/hooks.json
│   │   ├── .mcp.json
│   │   └── skills/crow-memory/SKILL.md
│   └── cursor/                # .cursor/ 또는 ~/.cursor/ 배포용
│       ├── hooks.json
│       ├── mcp.json
│       └── rules/crow-memory.mdc
└── scripts/
    └── install_plugin.py      # 원클릭 설치기 (데이터 마이그레이션 + 각 도구 어댑터 자동 연결)
```

---

#### ① Antigravity (`agy` 1.5.15+) 네이티브 플러그인 규격
> **검증된 핵심 주의사항** (`agy-customizations/docs/plugins.md#L61-L70`, `hooks.md#L129-L131`):
> 1. Antigravity 네이티브 플러그인(`plugin.json` 존재)은 `hooks/hooks.json`이 아니라 **반드시 플러그인 루트(`hooks.json`)** 에서 훅을 로드합니다.
> 2. Windows에서는 `cmd /c`로, CWD는 `hooks.json`이 있는 플러그인 루트로 실행되므로 커맨드에 `./`를 붙이지 말고 `python core/crow_cli.py ...` 형태를 사용해야 합니다.

**`~/.gemini/config/plugins/crow_memory/plugin.json`**:
```json
{
  "name": "crow_memory",
  "version": "2.0.0",
  "description": "Serverless external synaptic memory for AI coding agents (SQLite WAL + Lifecycle Hooks + Zero-Dep Stdio).",
  "author": "myk1yt",
  "license": "MIT",
  "keywords": ["memory", "crow", "hooks", "sqlite", "serverless"]
}
```

**`~/.gemini/config/plugins/crow_memory/hooks.json`**:
```json
{
  "crow-session-bias": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python core/crow_cli.py hook session-start --format agy",
        "timeout": 10
      }
    ]
  },
  "crow-turn-recall": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "python core/crow_cli.py hook pre-invocation --format agy",
        "timeout": 10
      }
    ]
  },
  "crow-auto-build-ingest": {
    "PostToolUse": [
      {
        "matcher": "run_command",
        "hooks": [
          {
            "type": "command",
            "command": "python core/crow_cli.py hook post-tool --format agy",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```
- **동작 방식**:
  - `SessionStart` 및 `PreInvocation`은 `stdin`으로 `conversationId`, `workspacePaths`, `lastUserInput`, `invocationNum`, `cwd` JSON을 받아 `< 15ms` 조회 후 `stdout`으로 아래 JSON을 출력하여 **모델이 생각하기 전에 컨텍스트를 확정 주입**합니다(`PreInvocation`은 `invocationNum == 1` 또는 턴 해시 중복 방지로 1회만 주입):
    ```json
    {
      "injectSteps": [
        {
          "systemMessage": {
            "systemMessage": "[User Bias -- Crow Memory]\n[Core Principles]\n- [life_phil] ...\n[Avoid / Past Failures]\n- [bug:AVOID] ...\n[Task Recall]\n- [arch] ..."
          }
        }
      ]
    }
    ```
  - `PostToolUse`(`matcher: "run_command"`)는 빌드·테스트 커맨드 실행 후 `error` 필드 유무를 감지해 LLM 개입 없이 조용히 성공(`+1.0`)/실패(`-0.5`)를 DB에 자동 기록하고 `{}`를 반환합니다.
- **검증 명령어**: `agy plugin validate ~/.gemini/config/plugins/crow_memory --strict`

**`~/.gemini/config/plugins/crow_memory/mcp_config.json` (심층 수동 기억 조작이 필요할 때만 선택 적용)**:
```json
{
  "mcpServers": {
    "crow_memory": {
      "command": "python",
      "args": ["core/crow_mcp_stdio.py"],
      "env": {
        "PYTHONUTF8": "1",
        "CROW_HOME": "~/.crow-memory"
      }
    }
  }
}
```

---

#### ② Kimi Code CLI (`kimi` 2.7.2+) 네이티브 연동 규격
> 로컬 `~/.kimi-code/config.toml` 검증 결과 Kimi Code는 `[[hooks]]` (`SessionStart`, `UserPromptSubmit`, `PostToolUse`)를 네이티브 지원하며, `~/.kimi-code/mcp.json`은 `stdio`를 지원해 기존에 문제가 많던 HTTP(:9021)/SSE(:9020) 서버를 완전히 없앨 수 있습니다.

**`~/.kimi-code/config.toml` 추가분 (`[[hooks]]`)**:
```toml
[[hooks]]
event = "SessionStart"
command = "python C:\\Users\\k1yt\\.crow-memory\\bin\\crow_cli.py hook session-start --format text"
timeout = 10

[[hooks]]
event = "UserPromptSubmit"
command = "python C:\\Users\\k1yt\\.crow-memory\\bin\\crow_cli.py hook pre-invocation --format text"
timeout = 10

[[hooks]]
event = "PostToolUse"
matcher = "Shell"
command = "python C:\\Users\\k1yt\\.crow-memory\\bin\\crow_cli.py hook post-tool --format text"
timeout = 10
```

**`~/.kimi-code/mcp.json` (기존 `http://127.0.0.1:9021/mcp` 대체 `stdio` 방식)**:
```json
{
  "mcpServers": {
    "crow-memory": {
      "command": "python",
      "args": ["C:\\Users\\k1yt\\.crow-memory\\bin\\crow_mcp_stdio.py"],
      "env": {
        "PYTHONUTF8": "1",
        "CROW_HOME": "C:\\Users\\k1yt\\.crow-memory"
      }
    }
  }
}
```

---

#### ③ Claude Code & Cursor 플러그인 규격

**Claude Code (`hooks/hooks.json` + `.claude-plugin/plugin.json`)**:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/core/crow_cli.py\" hook session-start --format claude",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/core/crow_cli.py\" hook pre-invocation --format claude",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Cursor (`.cursor/hooks.json` + `.cursor/mcp.json`)**:
```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      { "command": "python ~/.crow-memory/bin/crow_cli.py hook session-start --format cursor" }
    ],
    "beforeSubmitPrompt": [
      { "command": "python ~/.crow-memory/bin/crow_cli.py hook pre-invocation --format cursor" }
    ],
    "afterShellExecution": [
      { "command": "python ~/.crow-memory/bin/crow_cli.py hook post-tool --format cursor" }
    ]
  }
}
```

---

### 5.4 무서버 코어 SQLite WAL 스키마 명세 (`core/crow_db.py`)
제4장의 **3대 개선안(음수 극성 보존 `polarity_net`, `status`/`supersedes`, 반감기 감쇠, 500자 절단, `entry_id` 기반 `evolve_propose`)** 을 SQLite WAL 위에 곧바로 통합 구현하는 스키마입니다:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memories (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_uid        TEXT NOT NULL UNIQUE,   -- sha256[:12]
    register         TEXT NOT NULL,          -- style, bug, arch, context, life_*
    key_text         TEXT NOT NULL,
    value_text       TEXT NOT NULL,
    project          TEXT,                   -- project_slug() 정규화, NULL = global
    polarity_net     REAL NOT NULL,          -- 부호 보존 [-inf, +inf], 음수 시 [AVOID] 표출
    importance       REAL NOT NULL DEFAULT 1.0,
    ingest_count     INTEGER NOT NULL DEFAULT 1,
    recall_hits      INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'active', -- active | superseded | archived
    supersedes_uid   TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL,
    last_recalled_at REAL NOT NULL DEFAULT 0.0,
    UNIQUE(register, key_text)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    key_text,
    value_text,
    content='memories',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS entry_evolve_hits (
    entry_uid        TEXT PRIMARY KEY,
    distinct_queries TEXT NOT NULL DEFAULT '[]', -- JSON list capped at 50
    session_buckets  TEXT NOT NULL DEFAULT '[]', -- JSON list of int(ts // 3600)
    sim_sum          REAL NOT NULL DEFAULT 0.0,
    last_seen        REAL NOT NULL
);
```

---

## 제6장. 최종 권장안 (Recommended Master Strategy) 및 AI 에이전트용 실행 로드맵

사용자의 목적(**"내 철학을 LLM이 인간처럼 기억해 반복 설명을 줄이되, 매번 파이썬 서버를 띄우는 복잡함은 없애고 다양한 AI 코딩 도구에서 플러그인으로 쉽게 쓰고 싶다"**)을 가장 완벽하게 달성하기 위한 **최종 권장 전략은 두 트랙의 결합(무서버 v2.0 플러그인 전환 + 제4장 코어 수식/극성/진화 결함 일괄 해결)** 입니다.

### 6.1 최종 권장 결론
1. **만약 현행 `crow_core.py` (PyTorch + `crow.bin`) 아키텍처를 유지한 채 성능만 정상화하려면**: 제4장의 **개선안 1·2·3 (Option B 실용주의 조합)** 을 즉시 적용하십시오. (특히 `polarity_net` 부호 보존, `_effective_importance` 반감기 감쇠, 500자 스마트 절단, `mu_k/mu_v` 중심화 + Scaled-FP16은 지금 당장 망가진 회상 기능을 살리는 필수 응급처치입니다.)
2. **그러나 장기적으로 가장 강력히 추천하는 최종 권장안(★Master Recommendation)은 『v2.0 무서버 SQLite WAL 코어 + 네이티브 Lifecycle Hook 플러그인』 전환**입니다:
   - 기존 `value_bank.json` 500건과 `system_prompt.md`를 `~/.crow-memory/crow.db`로 1회 마이그레이션한 뒤, **Windows 작업 스케줄러(`CrowMemoryAuto`), `start_crow_sse.bat`, 포트 `9020/9021`, `torch` 대용량 런타임 의존성을 완전히 제거**합니다.
   - Antigravity·Kimi Code·Claude Code·Cursor의 **Lifecycle Hooks (`SessionStart` / `PreInvocation` / `PostToolUse`)** 가 매 세션 시작 시 2-Tier Core 철학을 자동 주입하고 빌드 실패/성공을 자동 수집하므로, LLM이 기억 도구를 까먹는 일 자체가 사라집니다.
   - 필요 시 ~120줄짜리 순수 stdlib `crow_mcp_stdio.py`를 연결하면 3개 MCP 도구(`crow_recall`, `crow_ingest`, `crow_admin`)도 데몬 서버 없이 클라이언트 자동 스폰 방식으로 그대로 유지할 수 있습니다.

---

### 6.2 AI 코딩 에이전트용 단계별 구현 체크리스트

다른 AI 코딩 에이전트에게 이 문서를 전달하고 아래 순서대로 작업을 지시하십시오.

#### [트랙 A] 현행 `v1.5.0` 코어 엔진 긴급 정상화 (기존 서버 방식 유지 시)
| 단계 | 작업 ID | 대상 파일 & 함수 | 핵심 구현 요건 | 독립 검증 명령어 |
|---|---|---|---|---|
| **P0** | **A-1** | `crow_core.py` (`_append_value_bank`, `_nearest_hints`, `_accept`, `recall`, `recall_multi`) | ① `polarity_net` 부호 저장 및 음수 기억 `[AVOID]` 양방향 회상, ② `_effective_importance` 반감기 감쇠 + 상한 `25.0` + 신규 기억 축출 보호 + `MIN_PER_REGISTER=15`, ③ `_smart_truncate(500)`, ④ `_nearest_hints` 전수 후보 스코어링(사전 `top_k` 절단 폐기) | `.venv\Scripts\python.exe -m unittest tests/test_recall_precision.py` |
| **P0** | **A-2** | `crow_core.py` (`_init_blank`, `ingest`, `_equalize_spectrum`) & `scripts/rebuild_matrices.py` | ① `mu_k`/`mu_v` 온라인 중심화 + `scale` 정규화 FP16 저장(언더플로 제거), ② 동일 키 쿨다운 & Rank-1 에너지 `0.35` 상한 감쇠, ③ `sim_syn + sim_key` 하이브리드 결합, ④ 기존 500개 엔트리에서 `crow.bin` 재구축 | `.venv\Scripts\python.exe -m unittest tests/test_recall_precision.py` (서로 다른 5개 쿼리에서 서로 다른 힌트 반환 & `s0_energy < 0.45` 검증) |
| **P1** | **A-3** | `crow_mcp_server.py`, `crow_core.py`, `memory/system_prompt.md`, `crow_sanitize.py` | ① `Literal[...]` `enum` 스키마 복원, ② `_recall`/`_ingest` 입구 `project_slug()` 연결, ③ `bias_block` 스코프 전달 + `track_stats=False` + 2-Tier Core/Dynamic Bias, ④ `system_prompt.md#L14` `crow_ingest_from_build` 제거, ⑤ `entry_hits` 기반 `evolve_propose` & 비파괴 `recover_from_drift`, ⑥ Semantic Upsert(`sim>=0.90`) | `.venv\Scripts\python.exe -m unittest discover tests` |

#### [트랙 B] 무서버 `v2.0` 유니버설 플러그인 전환 (★궁극적 권장 로드맵)
| 단계 | 작업 ID | 생성/수정 파일 | 핵심 구현 요건 | 독립 검증 명령어 |
|---|---|---|---|---|
| **Phase 1** | **B-1** | `core/crow_db.py`, `core/crow_sanitize.py`, `core/migrate_from_v1.py` | ① Python 3.11+ 순수 stdlib `sqlite3` (WAL + FTS5) 엔진 구축(제4장 개선안의 `polarity_net`, 반감기 감쇠, 레지스터 쿼터, 2-Tier Bias, 500자 절단, `entry_evolve_hits`, Semantic Upsert, `project_slug` 모두 내장), ② 기존 `memory/value_bank.json` 500건 + `system_prompt.md`를 `~/.crow-memory/crow.db`로 무손실 이관(테스트 잔해 `'k'`, `'test key'` 정화 옵션 포함) | `python core/migrate_from_v1.py --dry-run` 후 `--apply` 및 `python -m unittest tests/test_crow_db.py` (`recall`/`ingest` `< 20ms` 확인) |
| **Phase 2** | **B-2** | `core/crow_cli.py`, `core/crow_mcp_stdio.py` | ① `hook session-start`, `hook pre-invocation`(턴 중복 주입 방지 포함), `hook post-tool`(빌드/테스트 종료코드 자동 수집) 구현 및 `--format agy\|claude\|kimi\|cursor\|text` 출력기 작성, ② 외부 패키지(`mcp`, `torch`, `uvicorn`) 0개인 ~120줄 JSON-RPC 2.0 `stdio` 서버 구현 | `echo {"lastUserInput":"rust ffi","invocationNum":1} \| python core/crow_cli.py hook pre-invocation --format agy` |
| **Phase 3** | **B-3** | `adapters/antigravity/*`, `adapters/kimi-code/*`, `adapters/claude-code/*`, `adapters/cursor/*`, `scripts/install_plugin.py` | ① `~/.gemini/config/plugins/crow_memory/` 배포(루트 `hooks.json` 준수), ② `~/.kimi-code/mcp.json`의 `http://127.0.0.1:9021/mcp`를 `stdio`로 교체 및 `config.toml` `[[hooks]]` 등록, ③ Claude Code / Cursor 어댑터 템플릿 제공, ④ 기존 `CrowMemoryAuto` 작업 스케줄러 비활성화 안내 | `agy plugin validate ~/.gemini/config/plugins/crow_memory --strict` 및 Antigravity·Kimi 동시 세션 무충돌 검증 |

---

*참고: 본 보고서의 상세 기초 조사 원문은 [`reports/research-core-engine-report.md`](file:///D:/OneDrive/Projects/Crow%20Memory/reports/research-core-engine-report.md) 및 [`reports/research-report.md`](file:///D:/OneDrive/Projects/Crow%20Memory/reports/research-report.md)에서도 교차 확인할 수 있습니다.*
