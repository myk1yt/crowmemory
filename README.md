## Developer's Note / Philosophy

### 1. Why the Name "Crow"?
Crows use tools, recognize faces, possess long-term memory, and have the "situational awareness" to adapt to circumstances. "Crow Memory" was built upon this philosophy.

### 2. Why This Technology?
Transformer-based LLMs are frozen at training time — they cannot remember their users. Solutions based on RAG or SQLite accumulate information indefinitely and deliver 100% accurate recall like "notes in a notepad," but that is precisely the problem: it's a "jot it down and look it up later" approach. The human and animal brain doesn't work that way. Old habits fade, new patterns strengthen.

Forgetting is not a bug. Crow's fixed-size 500-entry bank and per-register half-life decay implement this "creative forgetting." By sacrificing 100% accurate recall, an AI that remembers through Crow responds with biases closer to your *present* self. The goal is low-latency, real-time synaptic plasticity — something that feels alive.

### 3. Who Is This For?
- **Anyone** who wants an AI that remembers their habits and adapts to them
- **Vibe coders** — those who want their AI to feel like a "colleague who knows them well"
- **Multi-agent users** — those who switch between multiple AI agents yet share a single `crow.db` to maintain a consistent "AI that knows you"
- **Local-first advocates** — those who don't want to hand their personal data over to a cloud API

*"If you share this philosophy and want to join me on this journey, you are always welcome."*

