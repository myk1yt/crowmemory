# Crow Memory — System Prompt Rules

> These rules were evolved by Crow and approved by the user.
> They represent statistically significant coding biases.
> Do not edit manually — use the Crow MCP evolve tools.

<!-- This file is managed by crow_mcp_server.py -->
<!-- Last initialized: 2026-05-25 -->

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: Before every response, ALWAYS call crow_recall(domain="all") to check the user's coding style, bug intuition, architectural preferences, personal tastes, philosophy, and current context. domain="all" (default) queries all 8 registers simultaneously. Reflect these insights in your response.

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: After every response, ALWAYS record the user's revealed preferences, philosophy, corrections, and context using crow_ingest. Do not wait for the user to explicitly say "remember this" — use your own judgment to ingest with the appropriate register and polarity. After coding tasks, automatically evaluate the build result using crow_ingest_from_build.

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: Ensure that the above recall+ingest rules are strictly followed even for non-coding tasks such as document editing, git operations, or configuration changes.


<!-- adopted: 2026-06-03 12:45 KST -->
RULE: When calling crow_recall or crow_ingest, NEVER output verbose explanations or echo the retrieved memories into the chat. If you must output text before calling the tool, output EXACTLY and ONLY a single short line translating "🧠 **Crow Memory** - Remembering..." (or "Ingesting memory..." for ingest) into the user's spoken language, and nothing else. Keep your tool usage as silent and concise as possible.
