#!/usr/bin/env python3
"""
tests/test_tool_schema.py — Batch C verification (plain unittest).

Covers AD-5 (tool consolidation 10 → 3), REQ-004 wiring (recall_multi in
_recall and REST), AD-8.2 (CROW_STATE_TAG state path resolution), and the
i18n schema mirror (crow_i18n.get_tool_definitions + en/ko.json keys).

No real encoder dependency: reuses the FakeEncoder pattern from
tests/test_recall_precision.py so CrowMemory constructs cheaply.
"""

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

import numpy as np

# Make project root importable when run as `python tests/test_tool_schema.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crow_core  # noqa: E402
import crow_mcp_server as cms  # noqa: E402
import crow_i18n  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (FakeEncoder pattern from tests/test_recall_precision.py)
# ---------------------------------------------------------------------------

class FakeEncoder:
    """Deterministic encoder seeded from the text's sha256."""

    def __init__(self):
        self.calls = []

    def encode(self, text, **kwargs):
        self.calls.append(text)
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        return rng.normal(size=crow_core.EMBED_DIM).astype(np.float32)


class SchemaTestBase(unittest.TestCase):
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
        self.tmp = tempfile.mkdtemp(prefix="crow_schema_")
        self.cm = crow_core.CrowMemory(os.path.join(self.tmp, "crow.bin"))
        self.cm._encoder = FakeEncoder()

    def tearDown(self):
        self.cm = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers (adapted from tests/test_recall_precision.py) -------------

    def align_S(self, register, key_text, entry):
        """Set register S so recall(key_text, register) hits `entry`
        with sim ~= 1."""
        d_k, d_v, _ = crow_core.REGISTERS[register]
        k = self.cm.encode(key_text).astype(np.float32)[:d_k]
        v = self.cm._decode_vector(entry["vector_b64"])[:d_v]
        v = v / np.linalg.norm(v)
        self.cm.data[f"{register}_S"] = np.outer(k, v).astype(np.float16)

    def ingest_hit(self, key, value, register):
        """Ingest and align S so `key` recalls `value` with sim ~= 1."""
        self.cm.ingest(key, value, 1.5, register)
        entry = self.cm._value_bank[-1]
        self.align_S(register, key, entry)
        return entry


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tool registration (exactly 3 tools)
# ---------------------------------------------------------------------------

class ToolRegistrationTests(SchemaTestBase):

    def setUp(self):
        super().setUp()
        # Fresh directory: the live crow.bin PID lock forbids two
        # CrowMemory instances on the same path in one process.
        server_dir = os.path.join(self.tmp, "server")
        os.makedirs(server_dir, exist_ok=True)
        self.server, self.server_crow = cms.create_server(
            os.path.join(server_dir, "crow.bin"))
        tools = _run(self.server.list_tools())
        self.tool_names = {t.name for t in tools}

    def test_exactly_three_tools(self):
        self.assertEqual(len(self.tool_names), 3, self.tool_names)

    def test_tool_names_match_ad5(self):
        self.assertEqual(self.tool_names,
                         {"crow_recall", "crow_ingest", "crow_admin"})

    def test_old_tool_names_gone(self):
        old = {"crow_evolve_propose", "crow_diagnostics", "crow_check_drift",
               "crow_ingest_from_build", "crow_get_user_bias",
               "crow_manage_prompt", "crow_manage_backup", "crow_project_info"}
        self.assertEqual(self.tool_names & old, set())


# ---------------------------------------------------------------------------
# crow_recall behavior
# ---------------------------------------------------------------------------

