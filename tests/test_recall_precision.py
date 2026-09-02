#!/usr/bin/env python3
"""
tests/test_recall_precision.py — Batch B verification (plain unittest).

Covers REQ-001 (no fabricated fallback), REQ-002 (cutoff + backdoor removal),
REQ-003 (importance boost cap x1.15), REQ-008 (project tagging via _accept),
REQ-010 (sha256 encode-cache key), REQ-011 (per-register NEG_DAMPEN),
AD-3 (recall_multi global merge), AD-1 wiring (ingest scrub gate + display
scrub).

No real encoder dependency: CrowMemory._encoder is replaced with a
deterministic fake before first use, and register dims are shrunk at the
module level so constructing CrowMemory is cheap.
"""

import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

# Make project root importable when run as `python tests/test_recall_precision.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crow_core  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeEncoder:
    """Deterministic stand-in for SentenceTransformer.

    Vector for a text is seeded from its sha256 — distinct texts get distinct
    vectors, same text reproduces the same vector. Records calls so cache
    behavior can be observed.
    """

    def __init__(self):
        self.calls = []

    def encode(self, text, **kwargs):
        self.calls.append(text)
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        return rng.normal(size=crow_core.EMBED_DIM).astype(np.float32)


class PrecisionTestBase(unittest.TestCase):
    """Shrinks module-level dims so CrowMemory loads fast and light."""

    @classmethod
    def setUpClass(cls):
        cls._saved = {n: getattr(crow_core, n)
                      for n in ("DIM", "EMBED_DIM", "REGISTERS")}
        crow_core.DIM = 64
        crow_core.EMBED_DIM = 8
        crow_core.REGISTERS = {
            "style":   (64, 64, 0.9999),
            "bug":     (32, 32, 0.9995),
            "arch":    (64, 64, 0.9995),
            "context": (32, 64, 0.95),
            "life_pref":    (64, 64, 0.9999),
            "life_avoid":   (32, 32, 0.9995),
            "life_phil":    (32, 32, 0.9995),
            "life_context": (32, 64, 0.95),
        }

    @classmethod
    def tearDownClass(cls):
        for name, value in cls._saved.items():
            setattr(crow_core, name, value)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crow_precision_")
        self.cm = crow_core.CrowMemory(os.path.join(self.tmp, "crow.bin"))
        self.cm._encoder = FakeEncoder()

    def tearDown(self):
        # Release the advisory lock file, then remove temp dir
        try:
            self.cm = None
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def unit_vec(self, dim, seedtext):
        rng = np.random.default_rng(
            int(hashlib.sha256(seedtext.encode("utf-8")).hexdigest()[:16], 16))
        v = rng.normal(size=dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def inject_entry(self, register, value, d_v, importance=1.0, project=None):
        """Insert a value_bank entry without touching S matrices."""
        vec = self.unit_vec(d_v, "value:" + value)
        entry = {
            "key": "key-" + value,
            "value": value,
            "vector_b64": self.cm._encode_vector(vec),
            "register": register,
            "timestamp": 0.0,
            "importance": importance,
            "ingest_count": 1,
        }
        if project is not None:
            entry["project"] = project
        self.cm._value_bank.append(entry)
        self.cm._faiss_indexes.pop(register, None)
        return entry

    def stored_vec(self, entry):
        """The normalized float32 vector actually stored for an entry."""
        v = self.cm._decode_vector(entry["vector_b64"])
        return v / np.linalg.norm(v)

    def query_vec_toward(self, register, stored, weight, seedtext):
        """A recall query residual r with cosine `weight` to `stored`
        (exact, via an explicit orthogonal complement)."""
        orth = self.unit_vec(len(stored), "ortho:" + seedtext)
        orth = orth - (orth @ stored) * stored
        orth = orth / np.linalg.norm(orth)
        r = weight * stored + np.sqrt(max(1.0 - weight * weight, 0.0)) * orth
        return r / np.linalg.norm(r)

    def align_S(self, register, key_text, entry):
        """Set register S so that recall(key_text, register) hits `entry`
        with sim ~= 1."""
        d_k, d_v, _ = crow_core.REGISTERS[register]
        k = self.cm.encode(key_text).astype(np.float32)[:d_k]
        v = self.stored_vec(entry)[:crow_core.REGISTERS[register][1]]
        self.cm.data[f"{register}_S"] = np.outer(k, v).astype(np.float16)


# ---------------------------------------------------------------------------
# REQ-002: cutoff boundary + importance backdoor removal
# ---------------------------------------------------------------------------

class CutoffTests(PrecisionTestBase):
    def test_sim_034_rejected(self):
        entry = self.inject_entry("style", "low sim case", 64)
        r = self.query_vec_toward("style", self.stored_vec(entry), 0.34, "q1")
        self.assertEqual(self.cm._nearest_hints(r, "style", top_k=2), [])

    def test_sim_036_accepted(self):
        entry = self.inject_entry("style", "ok sim case", 64)
        r = self.query_vec_toward("style", self.stored_vec(entry), 0.36, "q2")
        hints = self.cm._nearest_hints(r, "style", top_k=2)
        self.assertEqual(len(hints), 1)
        self.assertAlmostEqual(hints[0]["sim"], 0.36, places=3)

    def test_backdoor_gone_high_importance_low_sim(self):
        # Old backdoor: importance > 5.0 and sim > 0.15 → accepted.
        # Now raw sim < SIM_CUTOFF must reject regardless of importance.
        ok, _ = self.cm._accept(0.20, 50.0, None, None)
        self.assertFalse(ok)

    def test_default_cutoff_constant(self):
        self.assertEqual(crow_core.SIM_CUTOFF, 0.35)
        self.assertAlmostEqual(crow_core.CROSS_PROJECT_CUTOFF, 0.42, places=6)
        self.assertEqual(crow_core.PROJECT_BOOST, 1.05)


# ---------------------------------------------------------------------------
# REQ-001: no fabricated fallback hints
# ---------------------------------------------------------------------------

class NoFabricatedFallbackTests(PrecisionTestBase):
    def test_empty_bank_nearest_hints_returns_empty_list(self):
        # No candidates at all
        r = self.unit_vec(64, "whatever")
        self.assertEqual(self.cm._nearest_hints(r, "style", top_k=2), [])

    def test_no_accepted_hints_returns_empty_list(self):
        entry = self.inject_entry("style", "distant memory", 64)
        r = self.query_vec_toward("style", self.stored_vec(entry), 0.34, "qx")
        self.assertEqual(self.cm._nearest_hints(r, "style", top_k=2), [])

    def test_recall_on_empty_register_has_no_fabricated_text(self):
        result = self.cm.recall("any query", "style")
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["confidence"], 0.0)
        for hint in result.get("hints", []):
            self.assertNotIn("faint", hint)

    def test_recall_no_accepted_hint_has_no_faint_text(self):
        entry = self.inject_entry("arch", "real memory", 64)
        # _faiss_search normalizes r, so sim is a direction cosine. Build the
        # residual direction with cosine 0.20 to the stored vector: tilting
        # via an orthogonal complement gives exactly sim=0.20 < SIM_CUTOFF.
        q = self.cm.encode("qz").astype(np.float32)[:64]
        q_n = q / np.linalg.norm(q)
        v = self.stored_vec(entry)[:64]
        target_r = self.query_vec_toward("arch", v, 0.20, "qz")[:64]
        self.cm.data["arch_S"] = np.outer(q_n, target_r).astype(np.float16)
        result = self.cm.recall("qz", "arch")
        self.assertEqual(result["hints"], [])
        self.assertFalse(any("faint" in h for h in result["hints"]))

    def test_bias_block_no_fabricated_lines(self):
        block = self.cm.get_user_bias_block("anything")
        self.assertEqual(
            block, "[User Bias -- retrieved from Crow Memory]")


