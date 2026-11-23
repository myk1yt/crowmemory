# Crow (까마귀) Memory Architecture
## A Synaptic State Cache for Recursive Agent Development

**Version:** 1.5.0
**Date:** 2026-11-24
**Author:** Stefano,Kim & AI Collaborative Design
**Target Runtime:** Any AI coding agent with lifecycle hooks (Antigravity, Kimi Code, Claude Code, Cursor, Cline) or any agent that reads `AGENTS.md`; Python 3.11+ standard library only.
**Reading order:** §0 summary, §1 philosophy, then the v1.5.0 Serverless Architecture chapter. Everything from §2 onward documents the legacy v1.5 matrix engine and is kept as historical reference.

---

## 0. Executive Summary

**Crow** is an external long-term memory for AI coding agents. It does not remember *what* you did, it remembers *how* you think: your naming habits, your architectural reflexes, your bug intuition, your personal constraints. The current release (v1.5.0) stores that memory as rows in a single SQLite file, `~/.crow-memory/crow.db`, and injects it through editor lifecycle hooks before the model answers. It requires no server, no port, no scheduler, and no machine-learning runtime.

Earlier releases (v1.5.0-mcp and below) stored the same experience as compressed synaptic weights inside a fixed-size `crow.bin` matrix and served it from a Python MCP daemon. That design is documented in full from §2 onward as a legacy reference; the v1.5.0 Serverless Architecture chapter right after §1 describes what ships today.

The name "Crow (까마귀)" is deliberate. Crows possess episodic-like memory, tool-crafting intelligence, and social learning: they observe, remember, and adapt their behavior based on past outcomes without rewriting their DNA. Crow Memory does the same for an AI agent. It cannot modify the LLM's base weights, but it can sculpt the prompt environment and tool-use bias so effectively that the agent *behaves* as if it has evolved.

**Key Constraint (Non-Negotiable):**  
> Crow is **not** a knowledge base. It does not promise complete or exact retrieval. It stores short experiences with a signed polarity and an importance, ranks them by similarity and recency, and lets each register forget on its own schedule. Exact facts (API specs, file paths, syntax) still belong in RAG, markdown, or a spec. Crow handles the *vibe*: the gravitational pull of your coding style, your architectural instincts, your bug-hunting reflexes.

**What the serverless release changed, in one paragraph.** v1.5 stored experience as matrix weights and needed a resident Python daemon to survive model load time and to serialize writes through an exclusive lock. The serverless release stores the same experience as text rows in SQLite (WAL, FTS5) and scores them with `0.5 * token_cosine + 0.5 * bm25_norm`, decayed by a per-register half-life. That removed the daemon, the ports, the lock file and the ML runtime, and it removed three defects that the matrix could not escape: the Sign Inversion Paradox (negative memories were being strengthened by `abs(polarity)`), the Importance Ratchet (last-ingested rows never aged out), and Rank-1 collapse (repeated ingestions turned a register into a projector onto one pattern, so every query returned the same hint).

---

## 1. Philosophy & Design Principles

### 1.1 The Two-Brain Doctrine
Every coding agent needs two distinct knowledge organs:

| Organ | Medium | Precision | Role | Crow's Role |
|-------|--------|-----------|------|-------------|
| **Hippocampus** | Markdown, RAG, specs | Lossless | Exact facts, specs, file trees | **None** (v1.5.0 rows are text, but recall is scored, decayed and evictable, so it is still not a lossless store) |
| **Neocortex Bias** | `crow.db` rows ranked by similarity and decay (v1.5.0); `crow.bin` matrix (v1.5) | Lossy & Associative | Style, instinct, architectural gravity | **Everything** |

Crow occupies the second layer. It ensures that when the LLM writes code for you, it feels *your* hand--not generic best practices, not Stack Overflow averages, but *your* early-return reflex, *your* JSDoc verbosity, *your* terror of unhandled Windows encodings.

### 1.2 Hebbian Episodicity
Crow's write protocol mimics Hebbian plasticity: neurons that fire together, wire together. Repeating an experience raises its importance; correcting one lowers its signed polarity instead of adding weight. What prevents catastrophic interference is scheduled forgetting: v1.5.0 decays every register by its own half-life (7 to 180 days) before ranking, while v1.5 decayed the matrix weights with an Exponential Moving Average. Either way, new memories do not erase old ones. They reshape the dune instead of bulldozing it.

### 1.3 The Observer Effect
Crow learns not from what the model *generates*, but from what the *user accepts*. A generated snippet that passes `npm run build` and is accepted without human edit is a **positive reinforcement** (+1.5). A snippet that the user immediately rewrites is a **negative reinforcement** (-0.8). The model is not the teacher; the user is.

### 1.4 Prompt Evolution as Phenotype
While Crow cannot rewrite the LLM's genotype (base weights), it can rewrite its **phenotype** (system prompt and tool-call behavior). Crow's `evolve` protocol proposes prompt mutations, and v1.5.0 treats every model-written rule as untrusted: an append is scrubbed, flattened to a single line, capped at 400 characters and stored under an `[Unreviewed Model Suggestions]` section of `system_prompt.md`. Promotion needs a human-held secret: `admin prompt approve` refuses unless `CROW_ADMIN_TOKEN` is set in the environment and passed as `{"token": ...}`, and the model cannot read that variable, so it cannot promote its own line. Mutations still arise freely; selection stays human.

### 1.5 Fixed-Size Immortality
Crow's memory is bounded by design: v1.5.0 keeps at most 500 active rows (`MAX_BANK`) and v1.5 kept a ~140 MB `crow.bin`. The bank never grows with your project count. This is not a limitation; it is a *feature*. It forces the system to compress, abstract and generalize, exactly what human long-term memory does. You do not remember every line of code you wrote in 2003; you remember *that you preferred monolithic classes back then*.

---

## v1.5.0 Serverless Architecture (Current)

**Status:** current, v1.5.0 (2026-11-24). Source of truth: [`core/`](core).
**Shape:** editor lifecycle hooks + a short-lived CLI process + one SQLite file per user.

### v2.1 Why the daemon had to go

The v1.5 Python server existed for three reasons, none of them essential to the memory itself:

| v1.5 constraint (legacy) | Cause | v1.5.0 answer |
|---|---|---|
| Resident process | `torch` + `nomic-embed-text-v1.5` + a 140 MB `crow.bin` took seconds to load, so a per-turn CLI was impractical | Pure-stdlib SQLite: warm in-engine recall p95 ≈ 6 ms at 486 rows, and the engine costs ≈ 15-17 ms inside a fresh process |
| Single-writer file lock | `crow.bin` is one binary mutated in place; two processes corrupted it, so `crow.bin.lock` + PID checks + zombie cleanup were mandatory | SQLite WAL: readers never block, writers queue with `busy_timeout=5000` |
| Two transports | Kimi Code could not parse the server-sent-event handshake and Antigravity dropped it as well, so two HTTP transports had to run together | Hooks need no transport at all (stdin per event, stdout per response); the optional stdio MCP is spawned by the client and speaks over pipes |

### v2.2 Topology

