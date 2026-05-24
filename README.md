# Crow Memory (까마귀 메모리)

> *"Crow remembers not the code, but the hand that wrote it."*

**Crow** is an external synaptic memory system for LLM-powered AI assistants. It plugs into any MCP-compatible coding agent (Claude, GPT, DeepSeek, Gemini, etc.) and stores your coding style, bug intuition, architectural preferences, and personal context as compressed weight matrices inside a fixed-size `crow.bin` file. Think of it as long-term muscle memory for your AI pair programmer.

---

## Quick Start

### 1. Requirements

- **Python 3.10+**
- **Zoo Code** (VS Code extension)
- An **MCP-compatible AI coding agent** (Zoo Code, Claude Code, Cline, GitHub Copilot, etc.)

### 2. Installation

```bash
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
pip install -r requirements.txt
```

### 3. Connect to Zoo Code

Open Zoo Code's MCP settings file:
- Path: `%APPDATA%/Code/User/globalStorage/zoocodeorganization.zoo-code/settings/mcp_settings.json`

Add the following inside `mcpServers`:

```json
{
  "mcpServers": {
    "crow_memory": {
      "command": "python",
      "args": [
        "/absolute/path/to/crow_mcp_server.py",
        "--state",
        "/absolute/path/to/memory/crow.bin"
      ]
    }
  }
}
```

Restart Zoo Code. Crow activates automatically.

### 4. Verify

In Zoo Code, ask the AI:
> "Call the crow_diagnostics tool to check Crow memory status."

If Crow is alive, diagnostics will be returned.

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

The core challenge: LLMs don't spontaneously call tools. Crow solves this with three layers:

| Layer | Mechanism | When |
|-------|-----------|------|
| **MCP Prompt** | `crow_memory_bias` is auto-loaded by the LLM host at session start. No tool call needed. | Every session |
| **Auto-Inject** | [`crow_auto_inject.py`](crow_auto_inject.py) pre-generates a `[User Bias]` block for manual injection. | Pre-task hook |
| **Evolved Rules** | Statistically significant patterns promoted to `system_prompt.md` via HITL approval. | Permanent |

---

## 11 MCP Tools + 2 Prompts

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
| `crow_auto_inject` | *(Script)* Generate `[User Bias]` block for manual prompt injection |

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
| `test_*.py` | ✅ Yes | Tests |
| `requirements.txt` | ✅ Yes | Dependencies |
| `mcp_config.json` | ✅ Yes | Config example |
| **`memory/crow.bin`** | ❌ **No** | Your personal synaptic memories |
| **`memory/value_bank.json`** | ❌ **No** | Your experience data |
| **`memory/recall_stats.json`** | ❌ **No** | Your recall statistics |
| **`memory/system_prompt.md`** | ❌ **No** | Your evolved rules |

The included `.gitignore` automatically excludes all personal memory files.

---

## Troubleshooting

### Crow tools don't appear
- Restart Zoo Code
- First launch downloads `nomic-embed-text-v1.5` model (~30-60s). Subsequent launches are fast (~5-10s).
- Verify Python is in PATH: `python --version`

### Recall returns only "Few memories stored yet"
- Normal! Crow needs 20-30+ ingestions before meaningful hints emerge. Keep coding.

### PermissionError on Windows
- `crow_core.py` v1.0+ includes automatic retry with exponential backoff.

---

## Architecture

See [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md) for the full technical specification including mathematical foundations, Hebbian EMA update rules, spectral clipping, and capacity bounds.

---

## License

MIT License — see [`LICENSE`](LICENSE) for details.

---

*Crow Memory v1.0 — May 2026*  
*Co-designed by Stefano,Kim & AI*
