"""tests/test_install_plugin.py - unit tests for scripts/install_plugin.py.

Covers the installer's deploy primitives and its user-facing entry point:
write_text_deploy (create/update/unchanged + backup on difference),
upsert_marked_block (create/replace/idempotent/truncated), the Cursor
hooks.json merge (foreign keys survive), the codex/zoo AGENTS.md marked block,
probe_shim_flags (CREATE_NO_WINDOW), the migration fingerprint guard
(skip + --force-migrate), and a full installer run into a temp home.

Isolation: every target lives under tempfile.mkdtemp(). Homes are passed with
--home, adapter targets go through CROW_DEPLOY_HOME. The real ~/.crow-memory,
~/.kimi-code, ~/.cursor, ~/.codex, ~/.zoo, ~/.claude, ~/.gemini are never
touched; repo adapters/ and memory/system_prompt.md are read-only inputs.

Run:  python tests/test_install_plugin.py -v
"""

import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))

import install_plugin  # noqa: E402
import migrate_from_v1  # noqa: E402

CURSOR_HOOKS = install_plugin.ADAPTERS / "cursor" / "hooks.json"
CROW_MARKER = install_plugin.CROW_HOOK_MARKER


def _backups(path):
    folder = os.path.dirname(str(path))
    base = os.path.basename(str(path))
    return sorted(n for n in os.listdir(folder) if n.startswith(base + ".bak."))


def _read(path):
    with open(str(path), encoding="utf-8") as f:
        return f.read()


