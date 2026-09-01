"""crow_sanitize.py - Conservative text sanitizer for Crow Memory (Batch A).

Implements AD-1 from the recall-precision architect report:
    - scrub_text(text)  : ordered conservative rules, text -> text
    - scrub_display(text): display-time alias of scrub_text (REQ-006)
    - project_slug(path) : basename -> kebab slug for project tagging (REQ-008)

Design principle: remove only what is unambiguously noise, never restructure
prose. Korean composed syllables (U+AC00-U+D7A3) and ASCII identifiers are
never targeted. This module is stdlib-only (re, os) and MUST stay importable
without sentence_transformers so the migration script can use it standalone.

SANITIZE/design/001 - all patterns compiled once at module load.
"""

import os
import re

__all__ = ["scrub_text", "scrub_display", "project_slug"]

# ---------------------------------------------------------------------------
# Rule 1 (SANITIZE/scrub_text/001): emoji / pictograph / symbol blocks.
# Removes emoji + dingbats; protects ASCII, CJK, and Hangul.
# ---------------------------------------------------------------------------
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")

# ---------------------------------------------------------------------------
# Rule 2 (SANITIZE/scrub_text/002): lone jamo laughter + tilde/caret runs.
# Matches decomposed jamo (U+1100-11FF subset ㄱ-ㅎ consonants, ㅏ-ㅣ vowels)
# plus '~' and '^' when they appear in runs of 2+. Composed Hangul syllables
# (U+AC00-U+D7A3, e.g. 가-힣) are NOT in this range -> Korean prose is safe.
# ---------------------------------------------------------------------------
_JAMO_RUN_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ~^]{2,}")

# ---------------------------------------------------------------------------
# Rule 3 (SANITIZE/scrub_text/003): kaomoji / emoticon glyph runs.
# Three glyph-class patterns + one explicit literal list. Every pattern is
# anchored with non-word AND non-dot boundaries so identifiers, dotted
# version strings and dotted IPs can never match:
#   test_ok, foo_bar(), 10_000, 127.0.0.1, v1.0.0  -> all untouched.
# Kaomoji are standalone tokens in natural-language memories, so these
# boundaries remove nothing legitimate.
# ---------------------------------------------------------------------------

# Eye characters used in letter-based kaomoji (T_T, o_o, 0_0, x_x, ._. style).
# NOTE: '.' is deliberately NOT an exterior eye char (handled by the literal
# list) so "..." ellipsis or "127.0.0.1" can never be parsed as kaomoji.
_EYE = r"[xXoOuU0Tt@;+\-=]"

# letter _ / . letter  ->  T_T, o_o, 0_0, X_X, =_=, -_-, ;_;, @_@
_KAOMOJI_UNDERSCORE_RE = re.compile(r"(?<![\w.])" + _EYE + r"[_.]" + _EYE + r"(?![\w.])")

# letter v/w/. letter  ->  0v0, OvO, uwu, OwO, 0.0, o.o (uWu-style faces)
_KAOMOJI_UVU_RE = re.compile(r"(?<![\w.])[oOuU0][vVwW.][oOuU0](?![\w.])")

# non-alphabetic glyph pairs/runs -> >.<, ><, >_<, ^v^, ^^, >m<
_KAOMOJI_ANGLE_RE = re.compile(r"[><^]{2,}|[><^][._\-+oOvVmM^][><^]")

# explicit literal list for faces not covered by the letter classes. `._.`
# and `_._` use '.' as an eye — deliberately excluded from _EYE to protect
# IPs/version strings — so they are matched here as explicit literals with
# the same safe non-word/non-dot boundaries.
_KAOMOJI_LITERAL_RE = re.compile(
    r"(?<![\w.])(?:TuT|TnT|TvT|QuQ|QwQ|\._\.|_\._)(?![\w.])"
)

# ---------------------------------------------------------------------------
# Rule 4 (SANITIZE/scrub_text/004): repeated punctuation.
# Dots: 4+ run collapses to exactly 3 (ellipsis "..." is PRESERVED).
# !(question/star): 3+ run collapses to 2 ('!' '!' '*' '*').
# NOTE: '+' (#4 'C++' protection) and '#' are deliberately excluded.
# ---------------------------------------------------------------------------
_DOT_RUN_RE = re.compile(r"(\.)\1{3,}")
_PUNCT_RUN_RE = re.compile(r"([!?*])\1{2,}")

# ---------------------------------------------------------------------------
# Rule 5 (SANITIZE/scrub_text/005): whitespace normalization.
# [ \t]+ -> single space, 3+ newlines -> 2, then strip both ends.
# ---------------------------------------------------------------------------
_SPACES_RE = re.compile(r"[ \t]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def scrub_text(text: str) -> str:
    """Conservatively scrub noise text (SANITIZE/scrub_text/000).

    Ordered rules: emoji -> jamo/tilde runs -> kaomoji -> punctuation runs
    -> whitespace. Returns '' for text that is pure noise; callers (Batch B
    ingest gate) treat '' as a reject signal.
    """
    if not text:
        return ""
    out = _EMOJI_RE.sub("", text)
    out = _JAMO_RUN_RE.sub("", out)
    out = _KAOMOJI_UNDERSCORE_RE.sub("", out)
    out = _KAOMOJI_UVU_RE.sub("", out)
    out = _KAOMOJI_ANGLE_RE.sub("", out)
    out = _KAOMOJI_LITERAL_RE.sub("", out)
    out = _DOT_RUN_RE.sub(r"\1\1\1", out)
    out = _PUNCT_RUN_RE.sub(r"\1\1", out)
    out = _SPACES_RE.sub(" ", out)
    out = _NEWLINES_RE.sub("\n\n", out)
    return out.strip()


def scrub_display(text: str) -> str:
    """Display-time alias of scrub_text (SANITIZE/scrub_display/000, REQ-006).

    True name alias (same function object) for call-site clarity: legacy
    value_bank entries are scrubbed at render time so hint output never
    shows kaomoji/symbol garbage.
    """
    return scrub_text(text)


scrub_display = scrub_text  # true alias: single function object, both names


def project_slug(workspace_path: str | None) -> str | None:
    """Derive a kebab-case project slug from a workspace path (REQ-008).

    Examples:
        'd:/OneDrive/Projects/Crow Memory' -> 'crow-memory'
        'C:\\work\\MyProject\\'             -> 'myproject'   (trailing slash ok)
        'd:/work/한글프로젝트'              -> None          (non-ASCII name)
        None / ''                          -> None
    """
    if not workspace_path:
        return None
    base = os.path.basename(os.path.normpath(workspace_path))
    slug = re.sub(r"[^a-z0-9_-]+", "-", base.lower()).strip("-")
    return slug or None
