# Changelog

All notable changes to Crow Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.1] — 2026-06-03

### Fixed
- **Roo Code Lock Contention**: Changed Roo Code MCP configuration from stdio (`{"command": "python"}`) to SSE (`{"url": "http://127.0.0.1:9020/sse"}`) in `install.py` and `install.ps1` to prevent multiple processes from locking `crow.bin`.
- **Health Check Timeout**: Fixed the health check polling URL in `start_crow_sse.bat` to ping the root `/` endpoint instead of `/sse` which previously caused stream timeouts.
- **Data Loss Risk**: Improved safety in `install.ps1` when merging Zoo Code custom modes; if parsing fails, the installer now securely appends to the file instead of overwriting it.
- **Cross-Platform Bug**: Wrapped `.bat` execution in `install.py` with an OS check to prevent crashes on Mac/Linux environments.

## [1.4.0] — 2026-06-03

### Added
- **Silent Mode for Tools**: Added a new rule to system prompts (`system_prompt.example.md`, `system_prompt.example/ko.md`, `system_prompt.example/en.md`) to suppress verbose explanations when AI uses `crow_recall` and `crow_ingest` tools. The AI will now only output a concise `🧠 **Crow Memory** - 기억을 떠올려보는 중...` (or `기억을 기록하는 중...`) message, keeping the UI clean and less noisy.
- **i18n Support Restored**: Restored i18n support modules that were removed in the previous commit, but enforced English for prompt templates and configurations to ensure consistency and prevent AI drift.

## [1.3.7] — 2026-06-01

