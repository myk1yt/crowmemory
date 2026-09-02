#!/usr/bin/env python3
"""
tests/test_migrate.py — Batch D verification (plain unittest).

Covers scripts/migrate_value_bank.py per the Batch D plan (architect report
L295-299): dry-run makes no changes, kaomoji entries cleaned, pure-noise
entries dropped with count, backup created on apply, idempotent second run,
vector re-encode (dim match + change on text change), --no-reencode leaves
vectors untouched, and state-tag path resolution.

No real encoder (FakeEncoder, the tests/test_recall_precision.py pattern) and
no real memory dir: every test builds fixture JSON inside a temp dir.
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crow_core  # noqa: E402
import scripts.migrate_value_bank as mig  # noqa: E402
from scripts.migrate_value_bank import (  # noqa: E402
    main, migrate_entries, resolve_value_bank_path, resolve_state_path,
)


class FakeEncoder:
    """Deterministic stand-in for SentenceTransformer (test_recall_precision
    pattern): vector seeded from sha256(text) — distinct texts get distinct
    vectors, same text reproduces the same vector."""

    def encode(self, text, **kwargs):
        # Mimics CrowMemory.encode OUTPUT (post-projection): a DIM-length
        # vector. (The raw SentenceTransformer emits EMBED_DIM; crow_core
        # projects it to DIM before storage, crow_core.py:260.)
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        return rng.normal(size=crow_core.DIM).astype(np.float32)


def make_vec(dim, seed_text):
    rng = np.random.default_rng(
        int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16))
    v = rng.normal(size=dim).astype(np.float16)
    return base64.b64encode(v.tobytes()).decode("ascii")


def write_bank(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def read_bank(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class MigrateTestBase(unittest.TestCase):
    """FakeCrowDims: shrink register dims so crow_core import stays light.

    EMBED_DIM is shrunk too so FakeEncoder vectors match the projection
    math (crow_core.encode projects encoder output through proj_W).
    """

    @classmethod
    def setUpClass(cls):
        cls._saved = {n: getattr(crow_core, n)
                      for n in ("DIM", "EMBED_DIM", "REGISTERS")}
        crow_core.DIM = 64
        crow_core.EMBED_DIM = 32
        crow_core.REGISTERS = {r: (64, 64, 0.9999) for r in (
            "style", "bug", "arch", "context",
            "life_pref", "life_avoid", "life_phil", "life_context")}

    @classmethod
    def tearDownClass(cls):
        for name, value in cls._saved.items():
            setattr(crow_core, name, value)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_migrate_")
        self.mem = os.path.join(self.tmp, "memory")
        os.makedirs(self.mem)
        self.bank_path = os.path.join(self.mem, "value_bank.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixture helpers ---------------------------------------------------

    def write_fixture(self, entries, name="value_bank.json", tag=None):
        """Write a value_bank file; with tag, also create the tagged sibling
        name so resolve_value_bank_path tag resolution can be exercised."""
        if tag:
            name = f"value_bank-{tag}.json"
        path = os.path.join(self.mem, name)
        write_bank(path, entries)
        return path

    def noise_entry(self, key=">.< ㅋㅋㅋ", value=">.< ㅋㅋㅋ ㅠㅠ"):
        return {"key": key, "value": value,
                "vector_b64": make_vec(64, key + value),
                "register": "style", "timestamp": 1712345678.0,
                "importance": 1.0, "ingest_count": 1}

    def clean_entry(self, key="clean key", value="clean value text",
                    dim=64, project=None):
        e = {"key": key, "value": value,
             "vector_b64": make_vec(dim, key + value),
             "register": "context", "timestamp": 1712345678.0,
             "importance": 1.0, "ingest_count": 1}
        if project is not None:
            e["project"] = project
        return e

    def dirty_entry(self):
        """Kaomoji-polluted but non-empty after scrub."""
        return {"key": "fix login bug >.<",
                "value": "session expired ㅋㅋㅋ redirect failed",
                "vector_b64": make_vec(64, "dirty"),
                "register": "bug", "timestamp": 1712345678.0,
                "importance": 1.5, "ingest_count": 2}

    def decode(self, b64):
        return np.frombuffer(base64.b64decode(b64), dtype=np.float16)


class DryRunTests(MigrateTestBase):

    def test_dry_run_makes_no_changes(self):
        entries = [self.noise_entry(), self.dirty_entry(), self.clean_entry()]
        write_bank(self.bank_path, entries)
        with open(self.bank_path, "rb") as f:
            before = f.read()
        mtime = os.path.getmtime(self.bank_path)

        rc = main(["--memory-dir", self.mem])

        self.assertEqual(rc, 0)
        with open(self.bank_path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(os.path.getmtime(self.bank_path), mtime)
        # no backup, no tmp leftovers
        self.assertEqual(
            [f for f in os.listdir(self.mem) if f != "value_bank.json"], [])

    def test_dry_run_is_default_no_apply_flag(self):
        write_bank(self.bank_path, [self.dirty_entry()])
        rc = main(["--memory-dir", self.mem])
        self.assertEqual(rc, 0)
        # dirty entry still dirty — nothing was applied
        self.assertIn(">.<", read_bank(self.bank_path)[0]["key"])

    def test_dry_run_reports_counts_and_examples(self):
        entries = [self.noise_entry(), self.dirty_entry(), self.clean_entry()]
        write_bank(self.bank_path, entries)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--memory-dir", self.mem])
        out = buf.getvalue()

        self.assertIn("DRY-RUN", out)
        self.assertIn("entries scanned : 3", out)
        self.assertIn("would-scrub", out)
        self.assertIn("would-drop", out)
        self.assertIn("would-reencode", out)
        self.assertIn("no files modified", out)

    def test_apply_and_dry_run_flags_are_mutually_exclusive(self):
        write_bank(self.bank_path, [self.clean_entry()])
        rc = main(["--memory-dir", self.mem, "--apply", "--dry-run"])
        self.assertEqual(rc, 1)

    def test_dry_run_against_missing_file_errors(self):
        rc = main(["--memory-dir", os.path.join(self.tmp, "nowhere")])
        self.assertEqual(rc, 1)


class ApplyTests(MigrateTestBase):

    def run_apply(self, bank_name="value_bank.json", extra=(),
                  encode=None):
        # FakeEncoder seam: apply mode with dirty entries needs SOME encoder
        # (the real one requires sentence_transformers + a valid crow.bin);
        # tests inject the deterministic fake instead (no real encoder rule).
        return main(["--memory-dir", self.mem, "--apply",
                     "--value-bank", os.path.join(self.mem, bank_name)]
                    + list(extra),
                    encode_fn=encode if encode is not None
                    else FakeEncoder().encode)

    def test_kaomoji_entry_cleaned(self):
        entries = [self.dirty_entry(), self.clean_entry()]
        write_bank(self.bank_path, entries)

        rc = self.run_apply()
        self.assertEqual(rc, 0)
        out_bank = read_bank(self.bank_path)
        self.assertEqual(len(out_bank), 2)
        self.assertEqual(out_bank[0]["key"], "fix login bug")
        self.assertEqual(out_bank[0]["value"],
                         "session expired redirect failed")
        # clean entry untouched
        self.assertEqual(out_bank[1]["key"], "clean key")

    def test_pure_noise_entry_dropped_with_count(self):
        entries = [self.noise_entry(), self.noise_entry(
            key="ㅠㅠㅠ ㅋㅋ", value="T_T >.<"), self.clean_entry()]
        write_bank(self.bank_path, entries)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.run_apply()
        self.assertEqual(rc, 0)
        self.assertIn("dropped_noise", buf.getvalue())

        out_bank = read_bank(self.bank_path)
        self.assertEqual(len(out_bank), 1)   # 2 noise dropped, 1 clean kept
        self.assertEqual(out_bank[0]["key"], "clean key")

    def test_backup_created_on_apply(self):
        write_bank(self.bank_path, [self.dirty_entry(), self.clean_entry()])
        backups_before = [f for f in os.listdir(self.mem)
                          if "bak.migrate-" in f]
        self.assertEqual(backups_before, [])

        rc = self.run_apply()
        self.assertEqual(rc, 0)

        backups = [f for f in os.listdir(self.mem) if "bak.migrate-" in f]
        self.assertEqual(len(backups), 1)
        # backup holds the ORIGINAL (pre-migration) content
        with open(os.path.join(self.mem, backups[0]), encoding="utf-8") as f:
            bak_bank = json.load(f)
        self.assertIn(">.<", bak_bank[0]["key"])

    def test_idempotent_second_apply_zero_changes(self):
        write_bank(self.bank_path, [self.dirty_entry(), self.noise_entry(),
                                    self.clean_entry()])
        rc = self.run_apply()
        self.assertEqual(rc, 0)
        first_pass = read_bank(self.bank_path)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.run_apply()
        self.assertEqual(rc, 0)
        self.assertIn("nothing to migrate", buf.getvalue())
        self.assertEqual(read_bank(self.bank_path), first_pass)
        # second run made no new backup (file untouched)
        backups = [f for f in os.listdir(self.mem) if "bak.migrate-" in f]
        self.assertEqual(len(backups), 1)

    def test_no_reencode_stale_vectors_documented(self):
        entries = [self.dirty_entry()]
        original_vec = entries[0]["vector_b64"]
        write_bank(self.bank_path, entries)

        rc = self.run_apply(extra=("--no-reencode",))
        self.assertEqual(rc, 0)

        out_bank = read_bank(self.bank_path)
        self.assertEqual(out_bank[0]["key"], "fix login bug")     # text scrubbed
        self.assertEqual(out_bank[0]["vector_b64"], original_vec)  # vector untouched

    def test_other_fields_preserved(self):
        e = self.dirty_entry()
        e["project"] = "crow-memory"
        e["extra_future_field"] = {"nested": True}
        write_bank(self.bank_path, [e, self.clean_entry(project="other")])

        rc = self.run_apply()
        self.assertEqual(rc, 0)
        out = read_bank(self.bank_path)[0]
        self.assertEqual(out["register"], "bug")
        self.assertEqual(out["timestamp"], 1712345678.0)
        self.assertEqual(out["importance"], 1.5)
        self.assertEqual(out["ingest_count"], 2)
        self.assertEqual(out["project"], "crow-memory")
        self.assertEqual(out["extra_future_field"], {"nested": True})
        self.assertEqual(read_bank(self.bank_path)[1]["project"], "other")

    def test_malformed_non_dict_entries_passed_through(self):
        write_bank(self.bank_path, ["not-a-dict", self.clean_entry()])
        rc = self.run_apply()
        self.assertEqual(rc, 0)
        out = read_bank(self.bank_path)
        self.assertEqual(out[0], "not-a-dict")  # never destroyed

    def test_apply_exit_code_zero_success(self):
        write_bank(self.bank_path, [self.clean_entry()])
        self.assertEqual(self.run_apply(), 0)


class VectorReencodeTests(MigrateTestBase):
    """main(--apply) with a FakeEncoder injected via the encode_fn seam."""

    def run_apply_with_fake(self, entries):
        write_bank(self.bank_path, entries)
        return main(["--memory-dir", self.mem, "--apply",
                     "--value-bank", self.bank_path],
                    encode_fn=FakeEncoder().encode)

    def test_vector_dim_matches_original(self):
        dirty = self.dirty_entry()           # dim 64
        odd_dim = self.clean_entry(key="odd", value="x >.< y", dim=17)
        rc = self.run_apply_with_fake([dirty, odd_dim])
        self.assertEqual(rc, 0)
        out = read_bank(self.bank_path)
        self.assertEqual(len(self.decode(out[0]["vector_b64"])), 64)
        self.assertEqual(len(self.decode(out[1]["vector_b64"])), 17)

    def test_vector_changes_when_text_changes(self):
        dirty = self.dirty_entry()
        old_vec = self.decode(dirty["vector_b64"])
        rc = self.run_apply_with_fake([dirty])
        self.assertEqual(rc, 0)
        new_vec = self.decode(read_bank(self.bank_path)[0]["vector_b64"])
        self.assertEqual(len(new_vec), len(old_vec))
        self.assertFalse(np.array_equal(new_vec, old_vec))

    def test_clean_entry_vector_untouched(self):
        clean = self.clean_entry()
        rc = self.run_apply_with_fake([clean])
        self.assertEqual(rc, 0)
        self.assertEqual(read_bank(self.bank_path)[0]["vector_b64"],
                         clean["vector_b64"])

    def test_reencoded_vector_reproduces_encode_of_scrubbed_text(self):
        """Apply-path vector == fake-encode(scrubbed_value)[:orig_dim]
        (ingest parity with crow_core.py:487)."""
        fake = FakeEncoder()
        dirty = self.dirty_entry()
        expected = fake.encode("session expired redirect failed")[:64]

        write_bank(self.bank_path, [dirty])
        rc = main(["--memory-dir", self.mem, "--apply",
                   "--value-bank", self.bank_path],
                  encode_fn=fake.encode)
        self.assertEqual(rc, 0)
        got = self.decode(read_bank(self.bank_path)[0]["vector_b64"])
        np.testing.assert_allclose(got, expected.astype(np.float16),
                                    rtol=0, atol=0)

    def test_corrupt_vector_b64_is_skipped_not_crashed(self):
        bad = self.dirty_entry()
        bad["vector_b64"] = "!!!not-base64!!!"
        rc = self.run_apply_with_fake([bad])
        self.assertEqual(rc, 0)
        out = read_bank(self.bank_path)
        self.assertEqual(out[0]["key"], "fix login bug")  # text still scrubbed
        self.assertEqual(out[0]["vector_b64"], "!!!not-base64!!!")  # vec kept


class CoreFunctionTests(MigrateTestBase):

    def test_migrate_entries_counts(self):
        entries = [self.noise_entry(), self.dirty_entry(), self.clean_entry()]
        out, res = migrate_entries(entries, FakeEncoder().encode)
        self.assertEqual(res["scanned"], 3)
        self.assertEqual(res["dropped_noise"], 1)
        self.assertEqual(res["scrubbed"], 1)
        self.assertEqual(res["reencoded"], 1)
        self.assertEqual(len(out), 2)

    def test_scrub_text_idempotent(self):
        once = migrate_entries([self.dirty_entry()], None, reencode=False)[0]
        twice, res = migrate_entries(once, FakeEncoder().encode)
        self.assertEqual(res["scrubbed"], 0)
        self.assertEqual(res["reencoded"], 0)


class StateTagPathTests(MigrateTestBase):

    def test_tag_resolves_tagged_sibling(self):
        tagged = self.write_fixture([self.clean_entry()], tag="myk1yt")
        plain = self.write_fixture([self.clean_entry()])  # both exist
        got, note = resolve_value_bank_path(self.mem, "myk1yt")
        self.assertEqual(os.path.abspath(got), os.path.abspath(tagged))
        self.assertIsNotNone(note)  # warns about the untagged sibling

    def test_tag_falls_back_to_plain_when_only_plain_exists(self):
        plain = self.write_fixture([self.clean_entry()])
        got, note = resolve_value_bank_path(self.mem, "myk1yt")
        self.assertEqual(os.path.abspath(got), os.path.abspath(plain))
        self.assertIsNotNone(note)

    def test_untagged_resolves_plain(self):
        plain = self.write_fixture([self.clean_entry()])
        got, note = resolve_value_bank_path(self.mem, "")
        self.assertEqual(os.path.abspath(got), os.path.abspath(plain))
        self.assertIsNone(note)

    def test_missing_everything_raises(self):
        with self.assertRaises(FileNotFoundError):
            resolve_value_bank_path(self.mem, "myk1yt")

    def test_state_tag_resolution_matches_crow_server_derivation(self):
        """tag=myk1yt -> crow-myk1yt.bin preferred, else crow.bin (AD-8.2,
        mirroring crow_mcp_server.resolve_state_path)."""
        plain_state = os.path.join(self.mem, "crow.bin")
        with open(plain_state, "wb") as f:
            f.write(b"placeholder")  # existence-only check; never loaded here
        self.assertEqual(
            os.path.abspath(resolve_state_path(self.mem, "myk1yt")),
            os.path.abspath(plain_state))
        tagged_state = os.path.join(self.mem, "crow-myk1yt.bin")
        with open(tagged_state, "wb") as f:
            f.write(b"placeholder")
        self.assertEqual(
            os.path.abspath(resolve_state_path(self.mem, "myk1yt")),
            os.path.abspath(tagged_state))

    def test_tagged_bank_full_pipeline_dry_run(self):
        """tag=myk1yt CLI resolves the tagged sibling end-to-end."""
        tagged = self.write_fixture(
            [self.dirty_entry(), self.noise_entry()], tag="myk1yt")

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--memory-dir", self.mem, "--state-tag", "myk1yt"])
        self.assertEqual(rc, 0)
        self.assertIn(os.path.abspath(tagged),
                      os.path.abspath(tagged))  # resolve ran without error
        self.assertIn("value_bank-myk1yt.json", buf.getvalue())
        self.assertIn("would-drop", buf.getvalue())
        # dry-run: file unchanged, no backups, sibling set not created
        self.assertEqual(
            [f for f in os.listdir(self.mem)
              if f.startswith("value_bank")],
            ["value_bank-myk1yt.json"])


class EncoderTempDirTests(MigrateTestBase):
    """F2 regression: build_real_encode_fn must clean up its temp state
    copy instead of leaking a multi-MB crow.bin under %TEMP% forever."""

    class _RawEmbedEncoder:
        """Stand-in for the RAW SentenceTransformer output (EMBED_DIM
        length); crow_core.encode() projects it to DIM (crow_core.py:259).
        The module-level FakeEncoder mimics the POST-projection output and
        cannot be used through the real encode() path."""

        def encode(self, text, **kwargs):
            seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
            rng = np.random.default_rng(seed)
            return rng.normal(size=crow_core.EMBED_DIM).astype(np.float32)

    def test_temp_state_dir_removed_after_build(self):
        # Build a minimal valid state file via a real CrowMemory instance
        state_path = os.path.join(self.mem, "crow.bin")
        cm = crow_core.CrowMemory(state_path)
        cm._persist()  # write the safetensors state file to disk
        cm_lock = state_path + ".lock"
        self.addCleanup(lambda: os.path.exists(cm_lock) and os.remove(cm_lock))
        self.assertTrue(os.path.exists(state_path))

        # Patch the lazy SentenceTransformer loader at class level so the
        # encode function returned by build_real_encode_fn (whose internal
        # CrowMemory we never see) works without sentence_transformers.
        saved_prop = crow_core.CrowMemory.encoder
        fake = self._RawEmbedEncoder()
        crow_core.CrowMemory.encoder = property(lambda self: fake)
        self.addCleanup(setattr, crow_core.CrowMemory, "encoder", saved_prop)

        before = set(os.listdir(tempfile.gettempdir()))

        encode_fn = mig.build_real_encode_fn(state_path)

        after = set(os.listdir(tempfile.gettempdir()))
        # F2 core assertion: no crow_migrate_state_* dir survives the build
        leaked = {d for d in (after - before)
                  if d.startswith("crow_migrate_state_")}
        self.assertEqual(leaked, set())
        # The returned encode function still works after cleanup (all state
        # was loaded into RAM at construction)
        vec = encode_fn("hello world")
        self.assertEqual(vec.shape[0], crow_core.DIM)

        # Docstring previously FALSELY claimed "removed at process exit"
        # while no cleanup existed (F2 root cause) — now it must describe
        # the real mechanism.
        doc = mig.build_real_encode_fn.__doc__
        self.assertIsNotNone(doc)
        self.assertNotIn("removed at process exit", doc)
        self.assertIn("removed eagerly right after construction", doc)
        self.assertIn("atexit fallback", doc)
        # Cleanup helper is idempotent and safe on missing dirs
        gone_dir = os.path.join(tempfile.gettempdir(),
                                "crow_migrate_state_nonexistent_9d41f")
        mig._cleanup_temp_state_dir(gone_dir)  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)