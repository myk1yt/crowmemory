# 🏗️ Architect Task Report — Crow Memory Recall Precision Improvement (P3)

## Task Summary
Architecture design covering all 12 requirements (REQ-001~REQ-012) for recall noise removal, sanitization, project tagging, tool consolidation 10→3, two bug fixes, and the fork strategy decision.

## Scope Authority
- Spec: [`requirement-checklist.md`](docs/260901_0001_session_crow-recall-precision/requirement-checklist.md)
- Decisions: [`decisions.md`](docs/260901_0001_session_crow-recall-precision/decisions.md) — global-only storage, kaomoji in noise scope, full pipeline approved
- Source of truth audited: [`crow_core.py`](crow_core.py), [`crow_mcp_server.py`](crow_mcp_server.py), [`crow_i18n.py`](crow_i18n.py), [`CROW_MEMORY_ARCHITECTURE.md`](CROW_MEMORY_ARCHITECTURE.md)

---

# [1. Technical Specification]

## 1.0 Goals
1. Recall returns only real, relevant memories. No fabricated fallback hints. Higher base cutoff. Bounded importance boost.
2. Kaomoji/symbol/jamo garbage scrubbed at ingest gate, at recall display, and retroactively from the existing 500-entry value_bank.
3. Project-aware recall on a **single global** state file, via value_bank tagging + similarity adjustment only. No file splitting.
4. MCP surface reduced from 10 tools to 3 without losing capability.
5. Fix encode-cache collision and per-register NEG_DAMPEN.
6. Resolve the `-myk1yt` fork ambiguity with a single authoritative source.

## 1.1 Core Constraints (non-negotiable)
- Python stdlib + existing deps only (`numpy`, `safetensors`, `faiss` optional, `sentence_transformers`). No new runtime dependencies. The sanitizer is pure-regex `re` (stdlib).
- Backward-compatible value_bank JSON: new fields optional, old entries treated as global/untagged.
- No change to register decay λ or the weight-matrix update math (`S *= lam; S += outer(k,v)*(1-lam)*polarity`).
- All 8 registers remain.
- User rejected physical per-workspace isolation. Project awareness is metadata-only.

## 1.2 Data Flow (current → target)

### Recall path (the FE↔BE boundary here is MCP tool ↔ [`CrowMemory`](crow_core.py:131))
```
LLM tool call crow_recall
  → crow_mcp_server._recall()          [aggregation, domain=all merge]   (REQ-004, REQ-009)
  → CrowMemory.recall(query, register) [S^T q, confidence]
  → CrowMemory._nearest_hints()        [cutoff, boost cap, fallback]    (REQ-001/002/003/008)
  → sanitizer.scrub_display(hint)      [display-time clean]             (REQ-006)
  → JSON text back to LLM
```

### Ingest path
```
LLM tool call crow_ingest
  → crow_mcp_server._ingest()          [auto-polarity if exit_code given] (REQ-009)
  → sanitizer.scrub_text(key/value)    [ingest gate, BEFORE encode]       (REQ-005)
  → CrowMemory.ingest()                [encode, EMA, value_bank append]
  → value_bank entry += project field                                    (REQ-008)
```

### Migration path (one-time, offline)
```
scripts/migrate_value_bank.py
  → load value_bank.json
  → scrub_text(key,value) per entry    (REQ-007)
  → re-encode vectors via CrowMemory.encode
  → rebuild FAISS indexes
  → atomic write (backup first)
```

## 1.3 Type / Schema Definitions

### value_bank entry (JSON) — additive change
```jsonc
{
  "key": "string (<=500 chars, scrubbed)",
  "value": "string (<=1000 chars, scrubbed)",
  "vector_b64": "base64 float16[]",
  "register": "style|bug|arch|context|life_pref|life_avoid|life_phil|life_context",
  "timestamp": 1712345678.0,
  "importance": 1.0,
  "ingest_count": 1,
  "project": "string | null"          // NEW (REQ-008). null/absent = global. OPTIONAL.
}
```
Backward compatibility rule: any reader MUST use `entry.get("project")` and treat `None`/missing as global. Old entries require no rewrite except the one-time migration (which preserves the field as absent → null).