```
AI coding tool (Antigravity / Kimi Code / Claude Code / Cursor / Cline / AGENTS.md agents)
  |
  |-- SessionStart ------> python <CROW_HOME>/core/crow_cli.py hook session-start
  |-- UserPromptSubmit -->             ... hook pre-invocation     stdin JSON -> stdout JSON
  |-- PostToolUse ------>              ... hook post-tool          (silent auto-ingest)
  |                                             |
  |                                  core/crow_db.py  (CrowDB)
  |                                    recall()     scoring + half-life decay
  |                                    ingest()     merge / semantic upsert / eviction
  |                                    bias_block() 2-Tier text block
  |                                             |
  |                                  ~/.crow-memory/crow.db   (SQLite WAL + FTS5)
  |
  '-- optional stdio JSON-RPC ---> core/crow_mcp_stdio.py   (client-spawned, no socket)
```

Nothing stays resident between turns and nothing listens on a port.

### v2.3 Components

| Path | Runtime | Responsibility |
|------|---------|----------------|
| [`core/crow_db.py`](core/crow_db.py) | Python stdlib (`sqlite3`, `math`, `json`) | The engine. `CrowDB.recall()`, `.ingest()`, `.bias_block()`, `.admin()` (diagnostics, drift, prompt read/append/approve/stats, backup, evolve, project_info, delete, purge), `.rebuild_from_bank()`, `.stats()`. Owns the schema, the scoring formula, eviction, and the 2-Tier block. |
| [`core/crow_text.py`](core/crow_text.py) | Python stdlib (`re`, `math`, `os`) | Shared text utilities: `_tokenize()` (ASCII words + CJK/Hangul/Thai unigrams and bigrams), `token_cosine()`, `_smart_truncate()` (500 characters, sentence boundary, `CROW_HINT_MAX_CHARS` override with a 450 floor). |
| [`core/crow_sanitize.py`](core/crow_sanitize.py) | Python stdlib (`re`, `unicodedata`) | Verbatim v1.5 sanitizer: `scrub_text()`, `project_slug()`. Strips kaomoji, emoji and jamo runs while protecting code, URLs and Korean text. |
| [`core/crow_cli.py`](core/crow_cli.py) | Python stdlib (`argparse`, `json`) | The only interface most users touch: hook adapter plus `recall` / `ingest` / `admin` / `migrate` / `serve-stdio`. Hooks always exit 0. |
| [`core/crow_mcp_stdio.py`](core/crow_mcp_stdio.py) | Python stdlib | Optional MCP server: newline-delimited JSON-RPC 2.0, protocol `2025-03-26`, 3 tools and 2 prompts. |
| [`core/migrate_from_v1.py`](core/migrate_from_v1.py) | Python stdlib | One-shot importer for `memory/value_bank.json`; seeds `system_prompt.md`; requires `--dry-run` or `--apply`; non-destructive. |
| [`adapters/`](adapters) | Static templates | Per-tool hook, skill and rule files with `<CROW_HOME>` placeholders rewritten by the installer. |
| [`scripts/install_plugin.py`](scripts/install_plugin.py) | Python stdlib | One-command installer: copy core, create shims, deploy adapters, migrate, back up, print next steps. |
| `<CROW_HOME>/bin/*` | Generated shims | `crow_cli.py` / `crow_mcp_stdio.py` plus `.cmd` wrappers that put `<CROW_HOME>/core` on `sys.path`. |

### v2.4 Data flow

**Read path (session start, before each prompt).** The host pipes a JSON object on stdin:

```json
{"conversationId": "...", "workspacePaths": ["..."], "cwd": "...", "lastUserInput": "...", "invocationNum": 1, "locale": "ko"}
```

`session-start` renders the 2-Tier block with an empty query (no matching needed). `pre-invocation` renders it with `lastUserInput` as the query and skips injection when the prompt hash equals the value stored in `<CROW_HOME>/.last_inject.json` and `invocationNum != 1`. Output envelopes:

| `--format` | `session-start` / `pre-invocation` | `post-tool` |
|---|---|---|
| `agy` | `{"injectSteps":[{"systemMessage":{"systemMessage":"<block>"}}]}` | `{}` |
| `claude` | `{"hookSpecificOutput":{"hookEventName":"SessionStart"\|"UserPromptSubmit","additionalContext":"<block>"}}` | `{}` |
| `kimi` / `cursor` / `text` | raw block text (empty string when there is nothing to inject) | nothing |

**Write path (after a shell or build tool).** `post-tool` reads the tool-result JSON, decides whether the command looks like a build/test run (test, build, pytest, unittest, make, cargo, npm, pnpm, tsc, pyright, ...), extracts an exit status from `exitCode` / `exit_code` / `status` / `error`, and ingests a `context` row: exit 0 gives polarity `+1.0` with value `Build/test succeeded`; a nonzero exit gives `-0.5` with `Build/test failed (exit N): <last stderr line>`. Identical successful ingests inside `GRACE_SECONDS` (3600) are skipped using `.last_ingest.json`. Ingest failures are swallowed, so a hook can never break a build.

### v2.5 Scoring

Candidates are every row with `status != 'archived'` (`superseded` rows stay recallable as guardrails). Per candidate:

```
sim    = 0.5 * token_cosine(query, key_text + " " + value_text)
       + 0.5 * bm25_norm                    # FTS5 BM25, min-max rescaled to [0,1] per query
age    = now - max(last_recalled_at, updated_at)
decay  = 2 ** (-age_days / HALF_LIFE_DAYS[register])
eff_imp = min(importance, IMPORTANCE_CAP) * decay
factor = min(1 + 0.12 * ln(eff_imp + 1), 1.15)
project_factor = same project x1.05 (total boost capped x1.15)
                 cross-project rows x0.9 when a same-project row is in the candidate set
                 strict_project=True drops cross-project rows outright
final  = sim * factor * project_factor      # accept only if sim >= SIM_CUTOFF (0.35)
stance = "avoid" iff polarity_net < 0
```

Rows are sorted by `final` descending and cut to `top_k`. Negative rows are scored exactly like positive ones (the Sign Inversion Paradox fix) and merely labeled; they are never filtered out. `bias_block()` calls the same scoring with `track_stats=False`, so injecting bias does not pollute drift statistics.

### v2.6 Storage schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_uid TEXT NOT NULL UNIQUE,     -- sha256[:12]
    register TEXT NOT NULL,             -- style|bug|arch|context|life_*
    key_text TEXT NOT NULL,
    value_text TEXT NOT NULL,
    project TEXT,                       -- project_slug(), NULL = global
    polarity_net REAL NOT NULL,         -- signed sum; negative rows render as AVOID
    importance REAL NOT NULL DEFAULT 1.0,
    ingest_count INTEGER NOT NULL DEFAULT 1,
    recall_hits INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',   -- active|superseded|archived
    supersedes_uid TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_recalled_at REAL NOT NULL DEFAULT 0.0,
    UNIQUE(register, key_text)
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
    key_text, value_text, content='memories', content_rowid='id', tokenize='unicode61'
);

