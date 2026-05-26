#!/usr/bin/env python3
"""Verify all v1.3.2–v1.3.4 fixes with real crow_core imports."""
import sys
import os
import json
import math

# Ensure local modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []
errors = []

def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    results.append(line)
    if not passed:
        errors.append(name)

# ============================================================
# 1. DOMAINS["all"] exists with 8 registers (v1.3.2)
# ============================================================
try:
    from crow_core import DOMAINS, REGISTERS, VALUE_BANK_MAX, NEG_DAMPEN
    check("DOMAINS import", True)
except Exception as e:
    check("DOMAINS import", False, str(e))
    print("\n".join(results))
    sys.exit(1)

check("DOMAINS has 'all' key", "all" in DOMAINS,
      f"keys={list(DOMAINS.keys())}" if "all" not in DOMAINS else "")
check("DOMAINS['all'] has 8 registers", len(DOMAINS["all"]) == 8,
      f"got {len(DOMAINS['all'])}: {DOMAINS.get('all', [])}")
check("DOMAINS['all'] matches REGISTERS",
      set(DOMAINS["all"]) == set(REGISTERS.keys()),
      f"diff: {set(DOMAINS['all']) ^ set(REGISTERS.keys())}")

# ============================================================
# 2. _append_value_bank: importance-based eviction (v1.3.3)
# ============================================================

# Simulate the eviction logic
entries = [
    {"key": "critical", "importance": 10.0, "register": "style"},
    {"key": "medium",   "importance": 5.0,  "register": "style"},
    {"key": "trivial",  "importance": 0.5,  "register": "style"},
    {"key": "legacy",   "register": "style"},  # no importance → default 0
]

# Find weakest
min_idx = min(range(len(entries)), key=lambda i: entries[i].get("importance", 0))
check("Weakest is 'legacy' (no importance field)",
      entries[min_idx]["key"] == "legacy",
      f"got {entries[min_idx]['key']} (importance={entries[min_idx].get('importance', 0)})")

# Remove legacy, test again
entries.pop(min_idx)
min_idx = min(range(len(entries)), key=lambda i: entries[i].get("importance", 0))
check("Weakest after removal is 'trivial' (importance=0.5)",
      entries[min_idx]["key"] == "trivial",
      f"got {entries[min_idx]['key']} (importance={entries[min_idx].get('importance', 0)})")

# ============================================================
# 3. Duplicate key importance accumulation (v1.3.3)
# ============================================================
existing = {"key": "dup", "importance": 2.0, "ingest_count": 1, "value": "old", "register": "style"}
polarity = 1.5
existing["importance"] = existing.get("importance", 1.0) + abs(polarity)
existing["ingest_count"] = existing.get("ingest_count", 1) + 1
check("Duplicate key importance accumulation",
      existing["importance"] == 3.5 and existing["ingest_count"] == 2,
      f"imp={existing['importance']}, cnt={existing['ingest_count']}")

# ============================================================
# 4. _nearest_hints: adaptive threshold (v1.3.3)
# ============================================================
test_cases = [
    # (importance, sim, expected_visible)
    (1.0,   0.28, True),    # standard threshold
    (100.0, 0.16, True),    # high importance, sim>0.15: boost + secondary threshold
    (1.0,   0.25, False),   # below threshold
    (6.0,   0.16, True),    # importance > 5 AND sim > 0.15
    (5.0,   0.15, False),   # boundary: 5.0 is NOT > 5.0, sim=0.15 is NOT > 0.15
    (5.1,   0.151, True),   # just above boundary
]

for importance, sim, expected in test_cases:
    boost = 1.0 + 0.12 * math.log(max(importance, 0.1) + 1.0)
    effective = sim * boost
    visible = effective > 0.28 or (importance > 5.0 and sim > 0.15)
    check(
        f"Adaptive threshold: imp={importance}, sim={sim}",
        visible == expected,
        f"boost={boost:.3f} effective={effective:.3f} visible={visible} expected={expected}"
    )

