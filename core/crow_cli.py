#!/usr/bin/env python3
"""crow_cli.py - Crow Memory v2 unified CLI and lifecycle-hook adapter.

One entry point for every adapter (Antigravity `agy`, Claude Code, Kimi Code,
Cursor, generic text). Zero third-party dependencies: the only non-stdlib
imports are Crow Memory's own core modules, resolved from the directory this
file lives in (repo `core/` or `<CROW_HOME>/core`).

Hooks run on the host agent's hot path, so they never fail the host: malformed
stdin, an unreadable state file or an unavailable database all degrade to
"nothing to inject" with exit code 0.

Exit codes: 0 ok (hooks always), 1 runtime failure, 2 usage error.
Stdout carries machine-readable output only; diagnostics go to stderr.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from crow_db import GRACE_SECONDS, REGISTERS, CrowDB
except ImportError:  # core not installed yet - non-hook commands report it, hooks no-op
    CrowDB = None
    REGISTERS = ()
    GRACE_SECONDS = 3600

try:
    from crow_sanitize import project_slug, scrub_text
except ImportError:
    project_slug = None
    scrub_text = None

try:
    from crow_text import _smart_truncate
except ImportError:
    _smart_truncate = None

HOOK_EVENTS = ("session-start", "pre-invocation", "post-tool")
HOOK_FORMATS = ("agy", "claude", "kimi", "cursor", "text")
ADMIN_ACTIONS = ("diagnostics", "drift", "prompt", "backup", "evolve",
                 "project_info", "delete", "purge")

DEDUP_FILE = ".last_inject.json"
DEDUP_CONVERSATIONS_MAX = 20   # per-conversation dedup entries kept (R2-7)
LEDGER_FILE = ".last_ingest.json"

PROJECT_TOP_K = 3
DETAIL_MAX_CHARS = 240
COMMAND_MAX_CHARS = 300
LEDGER_TTL = 86400

_COMMAND_KEYS = frozenset(
    {"command", "cmd", "commandline", "command_line", "shellcommand", "shell_command", "script"}
)
_EXIT_KEYS = frozenset(
    {
        "exitcode",
        "exit_code",
        "returncode",
        "return_code",
        "exitstatus",
        "exit_status",
        "statuscode",
        "status_code",
    }
)
_ERROR_KEYS = frozenset({"error", "errors", "toolerror", "tool_error", "iserror", "is_error", "exception", "failed"})
_DETAIL_KEYS = frozenset({"stderr", "stdout", "output", "message", "result", "text", "detail", "details"})
_DETAIL_PRIORITY = {"stderr": 0, "output": 1, "stdout": 2, "message": 3, "text": 3, "detail": 3, "details": 3, "result": 4}
_ERROR_PRIORITY = 6

_OK_STATUS = frozenset(
    {"0", "ok", "okay", "success", "succeeded", "successful", "pass", "passed", "completed", "done", "finished"}
)
_FAIL_STATUS = frozenset(
    {
        "1",
        "2",
        "fail",
        "failed",
        "failure",
        "error",
        "errored",
        "nonzero",
        "non-zero",
        "timeout",
        "timedout",
        "killed",
        "crashed",
        "aborted",
    }
)

_BUILD_TEST_WORDS = frozenset(
    {
        "pytest",
        "py.test",
        "unittest",
        "nosetests",
        "tox",
        "nox",
        "jest",
        "vitest",
        "mocha",
        "ava",
        "karma",
        "playwright",
        "cypress",
        "make",
        "gmake",
        "cmake",
        "ninja",
        "msbuild",
        "gradle",
        "gradlew",
        "mvn",
        "maven",
        "ant",
        "bazel",
        "buck",
        "cargo",
        "rustc",
        "dotnet",
        "swift",
        "xcodebuild",
        "npm",
        "pnpm",
        "yarn",
        "npx",
        "bun",
        "corepack",
        "tsc",
        "pyright",
        "mypy",
        "ruff",
        "eslint",
        "flake8",
        "pylint",
        "black",
        "isort",
        "prettier",
        "stylelint",
        "test",
        "tests",
        "build",
        "compile",
        "lint",
        "typecheck",
    }
)


class _UsageError(Exception):
    """Raised for arguments that argparse cannot validate by itself."""


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _configure_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        kwargs = {"encoding": "utf-8", "errors": "replace"}
        if stream is sys.stdout:
            kwargs["newline"] = "\n"
        try:
            reconfigure(**kwargs)
        except (OSError, ValueError):
            pass


def _home() -> Path:
    raw = os.environ.get("CROW_HOME", "").strip()
    if raw:
        return Path(os.path.expanduser(raw))
    return Path.home() / ".crow-memory"


def _open_db():
    if CrowDB is None:
        raise RuntimeError("crow_db is not importable (run the installer or point CROW_HOME at a core install)")
    return CrowDB(_home())


def _close_db(db) -> None:
    try:
        db.close()
    except Exception:
        pass


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _emit(text: str) -> None:
    if not text:
        return
    sys.stdout.write(text)
    sys.stdout.flush()


def _debug_traceback() -> None:
    if os.environ.get("CROW_DEBUG"):
        traceback.print_exc()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    return None


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    if _smart_truncate is not None:
        try:
            return _smart_truncate(flat, limit)
        except Exception:
            pass
    return flat if len(flat) <= limit else flat[: max(1, limit - 3)].rstrip() + "..."


def _read_json_file(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, payload: dict) -> bool:
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _read_stdin_text() -> str:
    try:
        stream = sys.stdin
        if stream is None or stream.isatty():
            return ""
        buffer = getattr(stream, "buffer", None)
        raw = buffer.read() if buffer is not None else stream.read()
    except Exception:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw or ""


def _load_payload() -> dict:
    text = _read_stdin_text().strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_for(payload: dict):
    if project_slug is None:
        return None
    candidates = [payload.get("cwd")]
    paths = payload.get("workspacePaths")
    if isinstance(paths, list) and paths:
        candidates.append(paths[0])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            try:
                slug = project_slug(candidate)
            except Exception:
                return None
            if slug:
                return slug
    return None


def _bias_block(db, query: str, project) -> str:
    try:
        block = db.bias_block(
            query=query,
            domain="all",
            project=project,
            strict_project=False,
            top_k=PROJECT_TOP_K,
        )
    except TypeError:
        block = db.bias_block(query)
    return block.strip() if isinstance(block, str) else ""


def _render_bias(fmt: str, event: str, block: str) -> str:
    if fmt == "agy":
        return _compact({"injectSteps": [{"systemMessage": {"systemMessage": block}}]}) + "\n"
    if fmt == "claude":
        name = "SessionStart" if event == "session-start" else "UserPromptSubmit"
        return _compact({"hookSpecificOutput": {"hookEventName": name, "additionalContext": block}}) + "\n"
    return block + "\n"


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def _should_inject(home: Path, payload: dict, text: str) -> bool:
    if _as_int(payload.get("invocationNum")) == 1:
        return True
    state = _read_json_file(home / DEDUP_FILE)
    conversation = payload.get("conversationId")
    if isinstance(conversation, str) and conversation.strip():
        # per-conversation dedup: a new conversation re-injects even when
        # another conversation already saw this exact prompt (CR-10)
        by_conversation = state.get("conversations")
        if not isinstance(by_conversation, dict):
            return True
        previous = by_conversation.get(conversation.strip())
    else:
        previous = state.get("input_sha256")
    return previous != _sha256(text)


def _record_injection(home: Path, payload: dict, text: str) -> None:
    state = _read_json_file(home / DEDUP_FILE)
    conversations = state.get("conversations")
    if not isinstance(conversations, dict):
        conversations = {}
    digest = _sha256(text)
    conversation = payload.get("conversationId")
    if isinstance(conversation, str) and conversation.strip():
        key = conversation.strip()
        # re-insert so the dict's insertion order stays least-recent-first,
        # then evict the oldest entries (the state file must stay bounded)
        conversations.pop(key, None)
        conversations[key] = digest
        while len(conversations) > DEDUP_CONVERSATIONS_MAX:
            conversations.pop(next(iter(conversations)), None)
    state.update({
        "conversationId": conversation,
        "invocationNum": payload.get("invocationNum"),
        "input_sha256": digest,
        "conversations": conversations,
        "updated_at": time.time(),
    })
    _write_json_file(home / DEDUP_FILE, state)


def _hook_session_start(args) -> int:
    payload = _load_payload()
    db = _open_db()
    try:
        block = _bias_block(db, "", _project_for(payload))
    finally:
        _close_db(db)
    if block:
        _emit(_render_bias(args.format, "session-start", block))
    return 0


def _hook_pre_invocation(args) -> int:
    payload = _load_payload()
    last_input = payload.get("lastUserInput")
    text = last_input if isinstance(last_input, str) else ""
    home = _home()

    if not _should_inject(home, payload, text):
        return 0

    db = _open_db()
    try:
        block = _bias_block(db, text, _project_for(payload))
    finally:
        _close_db(db)

    if not block:
        return 0

    _emit(_render_bias(args.format, "pre-invocation", block))
    _record_injection(home, payload, text)
    return 0


def _hook_post_tool(args) -> int:
    try:
        _auto_ingest_build_result()
    except Exception:
        _debug_traceback()
    if args.format in ("agy", "claude"):
        _emit("{}\n")
    return 0


def _auto_ingest_build_result() -> None:
    payload = _load_payload()
    observation = _read_observation(payload)
    if observation is None:
        return

    command, exit_code, failed, detail = observation
    if failed is None or not _is_build_or_test(command):
        return

    home = _home()
    key = _clip(command, COMMAND_MAX_CHARS)

    if failed:
        suffix = (": " + detail) if detail else ""
        label = exit_code if exit_code is not None else "unknown"
        value = "Build/test failed (exit %s)%s" % (label, suffix)
        polarity = -0.5
    else:
        if _recently_ingested(home, "context", key):
            return
        value = "Build/test succeeded"
        polarity = 1.0

    # hostile build output must not ride into the bank verbatim (SEC-6):
    # scrub noise, flatten newlines, keep the existing 240-char cap
    if scrub_text is not None:
        value = scrub_text(value)
    value = _clip(" ".join((value or "").split()), DETAIL_MAX_CHARS + 60)
    if not value:
        return

    db = _open_db()
    try:
        result = db.ingest(key, value, "context", polarity=polarity)
    finally:
        _close_db(db)

    if isinstance(result, dict) and result.get("status") == "rejected":
        return
    if not failed:
        _mark_ingested(home, "context", key)


def _read_observation(payload: dict):
    signals = _collect_signals(payload)
    command = signals["command"]
    if not command:
        return None
    return command, signals["exit"], _decide_failure(signals), _detail_line(signals)


def _collect_signals(node, acc=None, depth: int = 0):
    if acc is None:
        acc = {"command": None, "exit": None, "status": None, "success": None, "error": False, "detail": []}
    if depth > 4:
        return acc

    if isinstance(node, str):
        stripped = node.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                return acc
            if isinstance(parsed, (dict, list)):
                _collect_signals(parsed, acc, depth + 1)
        return acc

    if isinstance(node, (list, tuple)):
        for item in node[:20]:
            _collect_signals(item, acc, depth + 1)
        return acc

    if not isinstance(node, dict):
        return acc

    for raw_key, value in node.items():
        key = str(raw_key).strip().lower()

        if acc["command"] is None and key in _COMMAND_KEYS and isinstance(value, str) and value.strip():
            acc["command"] = value.strip()
            continue

        if key in _EXIT_KEYS:
            number = _as_int(value)
            if number is not None and acc["exit"] is None:
                acc["exit"] = number
                continue

        if key == "status":
            number = _as_int(value)
            if number is not None:
                if acc["exit"] is None:
                    acc["exit"] = number
                continue
            if isinstance(value, str) and value.strip():
                acc["status"] = value.strip().lower()
                continue

        if key in ("success", "ok", "succeeded"):
            if isinstance(value, bool):
                acc["success"] = value
            else:
                number = _as_int(value)
                if number in (0, 1) and acc["success"] is None:
                    acc["success"] = bool(number)
            continue

        if key in _ERROR_KEYS:
            if _looks_like_error(value):
                acc["error"] = True
                text = _text_of(value)
                if text:
                    acc["detail"].append((_ERROR_PRIORITY, text))
            _collect_signals(value, acc, depth + 1)
            continue

        if key in _DETAIL_KEYS:
            text = _text_of(value)
            if text:
                acc["detail"].append((_DETAIL_PRIORITY.get(key, 5), text))
            _collect_signals(value, acc, depth + 1)
            continue

        _collect_signals(value, acc, depth + 1)

    return acc


def _looks_like_error(value) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (dict, list, tuple)):
        return bool(value)
    return bool(value)


def _text_of(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("stderr", "stdout", "message", "text", "output", "detail"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested
    if isinstance(value, (list, tuple)):
        return "\n".join(item for item in (_text_of(v) for v in value) if item)
    return ""


def _decide_failure(signals):
    if signals["error"]:
        return True
    if signals["exit"] is not None:
        return signals["exit"] != 0
    status = signals["status"]
    if status:
        if status.isdigit():
            return int(status) != 0
        if status in _OK_STATUS:
            return False
        if status in _FAIL_STATUS:
            return True
    if signals["success"] is not None:
        return not signals["success"]
    return None


def _detail_line(signals) -> str:
    for _priority, text in sorted(signals["detail"], key=lambda item: item[0]):
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if lines:
            return _clip(lines[-1], DETAIL_MAX_CHARS)
    return ""


def _is_build_or_test(command: str) -> bool:
    if not command or not command.strip():
        return False
    for token in re.split(r"[^0-9a-z_.\-]+", command.lower()):
        if not token:
            continue
        name = token.replace("\\", "/").rsplit("/", 1)[-1]
        if name.endswith(".exe"):
            name = name[:-4]
        if name in _BUILD_TEST_WORDS:
            return True
        if name.startswith("test") or name.startswith("build"):
            return True
    return False


def _ledger_key(register: str, key: str) -> str:
    return "%s|%s" % (register, _sha256(key)[:16])


def _recently_ingested(home: Path, register: str, key: str) -> bool:
    stamp = _read_json_file(home / LEDGER_FILE).get(_ledger_key(register, key))
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
        return False
    return (time.time() - float(stamp)) < float(GRACE_SECONDS)


def _mark_ingested(home: Path, register: str, key: str) -> None:
    ledger = _read_json_file(home / LEDGER_FILE)
    now = time.time()
    fresh = {
        k: v
        for k, v in ledger.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and now - float(v) < LEDGER_TTL
    }
    fresh[_ledger_key(register, key)] = now
    _write_json_file(home / LEDGER_FILE, fresh)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_recall(args) -> int:
    db = _open_db()
    try:
        result = db.recall(
            query=args.query,
            register=args.register or "all",
            domain=args.domain,
            top_k=args.top_k,
            fmt=args.format,
            project=args.project,
            strict_project=bool(args.strict_project),
            track_stats=not args.no_stats,
        )
    finally:
        _close_db(db)
    _emit(_compact(result) + "\n")
    return 0


def _cmd_ingest(args) -> int:
    db = _open_db()
    try:
        result = db.ingest(
            args.key,
            args.value,
            args.register,
            polarity=args.polarity,
            exit_code=args.exit_code,
            user_edited=bool(args.user_edited),
            project=args.project,
        )
    finally:
        _close_db(db)
    _emit(_compact(result) + "\n")
    return 0


def _cmd_admin(args) -> int:
    try:
        extra = json.loads(args.args or "{}")
    except ValueError as exc:
        raise _UsageError("--args must be valid JSON: %s" % exc) from exc
    if not isinstance(extra, dict):
        raise _UsageError("--args must be a JSON object")

    db = _open_db()
    try:
        result = db.admin(args.action, extra)
    finally:
        _close_db(db)
    _emit(_compact(result) + "\n")
    return 0


def _cmd_migrate(args) -> int:
    from migrate_from_v1 import migrate

    source = args.src_json or str(Path(_HERE).parent / "memory" / "value_bank.json")
    result = migrate(
        src_json=source,
        home=args.home or str(_home()),
        apply=bool(args.apply),
        scrub_junk=not args.keep_junk,
    )
    _emit(_compact(result) + "\n")
    return 0


def _cmd_serve_stdio(_args) -> int:
    from crow_mcp_stdio import main as mcp_main

    return int(mcp_main() or 0)


def _run_hook(args) -> int:
    handlers = {
        "session-start": _hook_session_start,
        "pre-invocation": _hook_pre_invocation,
        "post-tool": _hook_post_tool,
    }
    return handlers[args.event](args)


def _run_command(args) -> int:
    handlers = {
        "recall": _cmd_recall,
        "ingest": _cmd_ingest,
        "admin": _cmd_admin,
        "migrate": _cmd_migrate,
        "serve-stdio": _cmd_serve_stdio,
    }
    return handlers[args.command](args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crow_cli.py",
        description="Crow Memory v2 - serverless synaptic memory CLI and hook adapter.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser("hook", help="lifecycle hook adapter (stdin JSON -> stdout JSON)")
    hook.add_argument("event", choices=HOOK_EVENTS)
    hook.add_argument("--format", choices=HOOK_FORMATS, default="text", dest="format")

    register_choices = tuple(REGISTERS) if REGISTERS else None
    recall_register_choices = ("all",) + register_choices if register_choices else None

    recall = sub.add_parser("recall", help="query the memory bank")
    recall.add_argument("--query", required=True)
    recall.add_argument("--register", default="all", choices=recall_register_choices)
    recall.add_argument("--domain", default="all", choices=("code", "life", "all"))
    recall.add_argument("--top-k", type=int, default=2, dest="top_k")
    recall.add_argument("--format", default="hint", choices=("hint", "bias_block"), dest="format")
    recall.add_argument("--project", default=None)
    recall.add_argument("--strict-project", action="store_true", dest="strict_project")
    recall.add_argument("--no-stats", action="store_true", dest="no_stats")

    ingest = sub.add_parser("ingest", help="store one experience")
    ingest.add_argument("--key", required=True)
    ingest.add_argument("--value", required=True)
    ingest.add_argument("--register", required=True, choices=register_choices)
    ingest.add_argument("--polarity", type=float, default=None)
    ingest.add_argument("--exit-code", type=int, default=None, dest="exit_code")
    ingest.add_argument("--user-edited", action="store_true", dest="user_edited")
    ingest.add_argument("--project", default=None)

    admin = sub.add_parser("admin", help="administrative operations")
    admin.add_argument("--action", required=True, choices=ADMIN_ACTIONS)
    admin.add_argument("--args", default=None, help="action-specific JSON object")

    migrate = sub.add_parser("migrate", help="import a v1 value_bank.json into the v2 database")
    mode = migrate.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", dest="dry_run")
    mode.add_argument("--apply", action="store_true")
    migrate.add_argument("--src-json", default=None, dest="src_json")
    migrate.add_argument("--home", default=None)
    migrate.add_argument("--keep-junk", action="store_true", dest="keep_junk")

    sub.add_parser("serve-stdio", help="serve MCP over newline-delimited JSON-RPC on stdio")
    return parser


def main(argv=None) -> int:
    _configure_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "hook":
        try:
            return _run_hook(args)
        except Exception:
            _debug_traceback()
            return 0

    try:
        return _run_command(args)
    except _UsageError as exc:
        sys.stderr.write("crow_cli.py: %s\n" % exc)
        return 2
    except Exception as exc:
        _emit(_compact({"status": "error", "error": "%s: %s" % (type(exc).__name__, exc)}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
