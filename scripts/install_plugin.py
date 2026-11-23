#!/usr/bin/env python
"""Crow Memory v1.5.0 plugin installer.

Copies repo ``core/`` into the data home, creates ``bin/`` shims (plus
``.cmd`` wrappers on Windows so hooks work when ``python`` is not on PATH in
spawned shells), deploys adapter payloads to tool-specific config locations,
and optionally migrates v1 memory data via ``core.migrate_from_v1``.

Stdlib only. Idempotent. Non-destructive: every file it overwrites is backed
up next to it as ``<name>.bak.<timestamp>``. It never deletes anything and
never touches v1 repo files. Deploy targets that hold user content are merged
instead of replaced: ``~/.cursor/hooks.json`` keeps foreign events and foreign
entries, and ``~/.codex/AGENTS.md`` / ``~/.zoo/AGENTS.md`` get a marked block
(the same mechanism as the kimi ``config.toml`` block), so hand-written rules
survive. Migration is fingerprint-guarded through
``<home>/.migrated_v1.json``: re-running the installer does not re-ingest an
already migrated bank.

Usage:
    python scripts/install_plugin.py [--tools all|TOOL[,TOOL...]] [--home PATH]
                                     [--no-migrate] [--force-migrate]
                                     [--src-json PATH]

Environment:
    CROW_HOME        data home when --home is not given (default ~/.crow-memory)
    CROW_DEPLOY_HOME root for adapter deploy targets (default: user home).
                     Override intended for tests; production installs leave it unset.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.5.0"
TOOLS = ("generic", "antigravity", "kimi-code", "claude-code",
         "cursor", "cline", "codex", "zoo-code")

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = REPO_ROOT / "adapters"

TOML_MARK_BEGIN = "# >>> crow-memory hooks v2 >>>"
TOML_MARK_END = "# <<< crow-memory hooks v2 <<<"
MD_MARK_BEGIN = "<!-- >>> crow-memory v2 >>> -->"
MD_MARK_END = "<!-- <<< crow-memory v2 <<< -->"


# ---------------------------------------------------------------------------
# basics
# ---------------------------------------------------------------------------

def timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def resolve_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("CROW_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".crow-memory").resolve()


def deploy_root() -> Path:
    override = os.environ.get("CROW_DEPLOY_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home()


def rewrite_tokens(text: str, home: Path, escape: bool) -> str:
    """Replace <CROW_HOME> with the real home path.

    escape=True doubles backslashes for JSON / TOML double-quoted strings.
    """
    h = str(home)
    if escape:
        h = h.replace("\\", "\\\\")
    return text.replace("<CROW_HOME>", h)


def _backup(target: Path, log: list[str]) -> None:
    """Copy target to a timestamped .bak, never clobbering an existing one.

    The timestamp has one-second resolution, and two writes to the same target
    can land inside one second, so a counter suffix keeps every backup (R2-10).
    """
    base = target.with_name(target.name + ".bak." + timestamp())
    bak = base
    n = 1
    while bak.exists():
        bak = base.with_name(base.name + "." + str(n))
        n += 1
    shutil.copy2(target, bak)
    log.append(f"  backup    {target} -> {target.parent / bak.name}")


def _atomic_write_text(target: Path, content: str) -> None:
    """Write content via a temp file in the same directory + os.replace.

    A crash or a mid-write OSError can then never leave a truncated config or
    a half-appended marked block behind: readers see either the old file or
    the complete new one. An existing file keeps its permission bits, and a
    symlinked target keeps being written through the link (the previous
    behavior) instead of being replaced by a regular file.
    """
    if target.is_symlink():
        try:
            target = target.resolve()
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = target.stat().st_mode & 0o777
    except OSError:
        mode = None
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent),
                                   prefix="." + target.name + ".",
                                   suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_text_deploy(target: Path, content: str, log: list[str]) -> str:
    """Write content to target, backing up a differing existing file.

    Returns 'created' | 'updated' | 'unchanged'.
    """
    existed = target.exists()
    if existed:
        try:
            # newline-agnostic compare: .cmd shims carry \r\n but text-mode
            # reads normalize them, which would otherwise diff every run.
            if target.read_text(encoding="utf-8").replace("\r\n", "\n") == \
                    content.replace("\r\n", "\n"):
                return "unchanged"
        except (OSError, UnicodeDecodeError):
            pass
        _backup(target, log)
    _atomic_write_text(target, content)
    return "updated" if existed else "created"


def deploy_tree(src: Path, dst: Path, home: Path, log: list[str],
                only_py: bool = False, rewrite: bool = True) -> None:
    """Copy every file under src to dst, rewriting <CROW_HOME> tokens.

    JSON/TOML payloads get escaped backslashes; markdown/plain get raw paths.
    ``rewrite=False`` is used for the core/ copy: runtime modules must keep
    their literal ``<CROW_HOME>`` docstring placeholders untouched.
    """
    if not src.is_dir():
        log.append(f"  SKIP      template dir missing: {src}")
        return
    for p in sorted(src.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts:
            continue
        if only_py and p.suffix != ".py":
            continue
        rel = p.relative_to(src)
        target = dst / rel
        escape = p.suffix.lower() in (".json", ".toml", ".cmd")
        text = p.read_text(encoding="utf-8")
        content = rewrite_tokens(text, home, escape) if rewrite else text
        status = write_text_deploy(target, content, log)
        log.append(f"  {status:9s} {target}")


def merge_mcp_server(target: Path, snippet: Path, server_key: str,
                     home: Path, log: list[str]) -> None:
    """Merge one mcpServers entry from snippet into an existing JSON file."""
    entry = json.loads(
        rewrite_tokens(snippet.read_text(encoding="utf-8"), home, True)
    )["mcpServers"][server_key]
    data: dict = {}
    existed = target.exists()
    if existed:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.append(f"  WARN      {target} is not valid UTF-8 JSON; "
                       "recreating it")
            _backup(target, log)
            data = {}
            existed = False
        else:
            if not isinstance(data, dict):
                # a JSON array/string at the top level: merge into nothing
                log.append(f"  WARN      {target} top-level JSON is not an "
                           "object; recreating it")
                data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        if servers is not None:
            log.append(f"  WARN      {target}: \"mcpServers\" is not an "
                       "object; replacing it")
        servers = {}
        data["mcpServers"] = servers
    if servers.get(server_key) == entry:
        log.append(f"  unchanged {target} (mcpServers.{server_key})")
        return
    if existed:
        _backup(target, log)
    servers[server_key] = entry
    _atomic_write_text(target, json.dumps(data, indent=2,
                                         ensure_ascii=False) + "\n")
    log.append(f"  {'updated' if existed else 'created':9s} {target} "
               f"(mcpServers.{server_key})")


CROW_HOOK_MARKER = "crow_cli.py"


def _is_crow_hook_entry(entry) -> bool:
    """True for a hook entry that points at Crow Memory's own shim."""
    if not isinstance(entry, dict):
        return False
    return CROW_HOOK_MARKER in str(entry.get("command", ""))


