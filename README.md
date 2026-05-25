## Developer's Note / Philosophy

### 1. Why the Name "Crow"?
Crows use tools, recognize faces, possess long-term memory, and have the "situational awareness" to adapt to circumstances. "Crow Memory" was built upon this philosophy.

### 2. Why This Technology?
Transformer-based LLMs are frozen at training time — they cannot remember their users. Solutions based on RAG or SQLite accumulate information indefinitely and deliver 100% accurate recall like "notes in a notepad," but that is precisely the problem: it's a "jot it down and look it up later" approach. The human and animal brain doesn't work that way. Old habits fade, new patterns strengthen.

Forgetting is not a bug. Crow's fixed-size weight matrices and λ (decay rate) implement this "creative forgetting." By sacrificing 100% accurate recall, an AI that remembers through Crow responds with biases closer to your *present* self. The goal is low-latency, real-time synaptic plasticity — something that feels alive.

### 3. Who Is This For?
- **Anyone** who wants an AI that remembers their habits and adapts to them
- **Vibe coders** — those who want their AI to feel like a "colleague who knows them well"
- **Multi-agent users** — those who switch between multiple AI agents yet share a single `crow.bin` to maintain a consistent "AI that knows you"
- **Local-first advocates** — those who don't want to hand their personal data over to a cloud API

*"If you share this philosophy and want to join me on this journey, you are always welcome."*

---

# Crow Memory (까마귀 메모리)

> *"Crow remembers not the code, but the hand that wrote it."*

**Crow** is an external synaptic memory system for LLM-powered AI assistants. It plugs into any MCP-compatible coding agent (Claude, GPT, DeepSeek, Gemini, etc.) and stores your coding style, bug intuition, architectural preferences, and personal context as compressed weight matrices inside a fixed-size `crow.bin` file. Think of it as long-term muscle memory for your AI pair programmer.

---

## Quick Start

### 1. Requirements

- **Python 3.10+**
- **Zoo Code** or **Kimi Code** (or any MCP-compatible AI coding agent)
- Git (to clone the repository)

### 2. Install (One Command)

**Windows (PowerShell):**
```powershell
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
.\install.ps1
```

**macOS / Linux:**
```bash
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
python install.py
```

The installer automatically:
- Installs Python dependencies
- Initializes `crow.bin` (140MB fixed-size weight matrix)
- Creates `.roo/mcp.json` **and** `mcp_config.json` with SSE MCP server config — works for both Zoo Code and Kimi Code
- Creates `.vscode/tasks.json` — **auto-starts the SSE server when you open the workspace** (no manual commands needed)
- Creates a "Code + Crow Memory" custom mode with `allowedMcpServers` + AUTO-INGEST
- Registers a Startup `.bat` so the SSE server also starts with Windows
- Pre-authorizes all 10 Crow tools (`alwaysAllow`)

> ⚡ **That's it.** No manual server commands. The SSE server auto-starts when you open VS Code and **survives IDE restarts** (runs as a detached background process).

### How Auto-Start Works (v1.3.1)

[`start_crow_sse.bat`](start_crow_sse.bat) uses a three-layer strategy to eliminate `ECONNREFUSED` errors:

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| **Detached Process** | PowerShell `Start-Process -WindowStyle Hidden` | Server survives VS Code close; ready on next open |
| **Health Polling** | HTTP `GET /sse` with exponential backoff (0.5s→8s, max 30s) | Waits for server readiness before task exits |
| **Ready File** | `memory/.crow_ready` written by server on listen, deleted on shutdown | Alternative readiness signal for external scripts |

This means: **first open** → bat starts server detached + polls until ready. **Subsequent opens** → server already running → bat exits instantly → MCP connects immediately.

### 3. Restart & Switch Mode

1. **Restart Zoo Code / Kimi Code**
2. Open the `crowsmemory` workspace folder
3. Switch mode to **"Code + Crow Memory"**
4. Done. The SSE server auto-starts. Crow activates on every response.

### 4. Verify

Ask the AI:
> "Call the crow_diagnostics tool to check Crow memory status."

If Crow is alive, it will report register norms, update count, and value bank size.

### How Auto-Activation Works

Four layers ensure Crow is always active across all editors:

| Layer | Mechanism | Zoo Code | Kimi Code |
|-------|-----------|----------|-----------|
| **SSE Auto-Start** | [`.vscode/tasks.json`](.vscode/tasks.json) with `runOn: folderOpen` | ✅ | ✅ |
| **AGENTS.md** | Kimi Code CLI auto-injects via `${KIMI_AGENTS_MD}` | — | ✅ |
| **UNIVERSAL RECALL** | Custom mode system prompt (`custom_modes.yaml` for Zoo Code, [`AGENTS.md`](AGENTS.md) for Kimi Code) | ✅ | ✅ |
| **AUTO-INGEST** | Same as above — auto-detects preferences, corrections, context | ✅ | ✅ |

