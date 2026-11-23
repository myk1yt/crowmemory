"""tests/test_migrate_from_v1.py - Unit tests for core/migrate_from_v1.py.

Covers the two fix-polish behaviors on top of the base migrator:
  1. system_prompt.md seeding (audit spec §6.1): byte-identical copy into the
     target home, never overwrite an existing live file (unless force_prompt),
     dry-run reports would_copy without writing.
  2. Honest per-outcome report: processed == inserted + merged + rejected,
     legacy "migrated" stays equal to processed.

Stdlib unittest only. Tempfile homes only; the real ~/.crow-memory and the
repo memory/ directory are never written (repo memory/system_prompt.md and a
synthetic value bank are read read-only).

Run:  python tests/test_migrate_from_v1.py -v
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
CORE_DIR = os.path.join(REPO_ROOT, "core")
sys.path.insert(0, CORE_DIR)

from crow_db import CrowDB  # noqa: E402
import migrate_from_v1  # noqa: E402
from migrate_from_v1 import migrate  # noqa: E402

REPO_PROMPT = os.path.join(REPO_ROOT, "memory", "system_prompt.md")


def _bank(entries):
    return {"entries": entries}


class MigratePromptTests(unittest.TestCase):
    """Fix 2: system_prompt.md seeding (spec §6.1)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_migprompt_test_")
        self.home = os.path.join(self.tmp, "home")
        self.bank = os.path.join(self.tmp, "bank.json")
        with open(self.bank, "w", encoding="utf-8") as f:
            json.dump(_bank([{
                "key": "seed entry", "value": "a valid memory",
                "register": "context", "importance": 1.0,
                "polarity_net": 1.0,
            }]), f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers -----------------------------------------------------------
    def _apply(self, **kwargs):
        kwargs.setdefault("src_prompt", REPO_PROMPT)
        return migrate(self.bank, self.home, apply=True, **kwargs)

    # -- tests -------------------------------------------------------------
    def test_apply_copies_prompt_byte_identical(self):
        rep = self._apply()
        dst = os.path.join(self.home, "system_prompt.md")
        self.assertTrue(rep["prompt"]["copied"])
        self.assertTrue(rep["prompt"]["would_copy"])
        self.assertFalse(rep["prompt"]["skipped_exists"])
        self.assertIsNone(rep["prompt"]["error"])
        with open(REPO_PROMPT, "rb") as f:
            expected = f.read()
        with open(dst, "rb") as f:
            actual = f.read()
        self.assertEqual(actual, expected)  # byte-identical
        self.assertGreater(len(actual), 0)

    def test_second_apply_never_overwrites(self):
        self._apply()
        dst = os.path.join(self.home, "system_prompt.md")
        with open(dst, "ab") as f:  # simulate a live, edited file
            f.write(b"\n- live rule added after migration\n")
        rep = self._apply()
        self.assertFalse(rep["prompt"]["copied"])
        self.assertTrue(rep["prompt"]["skipped_exists"])
        self.assertFalse(rep["prompt"]["would_copy"])
        with open(dst, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"- live rule added after migration\n"))

    def test_dry_run_reports_would_copy_without_writing(self):
        rep = migrate(self.bank, self.home, apply=False, src_prompt=REPO_PROMPT)
        self.assertTrue(rep["dry_run"])
        self.assertTrue(rep["prompt"]["would_copy"])
        self.assertFalse(rep["prompt"]["copied"])
        self.assertFalse(os.path.exists(self.home))  # nothing written

    def test_dry_run_existing_target_would_not_copy(self):
        os.makedirs(self.home)
        with open(os.path.join(self.home, "system_prompt.md"), "w",
                  encoding="utf-8") as f:
            f.write("live\n")
        rep = migrate(self.bank, self.home, apply=False, src_prompt=REPO_PROMPT)
        self.assertFalse(rep["prompt"]["would_copy"])

    def test_force_prompt_overwrites_with_backup(self):
        self._apply()
        dst = os.path.join(self.home, "system_prompt.md")
        with open(dst, "wb") as f:
            f.write(b"LIVE CONTENT")
        rep = self._apply(force_prompt=True)
        self.assertTrue(rep["prompt"]["copied"])
        self.assertFalse(rep["prompt"]["skipped_exists"])
        with open(dst, "rb") as f:
            self.assertNotEqual(f.read(), b"LIVE CONTENT")
        backups = [n for n in os.listdir(self.home)
                   if n.startswith("system_prompt.md.bak.")]
        self.assertEqual(len(backups), 1, backups)
        with open(os.path.join(self.home, backups[0]), "rb") as f:
            self.assertEqual(f.read(), b"LIVE CONTENT")  # backup preserved

    def test_missing_source_is_a_quiet_noop(self):
        rep = self._apply(src_prompt=os.path.join(self.tmp, "nope.md"))
        self.assertFalse(rep["prompt"]["copied"])
        self.assertFalse(rep["prompt"]["would_copy"])
        self.assertIsNone(rep["prompt"]["error"])
        self.assertFalse(os.path.exists(os.path.join(self.home,
                                                     "system_prompt.md")))

    def test_cli_flags_roundtrip(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = migrate_from_v1.main([
                "--apply", "--src-json", self.bank,
                "--home", self.home,
                "--src-prompt", REPO_PROMPT,
            ])
        self.assertEqual(rc, 0)
        rep = json.loads(out.getvalue())
        self.assertTrue(rep["prompt"]["copied"])
        self.assertTrue(os.path.exists(os.path.join(self.home,
                                                    "system_prompt.md")))
        out2 = io.StringIO()
        with contextlib.redirect_stdout(out2):
            rc = migrate_from_v1.main([
                "--apply", "--src-json", self.bank,
                "--home", self.home,
                "--src-prompt", REPO_PROMPT,
                "--force-prompt",
            ])
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(out2.getvalue())["prompt"]["copied"])