def merge_cursor_hooks(target: Path, snippet: Path, home: Path,
                       log: list[str]) -> None:
    """Merge Crow's hook events into ~/.cursor/hooks.json, never wholesale.

    The user's other event keys survive, and inside a shared event list only
    entries pointing at crow_cli.py are replaced in place, so the user's own
    sessionStart/beforeShellExecution guards stay and a re-run is idempotent.
    An existing file that is not a JSON object is backed up and rewritten from
    the adapter template, with an explicit warning that nothing could be
    merged.
    """
    template = json.loads(
        rewrite_tokens(snippet.read_text(encoding="utf-8"), home, True))
    crow_hooks = template.get("hooks") or {}
    fresh = json.dumps(template, indent=2, ensure_ascii=False) + "\n"
    if not target.exists():
        _atomic_write_text(target, fresh)
        log.append(f"  created   {target} (hooks)")
        return
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("top-level JSON is not an object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        log.append(f"  WARN      {target} is not a JSON object; it was backed "
                   "up and rewritten from the adapter template. Content that "
                   "is not valid JSON could not be merged.")
        _backup(target, log)
        _atomic_write_text(target, fresh)
        log.append(f"  updated   {target} (template rewritten)")
        return

    merged = dict(loaded)
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        if hooks is not None:
            log.append(f"  WARN      {target}: \"hooks\" is not an object; "
                       "replacing it")
        hooks = {}
    for event, entries in crow_hooks.items():
        current = hooks.get(event)
        if current is not None and not isinstance(current, list):
            log.append(f"  WARN      {target}: hooks.{event} is not an array; "
                       "replacing it")
            current = []
        out, placed = [], False
        for item in current or []:
            if _is_crow_hook_entry(item):
                if not placed:  # first crow slot keeps its position
                    out.extend(entries)
                    placed = True
            else:
                out.append(item)
        if not placed:
            out.extend(entries)
        hooks[event] = out
    merged["hooks"] = hooks
    for key, value in template.items():  # e.g. "version", only when unset
        merged.setdefault(key, value)
    new = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if new == target.read_text(encoding="utf-8"):
        log.append(f"  unchanged {target}")
        return
    _backup(target, log)
    _atomic_write_text(target, new)
    log.append(f"  updated   {target} (hooks merged)")


