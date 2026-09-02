#!/usr/bin/env python3
"""
tests/test_purge_debris.py — search-log debris purge verification (plain unittest).

Covers scripts/purge_search_debris.py (User Decision [2026-09-02 07:18]):
each debris pattern removed (key-side AND value-side matches), non-debris
entries kept byte-equal, dry-run makes no changes, backup created on apply
holding the ORIGINAL content, idempotent second apply writes nothing,
--pattern extra prefix regex works, per-register breakdown counts correct.

No real memory dir: every test builds fixture JSON inside a temp dir
(the tests/test_merge.py pattern).
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.purge_search_debris import (  # noqa: E402
    compile_extra_patterns, is_debris, main, plan_purge,
)


def write_bank(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def read_bank(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def entry(key, value, register="context", timestamp=1712345678.0,
          importance=1.0, ingest_count=1, project=None, vector_b64="QUJD"):
    e = {"key": key, "value": value, "vector_b64": vector_b64,
         "register": register, "timestamp": timestamp,
         "importance": importance, "ingest_count": ingest_count}
    if project is not None:
        e["project"] = project
    return e


class PurgeDebrisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="purge_debris_test_")
        self.bank_path = os.path.join(self.tmp, "value_bank.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bank(self, entries):
        write_bank(self.bank_path, entries)
        return entries

    def debris(self):
        return [
            # Pattern 1 — "Search: " prefix
            entry("Search: translationMode → 0 AST + 0 line matches",
                  "search returned nothing (debris)", register="life_context"),
            # Pattern 1 via VALUE (key is clean)
            entry("search log value-side", 
                  "Search: flutter_rust_bridge → 0 AST + 0 line matches",
                  register="context"),
            # Pattern 2 — "Web search success" prefix
            entry("Web search success: CTranslate2 M2M-100",
                  "search engine result summary (debris)", register="context"),
            # Pattern 2 — "Web search failed" prefix, via key
            entry("Web search failed: timeout after 30s",
                  "failed search log", register="bug"),
            # Leading-whitespace variant (startswith checked after strip)
            entry("  Search: padded debris", "padded prefix still debris",
                  register="arch"),
        ]

    def keepers(self):
        return [
            entry("prefers functional components", "user prefers FP style",
                  register="style", project="crow-memory"),
            entry("Search bug in translationMode",
                  "real memory about a translation-mode bug (NOT a log)"),
            entry("web search workflow preference",
                  "user likes web-search-first workflow", register="context"),
            entry("Web research session", "user researched CTranslate2",
                  register="life_context"),
        ]

    # -- pattern classification ------------------------------------------------

    def test_is_debris_each_pattern(self):
        for e in self.debris():
            self.assertTrue(is_debris(e), f"expected debris: {e['key']!r}")

    def test_is_debris_not_debris(self):
        for e in self.keepers():
            self.assertFalse(is_debris(e), f"expected kept: {e['key']!r}")

    def test_case_sensitivity(self):
        # "search:" lowercase must NOT match (case-sensitive rule)
        e = entry("search: lower-case log", "value")
        self.assertFalse(is_debris(e))

    def test_substring_not_prefix(self):
        # "Search:" appearing mid-text is NOT debris (prefix rule)
        e = entry("memory about logs", "ran a Search: something log")
        self.assertFalse(is_debris(e))

    def test_malformed_never_debris(self):
        self.assertFalse(is_debris("Search: a plain string, not a dict"))
        self.assertFalse(is_debris(["Search: list"]))

    def test_compile_extra_patterns_bad_regex(self):
        with self.assertRaises(ValueError):
            compile_extra_patterns(["("])

    def test_extra_pattern_via_is_debris(self):
        rx = compile_extra_patterns(["^Probe: "])
        self.assertTrue(is_debris(entry("Probe: endpoint scan", "v"),
                                  rx))
        self.assertFalse(is_debris(entry("normal key", "v"), rx))

    # -- plan_purge ------------------------------------------------------------

    def test_plan_purge_breakdown(self):
        entries = self.debris() + self.keepers()
        kept, removed, stats = plan_purge(entries)
        self.assertEqual(stats["scanned"], len(entries))
        self.assertEqual(stats["removed"], len(self.debris()))
        self.assertEqual(len(kept), len(self.keepers()))
        self.assertEqual(len(removed), len(self.debris()))
        # per-register breakdown: life_context 1, context 2 (value-side
        # match + Web search success), bug 1, arch 1
        self.assertEqual(stats["per_register"],
                         {"life_context": 1, "context": 2, "bug": 1,
                          "arch": 1})
        # examples capped at max_examples
        _, _, s2 = plan_purge(entries, max_examples=2)
        self.assertEqual(len(s2["examples"]), 2)

    def test_plan_purge_malformed_passthrough(self):
        entries = ["not a dict", 42] + self.debris()
        kept, removed, stats = plan_purge(entries)
        self.assertEqual(stats["malformed_kept"], 2)
        self.assertIn("not a dict", kept)
        self.assertIn(42, kept)
        self.assertEqual(stats["removed"], len(self.debris()))

    # -- CLI: dry-run / apply / backup / idempotent ----------------------------

    def test_dry_run_no_changes(self):
        entries = self.debris() + self.keepers()
        self.bank(entries)
        rc = main(["--value-bank", self.bank_path])
        self.assertEqual(rc, 0)
        # file byte-equal to the fixture (no writes at all)
        self.assertEqual(read_bank(self.bank_path), entries)
        # no backup artifacts created
        leftovers = [f for f in os.listdir(self.tmp) if ".bak." in f]
        self.assertEqual(leftovers, [])

    def test_apply_removes_debris_keeps_others_byte_equal(self):
        debris, keepers = self.debris(), self.keepers()
        self.bank(debris + keepers)
        rc = main(["--value-bank", self.bank_path, "--apply"])
        self.assertEqual(rc, 0)
        after = read_bank(self.bank_path)
        self.assertEqual(len(after), len(keepers))
        # keepers appear byte-equal (identical dicts, all fields)
        for k in keepers:
            self.assertIn(k, after)
        # no debris remains
        for e in after:
            self.assertFalse(is_debris(e))

    def test_apply_backup_holds_original(self):
        debris, keepers = self.debris(), self.keepers()
        original = self.bank(debris + keepers)
        rc = main(["--value-bank", self.bank_path, "--apply"])
        self.assertEqual(rc, 0)
        baks = [f for f in os.listdir(self.tmp) if ".bak.purge-" in f]
        self.assertEqual(len(baks), 1)
        with open(os.path.join(self.tmp, baks[0]), "r", encoding="utf-8") as f:
            bak_content = json.load(f)
        self.assertEqual(bak_content, original)  # backup = pre-purge content

    def test_apply_idempotent_second_run(self):
        self.bank(self.debris() + self.keepers())
        rc1 = main(["--value-bank", self.bank_path, "--apply"])
        self.assertEqual(rc1, 0)
        after_first = read_bank(self.bank_path)
        rc2 = main(["--value-bank", self.bank_path, "--apply"])
        self.assertEqual(rc2, 0)  # exit 0 on nothing-to-purge
        self.assertEqual(read_bank(self.bank_path), after_first)
        # exactly ONE backup exists (second run wrote nothing)
        baks = [f for f in os.listdir(self.tmp) if ".bak.purge-" in f]
        self.assertEqual(len(baks), 1)

    def test_apply_with_extra_pattern(self):
        extra = entry("Probe: endpoint scan debris", "probe log",
                      register="bug")
        self.bank(self.debris() + self.keepers() + [extra])
        rc = main(["--value-bank", self.bank_path, "--apply",
                   "--pattern", "^Probe: "])
        self.assertEqual(rc, 0)
        after = read_bank(self.bank_path)
        self.assertEqual(len(after), len(self.keepers()))
        self.assertNotIn(extra, after)

    def test_dry_run_without_extra_pattern_keeps_probe(self):
        extra = entry("Probe: endpoint scan debris", "probe log")
        self.bank(self.keepers() + [extra])
        rc = main(["--value-bank", self.bank_path])
        self.assertEqual(rc, 0)
        self.assertEqual(read_bank(self.bank_path),
                         self.keepers() + [extra])

    # -- CLI error paths --------------------------------------------------------

    def test_missing_file_exit_1(self):
        rc = main(["--value-bank",
                   os.path.join(self.tmp, "nope.json")])
        self.assertEqual(rc, 1)

    def test_bad_regex_exit_1(self):
        self.bank(self.keepers())
        rc = main(["--value-bank", self.bank_path, "--pattern", "("])
        self.assertEqual(rc, 1)

    def test_apply_and_dry_run_mutually_exclusive(self):
        self.bank(self.keepers())
        rc = main(["--value-bank", self.bank_path, "--apply", "--dry-run"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)