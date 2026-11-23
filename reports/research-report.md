# Crow Memory — Serverless Plugin, Hook, CLI & `stdio` Architecture Research Report

**Date**: 2026-11-24  
**Workspace**: `D:\OneDrive\Projects\Crow Memory`  
**Target Clients**: Antigravity (`agy` CLI 1.5.15 / IDE / Desktop), Kimi Code CLI (`kimi` 2.7.2), Claude Code, Cursor  

---

## 1. Executive Summary

Crow Memory currently runs as a persistent dual-port Python HTTP server (`SSE :9020` + `Streamable HTTP :9021`) managed by Windows Task Scheduler (`CrowMemoryAuto`), PowerShell detached launchers (`start_crow_sse.bat`), watchdog scripts (`watch_crow_sse.bat`), and manual `AGENTS.md` prompt instructions.

**Root-Cause Finding**: Crow Memory did **not** choose a persistent server arbitrarily—two coupled implementation choices in `crow_core.py` forced it:
1. **Heavy ML Cold-Start**: Loading `torch>=2.0.0`, `sentence-transformers>=2.7.0`, and `nomic-ai/nomic-embed-text-v1.5` (`crow_core.py#L224-L231`), plus deserializing the `140.5 MB` `crow.bin` (`safetensors`) and `4.08 MB` `value_bank.json`, takes multiple seconds on cold start (`crow_mcp_server.py#L268`, `start_crow_sse.bat#L79-L108`).
2. **Exclusive Single-Writer Advisory Lock (`crow.bin.lock`)**: `CrowMemory.__init__` (`crow_core.py#L157-L161`) acquires an exclusive PID lock. When Crow v1.4.0 used `stdio` MCP (`CHANGELOG.md#L92`), opening two IDE/CLI sessions concurrently crashed the second process with `RuntimeError`, forcing the migration to a singleton HTTP daemon in v1.4.1.

**Strategic Conclusion**: By decoupling **fast operational recall/ingest** (SQLite WAL + FTS5 + `crow_sanitize.py` + `system_prompt.md`, **<15ms cold start**, zero external dependencies, multi-process concurrency-safe) from **optional/offline synaptic weight consolidation** (or lightweight ONNX embeddings), Crow Memory can become a **100% serverless, zero-daemon, zero-port plugin** across Antigravity, Kimi Code CLI, Claude Code, and Cursor. Better still, **Lifecycle Hooks** (`SessionStart` / `PreInvocation` / `PostToolUse` / `Stop`) eliminate the biggest behavioral flaw of MCP-only memory: instead of begging the LLM to remember to call `crow_recall`, hooks deterministically inject `[User Bias]` and automatically ingest build/test outcomes with zero wasted tool-call round-trips.

---

## 2. Current Architecture Audit & Friction Analysis

### 2.1 Dependency & Storage Footprint