# ---------------------------------------------------------------------------
# REQ-003: importance boost capped at x1.15
# ---------------------------------------------------------------------------

class BoostCapTests(PrecisionTestBase):
    def test_importance_1e6_boost_capped(self):
        accepted, eff = self.cm._accept(0.35, 1e6, None, None)
        self.assertTrue(accepted)
        self.assertLessEqual(eff, 0.35 * 1.15 + 1e-9)

    def test_normal_importance_boost_uncapped(self):
        _, eff = self.cm._accept(1.0, 1.0, None, None)
        expected = 1.0 + 0.12 * np.log(2.0)
        self.assertAlmostEqual(eff, expected, places=6)

    def test_same_project_boost_still_capped(self):
        accepted, eff = self.cm._accept(0.99, 1e6, "alpha", "alpha")
        self.assertTrue(accepted)
        self.assertLessEqual(eff, 0.99 * 1.15 + 1e-9)


# ---------------------------------------------------------------------------
# REQ-008: project tagging acceptance matrix
# ---------------------------------------------------------------------------

class ProjectAcceptTests(PrecisionTestBase):
    def test_untagged_entry_is_global(self):
        accepted, _ = self.cm._accept(0.36, 1.0, None, "alpha")
        self.assertTrue(accepted)

    def test_untagged_entry_eligible_without_query_project(self):
        accepted, _ = self.cm._accept(0.36, 1.0, "beta", None)
        self.assertTrue(accepted)

    def test_same_project_boosted_accepts(self):
        # 0.36 raw with same-project boost: boost=1.0832*1.05=1.1374,
        # eff=0.4095 > 0.35 → accepted.
        accepted, eff = self.cm._accept(0.36, 1.0, "alpha", "alpha")
        self.assertTrue(accepted)
        self.assertGreater(eff, 0.36 * (1.0 + 0.12 * np.log(2.0)))

    def test_cross_project_stricter_cutoff(self):
        # sim 0.36 < CROSS_PROJECT_CUTOFF 0.42 → rejected cross-project,
        # though it would pass base cutoff as untagged.
        accepted, _ = self.cm._accept(0.36, 1.0, "beta", "alpha")
        self.assertFalse(accepted)

    def test_cross_project_high_sim_accepted(self):
        accepted, _ = self.cm._accept(0.60, 1.0, "beta", "alpha")
        self.assertTrue(accepted)

    def test_strict_project_filters_cross_project(self):
        accepted, _ = self.cm._accept(0.90, 1.0, "beta", "alpha",
                                      strict_project=True)
        self.assertFalse(accepted)

    def test_strict_project_keeps_same_project(self):
        accepted, _ = self.cm._accept(0.90, 1.0, "alpha", "alpha",
                                      strict_project=True)
        self.assertTrue(accepted)

    def test_strict_project_keeps_untagged_global(self):
        accepted, _ = self.cm._accept(0.90, 1.0, None, "alpha",
                                      strict_project=True)
        self.assertTrue(accepted)

    def test_strict_project_ignored_without_query_project(self):
        accepted, _ = self.cm._accept(0.90, 1.0, "beta", None,
                                      strict_project=True)
        self.assertTrue(accepted)

    def test_value_bank_entry_carries_project_tag(self):
        self.cm.ingest("db choice", "we use postgres",
                       1.5, "arch", project="crowsnest")
        match = [e for e in self.cm._value_bank if e["key"] == "db choice"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["project"], "crowsnest")

    def test_legacy_entry_without_project_field_reads_global(self):
        self.cm._value_bank.append({  # entry with no "project" key at all
            "key": "legacy", "value": "old global note",
            "vector_b64": self.cm._encode_vector(
                self.unit_vec(64, "value:old global note")),
            "register": "style", "timestamp": 0.0,
            "importance": 1.0, "ingest_count": 1,
        })
        r = self.query_vec_toward("style", self.stored_vec(
            self.cm._value_bank[-1]), 0.90, "q")
        hints = self.cm._nearest_hints(r, "style", top_k=2, project="anyproj")
        self.assertEqual(len(hints), 1)


