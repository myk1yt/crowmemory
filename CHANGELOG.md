# Changelog

All notable changes to Crow Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.1] — 2026-05-25

### Fixed
- **`ECONNREFUSED 127.0.0.1:9020` on VS Code restart**: Root cause — race condition between MCP client connecting and SSE server starting. MCP client reads `mcp_config.json` and connects immediately on workspace open, but the `folderOpen` task that launches `crow_mcp_server.py` takes 3–10 seconds (Python imports + `crow.bin` load + SentenceTransformer model warm-up). The server process was also a child of VS Code's task (`start /b`), meaning it died when VS Code closed, forcing a cold start every time.
  - **Fix 1 — Detached process launch**: [`start_crow_sse.bat`](start_crow_sse.bat) now uses PowerShell `Start-Process -WindowStyle Hidden` instead of `start /b`. The Python server is fully detached from VS Code's process tree and survives IDE restarts.
  - **Fix 2 — Health polling with exponential backoff**: Bat file polls `http://127.0.0.1:9020/sse` with backoff (0.5s → 1s → 2s → 4s → 8s cap, max 30s) to confirm server readiness before exiting.
  - **Fix 3 — Ready file signal**: [`crow_mcp_server.py`](crow_mcp_server.py) now writes `memory/.crow_ready` when the server starts listening, deleted on shutdown. External scripts can poll this file as an alternative to HTTP health checks.
  - **Result**: On first VS Code open after system boot, the bat file starts the server detached and waits for readiness. On subsequent VS Code restarts, the server is already running → bat file exits instantly → MCP client connects without error.

### Changed
- **`install.py` / `install.ps1` bat template**: Generated `start_crow_sse.bat` now includes detached launch + health polling logic. Transport changed from `--transport sse` to `--transport dual` (SSE + Streamable HTTP).

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