CREATE TABLE entry_evolve_hits (
    entry_uid TEXT PRIMARY KEY,
    distinct_queries TEXT NOT NULL DEFAULT '[]',  -- JSON list, capped at 50
    session_buckets TEXT NOT NULL DEFAULT '[]',   -- JSON list of int(ts // 3600)
    sim_sum REAL NOT NULL DEFAULT 0.0,
    last_seen REAL NOT NULL
);

CREATE INDEX idx_memories_register_status ON memories(register, status);
```

`memories_fts` is an external-content FTS5 table over `memories`; `rebuild_from_bank()` repairs it with the FTS5 `rebuild` command instead of deleting and re-inserting rows.

### v2.7 Concurrency, durability, and what is deliberately absent

| Concern | v1.5.0 mechanism |
|---------|----------------|
| Many editors at once | SQLite WAL: concurrent readers never block, one writer at a time, waiters retry for 5 s (`busy_timeout`). Any number of Antigravity, Kimi, Claude and Cursor windows can share one `crow.db`. |
| Crash safety | Every ingest is a single transaction; WAL checkpoints on close. `admin --action backup` copies `crow.db` (and `system_prompt.md`) into `backups/`, keeping the last 10. |
| Daemon | Absent. Hooks are ordinary short-lived processes invoked by the host per event. |
| Port | Absent. The optional stdio MCP is spawned by the client and talks over pipes. |
| Lock file | Absent. No `*.lock`, no PID verification, no stale-lock cleanup. |
| Scheduler | Absent. No Task Scheduler task, no Startup entry, no `start_*.bat` watchdog. |
| Model load | Absent. No `torch`, no `sentence-transformers`, no `faiss`, no web-server package, no `mcp` package. |

### v2.8 Registers and decay

| Register | Domain | Half-life | Use case |
|----------|--------|-----------|----------|
| `style` | code | 180 days | Naming, comment style, folder aesthetics |
| `bug` | code | 60 days | Bug families, debugging reflexes |
| `arch` | code | 60 days | Early-return vs nesting, error-handling philosophy |
| `context` | code | 7 days | Recent project context, active files |
| `life_pref` | life | 180 days | Personal taste, habits, environments |
| `life_avoid` | life | 60 days | Situations to avoid, past mistakes |
| `life_phil` | life | 180 days | Life philosophy, decision principles |
| `life_context` | life | 7 days | Current plans, recent events |

Engine limits: `MAX_BANK` 500 active rows, `MIN_PER_REGISTER` 15 (a register is never evicted below this), `GRACE_SECONDS` 3600 (new rows are eviction-proof for an hour), `IMPORTANCE_CAP` 25.0, `UPSERT_COSINE` 0.90 (same register, same polarity sign, token cosine at or above this merges instead of creating a row), `SIM_CUTOFF` 0.35.

### v2.9 Install layout

```
~/.crow-memory/                  # $CROW_HOME overrides
├── core/                        # runtime copy of the repo's core/*.py
├── bin/crow_cli.py(.cmd)        # shims that prepend ../core to sys.path
├── bin/crow_mcp_stdio.py(.cmd)
├── crow.db                      # SQLite WAL database (+ -wal / -shm while open)
├── system_prompt.md             # seeded by migration; reviewed rules + [Unreviewed Model Suggestions]
├── backups/crow-<tag>-<ts>.db   # `admin --action backup`, rotate keeps 10
├── .last_inject.json            # prompt-hash dedup state
└── .last_ingest.json            # post-tool spam guard
```

The installer deploys adapters to per-tool locations: `~/.gemini/config/plugins/crow-memory/` (Antigravity), `~/.kimi-code/` (Kimi Code), `~/.claude/plugins/crow-memory/` (Claude Code), `~/.cursor/` (Cursor), `~/.clinerules` (Cline), `~/.codex/AGENTS.md` (Codex), `~/.zoo/AGENTS.md` (Zoo Code). Every overwrite is preserved as `*.bak.<timestamp>`. A pre-existing legacy `crow_memory/` (underscore) Antigravity directory is left in place and reported with a NOTE, so it can be removed by hand.

### v2.10 Migration from v1.5

`core/migrate_from_v1.py` (or `crow_cli.py migrate`) reads a v1.5 `value_bank.json`, imports each entry through `CrowDB.ingest()` with its stored register, importance and polarity sign, preserves `created_at` where the v1 record has a timestamp, and skips test debris (`k`, `test key`, `test`, `hello`, values containing `[CHECKPOINT]`, `Whiteboard state:`, `Dep analysis:`). It also seeds `<CROW_HOME>/system_prompt.md` byte-identically from `<repo>/memory/system_prompt.md`.

- Mode: the module CLI requires exactly one of `--dry-run` / `--apply`; `crow_cli.py migrate` maps a missing `--apply` to a dry run.
- `--dry-run` opens no database and writes nothing (`prompt.would_copy` reports what a real run would do).
- `--apply` writes to `<CROW_HOME>/crow.db` and seeds the prompt file; the v1 sources are only read.
- Prompt seeding never overwrites a live `<CROW_HOME>/system_prompt.md`: if the target exists, `prompt.skipped_exists` is set and the file is untouched. `--force-prompt` overwrites it and backs the displaced file up to `system_prompt.md.bak.<timestamp>` first; `--src-prompt` selects a different source file.
- Report keys: `{processed, inserted, merged, rejected, skipped_junk, skipped_invalid, errors, per_register, prompt{src, dst, would_copy, copied, skipped_exists, error}}`, with `migrated` kept equal to `processed` for compatibility.
- Verified against this repository: `processed 488 = inserted 486 + merged 2 + rejected 0`, `skipped_junk 12`, `errors 0`, prompt copied byte-identically; the database then reports `total_rows: 486`.

### v2.11 Operational characteristics

- Recall wall time at 486 rows: in-engine warm p95 ≈ 6 ms (bias block p95 ≈ 7 ms); the engine costs ≈ 15-17 ms inside a fresh process; an end-to-end CLI or hook call is dominated by Python interpreter start-up (≈ 140-180 ms p95, against ≈ 46 ms for a bare interpreter start on the test machine).
- Memory is revocable: `admin --action delete` removes one row and `admin --action purge` clears a filtered set, so a poisoned entry can be removed through the same CLI that stored it. Prompt rules written by the model stay under `[Unreviewed Model Suggestions]` until `admin prompt approve` promotes them, and the rendered bias block is framed as reference context, never as new instructions.
- An empty database produces no hook output at all. This is correct: there is nothing to inject, and the host must not receive an empty system message.
- When only `context` or `style` rows exist, `session-start` stays silent because Tier 1 draws from `life_phil` / `life_avoid` / `arch`. `pre-invocation` still injects as soon as a row matches the prompt.
- Hook failures are swallowed and the process exits 0. Set `CROW_DEBUG=1` to see a traceback on stderr.

---

## Legacy v1.5 Matrix Engine (historical reference)

> **Everything from §2 to the end of this document describes v1.5.0-mcp**, the PyTorch + `crow.bin` + MCP daemon engine. It is kept because old installations still exist and because the philosophy sections above reference it. New installations should use v1.5.0 only: see `README.md`, `core/`, and the chapter above.
>
> Section numbers (2-13) are unchanged from the published v1.5 document so external references stay valid.

## 2. System Architecture

### 2.1 Topology

```
+---------------------------------------------------------------------+
|                   VS CODE-BASED IDE (Zoo Code)                       |
|  +-----------------+  +------------------+  +---------------------+ |
|  |  User Editor    |  |  Build/Test Hook |  |  HITL Gate (UI)     | |
|  |  (TypeScript)   |  |  (Node.js)       |  |  (Approve/Reject)   | |
|  +--------+--------+  +--------+---------+  +----------+----------+  |
|           |                    |                       |              |
|           +--------------------+-----------+-----------+          |
|                                            |                      |
|                              +-------------v-------------+        |
|                              |      LLM API              |        |
|                              |   (Cloud / On-prem)       |        |
|                              |   - Base weights: RO      |        |
|                              |   - Large context window  |        |
|                              |   - Tool use: Enabled     |        |
|                              +-------------+-------------+        |
|                                            |                      |
|                    +-----------------------+------------------+   |
|                    |                       |                   |      |
|                    v                       v                   v      |
|         +-----------------+    +----------------+    +-----------------+
|         |  Tool: recall   |    | Tool: ingest   |    | Tool: evolve    |
|         |  (synaptic read)|    | (synaptic      |    | (prompt mutate  |
|         |                 |    |  write)        |    |  suggestion)    |
|         +--------+--------+    +--------+-------+    +--------+--------+
|                  |                      |                   |
|                  +----------------------+-------------------+
|                                         |
|                           +-------------v-------------+
|                           |  Local Python MCP Server  |
|                           |  (SSE HTTP, port 9020,    |
|                           |   Streamable HTTP 9021)   |
|                           |  - Detached process       |
|                           |    (survives IDE restart) |
|                           |  - Auto-started by        |
|                           |    Windows Task Scheduler |
|                           |    (AtLogon trigger)      |
|                           |    + start_crow_sse.bat   |
|                           |  - Health polling with    |
|                           |    exponential backoff    |
|                           |  - Ready file signal      |
|                           |    (memory/.crow_ready)   |
|                           |  - Multi-client safe      |
|                           +-------------+-------------+
|                                         |
|                           +-------------v-------------+
|                           |   crow.bin (safetensors)  |
|                           |   8 Registers             |
|                           +---------------------------+
+---------------------------------------------------------------------+
```

### 2.2 Component Responsibilities

| Component | Runtime | Responsibility |
|-----------|---------|----------------|
| **VS Code IDE** | Local Electron/Node | Orchestrates the agent loop, captures build exit codes, renders HITL UI. Auto-starts SSE server at Windows user logon via Task Scheduler (`CrowMemoryAuto`) → [`start_crow_sse.bat`](start_crow_sse.bat). **Default mode: "Orchestrator + Crow"** — configured via `.zoo/config.json`. |
| **LLM Agent** | Cloud/On-prem API | Inference engine, generates code, proposes prompt mutations, decides tool calls |
| **MCP Server (SSE)** | Local Python (detached) | Serves `crow.bin` I/O over HTTP (port 9020 SSE). Embedding encoding, weight math, FAISS nearest-neighbor lookup. Serializes all multi-client access. **Runs as detached process** — survives IDE restarts. Writes `memory/.crow_ready` on listen. Supports **36-language i18n** based on VS Code locale detection. |
| **`start_crow_sse.bat`** | Batch + PowerShell | Detached process launcher + health poller. Uses `Start-Process -WindowStyle Hidden` for process isolation. Polls `/sse` with exponential backoff (0.5s→8s, max 30s). Cleans stale lock files. |
| **`crow.bin`** | Local SSD | Fixed-size `safetensors` file containing 8 weight matrices + projection layer |
| **Build Hook** | Local Node | Captures `npm run build`, test results, linter output; emits JSON to MCP server |
| **`backup_manager.py`** | Local Python | CLI utility for backup creation, rotation, listing, and drift recovery |
| **`hitl_panel.html`** | Local Browser | Web UI for human-in-the-loop approval of evolved prompt rules |

---

## 3. The Memory Core: `crow.bin`

### 3.1 Physical Specification

```python
# state.safetensors -- fixed-size, memory-mappable
{
    # ── Code Domain ──
    # Register 1: Coding Style (slow accumulation, high permanence)
    "style_S":        Tensor [4096, 4096]  float16,   # ~32 MB

    # Register 2: Bug Pattern Intuition (medium accumulation)
    "bug_S":          Tensor [2048, 2048]  float16,   # ~8 MB

    # Register 3: Architecture Preference (medium accumulation)
    "arch_S":         Tensor [2048, 2048]  float16,   # ~8 MB

    # Register 4: Recent Code Context (fast decay, high turnover)
    "context_S":      Tensor [2048, 4096]  float16,   # ~16 MB

    # ── Life Domain (v1.1+) ──
    # Register 5: Personal Preferences (slow accumulation)
    "life_pref_S":    Tensor [4096, 4096]  float16,   # ~32 MB

    # Register 6: Life Avoidances (medium accumulation)
    "life_avoid_S":   Tensor [2048, 2048]  float16,   # ~8 MB

    # Register 7: Life Philosophy (medium accumulation)
    "life_phil_S":    Tensor [2048, 2048]  float16,   # ~8 MB

    # Register 8: Life Context (fast decay, high turnover)
    "life_context_S": Tensor [2048, 4096]  float16,   # ~16 MB

    # Projection: Embedding space -> Register space
    "proj_W":         Tensor [4096, 768]   float16,   # ~6 MB  (768->4096)
    "proj_b":         Tensor [4096]        float16,   # ~8 KB

    # Metadata
    "update_count":   int64 scalar,
    "schema_version": int64 scalar         # 1 (current)
}
# Total: ~140 MB (compressed ~100 MB)
```

### 3.2 Why 8 Registers?

Interference is the enemy. If "JSDoc style preference" and "PDF encoding bug" share the same 4096x4096 matrix, they corrupt each other. Separation by semantic domain preserves fidelity.

**Code Domain**

| Register | Dimensions | lambda (EMA decay) | Capacity (patterns) | Use Case |
|----------|------------|---------------------|-----------------------|----------|
| `style` | 4096^2 | 0.9999 (~7,000 updates to halve) | ~2,000 | Variable naming, comment style, folder aesthetics |
| `bug` | 2048^2 | 0.9995 (~1,400 updates to halve) | ~800 | Abstract bug families, not exact fixes |
| `arch` | 2048^2 | 0.9995 | ~800 | Early-return vs deep-nesting, error-handling philosophy |
| `context` | 2048x4096 | 0.9500 (~14 updates to halve) | ~400 | Recent conversation topics, active file context |

**Life Domain** (v1.1+)

| Register | Dimensions | lambda (EMA decay) | Capacity (patterns) | Use Case |
|----------|------------|---------------------|-----------------------|----------|
| `life_pref` | 4096^2 | 0.9999 | ~2,000 | Personal taste, preferred environments, habits |
| `life_avoid` | 2048^2 | 0.9995 | ~800 | Situations to avoid, dislikes, past mistakes |
| `life_phil` | 2048^2 | 0.9995 | ~800 | Life philosophy, decision principles, values |
| `life_context` | 2048x4096 | 0.9500 | ~400 | Current plans, recent events, ongoing concerns |

**Capacity estimation:** Based on Modern Hopfield Network theory, a d-dimensional register stores O(d) orthogonal patterns. For dense real-world vectors, practical capacity is ~0.3d to 0.5d.

### 3.3 Memory Mapping & I/O Performance

```python
import mmap
import numpy as np
from safetensors.numpy import load_file

class CrowState:
    def __init__(self, path: str):
        # Memory-map the entire file. 70 MB loads in <1 ms from SSD.
        self.data = load_file(path, device="cpu")
        # All tensors are np.ndarray views into the mmap buffer.
        # Zero-copy. No deserialization overhead after first load.

    def persist(self, path: str):
        # Atomic write: crow.tmp -> rename to crow.bin
        # Prevents corruption if process crashes mid-write.
        save_file(self.data, path + ".tmp")
        os.replace(path + ".tmp", path)
```

**Latency Budget:**
- `mmap` load: ~0.3 ms (SSD) / ~0.05 ms (RAM resident)
- Matrix-vector multiply (4096^2 x 4096): ~1.2 ms (single-core NumPy, float16)
- FAISS nearest-neighbor (2048-dim, 500 samples): ~0.1 ms
- **Total recall latency: <2 ms**

---

## 4. The Three Protocols

### 4.1 Protocol Alpha -- `recall` (Read)

**Purpose:** Inject user-specific inductive bias into the LLM's prompt context.

**Flow:**
1. The LLM receives user query: *"Fix the memory leak in this PDF worker"*
2. The agent decides to call `crow_recall(query="PDF worker memory leak", register="bug")`
3. MCP Server encodes query -> embedding -> projection -> query vector `q`
   (the LRU embedding cache is keyed by the `sha256` of the truncated input,
   eliminating the 200-char-prefix collisions of older versions)
4. Computes `r = S.T @ q` (recalled vector)
5. Looks up `value_bank` for nearest neighbors to `r`. Each candidate passes
   through the acceptance gate:
   - **Sanitize gate (ingest side):** text was scrubbed via `crow_sanitize.py`
     at ingest time; entries that became empty after sanitization were rejected
     (`empty_after_sanitize`) and never entered the bank.
   - **SIM_CUTOFF (default 0.35):** raw similarity must always be >= the cutoff
     (env: `CROW_SIM_CUTOFF`). No backdoor paths remain.
   - **Importance boost:** capped at ×1.15 total.
   - **Project tagging:** same-project entries get a ×`PROJECT_BOOST` (1.05)
     similarity boost; cross-project entries must clear the higher
     `CROSS_PROJECT_CUTOFF` (default 0.42); `strict_project=True` hard-filters
     cross-project entries out; untagged (`project=null`) entries are global.
6. When no specific register is given, `recall_multi()` queries the domain's
   registers and merges results by global effective similarity — no per-register
   fillers; stats are tracked only for hit registers.
7. Returns hint strings sorted by effective similarity.

**Example Return:**
```json
{
  "hints": [
    "User consistently prefers explicit cleanup in useEffect over weakRef patterns.",
    "User favors abortSignal linkage for all async workers; missing signal = high rejection risk."
  ],
  "confidence": 0.82,
  "register": "bug"
}
```

**LLM Prompt Injection:**
These hints are prepended to the system prompt as a `[User Bias]` block:
```
[System Prompt]
... base instructions ...

[User Bias -- retrieved from Crow Memory]
- User consistently prefers explicit cleanup in useEffect over weakRef patterns.
- User favors abortSignal linkage for all async workers.

[User Query]
Fix the memory leak in this PDF worker...
```

### 4.2 Protocol Beta -- `ingest` (Write)

**Purpose:** Consolidate experience into synaptic weights.

**Trigger Conditions:**

| Event | Polarity | Register | Rationale |
|-------|----------|----------|-----------|
| Build success + user accepts unchanged | +1.5 | `style` or `arch` | Strong positive reinforcement |
| Build success + user edits slightly | +0.5 | `style` | Acceptable but not perfect |
| Build failure + user rewrites entirely | -1.0 | `bug` or `style` | Strong negative reinforcement |
| User explicitly says "Remember this style" | +2.0 | `style` | Explicit override |
| User explicitly says "Never do this again" | -2.0 | any | Explicit suppression |

**Mathematical Form:**

```python
def ingest(self, key_text: str, value_text: str, 
           polarity: float, register: str):
    S = self.registers[register]        # (dim_k, dim_v)
    lam = self.lambdas[register]        # EMA decay

    # 1. Encode
    k = self.encode(key_text)           # (dim_k,), L2-normalized
    v = self.encode(value_text)         # (dim_v,), L2-normalized

    # 2. Decay old memories
    S *= lam

    # 3. Hebbian update with polarity-scaled strength
    delta = np.outer(k, v) * (1 - lam) * polarity
    S += delta.astype(np.float16)

    # 4. Spectral clipping (every 1000 updates)
    if self.update_count % 1000 == 0:
        self._clip_spectrum(register, max_sv=2.0)

    # 5. Sanitize gate: reject pure-noise input before touching memory
    if not scrub_text(value_text):
        return {"status": "rejected", "reason": "empty_after_sanitize"}

    # 6. Append to value_bank (importance-based priority queue, max 500)
    self.value_bank.append({
        "key": key_text,
        "value": value_text,
        "vector": v.tobytes(),
        "timestamp": time.time(),
        "project": project   # optional project tag; None/absent = global
    })
```

**Spectral Clipping:**
Without clipping, repeated positive ingestions cause singular values to explode, turning the matrix into a projector onto a single dominant pattern. Clipping enforces `sigma_max <= 2.0`, preserving multi-pattern capacity.

```python
def _clip_spectrum(self, register: str, max_sv: float):
    S = self.registers[register].astype(np.float32)
    U, s, Vt = np.linalg.svd(S, full_matrices=False)
    s = np.clip(s, -max_sv, max_sv)
    self.registers[register] = (U @ np.diag(s) @ Vt).astype(np.float16)
```

### 4.3 Protocol Gamma -- `evolve` (Prompt Mutation)

**Purpose:** Propose system prompt mutations based on statistically significant Crow patterns.

**Trigger:** When `crow.bin` detects that the same hint has been retrieved >3 times in the last 10 sessions with >0.85 confidence, the MCP server flags it as a **candidate rule**.

**Flow:**
1. Crow MCP server emits candidate rule to Zoo Code
2. Zoo Code forwards it to the LLM with special meta-prompt:
   > "You are the Prompt Architect. Based on this observed user bias, draft a concise system prompt addition."
3. The LLM generates a proposed prompt fragment (<=100 tokens)
4. Zoo Code renders HITL UI: **"Adopt this bias as permanent prompt rule?"**
5. User approves -> appended to `system_prompt.md` (text file, version-controlled)
6. User rejects -> `ingest(polarity=-0.3)` to suppress future similar proposals

**Example Evolution:**
- **Observed (Crow):** 5 sessions retrieved "User prefers early return over nested if-else"
- **Proposed (V4):** `RULE: When generating TypeScript functions, prefer early return guards. Avoid nesting beyond 2 levels.`
- **Adopted:** Inserted into system prompt. Now V4 receives this bias *directly* without needing Crow recall, saving API tokens.

---

## 5. MCP Tool Schema (LLM Interface)

This is the exact schema exposed by the local Python MCP server. The LLM sees these as native tools.

### 3 MCP Tools (v1.5.0-mcp — AD-5 consolidation)

The former 10-tool surface was consolidated into 3 tools. Legacy capabilities are absorbed as parameters/actions. This is the exact schema exposed by [`crow_mcp_server.py`](crow_mcp_server.py):

```json
{
  "tools": [
    {
      "name": "crow_recall",
      "description": "Recall user-specific coding style, bug intuition, architectural preference, or personal context from the Crow synaptic memory. Call this BEFORE every response to align with user's inductive bias. By default (register=all or omitted, domain=all), queries all 8 registers and merges results by effective similarity.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Natural language description of the current task."},
          "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"], "description": "Which register. Use 'all' (or omit) to query every register in the selected domain."},
          "domain": {"type": "string", "enum": ["code", "life", "all"], "description": "Domain filter used when register is 'all' or omitted. 'code' = style/bug/arch/context, 'life' = life_pref/life_avoid/life_phil/life_context, 'all' = all 8 registers (default)."},
          "top_k": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5, "description": "Number of hints (1-5)."},
          "project": {"type": "string", "description": "Project tag used to boost same-project hints and filter/penalize cross-project ones."},
          "strict_project": {"type": "boolean", "description": "When true, hard-filters cross-project hints out of the results."},
          "format": {"type": "string", "enum": ["hint", "bias_block"], "description": "Output format. 'hint' returns JSON hints (default); 'bias_block' returns the [User Bias] text block for system prompt injection (absorbs crow_get_user_bias)."}
        },
        "required": ["query"]
      }
    },
    {
      "name": "crow_ingest",
      "description": "Ingest a coding experience into Crow's long-term synaptic memory. Call AFTER build/test results or user explicit feedback. Provide either an explicit polarity or a build exit_code for automatic polarity mapping. Content is sanitized first; pure-noise input is rejected without touching the memory.",
      "parameters": {
        "type": "object",
        "properties": {
          "key": {"type": "string", "description": "Abstract description of the situation."},
          "value": {"type": "string", "description": "Code pattern or decision applied."},
          "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"], "description": "Which register to write to."},
          "polarity": {"type": "number", "description": "Reinforcement strength [-2.0, 2.0]. Optional if exit_code is given; explicit polarity wins when both are provided."},
          "exit_code": {"type": "integer", "description": "Build exit code (0 = success). Maps automatically to polarity (+1.5/+0.5 on success, -0.5/-1.0 on failure) unless an explicit polarity is given (absorbs crow_ingest_from_build)."},
          "user_edited": {"type": "boolean", "description": "Whether the user edited the AI's output. Adjusts the exit_code-derived polarity."},
          "project": {"type": "string", "description": "Project tag stored with the memory entry for later project-aware recall."}
        },
        "required": ["key", "value", "register"]
      }
    },
    {
      "name": "crow_admin",
      "description": "Crow administrative operations in one tool.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["diagnostics", "drift", "prompt", "backup", "evolve", "project_info"], "description": "Which admin operation: diagnostics (memory health/statistics), drift (consistency check), prompt (read/append/stats system_prompt.md), backup (create/rotate/list/recover), evolve (propose system prompt improvements), project_info (list/create project-isolated memory instances)."},
          "args": {"type": "object", "description": "Action-specific arguments, e.g. {\"threshold\": 0.5} for drift, {\"action\": \"append\", \"rule\": \"...\"} for prompt, {\"action\": \"create\", \"tag\": \"daily\"} for backup, {\"min_confidence\": 0.85} for evolve, {\"action\": \"create\", \"project_name\": \"myapp\"} for project_info."}
        },
        "required": ["action"]
      }
    }
  ]
}
```

### Constants (recall precision, `crow_core.py`)

| Constant | Default | Env Override | Meaning |
|----------|---------|--------------|---------|
| `SIM_CUTOFF` | 0.35 | `CROW_SIM_CUTOFF` | Minimum raw similarity for any hint to be visible (no backdoor paths) |
| `CROSS_PROJECT_CUTOFF` | 0.42 | `CROW_SIM_CUTOFF_CROSS_PROJECT` | Higher cutoff for cross-project entries |
| `PROJECT_BOOST` | 1.05 | `CROW_PROJECT_BOOST` | Same-project effective-similarity boost (total importance boost capped at ×1.15) |
| `NEG_DAMPEN_BY_REGISTER` | `bug`=1.0, `life_avoid`=1.0, others 0.6 | — | Per-register negative-polarity dampening |
| `importance_boost` cap | ×1.15 | — | Total boost cap (importance + project combined) |

### 2 MCP Prompts (Auto-Loaded by Host)

| Prompt | Description |
|--------|-------------|
| `crow_memory_bias` | Full context: evolved rules + recent memory hints from all registers. Loaded automatically at session start. |
| `crow_evolved_rules` | Permanent rules from `memory/system_prompt.md`. Returns only the approved RULE lines. |

---

## 6. The Agent Loop: Recursive (but Bounded) Development

### 6.1 One Complete Cycle

```
+------------------------------------------------------------------+
| Step 1: User submits task in Zoo Code                              |
|         "Implement EPUB metadata extraction in Bookviewer"        |
+------------------------------------------------------------------+
| Step 2: The LLM calls crow_recall(register="arch")                  |
|         -> Returns: "User prefers early validation + fail-fast     |
|            for file format parsers. Always check magic bytes       |
|            before full read."                                     |
+------------------------------------------------------------------+
| Step 3: The LLM generates code with bias injected into prompt       |
+------------------------------------------------------------------+
| Step 4: Zoo Code runs npm run build + tests                        |
|         -> Exit 0, user accepts without edits                      |
+------------------------------------------------------------------+
| Step 5: Zoo Code auto-triggers crow_ingest(                        |
|           key="EPUB metadata parser architecture",                 |
|           value="magic byte check -> early return if invalid",     |
|           polarity=+1.5, register="arch")                           |
+------------------------------------------------------------------+
| Step 6: Crow detects this pattern has hit confidence 0.91 over     |
|         4 sessions. Emits candidate rule to Zoo Code.              |
+------------------------------------------------------------------+
| Step 7: The LLM (via crow_admin action="evolve") drafts:          |
|         "RULE: For all binary format parsers, validate magic      |
|          bytes in the first 8 bytes and early-return on mismatch" |
+------------------------------------------------------------------+
| Step 8: HITL Gate -- User sees popup:                              |
|         "Adopt 'magic-byte validation' as permanent prompt rule?"   |
|         -> User clicks [YES]                                       |
+------------------------------------------------------------------+
| Step 9: Rule appended to system_prompt.md. Next cycle, the LLM      |
|         receives this rule natively, no recall needed.            |
+------------------------------------------------------------------+
                              |
                    [Next Task -- Loop Continues]
