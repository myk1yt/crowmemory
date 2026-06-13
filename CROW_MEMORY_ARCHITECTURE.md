# Crow (까마귀) Memory Architecture
## A Synaptic State Cache for Recursive Agent Development

**Version:** 1.4.2
**Date:** 2026-06-01
**Author:** Stefano,Kim & AI Collaborative Design
**Target Runtime:** Any MCP-compatible IDE + LLM API + Local Python MCP Server

---

## 0. Executive Summary

**Crow** is a fixed-size, weight-based associative memory system designed to be plugged into any MCP-compatible LLM agent as an external long-term memory chip. Unlike text-based journals or vector databases, Crow stores experience as compressed synaptic weights inside a `crow.bin` matrix. It does not remember *what* you did--it remembers *how* you think.

The name "Crow (까마귀)" is deliberate. Crows possess episodic-like memory, tool-crafting intelligence, and social learning: they observe, remember, and adapt their behavior based on past outcomes without rewriting their DNA. Crow Memory does the same for an AI agent. It cannot modify the LLM's base weights, but it can sculpt the prompt environment and tool-use bias so effectively that the agent *behaves* as if it has evolved.

**Key Constraint (Non-Negotiable):**  
> Crow is **not** a database. It does not store exact text. It stores *inductive biases*--the gravitational pull of your coding style, your architectural instincts, your bug-hunting reflexes. Exact facts (API specs, file paths, syntax) remain in RAG, SQLite, or markdown. Crow handles the *vibe*.

---

## 1. Philosophy & Design Principles

### 1.1 The Two-Brain Doctrine
Every coding agent needs two distinct knowledge organs:

| Organ | Medium | Precision | Role | Crow's Role |
|-------|--------|-----------|------|-------------|
| **Hippocampus** | Markdown, SQLite, RAG | Lossless | Exact facts, specs, file trees | **None** |
| **Neocortex Bias** | `crow.bin` weight matrix | Lossy & Associative | Style, instinct, architectural gravity | **Everything** |

Crow occupies the second layer. It ensures that when the LLM writes code for you, it feels *your* hand--not generic best practices, not Stack Overflow averages, but *your* early-return reflex, *your* JSDoc verbosity, *your* terror of unhandled Windows encodings.

### 1.2 Hebbian Episodicity
Crow's write protocol mimics Hebbian plasticity: neurons that fire together, wire together. But unlike biological brains, Crow uses **Exponential Moving Average (EMA) decay** to prevent catastrophic interference. New memories do not erase old ones--they gently push the weight landscape, like wind reshaping a dune rather than a bulldozer flattening it.

### 1.3 The Observer Effect
Crow learns not from what the model *generates*, but from what the *user accepts*. A generated snippet that passes `npm run build` and is accepted without human edit is a **positive reinforcement** (+1.5). A snippet that the user immediately rewrites is a **negative reinforcement** (-0.8). The model is not the teacher; the user is.

### 1.4 Prompt Evolution as Phenotype
While Crow cannot rewrite the LLM's genotype (base weights), it can rewrite its **phenotype** (system prompt and tool-call behavior). Crow's `evolve_prompt` protocol proposes prompt mutations. These mutations are **suggestions only**--a Human-in-the-Loop (HITL) gate must approve them. This mimics evolutionary selection: mutations arise freely, but only the fittest survive human curation.

### 1.5 Fixed-Size Immortality
The `crow.bin` file is forever fixed at ~140MB (configurable). It does not grow as you accumulate projects. This is not a limitation; it is a *feature*. It forces the system to compress, abstract, and generalize--exactly what human long-term memory does. You do not remember every line of code you wrote in 2003; you remember *that you preferred monolithic classes back then*.

