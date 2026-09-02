#!/usr/bin/env python3
"""
tests/test_merge.py — Global value_bank merge verification (plain unittest).

Covers scripts/merge_value_bank.py (User Decision A): exact dup metadata
merge, key dup, near-dup skip, unique migration with project preservation,
noise drop in both sets, backup of both files on apply, dry-run no changes,
idempotent second run, cap-overflow pruning mirroring the crow_core rule,
and metadata-merge parity against the REAL `_append_value_bank` method.

No real encoder (FakeEncoder, the tests/test_migrate.py pattern) and no
real memory dir: every test builds fixture JSON inside a temp dir.
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crow_core  # noqa: E402
import scripts.merge_value_bank as mv  # noqa: E402
from scripts.merge_value_bank import main, plan_merge, assemble  # noqa: E402


class FakeEncoder:
    """Deterministic stand-in for SentenceTransformer (test_migrate pattern):
    vector seeded from sha256(text) — distinct texts get distinct vectors,
    same text reproduces the same vector. Mimics CrowMemory.encode OUTPUT
    (post-projection, DIM-length)."""

    def encode(self, text, **kwargs):
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        return rng.normal(size=crow_core.DIM).astype(np.float32)

    __call__ = encode  # callable like build_real_encode_fn's bound method


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


def entry(key, value, register="context", dim=64, importance=1.0,
          ingest_count=1, timestamp=1712345678.0, project=None):
    e = {"key": key, "value": value,
         "vector_b64": make_vec(dim, key + "|" + value),
         "register": register, "timestamp": timestamp,
         "importance": importance, "ingest_count": ingest_count}
    if project is not None:
        e["project"] = project
    return e


class MergeTestBase(unittest.TestCase):
    """FakeCrowDims: shrink register dims so crow_core stays light (the
    test_migrate.py pattern)."""

    @classmethod
    def setUpClass(cls):
        cls._saved = {n: getattr(crow_core, n)
                      for n in ("DIM", "EMBED_DIM", "REGISTERS",
                                "VALUE_BANK_MAX")}
        crow_core.DIM = 64
        crow_core.EMBED_DIM = 32
        crow_core.REGISTERS = {r: (64, 64, 0.9999) for r in (
            "style", "bug", "arch", "context",
            "life_pref", "life_avoid", "life_phil", "life_context")}
        crow_core.VALUE_BANK_MAX = 500

    @classmethod
    def tearDownClass(cls):
        for name, value in cls._saved.items():
            setattr(crow_core, name, value)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_merge_")
        self.primary = os.path.join(self.tmp, "value_bank.json")
        self.secondary = os.path.join(self.tmp, "value_bank-myk1yt.json")
        self.fake = FakeEncoder()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def write_fixtures(self, primary, secondary):
        write_bank(self.primary, primary)
        write_bank(self.secondary, secondary)

    def run_main(self, *extra, encode_fn=None):
        argv = ["--primary", self.primary, "--secondary", self.secondary,
                *extra]
        return main(argv, encode_fn=encode_fn)

    def file_state(self, path):
        with open(path, "rb") as f:
            data = f.read()
        return data, os.path.getmtime(path)

    def baks(self, path):
        d = os.path.dirname(path)
        base = os.path.basename(path)
        return [n for n in os.listdir(d) if n.startswith(base + ".bak.")]


class TestDryRun(MergeTestBase):

    def test_dry_run_default_no_changes(self):
        p = [entry("pk1", "primary one", importance=2.0),
             entry(">.< ㅋㅋㅋ", "noise >.< value")]       # primary noise
        s = [entry("pk1", "primary one", importance=0.5),  # exact dup
             entry("sk1", ">.< ㅋㅋㅋ ㅠㅠ"),               # secondary noise
             entry("sk2", "secondary unique", project="proj-x")]
        self.write_fixtures(p, s)
        st_p, st_s = self.file_state(self.primary), \
            self.file_state(self.secondary)
        rc = self.run_main()  # no --apply
        self.assertEqual(rc, 0)
        self.assertEqual(st_p, self.file_state(self.primary))
        self.assertEqual(st_s, self.file_state(self.secondary))
        self.assertEqual(self.baks(self.primary), [])  # no backup in dry-run

    def test_explicit_dry_run_and_apply_conflict(self):
        self.write_fixtures([entry("k", "v")], [entry("k2", "v2")])
        rc = self.run_main("--apply", "--dry-run")
        self.assertEqual(rc, 1)

    def test_dry_run_reports_counts(self):
        import io
        from contextlib import redirect_stdout
        p = [entry("dup", "shared text"),
             entry("near-owner", "some long text about testing",
                   importance=2.0)]
        s_vec = make_vec(64, "near-owner|some long text about testing")
        s = [entry("dup", "shared text", importance=0.5),   # exact dup
             entry("near", "some long text about testing",  # near dup
                   register="context", dim=64),
             entry("uniq", "totally different thing")]
        # force the near-dup's vector to equal the primary's (cos 1.0)
        s[1]["vector_b64"] = s_vec
        self.write_fixtures(p, s)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.run_main()
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("exact dup", out)
        self.assertIn("near dup", out)
        self.assertIn("unique secondary entries: 1", out)
        self.assertIn("no files modified (dry-run)", out)

    def test_missing_files_error(self):
        write_bank(self.primary, [entry("k", "v")])  # no secondary
        self.assertEqual(self.run_main(), 1)
        os.remove(self.primary)
        write_bank(self.secondary, [entry("k", "v")])  # no primary
        self.assertEqual(self.run_main(), 1)

    def test_same_file_error(self):
        self.write_fixtures([entry("k", "v")], [entry("k", "v")])
        rc = main(["--primary", self.primary, "--secondary", self.primary],
                  encode_fn=None)
        self.assertEqual(rc, 1)

    def test_default_paths_resolve_in_memory_dir(self):
        # fixtures exist at the default-derived names inside --memory-dir
        self.write_fixtures([entry("pk", "primary text")],
                            [entry("sk", "secondary text")])
        rc = main(["--memory-dir", self.tmp], encode_fn=None)
        self.assertEqual(rc, 0)

    def test_default_memory_dir_missing_files_error(self):
        # --memory-dir with no value_bank files -> resolve error, exit 1
        rc = main(["--memory-dir", self.tmp], encode_fn=None)
        self.assertEqual(rc, 1)


class TestExactAndKeyDup(MergeTestBase):

    def test_exact_dup_primary_wins_metadata_merged(self):
        # a unique secondary entry rides along: per task rule #7, a
        # secondary FULLY contained (dups only) is the "already merged"
        # no-op state, so the dup-metadata merge is only reachable
        # alongside real migration work.
        p = [entry("dup", "shared text", register="style",
                   importance=1.5, ingest_count=2, timestamp=200.0,
                   project="projA")]
        s = [entry("dup", "shared text", register="style",
                   importance=0.8, ingest_count=1, timestamp=100.0,
                   project="projB"),
             entry("sk", "unique secondary value", register="context")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)  # 1 primary + 1 unique migrated
        m = next(e for e in merged if e["key"] == "dup")
        # primary text/vector identity preserved
        self.assertEqual(m["value"], "shared text")
        self.assertEqual(m["vector_b64"], p[0]["vector_b64"])
        self.assertEqual(m["project"], "projA")  # core never merges project
        # core re-ingest accumulation (crow_core.py:595-597): sum + newest
        self.assertAlmostEqual(m["importance"], 2.3, places=5)
        self.assertEqual(m["ingest_count"], 3)
        self.assertEqual(m["timestamp"], 200.0)  # newest wins

    def test_key_dup_different_value_keeps_primary_text(self):
        p = [entry("dup", "primary version", register="style",
                   importance=1.0, ingest_count=1, timestamp=100.0)]
        s = [entry("dup", "secondary version", register="style",
                   importance=0.5, ingest_count=1, timestamp=300.0),
             entry("sk", "unique secondary value", register="context")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)
        m = next(e for e in merged if e["key"] == "dup")
        self.assertEqual(m["value"], "primary version")
        self.assertEqual(m["vector_b64"], p[0]["vector_b64"])
        self.assertAlmostEqual(m["importance"], 1.5, places=5)
        self.assertEqual(m["ingest_count"], 2)
        self.assertEqual(m["timestamp"], 300.0)

    def test_multiple_secondary_dups_collapse_onto_one_primary(self):
        p = [entry("dup", "shared", importance=1.0, ingest_count=1)]
        s = [entry("dup", "shared", importance=0.5, ingest_count=1),
             entry("dup", "shared", importance=0.25, ingest_count=1)]
        self.write_fixtures(p, s)
        plan = plan_merge(p, s)
        merged, stats, pruned, _ = assemble(plan, self.fake, cap=500)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0]["importance"], 1.75, places=5)
        self.assertEqual(merged[0]["ingest_count"], 3)

    def test_exact_dup_requires_same_register(self):
        # core identity is (register, key) — same key, different register
        # is NOT a dup (crow_core.py:588)
        p = [entry("dup", "shared text", register="style")]
        s = [entry("dup", "shared text", register="context")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)
        regs = {m["register"] for m in merged}
        self.assertEqual(regs, {"style", "context"})


class TestNearDup(MergeTestBase):

    def _perturbed_vec(self, base_b64, noise_scale=0.3):
        v = crow_core.CrowMemory._decode_vector(base_b64).astype(np.float32)
        rng = np.random.default_rng(1234)
        v2 = v + noise_scale * rng.normal(size=v.shape).astype(np.float32)
        return base64.b64encode(v2.astype(np.float16).tobytes()).decode("ascii")

    def test_near_dup_skipped_no_metadata_merge(self):
        pv = make_vec(64, "nearbase")
        p = [entry("pk", "primary long text", importance=2.0,
                   ingest_count=2)]
        p[0]["vector_b64"] = pv
        s = [entry("sk", "a slightly different wording entirely",
                   importance=0.7, ingest_count=1)]
        s[0]["vector_b64"] = self._perturbed_vec(pv)  # cos ~0.95
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 1)  # near-dup NOT migrated
        # no metadata merge for near-dups
        self.assertAlmostEqual(merged[0]["importance"], 2.0, places=5)
        self.assertEqual(merged[0]["ingest_count"], 2)

    def test_near_threshold_flag(self):
        pv = make_vec(64, "nearbase")
        p = [entry("pk", "primary long text")]
        p[0]["vector_b64"] = pv
        s = [entry("sk", "slightly different wording")]
        s[0]["vector_b64"] = self._perturbed_vec(pv)  # cos ~0.95

        # threshold 0.90 -> near-dup -> merged length stays 1
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", "--near-threshold", "0.90",
                           encode_fn=self.fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(read_bank(self.primary)), 1)

        # threshold 0.99 -> not near -> migrated -> length 2
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", "--near-threshold", "0.99",
                           encode_fn=self.fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(read_bank(self.primary)), 2)

    def test_near_dup_requires_same_register(self):
        pv = make_vec(64, "nearbase2")
        p = [entry("pk", "primary long text", register="style")]
        p[0]["vector_b64"] = pv
        s = [entry("sk", "a slightly different wording",
                   register="context")]  # different register, same vector
        s[0]["vector_b64"] = pv  # cos 1.0 but cross-register
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)


class TestUniqueMigration(MergeTestBase):

    def test_unique_migrated_with_project_preserved(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text", project="crow-memory",
                   importance=1.7, ingest_count=4, timestamp=555.0)]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)
        migrated = next(m for m in merged if m["key"] == "sk")
        self.assertEqual(migrated["project"], "crow-memory")
        self.assertEqual(migrated["value"], "secondary text")
        self.assertAlmostEqual(migrated["importance"], 1.7, places=5)
        self.assertEqual(migrated["ingest_count"], 4)
        self.assertEqual(migrated["timestamp"], 555.0)
        self.assertEqual(migrated["vector_b64"], s[0]["vector_b64"])

    def test_scrubbed_unique_reencoded_to_scrubbed_text(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "value >.< with kaomoji ㅋㅋㅋ tail")]
        s[0]["vector_b64"] = make_vec(64, "sk|value  with kaomoji tail")
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        migrated = next(m for m in merged if m["key"] == "sk")
        scrubbed = mv.scrub_text("value >.< with kaomoji ㅋㅋㅋ tail")
        self.assertEqual(migrated["value"], scrubbed)
        expect = self.fake.encode(scrubbed)[:64]
        self.assertEqual(migrated["vector_b64"],
                         crow_core.CrowMemory._encode_vector(expect))

    def test_no_reencode_leaves_stale_vector(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "value >.< with kaomoji")]
        orig_vec = s[0]["vector_b64"]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", "--no-reencode", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        migrated = next(m for m in merged if m["key"] == "sk")
        self.assertEqual(migrated["value"],
                         mv.scrub_text("value >.< with kaomoji"))
        self.assertEqual(migrated["vector_b64"], orig_vec)  # stale, kept

    def test_corrupt_vector_entry_not_crashed(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        s[0]["vector_b64"] = "!!!not-base64!!!"
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 2)  # migrated despite undecodable vec


class TestNoiseAndMalformed(MergeTestBase):

    def test_noise_dropped_in_both_sets(self):
        p = [entry("pk", "real primary text"),
             entry("np", ">.< ㅋㅋㅋ ㅠㅠ")]          # primary pure noise
        s = [entry("ns", "ㅠㅠ ㅋㅋ >.<"),          # secondary pure noise
             entry("sk", "real secondary text")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        keys = [m["key"] for m in merged]
        self.assertEqual(sorted(keys), ["pk", "sk"])  # both noise gone

    def test_malformed_entries_passed_through_both_sets(self):
        p = [entry("pk", "primary text"), "i-am-not-a-dict"]
        s = [42, entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 4)  # 2 entries + 2 passthrough
        self.assertIn("i-am-not-a-dict", merged)
        self.assertIn(42, merged)


class TestApplySafety(MergeTestBase):

    def test_backups_created_and_hold_originals(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        pb = self.baks(self.primary)
        sb = self.baks(self.secondary)
        self.assertEqual(len(pb), 1)
        self.assertEqual(len(sb), 1)
        # backups hold the ORIGINAL pre-merge content
        self.assertEqual(read_bank(os.path.join(self.tmp, pb[0])), p)
        self.assertEqual(read_bank(os.path.join(self.tmp, sb[0])), s)

    def test_secondary_left_untouched_on_apply(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        before = self.file_state(self.secondary)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        self.assertEqual(before, self.file_state(self.secondary))

    def test_atomic_write_no_tmp_left_behind(self):
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        leftovers = [n for n in os.listdir(self.tmp) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestIdempotency(MergeTestBase):

    def test_second_apply_is_zero_change_no_write(self):
        p = [entry("pk", "primary text"),
             entry("pd", "dup text", importance=1.0)]
        s = [entry("pd", "dup text", importance=0.5),
             entry("sk", "secondary unique", project="p")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(read_bank(self.primary)), 3)  # 2 + 1 migrated
        first_baks = self.baks(self.primary)
        after_first = self.file_state(self.primary)

        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)  # already-merged exit is still success
        # no new backups, primary byte-identical (metadata NOT re-summed)
        self.assertEqual(self.baks(self.primary), first_baks)
        self.assertEqual(self.file_state(self.primary), after_first)
        merged = read_bank(self.primary)
        pd = next(m for m in merged if m["key"] == "pd")
        self.assertAlmostEqual(pd["importance"], 1.5, places=5)

    def test_dry_run_after_apply_reports_already_merged(self):
        import io
        from contextlib import redirect_stdout
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        self.run_main("--apply", encode_fn=self.fake)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("already merged", buf.getvalue())


class TestCapOverflow(MergeTestBase):
    """VALUE_BANK_MAX handling — mirrors the crow_core rule exactly:
    importance-based eviction (lowest first, first-minimal wins),
    crow_core.py:617-624. NOT oldest-timestamp."""

    def setUp(self):
        super().setUp()
        self._saved_cap = crow_core.VALUE_BANK_MAX

    def tearDown(self):
        crow_core.VALUE_BANK_MAX = self._saved_cap
        super().tearDown()

    def _bare_core(self):
        """A CrowMemory instance via __new__ (no __init__: no file lock, no
        encoder) with just the attributes _append_value_bank touches."""
        obj = crow_core.CrowMemory.__new__(crow_core.CrowMemory)
        obj._value_bank = []
        obj._faiss_vectors = {r: [] for r in crow_core.REGISTERS}
        obj._faiss_indexes = {}
        return obj

    def test_pruning_mirrors_core_rule(self):
        crow_core.VALUE_BANK_MAX = 5
        p = [entry(f"pk{i}", f"primary value {i}", importance=imp)
             for i, imp in enumerate([3.0, 1.0, 2.0, 4.0, 5.0])]
        # importance must exceed the eviction floor (1.0) so pk1 is evicted
        # instead of the new entry itself
        s = [entry("sk-new", "secondary value", importance=2.5)]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 5)  # capped
        keys = [m["key"] for m in merged]
        self.assertNotIn("pk1", keys)  # lowest importance (1.0) evicted
        self.assertIn("sk-new", keys)  # the new entry survives

        # Parity: run the REAL core method on the same overflow scenario
        core = self._bare_core()
        for e in p:
            core._value_bank.append(dict(e))
        vec = np.zeros(64, dtype=np.float32)
        core._append_value_bank("sk-new", "secondary value", vec,
                                "context", polarity=2.5)
        core_keys = [e["key"] for e in core._value_bank]
        self.assertEqual(sorted(core_keys), sorted(keys))

    def test_pruning_reports_pruned_entries(self):
        import io
        from contextlib import redirect_stdout
        crow_core.VALUE_BANK_MAX = 3
        p = [entry("pa", "va", importance=5.0),
             entry("pb", "vb", importance=4.0)]
        s = [entry("s1", "sv1", importance=0.1),
             entry("s2", "sv2", importance=0.2),
             entry("s3", "sv3", importance=0.3)]
        self.write_fixtures(p, s)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("EXCEEDED", out)
        self.assertIn("pruned 2", out)
        merged = read_bank(self.primary)
        self.assertEqual(len(merged), 3)
        # survivors: the 3 highest importances (5.0, 4.0, 0.3)
        keys = sorted(m["key"] for m in merged)
        self.assertEqual(keys, ["pa", "pb", "s3"])

    def test_within_cap_no_pruning(self):
        crow_core.VALUE_BANK_MAX = 10
        p = [entry("pk", "primary text")]
        s = [entry("sk", "secondary text")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(read_bank(self.primary)), 2)


class TestCoreSemanticsParity(MergeTestBase):
    """Metadata merge must match _append_value_bank re-ingest semantics.
    Verified by driving the REAL core method on a bare instance."""

    def _bare_core(self):
        obj = crow_core.CrowMemory.__new__(crow_core.CrowMemory)
        obj._value_bank = []
        obj._faiss_vectors = {r: [] for r in crow_core.REGISTERS}
        obj._faiss_indexes = {}
        return obj

    def test_metadata_merge_matches_core_reingest(self):
        p_entry = entry("dup", "shared value", register="style",
                        importance=1.5, ingest_count=2, timestamp=100.0,
                        project="projA")
        # secondary's importance IS the abs(polarity) its ingest contributed
        s_polarity = 0.8
        s_entry = entry("dup", "shared value", register="style",
                        importance=s_polarity, ingest_count=1,
                        timestamp=200.0, project="projB")

        # (a) OUR merge: plan + assemble
        plan = plan_merge([dict(p_entry)], [dict(s_entry)])
        self.assertEqual(plan["exact_dup"], 1)
        self.assertEqual(plan["uniques"], [])
        merged, _, pruned, _ = assemble(plan, self.fake, cap=500)
        self.assertEqual(pruned, [])
        m = merged[0]

        # (b) THE CORE: real _append_value_bank on the same base entry
        core = self._bare_core()
        core._value_bank.append(dict(p_entry))
        t0 = time.time()
        core._append_value_bank("dup", "shared value",
                                np.zeros(64, dtype=np.float32),
                                "style", polarity=s_polarity,
                                project="projB")
        c = core._value_bank[0]

        # Both accumulate identically (crow_core.py:595-597):
        self.assertAlmostEqual(c["importance"], m["importance"], places=5)
        self.assertEqual(c["ingest_count"], m["ingest_count"])
        # Both take the NEWEST timestamp (core: time.time() at re-ingest;
        # merge: max of the two stored timestamps — the faithful offline
        # equivalent, documented in the merge script docstring)
        self.assertGreaterEqual(c["timestamp"], t0)
        self.assertEqual(m["timestamp"], 200.0)
        # project is NEVER merged on re-ingest — primary wins
        self.assertEqual(c["project"], "projA")
        self.assertEqual(m["project"], "projA")
        # concrete core values
        self.assertAlmostEqual(c["importance"], 2.3, places=5)
        self.assertEqual(c["ingest_count"], 3)

    def test_core_creates_new_entry_when_no_dup(self):
        # sanity of the __new__ harness: no dup -> core appends
        core = self._bare_core()
        core._append_value_bank("k", "v", np.zeros(64, dtype=np.float32),
                                "context", polarity=1.2, project="pj")
        self.assertEqual(len(core._value_bank), 1)
        c = core._value_bank[0]
        self.assertAlmostEqual(c["importance"], 1.2, places=5)
        self.assertEqual(c["ingest_count"], 1)
        self.assertEqual(c["project"], "pj")
        self.assertIn("vector_b64", c)


class TestVectorReencode(MergeTestBase):

    def test_primary_scrubbed_entry_reencoded(self):
        p = [entry("pk", "text with >.< kaomoji ㅋㅋㅋ")]
        s = [entry("sk", "secondary clean")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        mp = next(m for m in merged if m["key"] == "pk")
        scrubbed = mv.scrub_text("text with >.< kaomoji ㅋㅋㅋ")
        self.assertEqual(mp["value"], scrubbed)
        expect = self.fake.encode(scrubbed)[:64]
        self.assertEqual(mp["vector_b64"],
                         crow_core.CrowMemory._encode_vector(expect))

    def test_clean_primary_vector_untouched(self):
        p = [entry("pk", "already clean text")]
        s = [entry("sk", "secondary clean")]
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        mp = next(m for m in merged if m["key"] == "pk")
        self.assertEqual(mp["vector_b64"], p[0]["vector_b64"])

    def test_odd_dim_vector_truncated_to_original_dim(self):
        p = [entry("pk", "text with >.< noise", dim=17)]
        s = []
        self.write_fixtures(p, s)
        rc = self.run_main("--apply", encode_fn=self.fake)
        self.assertEqual(rc, 0)
        merged = read_bank(self.primary)
        mp = merged[0]
        self.assertEqual(mp["value"], mv.scrub_text("text with >.< noise"))
        v = crow_core.CrowMemory._decode_vector(mp["vector_b64"])
        self.assertEqual(int(v.size), 17)  # original dim preserved


if __name__ == "__main__":
    unittest.main(verbosity=2)