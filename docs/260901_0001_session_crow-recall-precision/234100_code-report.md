# Code Mode Task Report — Batch A: Sanitizer Module
**Session:** docs/260901_0001_session_crow-recall-precision/
**Mode:** code | **Time:** 2026-09-01 23:41 KST

## Task Summary
Implement AD-1 from the architect report: a stdlib-only sanitizer module `crow_sanitize.py` (conservative noise scrubbing before encode) plus a full `unittest` pattern matrix in `tests/test_sanitize.py`. Covers REQ-005 (ingest-gate scrub), REQ-006 (display alias), and REQ-008 partially (`project_slug`).

## Actions Taken
1. Read AD-1 spec ([233400_architect-report.md](../233400_architect-report.md) L90-116) and requirement checklist REQ-005/006/008.
2. Created [`crow_sanitize.py`](../../../crow_sanitize.py):
   - `scrub_text(text)` — ordered rules 1-5 exactly per AD-1 rule table (emoji blocks → lone jamo/tilde/caret runs → kaomoji glyph classes + explicit literals → repeated punctuation → whitespace normalization). All 8 patterns compiled once at module load.
   - `scrub_display(text)` — **true alias** (`scrub_display = scrub_text`, same function object) per AD-1 "alias for call-site clarity".
   - `project_slug(workspace_path)` — architect's reference regex verbatim: basename of normpath → lowercase → `[^a-z0-9_-]+`→`-` → strip `-` → `slug or None`.
   - Pure stdlib (`re`, `os` only). Zero heavy deps; importable standalone for REQ-007 migration script.
3. Design refinement over the architect's sketch (documented, conservative-safe): the sketch regex `(?:[>oO0Tt][._-]?[<oO0vV])+` as written would swallow English words like "to". Implemented instead as boundary-guarded glyph classes (`(?<![\w.])…(?![\w.])`) + explicit literal list (`>_<' ._.`, `_._`, `TuT/TnT/TvT/QuQ/QwQ`). This protects `test_ok`, `10_000`, `127.0.0.1`, `v0.0.1` while removing all AD-1-listed kaomoji.
4. Created [`tests/test_sanitize.py`](../../../tests/test_sanitize.py) — 55 plain-`unittest` tests across 8 classes: Rule1 emoji, Rule2 jamo runs, Rule3 kaomoji (11 removal + 4 protection), Rule4 punctuation (incl. `C++` and ellipsis edge cases verbatim), Rule5 whitespace, MandatoryProtectionCases (all 5 AD-1 edge notes verbatim), MixAndContract, ProjectSlug (7 cases incl. trailing slash / non-ASCII / None / empty / symbol-only).
5. Iteration log (3 test-side issues found, zero spec violations):
   - FAIL `test_scrub_display_alias_signature`: wrapper ≠ true alias → made `scrub_display` a real name alias (`scrub_display = scrub_text`).
   - FAIL `test_dot_underscore_dot`: `._.` excluded by design to protect IPs → added `._.`/`_._` as explicit literals with the same safe boundaries (first attempt with a separate `_?._` pattern was itself buggy due to trailing-dot lookahead; second attempt folded literals into the alternation — root cause fixed).
   - FAIL `test_module_does_not_import_heavy_deps`: docstring text tripped substring check → test now scans only actual `import`/`from` statements.
6. Ran `python tests/test_sanitize.py -v` — **exit 0, 55/55 OK** (final run output below).

## Result
✅ SUCCESS — zero failures. Actual final run output:
```
Ran 55 tests in 0.003s

OK
```
All 55 test names listed `... ok` in the verbose run (Rule1 4/4, Rule2 5/5, Rule3 15/15, Rule4 8/8, Rule5 5/5, MandatoryProtection 5/5, MixAndContract 4/4, ProjectSlug 7/7, StdlibOnly 1/1, plus MixAndContract members listed above).

## Mandatory Protection Cases — verified
- `scrub_text("C++ and C#")` unchanged ✅
- `scrub_text("...")` → `...` preserved; 4+ dots → exactly 3 ✅
- `scrub_text("use abort_signal.link()")` unchanged ✅
- `scrub_text("이 패턴은 항상 실패한다")` unchanged ✅
- `scrub_text(">.< ㅋㅋㅋ")` → `""` ✅

## Issues Discovered
- None blocking. Note for Batch B: `scrub_text` returns `""` for pure-noise input; the `empty_after_sanitize` ingest-gate rejection is Batch B's responsibility per delegation.
- Note: `scrub_text(None)` defensively returns `""` (typed `str` param; None-tolerant like the rest of crow_core's ingest path).

## Next Step Recommendations
- Batch B may `from crow_sanitize import scrub_text, scrub_display, project_slug` — no `CrowMemory` instantiation needed.
- For REQ-008 server wiring: derive slug server-side from workspace path via `project_slug`; explicit `project` param overrides (AD-2/AD-3 territory).

## Affected File List
- **Created:** `crow_sanitize.py` (new, 129 lines)
- **Created:** `tests/test_sanitize.py` (new, 55 tests)
- **Edited:** none — zero modifications to existing files (crow_core.py untouched, per constraint).