class CrowRecallTests(SchemaTestBase):

    def test_single_register_path(self):
        self.ingest_hit("naming preference",
                        "Prefers PascalCase for all class names.", "style")
        res = json.loads(cms._recall(self.cm, {
            "query": "naming preference",
            "register": "style",
            "top_k": 2,
        })[0]["text"])
        self.assertIn("hints", res)
        self.assertEqual(res.get("register"), "style")
        self.assertTrue(any("PascalCase" in h for h in res["hints"]))

    def test_domain_all_multi_path_uses_recall_multi(self):
        self.ingest_hit("sql preference",
                        "Always uses parameterized SQL queries.", "style")
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            res = json.loads(cms._recall(self.cm, {
                "query": "sql preference",
                "domain": "all",
                "top_k": 2,
            })[0]["text"])
        spy.assert_called_once()
        self.assertIn("hints", res)
        self.assertIn("registers_hit", res)
        self.assertIn("confidence", res)
        self.assertTrue(any("SQL" in h.get("text", "") for h in res["hints"]))
        self.assertIn("style", res["registers_hit"])

    def test_register_all_maps_to_multi(self):
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            json.loads(cms._recall(self.cm, {
                "query": "anything", "register": "all",
            })[0]["text"])
        spy.assert_called_once()

    def test_single_register_does_not_use_multi(self):
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            json.loads(cms._recall(self.cm, {
                "query": "anything", "register": "style",
            })[0]["text"])
        spy.assert_not_called()

    def test_domain_code_scopes_registers(self):
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            json.loads(cms._recall(self.cm, {
                "query": "anything", "domain": "code",
            })[0]["text"])
        args, _ = spy.call_args
        self.assertEqual(args[1], crow_core.DOMAINS["code"])

    def test_project_params_forwarded(self):
        self.ingest_hit("gamma marker", "unique marker text gamma", "arch")
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            json.loads(cms._recall(self.cm, {
                "query": "gamma marker",
                "project": "p1", "strict_project": True,
            })[0]["text"])
        kwargs = spy.call_args[1]
        self.assertEqual(kwargs.get("project"), "p1")
        self.assertTrue(kwargs.get("strict_project"))

    def test_bias_block_format(self):
        self.ingest_hit("indentation",
                        "Prefers 2-space indentation everywhere.", "style")
        out = cms._recall(self.cm, {"query": "indentation",
                                    "format": "bias_block"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["type"], "text")
        self.assertIn("[User Bias", out[0]["text"])
        self.assertIn("2-space indentation", out[0]["text"])

    def test_top_k_clamped(self):
        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            json.loads(cms._recall(self.cm, {
                "query": "x", "top_k": 99,
            })[0]["text"])
        self.assertEqual(spy.call_args[0][2], 5)


# ---------------------------------------------------------------------------
# crow_ingest behavior
# ---------------------------------------------------------------------------

class CrowIngestTests(SchemaTestBase):

    def test_explicit_polarity(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "testing explicit polarity",
            "value": "Deterministic explicit-path marker alpha.",
            "register": "arch",
            "polarity": 2.0,
        })[0]["text"])
        self.assertEqual(res["status"], "ingested")
        self.assertEqual(res["polarity_applied"], 2.0)

    def test_exit_code_zero_defaults(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "build passed",
            "value": "Auto polarity marker on success.",
            "register": "arch",
            "exit_code": 0,
        })[0]["text"])
        self.assertEqual(res["status"], "ingested")
        self.assertEqual(res["polarity_applied"], 1.5)

    def test_exit_code_zero_user_edited(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "build passed edited",
            "value": "Auto polarity marker on success edit.",
            "register": "arch",
            "exit_code": 0,
            "user_edited": True,
        })[0]["text"])
        self.assertEqual(res["polarity_applied"], 0.5)

    def test_exit_code_nonzero_defaults(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "build failed",
            "value": "Auto polarity marker on failure.",
            "register": "bug",
            "exit_code": 1,
        })[0]["text"])
        self.assertEqual(res["status"], "ingested")
        # bug register: NEG_DAMPEN=1.0 (AD-7), so -0.5 stays -0.5
        self.assertEqual(res["polarity_applied"], -0.5)

    def test_explicit_polarity_wins_over_exit_code(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "both given",
            "value": "Explicit polarity precedence marker.",
            "register": "bug",  # NEG_DAMPEN=1.0: -2.0 survives undamped
            "polarity": -2.0,
            "exit_code": 0,
        })[0]["text"])
        self.assertEqual(res["polarity_applied"], -2.0)

    def test_negative_polarity_damped_on_arch(self):
        # AD-7 sanity: arch uses NEG_DAMPEN_DEFAULT=0.6 → -2.0 becomes -1.2
        res = json.loads(cms._ingest(self.cm, {
            "key": "dampened",
            "value": "Arch register damping marker.",
            "register": "arch",
            "polarity": -2.0,
        })[0]["text"])
        self.assertEqual(res["polarity_applied"], -1.2)

    def test_neither_polarity_nor_exit_code_errors(self):
        raw = cms._ingest(self.cm, {
            "key": "missing polarity",
            "value": "Should never ingest this marker.",
            "register": "arch",
        })[0]["text"]
        self.assertIn("error", json.loads(raw))

    def test_unknown_register_passthrough_error(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "k", "value": "some valid content",
            "register": "not_a_register", "polarity": 1.0,
        })[0]["text"])
        self.assertEqual(res.get("status"), "error")

    def test_scrub_gate_rejects_pure_noise(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "key", "value": ">.< ㅋㅋㅋ",  # scrubs to empty (Batch B case)
            "register": "style", "polarity": 1.5,
        })[0]["text"])
        self.assertEqual(res.get("status"), "rejected")
        self.assertEqual(res.get("reason"), "empty_after_sanitize")

    def test_project_tag_lands_in_value_bank(self):
        res = json.loads(cms._ingest(self.cm, {
            "key": "tagged entry",
            "value": "Project-tagged marker content omega.",
            "register": "arch",
            "polarity": 1.0,
            "project": "myproj",
        })[0]["text"])
        self.assertEqual(res["status"], "ingested")
        tagged = [e for e in self.cm._value_bank if e.get("project") == "myproj"]
        self.assertTrue(tagged)
        self.assertEqual(tagged[-1]["value"], "Project-tagged marker content omega.")


