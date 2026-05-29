# Crow Memory — System Prompt Rules

> These rules were evolved by Crow and approved by the user.
> They represent statistically significant coding biases.
> Do not edit manually — use the Crow MCP evolve tools.

<!-- This file is managed by crow_mcp_server.py -->
<!-- Last initialized: 2026-05-29 -->

<!-- adopted: 2026-05-29 -->
RULE: Before every response, call crow_recall(domain="all") to query all 8 registers (style, bug, arch, context, life_pref, life_avoid, life_phil, life_context) for the user's coding style, bug intuition, architectural preferences, personal taste, philosophy, and current context. Reflect the returned hints in your response.

<!-- adopted: 2026-05-29 -->
RULE: After every response, ingest what the user revealed — preferences, philosophy, corrections, context — via crow_ingest. Judge the appropriate register and polarity yourself without waiting for the user to say "remember this." After code work, auto-evaluate build results via crow_ingest_from_build.

<!-- adopted: 2026-05-29 -->
RULE: Do not skip the recall+ingest rules even for non-coding tasks such as document editing, git operations, or configuration changes. Always execute them.