```

### 6.2 Boundedness -- Why This Is Not AGI

The loop is **recursive but bounded**:
- **Upper bound:** The LLM's base capability. Crow cannot make the LLM smarter than it is.
- **Convergence:** Prompt space has diminishing returns. After ~20 high-quality rules, marginal utility drops.
- **Cost cap:** Each `evolve_propose` consumes API tokens. Hard limit: 1 proposal per day, max 5 API calls per cycle.
- **Human veto:** Every prompt mutation requires human approval. The agent cannot modify its own genotype.

**This is feature, not bug.** The goal is not transcendence; it is **habituation**--making the agent feel like a senior developer who has pair-programmed with you for 1,000 hours.

---

## 7. Safety, Guardrails & Anti-Runaway

### 7.1 The HITL Mandate

| Action | Automation Level | Human Gate |
|--------|------------------|------------|
| `crow_recall` | 100% auto | None needed (read-only) |
| `crow_ingest` | Auto-triggered by build hooks | User can review/undo in 30-second window |
| `crow_admin action="evolve"` | Auto-detected, auto-drafted | **Mandatory approval** before prompt append |
| Prompts are never auto-adopted | Never auto | `admin prompt approve` promotes a staged line |

**Serverless note:** this table describes the v1.5 daemon. In v1.5.0 the `evolve` action only proposes candidates; a model-written rule is stored under `[Unreviewed Model Suggestions]` and does not become standing context until a human runs `admin prompt approve` (see §1.4 and the v1.5.0 chapter).

### 7.2 Drift Detection

If `crow_recall` returns hints with confidence <0.5 for `min_low_confidence_count` (default 5) or more stat records across all registers, the system enters **drift alert**:
1. Pause auto-ingest
2. Notify user: "Crow memory seems confused. Recent tasks are too novel or memory is saturated."
3. Offer: **Spectral reset** (soft: clip singular values) or **Register archive** (move old `style_S` to `style_S.bak` and initialize fresh)

### 7.3 Negative Ingestion Ceiling

To prevent a single bad session from poisoning memory:
- `polarity` is clamped to [-2.0, 2.0]
- Negative ingestions are dampened per-register by `NEG_DAMPEN_BY_REGISTER`
  (`bug` = 1.0, `life_avoid` = 1.0 — bug lessons and avoidance signals are preserved
  at full strength; all other registers use the 0.6 default):
  actual delta = `polarity * dampen * (1-lam)`
- A single negative event cannot erase more than 40% of a pattern's accumulated weight (0.6-dampened registers)

### 7.4 Backup & Versioning

```
memory/
|-- crow.bin                              # Active memory
|-- crow.bin.bak.daily.20260525_143022    # Daily backup (rotating 7 days)
|-- crow.bin.bak.weekly.20260525_000000   # Weekly checkpoint
|-- system_prompt.md                      # Active prompt
|-- system_prompt.md.bak                  # Pre-evolution backup
```

Every `evolve` adoption triggers atomic backup. User can rollback to any previous week.

---

## 8. Implementation Roadmap

### Phase 0: Prototype — ✅ Implemented
- [x] Implement `CrowState` class (8 registers, EMA, spectral clip)
- [x] Integrate `nomic-embed-text-v1.5` encoder
- [x] Build MCP server exposing 3 tools (AD-5) + 2 prompts
- [x] Manual test: `recall` -> `ingest` -> `recall` cycle with dummy data

### Phase 1: Zoo Code Hook — ✅ Implemented
- [x] Capture `npm run build` exit code via `crow_ingest(exit_code=...)`
- [x] Auto-trigger `crow_ingest` on build success/failure
- [x] Inject `[User Bias]` block into the LLM system prompt before generation

### Phase 2: Feedback Loop — ✅ Implemented
- [x] Track user edit distance (accepted vs rewritten) via polarity auto-detection
- [x] Polarity modulation based on build exit code + user edits
- [x] `value_bank` importance-weighted priority queue + FAISS index for text retrieval

### Phase 3: Evolution — ✅ Implemented
- [x] Implement evolve proposals (`crow_admin action="evolve"`) with confidence/occurrence thresholds
- [x] Build HITL UI (`hitl_panel.html`) for rule approval
- [x] Connect to `system_prompt.md` append workflow with auto-backup

### Phase 4: Hardening — ✅ Implemented
- [x] Drift detection (`crow_admin action="drift"`) & auto-recovery (`recover_from_drift`)
- [x] Backup rotation (`crow_admin action="backup"`) & rollback
- [x] Project tagging (`project` parameter + `crow_admin action="project_info"`; single `crow.bin` with tag-based isolation via `CROW_STATE_TAG` when needed)

---

## 9. Appendix A: Mathematical Details

### 9.1 Linear Associative Memory

Given query vector `q in R^d`, state matrix `S in R^{dxd}`, recalled vector `r`:

```
r = S^T q
```

If `S = sum_i k_i v_i^T` (sum of outer products), then:

```
r = sum_i v_i (k_i^T q)
```

This is a **weighted sum of all stored values**, where weights are query-key similarities. No softmax, no attention heads--pure linear superposition.

### 9.2 EMA Update Rule

```
S_{t+1} = lambda S_t + (1-lambda) polarity_t * k_t v_t^T
```

For `lambda = 0.9999`, the half-life of a memory is:

```
n_{1/2} = ln(0.5) / ln(lambda) ~~ 6930 updates
```

For `context` register with `lambda = 0.95`:

```
n_{1/2} ~~ 14 updates
```

### 9.3 Capacity Bound

Modern Hopfield Network capacity for `d`-dimensional vectors with correlation `c`:

```
C ~~ 0.14 d^2 / (ln(d) * (1-c))
```

For `d=4096`, `c=0.3` (moderate correlation between coding styles):

```
C ~~ 0.14 * 16,777,216 / (8.3 * 0.7) ~~ 400,000 patterns (theoretical)
```

**Practical capacity** (accounting for non-orthogonality, noise, EMA decay): **~2,000 distinct style patterns** in the `style` register before recall fidelity drops below 0.7.

---

## 10. Appendix B: Why "Crow (까마귀)"?

> *The crow is not a repository. It is not a librarian.*  
> *The crow is a companion that flies beside you, watching your hands,*  
> *remembering not what you built, but how you breathed while building it.*  
> *It cannot read blueprints, but it knows you always reach for the same hammer.*  
> *It forgets the nail, but never forgets the swing.*

**Biological Homology:**
- **Tool Crafting:** New Caledonian crows manufacture compound tools. Crow Memory manufactures compound prompt biases.
- **Episodic Memory:** Crows remember specific past events (who, what, where, when). Crow Memory remembers specific past *outcomes* (build success/failure context).
- **Social Learning:** Crows learn from observing others' mistakes. Crow Memory learns from observing the user's corrections.
- **Neural Density:** Crow brains are dense with associative neurons relative to body size. Crow `crow.bin` is dense with associative weights relative to file size.

The name is not merely poetic. It is a **behavioral contract**: we are not building an oracle that knows everything. We are building a bird that recognizes your silhouette.

---

## 11. Appendix C: Minimal Viable Server (Python)

> **Note (v1.4.5+):** The production [`crow_mcp_server.py`](crow_mcp_server.py) uses the `MCPServer` high-level API (MCP Python SDK 2.1.1) with `@mcp.tool()` type-hint auto-schema, `@mcp.prompt()`, and `@mcp.custom_route()` decorators. The example below keeps the low-level `Server` style purely for brevity of illustration.

### C.1 stdio Transport (single client)

```python
#!/usr/bin/env python3
"""
crow_mcp_server.py -- Minimal viable Crow Memory MCP server.
Run: python crow_mcp_server.py --state ./memory/crow.bin
"""

