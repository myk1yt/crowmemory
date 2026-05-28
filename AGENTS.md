# Crow Memory (Auto-Activation)

You have access to **Crow Memory**, an external synaptic memory system connected via MCP.
It stores the user's coding style, bug intuition, architectural preferences, and personal context as compressed weight matrices.

**UNIVERSAL RECALL (MANDATORY): Before EVERY response — whether coding, writing, editing, or conversation — call `crow_recall(domain="all")` to retrieve the user's coding style, bug intuition, architectural preferences, personal taste, life philosophy, and current context.** `domain="all"` (the default) queries all **8 registers** (style, bug, arch, context, life_pref, life_avoid, life_phil, life_context) in a single call. Use the returned hints to personalize your response. Never skip this step.

**AUTO-INGEST (MANDATORY): After EVERY response, evaluate what the user revealed — a preference, a philosophy, a frustration, a pattern, a correction, ongoing plans, or explicit decision. Call `crow_ingest` with the appropriate register, a concise key/value summary, and appropriate polarity.** Do NOT wait for the user to say "remember this." For code work, also call `crow_ingest_from_build`.

**POLARITY GUIDE** (auto-determined, no user command needed):
- User likes / prefers something → +1.5 (`life_pref` / `style`)
- User reveals philosophy / values → +2.0 (`life_phil`)
- User corrects you / rewrites your work → -1.0 (`bug` / `style`)
- User shares ongoing context / plans → +1.5 (`life_context` / `context`)
- User explicitly says "remember" / "never forget" → +2.0 / -2.0
- User shows frustration / avoidance → -0.5 (`life_avoid` / `bug`)

Crow is not a database — it stores inductive biases. Use it as your intuition, not your encyclopedia.

---

## Orchestrator + Crow Mode (orchestrator-crow)

Crow Memory also supports an **orchestrator-crow** custom mode for task-delegation workflows.

### How to enable in Zoo Code:

1. Press `Ctrl+Shift+P` → type "Mode" → select "Switch Mode"
2. Choose **"Orchestrator + Crow"** from the list
3. Or set it as default in [`.zoo/config.json`](.zoo/config.json):
   ```json
   {
     "defaultMode": "orchestrator-crow"
   }
   ```

This mode integrates Crow Memory's recall/ingest cycle with orchestrator-style task delegation.