class DeployWriteTests(unittest.TestCase):
    """write_text_deploy: create, unchanged, update-with-backup."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_write_")
        self.target = Path(self.tmp) / "sub" / "file.txt"
        self.log = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_writes_content_without_backup(self):
        status = install_plugin.write_text_deploy(self.target, "hello\n",
                                                  self.log)
        self.assertEqual(status, "created")
        self.assertEqual(_read(self.target), "hello\n")
        self.assertEqual(_backups(self.target), [])

    def test_identical_content_is_unchanged(self):
        install_plugin.write_text_deploy(self.target, "hello\n", self.log)
        status = install_plugin.write_text_deploy(self.target, "hello\n",
                                                  self.log)
        self.assertEqual(status, "unchanged")
        self.assertEqual(_backups(self.target), [])

    def test_differing_content_updates_and_backs_up(self):
        install_plugin.write_text_deploy(self.target, "old\n", self.log)
        status = install_plugin.write_text_deploy(self.target, "new\n",
                                                  self.log)
        self.assertEqual(status, "updated")
        self.assertEqual(_read(self.target), "new\n")
        baks = _backups(self.target)
        self.assertEqual(len(baks), 1, baks)
        self.assertEqual(_read(Path(self.tmp) / "sub" / baks[0]), "old\n")
        self.assertTrue(any("backup" in line for line in self.log))

    def test_crlf_only_difference_is_unchanged(self):
        # .cmd shims carry \r\n; the compare must not rewrite them every run.
        self.target.parent.mkdir(parents=True)
        with open(str(self.target), "w", encoding="utf-8", newline="") as f:
            f.write("a\r\nb\r\n")
        status = install_plugin.write_text_deploy(self.target, "a\r\nb\r\n",
                                                  self.log)
        self.assertEqual(status, "unchanged")
        self.assertEqual(_backups(self.target), [])

    def test_symlinked_target_is_written_through(self):
        real = Path(self.tmp) / "dotfiles" / "file.txt"
        real.parent.mkdir()
        real.write_text("user content\n", encoding="utf-8")
        self.target.parent.mkdir(parents=True)
        try:
            os.symlink(str(real), str(self.target))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        status = install_plugin.write_text_deploy(self.target, "crow content\n",
                                                  self.log)
        self.assertEqual(status, "updated")
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(_read(real), "crow content\n")


class MarkedBlockTests(unittest.TestCase):
    """upsert_marked_block: create, replace, idempotent, truncated file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_block_")
        self.target = Path(self.tmp) / "config.toml"
        self.log = []
        self.begin = install_plugin.TOML_MARK_BEGIN
        self.end = install_plugin.TOML_MARK_END

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _upsert(self, body):
        install_plugin.upsert_marked_block(self.target, body, self.log,
                                           self.begin, self.end)

    def test_create_wraps_body_in_markers(self):
        self._upsert("[[hooks]]\ncommand = 'x'")
        text = _read(self.target)
        self.assertEqual(text.count(self.begin), 1)
        self.assertEqual(text.count(self.end), 1)
        self.assertTrue(text.startswith(self.begin + "\n"))
        self.assertTrue(text.endswith(self.end + "\n"))
        self.assertEqual(self.target.read_text(encoding="utf-8"), text)

    def test_replace_keeps_surrounding_text(self):
        self.target.write_text(
            "# user top\n" + self.begin + "\nold body\n" + self.end +
            "\n# user tail\n", encoding="utf-8")
        self._upsert("new body")
        text = _read(self.target)
        self.assertIn("# user top", text)
        self.assertIn("# user tail", text)
        self.assertIn("new body", text)
        self.assertNotIn("old body", text)
        self.assertEqual(text.count(self.begin), 1)
        self.assertEqual(text.count(self.end), 1)

    def test_second_upsert_is_unchanged(self):
        self._upsert("body")
        before = _read(self.target)
        self.log.clear()
        self._upsert("body")
        self.assertEqual(_read(self.target), before)
        self.assertEqual(_backups(self.target), [])
        self.assertTrue(any("unchanged" in line for line in self.log))

    def test_appends_when_no_marker_present(self):
        self.target.write_text("# user rules\n- keep me\n", encoding="utf-8")
        self._upsert("crow body")
        text = _read(self.target)
        self.assertIn("- keep me", text)
        self.assertIn("crow body", text)
        self.assertEqual(text.count(self.begin), 1)

    def test_lone_begin_marker_replaces_to_eof(self):
        # Simulates a file truncated inside our block: begin marker, no end.
        self.target.write_text(
            "# user top\n" + self.begin + "\nstale crow body without end\n",
            encoding="utf-8")
        self._upsert("fresh body")
        text = _read(self.target)
        self.assertIn("# user top", text)
        self.assertIn("fresh body", text)
        self.assertNotIn("stale crow body", text)
        self.assertEqual(text.count(self.begin), 1)
        self.assertEqual(text.count(self.end), 1)

    def test_truncated_re_run_yields_exactly_one_block(self):
        self._upsert("body v2")
        full = _read(self.target)
        self.target.write_text(full[:full.index(self.end)], encoding="utf-8")
        self._upsert("body v2")
        text = _read(self.target)
        self.assertEqual(text.count(self.begin), 1, text)
        self.assertEqual(text.count(self.end), 1, text)
        self.assertEqual(text.count("body v2"), 1, text)

    def test_lone_end_marker_is_stripped_not_a_crash(self):
        # R2-4: an end marker with no begin marker used to raise ValueError
        self.target.write_text(self.end + "\n# user rules\n- keep me\n",
                               encoding="utf-8")
        self._upsert("fresh body")
        text = _read(self.target)
        self.assertIn("# user rules", text)
        self.assertIn("- keep me", text)
        self.assertIn("fresh body", text)
        self.assertEqual(text.count(self.begin), 1, text)
        self.assertEqual(text.count(self.end), 1, text)
        self.assertTrue(any("stray end marker" in line for line in self.log))

    def test_end_marker_before_begin_marker_is_repaired(self):
        # R2-4: end-before-begin made rest.split(end, 1) unpack-fail
        self.target.write_text(
            self.end + "\n# user top\n" + self.begin + "\nstale body\n",
            encoding="utf-8")
        self._upsert("fresh body")
        text = _read(self.target)
        self.assertIn("# user top", text)
        self.assertNotIn("stale body", text)
        self.assertIn("fresh body", text)
        self.assertEqual(text.count(self.begin), 1, text)
        self.assertEqual(text.count(self.end), 1, text)

    def test_non_utf8_file_is_skipped_with_warning(self):
        # R2-6: rewriting a non-UTF-8 file would corrupt the user's encoding
        raw = "# user rules\n".encode("utf-8") + b"\xff\xfe caf\xe9\n"
        self.target.write_bytes(raw)
        self._upsert("crow body")
        self.assertEqual(self.target.read_bytes(), raw)  # untouched
        self.assertTrue(any("not UTF-8" in line for line in self.log))