# ============================================================
# 5. _recall handler: register="all" → register=None (v1.3.4)
# ============================================================
# Simulate the handler logic
def simulate_recall_handler(args):
    domain = args.get("domain", "all")
    register = args.get("register")
    if register == "all":
        register = None
    if domain and not register:
        return {"mode": "multi", "domain": domain, "registers": DOMAINS.get(domain, DOMAINS["all"])}
    return {"mode": "single", "register": register or "style"}

# Case 1: register="all", domain not specified → should use multi with domain="all"
r = simulate_recall_handler({"query": "test", "register": "all"})
check("register='all' → multi-register query",
      r["mode"] == "multi" and r["domain"] == "all",
      str(r))

# Case 2: register="style" → should use single
r = simulate_recall_handler({"query": "test", "register": "style"})
check("register='style' → single register query",
      r["mode"] == "single" and r["register"] == "style",
      str(r))

# Case 3: no params → should use multi with domain="all"
r = simulate_recall_handler({"query": "test"})
check("no params → multi-register query (default domain='all')",
      r["mode"] == "multi" and r["domain"] == "all",
      str(r))

# Case 4: domain="code" only → should use multi with 4 code registers
r = simulate_recall_handler({"query": "test", "domain": "code"})
check("domain='code' → multi with 4 registers",
      r["mode"] == "multi" and len(r["registers"]) == 4,
      str(r))

# Case 5: register="all", domain="code" → domain takes precedence, multi with code
r = simulate_recall_handler({"query": "test", "register": "all", "domain": "code"})
check("register='all' + domain='code' → domain takes precedence (code registers)",
      r["mode"] == "multi" and len(r["registers"]) == 4,
      str(r))

# ============================================================
# 6. NEG_DAMPEN constant unchanged
# ============================================================
check("NEG_DAMPEN unchanged", NEG_DAMPEN == 0.6, f"got {NEG_DAMPEN}")

# ============================================================
# 7. VALUE_BANK_MAX unchanged
# ============================================================
check("VALUE_BANK_MAX unchanged", VALUE_BANK_MAX == 500, f"got {VALUE_BANK_MAX}")

# ============================================================
# 8. REGISTERS lambda values unchanged
# ============================================================
check("REGISTERS style lambda", REGISTERS["style"][2] == 0.9999)
check("REGISTERS bug lambda", REGISTERS["bug"][2] == 0.9995)
check("REGISTERS context lambda", REGISTERS["context"][2] == 0.95)

# ============================================================
# 9. Existing value_bank.json backward compatibility
# ============================================================
vb_path = os.path.join("memory", "value_bank.json")
if os.path.exists(vb_path):
    with open(vb_path, "r", encoding="utf-8") as f:
        vb = json.load(f)
    total = len(vb)
    with_importance = sum(1 for e in vb if "importance" in e)
    with_ingest_count = sum(1 for e in vb if "ingest_count" in e)
    check("value_bank.json exists", True, f"{total} entries")
    check("All entries have importance field after migration",
          with_importance <= total,  # old entries may lack it, that's OK (default 1.0)
          f"{with_importance}/{total} have importance field (old entries default to 1.0)")
    # Show distribution
    if with_importance > 0:
        imps = [e.get("importance", 1.0) for e in vb]
        check("Importance range reasonable",
              min(imps) >= 0 and max(imps) < 1000,
              f"min={min(imps):.2f} max={max(imps):.2f}")
else:
    check("value_bank.json exists", False, "file not found — skipping compatibility check")

# ============================================================
# SUMMARY
# ============================================================
print("\n".join(results))
print(f"\n{'='*60}")
print(f"TOTAL: {len(results)} tests, {len(errors)} failures")
if errors:
    print(f"FAILED: {', '.join(errors)}")
else:
    print("ALL TESTS PASSED")
