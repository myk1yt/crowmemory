# Crow Memory — Kimi Code Integration

Crow Memory is an external synaptic memory system for LLM-based AI coding assistants. This file integrates Crow Memory into Kimi Code CLI via the `${KIMI_AGENTS_MD}` auto-injection mechanism.

---

## MCP Server Setup (Streamable HTTP)

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
| `crow_admin` | Administrative operations via `action` + `args`: `diagnostics` (memory health/statistics), `drift` (consistency check), `prompt` (manage the system_prompt.md file), `backup` (create/rotate/recover memory backups), `evolve` (propose system prompt improvements), `project_info` (list/create project-isolated memory instances) |

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
