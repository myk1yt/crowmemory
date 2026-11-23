# decisions.md — Crow Memory engineering decision log (append-only)

## 2026-11-24 — v2.0.0 Serverless rebuild (VP-orchestrated, user full authority incl. commit/push)

1. **Adopted spec Track B (Option C) as the master strategy**: SQLite WAL core + lifecycle hooks + optional thin stdio MCP; v1.5 PyTorch/crow.bin stack kept as legacy, untouched. Rationale: user asked for "lighter than MCP server, works everywhere"; audit spec §6.1 names it the master recommendation.
2. **Delegated build via contract-first swarm**: binding CONTRACT.md pinned APIs before parallel workers; all interfaces landed without drift (only recorded deviations).
3. **i18n: 96 locales (36 baseline + 60 new), full Google Translate coverage per user request.** Contract §11 freeze later overridden for the 34 stale legacy files after the reviewer swarm confirmed requirement "key-parity" (fix-list-1 CR-7); re-keyed in a 6-agent swarm.
4. **Trust-boundary hardening (security gate)**: `prompt approve` + `purge confirm_all` gated behind human-held `CROW_ADMIN_TOKEN`; model-appended rules render only in `[Unreviewed Model Suggestions]`; false "approved via HITL" claims removed (fix-list-2 R2-1/R2-3). Fail-closed by default.
5. **NEG_DAMPEN_BY_REGISTER wired per spec** (negative polarity dampened x0.6 except bug/life_avoid) after mechanical verification that it was declared-but-unused (fix-list-1 CR-3).
6. **Perf posture**: write-time tokenization (schema v2.1 tokens column); honest measured numbers documented (in-engine warm p95 ~6ms; fresh-process engine ~15-17ms; end-to-end hook dominated by interpreter start-up). Perf regression bound set to 20ms to guard the ~41ms re-tokenization regression without flaking under host load.
7. **Deferred (user-visible)**: `.vscode/tasks.json` legacy SSE-daemon autostart left in place (v1.5 dev tooling; decide at v1.5 teardown). JSON-RPC batch array responses documented-but-not-implemented (MCP clients do not batch).
8. **Session working folder `docs/261124_0001_session_crow-v2-serverless/` intentionally NOT committed** per AGENTS.md §5 (contains worker/reviewer reports, contract, fix-lists).
9. **Committed the user's audit spec + reports/ research files** as the v2.0 design rationale trail.
10. **Known incident**: a FIX-B probe created the real `~/.crow-memory/` (empty schema, 0 rows) during testing; left in place — it is the canonical v2 install location and will be populated by the user's first real install/migration.
EOF
echo done