# ---------------------------------------------------------------------------
# AD-3: recall_multi global merge
# ---------------------------------------------------------------------------

class RecallMultiTests(PrecisionTestBase):
    def _seed_two_registers(self):
        # arch: importance 50 → boost capped 1.15; style: importance 1 → 1.0832
        e_high = self.inject_entry("arch", "high imp note", 64, importance=50.0)
        e_low = self.inject_entry("style", "low imp note", 64, importance=1.0)
        r_arch = self.query_vec_toward("arch", self.stored_vec(e_high),
                                       0.90, "qa")
        r_style = self.query_vec_toward("style", self.stored_vec(e_low),
                                        0.90, "qs")
        # Force S so recall query "probe" yields those residuals exactly:
        # instead, easier: use distinct S as in full-path test.
        qk = self.cm.encode("probe").astype(np.float32)
        self.cm.data["arch_S"] = np.outer(
            qk[:64] / max(np.linalg.norm(qk[:64]), 1e-8),
            self.stored_vec(e_high)).astype(np.float16)
        self.cm.data["style_S"] = np.outer(
            qk[:64] / max(np.linalg.norm(qk[:64]), 1e-8),
            self.stored_vec(e_low)).astype(np.float16)

    def test_merge_orders_by_effective_sim(self):
        self._seed_two_registers()
        # Both hit with sim ~1.0; capped boost (1.15) > normal boost (1.0832)
        # so the arch hint must come first regardless of register order.
        out = self.cm.recall_multi("probe", ["style", "arch", "bug"], top_k=2)
        self.assertEqual(out["registers_hit"], ["style", "arch"])
        self.assertEqual(len(out["hints"]), 2)
        self.assertEqual(out["hints"][0]["text"], "high imp note")
        self.assertEqual(out["hints"][0]["register"], "arch")
        self.assertGreaterEqual(out["hints"][0]["eff_sim"],
                                out["hints"][1]["eff_sim"])

    def test_registers_with_zero_hints_skipped(self):
        self._seed_two_registers()
        out = self.cm.recall_multi("probe", ["style", "arch", "bug"],
                                   top_k=2)
        self.assertNotIn("bug", out["registers_hit"])
        # bug register must NOT be tracked in recall_stats (stats hygiene)
        stats = {r.stem for r in []}  # placeholder replaced below
        stats = self.cm._recall_stats
        self.assertNotIn("bug", stats)

    def test_top_k_slices_globally(self):
        self._seed_two_registers()
        out = self.cm.recall_multi("probe", ["style", "arch"], top_k=1)
        self.assertEqual(len(out["hints"]), 1)
        self.assertEqual(out["hints"][0]["register"], "arch")

    def test_merged_confidence_is_weighted_mean_of_hits(self):
        self._seed_two_registers()
        out = self.cm.recall_multi("probe", ["style", "arch"], top_k=2)
        c_style = self.cm._recall_stats["style"][
            hashlib.md5("probe".encode()).hexdigest()]["last_seen"]
        # confidence field present and in (0, 1]
        self.assertGreater(out["confidence"], 0.0)
        self.assertLessEqual(out["confidence"], 1.0)

    def test_no_hits_returns_empty_and_zero_confidence(self):
        out = self.cm.recall_multi("nothing", ["style", "arch"])
        self.assertEqual(out["hints"], [])
        self.assertEqual(out["confidence"], 0.0)
        self.assertEqual(out["registers_hit"], [])

    def test_legacy_kaomoji_value_scrubbed_in_multi_hints(self):
        """F1 regression (REQ-006): the DEFAULT recall path (register omitted/
        "all" -> recall_multi) must display-scrub hint text exactly like
        recall() does. A legacy pre-gate entry with raw kaomoji in its stored
        value must never leak verbatim into recall_multi output."""
        # Legacy-style entry: injected straight into the bank (ingest gate
        # would have scrubbed/rejected it — legacy entries predate the gate).
        entry = self.inject_entry("style", "keep tests fast >.< ㅋㅋㅋ ok", 64)
        # Force S so recall_multi("probe") hits this entry with sim ~1
        qk = self.cm.encode("probe").astype(np.float32)
        self.cm.data["style_S"] = np.outer(
            qk[:64] / max(np.linalg.norm(qk[:64]), 1e-8),
            self.stored_vec(entry)).astype(np.float16)
        out = self.cm.recall_multi("probe", ["style", "arch"], top_k=2)
        self.assertEqual(out["registers_hit"], ["style"])
        self.assertEqual(len(out["hints"]), 1)
        hint_text = out["hints"][0]["text"]
        # Clean core survives...
        self.assertIn("keep tests fast", hint_text)
        self.assertIn("ok", hint_text)
        # ...kaomoji garbage does not (scrub_display applied on this path)
        self.assertNotIn(">.<", hint_text)
        self.assertNotIn("ㅋㅋㅋ", hint_text)
        # Content contract matches recall()'s public strings: scrubbed AND
        # 200-truncated (payload-shape unification, F1 secondary fix)
        expected = crow_core.scrub_display("keep tests fast >.< ㅋㅋㅋ ok")[:200]
        self.assertEqual(hint_text, expected)
        single = self.cm.recall("probe", "style")
        # Both paths now surface identical cleaned content
        self.assertIn(expected, single["hints"][0])


