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
- **Zoo Code** (VS Code extension)
- An **MCP-compatible AI coding agent** (Zoo Code, Claude Code, Cline, GitHub Copilot, etc.)

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
- Initializes `crow.bin`
- Creates `.roo/mcp.json` with Crow MCP server config (project-level)
- Creates a "Code + Crow Memory" custom mode with `allowedMcpServers` + AUTO-INGEST
- Pre-authorizes all 10 Crow tools (`alwaysAllow`)

### 3. Restart & Switch Mode

1. **Restart Zoo Code**
2. Switch mode to **"Code + Crow Memory"**
3. Done. Crow now auto-activates on every response.

### 4. Verify

Ask the AI:
> "Call the crow_diagnostics tool to check Crow memory status."

If Crow is alive, it will report register norms, update count, and value bank size.

### How Auto-Activation Works

The installer created a Zoo Code custom mode that includes this instruction in the system prompt:

```
UNIVERSAL RECALL (MANDATORY): Before EVERY response, call
crow_recall(domain="all"). Use the hints to personalize your response.
AUTO-INGEST (MANDATORY): After EVERY response, call crow_ingest.
```

The installer also copies [`system_prompt.example.md`](system_prompt.example.md) → `memory/system_prompt.md` with 3 pre-evolved rules. This means the LLM is **always aware** of Crow and calls it automatically for every response — coding, writing, or conversation — no manual tool invocation needed.

---

## How It Works

```
User query → LLM (via MCP)
                ↓ crow_recall("query", "style")
           Crow MCP Server (stdio)
                ↓ encode() → Sᵀ @ q → nearest neighbor
           crow.bin (8-register weight matrix)
                ↓
           [User Bias] hints returned → injected into context
                ↓
           LLM generates response aligned with your preferences
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

### ⚠️ Critical: One crow.bin = One MCP Server

If you use Crow with **multiple AI clients simultaneously** (e.g., Zoo Code + Kimi Code), never let each client spawn its own `crow_mcp_server.py` process. Two processes writing to the same `crow.bin` will cause **silent data loss** (last-write-wins race condition).

### ✅ Safe: Shared SSE Server

Run **one** SSE server and point all clients to it:

```bash
# Start the shared SSE server (once)
python crow_mcp_server.py --transport sse --port 9020
```

Then configure all clients to use the same URL:

```json
{
  "type": "sse",
  "url": "http://127.0.0.1:9020/sse",
  "disabled": false,
  "alwaysAllow": ["crow_recall", "crow_ingest", ...]
}
```

The server serializes all requests internally — no data corruption, no race conditions.

### Single-Client Setup

If you only use one client (e.g., only Zoo Code), you can use the SSE mode (default, as generated by the installer). For advanced users who prefer Zoo Code to spawn the server automatically, switch `.roo/mcp.json` to `command` mode (see [`mcp_config.json`](mcp_config.json) for the stdio config template).

---

## Troubleshooting

### Crow tools don't appear in Zoo Code
- **Restart Zoo Code** — MCP settings are read at startup only.
- First launch downloads `nomic-embed-text-v1.5` model (~30-60s). Subsequent launches are fast (~5-10s).
- Verify Python is in PATH: `python --version`
- Check that `.roo/mcp.json` exists in your project root with `crow_memory` configured.
- Verify `custom_modes.yaml` has `allowedMcpServers: ["crow_memory"]` for your mode.
- Check that `alwaysAllow` is configured — open Zoo Code MCP settings, click `crow_memory`, ensure tools are toggled ON.

### Windows: MCP server silent / no response
- `crow_mcp_server.py` v1.1+ includes `WindowsSelectorEventLoopPolicy` patch.
- As an alternative, use SSE transport: `python crow_mcp_server.py --transport sse --port 9020` then set `"type": "sse", "url": "http://127.0.0.1:9020/sse"` in `.roo/mcp.json`.

### Recall returns only "Few memories stored yet"
- Normal! Crow needs 20-30+ ingestions before meaningful hints emerge. Keep coding.
- Enable AUTO-INGEST by switching to "Code + Crow Memory" mode — the AI will learn proactively.

### PermissionError on Windows
- `crow_core.py` v1.0+ includes automatic retry with exponential backoff.

---

## Architecture

See [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md) for the full technical specification including mathematical foundations, Hebbian EMA update rules, spectral clipping, and capacity bounds.

---

## License

MIT License — see [`LICENSE`](LICENSE) for details.

---

*Crow Memory v1.2.1 — May 2026*
*Co-designed by Stefano,Kim & AI*