# ---------------------------------------------------------------------------
# crow_admin dispatch
# ---------------------------------------------------------------------------

class CrowAdminTests(SchemaTestBase):

    def _dispatch(self, action, args=None):
        raw = cms._admin(self.cm, {"action": action, "args": args or {}})
        return json.loads(raw[0]["text"])

    def test_diagnostics(self):
        res = self._dispatch("diagnostics")
        self.assertIn("value_bank_size", res)
        self.assertIn("prompt", res)

    def test_drift(self):
        res = self._dispatch("drift")
        self.assertIn("drift_detected", res)

    def test_prompt_read(self):
        raw = cms._admin(self.cm, {"action": "prompt",
                                   "args": {"action": "read"}})[0]["text"]
        # _manage_prompt returns raw prompt text (not a JSON envelope)
        self.assertIn("Crow Memory", raw)

    def test_prompt_stats(self):
        res = self._dispatch("prompt", {"action": "stats"})
        self.assertIsInstance(res, dict)

    def test_prompt_append(self):
        res = self._dispatch("prompt",
                             {"action": "append", "rule": "RULE: test rule"})
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "appended")

    def test_backup_list(self):
        res = self._dispatch("backup", {"action": "list"})
        self.assertIn("backups", res)

    def test_backup_create_dispatches_to_handler(self):
        with mock.patch.object(self.cm, "create_backup",
                               return_value="x.bak") as spy:
            res = self._dispatch("backup", {"action": "create", "tag": "test"})
        spy.assert_called_once_with("test")
        self.assertEqual(res, {"backup_path": "x.bak"})

    def test_backup_rotate(self):
        res = self._dispatch("backup", {"action": "rotate"})
        self.assertIn("rotated", res)

    def test_backup_recover(self):
        res = self._dispatch("backup", {"action": "recover"})
        self.assertIsInstance(res, dict)

    def test_evolve(self):
        res = self._dispatch("evolve")
        self.assertIn("requires_human_approval", res)

    def test_project_info_list(self):
        res = self._dispatch("project_info", {"action": "list"})
        self.assertIn("projects", res)

    def test_project_info_create_requires_name(self):
        res = self._dispatch("project_info", {"action": "create"})
        self.assertIn("error", res)

    def test_unknown_action_errors(self):
        res = self._dispatch("nonexistent_action")
        self.assertIn("error", res)
        self.assertIn("nonexistent_action", res["error"])

    def test_dispatch_table_reuses_handlers(self):
        # AD-5 L222-229: crow_admin maps to the SAME handler functions
        with mock.patch.object(cms, "_diagnostics", wraps=cms._diagnostics) as spy:
            cms._admin(self.cm, {"action": "diagnostics", "args": {}})
            spy.assert_called_once()
        with mock.patch.object(cms, "_drift", wraps=cms._drift) as spy:
            cms._admin(self.cm, {"action": "drift", "args": {}})
            spy.assert_called_once()
        with mock.patch.object(cms, "_evolve", wraps=cms._evolve) as spy:
            cms._admin(self.cm, {"action": "evolve", "args": {}})
            spy.assert_called_once()


# ---------------------------------------------------------------------------
# REST parity (route logic mirrors the tool dispatch)
# ---------------------------------------------------------------------------

