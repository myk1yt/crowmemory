"""crow_text.py - shared text utilities for Crow Memory v2 (contract S5).

Stdlib only (os, re, math, unicodedata).

- _smart_truncate(text, limit=None) : env CROW_HINT_MAX_CHARS aware cut at
  sentence/space boundary (default 500, floor 450).
- _tokenize(text) : lowercase; ASCII/alnum runs become whole words; scripts
  without spaces (Hangul/CJK/Thai/...) become character unigrams+bigrams.
  Stopword-free.
- token_cosine(a_tokens, b_tokens) : cosine similarity over frequency vectors.
"""

import math
import os
import re
import unicodedata
from functools import lru_cache

HINT_MAX_CHARS_DEFAULT = 500
HINT_MAX_CHARS_FLOOR = 450

# On lowered text: ASCII alnum runs OR single non-ASCII, non-space chars.
# Punctuation and whitespace are separators.
_TOKEN_RUN_RE = re.compile(r"[a-z0-9]+|[^\x00-\x7f\s]", re.UNICODE)

# Sentence terminators (ASCII + CJK full-width).
_SENT_END_RE = re.compile(r"[.!?。！？\n]")


def _in_spaceless_block(o: int) -> bool:
    """Codepoint ranges for scripts written without inter-word spaces
    (Hangul, CJK, kana, Thai, Lao, Tibetan, Burmese, Khmer, Yi, ...)."""
    return (
        0x1100 <= o <= 0x11FF      # Hangul jamo
        or 0x0E00 <= o <= 0x0E7F   # Thai
        or 0x0E80 <= o <= 0x0EFF   # Lao
        or 0x0F00 <= o <= 0x0FFF   # Tibetan
        or 0x1000 <= o <= 0x109F   # Burmese
        or 0x1780 <= o <= 0x17FF   # Khmer
        or 0x2E80 <= o <= 0x30FF   # CJK radicals / kana
        or 0x3130 <= o <= 0x318F   # Hangul compat jamo
        or 0x3400 <= o <= 0x4DBF   # CJK ext A
        or 0x4E00 <= o <= 0x9FFF   # CJK unified
        or 0xA000 <= o <= 0xA4CF   # Yi
        or 0xAC00 <= o <= 0xD7AF   # Hangul syllables
        or 0xF900 <= o <= 0xFAFF   # CJK compat ideographs
        or 0x20000 <= o <= 0x2FA1F  # CJK ext B..compat sup
    )


@lru_cache(maxsize=8192)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    prev_cjk = ""
    in_block = _in_spaceless_block
    for tok in _TOKEN_RUN_RE.findall(text.lower()):
        if len(tok) == 1 and not tok.isascii():
            o = ord(tok)
            if not in_block(o):
                cat = unicodedata.category(tok)
                if cat.startswith(("P", "S", "Z", "C")):
                    prev_cjk = ""
                    continue
                # space-separated non-ASCII script (Cyrillic, Greek, ...):
                # the char is its own word token
                tokens.append(tok)
                prev_cjk = ""
                continue
            # space-less script char: unigram + bigram with previous char
            tokens.append(tok)
            if prev_cjk:
                tokens.append(prev_cjk + tok)
            prev_cjk = tok
        else:
            tokens.append(tok)
            prev_cjk = ""
    return tuple(tokens)


def _tokenize(text: str) -> list[str]:
    """Tokenize per contract S3: lowercase; ASCII/alnum runs = words; scripts
    without spaces (Hangul/CJK/Thai/...) = character unigrams+bigrams.
    Stopword-free. Cached per process (bounded lru_cache)."""
    return list(_tokenize_cached(text or ""))


@lru_cache(maxsize=8192)
def _freq_cached(tokens: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return tuple(freq.items())


def token_cosine(a_tokens: list[str], b_tokens: list[str]) -> float:
    """Cosine similarity over token frequency vectors. Empty side -> 0.0."""
    if not a_tokens or not b_tokens:
        return 0.0
    fa = dict(_freq_cached(tuple(a_tokens)))
    fb = dict(_freq_cached(tuple(b_tokens)))
    if len(fa) > len(fb):
        fa, fb = fb, fa
    dot = 0.0
    for t, c in fa.items():
        other = fb.get(t)
        if other:
            dot += c * other
    na = math.sqrt(sum(c * c for c in fa.values()))
    nb = math.sqrt(sum(c * c for c in fb.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _smart_truncate(text: str, limit: int | None = None) -> str:
    """Cut text at the last sentence/space boundary at or below limit.

    limit=None resolves from env CROW_HINT_MAX_CHARS (default 500, floor 450).
    An explicit limit is honored as-is. '...' is appended only when the text
    was actually truncated (mid-text cut). A cut that lands exactly on a
    sentence terminator gets ' ...' to avoid '....' runs.
    """
    if limit is None:
        limit = HINT_MAX_CHARS_DEFAULT
        env = os.environ.get("CROW_HINT_MAX_CHARS")
        if env:
            try:
                limit = int(env)
            except ValueError:
                limit = HINT_MAX_CHARS_DEFAULT
        limit = max(HINT_MAX_CHARS_FLOOR, limit)
    if not text:
        return ""
    if len(text) <= limit:
        return text

    # reserve room for the ellipsis so the result never exceeds limit
    window = text[:limit - 3]
    cut = -1
    for m in _SENT_END_RE.finditer(window):
        cut = m.end()
    if cut <= 0:
        sp = window.rfind(" ")
        cut = sp + 1 if sp > 0 else len(window)
    out = window[:cut].rstrip()
    if not out:
        out = window.rstrip()
    suffix = " ..." if out and out[-1] in ".!?。！？" else "..."
    if len(out) + len(suffix) > limit:
        out = out[:limit - len(suffix)].rstrip()
    return out + suffix