class CursorHooksMergeTests(unittest.TestCase):
    """~/.cursor/hooks.json is merged, never replaced wholesale (SEC-5)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_cursor_")
        self.home = Path(self.tmp) / "home"
        self.hooks = Path(self.tmp) / "deploy" / ".cursor" / "hooks.json"
        self.log = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _merge(self):
        install_plugin.merge_cursor_hooks(self.hooks, CURSOR_HOOKS, self.home,
                                          self.log)

    def _seed(self, payload):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.write_text(json.dumps(payload, indent=2) + "\n",
                              encoding="utf-8")

    def _crow_entries(self, data, event):
        return [e for e in data["hooks"].get(event, [])
                if isinstance(e, dict) and CROW_MARKER in str(e.get("command", ""))]

    def test_creates_file_with_crow_events(self):
        self._merge()
        data = json.loads(_read(self.hooks))
        self.assertEqual(sorted(data["hooks"]),
                         ["afterShellExecution", "beforeSubmitPrompt",
                          "sessionStart"])
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)
        command = data["hooks"]["sessionStart"][0]["command"]
        self.assertIn(str(self.home), command)  # <CROW_HOME> was rewritten

    def test_merge_preserves_foreign_events_and_entries(self):
        self._seed({"version": 1, "hooks": {
            "beforeShellExecution": [{"command": "block-rm-rf.sh"}],
            "sessionStart": [{"command": "my-telemetry.sh"}],
        }})
        self._merge()
        data = json.loads(_read(self.hooks))
        # the user's unrelated event survives untouched
        self.assertEqual(data["hooks"]["beforeShellExecution"],
                         [{"command": "block-rm-rf.sh"}])
        # the user's own entry in a shared event survives next to Crow's
        commands = [e.get("command") for e in data["hooks"]["sessionStart"]]
        self.assertIn("my-telemetry.sh", commands)
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)
        # a key the template carries but the user did not is added
        self.assertIn("beforeSubmitPrompt", data["hooks"])
        # the change is backed up (the first write differs from the seed)
        baks = _backups(self.hooks)
        self.assertEqual(len(baks), 1, baks)
        seeded = json.loads(_read(self.hooks.parent / baks[0]))
        self.assertEqual(seeded["hooks"]["beforeShellExecution"],
                         [{"command": "block-rm-rf.sh"}])

    def test_merge_is_idempotent(self):
        self._merge()
        before = _read(self.hooks)
        self.log.clear()
        self._merge()
        self.assertEqual(_read(self.hooks), before)
        self.assertEqual(_backups(self.hooks), [])
        data = json.loads(before)
        for event in ("sessionStart", "beforeSubmitPrompt",
                      "afterShellExecution"):
            self.assertEqual(len(self._crow_entries(data, event)), 1, event)

    def test_invalid_json_is_backed_up_warned_and_rewritten(self):
        self.hooks.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.write_text("this is not json", encoding="utf-8")
        self._merge()
        baks = _backups(self.hooks)
        self.assertEqual(len(baks), 1, baks)
        self.assertEqual(_read(self.hooks.parent / baks[0]), "this is not json")
        self.assertTrue(any("WARN" in line for line in self.log))
        data = json.loads(_read(self.hooks))
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)

    def test_hooks_key_that_is_not_an_object_is_replaced(self):
        # R2-6: a nesting anomaly must warn and continue, never abort
        self._seed({"version": 1, "hooks": ["sessionStart"]})
        self._merge()
        data = json.loads(_read(self.hooks))
        self.assertIsInstance(data["hooks"], dict)
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)
        self.assertTrue(any("not an object" in line for line in self.log))

    def test_event_value_that_is_not_an_array_is_replaced(self):
        self._seed({"hooks": {"sessionStart": {"command": "odd-client.sh"},
                              "beforeShellExecution": [{"command": "guard.sh"}]
                              }})
        self._merge()
        data = json.loads(_read(self.hooks))
        self.assertIsInstance(data["hooks"]["sessionStart"], list)
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)
        # the unrelated event keeps its entry
        self.assertEqual(data["hooks"]["beforeShellExecution"],
                         [{"command": "guard.sh"}])
        self.assertTrue(any("not an array" in line for line in self.log))

    def test_entries_that_are_not_objects_are_kept(self):
        self._seed({"hooks": {"sessionStart": ["plain-string-entry", 7, None]}})
        self._merge()
        data = json.loads(_read(self.hooks))
        commands = data["hooks"]["sessionStart"]
        self.assertIn("plain-string-entry", commands)
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)

    def test_duplicate_crow_entries_collapse_to_one(self):
        self._seed({"version": 1, "hooks": {"sessionStart": [
            {"command": "python /h/bin/crow_cli.py hook session-start"},
            {"command": "python /h/bin/crow_cli.py hook session-start"},
            {"command": "user-hook.sh"},
        ]}})
        self._merge()
        data = json.loads(_read(self.hooks))
        self.assertEqual(len(self._crow_entries(data, "sessionStart")), 1)
        self.assertIn("user-hook.sh",
                      [e.get("command") for e in data["hooks"]["sessionStart"]])

    def test_deploy_cursor_keeps_existing_hooks(self):
        self._seed({"version": 1, "hooks": {
            "beforeShellExecution": [{"command": "guard.sh"}]}})
        deploy_root = Path(self.tmp) / "deploy"
        install_plugin.deploy_cursor(self.home, deploy_root, self.log)
        data = json.loads(_read(self.hooks))
        self.assertEqual(data["hooks"]["beforeShellExecution"],
                         [{"command": "guard.sh"}])
        self.assertTrue((deploy_root / ".cursor" / "mcp.json").exists())
        self.assertTrue((deploy_root / ".cursor" / "rules").is_dir())


class AgentsMdUpsertTests(unittest.TestCase):
    """codex/zoo AGENTS.md gets a marked block instead of a whole-file copy."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_agents_")
        self.home = Path(self.tmp) / "home"
        self.deploy = Path(self.tmp) / "deploy"
        self.log = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _target(self, sub):
        return self.deploy / sub / "AGENTS.md"

    def test_codex_keeps_user_rules(self):
        target = self._target(".codex")
        target.parent.mkdir(parents=True)
        target.write_text("# My rules\n\n- never force push\n",
                          encoding="utf-8")
        install_plugin.deploy_codex(self.home, self.deploy, self.log)
        text = _read(target)
        self.assertIn("# My rules", text)
        self.assertIn("- never force push", text)
        self.assertEqual(text.count(install_plugin.MD_MARK_BEGIN), 1)
        self.assertEqual(text.count(install_plugin.MD_MARK_END), 1)
        self.assertIn(str(self.home), text)  # <CROW_HOME> was rewritten

    def test_zoo_re_run_adds_no_second_block(self):
        install_plugin.deploy_zoo_code(self.home, self.deploy, self.log)
        before = _read(self._target(".zoo"))
        self.log.clear()
        install_plugin.deploy_zoo_code(self.home, self.deploy, self.log)
        after = _read(self._target(".zoo"))
        self.assertEqual(before, after)
        self.assertEqual(after.count(install_plugin.MD_MARK_BEGIN), 1)
        self.assertTrue(any("unchanged" in line for line in self.log))