import asyncio
import numpy as np
import torch
import torch.nn as nn
from sentence_transformers import SentenceTransformer
from safetensors.numpy import load_file, save_file
from mcp.server import Server
from mcp.server.stdio import stdio_server

DIM = 4096
REGISTERS = {
    # Code domain
    "style":   (DIM, DIM,    0.9999),
    "bug":     (2048, 2048,  0.9995),
    "arch":    (2048, 2048,  0.9995),
    "context": (2048, DIM,   0.9500),
    # Life domain (v1.1+)
    "life_pref":    (DIM, DIM,    0.9999),
    "life_avoid":   (2048, 2048,  0.9995),
    "life_phil":    (2048, 2048,  0.9995),
    "life_context": (2048, DIM,   0.9500),
}

class CrowMemory:
    def __init__(self, path: str):
        self.path = path
        try:
            self.data = load_file(path)
        except FileNotFoundError:
            self.data = self._init_blank()
        self.encoder = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5")
        self.proj = nn.Linear(768, DIM).half().eval()
        if "proj_W" in self.data:
            self.proj.weight.data = torch.from_numpy(self.data["proj_W"])
            self.proj.bias.data = torch.from_numpy(self.data["proj_b"])

    def _init_blank(self):
        data = {}
        for name, (d_k, d_v, _) in REGISTERS.items():
            data[f"{name}_S"] = np.zeros((d_k, d_v), dtype=np.float16)
        data["proj_W"] = np.random.randn(DIM, 768).astype(np.float16) * 0.01
        data["proj_b"] = np.zeros(DIM, dtype=np.float16)
        data["update_count"] = np.array(0, dtype=np.int64)
        return data

    def encode(self, text: str) -> np.ndarray:
        vec = self.encoder.encode(text, normalize_embeddings=True)
        vec = torch.from_numpy(vec).half()
        with torch.no_grad():
            projected = self.proj(vec).numpy()
        projected /= (np.linalg.norm(projected) + 1e-8)
        return projected.astype(np.float16)

    def recall(self, query: str, register: str) -> dict:
        q = self.encode(query)
        S = self.data[f"{register}_S"]
        r = S.T.astype(np.float32) @ q.astype(np.float32)
        conf = float(np.linalg.norm(r) / (np.linalg.norm(S) + 1e-8))
        return {
            "hints": [f"Crow recalls a strong {register} bias for: {query}"],
            "confidence": round(min(conf, 1.0), 2),
            "register": register
        }

    def ingest(self, key: str, value: str, polarity: float, register: str):
        k = self.encode(key)
        v = self.encode(value)[:REGISTERS[register][1]]
        S = self.data[f"{register}_S"]
        lam = REGISTERS[register][2]
        S *= lam
        delta = np.outer(k[:S.shape[0]], v) * (1 - lam) * polarity
        S += delta.astype(np.float16)
        self.data["update_count"] += 1
        self._maybe_clip(register)
        self._persist()

    def _maybe_clip(self, register: str):
        if int(self.data["update_count"]) % 1000 == 0:
            S = self.data[f"{register}_S"].astype(np.float32)
            U, s, Vt = np.linalg.svd(S, full_matrices=False)
            s = np.clip(s, -2.0, 2.0)
            self.data[f"{register}_S"] = (U @ np.diag(s) @ Vt).astype(np.float16)

    def _persist(self):
        save_file(self.data, self.path + ".tmp")
        import os
        os.replace(self.path + ".tmp", self.path)