def upsert_marked_block(target: Path, body: str, log: list[str],
                        begin: str, end: str) -> None:
    """Insert or replace a marked block inside a config file (idempotent).

    Existing-file shapes handled: both markers present (replace between them,
    keep the surrounding text); begin marker without the end marker (the file
    was truncated inside our block, so replace from the lone begin marker to
    EOF and repair it instead of appending a second copy); a lone end marker,
    including one that appears before the begin marker (stripped, then the
    block is appended, so user content that contains a stray end marker can
    never abort the run); neither marker (append). A file that is not UTF-8 is
    left untouched with a warning: rewriting it would corrupt the user's
    encoding. Writes are atomic.
    """
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    existed = target.exists()
    if existed:
        try:
            old = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            log.append(f"  WARN      {target} is not UTF-8 text; skipped, no "
                       "marked block was written (convert it to UTF-8 first)")
            return
        begin_at = old.find(begin)
        end_at = old.find(end)
        stripped = False
        # Drop end markers that have no begin marker before them: a stray or
        # out-of-order end marker must not crash the deployer (R2-4).
        while end_at != -1 and (begin_at == -1 or end_at < begin_at):
            old = old[:end_at] + old[end_at + len(end):]
            stripped = True
            begin_at = old.find(begin)
            end_at = old.find(end)
        if stripped:
            log.append(f"  WARN      {target} had a stray end marker; it was "
                       "stripped before the block was written")
        if begin_at != -1 and end_at != -1:
            # canonical form: exactly one trailing newline, so re-runs compare
            # equal instead of accumulating newlines after the end marker.
            new = (old[:begin_at] + block + old[end_at + len(end):]
                   ).rstrip("\n") + "\n"
            if new == old and not stripped:
                log.append(f"  unchanged {target}")
                return
            _backup(target, log)
            _atomic_write_text(target, new)
            log.append(f"  updated   {target} (marked block)")
            return
        if begin_at != -1:
            new = (old[:begin_at] + block).rstrip("\n") + "\n"
            _backup(target, log)
            _atomic_write_text(target, new)
            log.append(f"  updated   {target} (repaired truncated block)")
            return
        new = old.rstrip("\n") + "\n\n" + block
        _backup(target, log)
        _atomic_write_text(target, new)
        log.append(f"  appended  {target}")
        return
    _atomic_write_text(target, block)
    log.append(f"  created   {target}")


# ---------------------------------------------------------------------------
# bin shims
# ---------------------------------------------------------------------------

# Hooks are short-lived processes, so interpreter start-up is on the critical
# path: -S skips site/`.pth` processing and user-site, -E ignores PYTHON*
# environment variables. Both leave the stdlib (sqlite3, json, argparse, ...)
# fully importable, which is all Crow Memory needs. The installer probes this
# once and omits the flags if the local interpreter cannot run with them.
SHIM_FLAGS: tuple[str, ...] = ("-S", "-E")


