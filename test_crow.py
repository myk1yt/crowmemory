#!/usr/bin/env python3
"""
test_crow.py — Manual test script for Crow Memory core engine.
Tests the recall→ingest→recall cycle with dummy data.
"""

import sys
import os

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crow_core import CrowMemory

TEST_STATE_PATH = "./memory/crow_test.bin"


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_init():
    """Test 1: Initialize CrowMemory (creates blank state)."""
    print_section("Test 1: Initialize CrowMemory")

    # Clean up any previous test state
    for f in [TEST_STATE_PATH, TEST_STATE_PATH + ".tmp"]:
        if os.path.exists(f):
            os.remove(f)

    crow = CrowMemory(TEST_STATE_PATH)
    stats = crow.stats()

    print(f"  update_count: {stats['update_count']}")
    print(f"  value_bank_size: {stats['value_bank_size']}")
    for name, info in stats["registers"].items():
        print(f"  {name}: norm={info['norm']:.4f}, sparsity={info['sparsity']:.2%}")

    assert stats["update_count"] == 0, "Initial update_count should be 0"
    assert stats["value_bank_size"] == 0, "Initial value_bank should be empty"
    for name, info in stats["registers"].items():
        assert info["norm"] == 0.0, f"Register {name} should start at zero norm"

    print("  ✅ PASSED")
    return crow


def test_ingest(crow: CrowMemory):
    """Test 2: Ingest some coding experiences."""
    print_section("Test 2: Ingest experiences")

    experiences = [
        {
            "key": "React useEffect cleanup for PDF worker",
            "value": "Always use explicit cleanup in useEffect return; prefer abortSignal over weakRef",
            "polarity": 1.5,
            "register": "bug",
        },
        {
            "key": "TypeScript function with nested conditions",
            "value": "Prefer early return guards over deep if-else nesting; max 2 levels",
            "polarity": 1.5,
            "register": "style",
        },
        {
            "key": "Binary file format parser",
            "value": "Always validate magic bytes in first 8 bytes; early return on mismatch",
            "polarity": 1.5,
            "register": "arch",
        },
        {
            "key": "Windows file encoding issue",
            "value": "User had a bad experience with unhandled Windows encodings; always specify UTF-8 explicitly",
            "polarity": -1.0,
            "register": "bug",
        },
        {
            "key": "Current task context",
            "value": "User is building a book viewer application with EPUB support",
            "polarity": 1.0,
            "register": "context",
        },
    ]

    for exp in experiences:
        result = crow.ingest(**exp)
        print(f"  ingest: {exp['key'][:50]}... → {result['status']} "
              f"(polarity={result['polarity_applied']})")

    stats = crow.stats()
    print(f"\n  update_count after 5 ingests: {stats['update_count']}")
    print(f"  value_bank_size: {stats['value_bank_size']}")

    for name, info in stats["registers"].items():
        print(f"  {name}: norm={info['norm']:.4f}, max_abs={info['max_abs']:.4f}")

    assert stats["update_count"] == 5, "Should have 5 updates"
    assert stats["value_bank_size"] == 5, "Should have 5 value_bank entries"

    # Register norms should be non-zero after ingest
    for name in ("bug", "style", "arch", "context"):
        assert stats["registers"][name]["norm"] > 0, f"{name} register should be non-zero"

    print("  ✅ PASSED")
    return crow


def test_recall(crow: CrowMemory):
    """Test 3: Recall hints for various queries."""
    print_section("Test 3: Recall hints")

    queries = [
        ("Fix memory leak in React PDF worker", "bug"),
        ("Write a TypeScript file parser", "style"),
        ("Design a binary format reader", "arch"),
        ("What is the user currently working on?", "context"),
    ]

    for query, register in queries:
        result = crow.recall(query, register, top_k=2)
        print(f"  query: '{query[:60]}...' [{register}]")
        print(f"    confidence: {result['confidence']}")
        for hint in result["hints"]:
            print(f"    → {hint[:100]}...")
        print()

        # At least one hint should be returned
        assert len(result["hints"]) >= 1, "Should return at least one hint"
        assert 0 <= result["confidence"] <= 1.0, "Confidence should be in [0, 1]"

    print("  ✅ PASSED")
    return crow


def test_evolve(crow: CrowMemory):
    """Test 4: Simulate multiple recalls, then check evolve_propose."""
    print_section("Test 4: Evolve proposal")

    # Simulate multiple recalls of the same pattern to build stats
    for _ in range(4):
        crow.recall("React useEffect cleanup pattern", "bug")

    result = crow.evolve_propose(min_confidence=0.3, min_occurrences=2)

    print(f"  proposal: {result.get('proposal', 'None')}")
    print(f"  confidence: {result.get('confidence', 0)}")
    print(f"  requires_human_approval: {result.get('requires_human_approval', True)}")

    assert result.get("requires_human_approval") is True, \
        "Evolve proposals must require human approval"

    print("  ✅ PASSED")
    return crow


def test_drift(crow: CrowMemory):
    """Test 5: Drift detection."""
    print_section("Test 5: Drift detection")

    result = crow.check_drift(threshold=0.5, consecutive_calls=5)
    print(f"  drift_detected: {result['drift_detected']}")
    print(f"  message: {result['message']}")

    # Fresh memory with few entries should not drift
    # (may or may not drift depending on confidence values)
    print("  ✅ PASSED (informational)")
    return crow


def test_persistence(crow: CrowMemory):
    """Test 6: Persist and reload."""
    print_section("Test 6: Persistence round-trip")

    # Get stats before
    stats_before = crow.stats()

    # Force persist
    crow._persist()

    # Load a new instance from the same file
    crow2 = CrowMemory(TEST_STATE_PATH)
    stats_after = crow2.stats()

    print(f"  Before: update_count={stats_before['update_count']}, "
          f"value_bank={stats_before['value_bank_size']}")
    print(f"  After:  update_count={stats_after['update_count']}, "
          f"value_bank={stats_after['value_bank_size']}")

    assert stats_after["update_count"] == stats_before["update_count"], \
        "Update count should survive reload"
    assert stats_after["value_bank_size"] == stats_before["value_bank_size"], \
        "Value bank should survive reload"

    # Verify we can still recall
    result = crow2.recall("PDF worker memory", "bug")
    assert len(result["hints"]) >= 1, "Should recall hints after reload"

    print("  ✅ PASSED")
    return crow2


def cleanup():
    """Remove test artifacts."""
    for f in [TEST_STATE_PATH, TEST_STATE_PATH + ".tmp"]:
        if os.path.exists(f):
            os.remove(f)

    memory_dir = os.path.dirname(TEST_STATE_PATH) or "."
    for f in ["value_bank.json", "value_bank.json.tmp",
              "recall_stats.json", "recall_stats.json.tmp"]:
        path = os.path.join(memory_dir, f)
        if os.path.exists(path):
            os.remove(path)


def main():
    print("=" * 60)
    print("  CROW MEMORY — Phase 0 Manual Test Suite")
    print("=" * 60)

    try:
        crow = test_init()
        crow = test_ingest(crow)
        crow = test_recall(crow)
        crow = test_evolve(crow)
        crow = test_drift(crow)
        crow = test_persistence(crow)

        print_section("🎉 ALL TESTS PASSED 🎉")
        print("  Crow Memory core engine is functional.\n")

    except AssertionError as e:
        print(f"\n  ❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n  💥 UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Ask before cleanup
        pass  # Keep test state for inspection


if __name__ == "__main__":
    main()
