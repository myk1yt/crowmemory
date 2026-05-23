# Crow Memory (까마귀 메모리)

> *"Crow remembers not the code, but the hand that wrote it."*

**Crow** is an external synaptic memory chip for AI coding agents (DeepSeek V4 Pro). It stores your coding style, bug intuition, and architectural preferences as compressed weight matrices inside a fixed-size `crow.bin` file, and retrieves them via natural language queries.

---

## Quick Start

### 1. Requirements

- **Python 3.10+**
- **Zoo Code** (VS Code extension)
- **DeepSeek V4 Pro API** access

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
User query → DeepSeek V4 Pro
                ↓ crow_recall("query", "style")
           Crow MCP Server (stdio)
                ↓ encode() → Sᵀ @ q → nearest neighbor
           crow.bin (4-register weight matrix)
                ↓
           [User Bias] hints returned → prepended to system prompt
                ↓
           DeepSeek V4 Pro generates code in your style
```

### The 4 Registers

| Register | Dimensions | λ (EMA decay) | Capacity | Domain |
|----------|-----------|----------------|----------|--------|
| `style` | 4096×4096 | 0.9999 (~7K to halve) | ~2,000 patterns | Variable naming, comment style, folder aesthetics |
| `bug` | 2048×2048 | 0.9995 (~1.4K to halve) | ~800 patterns | Abstract bug families, not exact fixes |
| `arch` | 2048×2048 | 0.9995 | ~800 patterns | Early-return vs deep-nesting, error-handling philosophy |
| `context` | 2048×4096 | 0.9500 (~14 to halve) | ~400 patterns | Recent conversation topics, active file context |

---

## 10 MCP Tools

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
*Co-designed by User & DeepSeek V4 Pro*