The installer copies [`system_prompt.example.md`](system_prompt.example.md) → `memory/system_prompt.md` with 3 pre-evolved rules. Kimi Code users also get [`AGENTS.md`](AGENTS.md) at the project root — the CLI auto-injects these rules every session, no patching required, survives updates permanently.

---

## How It Works

```
User query → LLM (via MCP over SSE)
                ↓ crow_recall("query", "style")
           Crow MCP Server (SSE, port 9020)
                ↓ encode() → Sᵀ @ q → nearest neighbor
           crow.bin (8-register weight matrix)
                ↓
           [User Bias] hints returned → injected into context
                ↓
           LLM generates response aligned with your preferences

Multi-client safe: One SSE server → many AI clients share one crow.bin
```

### The 8 Registers (Hybrid: Code + Life)

**Code Domain**

| Register | Dimensions | λ (EMA decay) | Capacity | Domain |
|----------|-----------|----------------|----------|--------|
| `style` | 4096×4096 | 0.9999 (~7K to halve) | ~2,000 patterns | Variable naming, comment style, folder aesthetics |
| `bug` | 2048×2048 | 0.9995 (~1.4K to halve) | ~800 patterns | Abstract bug families, not exact fixes |
| `arch` | 2048×2048 | 0.9995 | ~800 patterns | Early-return vs deep-nesting, error-handling philosophy |
| `context` | 2048×4096 | 0.9500 (~14 to halve) | ~400 patterns | Recent project context, active file context |

**Life Domain** (NEW)

| Register | Dimensions | λ (EMA decay) | Capacity | Domain |
|----------|-----------|----------------|----------|--------|
| `life_pref` | 4096×4096 | 0.9999 | ~2,000 | Personal taste, preferred environments, habits |
| `life_avoid` | 2048×2048 | 0.9995 | ~800 | Situations to avoid, dislikes, past mistakes |
| `life_phil` | 2048×2048 | 0.9995 | ~800 | Life philosophy, decision principles, values |
| `life_context` | 2048×4096 | 0.9500 | ~400 | Current plans, recent events, ongoing concerns |

> **Backward compatible**: `style`, `bug`, `arch`, `context` still work as before.

### How Crow Remembers (Without Being Asked)

The core challenge: LLMs don't spontaneously call tools. Crow solves this with four layers:

| Layer | Mechanism | When |
|-------|-----------|------|
| **AUTO-INGEST** | AI proactively evaluates every exchange and calls `crow_ingest` when it detects preferences, philosophy, corrections, or context. No "remember this" needed. | Every exchange |
| **MCP Prompt** | `crow_memory_bias` is auto-loaded by the LLM host at session start. No tool call needed. | Every session |
| **Auto-Inject** | [`crow_auto_inject.py`](crow_auto_inject.py) pre-generates a `[User Bias]` block for manual injection. | Pre-task hook |
| **Evolved Rules** | Statistically significant patterns promoted to `system_prompt.md` via HITL approval. | Permanent |

---

## 10 MCP Tools + 1 Script + 2 Prompts

### MCP Tools (auto-connected via Zoo Code)

| Tool | Description |
|------|-------------|
| `crow_recall` | Retrieve stored coding style / bug intuition |
| `crow_ingest` | Write new experience into synaptic memory |
| `crow_evolve_propose` | Propose permanent prompt rule from statistically significant patterns |
| `crow_diagnostics` | Memory state diagnostics |
| `crow_check_drift` | Detect memory drift (confidence too low) |
| `crow_ingest_from_build` | Auto-evaluate from build exit code + user edits |
| `crow_get_user_bias` | Generate `[User Bias]` block for prompt injection |
| `crow_manage_prompt` | Read / append to `system_prompt.md` |
| `crow_manage_backup` | Create / rotate / list / recover backups |
| `crow_project_info` | Multi-project memory isolation |

### Standalone Script

| Script | Description |
|--------|-------------|
| [`crow_auto_inject.py`](crow_auto_inject.py) | Generate `[User Bias]` block for manual prompt injection (no MCP needed) |

### MCP Prompts (Auto-Loaded by Host)

| Prompt | Description |
|--------|-------------|
| `crow_memory_bias` | Full context: evolved rules + recent memory hints. Loaded automatically at session start. |
| `crow_evolved_rules` | Permanent rules from `system_prompt.md`. |

---

## Sharing Policy (Important!)

| File | Share? | Reason |
|------|--------|--------|
| `crow_core.py` | ✅ Yes | Core engine (code) |
| `crow_mcp_server.py` | ✅ Yes | MCP server |
| `backup_manager.py` | ✅ Yes | Backup utility |
| `hitl_panel.html` | ✅ Yes | HITL UI |
| `requirements.txt` | ✅ Yes | Dependencies |
| `mcp_config.json` | ✅ Yes | Config example |
| **`memory/crow.bin`** | ❌ **No** | Your personal synaptic memories |
| **`memory/value_bank.json`** | ❌ **No** | Your experience data |
| **`memory/recall_stats.json`** | ❌ **No** | Your recall statistics |
| `system_prompt.example.md` | ✅ Yes | Evolved rules template (copied to memory/ on install) |
| `install.py` / `install.ps1` | ✅ Yes | One-command installers |
| **`memory/system_prompt.md`** | ❌ **No** | Your evolved rules (auto-copied from template) |