### Runtime config (env vars, read once at server start)
| Env var | Default | Meaning |
|---|---|---|
| `CROW_SIM_CUTOFF` | `0.35` | Base similarity floor for a hint to be shown (REQ-002) |
| `CROW_SIM_CUTOFF_CROSS_PROJECT` | `CROW_SIM_CUTOFF + 0.07` | Stricter floor for entries tagged with a different project (REQ-008) |
| `CROW_PROJECT_BOOST` | `1.05` | Same-project similarity multiplier, applied inside the ×1.15 total cap (REQ-008) |
| `CROW_STATE_TAG` | `""` | Optional state-file suffix selector for fork unification (REQ-012) |

---

# [2. Architecture Decisions]

## AD-1: Sanitizer lives in a NEW module `crow_sanitize.py` (not inside crow_core)
**Decision.** Create [`crow_sanitize.py`](crow_sanitize.py). [`crow_core.py`](crow_core.py) imports and calls it at the ingest gate and at hint-render time.

**Why not inside crow_core.** crow_core is weight math + persistence. The sanitizer is a pure text→text function with its own pattern table and unit tests. Isolating it keeps crow_core's diff small (lower regression risk on the math path), makes the patterns independently testable, and lets the migration script import the same function without instantiating `CrowMemory` (which acquires a file lock).

### Sanitizer pattern design (conservative — REQ-005/006)
Single public function plus a display alias:
```python
def scrub_text(text: str) -> str: ...
def scrub_display(text: str) -> str: ...   # == scrub_text; alias for call-site clarity
```
Ordered, conservative rules. Each rule is compiled once at module load. The design principle: **remove only what is unambiguously noise, never restructure prose.**

| # | Rule (regex, `re.UNICODE`) | Removes | Protects |
|---|---|---|---|
| 1 | Emoji/Symbol blocks `[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]` | emoji, pictographs | ASCII, CJK, Hangul |
| 2 | Lone jamo laughter/tilde runs `[ㄱ-ㅎㅏ-ㅣ~^]{2,}` | ㅋㅋㅋ, ㅠㅠ, ㅎㅎ, ~~~, ^^^ | single ㅋ inside words is left; composed Hangul syllables (가-힣) are NOT in the lone-jamo range, so Korean words are safe |
| 3 | Kaomoji runs: sequences of ≥2 face-glyphs from a small set (`>.<`, `o_o`, `0v0`, `T_T`, `><`, `._.` style) — implemented as `(?:[>oO0Tt][._-]?[<oO0vV])+` style class, plus explicit literal list | `>.<`, `0v0`, `T_T` | normal words |
| 4 | Repeated punctuation ≥3 → collapse to 2: `([!?.,*])\1{2,}` → `\1\1` | `!!!`, `???`, `....`→`..` | `...` collapses to `..`? No — see edge note |
| 5 | Whitespace normalization: `[ \t]+`→` `, leading/trailing strip, 3+ newlines → 2 | runs of spaces | single newlines |

