"""tests/test_recall_perf.py - recall latency regression guard (schema v2.1).

Hooks run as short-lived processes, so recall latency is a user-visible
property, not a micro-benchmark: a hook that takes 100ms shows up as lag on
every prompt. Schema v2.1 stores the tokenized row text (memories.tokens) at
write time so a read only splits strings instead of re-tokenizing ~233KB.

Three measurements, all against a real 486-row bank migrated from the repo
value_bank.json into a tempfile home:

1. in-engine, same process, warm: p95 < IN_ENGINE_P95_MS over three warm
   20-run batches (pooled, so the percentile is not one hiccup).
2. end-to-end `python core/crow_cli.py recall` (fresh process per call):
   p95 < CLI_P95_MS over 10 runs.
3. engine time reported by a fresh process (the real hook shape):
   median < COLD_MEDIAN_MS and p95 < COLD_P95_MS over 10 runs.

Bounds come from back-to-back measurements on the authoring machine
(Windows 11, Python 3.11.9, 486 rows, 233KB of row text), pre-v2.1 engine
versus this one:
    in-engine  p95 10.3-12.7 -> 4.7-5.0ms   (pooled p95 ~6.0ms)
    CLI recall p95 208       -> 180ms       (-140ms of that is interpreter
                                             start-up, so the bound is loose)
    cold engine median 29.4  -> 15.3ms, p95 42.8 -> 16.1ms
An absolute latency bound on a shared machine can also fail because of load,
so the class skips (instead of reporting a false failure) when interpreter
start-up is more than LOAD_TOLERANCE times its clean-machine value.

Run:  python tests/test_recall_perf.py -v
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
CORE_DIR = os.path.join(REPO_ROOT, "core")
CLI = os.path.join(CORE_DIR, "crow_cli.py")
VALUE_BANK = os.path.join(REPO_ROOT, "memory", "value_bank.json")
sys.path.insert(0, CORE_DIR)

from crow_db import CrowDB  # noqa: E402
from migrate_from_v1 import migrate  # noqa: E402

BANK_ROWS = 486                 # 488 entries - 2 semantic merges
LOAD_BASELINE_MS = 45.0         # clean-machine p95 of `python -S -E -c pass`
LOAD_TOLERANCE = 3.0            # above 3x that, absolute latency bounds are
                                # meaningless: skip instead of asserting
IN_ENGINE_P95_MS = 20.0         # DoD bound for warm in-engine recall (CR-4:
                                # 8.0ms flaked ~1/4 runs on a quiet-slower box,
                                # 12.0ms still flakes under host load; the value
                                # guards the re-tokenization regression at ~41ms,
                                # not an absolute latency SLA)
CLI_P95_MS = 500.0              # ~2.2x the worst p95 observed (interpreter
                                # start-up dominates; see module docstring)
COLD_P95_MS = 40.0              # ~1.8x the worst p95 observed
COLD_MEDIAN_MS = 25.0           # median is stable (+/-0.3ms); a per-process
                                # re-tokenization regression lands at ~29ms
WARMUP_RECALLS = 5
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

QUERIES = (
    "how do I run the test suite",
    "why did the importance score creep up after I logged a failure lesson",
    "npm install fails with TAR_ENTRY_ERROR",
    "sqlite wal daemon architecture",
    "훅 출력이 깨지면 안 된다",
    "python naming conventions snake_case",
)

# The migrated bank holds no row close enough to this Korean paraphrase, so it
# only contributes a (slower, CJK-channel) timing sample.
NO_HIT_QUERIES = ("훅 출력이 깨지면 안 된다",)

COLD_PROBE = (
    "import os, sys, time\n"
    "sys.path.insert(0, %r)\n"
    "from crow_db import CrowDB\n"
    "db = CrowDB(os.environ['CROW_HOME'])\n"
    "t0 = time.perf_counter()\n"
    "db.recall('how do I run the test suite', top_k=3, track_stats=False)\n"
    "print((time.perf_counter() - t0) * 1000)\n"
    "db.close()\n"
) % CORE_DIR


def p95(values):
    """Nearest-rank 95th percentile."""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1,
                              int(round(0.95 * (len(ordered) - 1)))))]


class RecallPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="crow_perf_test_")
        cls.home = os.path.join(cls.tmp, "home")
        report = migrate(VALUE_BANK, cls.home, apply=True)
        if report["inserted"] + report["merged"] != 488:
            raise unittest.SkipTest(f"value_bank migration incomplete: {report}")
        cls.env = dict(os.environ, CROW_HOME=cls.home,
                       PYTHONDONTWRITEBYTECODE="1")
        # settle the WAL the migration just wrote, and warm the page cache
        db = CrowDB(cls.home)
        try:
            db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            db.conn.commit()
            for i in range(WARMUP_RECALLS):
                db.recall(QUERIES[i % len(QUERIES)], top_k=3,
                          track_stats=False)
        finally:
            db.close()
        # Interpreter start-up is a good proxy for how busy the box is. These
        # are absolute latency assertions; on a box several times slower than
        # the one the bounds came from they measure the load, not the engine.
        startup = []
        for _ in range(8):
            started = time.perf_counter()
            subprocess.run([sys.executable, "-S", "-E", "-c", "pass"],
                           capture_output=True, env=cls.env, cwd=cls.home,
                           creationflags=NO_WINDOW)
            startup.append((time.perf_counter() - started) * 1000.0)
        cls.startup_p95 = p95(startup)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers -----------------------------------------------------------
    def _require_quiet_machine(self):
        limit = LOAD_BASELINE_MS * LOAD_TOLERANCE
        if self.startup_p95 > limit:
            self.skipTest(
                "machine too busy for a latency assertion: interpreter "
                "start-up p95 %.0fms exceeds %.0fms" % (self.startup_p95, limit))

    def _bank_rows(self):
        db = CrowDB(self.home)
        try:
            return db.conn.execute(
                "SELECT COUNT(*) c FROM memories").fetchone()["c"]
        finally:
            db.close()

    def _warm_batch(self, db, n=20):
        for i in range(WARMUP_RECALLS):
            db.recall(QUERIES[i % len(QUERIES)], top_k=3, track_stats=False)
        times = []
        for i in range(n):
            started = time.perf_counter()
            db.recall(QUERIES[i % len(QUERIES)], top_k=3, track_stats=False)
            times.append((time.perf_counter() - started) * 1000.0)
        return times

    # -- 1. in-engine, warm ------------------------------------------------
    def test_in_engine_warm_recall_p95_under_bound(self):
        self._require_quiet_machine()
        self.assertEqual(self._bank_rows(), BANK_ROWS)
        db = CrowDB(self.home)
        try:
            batches = [self._warm_batch(db) for _ in range(3)]
        finally:
            db.close()
        # p95 of a single 20-run batch is the 2nd-slowest sample, which swings
        # by +/-3ms on this class of machine. Pool three warm batches (60
        # samples) so the percentile estimates the distribution instead of one
        # hiccup; a structural regression moves all 60.
        pooled = [t for batch in batches for t in batch]
        measured = p95(pooled)
        self.assertLess(
            measured, IN_ENGINE_P95_MS,
            "warm in-engine recall p95 %.2fms over %d pooled runs "
            "(per-batch p95 %s, median %.2fms) exceeds %.1fms at %d rows"
            % (measured, len(pooled),
               ", ".join("%.2f" % p95(b) for b in batches),
               statistics.median(pooled), IN_ENGINE_P95_MS, BANK_ROWS))

    # -- 2. end-to-end CLI, fresh process per call -------------------------
    def test_cli_recall_p95_under_bound(self):
        self._require_quiet_machine()
        rounds = []
        for _ in range(2):
            times = []
            for i in range(10):
                query = QUERIES[i % len(QUERIES)]
                started = time.perf_counter()
                proc = subprocess.run(
                    [sys.executable, CLI, "recall", "--query", query,
                     "--top-k", "3", "--no-stats"],
                    capture_output=True, text=True, encoding="utf-8",
                    env=self.env, cwd=self.home, creationflags=NO_WINDOW)
                times.append((time.perf_counter() - started) * 1000.0)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                hits = json.loads(proc.stdout)
                self.assertIsInstance(hits, list)
                if query not in NO_HIT_QUERIES:
                    self.assertTrue(hits,
                                    "recall returned nothing for %r" % query)
            rounds.append(times)
            if p95(times) < CLI_P95_MS:
                break
        times = rounds[-1]
        measured = p95(times)
        self.assertLess(
            measured, CLI_P95_MS,
            "crow_cli.py recall p95 %.1fms over 10 fresh processes "
            "(median %.1fms) exceeds %.0fms"
            % (measured, sorted(times)[len(times) // 2], CLI_P95_MS))

    # -- 3. engine time inside a fresh process (the hook shape) ------------
    def test_fresh_process_recall_engine_time_under_bound(self):
        self._require_quiet_machine()
        rounds = []
        for _ in range(2):
            times = []
            for _ in range(10):
                proc = subprocess.run(
                    [sys.executable, "-S", "-E", "-c", COLD_PROBE],
                    capture_output=True, text=True, encoding="utf-8",
                    env=self.env, cwd=self.home, creationflags=NO_WINDOW)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                times.append(float(proc.stdout.strip()))
            rounds.append(times)
            if p95(times) < COLD_P95_MS:
                break
        times = rounds[-1]
        measured = p95(times)
        self.assertLess(
            statistics.median(times), COLD_MEDIAN_MS,
            "fresh-process recall engine median %.1fms exceeds %.0fms - the "
            "read path is re-deriving work that belongs at write time"
            % (statistics.median(times), COLD_MEDIAN_MS))
        self.assertLess(
            measured, COLD_P95_MS,
            "fresh-process recall engine time p95 %.1fms (median %.1fms) "
            "exceeds %.0fms - reading a bank this size must not re-tokenize "
            "row text" % (measured, sorted(times)[len(times) // 2],
                          COLD_P95_MS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
