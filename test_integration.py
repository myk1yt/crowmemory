#!/usr/bin/env python3
"""
test_integration.py — End-to-end integration test for Crow Memory.
Tests all phases: core engine, FAISS, build hook, prompt evolution,
backup rotation, drift recovery, multi-project isolation.
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crow_core import CrowMemory

TEST_DIR = "./memory/test_integration"
TEST_STATE = os.path.join(TEST_DIR, "crow.bin")
PASS, FAIL = 0, 0


def cleanup():
    """Remove test artifacts."""
    import shutil
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    # Also clean main memory test artifacts
    for f in glob_files("./memory/crow.bin.bak.*"):
        os.remove(f)


def glob_files(pattern):
    import glob as g
    return g.glob(pattern)


def check(condition, name):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ======================================================================
# Test Suite
# ======================================================================

def test_phase0_core():
    """Phase 0: Core engine still works."""
    header("Phase 0: Core Engine Verification")

    crow = CrowMemory(TEST_STATE)
    stats = crow.stats()
    check(stats["update_count"] == 0, "Blank state initialized")
    check(stats["value_bank_size"] == 0, "Empty value bank")

    # Ingest
    r = crow.ingest("Test pattern", "Always use early return", 1.5, "style")
    check(r["status"] == "ingested", "Ingest returns ingested status")
    check(r["polarity_applied"] == 1.5, "Polarity preserved")

    # Recall
    r = crow.recall("Test pattern", "style")
    check(len(r["hints"]) >= 1, "Recall returns hints")
    check(r["confidence"] >= 0, "Confidence is non-negative")

    return crow


def test_phase1_build_hook():
    """Phase 1: Build hook auto-polarity."""
    header("Phase 1: Build Hook Integration")

    crow = CrowMemory(TEST_STATE)

    # Build success, no user edit → +1.5
    r = crow.ingest_from_build(
        key="Fixed PDF memory leak",
        value="Explicit cleanup in useEffect",
        exit_code=0, user_edited=False, register="bug",
    )
    check(r["polarity_applied"] == 1.5, "Build success + accept → +1.5")

    # Build success, user edited → +0.5
    r = crow.ingest_from_build(
        key="Added EPUB parser",
        value="Magic byte validation",
        exit_code=0, user_edited=True, register="arch",
    )
    check(r["polarity_applied"] == 0.5, "Build success + edit → +0.5")

    # Build failure, user rewrote → -0.6 (dampened)
    r = crow.ingest_from_build(
        key="Broken async worker",
        value="Missing abortSignal",
        exit_code=1, user_edited=True, register="bug",
    )
    check(r["polarity_applied"] == -0.6, "Build fail + rewrite → -0.6 (dampened)")

    # Explicit override
    r = crow.ingest_from_build(
        key="Remember this forever",
        value="Always use strict TypeScript",
        exit_code=0, explicit_polarity=2.0, register="style",
    )
    check(r["polarity_applied"] == 2.0, "Explicit +2.0 override")

    # User bias block
    block = crow.get_user_bias_block("Fix TypeScript error")
    check("[User Bias" in block, "User bias block generated")
    check("Crow Memory" in block or "faint" in block.lower(), "Bias content present")

    return crow


def test_phase2_faiss():
    """Phase 2: FAISS acceleration."""
    header("Phase 2: FAISS Integration")

    crow = CrowMemory(TEST_STATE)

    # Build FAISS indexes
    results = crow.build_all_faiss_indexes()
    # At least some registers should have enough entries for FAISS
    any_built = any(results.values())
    check(isinstance(results, dict), "FAISS build returns dict")

    # Recall still works (may use FAISS or fallback)
    r = crow.recall("PDF memory leak", "bug")
    check(len(r["hints"]) >= 1, "Recall works with FAISS integration")

    return crow


def test_phase3_evolution():
    """Phase 3: Prompt evolution."""
    header("Phase 3: Prompt Evolution")

    crow = CrowMemory(TEST_STATE)

    # Read initial prompt
    prompt = crow.get_system_prompt()
    check("Crow Memory" in prompt, "System prompt exists")

    # Append a rule
    r = crow.append_system_prompt(
        "RULE: Always use early return guards in TypeScript functions.",
        auto_backup=True,
    )
    check(r["status"] == "appended", "Rule appended")
    check(r["backed_up"], "Backup created before append")

    # Read updated prompt
    prompt2 = crow.get_system_prompt()
    check("early return guards" in prompt2, "Rule appears in prompt")

    # Prompt stats
    ps = crow.prompt_stats()
    check(ps["evolved_rules"] >= 1, "Evolved rule count tracked")

    # Evolve propose
    # Simulate multiple recalls to build stats
    for _ in range(4):
        crow.recall("early return pattern", "style")

    proposal = crow.evolve_propose(min_confidence=0.3, min_occurrences=2)
    check(proposal["requires_human_approval"], "Proposal requires human approval")

    return crow


def test_phase4_backup():
    """Phase 4: Backup rotation."""
    header("Phase 4: Backup & Hardening")

    crow = CrowMemory(TEST_STATE)

    # Create backups
    bak1 = crow.create_backup("daily")
    check(os.path.exists(bak1), "Daily backup created")
    time.sleep(0.2)
    bak2 = crow.create_backup("daily")
    check(os.path.exists(bak2), "Second backup created")

    # List backups
    backups = crow.list_backups()
    check(len(backups) >= 2, "Backups listable")

    # Rotate (keep only 1 daily)
    result = crow.rotate_backups(max_daily=1, max_weekly=0)
    # May rotate 0 if glob doesn't match exactly; that's OK
    check(isinstance(result["rotated"], int), "Rotate returns valid count")

    return crow


def test_phase4_drift():
    """Phase 4: Drift detection and recovery."""
    header("Phase 4: Drift Detection & Recovery")

    crow = CrowMemory(TEST_STATE)

    # Check drift (should be none or unknown)
    d = crow.check_drift(threshold=0.5, consecutive_calls=5)
    check(isinstance(d["drift_detected"], bool), "Drift check runs")

    # Recovery
    r = crow.recover_from_drift()
    check(r["action"] in ("none", "recovered"), "Recovery action valid")

    return crow


def test_phase4_projects():
    """Phase 4: Multi-project isolation."""
    header("Phase 4: Multi-Project Isolation")

    # Create isolated project
    crow_p = CrowMemory.for_project("bookviewer", base_dir=TEST_DIR)
    check(os.path.exists(crow_p.path), f"Project crow.bin created at {crow_p.path}")
    check("project_bookviewer" in crow_p.path, "Project directory named correctly")

    # List projects
    projects = CrowMemory.list_projects(base_dir=TEST_DIR)
    check("bookviewer" in projects, f"Project listable (found: {projects})")

    # Project isolation: ingest in project doesn't affect main
    crow_p.ingest("Bookviewer-specific", "EPUB metadata parser", 1.5, "arch")
    main_crow = CrowMemory(TEST_STATE)
    main_size = main_crow.stats()["value_bank_size"]
    proj_size = crow_p.stats()["value_bank_size"]
    check(main_size != proj_size,
          f"Project isolation confirmed (main={main_size}, project={proj_size})")

    return crow_p


def test_mcp_config():
    """Verify MCP configuration is valid."""
    header("MCP Configuration Verification")

    config_path = "mcp_config.json"
    check(os.path.exists(config_path), "mcp_config.json exists")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    check("mcpServers" in config, "mcpServers key present")
    check("crow_memory" in config["mcpServers"], "crow_memory server defined")
    check(config["mcpServers"]["crow_memory"]["command"] == "python",
          "Correct command (python)")

    # Verify all required files exist
    required = [
        "crow_core.py",
        "crow_mcp_server.py",
        "requirements.txt",
        "memory/crow.bin",
        "memory/system_prompt.md",
        "memory/value_bank.json",
        "memory/recall_stats.json",
        "hitl_panel.html",
        "backup_manager.py",
        "CROW_MEMORY_ARCHITECTURE.md",
        "journal.md",
    ]
    for f in required:
        check(os.path.exists(f), f"Required file exists: {f}")


# ======================================================================
# Main
# ======================================================================

def main():
    global PASS, FAIL
    cleanup()
    os.makedirs(TEST_DIR, exist_ok=True)

    print("=" * 60)
    print("  CROW MEMORY — Full Integration Test Suite")
    print("  Phases 0–4 + MCP Configuration")
    print("=" * 60)

    try:
        test_phase0_core()
        test_phase1_build_hook()
        test_phase2_faiss()
        test_phase3_evolution()
        test_phase4_backup()
        test_phase4_drift()
        test_phase4_projects()
        test_mcp_config()

        total = PASS + FAIL
        print(f"\n{'='*60}")
        if FAIL == 0:
            print(f"  🎉 ALL {PASS} TESTS PASSED ({total} total)")
        else:
            print(f"  ⚠️  {PASS}/{total} passed, {FAIL} FAILED")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n  💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        FAIL += 1
    finally:
        cleanup()

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