**Edge cases the implementation MUST honor (audit-ready, for `ask`):**
- `C++` MUST survive: rule 4 operates on `[!?.,*]` only, `+` is excluded. Test: `scrub_text("C++ and C#") == "C++ and C#"`.
- `...` (ellipsis) — decision: collapse `....+` (4+) → `...`; exactly-3 dots preserved. Implement rule 4 as `([!?.,*])\1{3,}` → `\1\1\1` for `.`, and `([!?*])\1{2,}` → `\1\1` for the others. This keeps "..." intact while killing "!!!!". Test both.
- Code identifiers (`snake_case`, `camelCase`, `foo.bar()`) contain no targeted glyphs → untouched. Test: `scrub_text("use abort_signal.link()")` unchanged.
- Korean prose (`"이 패턴은 항상 실패한다"`) — composed syllables, untouched.
- A value that is **only** noise (`">.< ㅋㅋㅋ"`) scrubs to `""`. Ingest gate behavior: if `scrub_text(value)` is empty after scrub, the ingest is **rejected** with `{status:"rejected", reason:"empty_after_sanitize"}` rather than storing an empty memory. (Prevents embedding-space pollution by a null vector.)

## AD-2: Recall noise removal (REQ-001/002/003) — `_nearest_hints` rewrite
Location: [`CrowMemory._nearest_hints()`](crow_core.py:283).

- **REQ-001 (fabricated fallback):** Delete both `return [f"Crow recalls a faint {register} bias..."]` sites ([`crow_core.py:289`](crow_core.py:289), [`crow_core.py:309`](crow_core.py:309)). Return `[]`. Confidence=0 (already returned by [`recall()`](crow_core.py:276)) is the "no match" signal. Callers handle empty hints.
- **REQ-002 (cutoff):** Replace hardcoded `0.28` with module constant `SIM_CUTOFF = float(os.environ.get("CROW_SIM_CUTOFF", "0.35"))`. **Remove the importance backdoor** `or (importance > 5.0 and sim > 0.15)` — the minimum acceptable raw sim must not fall below the base cutoff.
- **REQ-003 (boost cap):** `importance_boost = min(1.0 + 0.12*math.log(max(importance,0.1)+1.0), 1.15)`. Acceptance check `effective_sim = sim * importance_boost > SIM_CUTOFF`.

New acceptance logic (single place, also the project-boost hook for REQ-008):
```python
def _accept(sim, importance, entry_project, query_project) -> tuple[bool, float]:
    boost = min(1.0 + 0.12*math.log(max(importance,0.1)+1.0), 1.15)   # REQ-003 cap
    if query_project and entry_project == query_project:
        boost = min(boost * PROJECT_BOOST, 1.15)                        # REQ-008 same-project
    cutoff = SIM_CUTOFF
    if query_project and entry_project not in (None, query_project):
        cutoff = CROSS_PROJECT_CUTOFF                                   # REQ-008 stricter
    eff = sim * boost
    return (sim >= BASE_MIN and eff > cutoff), eff   # BASE_MIN == SIM_CUTOFF; backdoor gone
```

## AD-3: domain=all aggregation fix (REQ-004) — server-side
Location: [`crow_mcp_server._recall()`](crow_mcp_server.py:75) and the [`/recall`](crow_mcp_server.py:470) REST route.

Current bug: per-register loop calls `recall(..., top_k // 8)` (→ 0 for top_k=2, clamped to 1), concatenates in fixed register order, slices `[:top_k]` — so low-sim hints from early registers crowd out high-sim hints from later ones, and empty registers inject fallback fillers.

Fix design — add a **single** core method that does the merge correctly, so both MCP and REST share it:
```python
# crow_core.py
def recall_multi(self, query, registers, top_k, project=None) -> dict:
    """Query each register, merge ALL candidate hints globally by effective
    similarity desc, slice top_k. Skip registers with zero accepted hints.
    Only registers that produced ≥1 hint are tracked in recall_stats."""
    # returns {"hints": [...], "confidence": weighted_avg, "registers_hit": [...]}
```
- (a) registers with no accepted hints contribute nothing (REQ-001 makes this natural — they return `[]`).
- (b) merge is by `effective_sim` across registers, not register order. `_nearest_hints` must therefore return `(text, eff_sim)` pairs internally; the public `recall()` keeps returning strings for backward compat, `recall_multi` uses the pairs. Implement by having `_nearest_hints` return `list[dict{"text","sim"}]` and `recall()` formatting to strings.
- (c) `recall_stats` pollution: only call `_track_recall` for registers in `registers_hit`. Confidence for the merged result = importance-weighted mean of hit registers (not ÷8).

