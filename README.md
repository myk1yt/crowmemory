# Crow Memory (까마귀 메모리)

> *"Crow remembers not the code, but the hand that wrote it."*
> — 까마귀는 코드를 기억하지 않고, 코드를 쓴 손을 기억한다.

**Crow**는 AI 코딩 에이전트(DeepSeek V4 Pro)에 장착하는 외부 시냅스 기억 장치다. 네 코딩 스타일, 버그 직관, 아키텍처 선호도를 압축된 가중치 행렬로 저장하고, 자연어 질문으로 인출한다.

---

## 빠른 시작 (5분)

### 1. 요구사항

- **Python 3.10+**
- **Zoo Code** (VS Code 확장)
- **DeepSeek V4 Pro API** 접근 권한

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/YOUR_USER/crow-memory.git
cd crow-memory

# 의존성 설치
pip install -r requirements.txt
```

### 3. Zoo Code에 MCP 연결

Zoo Code의 MCP 설정 파일을 연다:
- 경로: `%APPDATA%/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json`

다음 내용을 `mcpServers` 안에 추가한다:

```json
{
  "mcpServers": {
    "crow_memory": {
      "command": "python",
      "args": [
        "절대경로/crow_mcp_server.py",
        "--state",
        "절대경로/memory/crow.bin"
      ]
    }
  }
}
```

Zoo Code를 재시작하면 Crow가 자동으로 활성화된다.

### 4. 작동 확인

Zoo Code에서 AI에게 이렇게 말해본다:
> "crow_diagnostics 도구를 호출해서 Crow 메모리 상태를 확인해줘."

Crow가 살아있다면 진단 정보가 반환된다.

---

## crow.bin 공유 정책 (중요!)

| 파일 | 공유 여부 | 이유 |
|------|----------|------|
| `crow_core.py` | ✅ 공유 | 핵심 엔진 (코드) |
| `crow_mcp_server.py` | ✅ 공유 | MCP 서버 |
| `backup_manager.py` | ✅ 공유 | 백업 유틸리티 |
| `hitl_panel.html` | ✅ 공유 | HITL UI |
| `test_crow.py` | ✅ 공유 | 테스트 |
| `test_integration.py` | ✅ 공유 | 통합 테스트 |
| `requirements.txt` | ✅ 공유 | 의존성 |
| `mcp_config.json` | ✅ 공유 | 설정 예시 |
| **`memory/crow.bin`** | ❌ **비공유** | 네 개인 기억이 담겨 있음 |
| **`memory/value_bank.json`** | ❌ **비공유** | 네 경험 데이터 |
| **`memory/recall_stats.json`** | ❌ **비공유** | 네 리콜 통계 |
| **`memory/system_prompt.md`** | ❌ **비공유** | 네 진화된 규칙 |

**`.gitignore`에 반드시 추가할 것:**
```
memory/crow.bin
memory/*.bak*
memory/value_bank.json
memory/recall_stats.json
memory/system_prompt.md
memory/test_*/
```

각 사용자는 처음 실행 시 자동으로 빈 `crow.bin`을 생성하므로, 네 기억이 다른 사람에게 넘어갈 일은 없다.

---

## 작동 원리

```
사용자 질문 → DeepSeek V4 Pro
                  ↓ crow_recall("query", "style")
             Crow MCP Server (stdio)
                  ↓ encode() → S.T @ q → nearest neighbor
             crow.bin (4-register weight matrix)
                  ↓
             [User Bias] 힌트 반환 → 시스템 프롬프트 앞에 주입
                  ↓
             DeepSeek V4 Pro가 네 스타일로 코드 생성
```

---

## 10가지 MCP 도구

| 도구 | 설명 |
|------|------|
| `crow_recall` | 저장된 코딩 스타일/버그 직관 인출 |
| `crow_ingest` | 새로운 경험을 시냅스에 기록 |
| `crow_evolve_propose` | 통계적으로 유의미한 패턴 → 영구 프롬프트 규칙 제안 |
| `crow_diagnostics` | 메모리 상태 진단 |
| `crow_check_drift` | 기억 드리프트 감지 |
| `crow_ingest_from_build` | 빌드 결과 기반 자동 평가 |
| `crow_get_user_bias` | [User Bias] 블록 생성 |
| `crow_manage_prompt` | 시스템 프롬프트 관리 |
| `crow_manage_backup` | 백업 생성/순환/복구 |
| `crow_project_info` | 프로젝트별 메모리 격리 |

---

## 문제 해결

### Crow 도구가 보이지 않아요
- Zoo Code 재시작
- 최초 실행 시 `nomic-embed-text-v1.5` 모델 다운로드로 30~60초 소요될 수 있음
- Python이 PATH에 등록되어 있는지 확인: `python --version`

### recall 결과가 "Few memories stored yet"만 나와요
- 정상! Crow는 경험이 쌓일수록 정확해진다. 20~30회 이상 ingest하면 의미 있는 힌트가 나오기 시작한다.

### Windows에서 PermissionError 발생
- crow_core.py v1.0.1 이상에서는 자동 재시도 메커니즘이 내장되어 있다.

---

## 라이선스

MIT License — 자유롭게 사용, 수정, 공유할 수 있다.

---

*Crow Memory v1.0 — 2026년 5월*
*공동 설계: User & DeepSeek V4 Pro*
