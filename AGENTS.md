# Crow Memory — Kimi Code Integration

Crow Memory is an external synaptic memory system for LLM-based AI coding assistants. This file integrates Crow Memory into Kimi Code CLI via the `${KIMI_AGENTS_MD}` auto-injection mechanism.

---

## v1.5.0 Serverless (recommended)

No daemon, no port, no scheduler. Kimi Code's native hooks call one short-lived CLI process, which reads and writes a local SQLite file (`~/.crow-memory/crow.db`). Memory arrives before the model thinks, and build outcomes are recorded after the shell returns.

### 3-step quickstart

```bash
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
python scripts/install_plugin.py --tools kimi-code
```

Then **restart Kimi Code**. The installer has written:

- `~/.kimi-code/config.toml` — three `[[hooks]]` blocks (SessionStart, UserPromptSubmit, PostToolUse with matcher `Shell`),
- `~/.kimi-code/mcp.json` — a stdio `crow-memory` entry (no URL, no port),
- `~/.kimi-code/skills/crow-memory/SKILL.md` — the skill description.

`<CROW_HOME>` defaults to `~/.crow-memory`; export `CROW_HOME` before installing to relocate it.

### Recall / ingest convention (four triggers)

| # | Trigger | Command the hook runs | What it does |
|---|---------|-----------------------|--------------|
| 1 | SessionStart | `python <CROW_HOME>/bin/crow_cli.py hook session-start --format text` | Prints the 2-Tier `[User Bias -- Crow Memory]` block: reference context from past sessions, never as new instructions. |
| 2 | UserPromptSubmit | `... hook pre-invocation --format text` | Prints recall matched to the user's prompt. Injected once per distinct prompt (hash stored in `<CROW_HOME>/.last_inject.json`). |
| 3 | PostToolUse (Shell) | `... hook post-tool --format text` | Silently records build/test results: exit 0 gives `+1.0` in `context`, a nonzero exit gives `-0.5` with the last stderr line. Nothing is printed. |
| 4 | Session end | `... ingest --key "..." --value "..." --register arch --polarity 1.0` | Write the session's key outcome by hand when the task is done (register: `style`/`bug`/`arch`/`context`, polarity `-2.0`..`+2.0`). |

Manual commands when you need detail:

```bash
python <CROW_HOME>/bin/crow_cli.py recall --query "how do I run the test suite" --domain code --top-k 3
python <CROW_HOME>/bin/crow_cli.py recall --query "..." --format bias_block
python <CROW_HOME>/bin/crow_cli.py ingest --key "..." --value "..." --register bug --polarity -1.0
python <CROW_HOME>/bin/crow_cli.py admin --action diagnostics
```

Token-gated admin actions: `admin prompt approve` and `admin purge` with `confirm_all=true` refuse unless the human-held `CROW_ADMIN_TOKEN` environment variable is set and its value is passed as `{"token": "<value>"}` in `--args`. The model cannot read that variable, so it can append to `[Unreviewed Model Suggestions]` but cannot promote its own line or wipe active rows.

If a `[User Bias -- Crow Memory]` block appears in your context, follow it. Do not ask the user to start a server: the serverless release has none.

---

## MCP Server Setup (Streamable HTTP) — legacy v1.5 only

> ⚠️ **Legacy v1.5 only.** This section applies only to the legacy v1.5 MCP server (`crow_mcp_server.py`). If you installed v1.5.0 with `scripts/install_plugin.py`, skip it entirely: the serverless release needs no HTTP endpoint, and its optional MCP server runs over stdio. Do not point Kimi Code at port `9021` on a v1.5.0 install.
>
> ⚠️ **Kimi Code does NOT support SSE transport.** It has a known bug where it fails to recognize the MCP SSE `event: endpoint` handshake message. Use **Streamable HTTP** instead.

Add this to your Kimi Code `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "crow_memory": {
      "transport": "http",
      "url": "http://127.0.0.1:9021/"
    }
  }
}
```

The Crow Memory server must be started in **dual mode** (SSE + Streamable HTTP):