class RestRouteTests(SchemaTestBase):

    def test_recall_all_uses_recall_multi_with_project_params(self):
        self.ingest_hit("class writing", "Store all timestamps in UTC.", "context")

        class FakeRequest:
            query_params = {
                "query": "class writing",
                "register": "all",
                "limit": "3",
                "project": "webapp",
                "strict_project": "true",
            }
            def get(self, k, default=None):
                return self.query_params.get(k, default)

        with mock.patch.object(crow_core.CrowMemory, "recall_multi",
                               wraps=self.cm.recall_multi) as spy:
            body = _run(_rest_recall(self.cm, FakeRequest()))
        spy.assert_called_once()
        kwargs = spy.call_args[1]
        self.assertEqual(kwargs.get("project"), "webapp")
        self.assertTrue(kwargs.get("strict_project"))
        data = json.loads(body)
        self.assertIn("results", data)
        self.assertTrue(any("UTC" in r["content"] for r in data["results"]))

    def test_ingest_route_accepts_project(self):
        class FakeRequest:
            async def body(self):
                return json.dumps({
                    "content": "REST project route marker text.",
                    "register": "arch",
                    "project": "restproj",
                }).encode("utf-8")

        _run(_rest_ingest_helper(self.cm, FakeRequest()))
        tagged = [e for e in self.cm._value_bank
                  if e.get("project") == "restproj"]
        self.assertTrue(any("REST project route" in e["value"] for e in tagged))


async def _rest_recall(crow, request):
    """Mirrors the /recall route body (see crow_mcp_server.rest_recall) so
    param forwarding can be asserted without binding to the server closure."""
    query = request.query_params.get("query", "")
    register = request.query_params.get("register", "all")
    limit = min(max(int(request.query_params.get("limit", "5")), 1), 20)
    project = request.query_params.get("project") or None
    strict_project = request.query_params.get("strict_project", "false") \
        .lower() in ("1", "true", "yes")

    if register == "all":
        result = crow.recall_multi(query, crow_core.DOMAINS["all"], limit,
                                   project=project,
                                   strict_project=strict_project)
        results = [{"content": h.get("text", ""),
                    "score": h.get("eff_sim", 0.0)}
                   for h in result.get("hints", [])]
    else:
        r = crow.recall(query, register, top_k=limit,
                        project=project, strict_project=strict_project)
        results = [{"content": h, "score": r.get("confidence", 0.0)}
                   for h in r.get("hints", [])]
    return json.dumps({"results": results, "count": len(results)})


async def _rest_ingest_helper(crow, request):
    """Mirrors the /ingest route body — scrub gate stays inside crow.ingest."""
    body_bytes = await request.body()
    data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    content = data.get("content", "")
    crow.ingest(key=content[:200], value=content, polarity=1.0,
                register=data.get("register", "context"),
                project=data.get("project"))


# ---------------------------------------------------------------------------
# i18n mirror
# ---------------------------------------------------------------------------

