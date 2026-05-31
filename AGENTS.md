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
- Call `crow_recall` with `domain="user"` to understand the user's personality, preferences, working style, and past interactions.
- Call `crow_recall` with `domain="project"` to understand the current project context and recent activities.
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
- Use `crow_diagnostics` to check memory health.
- Use `crow_check_drift` to verify memory consistency.
- These calls are not required for every response — use your judgment.

### AVAILABLE TOOLS

| Tool | Purpose |
|------|---------|
| `crow_recall` | Retrieve user/project context from memory |
| `crow_ingest` | Store new experiences into memory |
| `crow_ingest_from_build` | Auto-ingest based on build exit code |
| `crow_evolve_propose` | Propose system prompt improvements |
| `crow_diagnostics` | Check memory health and statistics |
| `crow_check_drift` | Detect memory drift |
| `crow_get_user_bias` | Generate [User Bias] block for system prompt |
| `crow_manage_prompt` | Manage the system_prompt.md file |
| `crow_manage_backup` | Create/rotate/recover memory backups |
| `crow_project_info` | List/create project-isolated memory instances |

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
export KIMI_AGENTS_MD="/path/to/crowsmemory/AGENTS.md"
```

Or copy this file to your Kimi Code configuration directory.

---

*Crow Memory — External Synaptic Memory for AI Coding Assistants*
