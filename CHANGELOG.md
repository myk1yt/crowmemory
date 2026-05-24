# Changelog

All notable changes to Crow Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