class I18nSchemaTests(unittest.TestCase):

    def setUp(self):
        crow_i18n._CACHE.clear()
        crow_i18n._detected_locale = None

    def tearDown(self):
        crow_i18n._CACHE.clear()
        crow_i18n._detected_locale = None

    def test_en_definitions_three_tools(self):
        tools = crow_i18n.get_tool_definitions("en")
        self.assertEqual({t["name"] for t in tools},
                         {"crow_recall", "crow_ingest", "crow_admin"})

    def test_recall_schema_params(self):
        tools = {t["name"]: t for t in crow_i18n.get_tool_definitions("en")}
        props = tools["crow_recall"]["inputSchema"]["properties"]
        self.assertIn("format", props)
        self.assertIn("project", props)
        self.assertIn("strict_project", props)
        self.assertEqual(tools["crow_recall"]["inputSchema"]["required"], ["query"])
        self.assertEqual(props["format"]["enum"], ["hint", "bias_block"])
        self.assertEqual(props["top_k"]["minimum"], 1)
        self.assertEqual(props["top_k"]["maximum"], 5)

    def test_ingest_schema_params(self):
        tools = {t["name"]: t for t in crow_i18n.get_tool_definitions("en")}
        props = tools["crow_ingest"]["inputSchema"]["properties"]
        self.assertIn("polarity", props)
        self.assertIn("exit_code", props)
        self.assertIn("user_edited", props)
        self.assertIn("project", props)
        self.assertEqual(tools["crow_ingest"]["inputSchema"]["required"],
                         ["key", "value", "register"])

    def test_admin_schema_params(self):
        tools = {t["name"]: t for t in crow_i18n.get_tool_definitions("en")}
        props = tools["crow_admin"]["inputSchema"]["properties"]
        self.assertEqual(props["action"]["enum"],
                         ["diagnostics", "drift", "prompt", "backup",
                          "evolve", "project_info"])
        self.assertEqual(props["args"]["type"], "object")
        self.assertEqual(tools["crow_admin"]["inputSchema"]["required"], ["action"])

    def test_ko_keys_descriptions(self):
        data = crow_i18n._load_locale("ko")
        for name in ("crow_recall", "crow_ingest", "crow_admin"):
            self.assertIn(name, data["tools"])
            self.assertTrue(data["tools"][name]["description"])
            self.assertIsInstance(data["tools"][name]["parameters"], dict)

    def test_ko_new_param_keys(self):
        data = crow_i18n._load_locale("ko")
        self.assertIn("format", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("project", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("strict_project", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("exit_code", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("user_edited", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("project", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("args", data["tools"]["crow_admin"]["parameters"])

    def test_en_new_param_keys(self):
        data = crow_i18n._load_locale("en")
        self.assertIn("format", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("project", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("strict_project", data["tools"]["crow_recall"]["parameters"])
        self.assertIn("exit_code", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("user_edited", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("project", data["tools"]["crow_ingest"]["parameters"])
        self.assertIn("args", data["tools"]["crow_admin"]["parameters"])

    def test_obsolete_keys_removed_en(self):
        data = crow_i18n._load_locale("en")
        for name in ("crow_evolve_propose", "crow_diagnostics", "crow_check_drift",
                     "crow_ingest_from_build", "crow_get_user_bias",
                     "crow_manage_prompt", "crow_manage_backup", "crow_project_info"):
            self.assertNotIn(name, data["tools"])

    def test_obsolete_keys_removed_ko(self):
        data = crow_i18n._load_locale("ko")
        for name in ("crow_evolve_propose", "crow_diagnostics", "crow_check_drift",
                     "crow_ingest_from_build", "crow_get_user_bias",
                     "crow_manage_prompt", "crow_manage_backup", "crow_project_info"):
            self.assertNotIn(name, data["tools"])

    def test_server_and_i18n_schemas_match(self):
        tmp = tempfile.mkdtemp(prefix="crow_schema_match_")
        try:
            server, _ = cms.create_server(os.path.join(tmp, "crow.bin"))
            mcp_tools = {t.name for t in _run(server.list_tools())}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        i18n_tools = {t["name"] for t in crow_i18n.get_tool_definitions("en")}
        self.assertEqual(mcp_tools, i18n_tools)


# ---------------------------------------------------------------------------
# CROW_STATE_TAG resolution (AD-8.2)
# ---------------------------------------------------------------------------

class StatePathTests(unittest.TestCase):

    def test_tag_set(self):
        with mock.patch.dict(os.environ, {"CROW_STATE_TAG": "myk1yt"}):
            resolved = cms.resolve_state_path("./memory/crow.bin")
        self.assertEqual(PurePosixPath(*Path(resolved).parts[-2:]).as_posix(),
                         "memory/crow-myk1yt.bin")

    def test_tag_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "CROW_STATE_TAG"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cms.resolve_state_path("./memory/crow.bin"),
                             "./memory/crow.bin")

    def test_tag_whitespace_only_is_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "CROW_STATE_TAG"}
        env["CROW_STATE_TAG"] = "   "
        with mock.patch.dict(os.environ, env, clear=True):
            # Whitespace-only tag must NOT trigger the suffix
            self.assertEqual(cms.resolve_state_path("./memory/crow.bin"),
                             "./memory/crow.bin")

    def test_full_state_path(self):
        with mock.patch.dict(os.environ, {"CROW_STATE_TAG": "myk1yt"}):
            p = cms.resolve_state_path("/data/crow.bin")
        self.assertEqual(os.path.basename(p), "crow-myk1yt.bin")

    def test_memory_dir_derives_from_state_dir(self):
        # VERIFY (AD-8.2): crow_core.memory_dir = dirname(state_path), so
        # tag-resolved state paths automatically relocate value_bank.json,
        # recall_stats.json, and system_prompt.md next to the tagged bin.
        tmp = tempfile.mkdtemp(prefix="crow_state_")
        try:
            real = os.path.join(tmp, "crow-myk1yt.bin")
            cm = crow_core.CrowMemory(real)
            self.assertEqual(cm.memory_dir, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Batch B regression wiring (server imports crow_core cleanly)
# ---------------------------------------------------------------------------

class ServerCoreWiringTests(SchemaTestBase):

    def test_recall_multi_present(self):
        self.assertTrue(hasattr(crow_core.CrowMemory, "recall_multi"))

    def test_ingest_accepts_project(self):
        import inspect
        sig = inspect.signature(crow_core.CrowMemory.ingest)
        self.assertIn("project", sig.parameters)

    def test_recall_accepts_project(self):
        import inspect
        for p in ("project", "strict_project"):
            self.assertIn(p,
                          inspect.signature(crow_core.CrowMemory.recall).parameters)

    def test_server_module_imports_domains(self):
        # crow_mcp_server imports DOMAINS at module level (used by _recall)
        self.assertTrue(hasattr(cms, "DOMAINS"))
        self.assertEqual(set(cms.DOMAINS["code"]),
                         {"style", "bug", "arch", "context"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