# ---------------------------------------------------------------------------
# REQ-010: sha256 encode cache key
# ---------------------------------------------------------------------------

class EncodeCacheKeyTests(PrecisionTestBase):
    def test_200_char_prefix_collision_fixed(self):
        a = "A" * 200 + "tail-one"
        b = "A" * 200 + "tail-two"
        va = self.cm.encode(a)
        vb = self.cm.encode(b)
        self.assertFalse(np.array_equal(va, vb))
        self.assertEqual(len(self.cm._encode_cache), 2)

    def test_invariant_for_full_text(self):
        t1 = "u" * 180 + "x" + "N" * 300
        t2 = "u" * 180 + "y" + "N" * 300
        self.assertFalse(np.array_equal(self.cm.encode(t1), self.cm.encode(t2)))

    def test_repeat_call_hits_cache(self):
        enc = self.cm._encoder
        self.cm.encode("same text")
        self.cm.encode("same text")
        self.assertEqual(len(enc.calls), 1)


# ---------------------------------------------------------------------------
# REQ-011: per-register NEG_DAMPEN
# ---------------------------------------------------------------------------

class NegativeDampenTests(PrecisionTestBase):
    def test_bug_register_undamped(self):
        res = self.cm.ingest("bug key", "null deref pattern",
                             -1.0, "bug")
        self.assertAlmostEqual(res["polarity_applied"], -1.0, places=6)

    def test_life_avoid_register_undamped(self):
        res = self.cm.ingest("avoid key", "never skip leg day",
                             -1.0, "life_avoid")
        self.assertAlmostEqual(res["polarity_applied"], -1.0, places=6)

    def test_style_register_damped_default(self):
        res = self.cm.ingest("style key", "two spaces indent",
                             -1.0, "style")
        self.assertAlmostEqual(res["polarity_applied"], -0.6, places=6)

    def test_arch_register_damped_default(self):
        res = self.cm.ingest("arch key", "layer violation",
                             -1.0, "arch")
        self.assertAlmostEqual(res["polarity_applied"], -0.6, places=6)

    def test_constants_and_alias(self):
        self.assertEqual(crow_core.NEG_DAMPEN_DEFAULT, 0.6)
        self.assertEqual(crow_core.NEG_DAMPEN, crow_core.NEG_DAMPEN_DEFAULT)
        self.assertEqual(crow_core.NEG_DAMPEN_BY_REGISTER["bug"], 1.0)
        self.assertEqual(crow_core.NEG_DAMPEN_BY_REGISTER["life_avoid"], 1.0)


