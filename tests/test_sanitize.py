"""tests/test_sanitize.py - Unit tests for crow_sanitize (Batch A).

Covers the full AD-1 pattern matrix: emoji, jamo/tilde runs, kaomoji,
repeated punctuation, whitespace; all mandatory protection cases from the
architect report edge notes; and project_slug (REQ-008).

Run:  python tests/test_sanitize.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crow_sanitize  # noqa: E402
from crow_sanitize import project_slug, scrub_display, scrub_text  # noqa: E402


class Rule1EmojiTests(unittest.TestCase):
    def test_emoji_removed(self):
        self.assertEqual(scrub_text("Party 🎉 time"), "Party time")

    def test_dingbat_and_fe0f_removed(self):
        self.assertEqual(scrub_text("ok\u2764\uFE0F"), "ok")

    def test_emoji_only_to_empty(self):
        self.assertEqual(scrub_text("\U0001F600\U0001F602"), "")

    def test_cjk_protected_from_emoji_rule(self):
        self.assertEqual(scrub_text("한국어 확실히 지원"), "한국어 확실히 지원")


class Rule2JamoRunTests(unittest.TestCase):
    def test_jamo_laughter_run_removed(self):
        self.assertEqual(scrub_text("ㅋㅋㅋ 웃겨"), "웃겨")

    def test_cry_run_removed(self):
        self.assertEqual(scrub_text("ㅠㅠ 슬퍼"), "슬퍼")

    def test_tilde_run_removed(self):
        self.assertEqual(scrub_text("아니~~~ 진짜"), "아니 진짜")

    def test_caret_run_removed(self):
        self.assertEqual(scrub_text("ㅎㅎ^^ 좋아"), "좋아")

    def test_korean_prose_unchanged(self):
        # composed syllables 가-힣 are NOT in the lone-jamo range
        self.assertEqual(
            scrub_text("이 패턴은 항상 실패한다"), "이 패턴은 항상 실패한다"
        )

    def test_single_jamo_protected(self):
        self.assertEqual(scrub_text("가힣"), "가힣")


class Rule3KaomojiTests(unittest.TestCase):
    def test_gt_lt_dot(self):
        self.assertEqual(scrub_text(">.<"), "")

    def test_gt_lt(self):
        self.assertEqual(scrub_text(">< 그만"), "그만")

    def test_zero_v_zero(self):
        self.assertEqual(scrub_text("0v0 놀랐다"), "놀랐다")

    def test_tt_underscore(self):
        self.assertEqual(scrub_text("T_T 나도 몰라"), "나도 몰라")

    def test_o_o(self):
        self.assertEqual(scrub_text("o_o 진심?"), "진심?")

    def test_uwu(self):
        self.assertEqual(scrub_text("uwu 귀여워"), "귀여워")

    def test_caret_v_caret(self):
        self.assertEqual(scrub_text("^v^ 기분좋음"), "기분좋음")

    def test_dot_underscore_dot(self):
        self.assertEqual(scrub_text("._. 무말랭"), "무말랭")

    def test_qwq_literal(self):
        self.assertEqual(scrub_text("QwQ 좀 일해"), "좀 일해")

    def test_x_x(self):
        self.assertEqual(scrub_text("x_X 힘들다"), "힘들다")

    def test_only_noise_to_empty(self):
        # mandatory AD-1 edge case
        self.assertEqual(scrub_text(">.< ㅋㅋㅋ"), "")

    def test_underscore_identifier_protected(self):
        self.assertEqual(scrub_text("test_ok case_o"), "test_ok case_o")

    def test_numbers_protected_by_boundaries(self):
        self.assertEqual(scrub_text("총 10_000건"), "총 10_000건")

    def test_dotted_ip_protected(self):
        self.assertEqual(scrub_text("IP 127.0.0.1 접속"), "IP 127.0.0.1 접속")

    def test_version_string_protected(self):
        self.assertEqual(scrub_text("v0.0.1 배포"), "v0.0.1 배포")


class Rule4PunctuationTests(unittest.TestCase):
    def test_exactly_three_dots_preserved(self):
        self.assertEqual(scrub_text("..."), "...")

    def test_four_dots_collapse_to_three(self):
        self.assertEqual(scrub_text("그래.... 알았어"), "그래... 알았어")

    def test_long_dot_run_collapse_to_three(self):
        self.assertEqual(scrub_text("하아......"), "하아...")

    def test_bang_run_collapse_to_two(self):
        self.assertEqual(scrub_text("놀라워!!!"), "놀라워!!")

    def test_question_run_collapse_to_two(self):
        self.assertEqual(scrub_text("진짜????"), "진짜??")

    def test_star_run_collapse_to_two(self):
        self.assertEqual(scrub_text("****중요****"), "**중요**")

    def test_cpp_and_csharp_protected(self):
        # mandatory AD-1 edge case (+ excluded from rule 4)
        self.assertEqual(scrub_text("C++ and C#"), "C++ and C#")

    def test_markdown_bold_protected(self):
        self.assertEqual(scrub_text("**굵게** 짧게"), "**굵게** 짧게")


class Rule5WhitespaceTests(unittest.TestCase):
    def test_multi_space_to_single(self):
        self.assertEqual(scrub_text("many   spaces   here"), "many spaces here")

    def test_tabs_to_single_space(self):
        self.assertEqual(scrub_text("col1\tcol2"), "col1 col2")

    def test_triple_newline_to_double(self):
        self.assertEqual(scrub_text("a\n\n\n\nb"), "a\n\nb")

    def test_single_newline_preserved(self):
        self.assertEqual(scrub_text("line1\nline2"), "line1\nline2")

    def test_leading_trailing_stripped(self):
        self.assertEqual(scrub_text("   padded text   "), "padded text")


class MandatoryProtectionCases(unittest.TestCase):
    """AD-1 edge-note cases, verbatim."""

    def test_case_cpp(self):
        self.assertEqual(scrub_text("C++ and C#"), "C++ and C#")

    def test_case_ellipsis(self):
        self.assertEqual(scrub_text("..."), "...")

    def test_case_identifier(self):
        self.assertEqual(scrub_text("use abort_signal.link()"), "use abort_signal.link()")

    def test_case_korean_prose(self):
        self.assertEqual(scrub_text("이 패턴은 항상 실패한다"), "이 패턴은 항상 실패한다")

    def test_case_pure_noise_empty(self):
        self.assertEqual(scrub_text(">.< ㅋㅋㅋ"), "")


class MixAndContractTests(unittest.TestCase):
    def test_mixed_noise_and_prose(self):
        self.assertEqual(
            scrub_text("ㅋㅋㅋ 이건 실제 오류다!!! Traceback 확인 🤔"),
            "이건 실제 오류다!! Traceback 확인",
        )

    def test_empty_and_none_input(self):
        self.assertEqual(scrub_text(""), "")
        self.assertEqual(scrub_text(None), "")

    def test_scrub_display_is_scrub_text(self):
        self.assertEqual(scrub_display("C++ o_o ㅎㅎ"), "C++")

    def test_scrub_display_alias_signature(self):
        self.assertIs(crow_sanitize.scrub_display, crow_sanitize.scrub_text)


class ProjectSlugTests(unittest.TestCase):
    def test_normal_path(self):
        self.assertEqual(project_slug("d:/work/Crow Memory"), "crow-memory")

    def test_trailing_slash(self):
        self.assertEqual(project_slug("C:\\work\\MyProject\\"), "myproject")

    def test_underscores_and_kebab_preserved(self):
        self.assertEqual(project_slug("my_cool-tool"), "my_cool-tool")

    def test_non_ascii_name_returns_none(self):
        self.assertIsNone(project_slug("d:/work/한글프로젝트"))

    def test_none_input(self):
        self.assertIsNone(project_slug(None))

    def test_empty_input(self):
        self.assertIsNone(project_slug(""))

    def test_symbols_only_name_returns_none(self):
        self.assertIsNone(project_slug("d:/work/###"))


class StdlibOnlyImportTests(unittest.TestCase):
    def test_module_does_not_import_heavy_deps(self):
        # scan actual import STATEMENTS (docstring mentions are irrelevant)
        src = getattr(crow_sanitize, "__file__", "")
        self.assertTrue(src.endswith("crow_sanitize.py"))
        with open(src, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    for banned in ("sentence_transformers", "numpy", "faiss"):
                        self.assertNotIn(
                            banned, stripped,
                            f"crow_sanitize must stay stdlib-only; found: {stripped}",
                        )


if __name__ == "__main__":
    unittest.main()