def probe_shim_flags(log: list[str]) -> tuple[str, ...]:
    """-S -E when `python` can still import the stdlib Crow Memory uses."""
    for exe in ("python", "py", sys.executable):
        try:
            proc = subprocess.run(
                [exe, *SHIM_FLAGS, "-c",
                 "import sqlite3, json, argparse, hashlib"],
                capture_output=True, timeout=60,
                # no console flash when the installer was launched from a GUI
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return SHIM_FLAGS
    log.append("  NOTE      python -S -E unusable here; bin/*.cmd shims omit "
               "the flags (PYTHONDONTWRITEBYTECODE=1 still applies)")
    return ()


def _py_shim(mod_py: str) -> str:
    return (
        "#!/usr/bin/env python\n"
        '"""Crow Memory shim: re-exec core/%s with core/ importable.\n'
        "\n"
        "Runs the real module in this process on purpose: the interpreter is\n"
        "already up, so re-execing under -S -E costs more (an extra process\n"
        "creation) than it saves. Launch this file with the flags instead:\n"
        "    python -S -E -B <CROW_HOME>/bin/%s ...\n"
        '"""\n'
        "import os\n"
        "import runpy\n"
        "import sys\n"
        "\n"
        "_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
        "_CORE = os.path.join(_HOME, \"core\")\n"
        "if _CORE not in sys.path:\n"
        "    sys.path.insert(0, _CORE)\n"
        "runpy.run_path(os.path.join(_CORE, %r), run_name=\"__main__\")\n"
    ) % (mod_py, mod_py, mod_py)


def _home_expr_for_cmd(home: Path) -> str:
    """%USERPROFILE% form for the default Windows home, literal path otherwise."""
    if os.name == "nt":
        try:
            if home.resolve() == (Path.home() / ".crow-memory").resolve():
                return r"%USERPROFILE%\.crow-memory"
        except OSError:
            pass
    return str(home)


def _cmd_shim(home_expr: str, mod: str, flags: tuple[str, ...] = ()) -> str:
    script = home_expr.rstrip("\\/") + "\\core\\" + mod + ".py"
    flag_s = "".join(f" {f}" for f in flags)
    return (
        "@echo off\r\n"
        "set \"PYTHONDONTWRITEBYTECODE=1\"\r\n"
        f'python{flag_s} "{script}" %*\r\n'
        "if %errorlevel%==9009 "
        f'py{flag_s} "{script}" %*\r\n'
    )


def create_bin(home: Path, log: list[str]) -> None:
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    flags = probe_shim_flags(log) if os.name == "nt" else ()
    for mod in ("crow_cli", "crow_mcp_stdio"):
        shim = bin_dir / (mod + ".py")
        status = write_text_deploy(shim, _py_shim(mod + ".py"), log)
        log.append(f"  {status:9s} {shim}")
        if os.name == "nt":
            cmd = bin_dir / (mod + ".cmd")
            status = write_text_deploy(
                cmd, _cmd_shim(_home_expr_for_cmd(home), mod, flags), log)
            log.append(f"  {status:9s} {cmd}")


# ---------------------------------------------------------------------------
# migration (best effort, non-fatal)
# ---------------------------------------------------------------------------

def run_migration(home: Path, src_json: Path, log: list[str],
                  force: bool = False) -> None:
    core_dir = home / "core"
    if not (core_dir / "migrate_from_v1.py").exists():
        log.append(f"migrate   SKIP ({core_dir / 'migrate_from_v1.py'} not found yet)")
        return
    if not src_json.exists():
        log.append(f"migrate   SKIP (source {src_json} not found)")
        return
    sys.path.insert(0, str(core_dir))
    try:
        import migrate_from_v1
        result = migrate_from_v1.migrate(
            src_json=str(src_json), home=str(home), apply=True,
            src_prompt=str(REPO_ROOT / "memory" / "system_prompt.md"),
            force_migrate=force)
        log.append("migrate   " + json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # best effort: never fatal
        log.append(f"migrate   FAILED (non-fatal): {exc!r}")
    finally:
        try:
            sys.path.remove(str(core_dir))
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# per-tool deployers (all best effort)
# ---------------------------------------------------------------------------

def deploy_generic(home: Path, root: Path, log: list[str]) -> None:
    log.append("generic   no auto-deploy location; copy "
               f"{ADAPTERS / 'generic' / 'AGENTS.md'} into your project root "
               "or paste its rules into your global agent instructions.")


def deploy_antigravity(home: Path, root: Path, log: list[str]) -> None:
    dst = root / ".gemini" / "config" / "plugins" / "crow-memory"
    log.append(f"antigravity -> {dst}")
    deploy_tree(ADAPTERS / "antigravity", dst, home, log)
    legacy = root / ".gemini" / "config" / "plugins" / "crow_memory"
    if legacy.is_dir() and legacy.resolve() != dst.resolve():
        log.append(f"  NOTE      legacy plugin dir {legacy} still exists; remove it "
                   "so Antigravity does not load two copies of Crow Memory.")


def deploy_kimi_code(home: Path, root: Path, log: list[str]) -> None:
    kdir = root / ".kimi-code"
    log.append(f"kimi-code   -> {kdir}")
    merge_mcp_server(kdir / "mcp.json",
                     ADAPTERS / "kimi-code" / "mcp.json.snippet",
                     "crow-memory", home, log)
    body = rewrite_tokens(
        (ADAPTERS / "kimi-code" / "hooks.toml.snippet").read_text(encoding="utf-8"),
        home, escape=True)
    upsert_marked_block(kdir / "config.toml", body, log,
                        TOML_MARK_BEGIN, TOML_MARK_END)
    deploy_tree(ADAPTERS / "kimi-code" / "skills", kdir / "skills", home, log)


def deploy_claude_code(home: Path, root: Path, log: list[str]) -> None:
    dst = root / ".claude" / "plugins" / "crow-memory"
    log.append(f"claude-code -> {dst}")
    deploy_tree(ADAPTERS / "claude-code", dst, home, log)


def deploy_cursor(home: Path, root: Path, log: list[str]) -> None:
    cdir = root / ".cursor"
    log.append(f"cursor      -> {cdir}")
    merge_cursor_hooks(cdir / "hooks.json", ADAPTERS / "cursor" / "hooks.json",
                       home, log)
    merge_mcp_server(cdir / "mcp.json", ADAPTERS / "cursor" / "mcp.json",
                     "crow-memory", home, log)
    deploy_tree(ADAPTERS / "cursor" / "rules", cdir / "rules", home, log)


def deploy_cline(home: Path, root: Path, log: list[str]) -> None:
    log.append("cline       -> ~/.clinerules (rules) + manual MCP step")
    body = rewrite_tokens(
        (ADAPTERS / "cline" / "crow-memory.md").read_text(encoding="utf-8"),
        home, escape=False)
    upsert_marked_block(root / ".clinerules", body, log,
                        MD_MARK_BEGIN, MD_MARK_END)
    cline_mcp = root / ".cline" / "mcp_settings.json"
    if cline_mcp.exists():
        merge_mcp_server(cline_mcp, ADAPTERS / "cline" / "mcp.json.snippet",
                         "crow-memory", home, log)
    else:
        log.append(f"  SKIP      {cline_mcp} not found; add the crow-memory "
                   "server from adapters/cline/mcp.json.snippet via the Cline "
                   "MCP settings UI (rewriting <CROW_HOME> first).")


def _deploy_agents_md(root: Path, sub: str, home: Path, log: list[str]) -> None:
    """Upsert the Crow rules as a marked block; the user's own rules stay."""
    target = root / sub / "AGENTS.md"
    body = rewrite_tokens(
        (ADAPTERS / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
        home, escape=False)
    upsert_marked_block(target, body, log, MD_MARK_BEGIN, MD_MARK_END)


def deploy_codex(home: Path, root: Path, log: list[str]) -> None:
    log.append("codex       -> ~/.codex/AGENTS.md (marked block; existing "
               "rules are preserved)")
    _deploy_agents_md(root, ".codex", home, log)


def deploy_zoo_code(home: Path, root: Path, log: list[str]) -> None:
    log.append("zoo-code    -> ~/.zoo/AGENTS.md (marked block; existing rules "
               "are preserved). Copy to a project root for per-project memory")
    _deploy_agents_md(root, ".zoo", home, log)


DEPLOYERS = {
    "generic": deploy_generic,
    "antigravity": deploy_antigravity,
    "kimi-code": deploy_kimi_code,
    "claude-code": deploy_claude_code,
    "cursor": deploy_cursor,
    "cline": deploy_cline,
    "codex": deploy_codex,
    "zoo-code": deploy_zoo_code,
}

NEXT_STEPS = {
    "generic": ["Copy adapters/generic/AGENTS.md to your project root (or paste "
                "into your global agent config). No restart needed."],
    "antigravity": ["Validate: agy plugin validate "
                    "~/.gemini/config/plugins/crow-memory --strict",
                    "Restart Antigravity to activate the hooks."],
    "kimi-code": ["Restart Kimi Code; hooks and the stdio MCP server load at startup.",
                  "If the old v1 crow_memory HTTP(:9021)/SSE(:9020) entry is still "
                  "in mcp.json, remove it (the installer replaced it with stdio)."],
    "claude-code": ["Restart Claude Code; the plugin loads from "
                    "~/.claude/plugins/crow-memory."],
    "cursor": ["Restart Cursor; it reads ~/.cursor/hooks.json and ~/.cursor/mcp.json."],
    "cline": ["Restart your IDE so Cline reloads ~/.clinerules and MCP settings."],
    "codex": ["Codex reads ~/.codex/AGENTS.md automatically on next run."],
    "zoo-code": ["Zoo Code reads AGENTS.md; copy it into a project root for "
                 "per-project memory."],
}
COMMON_NEXT_STEPS = [
    "If Crow Memory v1.5 autostart is still registered (Task Scheduler "
    "'CrowMemoryAuto' or start_crow_sse.bat), disable it: v2 needs no server, "
    "port, or scheduler.",
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="install_plugin.py",
        description=f"Crow Memory v{VERSION} plugin installer (stdlib only, "
                    "idempotent, non-destructive).",
        epilog="Tools: all | " + ", ".join(TOOLS))
    ap.add_argument("--tools", default="all",
                    help="comma-separated tool list or 'all' (default: all)")
    ap.add_argument("--home", default=None,
                    help="data home (default: env CROW_HOME or ~/.crow-memory)")
    ap.add_argument("--no-migrate", action="store_true",
                    help="skip v1 -> v2 memory migration")
    ap.add_argument("--force-migrate", action="store_true",
                    help="re-apply the v1 migration even when "
                         "<home>/.migrated_v1.json matches the source bank "
                         "(default: skip, so a re-run cannot re-weight rows)")
    ap.add_argument("--src-json", default=None,
                    help="v1 value_bank.json path (default: <repo>/memory/value_bank.json)")
    args = ap.parse_args(argv)

    raw = args.tools.strip().lower()
    tools = list(TOOLS) if raw == "all" else [t.strip() for t in raw.split(",") if t.strip()]
    unknown = [t for t in tools if t not in TOOLS]
    if unknown:
        ap.error(f"unknown tool(s): {', '.join(unknown)} "
                 f"(choose from: all, {', '.join(TOOLS)})")

    home = resolve_home(args.home)
    root = deploy_root()
    log: list[str] = []

    print(f"Crow Memory v{VERSION} installer")
    print(f"  repo   : {REPO_ROOT}")
    print(f"  home   : {home}")
    print(f"  deploy : {root}")
    print(f"  tools  : {', '.join(tools)}")

    # 1. core copy
    src_core = REPO_ROOT / "core"
    if src_core.is_dir():
        log.append(f"core: {src_core} -> {home / 'core'}")
        deploy_tree(src_core, home / "core", home, log, only_py=True,
                    rewrite=False)
    else:
        log.append(f"core: SKIP ({src_core} not found; rerun after core/ exists)")

    # 2. bin shims (+ .cmd on Windows)
    create_bin(home, log)

    # 3. adapter payloads (per-target isolation: one bad user config must not
    #    abort the remaining tools, and the install still exits 0)
    failed: list[str] = []
    for tool in tools:
        try:
            DEPLOYERS[tool](home, root, log)
        except Exception as exc:  # noqa: BLE001 - deliberate per-target guard
            failed.append(tool)
            log.append(f"{tool}: FAILED (non-fatal): {exc!r}")

    # 4. migration (unless --no-migrate)
    if args.no_migrate:
        log.append("migrate: skipped (--no-migrate)")
    else:
        src_json = (Path(args.src_json).expanduser().resolve() if args.src_json
                    else REPO_ROOT / "memory" / "value_bank.json")
        run_migration(home, src_json, log, force=args.force_migrate)

    for line in log:
        print("  " + line)

    if failed:
        ok = len(tools) - len(failed)
        print(f"\nPartial install: {ok}/{len(tools)} deploy targets ok; "
              f"failed: {', '.join(failed)} (see FAILED lines above). "
              "Everything else was deployed.")

    # 5. next steps
    print("\nNext steps:")
    for tool in tools:
        for step in NEXT_STEPS[tool]:
            print(f"  [{tool}] {step}")
    for step in COMMON_NEXT_STEPS:
        print(f"  [all] {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