app = Server("crow_memory")
crow = CrowMemory("./memory/crow.bin")

@app.call_tool()
async def handle_tool(name: str, arguments: dict):
    if name == "crow_recall":
        return crow.recall(arguments["query"], arguments.get("register"))
    elif name == "crow_ingest":
        crow.ingest(arguments["key"], arguments["value"],
                    arguments["polarity"], arguments["register"])
        return {"status": "ingested"}
    elif name == "crow_admin":
        # AD-5 dispatch: diagnostics/drift/prompt/backup/evolve/project_info
        if arguments.get("action") == "evolve":
            return {"proposal": "RULE: Prefer early return guards in all async functions.",
                    "confidence": 0.91, "requires_human_approval": True}
        return crow.diagnostics() if arguments.get("action") == "diagnostics" else {}
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### C.2 Dual Transport (SSE + Streamable HTTP)

For multi-client safety, run the server in **dual mode** so multiple clients (Zoo Code, etc.) share a single `crow.bin`:

```bash
python crow_mcp_server.py --transport dual --port 9020 --http-port 9021
```

This launches two Uvicorn servers — one for SSE (`/sse`) and one for Streamable HTTP — using a single `CrowMemory` instance. All reads and writes are serialized through the same process, eliminating race conditions.

> ⚠️ **Do not use stdio mode with multiple editors.** Each editor spawns its own `crow_mcp_server.py` process, and concurrent writes to `crow.bin` will cause silent data loss. Always use SSE or dual mode for multi-client setups.