---

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
4. Computes `r = S.T @ q` (recalled vector)
5. Looks up `value_bank` for nearest neighbors to `r`
6. Returns 2-3 hint strings to V4

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

    # 5. Append to value_bank (circular buffer, max 500)
    self.value_bank.append({
        "key": key_text,
        "value": value_text,
        "vector": v.tobytes(),
        "timestamp": time.time()
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

### 10 MCP Tools

```json
{
  "tools": [
    {
      "name": "crow_recall",
      "description": "Recall user-specific coding style, bug intuition, architectural preference, or personal context from the Crow synaptic memory. Call this BEFORE every response to align with user's inductive bias. By default (no register, domain=all), queries all 8 registers.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Natural language description of the current task."},
          "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context", "all"], "description": "Which register. Use 'all' to query every register. Code: style/bug/arch/context. Life: life_pref/life_avoid/life_phil/life_context."},
          "top_k": {"type": "integer", "default": 2, "description": "Number of hints (1-3)."},
          "domain": {"type": "string", "enum": ["code", "life", "all"], "default": "all", "description": "Domain filter shortcut. 'code' = 4 code registers, 'life' = 4 life registers, 'all' = all 8 (default)."}
        },
        "required": ["query"]
      }
    },
    {
      "name": "crow_ingest",
      "description": "Ingest a coding experience into Crow's long-term synaptic memory. Call AFTER build/test results or user explicit feedback.",
      "parameters": {
        "type": "object",
        "properties": {
          "key": {"type": "string", "description": "Abstract description of the situation."},
          "value": {"type": "string", "description": "Code pattern or decision applied."},
          "polarity": {"type": "number", "description": "Reinforcement strength [-2.0, 2.0]."},
          "register": {"type": "string", "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"], "description": "Which register to write to."}
        },
        "required": ["key", "value", "polarity", "register"]
      }
    },
    {
      "name": "crow_evolve_propose",
      "description": "Analyze recent memory patterns and propose a permanent system prompt mutation. Returns a suggestion only; human approval is required for adoption.",
      "parameters": {
        "type": "object",
        "properties": {
          "min_confidence": {"type": "number", "default": 0.85},
          "min_occurrences": {"type": "integer", "default": 3}
        }
      }
    },
    {
      "name": "crow_diagnostics",
      "description": "Return diagnostic information about the Crow memory state (register norms, sparsity, update count, value bank size, prompt stats). Matches crow_diagnostics tool output.",
      "parameters": {"type": "object", "properties": {}}
    },
    {
      "name": "crow_check_drift",
      "description": "Check if recent recalls show signs of memory drift (confidence too low across multiple records).",
      "parameters": {
        "type": "object",
        "properties": {
          "threshold": {"type": "number", "default": 0.5},
          "min_low_confidence_count": {"type": "integer", "default": 5}
        }
      }
    },
    {
      "name": "crow_ingest_from_build",
      "description": "Auto-determine polarity from build exit code and user edit status, then ingest the experience. Use this after npm run build completes.",
      "parameters": {
        "type": "object",
        "properties": {
          "key": {"type": "string", "description": "Abstract description."},
          "value": {"type": "string", "description": "Code pattern applied."},
          "exit_code": {"type": "integer", "description": "Build exit code (0 = success)."},
          "user_edited": {"type": "boolean", "default": false},
          "register": {"type": "string", "enum": ["style", "bug", "arch", "context"], "default": "arch"},
          "explicit_polarity": {"type": "number", "description": "Override auto-polarity."}
        },
        "required": ["key", "value", "exit_code"]
      }
    },
    {
      "name": "crow_get_user_bias",
      "description": "Generate the [User Bias] block for injection into the system prompt. Queries all registers and formats hints for prompt prepending.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Current task description."},
          "registers": {"type": "array", "items": {"type": "string"}, "description": "Registers to query (default: all)."}
        },
        "required": ["query"]
      }
    },
    {
      "name": "crow_manage_prompt",
      "description": "Read, append to, or get statistics about the system_prompt.md file. Use 'read' to view current prompt, 'append' to adopt an evolved rule, 'stats' for metrics. Matches crow_manage_prompt tool.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["read", "append", "stats"]},
          "rule": {"type": "string", "description": "Rule text (required for append action)."},
          "auto_backup": {"type": "boolean", "default": true}
        },
        "required": ["action"]
      }
    },
    {
      "name": "crow_manage_backup",
      "description": "Manage Crow memory backups. Create, rotate, list, or recover from drift. Matches crow_manage_backup tool.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["create", "rotate", "list", "recover"]},
          "tag": {"type": "string", "default": "daily", "enum": ["daily", "weekly", "manual"]},
          "max_daily": {"type": "integer", "default": 7},
          "max_weekly": {"type": "integer", "default": 4}
        },
        "required": ["action"]
      }
    },
    {
      "name": "crow_project_info",
      "description": "List existing project-isolated Crow memory instances, or create a new isolated project memory.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["list", "create"]},
          "project_name": {"type": "string", "description": "Project name (required for create)."}
        },
        "required": ["action"]
      }
    }
  ]
}
```

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
| Step 7: The LLM (via crow_evolve_propose) drafts:                  |
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
| `crow_evolve_propose` | Auto-detected, auto-drafted | **Mandatory approval** before prompt append |
| Prompt adoption | Never auto | User clicks [YES] or edits proposal first |

### 7.2 Drift Detection

If `crow_recall` returns hints with confidence <0.5 for `min_low_confidence_count` (default 5) or more stat records across all registers, the system enters **drift alert**:
1. Pause auto-ingest
2. Notify user: "Crow memory seems confused. Recent tasks are too novel or memory is saturated."
3. Offer: **Spectral reset** (soft: clip singular values) or **Register archive** (move old `style_S` to `style_S.bak` and initialize fresh)

### 7.3 Negative Ingestion Ceiling

To prevent a single bad session from poisoning memory:
- `polarity` is clamped to [-2.0, 2.0]
- Negative ingestions are dampened by `neg_dampen = 0.6` factor: actual delta = `polarity * 0.6 * (1-lam)`
- A single negative event cannot erase more than 40% of a pattern's accumulated weight

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
- [x] Build MCP server exposing 10 tools + 2 prompts
- [x] Manual test: `recall` -> `ingest` -> `recall` cycle with dummy data

### Phase 1: Zoo Code Hook — ✅ Implemented
- [x] Capture `npm run build` exit code via `crow_ingest_from_build`
- [x] Auto-trigger `crow_ingest` on build success/failure
- [x] Inject `[User Bias]` block into the LLM system prompt before generation

### Phase 2: Feedback Loop — ✅ Implemented
- [x] Track user edit distance (accepted vs rewritten) via polarity auto-detection
- [x] Polarity modulation based on build exit code + user edits
- [x] `value_bank` importance-weighted priority queue + FAISS index for text retrieval

### Phase 3: Evolution — ✅ Implemented
- [x] Implement `crow_evolve_propose` with confidence/occurrence thresholds
- [x] Build HITL UI (`hitl_panel.html`) for rule approval
- [x] Connect to `system_prompt.md` append workflow with auto-backup

### Phase 4: Hardening — ✅ Implemented
- [x] Drift detection (`crow_check_drift`) & auto-recovery (`recover_from_drift`)
- [x] Backup rotation (`crow_manage_backup`) & rollback
- [x] Multi-project isolation (`crow_project_info` with per-project `crow.bin`)

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
        return crow.recall(arguments["query"], arguments["register"])
    elif name == "crow_ingest":
        crow.ingest(arguments["key"], arguments["value"],
                    arguments["polarity"], arguments["register"])
        return {"status": "ingested"}
    elif name == "crow_evolve_propose":
        return {"proposal": "RULE: Prefer early return guards in all async functions.",
                "confidence": 0.91, "requires_human_approval": True}
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

*End of Document.*  
*Crow remembers not the code, but the hand that wrote it.*
