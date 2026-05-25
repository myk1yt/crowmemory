# Kimi Code CLI Crow 자동 연결 — AGENTS.md 방식 이관 지시

> 이 문서는 Zoo Code의 딥시크에게 전달하는 핸드오프 문서입니다.
> 목표: VS Code 실행 → Kimi Code 탭 열기 → 즉시 Crow Memory 연결 및 자동 활성화

---

## 1. 발견사항 (Kimi Code CLI 공식 문서 기반)

Kimi Code CLI의 공식 문서를 확인한 결과, 다음 사실들을 확인했습니다:

### 1.1 `custom_modes.yaml`은 Zoo Code 전용
- Kimi Code CLI는 **공식적으로 `custom_modes.yaml`을 지원하지 않습니다**.
- `%APPDATA%/Code/User/globalStorage/moonshot-ai.kimi-code/settings/custom_modes.yaml`이 없어도 Kimi Code CLI는 이 파일을 읽지 않습니다.

### 1.2 `AGENTS.md` 자동 주입
- Kimi Code CLI의 `system.md` 템플릿에는 **`${KIMI_AGENTS_MD}`**라는 빌트인 변수가 존재합니다.
- 이 변수는 **프로젝트 루트의 `AGENTS.md` 내용을 system prompt에 자동으로 삽입**합니다.
- 깊이 우선 탐색으로 `.kimi/AGENTS.md`도 포함됩니다.
- **결론**: `patch_kimi_code.py`처럼 Kimi Code CLI 낶부 파일을 해킹하지 않고도, 프로젝트 루트의 `AGENTS.md`에 Crow 규칙을 작성하면 매 세션 시작 시 자동으로 주입됩니다.

### 1.3 Kimi Code CLI MCP 표준 설정 위치
- Kimi Code CLI의 MCP 설정 **표준 위치**는 **`~/.kimi/mcp.json`** 입니다.
- 현재 `%APPDATA%/.../moonshot-ai.kimi-code/settings/mcp_settings.json`에 등록되어 있지만, 이것은 낶부 캐시일 가능성이 있습니다.
- 공식 문서: `kimi mcp add --transport http ...` 명령어를 사용하면 `~/.kimi/mcp.json`에 기록됩니다.

### 1.4 MCP 툴 승인 메커니즘
- Kimi Code CLI는 기본적으로 **모든 MCP 툴 호출에 사용자 승인 팝업**을 띄웁니다.
- `.roo/mcp.json`의 `alwaysAllow`는 Roo/Zoo Code 전용 기능이며, Kimi Code CLI는 이를 인식하지 않습니다.
- **YOLO 모드 또는 AFK 모드**에서만 MCP 툴이 자동 승인됩니다.

---

## 2. 기존 방식의 한계

| 기존 방식 | 한계 |
|---|---|
| `patch_kimi_code.py` | Kimi Code CLI 업데이트 시마다 `system.md`가 덮어써지므로 **재패치가 필수** |
| `custom_modes.yaml` | Kimi Code CLI가 인식하지 않으므로 **아무 효과 없음** |
| `mcp_settings.json` | Kimi Code CLI 낶부 캐시일 수 있어 **업데이트 시 초기화 위험** |

---

## 3. 새로운 방식: AGENTS.md + `~/.kimi/mcp.json`

### 3.1 `AGENTS.md` (프로젝트 루트)
- `patch_kimi_code.py`의 `CROW_SECTION` 내용을 그대로 이관합니다.
- Kimi Code CLI가 `${KIMI_AGENTS_MD}`로 **자동 로드**하므로 별도 패치가 필요 없습니다.
- Kimi Code CLI 업데이트에도 **영향을 받지 않습니다**.

### 3.2 `~/.kimi/mcp.json` (Kimi Code CLI 전역 설정)
- `crow_memory`를 공식 위치에 등록하여 프로젝트 무관하게 항상 연결되도록 합니다.
- SSE URL: `http://127.0.0.1:9020/sse`

---

## 4. 작업 항목 (딥시크가 수행)

### ✅ 필수 작업
- [ ] **`AGENTS.md` 검토 및 보강**
  - 프로젝트 루트의 `AGENTS.md`를 확인
  - 필요시 Crow Memory 규칙 추가/수정
- [ ] **`~/.kimi/mcp.json` 생성/검증**
  - Kimi Code CLI 전역 MCP 설정에 `crow_memory`가 등록되어 있는지 확인
  - 없다면 `kimi mcp add --transport http crow_memory http://127.0.0.1:9020/sse` 실행
- [ ] **자동 시작 파이프라인 점검**
  - Windows 시작 프로그램의 `Crow_Memory_SSE.bat`이 `start_crow_sse.bat`을 호출하도록 확인
  - `.vscode/tasks.json`의 `folderOpen` 태스크가 정상 동작하는지 확인

### ⚙️ 선택 작업
- [ ] **`install.py` / `install.ps1` 업데이트**
  - `AGENTS.md` 생성 로직 추가
  - `~/.kimi/mcp.json` 등록 로직 추가
  - `patch_kimi_code.py` 호출 제거 또는 선택적 실행으로 변경
- [ ] **`patch_kimi_code.py` 정리**
  - AGENTS.md 방식이 안정적으로 작동하면 `patch_kimi_code.py`는 백업용으로만 유지하거나 제거

---

## 5. 현재 이미 설정되어 있는 부분들 (재확인 불필요)

| 항목 | 상태 | 파일/위치 |
|---|---|---|
| SSE 서버 설정 | ✅ | `.roo/mcp.json` |
| SSE 서버 설정 (프로젝트) | ✅ | `mcp_config.json` |
| VS Code 자동 시작 태스크 | ✅ | `.vscode/tasks.json` (`folderOpen`) |
| Windows 시작 프로그램 | ✅ | `%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/Crow_Memory_SSE.bat` |
| 강건한 시작 스크립트 | ✅ | `start_crow_sse.bat` (중복 방지 + lock 정리) |
| Crow 메모리 파일 | ✅ | `memory/crow.bin` (135MB) |
| SSE 서버 실행 중 | ✅ | `pythonw.exe` on port 9020 |

---

## 6. 참고: Kimi Code CLI 커스텀 에이전트 (`--agent-file`)

만약 `AGENTS.md` 외에 더 강력한 커스텀이 필요하다면, Kimi Code CLI는 **`--agent-file` 플래그**로 커스텀 에이전트 YAML을 로드할 수 있습니다.

```yaml
# crow-agent.yaml (예시)
version: 1
agent:
  extend: default
  system_prompt_args:
    ROLE_ADDITIONAL: |
      [Crow Memory 규칙 전체]
```

다만 이 방식은 VS Code 확장 프로그램에서 자동 선택되지 않으므로, **현재 단계에서는 `AGENTS.md` 방식으로 충분**합니다.

---

## 7. 핵심 요약

> **Zoo Code의 `custom_modes.yaml`은 Kimi Code CLI에서 작동하지 않습니다.**
> **대신 프로젝트 루트의 `AGENTS.md`에 Crow 규칙을 작성하면, Kimi Code CLI가 `${KIMI_AGENTS_MD}`로 매 세션 시작 시 자동 주입합니다.**
> **`patch_kimi_code.py`의 기능은 `AGENTS.md`로 완전히 대체 가능하며, 업데이트 내구성이 훨씬 뛰어납니다.**