The included `.gitignore` automatically excludes all personal memory files.

---

## Multi-Client Setup (Zoo Code + Kimi Code + others)

### ✅ Default: Shared SSE Server (Auto-Start)

The installer configures everything for SSE mode by default. This is the only safe way to share `crow.bin` across multiple AI clients:

```
┌──────────────┐     ┌──────────────┐
│  Zoo Code    │     │  Kimi Code   │
│  (SSE MCP)   │     │  (SSE MCP)   │
└──────┬───────┘     └──────┬───────┘
       │                    │
       └────────┬───────────┘
                │ http://127.0.0.1:9020/sse
       ┌────────┴───────────┐
       │  Crow MCP Server   │
       │  (SSE, port 9020)  │
       │  Auto-started by   │
       │  .vscode/tasks.json│
       └────────┬───────────┘
                │
       ┌────────┴───────────┐
       │     crow.bin       │
       │  (single source)   │
       └────────────────────┘
```

**How it works:**
1. You open the `crowsmemory` workspace in **any** VS Code-based editor
2. [`.vscode/tasks.json`](.vscode/tasks.json) auto-runs [`start_crow_sse.bat`](start_crow_sse.bat) — if server is already running (detached from previous session), exits instantly; otherwise starts it detached + polls until ready
3. All AI clients (Zoo Code, Kimi Code, etc.) connect to `http://127.0.0.1:9020/sse`
4. The single SSE server serializes all reads/writes — **no race conditions, no data corruption**
5. The server process is **detached** from VS Code — closing the IDE does not kill it

### ⚠️ Warning: stdio Mode

If you manually switch to `"type": "stdio"` (command mode), each VS Code instance spawns its own `crow_mcp_server.py` process. **Two processes writing to the same `crow.bin` will cause silent data loss.** Only use stdio mode if you run exactly one AI client.

### Cross-Editor Compatibility

| Client | Config File | Auto-Generated by Installer |
|--------|-------------|----------------------------|
| Zoo Code | `.roo/mcp.json` | ✅ Yes |
| Kimi Code / VS Code | `mcp_config.json` | ✅ Yes |
| Cline / Roo Code | `.roo/mcp.json` | ✅ Yes |

---

## Troubleshooting

### Crow tools don't appear
- **Restart your editor** — MCP settings are read at startup only.
- First launch downloads `nomic-embed-text-v1.5` model (~30-60s). Subsequent launches are fast (~5-10s).
- Verify Python is in PATH: `python --version`
- Check the SSE server is running: visit `http://127.0.0.1:9020/` in a browser — should show "Crow Memory MCP SSE Server"
- Verify `.roo/mcp.json` (Zoo Code) or `mcp_config.json` (VS Code/Kimi Code) has `crow_memory` configured for SSE.

### ECONNREFUSED 127.0.0.1:9020 on VS Code restart
- This is a **race condition** fixed in v1.3.1. The SSE server now runs as a **detached process** that survives VS Code restarts.
- If you still see this: wait 10 seconds and re-run the `Crow SSE Server — Auto Start` task manually (`Ctrl+Shift+P` → `Tasks: Run Task`).
- Verify the server is alive: visit `http://127.0.0.1:9020/` in a browser.

### SSE server not auto-starting
- Verify [`.vscode/tasks.json`](.vscode/tasks.json) exists in the workspace root
- Run manually once: `python crow_mcp_server.py --transport dual --port 9020`
- Check `sse_server.log` for error messages
- Ensure no other process is using port 9020: `netstat -ano | findstr :9020`

### Port 9020 already in use
- [`start_crow_sse.bat`](start_crow_sse.bat) detects this and skips duplicate starts automatically
- To force restart: kill the process on port 9020, delete `memory\crow.bin.lock`, then re-open the workspace

### Recall returns only "Few memories stored yet"
- Normal! Crow needs 20-30+ ingestions before meaningful hints emerge. Keep coding.
- Enable AUTO-INGEST by switching to "Code + Crow Memory" mode — the AI will learn proactively.

### PermissionError / lock file issues
- Delete stale lock: `del memory\crow.bin.lock` (Windows) or `rm memory/crow.bin.lock` (macOS/Linux)
- [`start_crow_sse.bat`](start_crow_sse.bat) automatically cleans stale locks before starting

---

## Architecture

See [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md) for the full technical specification including mathematical foundations, Hebbian EMA update rules, spectral clipping, and capacity bounds.

---

## License

MIT License — see [`LICENSE`](LICENSE) for details.

---

*Crow Memory v1.3.1 — May 2026*
*Co-designed by Stefano,Kim & AI*