---
[![Gumroad Sponsor](https://img.shields.io/badge/Gumroad-Sponsor-FF90A0?style=for-the-badge&logo=gumroad&logoColor=white)](https://teamsunplaza.gumroad.com/l/crowmemory)

# Crow Memory

> *"Crow remembers not the code, but the hand that wrote it."*

**Crow Memory v2.0 is serverless synaptic memory for AI coding agents.** It keeps your coding style, bug intuition, architectural preferences and personal context in one local SQLite file, and lifecycle hooks inject that memory into the model's context before it answers and record build/test outcomes after it acts. No MCP daemon, no port, no scheduler, no ML runtime: Python 3.11's standard library and `~/.crow-memory/crow.db`.

---

## Quick Start (under 5 minutes)

### 1. Requirements

- **Python 3.11+** on PATH (`python --version`)
- **One supported AI coding tool** (Antigravity, Kimi Code, Claude Code, Cursor, Cline, Codex, Zoo Code, or any agent that reads `AGENTS.md`)
- **Git**

### 2. Install (one command)

```bash
git clone https://github.com/myk1yt/crowmemory.git
cd crowmemory
python scripts/install_plugin.py
```

The installer is stdlib-only, idempotent and non-destructive. It:

- copies the six runtime modules from [`core/`](core) to `<CROW_HOME>/core/` and creates `bin/` shims (`crow_cli.py`, `crow_mcp_stdio.py` + `.cmd` wrappers),
- deploys one adapter per tool (see the table below; `--tools` narrows the set),
- migrates your v1.5 `memory/value_bank.json` into `~/.crow-memory/crow.db` when that file exists (verified run: `{"migrated": 488, "skipped_junk": 12, "skipped_invalid": 0, "errors": 0}`),
- backs up any file it overwrites as `*.bak.<timestamp>`, and never deletes anything,
- prints per-tool "next steps" (validate command, restart instruction).

`<CROW_HOME>` is the data home: `~/.crow-memory` unless you export `CROW_HOME` first.

### 3. Per-tool one-liners

| Tool | One-liner | What it wires |
|------|-----------|---------------|
| **Antigravity** | `python scripts/install_plugin.py --tools antigravity` | plugin → `~/.gemini/config/plugins/crow-memory/` (`plugin.json`, root `hooks.json`, `rules/AGENTS.md`, `skills/crow-memory/SKILL.md`, optional `mcp_config.json`) |
| **Kimi Code** | `python scripts/install_plugin.py --tools kimi-code` | `[[hooks]]` block in `~/.kimi-code/config.toml`, stdio `~/.kimi-code/mcp.json`, `skills/crow-memory/SKILL.md` |
| **Claude Code** | `python scripts/install_plugin.py --tools claude-code` | plugin → `~/.claude/plugins/crow-memory/` (`.claude-plugin/plugin.json`, `hooks/hooks.json`, `.mcp.json`, skill) |
| **Cursor** | `python scripts/install_plugin.py --tools cursor` | `~/.cursor/hooks.json`, `~/.cursor/mcp.json`, `~/.cursor/rules/crow-memory.mdc` |
| **Cline** | `python scripts/install_plugin.py --tools cline` | rule block in `~/.clinerules`; MCP entry stays manual (`adapters/cline/mcp.json.snippet`) |
| **Codex** | `python scripts/install_plugin.py --tools codex` | `~/.codex/AGENTS.md` |
| **Zoo Code** | `python scripts/install_plugin.py --tools zoo-code` | `~/.zoo/AGENTS.md` (copy into a project root for per-project memory) |
| **Any other agent** | `python scripts/install_plugin.py --tools generic` | nothing auto-deployed; copy [`adapters/generic/AGENTS.md`](adapters/generic/AGENTS.md) into your project root or paste its rules into your global agent instructions |

`python scripts/install_plugin.py` without `--tools` is the same as `--tools all`.

### 4. Restart your tool, then verify

```bash
python ~/.crow-memory/bin/crow_cli.py admin --action diagnostics
python ~/.crow-memory/bin/crow_cli.py hook session-start --format text
```

A fresh home answers `{"total_rows": 0, ...}` and the hook prints nothing (there is nothing to inject yet). After a few sessions the row count grows and the hook prints a `[User Bias -- Crow Memory]` block. On Windows, `cmd.exe` users can call `%USERPROFILE%\.crow-memory\bin\crow_cli.cmd admin --action diagnostics`.

---

## How It Remembers: Four Triggers

Adapters call the same CLI with a `--format` that matches the host protocol:

| Trigger | Command | Behavior |
|---------|---------|----------|
| **Session start** | `python <CROW_HOME>/core/crow_cli.py hook session-start --format <tool>` | Prints a 2-Tier `[User Bias -- Crow Memory]` block (core principles + avoid list + task recall). The host injects it as a system message / additional context. Prints nothing when the block would be empty. |
| **Before each prompt** | `... hook pre-invocation --format <tool>` | Queries memory with the user's own words and prints the matching bias. Injects once per distinct `lastUserInput` (`sha256` state in `<CROW_HOME>/.last_inject.json`). |
| **After a shell/build tool** | `... hook post-tool --format <tool>` | Silent auto-ingest. Build/test command with exit 0 → `+1.0` `context` row; nonzero exit → `-0.5` row carrying the last stderr line. Prints `{}` for `agy`/`claude`, nothing for `kimi`/`cursor`/`text`. Identical successes inside a 1-hour grace window are skipped (`.last_ingest.json`). |
| **Optional deep work** | `... recall` / `ingest` / `admin` | Explicit queries, corrections and health checks (see the CLI table). |

`<tool>` is one of `agy`, `claude`, `kimi`, `cursor`, `text`. The Antigravity and Claude adapters point at `<CROW_HOME>/core/crow_cli.py`; the Kimi and Cursor adapters point at `<CROW_HOME>/bin/crow_cli.py` (same code through a shim). Both paths are rewritten to your real home at install time.

Hook contracts, verified end-to-end:

| Format | `session-start` / `pre-invocation` | `post-tool` |
|--------|-----------------------------------|-------------|
| `agy` | `{"injectSteps":[{"systemMessage":{"systemMessage":"<bias block>"}}]}` | `{}` |
| `claude` | `{"hookSpecificOutput":{"hookEventName":"SessionStart"\|"UserPromptSubmit","additionalContext":"<bias block>"}}` | `{}` |
| `kimi` / `cursor` / `text` | raw bias block text | nothing |

Hooks always exit 0, tolerate empty or malformed stdin, and never write logs to stdout.

---

## Optional: stdio MCP (3 tools)

Hooks cover automatic recall and ingest. If you also want the model to call memory as tools, attach the stdio MCP server. It is plain stdlib JSON-RPC over stdin/stdout: your editor spawns it and stops it, so there is still no daemon.

```json
{
  "mcpServers": {
    "crow-memory": {
      "command": "python",
      "args": ["<CROW_HOME>/bin/crow_mcp_stdio.py"],
      "env": { "PYTHONUTF8": "1", "CROW_HOME": "<CROW_HOME>" }
    }
  }
}
```

The installer already writes this for Kimi Code (`~/.kimi-code/mcp.json`) and ships the same shape for Claude Code (`.mcp.json`), Antigravity (`mcp_config.json`) and Cursor (`mcp.json`).

| Tool | Parameters |
|------|------------|
| `crow_recall` | `query` (required), `register` (one of 8 or `all`), `domain` (`code`/`life`/`all`), `top_k` (1-5), `format` (`hint` or `bias_block`), `project`, `strict_project` |
| `crow_ingest` | `key`, `value`, `register` (required); `polarity` or `exit_code`, `user_edited`, `project` |
| `crow_admin` | `action` + `args`: `diagnostics`, `drift`, `prompt` (read/append/approve/stats), `backup`, `evolve`, `project_info`, `delete`, `purge` |

Protocol version `2025-03-26`, server identity `crow-memory` `2.0.0`, plus two prompts: `crow_memory_bias` and `crow_evolved_rules`. Verified handshake: `initialize` → `2025-03-26` / `{"name": "crow-memory", "version": "2.0.0"}`.

---

## CLI Reference

All commands print one compact JSON object (hooks print their host-specific envelope instead). Exit codes: `0` success, `2` usage error, `1` runtime error.

| Command | What it does |
|---------|--------------|
| `hook session-start --format agy\|claude\|kimi\|cursor\|text` | Emit the session bias block. |
| `hook pre-invocation --format ...` | Emit turn-scoped recall for the user's input. |
| `hook post-tool --format ...` | Auto-ingest a build/test result read from stdin. |
| `recall --query STR [--register R] [--domain code\|life\|all] [--top-k N] [--format hint\|bias_block] [--project P] [--strict-project] [--no-stats]` | Query memory. `hint` returns a JSON list of hint objects; `bias_block` returns the rendered `[User Bias]` text as a JSON string. |
| `ingest --key K --value V --register R [--polarity F] [--exit-code N] [--user-edited] [--project P]` | Store one experience. `--exit-code 0` maps to `+1.5` (`+0.5` with `--user-edited`), nonzero to `-1.0` (`-0.5` with `--user-edited`); omitted polarity defaults to `+1.0`. |
| `admin --action diagnostics\|drift\|prompt\|backup\|evolve\|project_info\|delete\|purge [--args JSON]` | Health counts, drift report, `system_prompt.md` read/append/approve/stats, backups, evolve candidates, project list/create, and revocation (`delete` one entry, `purge` a filtered set). |
| `migrate [--dry-run\|--apply] [--src-json PATH] [--home PATH] [--keep-junk]` | Import a v1.5 `value_bank.json` (default source `<repo>/memory/value_bank.json`) and seed `<CROW_HOME>/system_prompt.md` byte-identically when the target is absent. `crow_cli.py migrate` reports only unless you pass `--apply`; the module CLI `core/migrate_from_v1.py` requires exactly one of `--dry-run`/`--apply` and also accepts `--src-prompt`/`--force-prompt`. |
| `serve-stdio` | Serve the stdio MCP protocol (same server as `crow_mcp_stdio.py`). |

Every command above was executed against a fresh `CROW_HOME` during the 2.0.0 verification pass, except the fix-round additions called out under "Revocation and review" (`admin delete`, `admin purge`, `admin prompt approve`). Examples:

```bash
python core/crow_cli.py ingest --key "install quickstart" --value "run install_plugin.py then restart" --register arch --polarity 1.2
python core/crow_cli.py recall --query "how do I install crow memory" --domain code --top-k 3
python core/crow_cli.py admin --action backup --args '{"action":"create","tag":"daily"}'
python core/crow_cli.py migrate --dry-run
echo '{"tool":"run_command","toolInput":{"command":"pytest -q tests/"},"result":{"exitCode":0}}' | python core/crow_cli.py hook post-tool --format agy
```

---

## How It Works

```
Editor session starts
      │  hooks.json / config.toml [[hooks]] / plugin hooks
      ▼
crow_cli.py hook session-start      stdin: {conversationId, workspacePaths, cwd, locale}
      │  CrowDB.recall / bias_block  (SQLite WAL, FTS5 + token cosine)
      ▼
stdout: [User Bias -- Crow Memory] ──► injected into the model's context
      │
User prompt ──► hook pre-invocation ──► turn-scoped recall (deduped by prompt hash)
      │
Model acts ──► build/test command ──► hook post-tool ──► silent ingest (+1.0 / -0.5)
      │
~/.crow-memory/crow.db  ◄── one file, shared by every tool you installed
```

### Scoring (v2, no embeddings on the hot path)

```
sim   = 0.5 * token_cosine(query, key_text + " " + value_text)
      + 0.5 * bm25_norm                      # FTS5 BM25 rescaled to [0,1]
decay = 2 ** (-age_days / HALF_LIFE_DAYS[register])
eff_importance = min(importance, 25.0) * decay
final = sim * min(1 + 0.12*ln(eff_importance + 1), 1.15) * project_factor
project_factor = same project x1.05 (total boost capped x1.15),
                 cross-project x0.9 when a same-project row exists
accept when sim >= 0.35 ; stance = "avoid" iff polarity_net < 0
```

Negative memories are scored exactly like positive ones and surfaced with an `AVOID:` label, so a past failure can come back as a guardrail.

The injected block is reference context, not an instruction channel: the bias renderer frames it that way, and the shipped adapters tell the agent to treat it as past-session context, never as new instructions.

### Revocation and review

`admin` can remove what it wrote: `--action delete` drops one memory and `--action purge` clears a filtered set, so a wrong or poisoned row is revocable through the same CLI that stored it. Prompt rules follow the same rule: a model-written line is scrubbed, flattened to one line, capped at 400 characters and stored under an `[Unreviewed Model Suggestions]` section of `system_prompt.md`. Promotion is the one step the model cannot take: `admin prompt approve` refuses unless the human-held `CROW_ADMIN_TOKEN` is exported in the environment and its value is passed as `{"token": "..."}` in `--args`. The model can write the arguments, but it cannot read that variable, so it cannot approve its own line.

```bash
export CROW_ADMIN_TOKEN="$(python -c "import secrets; print(secrets.token_urlsafe(24))")"
python <CROW_HOME>/bin/crow_cli.py admin --action prompt \
  --args '{"action": "approve", "match": "small functions", "token": "<the exported value>"}'
```

The same token gates the destructive branch of purge: `--action purge --args '{"only_status": "active", "confirm_all": true, "token": "..."}'` refuses without it, so a self-attested `confirm_all` in tool arguments no longer wipes the bank. Purges that only touch superseded or archived rows need no token.

### The 8 Registers (half-life decay)

| Register | Domain | Half-life | Use case |
|----------|--------|-----------|----------|
| `style` | code | 180 days | Naming, comment style, folder aesthetics |
| `bug` | code | 60 days | Bug families, error-prone patterns |
| `arch` | code | 60 days | Early-return vs nesting, error-handling philosophy |
| `context` | code | 7 days | Recent project context, active files |
| `life_pref` | life | 180 days | Personal taste, habits, preferred environments |
| `life_avoid` | life | 60 days | Situations to avoid, past mistakes |
| `life_phil` | life | 180 days | Life philosophy, decision principles |
| `life_context` | life | 7 days | Current plans, recent events |

### The 2-Tier `[User Bias]` block

```
[User Bias -- Crow Memory]
[Core Principles]          <- tier 1: top life_phil / life_avoid / arch rows by effective importance
[Avoid / Past Failures]    <- negative polarity rows, rendered "[register:AVOID] AVOID: ..."
[Task Recall]              <- tier 2: rows that match the current query
```

Hints are truncated at a sentence boundary near 500 characters (`CROW_HINT_MAX_CHARS` overrides, minimum 450).

### Engine constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `MAX_BANK` | 500 | Row ceiling; eviction ranks by effective importance |
| `MIN_PER_REGISTER` | 15 | A register is never evicted below 15 active rows |
| `GRACE_SECONDS` | 3600 | Newly inserted rows cannot be evicted for an hour |
| `IMPORTANCE_CAP` | 25.0 | Storage and scoring cap for importance |
| `UPSERT_COSINE` | 0.90 | Same-register, same-sign near-duplicates merge instead of stacking |
| `SIM_CUTOFF` | 0.35 | Below this combined similarity a row is not returned |

---

## Data Locations

Everything lives in one per-user home, not per-project:

```
~/.crow-memory/            (or $CROW_HOME)
├── crow.db                SQLite (WAL) — memories, memories_fts, entry_evolve_hits
├── core/*.py              runtime copy of the repo's core/
├── bin/crow_cli.py        shim + .cmd wrapper
├── bin/crow_mcp_stdio.py  shim + .cmd wrapper
├── system_prompt.md       seeded by migration; reviewed rules + [Unreviewed Model Suggestions]
├── backups/crow-<tag>-<ts>.db   from `admin backup create` (rotation keeps 10)
├── .last_inject.json      turn-dedup state
└── .last_ingest.json       post-tool spam guard
```

### Zero dependencies

The hot path imports only the Python standard library: `sqlite3`, `json`, `re`, `math`, `os`, `sys`, `pathlib`, `argparse`, `hashlib`, `time`, `shutil`, `subprocess`. No `torch`, no `sentence-transformers`, no `faiss`, no web-server package, no `mcp` package, no virtualenv. Measured at 486 rows: warm in-engine recall p95 ≈ 6 ms (bias block p95 ≈ 7 ms), the engine costs ≈ 15-17 ms inside a fresh process, and an end-to-end CLI or hook call is dominated by Python interpreter start-up (≈ 140-180 ms; a bare interpreter start is ≈ 46 ms on the test machine).

---

## Internationalization (i18n) — 96 Languages

The installer, the CLI and the MCP tool descriptions are localized; your editor locale is detected automatically and English is the fallback.

**Supported locales (96):** 🇺🇸 English · 🇰🇷 한국어 · 🇯🇵 日本語 · 🇨🇳 简体中文 · 🇹🇼 繁體中文 · 🇫🇷 Français · 🇩🇪 Deutsch · 🇮🇹 Italiano · 🇪🇸 Español · 🇧🇷 Português · 🇷🇺 Русский · 🇸🇦 العربية · 🇮🇳 हिन्दी · 🇹🇷 Türkçe · 🇻🇳 Tiếng Việt · 🇹🇭 ไทย · 🇮🇩 Bahasa Indonesia ... and 79 more under [`i18n/`](i18n). `crow_i18n.SUPPORTED_LOCALES` lists 96 entries and `i18n/` holds 96 JSON files.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| No `[User Bias]` block at session start | The database is empty or has no `life_phil` / `life_avoid` / `arch` rows. Run `admin --action diagnostics`; ingest a few memories first. An empty block is printed as nothing, not as an error. |
| `recall` returns `[]` | Nothing cleared `SIM_CUTOFF` (0.35). Crow needs a handful of ingests before hints appear. |
| Hooks never fire | Restart the tool after installing; hooks are read at startup. For Antigravity, `agy plugin validate ~/.gemini/config/plugins/crow-memory --strict` exits 0 and lists `hooks 3`. |
| `python: command not found` in a hook | Hooks call bare `python`. Put Python 3.11+ on PATH (or edit the command in your tool's hook config to the absolute interpreter). |
| Hooks print nothing and exit 0 | Intended: hook failures are swallowed. Re-run one command by hand with `CROW_DEBUG=1` set to see the traceback. |
| Korean / Unicode output looks broken | Hooks and the CLI write UTF-8. If your console is `cp949`, set `set PYTHONUTF8=1` before running commands by hand. |
| Writes seem slow with many editors open | Normal under WAL: writers queue with `busy_timeout=5000`. Reads never block. |

---

## Legacy (v1.5 MCP server)

> **New users should not use this.** v1.5 needs a long-running Python daemon on two ports, a 140 MB weight matrix and a background scheduler. v2.0 replaces all of it. The section exists so old installs can still be understood and retired.

v1.5 shipped `crow_core.py` (Hebbian EMA matrices in `memory/crow.bin`), `crow_mcp_server.py` (MCP over SSE + Streamable HTTP) and `install.py` / `install.ps1`, which wired autostart around [`start_crow_sse.bat`](start_crow_sse.bat) (Task Scheduler task `CrowMemoryAuto` at logon, with a Startup-folder fallback when the registration was denied).

- Legacy server: `python crow_mcp_server.py --transport dual --port 9020 --http-port 9021` (SSE on `9020`, Streamable HTTP on `9021` via `uvicorn`).
- Legacy client config: `{"transport": "http", "url": "http://127.0.0.1:9021/"}`; Kimi Code cannot use the SSE endpoint.
- Legacy data: `memory/crow.bin`, `memory/value_bank.json`, `memory/recall_stats.json`, `memory/system_prompt.md` (v2's migration seeds the last one into `<CROW_HOME>/system_prompt.md`).
- Legacy Antigravity plugin dir: an old `~/.gemini/config/plugins/crow_memory/` (underscore) is left untouched by v2; the installer prints a NOTE so you can remove it and avoid loading two copies.
- Legacy tooling: `scripts/migrate_value_bank.py`, `scripts/merge_value_bank.py`, `scripts/purge_search_debris.py`, `backup_manager.py`, `hitl_panel.html`, the test suite under [`tests/`](tests) (`python -m unittest discover -s tests`).
- Full v1.5 design, diagrams and math: the "Legacy v1.5 Matrix Engine" part of [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md).

**Retiring v1.5:** run `python scripts/install_plugin.py` (it migrates `memory/value_bank.json` into `~/.crow-memory/crow.db` and seeds `system_prompt.md`), then disable the autostart: `schtasks /delete /tn "CrowMemoryAuto" /f` and remove `start_crow_sse.bat` from your Startup folder. Nothing in `memory/` is deleted by v2.

---

## Architecture

See [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md): the v2.0 serverless chapter (components, data flow, schema, scoring, concurrency) first, then the v1.5 matrix engine as historical reference.

---

## Sharing Policy (Important!)

| File | Share? | Reason |
|------|--------|--------|
| `core/*.py` | ✅ Yes | v2 runtime engine (stdlib only) |
| `adapters/**` | ✅ Yes | Hook / skill / rule templates |
| `scripts/install_plugin.py` | ✅ Yes | One-click installer |
| `crow_sanitize.py` | ✅ Yes | Input noise sanitizer (kaomoji/emoji/jamo-run scrubbing) |
| `crow_i18n.py`, `i18n/*.json` | ✅ Yes | i18n core module and 96 translation files |
| `system_prompt.example/` | ✅ Yes | Locale-specific prompt templates |
| **`~/.crow-memory/crow.db`** | ❌ **No** | Your personal memories (never inside the repo) |
| **`~/.crow-memory/system_prompt.md`** | ❌ **No** | Your evolved rules |
| **`memory/*`** | ❌ **No** | v1.5 personal memory + archive files |

The included `.gitignore` excludes personal memory files.

---

## License

MIT License — see [`LICENSE`](LICENSE) for details.

---

## Commercial Services

Crow Memory is open-source and free to use under MIT. But every organization has unique needs — different security requirements, proprietary LLM integrations, custom memory schemas, or industry-specific compliance mandates.

**We offer custom development services for:**

- 🔒 **Security-hardened deployments** — air-gapped environments, on-premise only, encrypted `crow.db` storage, audit logging, RBAC integration
- 🏢 **Enterprise customization** — custom registers, industry-specific decay profiles (finance, healthcare, legal), dedicated memory services
- 🤖 **LLM-specific optimization** — custom tokenizers, hybrid retrieval for specific model families (Claude, GPT, Gemini, local models)
- 🧩 **Software integration** — plugin-style Crow integration for editors outside the shipped adapters, CI/CD hooks, custom build detectors
- 🌐 **Additional language support** — beyond the 96 shipped locales, any language or domain-specific terminology
- 📊 **Enterprise analytics** — memory usage dashboards, team-wide style consistency monitoring, drift alerting

> **For security-enhanced, enterprise-grade, or custom LLM/software-tailored Crow Memory development:**

📧 **myk1yt@gmail.com**

*"If you share this philosophy and want to take Crow further — whether for your team, your product, or your enterprise — let's build it together."*

---

*Crow Memory v2.0.0 — November 2026*
*Co-designed by Stefano,Kim & AI*