---

## 12. Fork Files & State Tagging

### 12.1 `-myk1yt` Consolidation (v1.5.0-mcp)

All `-myk1yt` file copies (docs, code shims, bats, requirements) have been **fully merged into the canonical originals and removed** — the untagged files are the single source of truth.

The `-myk1yt` **data files** under `memory/` remain as a **historical archive snapshot** — the active memory is the untagged set (`memory/crow.bin`, `memory/value_bank.json`).

### 12.2 `CROW_STATE_TAG` (AD-8.2)

[`crow_mcp_server.py`](crow_mcp_server.py) `resolve_state_path()` honors the `CROW_STATE_TAG` environment variable: when set (e.g. `myk1yt`), the default state path `memory/crow.bin` becomes `memory/crow-<tag>.bin`. This enables intentional isolated instances.

**Current status: no tag is in use.** [`start_crow_sse.bat`](start_crow_sse.bat) had a tag set briefly (in the now-removed fork copy), then it was removed — file timestamps proved the live state is `memory/crow.bin`. Set `CROW_STATE_TAG` only when a deliberately isolated instance is needed.

---

## 13. Version History

| Version | Date | Change |
|---------|------|--------|
| 1.4.2 | 2026-06-01 | 8-register spec, i18n, REST API documentation |
| 1.4.5 | 2026-08-30 | MCP SDK 2.1.1 migration (`MCPServer` high-level API) |
| 1.5.0-mcp | 2026-09-02 | **Recall precision overhaul**: `crow_sanitize.py` sanitize gate, `SIM_CUTOFF` 0.35 (env-overridable), `recall_multi()` global eff_sim merge, project tagging (`project`/`strict_project`), importance boost cap ×1.15, `NEG_DAMPEN_BY_REGISTER`, sha256 encode-cache keys. **AD-5 tool consolidation**: 10 → 3 tools (`crow_recall`/`crow_ingest`/`crow_admin`). Fork files converted to re-export shims. Maintenance scripts (`migrate_value_bank`, `merge_value_bank`, `purge_search_debris`) with dry-run default. 231 tests. |
| 1.5.0 | 2026-11-24 | **Serverless rewrite (current)**: `core/crow_db.py` SQLite WAL + FTS5 engine replaces the matrix daemon; BM25 + token-cosine scoring; signed `polarity_net`; half-life effective importance; grace shield and register quotas; semantic upsert; 2-Tier bias block; lifecycle hook adapters for Antigravity/Kimi/Claude/Cursor/Cline plus universal `AGENTS.md`; optional stdlib stdio MCP (`2025-03-26`); one-click installer; 96 locales; `migrate_from_v1.py`. |

*Note: the version table is chronological. §2 onward describes the 1.5.0-mcp engine; the serverless architecture chapter appears earlier in this document.*

---

*End of Document.*
*Crow remembers not the code, but the hand that wrote it.*