class MigrateReportTests(unittest.TestCase):
    """Fix 3: per-outcome counts, legacy keys, sum identity."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_migreport_test_")
        self.home = os.path.join(self.tmp, "home")
        self.bank = os.path.join(self.tmp, "bank.json")
        self.prompt = os.path.join(self.tmp, "prompt.md")
        with open(self.prompt, "w", encoding="utf-8") as f:
            f.write("# test prompt\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_bank(self, entries):
        with open(self.bank, "w", encoding="utf-8") as f:
            json.dump(_bank(entries), f)

    def test_inserted_vs_merged_counts_sum(self):
        self._write_bank([
            {"key": "npm ci before build",
             "value": "always run npm ci before build so the lockfile "
                      "stays consistent",
             "register": "context", "polarity_net": 1.0, "importance": 1.0},
            {"key": "npm ci first",  # different key, near-identical text
             "value": "always run npm ci before build so the lockfile "
                      "stays consistent",
             "register": "context", "polarity_net": 1.0, "importance": 1.0},
            {"key": "other topic", "value": "completely unrelated words here",
             "register": "arch", "polarity_net": 1.0, "importance": 1.0},
            {"key": "k", "value": "junk key is filtered",
             "register": "context"},                       # junk
            {"key": "bad", "value": "unknown register",
             "register": "nonsense"},                      # invalid register
            {"key": "", "value": "empty key is invalid",
             "register": "context"},                       # invalid empty key
        ])
        rep = migrate(self.bank, self.home, apply=True, src_prompt=self.prompt)

        # per-outcome counts
        self.assertEqual(rep["processed"], 3)
        self.assertEqual(rep["inserted"], 2)
        self.assertEqual(rep["merged"], 1)
        self.assertEqual(rep["rejected"], 0)
        self.assertEqual(rep["skipped_junk"], 1)
        self.assertEqual(rep["skipped_invalid"], 2)
        self.assertEqual(rep["errors"], 0)
        # sum identity: every processed row landed in exactly one bucket
        self.assertEqual(rep["processed"],
                         rep["inserted"] + rep["merged"] + rep["rejected"])
        # legacy total key still equals processed
        self.assertEqual(rep["migrated"], rep["processed"])
        # the DB really holds inserted rows only
        db = CrowDB(self.home)
        try:
            self.assertEqual(db.admin("diagnostics")["total_rows"], 2)
        finally:
            db.close()

    def test_same_register_key_merge_counts_as_merged(self):
        self._write_bank([
            {"key": "identical key", "value": "first wording",
             "register": "style", "polarity_net": 1.0, "importance": 1.0},
            {"key": "identical key", "value": "second wording",
             "register": "style", "polarity_net": 1.0, "importance": 1.0},
        ])
        rep = migrate(self.bank, self.home, apply=True, src_prompt=self.prompt)
        self.assertEqual(rep["inserted"], 1)
        self.assertEqual(rep["merged"], 1)
        self.assertEqual(rep["processed"], 2)

    def test_dry_run_keeps_outcome_counts_zero(self):
        self._write_bank([
            {"key": "a", "value": "valid one", "register": "context"},
            {"key": "b", "value": "valid two", "register": "context"},
        ])
        rep = migrate(self.bank, self.home, apply=False, src_prompt=self.prompt)
        self.assertTrue(rep["dry_run"])
        self.assertEqual(rep["processed"], 2)
        self.assertEqual(rep["migrated"], 2)
        self.assertEqual(rep["inserted"], 0)
        self.assertEqual(rep["merged"], 0)
        self.assertEqual(rep["rejected"], 0)
        self.assertFalse(os.path.exists(self.home))

    def test_report_has_all_legacy_and_new_keys(self):
        self._write_bank([
            {"key": "a", "value": "valid one", "register": "context"},
        ])
        rep = migrate(self.bank, self.home, apply=True, src_prompt=self.prompt)
        for key in ("migrated", "processed", "inserted", "merged", "rejected",
                    "skipped_junk", "skipped_invalid", "errors",
                    "per_register", "dry_run", "prompt"):
            self.assertIn(key, rep, key)
        for key in ("src", "dst", "would_copy", "copied", "skipped_exists",
                    "error"):
            self.assertIn(key, rep["prompt"], key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