class FingerprintGuardTests(unittest.TestCase):
    """CR-1: a re-run must not re-ingest an already migrated bank."""

    ENTRIES = [
        {"key": "npm ci before build",
         "value": "always run npm ci before build for a stable lockfile",
         "register": "context", "polarity_net": 1.0, "importance": 2.0},
        {"key": "guard clauses first",
         "value": "return early instead of nesting conditionals",
         "register": "style", "polarity_net": 1.0, "importance": 1.5},
        {"key": "avoid global mutable state",
         "value": "pass state explicitly so tests stay isolated",
         "register": "arch", "polarity_net": -0.5, "importance": 1.0},
    ]

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_fp_")
        self.home = Path(self.tmp) / "home"
        self.bank = Path(self.tmp) / "bank.json"
        self._write_bank(self.ENTRIES)
        log = []
        install_plugin.deploy_tree(install_plugin.REPO_ROOT / "core",
                                   self.home / "core", self.home, log,
                                   only_py=True, rewrite=False)
        self.assertTrue((self.home / "core" / "migrate_from_v1.py").exists())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_bank(self, entries):
        self.bank.write_text(json.dumps({"entries": entries}), encoding="utf-8")

    def _run(self, force=False, bank=None):
        log = []
        install_plugin.run_migration(self.home, bank or self.bank, log,
                                     force=force)
        return log

    def _report(self, log):
        line = [ln for ln in log if ln.startswith("migrate   {")][-1]
        return json.loads(line[len("migrate   "):])

    def _sums(self):
        conn = sqlite3.connect(str(self.home / "crow.db"))
        try:
            return conn.execute(
                "SELECT count(*), sum(importance), sum(polarity_net) "
                "FROM memories").fetchone()
        finally:
            conn.close()

    def test_first_run_writes_fingerprint(self):
        rep = self._report(self._run())
        self.assertEqual(rep["inserted"], 3)
        self.assertFalse(rep["skipped_fingerprint_match"])
        fp_path = self.home / migrate_from_v1.FINGERPRINT_NAME
        self.assertTrue(fp_path.exists())
        stored = json.loads(_read(fp_path))
        self.assertEqual(sorted(stored), ["applied_at", "inserted", "merged",
                                          "processed", "src_mtime",
                                          "src_sha256"])
        self.assertEqual(stored["processed"], 3)
        self.assertEqual(stored["inserted"], 3)
        self.assertEqual(stored["merged"], 0)
        self.assertIsInstance(stored["applied_at"], float)
        # mtime is recorded for humans, never used for the match decision
        self.assertAlmostEqual(stored["src_mtime"],
                               os.stat(str(self.bank)).st_mtime, places=3)

    def test_second_run_skips_without_touching_the_db(self):
        self._run()
        db_path = self.home / "crow.db"
        sums_before = self._sums()
        mtime_before = os.stat(str(db_path)).st_mtime_ns
        rep = self._report(self._run())
        self.assertTrue(rep["skipped_fingerprint_match"])
        self.assertEqual(rep["processed"], 0)
        self.assertEqual(rep["inserted"], 0)
        self.assertEqual(self._sums(), sums_before)
        self.assertEqual(os.stat(str(db_path)).st_mtime_ns, mtime_before)

    def test_force_migrate_reapplies(self):
        self._run()
        sums_before = self._sums()
        rep = self._report(self._run(force=True))
        self.assertFalse(rep["skipped_fingerprint_match"])
        self.assertEqual(rep["merged"], 3)
        sums_after = self._sums()
        self.assertNotEqual(sums_after, sums_before)
        self.assertGreater(sums_after[2], sums_before[2])

    def test_changed_source_is_not_skipped(self):
        self._run()
        self._write_bank(self.ENTRIES + [{
            "key": "new row after edit", "value": "a fourth memory entry",
            "register": "bug", "polarity_net": -1.0, "importance": 1.0}])
        rep = self._report(self._run())
        self.assertFalse(rep["skipped_fingerprint_match"])
        self.assertEqual(rep["processed"], 4)
        self.assertEqual(rep["inserted"], 1)

    def test_missing_db_is_not_skipped(self):
        self._run()
        for name in ("crow.db", "crow.db-wal", "crow.db-shm"):
            try:
                os.remove(str(self.home / name))
            except OSError:
                pass
        rep = self._report(self._run())
        self.assertFalse(rep["skipped_fingerprint_match"])
        self.assertEqual(rep["inserted"], 3)

    def test_dry_run_does_not_write_a_fingerprint(self):
        rep = migrate_from_v1.migrate(str(self.bank), str(self.home),
                                      apply=False,
                                      src_prompt=os.path.join(
                                          REPO_ROOT, "memory",
                                          "system_prompt.md"))
        self.assertEqual(rep["processed"], 3)
        self.assertFalse((self.home /
                          migrate_from_v1.FINGERPRINT_NAME).exists())

    def test_source_fingerprint_ignores_mtime(self):
        first = migrate_from_v1.source_fingerprint(self.bank)
        self.assertEqual(first,
                         migrate_from_v1.source_fingerprint(self.bank))
        st = os.stat(str(self.bank))
        os.utime(str(self.bank), ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
        self.assertEqual(first,
                         migrate_from_v1.source_fingerprint(self.bank))

    def test_source_fingerprint_tracks_content(self):
        first = migrate_from_v1.source_fingerprint(self.bank)
        self._write_bank(self.ENTRIES + [{
            "key": "fourth", "value": "a fourth memory entry",
            "register": "bug", "polarity_net": -1.0, "importance": 1.0}])
        self.assertNotEqual(first,
                            migrate_from_v1.source_fingerprint(self.bank))

    def test_reformatted_source_changes_the_fingerprint(self):
        # same JSON value, different bytes (indent) -> content differs, so this
        # is a real content change and must re-fingerprint; only byte-identical
        # files may match
        first = migrate_from_v1.source_fingerprint(self.bank)
        self.bank.write_text(json.dumps({"entries": self.ENTRIES}, indent=2),
                             encoding="utf-8")
        self.assertNotEqual(first,
                            migrate_from_v1.source_fingerprint(self.bank))

    def test_copied_source_with_new_mtime_still_skips(self):
        self._run()
        sums_before = self._sums()
        copy = Path(self.tmp) / "restored" / "value_bank.json"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(self.bank), str(copy))
        st = os.stat(str(copy))
        os.utime(str(copy), ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
        rep = self._report(self._run(bank=copy))
        self.assertTrue(rep["skipped_fingerprint_match"])
        self.assertEqual(rep["processed"], 0)
        self.assertEqual(self._sums(), sums_before)


class McpMergeMalformedTests(unittest.TestCase):
    """R2-6: a malformed user mcp.json is skipped+warned, never fatal."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_mcp_")
        self.target = Path(self.tmp) / "mcp.json"
        self.snippet = install_plugin.ADAPTERS / "kimi-code" / "mcp.json.snippet"
        self.home = Path(self.tmp) / "home"
        self.log = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _merge(self):
        install_plugin.merge_mcp_server(self.target, self.snippet,
                                        "crow-memory", self.home, self.log)
        return json.loads(_read(self.target))

    def test_non_object_mcpservers_is_replaced(self):
        self.target.write_text(json.dumps({"mcpServers": "nope",
                                           "userKey": 1}), encoding="utf-8")
        data = self._merge()
        self.assertIsInstance(data["mcpServers"], dict)
        self.assertIn("crow-memory", data["mcpServers"])
        self.assertEqual(data["userKey"], 1)  # other keys survive
        self.assertTrue(any("WARN" in line for line in self.log))

    def test_non_object_top_level_is_recreated(self):
        self.target.write_text(json.dumps(["not", "an", "object"]),
                               encoding="utf-8")
        data = self._merge()
        self.assertIsInstance(data, dict)
        self.assertIn("crow-memory", data["mcpServers"])
        self.assertTrue(any("WARN" in line for line in self.log))

    def test_invalid_json_is_backed_up_and_recreated(self):
        self.target.write_text("{not json", encoding="utf-8")
        data = self._merge()
        self.assertIn("crow-memory", data["mcpServers"])
        self.assertTrue(_backups(self.target))

    def test_user_servers_are_preserved(self):
        self.target.write_text(json.dumps(
            {"mcpServers": {"user-server": {"command": "x"}}}),
            encoding="utf-8")
        data = self._merge()
        self.assertEqual(data["mcpServers"]["user-server"], {"command": "x"})
        self.assertIn("crow-memory", data["mcpServers"])


class DeployerIsolationTests(unittest.TestCase):
    """R2-6: one broken deploy target must not abort the whole install."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_iso_")
        self.home = os.path.join(self.tmp, "home")
        self.deploy = os.path.join(self.tmp, "deploy")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main(self, argv, patch):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CROW_DEPLOY_HOME": self.deploy}), \
                mock.patch.dict(install_plugin.DEPLOYERS, patch, clear=False), \
                contextlib.redirect_stdout(out):
            rc = install_plugin.main(["--home", self.home, *argv])
        return rc, out.getvalue()

    def test_failing_deployer_reports_partial_and_exits_zero(self):
        def boom(home, root, log):
            raise RuntimeError("malformed user config")

        rc, out = self._main(["--tools", "cursor,codex", "--no-migrate"],
                             {"cursor": boom})
        self.assertEqual(rc, 0, out)
        self.assertIn("FAILED (non-fatal)", out)
        self.assertIn("Partial install: 1/2", out)
        # the remaining tool still deployed
        self.assertTrue((Path(self.deploy) / ".codex" / "AGENTS.md").exists())

    def test_broken_user_config_does_not_abort_other_targets(self):
        deploy = Path(self.deploy)
        (deploy / ".cursor").mkdir(parents=True, exist_ok=True)
        (deploy / ".cursor" / "mcp.json").write_text(
            json.dumps({"mcpServers": []}), encoding="utf-8")
        (deploy / ".codex").mkdir(parents=True, exist_ok=True)
        (deploy / ".codex" / "AGENTS.md").write_bytes(
            b"\xff\xfe not utf-8 \xff\n")
        rc, out = self._main(["--tools", "cursor,codex", "--no-migrate"], {})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Partial install", out)  # both deployers survived
        self.assertEqual((deploy / ".codex" / "AGENTS.md").read_bytes(),
                         b"\xff\xfe not utf-8 \xff\n")  # untouched
        self.assertIn("crow-memory", json.loads(
            _read(deploy / ".cursor" / "mcp.json"))["mcpServers"])