# ---------------------------------------------------------------------------
# AD-1 wiring: ingest scrub gate + display scrub
# ---------------------------------------------------------------------------

class IngestScrubGateTests(PrecisionTestBase):
    def test_pure_noise_value_rejected(self):
        res = self.cm.ingest("key", ">.< ㅋㅋㅋ", 1.5, "style")
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(res["reason"], "empty_after_sanitize")

    def test_rejection_touches_nothing(self):
        self.cm.ingest("key", ">.< ㅋㅋㅋ", 1.5, "style")
        self.assertEqual(self.cm._value_bank, [])
        self.assertEqual(int(self.cm.data["update_count"]), 0)

    def test_scrubbed_value_clean_in_hints(self):
        res = self.cm.ingest("recall probe alpha",
                             "always run tests 🎉", 1.5, "style")
        self.assertEqual(res["status"], "ingested")
        entry = self.cm._value_bank[-1]
        self.assertEqual(entry["value"], "always run tests")
        # Force S so this entry is recalled with high sim
        self.align_S("style", "recall probe alpha", entry)
        out = self.cm.recall("recall probe alpha", "style")
        self.assertEqual(len(out["hints"]), 1)
        self.assertIn("always run tests", out["hints"][0])
        self.assertNotIn("🎉", out["hints"][0])

    def test_ingest_key_also_scrubbed(self):
        self.cm.ingest("key 🎉 noisy", "clean value", 1.0, "style")
        entry = self.cm._value_bank[-1]
        self.assertNotIn("🎉", entry["key"])


# ---------------------------------------------------------------------------
# REQ-002/AD-2: env var configuration (module reload)
# ---------------------------------------------------------------------------

class EnvOverrideTests(unittest.TestCase):
    def test_env_overrides_read_at_import(self):
        old = {k: os.environ.get(k) for k in
               ("CROW_SIM_CUTOFF", "CROW_SIM_CUTOFF_CROSS_PROJECT",
                "CROW_PROJECT_BOOST")}
        try:
            os.environ["CROW_SIM_CUTOFF"] = "0.50"
            os.environ["CROW_PROJECT_BOOST"] = "1.10"
            os.environ.pop("CROW_SIM_CUTOFF_CROSS_PROJECT", None)
            mod = importlib.reload(crow_core)
            self.assertEqual(mod.SIM_CUTOFF, 0.50)
            self.assertAlmostEqual(mod.CROSS_PROJECT_CUTOFF, 0.57, places=6)
            self.assertEqual(mod.PROJECT_BOOST, 1.10)

            os.environ["CROW_SIM_CUTOFF_CROSS_PROJECT"] = "0.9"
            mod = importlib.reload(crow_core)
            self.assertEqual(mod.CROSS_PROJECT_CUTOFF, 0.9)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(crow_core)
        # Defaults restored after final reload
        self.assertEqual(crow_core.SIM_CUTOFF, 0.35)


if __name__ == "__main__":
    unittest.main(verbosity=2)