### Added
- **`.roomodes`** — Zoo Code 프로젝트 수준 `orchestrator-crow` 모드 설정 추가 (git 추적됨)
- **`.github/FUNDING.yml`** — Gumroad 커스텀 펀딩 링크
- **`Logo/`** — 프로젝트 로고 이미지 (2개 PNG 파일)
- **Gumroad Sponsor 배지** — README 상단에 [![Gumroad Sponsor](https://img.shields.io/badge/Gumroad-Sponsor-FF90A0?style=for-the-badge&logo=gumroad&logoColor=white)](https://teamsunplaza.gumroad.com/l/crowmemory) 배지 추가
- **`$null`** 가비지 파일 git 추적에서 제거

### Changed
- **`AGENTS.md`** — Kimi Code MCP 설정 SSE → Streamable HTTP 마이그레이션:
  - 설정 파일 경로: `mcp_settings.json` → `~/.kimi/mcp.json`
  - 전송 방식: `"type": "sse"` → `"transport": "http"`, URL 포트 9020→9021
  - 서버 실행: `--transport sse --port 9020` → `--transport dual --port 9020 --http-port 9021`
  - Kimi Code SSE 미지원 버그 경고 추가
- **`README.md`** — 다음 내용 업데이트:
  - 프로젝트 제목: `Crow Memory (까마귀 메모리)` → `Crow Memory`
  - 다이어그램: SSE 전용 → 듀얼 모드(SSE + Streamable HTTP) 아키텍처 다이어그램
  - 멀티 클라이언트 테이블: Zoo Code/Cline `.roo/mcp.json` → `mcp_settings.json` (global), Kimi Code 행 추가
  - Kimi Code 섹션: 상세한 Streamable HTTP 설정 가이드 추가 (JSON 예제, 듀얼 모드 실행 명령어, SSE 버그 경고)
  - "Commercial Services / 맞춤형 개발 문의" 섹션 추가 (이미 v1.3.6에 있음)
- **`custom_modes.example.yaml`** — 다음 내용 업데이트:
  - Zoo Code ARRAY 형식 중요 주석 추가
  - `browse` 그룹 권한 제거
  - 주석 위치 조정 (섹션 헤더를 `customModes:` 상단으로 이동)
- **README.md 버전 문자열**: `v1.3.6` → `v1.3.7`
- **버전 참조 일관성**: 모든 파일의 v1.3.6 참조를 v1.3.7로 업데이트

### Fixed
- **v1.3.4 태그 위치 오류**: v1.3.4 태그가 HEAD(`bd67634`)를 가리키는 문제 — v1.3.4는 v1.3.5/v1.3.6보다 이전 버전이어야 함 (별도 git 명령어로 처리)

---

## [2026-05-28] — Kimi Code Integration Restored

### Added
- **`AGENTS.md`** — Single-file Kimi Code Crow Memory integration (replaces deleted `patch_kimi_code.py`, `crow_auto_inject.py`, and old `AGENTS.md`)
  - Session-start `crow_recall` + session-end `crow_ingest` rules
  - Full 10-tool reference with register guide
  - Designed for `${KIMI_AGENTS_MD}` auto-injection — equivalent to Zoo Code's `orchestrator-crow` mode

### Changed
- `README.md` — Kimi Code integration guide linking to `AGENTS.md`

---

## [1.3.6] — 2026-05-28

### Removed
- **Kimi Code 지원 완전 제거** — Zoo Code 전용 프로젝트로 전환
- `AGENTS.md` — Kimi Code CLI 자동 주입 파일 (Zoo Code는 custom_modes.example.yaml 사용)
- `patch_kimi_code.py` — Kimi Code CLI 패치 스크립트
- `mcp_config.json` — `.roo/mcp.json`과 100% 중복되는 범용 MCP 설정
- `journal.md` — 개인 개발 일지 (공개 저장소 부적합)
- `verify_fixes.py` — 내부 테스트 스크립트
- `crow_auto_inject.py` — MCP 서버 도구로 대체된 중복 CLI 도구
- `memory/project_pytest_demo/` — 빈 테스트 디렉토리

### Changed
- `install.ps1` / `install.py` — Kimi Code 관련 Step 4.5 전체 제거, mcp_config.json 생성 제거, Step 카운트 7→5
- `README.md` — 모든 "Kimi Code" → "Zoo Code" 대체, Multi-Client 섹션 단순화
- `CROW_MEMORY_ARCHITECTURE.md` — Kimi Code + Streamable HTTP 참조 제거
- `.vscode/tasks.json` — detail 문자열 Zoo Code 전용으로 수정

---

## [1.3.5] — 2026-05-28

### Added
- `orchestrator-crow` 커스텀 모드 지원 — 작업 위임 중심 워크플로우에 Crow Memory 통합
- `.zoo/` 디렉토리 구조: `config.json`, `config.schema.json`
- `.roo/mcp.schema.json` — MCP 설정 JSON Schema 검증
- `templates/` 디렉토리: `zoo-config.json`, `.roo/mcp.json` 프로젝트 템플릿

### Changed
- `custom_modes.example.yaml`에 `orchestrator-crow` 모드 예시 추가
- `AGENTS.md`에 `orchestrator-crow` 모드 활성화 가이드 추가
- `README.md`에 `.zoo/` 설정 구조 및 `orchestrator-crow` 모드 안내 추가

---

## [1.3.4] — 2026-05-26

### Fixed
- **`crow_recall(register="all")` caused "Unknown register: all" error**: [`crow_mcp_server.py`](crow_mcp_server.py) `_recall` handler did not handle `register="all"`. When passed, it was forwarded to [`crow_core.py`](crow_core.py) `recall()` which rejected it. Now `register="all"` is converted to `register=None`, forcing domain-based multi-register query (same behavior as `domain="all"` without register).

---

## [1.3.3] — 2026-05-26

### Changed — "Important memories survive" design philosophy
- **Value Bank: FIFO → Importance-based priority queue**: [`crow_core.py`](crow_core.py) `_append_value_bank` no longer drops the oldest entry. Instead, it drops the entry with the lowest `importance` score, preserving frequently-ingested / high-polarity memories. Duplicate keys accumulate importance on re-ingest.
- **Recall Stats: 7-day hard TTL → dual-threshold with recall frequency**: [`crow_core.py`](crow_core.py) `_track_recall` now uses **30-day hard TTL** (remove regardless) + **7-day soft TTL** (remove only if recalled < 3 times). Frequently recalled patterns survive longer. Per-register max entries now evict least-frequently-recalled first.
- **Recall visibility: fixed threshold → importance-weighted adaptive**: [`crow_core.py`](crow_core.py) `_nearest_hints` no longer uses a fixed `sim > 0.3` threshold. High-importance entries get an effective similarity boost (`importance_boost = 1 + 0.12 * log(importance + 1)`) and a lower visibility floor (`sim > 0.15` when `importance > 5`).
- **Ingest strengthens, not just adds**: Re-ingesting the same key now accumulates `importance` and increments `ingest_count` instead of creating a duplicate entry.

---

## [1.3.2] — 2026-05-26

### Fixed
- **`crow_recall(domain="all")` silently queries only `style` register**: [`crow_core.py`](crow_core.py) `DOMAINS` dictionary was missing the `"all"` key. When `_recall` handler received `domain="all"`, it fell back to `DOMAINS.get("all", ["style"])` → returned only `style` hints instead of all 8 registers.
  - **Fix**: Added `"all"` key to `DOMAINS` mapping to all 8 registers (`style`, `bug`, `arch`, `context`, `life_pref`, `life_avoid`, `life_phil`, `life_context`).
- **`_recall` handler no default domain**: When `domain` argument was omitted, `args.get("domain")` returned `None`, skipping the multi-register path and falling back to `register or "style"` — only 1 register queried.
  - **Fix**: Changed to `args.get("domain", "all")` so domain defaults to `"all"`, automatically querying all registers even when no arguments are passed beyond `query`.

### Changed
- **`crow_recall` tool definition**: `register` enum now includes `"all"`, allowing callers to explicitly specify `register="all"` for multi-register query.
- **Domain fallback hardened**: `DOMAINS.get(domain, ["style"])` → `DOMAINS.get(domain, DOMAINS["all"])` so unknown domains fall back to all registers instead of just `style`.

### Changed
- **`code-crow` mode definition**: Added `description` field to both [`custom_modes.example.yaml`](custom_modes.example.yaml) and [`install.py`](install.py) `YAML_MODE` template. The description explains the difference between Code and Code+Crow modes: Code+Crow auto-recalls style/preferences and learns from feedback; plain Code mode provides unbiased, one-shot answers without memory influence.

### Documentation
- **AGENTS.md**: UNIVERSAL RECALL rule now explicitly states that `domain="all"` queries all **8 registers**.
- **system_prompt.example.md**: Same clarification added to the evolved Korean RULE.
- **install.py**: Both `customInstructions`, `YAML_MODE`, and `agents_md_content` templates updated with the 8-register clarification and mode description.
- **patch_kimi_code.py**: `CROW_SECTION` template updated with the same clarification.
- **custom_modes.example.yaml**: Added `description` field to `code-crow` mode explaining when to use it vs. plain Code mode.

---

## [1.3.1] — 2026-05-25

### Fixed
- **`ECONNREFUSED 127.0.0.1:9020` on VS Code restart**: Race condition between MCP client connecting and SSE server starting. MCP client reads `mcp_config.json` and connects immediately on workspace open, but the `folderOpen` task that launches `crow_mcp_server.py` takes 3–10 seconds. Server was a child of VS Code's task (`start /b`), dying with the IDE.
  - **Fix 1 — Detached process launch**: [`start_crow_sse.bat`](start_crow_sse.bat) uses PowerShell `Start-Process -WindowStyle Hidden`. Server survives VS Code restarts.
  - **Fix 2 — Health polling with exponential backoff**: Bat file polls `/sse` with backoff (500ms→8s, max 30s).
  - **Fix 3 — Ready file signal**: [`crow_mcp_server.py`](crow_mcp_server.py) writes `memory/.crow_ready` on listen, deleted on shutdown.
- **Hotfix — `NameError: name 'os' is not defined`**: `_write_ready_file()` called `os.getpid()` but `import os` was missing from [`crow_mcp_server.py`](crow_mcp_server.py). Added import.
- **Hotfix — Batch `SLEEP` decimal syntax error**: `SLEEP=0.5` caused `'. was unexpected at this time'` in batch parser and `timeout /t` failure. Changed to integer milliseconds (500, 1000, 2000, 4000, 8000).
- **Hotfix — cp949 `UnicodeEncodeError` on Korean Windows**: MCP responses used `json.dumps(ensure_ascii=False)` which emitted raw Unicode characters (Korean text, checkmarks) that Kimi Code's cp949 codec could not encode. Changed to `ensure_ascii=True` in all MCP response handlers. Also cleaned a self-referential value_bank entry that stored a `✓` character in a "cp949 fix" memory.
- **Encoding hardening**: Added `PYTHONUTF8=1` environment variable and `-X utf8` Python flag to [`start_crow_sse.bat`](start_crow_sse.bat) and installer templates. [`crow_mcp_server.py`](crow_mcp_server.py) enhanced to set `PYTHONIOENCODING`/`PYTHONUTF8` at module level before any imports.

### Changed
- **`install.py` / `install.ps1` bat template**: Includes detached launch + health polling + `PYTHONUTF8=1` + `-X utf8`. Transport changed from `--transport sse` to `--transport dual` (SSE + Streamable HTTP).
- **Kimi Code transport**: Changed from SSE (port 9020, `"type": "sse"`) to Streamable HTTP (port 9021, `"type": "http"`) in `~/.kimi/mcp.json` template. Kimi Code CLI has a known bug where it does not recognize the MCP SSE `event: endpoint` handshake message, causing infinite "Testing..." hang. Streamable HTTP avoids this. Both transports share the same `crow.bin` via the single `dual`-mode server process.
- **`.gitignore`**: Added `.crow_ready`, `crow.bin.lock`, `*.log` patterns.

### Removed
- **`DEEPSEEK_HANDOFF.md`**: Superseded by `AGENTS.md`.
- **`$null`**: Garbage artifact from previous sessions.
- **`sse_test.log`**: Test log artifact.

### Documentation
- **README.md**: Added "How Auto-Start Works" section, `UnicodeEncodeError` troubleshooting with Windows UTF-8 setup guide, affected languages table (Korean cp949, Japanese cp932, Chinese cp936/cp950, Thai cp874, etc.).
- **CROW_MEMORY_ARCHITECTURE.md**: Updated topology diagram (detached process, ready file, health polling), component responsibilities table, version 1.3→1.3.1.

---

## [1.3.0] — 2026-05-25

### Added
- **`AGENTS.md` — Kimi Code CLI official support**: The official Kimi Code CLI mechanism (`${KIMI_AGENTS_MD}`) is now used instead of `patch_kimi_code.py` hacks. `AGENTS.md` at project root auto-injects Crow rules into every Kimi Code session. Survives CLI updates permanently.
- **`~/.kimi/mcp.json` generation**: Installers now write the Kimi Code CLI standard MCP config (`~/.kimi/mcp.json`) with SSE endpoint. Kimi Code finds Crow automatically regardless of project.
- **`.vscode/tasks.json` auto-generated**: SSE server now auto-starts on workspace open via `runOn: folderOpen` task. No manual server commands needed — clone, install, open, done.
- **`.vscode/tasks.json` + `.roo/mcp.json` + `AGENTS.md` shared on GitHub**: `.gitignore` updated to allow essential config files so new users get plug-and-play experience.
- **Robust `start_crow_sse.bat`**: Port check (skip if already running), stale lock cleanup (PID verification), start verification. Used by both `.vscode/tasks.json` and Windows Startup.

### Changed
- **SSE mode is now the one and only default**: Installers no longer generate stdio config. SSE is required for multi-client safety.
- **Kimi Code architecture**: `patch_kimi_code.py` → `AGENTS.md` (official, update-proof). `patch_kimi_code.py` kept as optional fallback for CLI < v1.2.
- **Kimi Code `custom_modes.yaml` removed from install**: Kimi Code CLI does not support `custom_modes.yaml` (Zoo Code only). Replaced with `AGENTS.md` + `~/.kimi/mcp.json`.
- **Startup `.bat` is now a copy of `start_crow_sse.bat`**: Single source of truth.
- **`install.py` / `install.ps1` step count**: 5 → 7 (Step 3.5: `.vscode/tasks.json`, Step 4.5: Kimi Code AGENTS.md + ~/.kimi/mcp.json).

### Fixed
- **SSE server not surviving VS Code restart**: Root cause — auto-start was Windows-boot-only. Now `.vscode/tasks.json` handles workspace-open trigger.
- **`.gitignore` blocking essential config files**: `.vscode/tasks.json`, `.roo/mcp.json`, and `AGENTS.md` now correctly shared.
- **Kimi Code: `custom_modes.yaml` silently ineffective**: Removed. Kimi Code now uses `AGENTS.md` (official) + `~/.kimi/mcp.json` (standard).

---

## [1.2.1] — 2026-05-25

### Fixed
- **Lock acquisition silently ignored**: `__init__` now raises `RuntimeError` when `_acquire_file_lock()` returns `False` (another live process holds the lock).
- **`_encode_cache` class variable → instance-level true LRU**: Changed from class-level dict (shared across all `CrowMemory` instances, FIFO eviction) to per-instance `OrderedDict` with `move_to_end()` for genuine LRU behavior.
- **`_track_recall()` O(n) overhead**: Lazy pruning — 7-day TTL cleanup and `recall_stats.json` persist now runs at most once per hour instead of every recall call. Added per-register max 1000 entries.
- **`spectral_reset()` LinAlgError silently passed**: Now falls back to per-element norm clipping (same as `_maybe_clip`).
- **`encode()` unbounded input**: Truncates text to 2000 chars before SentenceTransformer encoding.
- **`requirements.txt` missing uvicorn + PyYAML**: Added `uvicorn>=0.29.0` (required for SSE transport) and `PyYAML>=6.0` (required for `install.py` custom_modes merge).

### Changed
- **Architecture doc §2.2**: "4 weight matrices" → "8 weight matrices".
- **Architecture doc §7.2**: "5 consecutive calls" → accurate description of `min_low_confidence_count` behavior.
- **README Single-Client Setup**: Clarified SSE is default, stdio is advanced option.

---

## [1.2.0] — 2026-05-25

### Added
- **File locking**: Advisory lock (`crow.bin.lock` + PID check) prevents silent data corruption from concurrent MCP server processes.
- **Encoder pre-warm**: Background thread loads SentenceTransformer at server startup, eliminating 30-60s cold-start latency on first request.
- **LRU embedding cache**: 1024-entry cache in `encode()` avoids re-encoding identical/similar strings.
- **Backup auto-recovery**: Corrupted `crow.bin` (`ValueError`) now attempts recovery from the most recent `.bak.*` file instead of silently initializing blank.
- **`patch_kimi_code.py` append mode**: Can now inject Crow Memory into clean Kimi Code installations (no existing Crow section required).

### Changed
- **SVD clipping fallback**: On `LinAlgError`, falls back to per-element norm clipping instead of silently passing (prevented singular value explosion).
- **`check_drift()` parameter**: Renamed `consecutive_calls` → `min_low_confidence_count` to match actual behavior.
- **`_track_recall()` hash**: Replaced non-portable `hash(query)` with stable `hashlib.md5(query.encode())`.
- **`install.py` / `install.ps1`**: Now generate `Crow_Memory_SSE.bat` with absolute paths (fixes auto-start failure when copied to Startup folder).
- **`install.py` custom mode merge**: Preserves existing user modes instead of overwriting `custom_modes.yaml`.
- **`install.ps1` step numbering**: Unified to `[1/5]`–`[5/5]`.
- **Architecture doc**: Updated to 8-register specification (code + life domains), bumped to v1.2.

### Fixed
- **`crow_core.py` docstring**: Class now correctly states "8 semantic registers".
- **`crow_mcp_server.py` docstring**: Corrected from "9 tools" to "10 tools" (includes `crow_project_info`).
- **Dead code removal**: Removed unused `ORIGINAL_CROW_MARKER` from `patch_kimi_code.py`.

---

## [1.1.1] — 2026-05-25

### Changed
- **Generic LLM terminology**: Replaced all vendor-specific references ("DeepSeek V4 Pro", "DeepSeek V4", "V4") in [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md) and [`journal.md`](journal.md) with generic expressions ("the LLM", "the agent", "MCP-compatible LLM"). Crow Memory is provider-agnostic by design — the architecture now reflects that.
- **Docstring fix**: [`crow_core.py`](crow_core.py) now correctly states "8-register" instead of the old "4-register".

### Fixed
- **Architecture document vendor lock-in**: The architecture spec previously assumed DeepSeek V4 Pro as the sole inference backend. Now correctly describes any MCP-compatible LLM.

---

## [1.1.0] — 2026-05-24

### Fixed
- **Windows MCP stdio silent failure**: `crow_mcp_server.py` now uses `WindowsSelectorEventLoopPolicy` instead of default `ProactorEventLoop` which doesn't support pipe I/O on Windows. ([`6d987d9`](https://github.com/myk1yt/crowmemory/commit/6d987d9))
- **Missing `cwd` and `PYTHONUNBUFFERED` in MCP config**: Both `install.py` and `install.ps1` now include `cwd` (working directory) and `env.PYTHONUNBUFFERED=1` in the generated config. ([`6d987d9`](https://github.com/myk1yt/crowmemory/commit/6d987d9), [`d7a41ba`](https://github.com/myk1yt/crowmemory/commit/d7a41ba))
- **Zoo Code MCP integration**: Discovered Zoo Code uses `.roo/mcp.json` (not `mcp_settings.json`) for project-level MCP config, and `custom_modes.yaml` requires `allowedMcpServers` field (per [PR #75](https://github.com/Zoo-Code-Org/Zoo-Code/pull/75)) to expose MCP tools to the AI. Installers now generate `.roo/mcp.json` with `disabled: false`.

### Added
- **AUTO-INGEST (Proactive Memory)**: A new system prompt rule that instructs the AI to proactively evaluate every exchange and call `crow_ingest` when it detects user preferences, philosophy, corrections, context, or frustration — no explicit "remember this" command needed. Includes a Polarity Guide for auto-determining reinforcement strength. Applied to all 4 mode definition files. ([`d3eddd7`](https://github.com/myk1yt/crowmemory/commit/d3eddd7))
- **`alwaysAllow` in all config templates**: The 10 Crow MCP tools are now pre-authorized in `install.py`, `install.ps1`, and `mcp_config.json`, so the AI can call them without user approval prompts. This is essential for AUTO-INGEST to work silently. ([`d3c6f47`](https://github.com/myk1yt/crowmemory/commit/d3c6f47))
- **SSE HTTP transport**: `crow_mcp_server.py` now supports `--transport sse --port 9020` for HTTP-based MCP connections via `SseServerTransport`. Raw ASGI fallback when Starlette is unavailable.
- **`allowedMcpServers` in custom mode config**: Added `allowedMcpServers: ["crow_memory"]` to all `custom_modes.yaml` templates so Zoo Code exposes Crow tools to the AI.
- **`patch_kimi_code.py`**: Patching tool for Kimi Code CLI to inject Crow Memory auto-ingest rules into its system prompt.
- **`CHANGELOG.md`**: This file.
- **Multi-Client Safety Guide**: Documented in README — one `crow.bin` must only be accessed by a single MCP server process. Use SSE shared server for multiple AI clients.

### Security
- **Concurrency warning**: Simultaneous writes to `crow.bin` from multiple processes cause silent data loss (last-write-wins). Single SSE server serializes all access safely.

### Changed
- Updated `custom_modes.yaml` (active Zoo Code config) with AUTO-INGEST rule, polarity guide, and `allowedMcpServers`.
- Updated `custom_modes.example.yaml` with AUTO-INGEST rule and `allowedMcpServers` for new installations.
- Installers now generate `.roo/mcp.json` (project-level) instead of `mcp_settings.json` (global).
- Bumped version to v1.1.0.

---

## [1.0.0] — 2026-05-24

### Added
- **Core Engine** (`crow_core.py`): 8-register synaptic weight matrix (code: style/bug/arch/context, life: life_pref/life_avoid/life_phil/life_context) with Hebbian EMA updates, spectral clipping, FAISS acceleration, drift detection, backup rotation, multi-project isolation, and system prompt evolution.
- **MCP Server** (`crow_mcp_server.py`): 10 MCP tools + 2 MCP prompts via stdio transport.
- **Build Hook** (`crow_ingest_from_build`): Auto-determine polarity from build exit code + user edit status.
- **Auto-Inject** (`crow_auto_inject.py`): Generate `[User Bias]` block for manual prompt injection without MCP.
- **HITL Panel** (`hitl_panel.html`): Web UI for human-in-the-loop approval of evolved prompt rules.
- **Backup Manager** (`backup_manager.py`): CLI utility for backup creation, rotation, listing, and drift recovery.
- **Installers**: `install.py` (cross-platform) and `install.ps1` (Windows) for one-command setup.
- **Test Suite**: 37/37 tests passing across all 4 phases.
- **Documentation**: `CROW_MEMORY_ARCHITECTURE.md`, `README.md`, `journal.md`.