| Component | Path / Source | Observed Reality | Impact on Serverless Execution |
| :--- | :--- | :--- | :--- |
| **Python Dependencies** | [`requirements.txt#L1-L10`](file:///D:/OneDrive/Projects/Crow%20Memory/requirements.txt#L1-L10) | `numpy`, `torch`, `safetensors`, `sentence-transformers`, `faiss-cpu`, `einops`, `mcp==2.1.1`, `uvicorn`, `PyYAML` | Heavy (~GB-scale `.venv`, multi-second `torch` import). Cannot run synchronously inside a per-turn hook (`PreInvocation`). |
| **Embedding Model** | [`crow_core.py#L224-L231`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L224-L231) | Lazy-loads `SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)`; prewarmed in daemon thread [`crow_mcp_server.py#L268`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_mcp_server.py#L268) | Blocks cold CLI/stdio startup for several seconds unless replaced or deferred. |
| **Synaptic Matrix (`crow.bin`)** | [`memory/crow.bin`](file:///D:/OneDrive/Projects/Crow%20Memory/memory/crow.bin), [`crow_core.py#L120-L131`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L120-L131) | `140,518,352` bytes (`~134 MiB`) `safetensors` float16 tensors (8 registers up to `4096x4096` + `proj_W` `4096x768`) | Whole-file atomic rewrite on every `ingest()` ([`crow_core.py#L794-L815`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L794-L815)); requires exclusive PID lock (`crow.bin.lock`, [`crow_core.py#L42-L83`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L42-L83)). |
| **Value Bank (`value_bank.json`)** | [`memory/value_bank.json`](file:///D:/OneDrive/Projects/Crow%20Memory/memory/value_bank.json), [`crow_core.py#L103`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_core.py#L103) | `4,082,781` bytes (`~3.89 MiB`), capped at `VALUE_BANK_MAX = 500` entries (each holds `key`, `value`, `vector_b64`, `register`, `timestamp`, `importance`, `ingest_count`, `project`) | Only ~500 text records! Without the `4096`-dim `vector_b64` blobs, the actual text knowledge base is `<250 KB`. |
| **Evolved Rules (`system_prompt.md`)** | [`memory/system_prompt.md`](file:///D:/OneDrive/Projects/Crow%20Memory/memory/system_prompt.md) | `2,034` bytes (`24` lines) | Pure Markdown; directly readable in `<1 ms` by any hook or CLI. |
| **Sanitizer (`crow_sanitize.py`)** | [`crow_sanitize.py#L1-L132`](file:///D:/OneDrive/Projects/Crow%20Memory/crow_sanitize.py#L1-L132) | Pure stdlib (`os`, `re`) — zero ML imports | Already decoupled and ready for zero-dependency CLI/hook use. |

### 2.2 Why the Daemon Setup Causes Operational Friction

1. **Multi-Layer Windows Plumbing**: Requires `install.py` / `install.ps1` (`install.py#L220-L250`) to register Task Scheduler `CrowMemoryAuto`, launch detached PowerShell (`start_crow_sse.bat#L74`), clean stale `.crow_ready` and `crow.bin.lock` (`start_crow_sse.bat#L43-L56`), taskkill zombie listeners (`start_crow_sse.bat#L68-L71`), and poll `/health` up to ~55s.
2. **Transport Fragmentation Across Agents**:
   - **Kimi Code CLI** failed to recognize MCP SSE `event: endpoint` ([`AGENTS.md#L9`](file:///D:/OneDrive/Projects/Crow%20Memory/AGENTS.md#L9)), requiring dual-port `--transport dual --port 9020 --http-port 9021` (`~/.kimi-code/mcp.json` points to `http://127.0.0.1:9021/mcp`).
   - **Antigravity** explicitly dropped legacy HTTP+SSE (MCP 2024-11-05) and supports only **Stdio** or **Streamable HTTP** (`mcp_servers.md#L68-L71`).
   - **Observed Failure Mode** ([`scripts/ingest_session_result.py#L9-L18`](file:///D:/OneDrive/Projects/Crow%20Memory/scripts/ingest_session_result.py#L9-L18)): Stale system-python processes lingered on ports, SSE hung silently while `/mcp` reported healthy, and clients silently fell back to skipping recall (`~/.kimi-code/AGENTS.md#L61`).
3. **LLM Compliance Tax**: Even when the server is healthy, `AGENTS.md` and `system_prompt.md` rely on prompting the LLM to *remember* to call `crow_recall` before every response and `crow_ingest` afterward—adding latency, token cost, and non-deterministic compliance.

---

## 3. Target Agent Capabilities Matrix (Verified)

| Capability | Antigravity (`agy` 1.5.15) | Kimi Code CLI (`kimi` 2.7.2) | Claude Code | Cursor |
| :--- | :--- | :--- | :--- | :--- |
| **Plugin Manifest** | `plugin.json` in `~/.gemini/config/plugins/<name>/` or `.agents/plugins/<name>/` ([`plugins.md#L16-L37`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/plugins.md#L16-L37)) | Plugin directory / `/plugins install` (`kimi.plugin.json` / `plugin.json`) | `.claude-plugin/plugin.json` | `.cursor/` project/user directories (no unified plugin manifest; rules/hooks/mcp files) |
| **Lifecycle Hooks** | **Root `hooks.json`** ([`plugins.md#L62-L70`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/plugins.md#L62-L70)): `SessionStart`, `PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse`, `Stop` ([`hooks.md#L85-L106`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md#L85-L106)) | **`[[hooks]]` in `~/.kimi-code/config.toml`** (verified locally in `config.toml`): `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop` | `hooks/hooks.json`: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop` | `.cursor/hooks.json` (`version: 1`): `sessionStart`, `beforeSubmitPrompt`, `beforeShellExecution`, `afterFileEdit`, `stop` |
| **Context Injection via Hook** | `stdout` JSON: `{"injectSteps": [{"systemMessage": {"systemMessage": "..."}}]}` ([`hooks.md#L279-L331`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md#L279-L331)) | `stdout` text/JSON on `SessionStart` / `UserPromptSubmit` | `stdout` text or JSON `hookSpecificOutput.additionalContext` | `stdout` JSON (`additional_context` / `continue`) |
| **`stdio` MCP (Client Auto-Spawns)** | `mcp_config.json` (`command`, `args`, `env`) ([`mcp_servers.md#L31-L57`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/mcp_servers.md#L31-L57)) | `~/.kimi-code/mcp.json` (`command`, `args`, `env`) | `.mcp.json` / plugin `.mcp.json` (`command`, `args`, `env`) | `.cursor/mcp.json` (`command`, `args`, `env`) |
| **Skills & Rules** | `skills/<name>/SKILL.md` + `rules/AGENTS.md` ([`plugins.md#L20-L24`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/plugins.md#L20-L24)) | `~/.kimi-code/skills/*/SKILL.md` (or `--skills-dir`) + `~/.kimi-code/AGENTS.md` | `skills/*/SKILL.md` + `CLAUDE.md` | `skills/*/SKILL.md` + `.cursor/rules/*.mdc` |
| **CLI Validation** | `agy plugin validate [target] [--strict]` | `kimi doctor` | `claude plugin validate` | N/A |

> [!IMPORTANT]
> **Antigravity Native Plugin Gotcha** ([`plugins.md#L61-L70`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/plugins.md#L61-L70)): Native plugins (directories with `plugin.json`) do **not** run extension staging and strictly load `hooks.json` from the **plugin root** (`<plugin_dir>/hooks.json`), whereas Claude Code places it in `hooks/hooks.json`. Also, Antigravity hooks run via `cmd /c` on Windows and `sh -c` on Unix with CWD = the `hooks.json` directory ([`hooks.md#L129-L131`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md#L129-L131)) — avoid `./` in commands on Windows `cmd /c`; use `python scripts/crow_cli.py ...` (no leading `./`) for cross-platform compatibility.

---

## 4. Comparative Architecture of Serverless / Zero-Daemon Alternatives

### Option A: Pure Hook + CLI + Skill Plugin (Zero-MCP, Zero-Server)

**Mechanism**: Completely removes `crow_mcp_server.py` (no ports, no Task Scheduler, no `.bat`, no MCP schema tokens).
- **Read path (Automatic)**: `SessionStart` injects evolved `RULE:` lines from `system_prompt.md` + top `[User Bias]` context; `PreInvocation` / `UserPromptSubmit` runs a `<15ms` query against SQLite FTS5 / `value_bank` using `lastUserInput` and injects matching hints into `systemMessage` (deduplicated per turn via `invocationNum == 1` or prompt hash).
- **Write path (Automatic + Skill)**:
  - `PostToolUse` (matcher `run_command` / shell execution) automatically captures build/test failures or successes (`error` field in Antigravity [`hooks.md#L260`](file:///C:/Users/k1yt/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md#L260)) and ingests them silently with zero LLM involvement!
  - `SKILL.md` / `AGENTS.md` instructs the LLM to run `crow ingest --register <reg> --polarity <p> --key "..." --value "..."` via its normal shell tool only when recording explicit user preferences or architectural decisions.

**Pros**:
- **Zero persistent processes, zero ports, zero MCP handshake bugs** (follows the same *"Zero-MCP Self-Contained"* philosophy as [`designer/plugin.json`](file:///C:/Users/k1yt/.gemini/config/plugins/designer/plugin.json)).
- **Deterministic Recall**: Memory is guaranteed to be injected before the model thinks—zero LLM forgetfulness and saves 1 tool-call round-trip per session.
- **Lowest Context Overhead**: Saves ~500–1,000 tokens of MCP tool descriptions on every prompt.

**Cons**:
- If keeping `nomic-embed-text-v1.5` (`torch`), pure ephemeral CLI cannot run semantic vector encoding in `<15ms`. Must migrate hot-path retrieval/storage to **SQLite WAL + FTS5** (or lightweight ONNX/TF-IDF) — *or* queue writes to SQLite and run heavy `crow.bin` Hebbian consolidation asynchronously/on-demand.
- Explicit `crow ingest` relies on shell tool permission (`run_command`), which may prompt for user approval unless allowlisted (`PreToolUse` hook can auto-return `{"decision": "allow"}` for `crow ingest`!).

---

### Option B: Client-Managed `stdio` MCP + SQLite WAL (Auto-Spawned, Zero Manual Server)

**Mechanism**: Keep the 3 MCP tools (`crow_recall`, `crow_ingest`, `crow_admin`), but drop SSE/HTTP (`9020`/`9021`) completely. Every client (`mcp_config.json`, `~/.kimi-code/mcp.json`, `.mcp.json`, `.cursor/mcp.json`) configures `"command": "python", "args": [".../crow_mcp_server.py", "--transport", "stdio"]`. The client spawns and terminates the process automatically.

**Why v1.4.0 `stdio` failed & what MUST change for `stdio` to work**:
1. **Replace `crow.bin.lock` exclusive lock with SQLite WAL (`crow.db`)**: Multiple IDE/CLI windows each spawn their own `stdio` child process. SQLite with `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` allows unlimited concurrent readers and serialized non-crashing writers across Antigravity, Kimi Code, Claude Code, and Cursor simultaneously.
2. **Eliminate PyTorch 5s Cold-Start**: Either:
   - **B1 (Pure-Stdlib / SQLite FTS5 + BM25 + EMA Decay)**: `<50ms` `stdio` startup, zero ML deps (`requirements.txt` shrinks to `mcp` only—or zero external deps if pure JSON-RPC stdio in 150 lines!).
   - **B2 (FastEmbed / ONNX Quantized Embeddings)**: Replace `torch` + `sentence-transformers` (`~2 GB`) with `onnxruntime` + quantized `all-MiniLM-L6-v2` (~23 MB, ~200–400ms lazy load inside the long-lived `stdio` session—fast enough because a `stdio` MCP process lives for the entire chat session!).

**Pros**:
- Preserves the exact 3-tool MCP contract (`crow_recall`, `crow_ingest`, `crow_admin`) and silent tool UX (`alwaysAllow` without shell command permission prompts).
- Client manages process lifecycle automatically—no Task Scheduler, no `start_crow_sse.bat`, no port conflicts.

**Cons**:
- Still relies on the LLM deciding to invoke `crow_recall` unless paired with a `SessionStart` hook (Option C).
- Each open IDE/CLI window spawns one `stdio` process (acceptable if memory footprint is ~15–40 MB without PyTorch, vs ~1.2 GB with PyTorch!).

---

### Option C: Hybrid Universal Architecture — Core SQLite WAL + Lifecycle Hooks + Thin `stdio` / CLI Adapters (Recommended)

```text
+-----------------------------------------------------------------------------+
|                    AI CODING AGENTS (Zero Manual Server)                    |
|                                                                             |
|  [Antigravity Plugin]   [Kimi Code CLI]    [Claude Code]     [Cursor]       |
|  plugin.json            config.toml        .claude-plugin/   .cursor/       |
|  hooks.json (root)      [[hooks]]          hooks/hooks.json  hooks.json     |
|  rules/AGENTS.md        AGENTS.md          CLAUDE.md         rules/*.mdc    |
|  skills/*/SKILL.md      skills/*/SKILL.md  skills/*/SKILL.md skills/*/      |
|  mcp_config.json(stdio) mcp.json (stdio)   .mcp.json (stdio) mcp.json(stdio)|
+-----------+--------------------+------------------+---------------+---------+
            | (1) Hooks: SessionStart / PreInvocation / PostToolUse (<15ms)
            | (2) Optional MCP: stdio JSON-RPC (no ports, auto-spawned)
            v
+-----------------------------------------------------------------------------+
|           crow_cli.py  (Pure Python 3.11+ Stdlib — Zero Pip Deps!)          |
|  Subcommands: hook session-start | hook pre-prompt | hook post-tool |       |
|               recall | ingest | admin | mcp-stdio (zero-dep JSON-RPC!)      |
+-----------------------------------+-----------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------------+
|        ~/.crow-memory/  (Global Shared Store — Multi-Client Safe)           |
|  - crow.db          (SQLite WAL + FTS5 + Register EMA Decay + Polarity)     |
|  - system_prompt.md (Evolved permanent RULE: directives)                    |
|  - crow.bin         (Optional legacy/cold archive; synced via `crow sync`)  |
+-----------------------------------------------------------------------------+
```

**Why Option C is the Optimal Solution**:
1. **Zero Pip Dependencies in Hot Path**: Python 3.11+ ships with `sqlite3` (with FTS5), `json`, `re`, `math`, `hashlib`, `argparse`, and `sys.stdin/stdout`! Even the **`stdio` MCP server** can be implemented in ~120 lines of pure Python stdlib JSON-RPC 2.0 over `stdin`/`stdout` (eliminating `mcp==2.1.1`, `pydantic`, `uvicorn`, `torch`, `numpy`, `faiss-cpu`, and `.venv` entirely for runtime!).
2. **True Multi-Agent Concurrency**: `crow.db` in SQLite `WAL` mode (`busy_timeout=5000`) lets Antigravity, Kimi Code CLI, Claude Code, and Cursor read and write concurrently without `crow.bin.lock` errors or port `9020`/`9021` collisions.
3. **Preserves Crow's "Creative Forgetting" Physics**: Crow's core philosophy (`README.md#L7-L9`, `CROW_MEMORY_ARCHITECTURE.md#L35`) is **not** infinite RAG—it is fixed-capacity, decay-weighted inductive bias across 8 registers (`style`, `bug`, `arch`, `context`, `life_pref`, `life_avoid`, `life_phil`, `life_context`). In SQLite, every entry stores `register`, `polarity`, `importance`, `ingest_count`, `project`, `created_at`, `last_recalled_at`, and `updated_at`. At recall time, effective score is computed analytically as:
   $$\text{score} = \text{BM25\_norm} \times \lambda^{\Delta t} \times \min(1 + 0.12 \ln(\text{importance} + 1), 1.15) \times \text{project\_boost}$$
   Combined with `crow_sanitize.py` (`scrub_text`), `VALUE_BANK_MAX` (or per-register soft caps with importance-based eviction), and `evolve_propose` SQL aggregation, you keep **100% of Crow's behavioral semantics** in `<15ms`!
4. **Optional Semantic Upgrade Path (Zero-Server)**: If vector similarity beyond FTS5 + synonym/tag matching is ever missed, a 4-line adapter can optionally use either (a) a pre-built ONNX `all-MiniLM-L6-v2` quantized model (~23 MB, no `torch`), or (b) `crow sync` batch command that consolidates `crow.db` into `crow.bin` offline using the existing `crow_core.py` engine.

---

## 5. Concrete Migration Blueprint & Exact Config Schemas

### 5.1 Proposed Unified Repository Layout

```text
crow-memory/
├── core/
│   ├── crow_db.py             # Pure stdlib SQLite WAL + FTS5 + EMA decay + 8-register engine
│   ├── crow_sanitize.py       # Existing stdlib sanitizer (moved/shared unchanged)
│   ├── crow_mcp_stdio.py      # Zero-dep JSON-RPC 2.0 MCP stdio server (3 tools, 2 prompts)
│   ├── crow_cli.py            # CLI + Hook adapter (--format agy|claude|kimi|cursor|text)
│   └── migrate_from_v1.py     # One-shot importer: memory/value_bank.json + recall_stats.json + system_prompt.md -> ~/.crow-memory/crow.db
├── adapters/
│   ├── antigravity/           # Deployable directly to ~/.gemini/config/plugins/crow_memory/
│   │   ├── plugin.json
│   │   ├── hooks.json         # MUST be at plugin root for Antigravity native plugins
│   │   ├── mcp_config.json    # Optional stdio MCP (if tool-based ingest is desired)
│   │   ├── rules/
│   │   │   └── AGENTS.md
│   │   └── skills/
│   │       └── crow-memory/
│   │           └── SKILL.md
│   ├── claude-code/           # Deployable as Claude Code plugin
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   ├── hooks/
│   │   │   └── hooks.json
│   │   ├── .mcp.json
│   │   └── skills/crow-memory/SKILL.md
│   ├── kimi-code/             # Fragments/installer for ~/.kimi-code/
│   │   ├── hooks.toml.snippet # [[hooks]] entries for ~/.kimi-code/config.toml
│   │   ├── mcp.json.snippet   # stdio entry for ~/.kimi-code/mcp.json
│   │   ├── AGENTS.crow.md
│   │   └── skills/crow-memory/SKILL.md
│   └── cursor/                # Deployable to .cursor/ or ~/.cursor/
│       ├── hooks.json
│       ├── mcp.json
│       └── rules/crow-memory.mdc
└── scripts/
    └── install_plugin.py      # Pure stdlib installer: migrates data -> ~/.crow-memory/ & links/copies adapters
```

---

### 5.2 Adapter 1: Antigravity (`agy`) Native Plugin

Path: `~/.gemini/config/plugins/crow_memory/` (or `.agents/plugins/crow_memory/` per project).

#### `plugin.json`
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

#### `hooks.json` (Must be at plugin root per `agy-customizations/docs/plugins.md#L62-L70`)
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
*Implementation notes for Antigravity hooks (`hooks.md#L129-L349`)*:
- Antigravity executes `command` in the directory containing `hooks.json` (`PLUGIN_ROOT`), via `cmd /c` on Windows and `sh -c` on Unix. Keep `core/` (or relative path / `%PLUGIN_ROOT%` wrapper) reachable from the plugin root without leading `./`.
- `SessionStart` & `PreInvocation` read JSON from `stdin` (`conversationId`, `workspacePaths`, `lastUserInput`, `invocationNum`, `cwd`) and print to `stdout`:
  ```json
  {
    "injectSteps": [
      {
        "systemMessage": {
          "systemMessage": "[User Bias -- Crow Memory]\n- [style] Prefer early returns..."
        }
      }
    ]
  }
  ```
- **Deduplication guard**: In `PreInvocation`, only inject when `invocationNum == 1` (or when `sha256(conversationId + lastUserInput)` hasn't been seen in that session's temp state) so multi-step tool loops don't inject duplicate bias messages on steps 2..N.
- `PostToolUse` outputs `{}` (`hooks.md#L265`) and silently records build/test command pass/fail (`error` field present -> negative polarity `-0.5`, absent on known build/test commands -> positive `+1.0`).

#### Optional `mcp_config.json` (Client-managed `stdio`, zero daemon)
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
*Validation*: Run `agy plugin validate ~/.gemini/config/plugins/crow_memory --strict`.

---

### 5.3 Adapter 2: Kimi Code CLI (`~/.kimi-code/`)

#### Option 1: Native `[[hooks]]` in `~/.kimi-code/config.toml` (Matches existing `ensure-exa-proxy.js` pattern)
```toml
[[hooks]]
event = "SessionStart"
command = "python C:\\Users\\k1yt\\crow-memory\\core\\crow_cli.py hook session-start --format text"
timeout = 10

[[hooks]]
event = "UserPromptSubmit"
command = "python C:\\Users\\k1yt\\crow-memory\\core\\crow_cli.py hook pre-invocation --format text"
timeout = 10

[[hooks]]
event = "PostToolUse"
matcher = "Shell"
command = "python C:\\Users\\k1yt\\crow-memory\\core\\crow_cli.py hook post-tool --format text"
timeout = 10
```

#### Option 2: `stdio` MCP in `~/.kimi-code/mcp.json` (Replaces `http://127.0.0.1:9021/mcp`)
```json
{
  "mcpServers": {
    "crow-memory": {
      "command": "python",
      "args": ["D:\\OneDrive\\Projects\\Crow Memory\\core\\crow_mcp_stdio.py"],
      "env": {
        "PYTHONUTF8": "1",
        "CROW_HOME": "C:\\Users\\k1yt\\.crow-memory"
      }
    }
  }
}
```
*(No `transport: http`, no port `9021`, no `start_crow_sse.bat` needed; Kimi spawns and reaps the process automatically.)*

---

### 5.4 Adapter 3: Claude Code Plugin

```text
crow-memory-claude/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
├── .mcp.json
└── skills/crow-memory/SKILL.md
```

#### `hooks/hooks.json`
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

---

### 5.5 Adapter 4: Cursor (`.cursor/`)

#### `.cursor/hooks.json`
```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": "python ~/.crow-memory/bin/crow_cli.py hook session-start --format cursor"
      }
    ],
    "beforeSubmitPrompt": [
      {
        "command": "python ~/.crow-memory/bin/crow_cli.py hook pre-invocation --format cursor"
      }
    ],
    "afterShellExecution": [
      {
        "command": "python ~/.crow-memory/bin/crow_cli.py hook post-tool --format cursor"
      }
    ]
  }
}
```

#### `.cursor/mcp.json` (Optional `stdio`)
```json
{
  "mcpServers": {
    "crow_memory": {
      "command": "python",
      "args": ["~/.crow-memory/bin/crow_mcp_stdio.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

---

## 6. SQLite WAL Schema & Migration Specification (`crow_db.py`)

To preserve 100% compatibility with existing Crow Memory data (`memory/value_bank.json`, `memory/recall_stats.json`, `memory/system_prompt.md`), the new pure-stdlib core uses:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    register        TEXT NOT NULL,          -- style, bug, arch, context, life_*
    key_text        TEXT NOT NULL,
    value_text      TEXT NOT NULL,
    project         TEXT,                   -- NULL = global
    polarity        REAL NOT NULL,          -- clamped [-2.0, 2.0] with NEG_DAMPEN_BY_REGISTER
    importance      REAL NOT NULL DEFAULT 1.0,
    ingest_count    INTEGER NOT NULL DEFAULT 1,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    last_recalled_at REAL DEFAULT 0.0,
    UNIQUE(register, key_text)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    key_text,
    value_text,
    content='memories',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS recall_stats (
    register        TEXT NOT NULL,
    query_hash      TEXT NOT NULL,
    occurrences     INTEGER NOT NULL DEFAULT 0,
    total_conf      REAL NOT NULL DEFAULT 0.0,
    avg_conf        REAL NOT NULL DEFAULT 0.0,
    last_hints_json TEXT NOT NULL DEFAULT '[]',
    last_seen       REAL NOT NULL,
    PRIMARY KEY(register, query_hash)
);
```

### Migration Steps (Zero Data Loss)
1. **One-time import (`migrate_from_v1.py`)**: Reads `memory/value_bank.json` (`500` entries), `memory/recall_stats.json`, and copies `memory/system_prompt.md` into `~/.crow-memory/` (`crow.db` + `system_prompt.md`). `memory/crow.bin` remains untouched as archive (or optional offline vector sync target).
2. **Keep `crow_sanitize.py` verbatim**: All ingest paths pass through `scrub_text()` before writing to `memories`.
3. **Preserve 3-tool + 2-prompt surface in `crow_mcp_stdio.py`**: Same `crow_recall`, `crow_ingest`, `crow_admin` schemas (`crow_mcp_server.py#L274-L433`) so existing `AGENTS.md` / `SKILL.md` prompts continue working without breaking mental models.
4. **Retire Windows Task Scheduler & `.bat` launchers**: Replace `install.py` Step 3–5 (`CrowMemoryAuto`, `start_crow_sse.bat`, `watch_crow_sse.bat`) with `install_plugin.py` (registers Antigravity plugin, updates `~/.kimi-code/mcp.json` or `config.toml`, removes stale `CrowMemoryAuto` scheduled task if desired).

---

## 7. Phased Implementation Roadmap

1. **Phase 1 — Pure-Stdlib Core (`crow_db.py` + `migrate_from_v1.py`)**:
   - Build SQLite WAL + FTS5 + EMA-decay scoring engine with unit tests verifying parity with `crow_sanitize`, project-boost (`×1.05`), negative damping (`bug`/`life_avoid` = `1.0`), and `evolve_propose`.
   - Benchmark cold-start latency: target `<20ms` for `recall` and `ingest`.
2. **Phase 2 — Zero-Dep `stdio` MCP & Hook CLI (`crow_cli.py` + `crow_mcp_stdio.py`)**:
   - Implement `hook session-start`, `hook pre-invocation` (with turn deduplication), and `hook post-tool` (automatic build/test outcome ingest) outputting agent-specific JSON (`--format agy|claude|kimi|cursor`).
   - Implement pure-stdlib JSON-RPC 2.0 `stdio` MCP server exposing `crow_recall`, `crow_ingest`, `crow_admin`.
3. **Phase 3 — Antigravity & Kimi Code Plugin Deployment**:
   - Package `adapters/antigravity/` into `~/.gemini/config/plugins/crow_memory/` and verify with `agy plugin validate --strict`.
   - Switch `~/.kimi-code/mcp.json` from `http://127.0.0.1:9021/mcp` to `stdio` (or `[[hooks]]` in `config.toml`) and verify concurrent Antigravity + Kimi Code sessions without lock errors.
4. **Phase 4 — Legacy Cleanup (Optional)**:
   - Keep `crow_core.py` / `crow_mcp_server.py` available under `legacy/` or behind an `--engine synaptic` flag for users who specifically want offline `crow.bin` matrix consolidation (`crow sync`).