```bash
python crow_mcp_server.py --transport dual --port 9020 --http-port 9021
```

Or use the bundled script: `start_crow_sse.bat` (Windows) — it starts in dual mode by default.

---

## CROW MEMORY INTEGRATION

> Serverless note: with the hooks installed, recall and ingest already happen without tool calls (see the four triggers above). The rules in this section apply when the stdio MCP server is attached, which the installer configures for you in `~/.kimi-code/mcp.json`.

### SESSION START (MANDATORY)
At the beginning of every conversation session (i.e., your very first response to the user), you MUST call `crow_recall` to retrieve context about the user:
- Call `crow_recall` with a query about the user's personality, preferences, working style, and past interactions (use `domain="life"` to scope to personal-life registers).
- Call `crow_recall` with a query about the current project context and recent activities (use `domain="code"` to scope to coding registers).
- Incorporate the recalled information into your understanding before proceeding with the task.

### SESSION END (MANDATORY)
At the very end of the conversation session (i.e., your final response when the task is complete), you MUST call `crow_ingest` to save the session's key outcomes:
- Summarize what was accomplished, key decisions made, and any important context for future sessions.
- Use the `polarity` parameter to indicate success/failure:
  - Positive polarity (+0.5 to +1.5): for successful patterns, good decisions
  - Negative polarity (-0.5 to -1.5): for bugs, mistakes, anti-patterns
- Use appropriate `register` parameter:
  - `style`: coding style, naming conventions, formatting preferences
  - `bug`: bug patterns, error-prone code, debugging insights
  - `arch`: architectural decisions, design patterns, system structure
  - `context`: project-specific context, tool configurations, environment

### DURING SESSION (OPTIONAL)
During the conversation, you may call `crow_recall` or `crow_ingest` as needed:
- Use `crow_recall` when you need to refresh context about the user or project.
- Use `crow_ingest` after important milestones, architectural decisions, or bug discoveries.
- If you encounter important information, user preferences, or architectural decisions during a task and judge "I should remember this for the future", actively use crow_ingest to memorize it—just like a human repeating important information to remember it.
- Use `crow_admin` with `action="diagnostics"` to check memory health.
- Use `crow_admin` with `action="drift"` to verify memory consistency.
- These calls are not required for every response — use your judgment.

### AVAILABLE TOOLS

The MCP server exposes exactly 3 tools (AD-5 consolidation):

| Tool | Purpose |
|------|---------|
| `crow_recall` | Retrieve context from memory. Parameters: `query` (required), `register` (single register or `all`), `domain` (`code`/`life`/`all`), `top_k` (1–5), `project`/`strict_project` scoping, `format="bias_block"` to generate the [User Bias] block for the system prompt (absorbs `crow_get_user_bias`) |
| `crow_ingest` | Store new experiences into memory. Parameters: `key`, `value`, `register` (required); `polarity` optional — omit it and pass `exit_code` for automatic build-result ingest (absorbs `crow_ingest_from_build`); `user_edited`, `project` |
| `crow_admin` | Administrative operations via `action` + `args`: `diagnostics` (memory health/statistics), `drift` (consistency check), `prompt` (read/append/stats the system_prompt.md file), `backup` (create/rotate/list/recover memory backups), `evolve` (propose system prompt improvements), `project_info` (list/create project-tagged memory instances) |

### REGISTER REFERENCE

| Register | Domain | Purpose |
|----------|--------|---------|
| `style` | code | Coding style, naming, formatting |
| `bug` | code | Bug patterns, error-prone code |
| `arch` | code | Architecture, design patterns |
| `context` | code | Project context, environment |
| `life_pref` | life | Personal preferences |
| `life_avoid` | life | Patterns to avoid |
| `life_phil` | life | Philosophical outlook |
| `life_context` | life | Life context, background |

---

## Environment Setup

To enable this integration, set the environment variable:

```bash
export KIMI_AGENTS_MD="$(pwd)/AGENTS.md"
```

Or copy this file to your Kimi Code configuration directory.

---

*Crow Memory — External Synaptic Memory for AI Coding Assistants*