## AD-4: Project tagging (REQ-008) — metadata-only, global file
**Slug computation** (from workspace path), in `crow_sanitize.py` or a tiny `crow_project.py`:
```python
def project_slug(workspace_path: str | None) -> str | None:
    if not workspace_path: return None
    base = os.path.basename(os.path.normpath(workspace_path))
    slug = re.sub(r'[^a-z0-9_-]+', '-', base.lower()).strip('-')
    return slug or None
```
Explicit `project` param on the tool overrides the derived slug; if the param is absent the server derives it from the client's workspace path when available, else `None` (global).

**Recall behavior** (with AD-2's `_accept`):
- untagged entry (`project=None`) → always eligible at base cutoff (global memory).
- same-project entry → boost ×1.05 (capped within ×1.15 total).
- cross-project entry → stricter cutoff `CROW_SIM_CUTOFF_CROSS_PROJECT`.
- optional tool param `strict_project: bool = False` → when true, hard-filter cross-project entries (not just stricter cutoff).

**Weight matrix S stays global/unchanged.** Only value_bank entries carry the tag; the Hebbian math is untouched (satisfies the λ/update-math constraint).

## AD-5: Tool consolidation 10→3 (REQ-009)
Three tools. Exact schemas below. `crow_i18n.py` `_BASE_TOOL_DEFINITIONS` is replaced to match, and each `i18n/*.json` gains `tools.crow_admin.*` keys (English fallback covers the rest until translated).

### Tool 1 — `crow_recall`
```jsonc
{ "name": "crow_recall",
  "inputSchema": { "type":"object",
    "properties": {
      "query": {"type":"string"},
      "register": {"type":"string","enum":["style","bug","arch","context","life_pref","life_avoid","life_phil","life_context","all"]},
      "domain": {"type":"string","enum":["code","life","all"],"default":"all"},
      "top_k": {"type":"integer","default":2,"minimum":1,"maximum":5},
      "format": {"type":"string","enum":["hint","bias_block"],"default":"hint"},  // absorbs crow_get_user_bias
      "project": {"type":"string"},                                               // REQ-008
      "strict_project": {"type":"boolean","default":false}                        // REQ-008
    },
    "required": ["query"] } }
```
`format="bias_block"` routes to [`get_user_bias_block()`](crow_core.py:929) and returns the `[User Bias]` text block instead of JSON hints.

### Tool 2 — `crow_ingest`
```jsonc
{ "name": "crow_ingest",
  "inputSchema": { "type":"object",
    "properties": {
      "key": {"type":"string"}, "value": {"type":"string"},
      "register": {"type":"string","enum":[8 registers]},
      "polarity": {"type":"number"},                  // optional now
      "exit_code": {"type":"integer"},                // absorbs crow_ingest_from_build
      "user_edited": {"type":"boolean","default":false},
      "project": {"type":"string"}
    },
    "required": ["key","value","register"] } }
```
Polarity resolution order: explicit `polarity` → (if `exit_code` present) auto map `{0:{edited?+0.5:+1.5}, nonzero:{edited?-1.0:-0.5}}` via existing [`ingest_from_build()`](crow_core.py:727) logic → error if neither given.

### Tool 3 — `crow_admin`
```jsonc
{ "name": "crow_admin",
  "inputSchema": { "type":"object",
    "properties": {
      "action": {"type":"string","enum":["diagnostics","drift","prompt","backup","evolve","project_info"]},
      "args": {"type":"object"}   // action-specific passthrough
    },
    "required":["action"] } }
```
Dispatch table (reuses existing handlers verbatim):
| action | maps to former tool | handler |
|---|---|---|
| `diagnostics` | crow_diagnostics | [`_diagnostics`](crow_mcp_server.py:124) |
| `drift` | crow_check_drift | [`_drift`](crow_mcp_server.py:130) |
| `prompt` | crow_manage_prompt | [`_manage_prompt`](crow_mcp_server.py:156) (`args.action` read/append/stats) |
| `backup` | crow_manage_backup | [`_manage_backup`](crow_mcp_server.py:171) |
| `evolve` | crow_evolve_propose | [`_evolve`](crow_mcp_server.py:116) |
| `project_info` | crow_project_info | [`_project_info`](crow_mcp_server.py:189) |

**REST parity:** [`/health`](crow_mcp_server.py:444), [`/ingest`](crow_mcp_server.py:453), [`/recall`](crow_mcp_server.py:470) are unaffected by consolidation (they call core directly). `/recall` is updated to use `recall_multi` (AD-3) and accept optional `project` query param. `/ingest` routes through the scrub gate (AD-1).

**Backward compat for AGENTS.md tool tables:** [`AGENTS.md`](AGENTS.md) documents the 10-tool table. Decision: update AGENTS.md to the 3-tool table **in the docs batch** (it is documentation, not runtime). No runtime shim — the 7 removed tool names are gone from the schema. Risk noted in §Risks; agents with cached old prompts will get "unknown tool" until their instructions refresh.

## AD-6: Encode cache key (REQ-010)
[`encode()`](crow_core.py:230): cache key is currently `truncated[:200]` — two different texts sharing a 200-char prefix collide. Fix: `cache_key = hashlib.sha256(truncated.encode("utf-8")).hexdigest()`. `hashlib` already imported. Cache size/eviction unchanged.

## AD-7: Per-register NEG_DAMPEN (REQ-011)
Replace scalar `NEG_DAMPEN = 0.6` with:
```python
NEG_DAMPEN_DEFAULT = 0.6
NEG_DAMPEN_BY_REGISTER = {"bug": 1.0, "life_avoid": 1.0}   # failure-memory registers undamped
```
In [`ingest()`](crow_core.py:316): `dampen = NEG_DAMPEN_BY_REGISTER.get(register, NEG_DAMPEN_DEFAULT)`; apply when `polarity < 0`. Rationale: `bug`/`life_avoid` exist to remember failures; damping them to 0.6 weakens exactly the signal they are for.

## AD-8: Fork strategy (REQ-012) — UNIFY, single source
**Findings (audited this session):**
- [`crow_mcp_server.py`](crow_mcp_server.py) ≡ [`crow_mcp_server-myk1yt.py`](crow_mcp_server-myk1yt.py): byte-identical.
- [`crow_core.py`](crow_core.py) vs [`crow_core-myk1yt.py`](crow_core-myk1yt.py): differ only in a docstring version string.
- [`start_crow_sse-myk1yt.bat`](start_crow_sse-myk1yt.bat) itself launches **crow_mcp_server.py** (the non-suffixed file).
- Two data state sets exist; `value_bank-myk1yt.json` is at the 500-entry cap and is the live set per REQ-012.

**Conclusion:** the `-myk1yt` suffix is a user-instance **branding/sync artifact** (~20 files: AGENTS, README, CHANGELOG, requirements, bat), not a functional code fork. Maintaining two identical code files is pure drift risk.

**Decision — Option B (pragmatic, least-risky): single authoritative code source + data-path parameterization.**
1. **Code:** [`crow_core.py`](crow_core.py) and [`crow_mcp_server.py`](crow_mcp_server.py) are the ONLY edited files. The `-myk1yt` code copies become thin shims that re-export the canonical module (`from crow_core import *` / a 3-line `runpy` wrapper for the server), preserving any external reference to the `-myk1yt` filename without duplicating logic. (Alternative A — delete the `-myk1yt` code files outright — is riskier: unknown external scripts may invoke them. Rejected as irreversible without a usage audit.)
2. **Data:** add `--state` resolution that honors `CROW_STATE_TAG`. When `CROW_STATE_TAG=myk1yt`, default state path becomes `memory/crow-myk1yt.bin` and value_bank/recall_stats resolve to their `-myk1yt` siblings. This makes the **existing live `-myk1yt` data set** the authoritative one without renaming/migrating files, and keeps a plain `crow.bin` usable for a fresh instance. Set `CROW_STATE_TAG=myk1yt` in [`start_crow_sse-myk1yt.bat`](start_crow_sse-myk1yt.bat) (and the non-suffixed bat leaves it unset). No data loss, no file moves.
3. The non-code `-myk1yt` docs (README/CHANGELOG/AGENTS) are left as-is — out of scope for this task.

## Risks & Edge Cases
| Risk | Mitigation |
|---|---|
| Removing 7 tools breaks agents with cached instructions | Documented in AGENTS.md update; `crow_admin` covers all removed functions |
| Sanitizer false-positives on legit text | Conservative patterns + unit tests for C++/ellipsis/identifiers/Korean (AD-1) |
| Migration re-encode changes recall behavior | Backup value_bank + FAISS before run; migration is idempotent & dry-run capable |
| Empty-after-scrub ingest | Rejected with explicit status (AD-1) |
| `recall_multi` changes confidence semantics | Document: merged confidence = weighted mean over hit registers only |
| Cross-project boost could starve global memories | Untagged entries always eligible at base cutoff; boost capped ×1.15 |

---

# [3. Implementation Plan]

5 independent sub-tasks. **No two batches edit the same file** (no-same-file-conflict rule). File ownership is exclusive per batch.

## Batch A — Sanitizer module (foundation, no core edits)
- **Create:** [`crow_sanitize.py`](crow_sanitize.py) — `scrub_text`, `scrub_display`, `project_slug`, compiled pattern table.
- **Prereq:** none.
- **Tests:** `tests/test_sanitize.py` — pattern matrix: kaomoji runs, lone jamo, ≥3 punctuation, emoji, whitespace; protection cases: `C++`, `C#`, `...`, `snake_case`/`foo.bar()`, Korean prose, empty-after-scrub → `""`.
- **CLI:** `python -m pytest tests/test_sanitize.py -v` (or `python tests/test_sanitize.py` if no pytest — use plain `unittest`).

## Batch B — Core recall/ingest fixes (crow_core only)
- **Modify:** [`crow_core.py`](crow_core.py) — REQ-001 (drop fallbacks), REQ-002 (`SIM_CUTOFF` env, remove backdoor), REQ-003 (×1.15 cap), REQ-008 (`recall(..., project=None)`, `_accept`, `recall_multi`, untagged=global), REQ-010 (sha256 cache key), REQ-011 (per-register NEG_DAMPEN), ingest-gate + display scrub hooks (import from crow_sanitize), value_bank `project` field in [`_append_value_bank()`](crow_core.py:410).
- **Prereq:** Batch A (imports crow_sanitize).
- **Tests:** `tests/test_recall_precision.py` — cutoff boundary (0.34 rejected / 0.36 accepted at default), no fabricated hint on empty bank, boost cap at ×1.15 (importance=1e6 → boost ≤1.15), cache-key collision (two texts, same 200-prefix, different vectors), NEG_DAMPEN: `bug` polarity −1 → applied −1.0, `style` −1 → −0.6, project same/cross/strict logic.
- **CLI:** `python -m pytest tests/test_recall_precision.py -v`

## Batch C — Server + i18n consolidation (crow_mcp_server + crow_i18n + i18n json)
- **Modify:** [`crow_mcp_server.py`](crow_mcp_server.py) — 3 tools (AD-5), `crow_admin` dispatch, `_recall`→`recall_multi`, project/strict_project params, REST `/recall` project param + `/ingest` scrub, `CROW_STATE_TAG` state resolution.
- **Modify:** [`crow_i18n.py`](crow_i18n.py) — `_BASE_TOOL_DEFINITIONS` → 3 tools; `i18n/en.json` + `i18n/ko.json` add `tools.crow_admin.*`, `tools.crow_recall.parameters.format/project/strict_project`, `tools.crow_ingest.parameters.exit_code/user_edited/project`. Other 34 locales fall back to `en`.
- **Prereq:** Batch B (calls `recall_multi`, project params).
- **Tests:** `tests/test_tool_schema.py` — exactly 3 tools registered; `crow_recall` accepts `format=bias_block`; `crow_ingest` auto-polarity from `exit_code`; `crow_admin` each action dispatches; unknown action → error; i18n `get_tool_definitions()` returns 3 tools with `crow_admin` description.
- **CLI:** `python -m pytest tests/test_tool_schema.py -v`

## Batch D — Migration script (standalone, offline)
- **Create:** [`scripts/migrate_value_bank.py`](scripts/migrate_value_bank.py) — load `value_bank(-myk1yt).json`, `scrub_text` key+value, re-encode via `CrowMemory.encode`, rebuild FAISS, atomic write. Flags: `--dry-run`, `--state-tag`. Backup before write.
- **Prereq:** Batch A (sanitizer). Independent of B/C at runtime but logically after.
- **Tests:** `tests/test_migrate.py` — dry-run makes no changes; kaomoji entry cleaned; vector re-encoded (dim matches); backup file created; idempotent on second run.
- **CLI:** `python -m pytest tests/test_migrate.py -v` then manual `python scripts/migrate_value_bank.py --state-tag myk1yt --dry-run`

## Batch E — Docs + AGENTS.md + fork shims
- **Modify:** [`AGENTS.md`](AGENTS.md) — 10-tool table → 3-tool table.
- **Modify:** [`crow_core-myk1yt.py`](crow_core-myk1yt.py), [`crow_mcp_server-myk1yt.py`](crow_mcp_server-myk1yt.py) — convert to re-export shims.
- **Modify:** [`start_crow_sse-myk1yt.bat`](start_crow_sse-myk1yt.bat) — set `CROW_STATE_TAG=myk1yt`.
- **Prereq:** B, C.
- **Tests:** manual — launch server via bat, `GET /health` 200, `crow_admin diagnostics` returns stats against `crow-myk1yt.bin`.

## Batch order for VP
A → B → C (strict chain, A and B and C touch disjoint files but are logically sequential) → D and E can run in parallel after C. Batches touch these files exactly once: A(crow_sanitize), B(crow_core), C(server+i18n), D(migration script), E(docs+shims+bat). Zero file overlap between batches.

## Result
Success — full architecture for REQ-001~REQ-012 delivered.

## Issues Discovered
- Two live data state sets (plain + `-myk1yt`); resolved via `CROW_STATE_TAG` rather than file migration (AD-8).
- `_recall` `top_k // 8` yields 0 for default top_k=2 — root cause of the aggregation noise, fixed by `recall_multi`.

## Next Step Recommendations
- VP: dispatch Batch A → B → C to `code`, D+E after C. Run `security-reviewer` after C (tool-schema/auth surface change). `ask` gate uses the audit-ready edge cases in AD-1/AD-2.

## Affected File List
- Create: `crow_sanitize.py`, `scripts/migrate_value_bank.py`, `tests/test_sanitize.py`, `tests/test_recall_precision.py`, `tests/test_tool_schema.py`, `tests/test_migrate.py`
- Modify: `crow_core.py`, `crow_mcp_server.py`, `crow_i18n.py`, `i18n/en.json`, `i18n/ko.json`, `AGENTS.md`, `crow_core-myk1yt.py` (shim), `crow_mcp_server-myk1yt.py` (shim), `start_crow_sse-myk1yt.bat`