class BackupCollisionTests(unittest.TestCase):
    """R2-10: two backups of one target inside a second must both survive."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_bak_")
        self.target = Path(self.tmp) / "hooks.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_second_backups_get_counter_suffixes(self):
        log = []
        with mock.patch.object(install_plugin, "timestamp",
                               return_value="20260101_000000"):
            self.target.write_text("first\n", encoding="utf-8")
            install_plugin._backup(self.target, log)
            self.target.write_text("second\n", encoding="utf-8")
            install_plugin._backup(self.target, log)
        names = _backups(self.target)
        self.assertEqual(len(names), 2, names)
        contents = sorted(_read(Path(self.tmp) / name) for name in names)
        self.assertEqual(contents, ["first\n", "second\n"])


class ProbeShimFlagsTests(unittest.TestCase):
    """CR-11: the probe subprocess must not flash a console window."""

    def setUp(self):
        self.log = []

    def test_probe_passes_create_no_window_flag(self):
        with mock.patch.object(install_plugin.subprocess, "run",
                               return_value=types.SimpleNamespace(
                                   returncode=0)) as run:
            flags = install_plugin.probe_shim_flags(self.log)
        self.assertEqual(flags, install_plugin.SHIM_FLAGS)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs.get("creationflags"),
                         getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertTrue(kwargs.get("capture_output"))
        self.assertEqual(kwargs.get("timeout"), 60)

    def test_falls_back_when_flags_do_not_work(self):
        with mock.patch.object(install_plugin.subprocess, "run",
                               return_value=types.SimpleNamespace(
                                   returncode=1)):
            flags = install_plugin.probe_shim_flags(self.log)
        self.assertEqual(flags, ())
        self.assertTrue(any("NOTE" in line for line in self.log))

    def test_missing_interpreter_is_skipped(self):
        with mock.patch.object(install_plugin.subprocess, "run",
                               side_effect=OSError("nope")):
            flags = install_plugin.probe_shim_flags(self.log)
        self.assertEqual(flags, ())


class InstallerEndToEndTests(unittest.TestCase):
    """Full installer run into a temp home + temp CROW_DEPLOY_HOME."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_install_e2e_")
        self.home = os.path.join(self.tmp, "home")
        self.deploy = os.path.join(self.tmp, "deploy")
        self.bank = os.path.join(self.tmp, "bank.json")
        with open(self.bank, "w", encoding="utf-8") as f:
            json.dump({"entries": [
                {"key": "installer e2e one", "value": "first temp memory",
                 "register": "context", "polarity_net": 1.0,
                 "importance": 2.0},
                {"key": "installer e2e two", "value": "second temp memory",
                 "register": "arch", "polarity_net": 1.0,
                 "importance": 1.0},
            ]}, f)
        # exercise the migrator that the installer copies into the home
        self.saved_migrator = sys.modules.pop("migrate_from_v1", None)

    def tearDown(self):
        sys.modules.pop("migrate_from_v1", None)
        if self.saved_migrator is not None:
            sys.modules["migrate_from_v1"] = self.saved_migrator
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main(self, *extra):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CROW_DEPLOY_HOME": self.deploy}), \
                contextlib.redirect_stdout(out):
            rc = install_plugin.main(["--home", self.home,
                                      "--src-json", self.bank, *extra])
        return rc, out.getvalue()

    def _sums(self):
        conn = sqlite3.connect(os.path.join(self.home, "crow.db"))
        try:
            return conn.execute(
                "SELECT count(*), sum(importance), sum(polarity_net) "
                "FROM memories").fetchone()
        finally:
            conn.close()

    def test_full_install_then_re_run_is_idempotent(self):
        rc, out = self._main("--tools", "all")
        self.assertEqual(rc, 0, out)
        home = Path(self.home)
        deploy = Path(self.deploy)
        self.assertTrue((home / "core" / "crow_cli.py").exists())
        self.assertTrue((home / "core" / "migrate_from_v1.py").exists())
        self.assertTrue((home / "bin" / "crow_cli.py").exists())
        self.assertTrue((home / "bin" / "crow_mcp_stdio.py").exists())
        if os.name == "nt":
            self.assertTrue((home / "bin" / "crow_cli.cmd").exists())
        self.assertTrue((home / "system_prompt.md").exists())
        self.assertTrue((home / ".migrated_v1.json").exists())

        config = _read(deploy / ".kimi-code" / "config.toml")
        self.assertEqual(config.count(install_plugin.TOML_MARK_BEGIN), 1)
        self.assertEqual(config.count(install_plugin.TOML_MARK_END), 1)
        self.assertTrue((deploy / ".kimi-code" / "mcp.json").exists())
        self.assertTrue((deploy / ".claude" / "plugins" / "crow-memory"
                         ).is_dir())
        self.assertTrue((deploy / ".gemini" / "config" / "plugins"
                         / "crow-memory").is_dir())
        self.assertTrue((deploy / ".clinerules").exists())
        for sub in (".cursor", ".codex", ".zoo"):
            self.assertTrue((deploy / sub).exists(), sub)
        cursor = json.loads(_read(deploy / ".cursor" / "hooks.json"))
        self.assertIn("sessionStart", cursor["hooks"])
        agents = _read(deploy / ".codex" / "AGENTS.md")
        self.assertEqual(agents.count(install_plugin.MD_MARK_BEGIN), 1)
        self.assertEqual(agents.count(install_plugin.MD_MARK_END), 1)

        sums_first = self._sums()
        self.assertEqual(sums_first[0], 2)

        rc2, out2 = self._main("--tools", "all")
        self.assertEqual(rc2, 0, out2)
        self.assertIn("unchanged", out2)
        self.assertNotIn("  updated ", out2)
        self.assertNotIn("  backup    ", out2)
        self.assertIn('"skipped_fingerprint_match": true', out2)
        self.assertEqual(self._sums(), sums_first)

    def test_force_migrate_flag_reapplies(self):
        rc, _ = self._main("--tools", "generic")
        self.assertEqual(rc, 0)
        sums_first = self._sums()
        rc2, out2 = self._main("--tools", "generic", "--force-migrate")
        self.assertEqual(rc2, 0, out2)
        self.assertNotIn('"skipped_fingerprint_match": true', out2)
        self.assertNotEqual(self._sums(), sums_first)

    def test_tool_subset_deploys_only_that_tool(self):
        rc, out = self._main("--tools", "cursor")
        self.assertEqual(rc, 0, out)
        deploy = Path(self.deploy)
        self.assertTrue((deploy / ".cursor" / "hooks.json").exists())
        self.assertFalse((deploy / ".kimi-code").exists())
        self.assertFalse((deploy / ".claude").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
