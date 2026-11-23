"""tests/test_i18n_claims.py - R2-8: no locale may advertise a trust claim that
the code does not enforce.

The v1.5 legacy display path reads `server.prompts.crow_evolved_rules.description`
from `i18n/<locale>.json`. Before FIX-E, 96/96 locales claimed the permanent
rules were "HITL approved", which was false while `prompt approve` needed no
human. The description is now a single canonical, token-truthful string in
every locale, and no locale may reintroduce the old wording.

Run:  python tests/test_i18n_claims.py -v
"""

import glob
import io
import json
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
I18N_DIR = os.path.join(REPO_ROOT, "i18n")
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))

import crow_mcp_stdio  # noqa: E402

# Wording that was only true if a human approved by hand and a token gate was
# in place; every variant claims a human checkpoint the model could bypass.
OLD_CLAIMS = (
    "HITL",
    "approved via HITL",
    "Permanent rules are HITL-approved",
)

CANONICAL = (
    "Permanent evolved rules from Crow's system_prompt.md: permanent rules "
    "(human-promoted via CROW_ADMIN_TOKEN) plus unreviewed model suggestions."
)


def _locales():
    for path in sorted(glob.glob(os.path.join(I18N_DIR, "*.json"))):
        with open(path, encoding="utf-8") as handle:
            yield path, json.load(handle)


def _raw(path):
    with io.open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _description(data):
    return data["server"]["prompts"]["crow_evolved_rules"]["description"]


class LocaleEvolutionDescriptionTests(unittest.TestCase):
    def test_all_96_locales_exist_and_share_one_description(self):
        locales = list(_locales())
        self.assertEqual(len(locales), 96)
        descriptions = {_description(data): path for path, data in locales}
        self.assertEqual(len(descriptions), 1, descriptions.keys())
        self.assertEqual(list(descriptions)[0], CANONICAL)

    def test_no_locale_carries_the_old_hitl_claim(self):
        offenders = []
        for path, data in _locales():
            raw = _raw(path)
            for claim in OLD_CLAIMS:
                if claim in raw:
                    offenders.append((os.path.basename(path), claim))
            description = _description(data)
            for claim in OLD_CLAIMS:
                self.assertNotIn(claim, description, path)
        self.assertEqual(offenders, [])

    def test_description_matches_the_mcp_prompt_constant(self):
        # the legacy i18n display path and the v2 PROMPTS text must not drift
        desc = crow_mcp_stdio.PROMPTS[1]["description"]
        self.assertEqual(desc, CANONICAL)
        self.assertIn("CROW_ADMIN_TOKEN", desc)
        self.assertNotIn("HITL", desc)

    def test_tool_description_names_the_token_gated_actions(self):
        tools = {t["name"]: t for t in crow_mcp_stdio.TOOLS}
        admin = tools["crow_admin"]["description"]
        self.assertIn("CROW_ADMIN_TOKEN", admin)
        self.assertIn("prompt approve", admin)
        self.assertIn("confirm_all", admin)
        self.assertNotIn("HITL", admin)

    def test_rewriting_the_same_value_changes_nothing(self):
        # the sync script is idempotent: a re-run must report 0 changes
        literal = json.dumps(CANONICAL)
        changed = []
        for path in sorted(glob.glob(os.path.join(I18N_DIR, "*.json"))):
            raw = _raw(path)
            self.assertEqual(raw.count('"crow_evolved_rules"'), 1, path)
            key_at = raw.index('"crow_evolved_rules"')
            desc_at = raw.index('"description"', key_at)
            start = raw.index('"', raw.index(":", desc_at))
            end = raw.index(literal, start)
            rewritten = raw[:start] + literal + raw[end + len(literal):]
            if rewritten != raw:
                changed.append(os.path.basename(path))
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
