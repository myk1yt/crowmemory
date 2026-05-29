#!/usr/bin/env python3
"""
crow_i18n.py — Crow Memory i18n (Internationalization) Core Module

Provides locale detection, translation lookup, and localized MCP tool definitions.
Uses only the Python standard library — no pip install required.

Public API:
    detect_locale()       -> str
    get_text()            -> str
    get_tool_definitions() -> list[dict]
    get_server_instructions() -> str
    get_prompt_messages() -> dict
    get_installer_messages() -> dict
    get_available_locales() -> list[str]
"""

import json
import locale as _locale
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_I18N_DIR = Path(__file__).parent / "i18n"

SUPPORTED_LOCALES = frozenset({
    "en", "ko", "ja", "zh-cn", "zh-tw",
    "fr", "de", "it", "es", "pt-br", "ru", "tr", "pl", "cs", "hu",
    "nl", "uk", "sv", "th", "vi", "ro", "bg", "el", "hr", "id",
    "ms", "fi", "nb", "da", "sk", "sl", "et", "lv", "lt", "hi", "bn",
})

# ---------------------------------------------------------------------------
# Base tool definitions (hardcoded mirror of crow_mcp_server.py TOOL_DEFINITIONS)
# ---------------------------------------------------------------------------

_BASE_TOOL_DEFINITIONS = [
    {
        "name": "crow_recall",
        "description": (
            "Recall user-specific coding style, bug intuition, architectural "
            "preference, or personal context from the Crow synaptic memory. "
            "Call this BEFORE every response to align with user's inductive bias. "
            "By default (no register, domain=all), queries all 8 registers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language description of the current task."},
                "register": {
                    "type": "string",
                    "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context", "all"],
                    "description": "Which register. Use 'all' to query every register (same as domain=all). Code: style/bug/arch/context. Life: life_pref/life_avoid/life_phil/life_context.",
                },
                "top_k": {"type": "integer", "default": 2, "description": "Number of hints (1-3)."},
                "domain": {
                    "type": "string",
                    "enum": ["code", "life", "all"],
                    "default": "all",
                    "description": "Domain filter shortcut. 'code' = style/bug/arch/context, 'life' = life_pref/life_avoid/life_phil/life_context, 'all' = all 8 registers (default).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "crow_ingest",
        "description": (
            "Ingest a coding experience into Crow's long-term synaptic memory. "
            "Call AFTER build/test results or user explicit feedback."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Abstract description of the situation."},
                "value": {"type": "string", "description": "Code pattern or decision applied."},
                "polarity": {"type": "number", "description": "Reinforcement strength [-2.0, 2.0]."},
                "register": {
                    "type": "string",
                    "enum": ["style", "bug", "arch", "context", "life_pref", "life_avoid", "life_phil", "life_context"],
                },
            },
            "required": ["key", "value", "polarity", "register"],
        },
    },
    {
        "name": "crow_evolve_propose",
        "description": (
            "Analyze recent memory patterns and propose a permanent system prompt mutation. "
            "Returns a suggestion only; human approval is required for adoption."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_confidence": {"type": "number", "default": 0.85},
                "min_occurrences": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "crow_diagnostics",
        "description": "Return diagnostic information about the Crow memory state (register norms, sparsity, update count, value bank size, prompt stats).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "crow_check_drift",
        "description": "Check if recent recalls show signs of memory drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "default": 0.5},
                "min_low_confidence_count": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "crow_ingest_from_build",
        "description": (
            "Auto-determine polarity from build exit code and user edit status, "
            "then ingest the experience. Use this after npm run build completes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Abstract description."},
                "value": {"type": "string", "description": "Code pattern applied."},
                "exit_code": {"type": "integer", "description": "Build exit code (0 = success)."},
                "user_edited": {"type": "boolean", "default": False},
                "register": {"type": "string", "enum": ["style", "bug", "arch", "context"], "default": "arch"},
                "explicit_polarity": {"type": "number", "description": "Override auto-polarity."},
            },
            "required": ["key", "value", "exit_code"],
        },
    },
    {
        "name": "crow_get_user_bias",
        "description": (
            "Generate the [User Bias] block for injection into the system prompt. "
            "Queries all registers and formats hints for prompt prepending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Current task description."},
                "registers": {"type": "array", "items": {"type": "string"}, "description": "Registers to query (default: all)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "crow_manage_prompt",
        "description": (
            "Read, append to, or get statistics about the system_prompt.md file. "
            "Use 'read' to view current prompt, 'append' to adopt an evolved rule, 'stats' for metrics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "append", "stats"]},
                "rule": {"type": "string", "description": "Rule text (required for append action)."},
                "auto_backup": {"type": "boolean", "default": True},
            },
            "required": ["action"],
        },
    },
    {
        "name": "crow_manage_backup",
        "description": (
            "Manage Crow memory backups. Create, rotate, list, or recover from drift."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "rotate", "list", "recover"]},
                "tag": {"type": "string", "default": "daily", "enum": ["daily", "weekly", "manual"]},
                "max_daily": {"type": "integer", "default": 7},
                "max_weekly": {"type": "integer", "default": 4},
            },
            "required": ["action"],
        },
    },
    {
        "name": "crow_project_info",
        "description": "List or create project-isolated Crow memory instances.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create"]},
                "project_name": {"type": "string", "description": "Project name (required for create)."},
            },
            "required": ["action"],
        },
    },
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict] = {}  # locale -> parsed JSON cache
_detected_locale: str | None = None  # session-level locale cache


def _get_argv_json_path() -> Path | None:
    """Return the VS Code argv.json path for the current platform."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
        return Path(base) / "Code" / "User" / "argv.json" if base else None
    elif sys.platform == "darwin":
        home = os.path.expanduser("~")
        return Path(home) / "Library" / "Application Support" / "Code" / "User" / "argv.json"
    else:  # Linux
        home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return Path(home) / "Code" / "User" / "argv.json"


def _strip_json_comments(content: str) -> str:
    """Remove // line comments from JSON content (simple heuristic)."""
    lines = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _parse_vscode_locale() -> str | None:
    """Extract the locale field from VS Code argv.json."""
    path = _get_argv_json_path()
    if path is None or not path.exists():
        return None
    try:
        content = path.read_text("utf-8")
        cleaned = _strip_json_comments(content)
        data = json.loads(cleaned)
        locale_value = data.get("locale")
        if isinstance(locale_value, str) and locale_value.strip():
            return locale_value.strip().lower()
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _parse_system_locale() -> str | None:
    """Extract language code from system locale."""
    try:
        loc = _locale.getdefaultlocale()
        if loc and loc[0]:
            lang = loc[0].lower().replace("_", "-")
            if "-" in lang:
                parts = lang.split("-", 1)
                if len(parts) > 1 and len(parts[1]) == 2:
                    return f"{parts[0]}-{parts[1]}"
                return parts[0]
            return lang
    except Exception:
        pass
    return None


def _canonicalize_locale(raw: str) -> str:
    """Normalize a raw locale string to canonical form."""
    loc = raw.strip().lower().replace("_", "-")
    if loc in SUPPORTED_LOCALES:
        return loc
    if "-" in loc:
        prefix = loc.split("-")[0]
        if prefix == "zh":
            if "hans" in loc:
                return "zh-cn"
            if "hant" in loc:
                return "zh-tw"
            return "zh-cn"
        if prefix == "pt":
            return "pt-br"
        if prefix == "nb" or prefix == "nn":
            return "nb"
        if prefix in SUPPORTED_LOCALES:
            return prefix
    return "en"


def _load_locale(locale_code: str) -> dict:
    """Load i18n/{locale}.json into memory (cached)."""
    if locale_code in _CACHE:
        return _CACHE[locale_code]
    path = _I18N_DIR / f"{locale_code}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    _CACHE[locale_code] = data
    return data


def _resolve_key(data: dict, key: str) -> str | None:
    """Resolve a dot-separated nested key in a dictionary."""
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current if isinstance(current, str) else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_locale() -> str:
    """
    Detect the current VS Code locale.

    Fallback chain: argv.json -> locale.getdefaultlocale() -> 'en'
    Result is cached for the duration of the session (first call only triggers I/O).
    """
    global _detected_locale
    if _detected_locale is not None:
        return _detected_locale

    raw = _parse_vscode_locale()
    if not raw:
        raw = _parse_system_locale()
    if not raw:
        raw = "en"

    _detected_locale = _canonicalize_locale(raw)
    return _detected_locale


def get_text(key: str, locale: str | None = None, **fmt_kwargs: Any) -> str:
    """
    Retrieve a translated string for the given key and locale.

    Fallback chain:
        1. Requested locale JSON
        2. en.json
        3. Raw key string

    Supports str.format() via **fmt_kwargs, e.g. get_text("errors.unknown_tool", name="crow_xyz").
    """
    loc = locale or detect_locale()

    # 1. Try requested locale
    data = _load_locale(loc)
    value = _resolve_key(data, key)
    if value is not None:
        return value.format(**fmt_kwargs) if fmt_kwargs else value

    # 2. Fall back to en
    if loc != "en":
        en_data = _load_locale("en")
        value = _resolve_key(en_data, key)
        if value is not None:
            return value.format(**fmt_kwargs) if fmt_kwargs else value

    # 3. Return raw key
    return key.format(**fmt_kwargs) if fmt_kwargs else key


def get_tool_definitions(locale: str | None = None) -> list[dict]:
    """
    Return MCP Tool definitions with descriptions translated to the given locale.

    Tool names and enum values are NEVER translated (MCP protocol contract).
    Returns a deep copy so callers cannot mutate the base definitions.
    """
    loc = locale or detect_locale()
    tools = deepcopy(_BASE_TOOL_DEFINITIONS)

    for tool in tools:
        name = tool["name"]
        desc = get_text(f"tools.{name}.description", loc)
        if desc:
            tool["description"] = desc

        props = tool.get("inputSchema", {}).get("properties", {})
        for param_name, param_def in props.items():
            param_desc = get_text(f"tools.{name}.parameters.{param_name}", loc)
            if param_desc:
                param_def["description"] = param_desc

    return tools


def get_server_instructions(locale: str | None = None) -> str:
    """Return the MCP server instructions string for the given locale."""
    return get_text("server.instructions", locale)


def get_prompt_messages(locale: str | None = None) -> dict:
    """
    Return localized MCP Prompt messages.

    Returns:
        dict: {
            "crow_memory_bias": {"description": str, "body": str},
            "crow_evolved_rules": {"description": str, "body": str},
        }
    """
    loc = locale or detect_locale()
    return {
        "crow_memory_bias": {
            "description": get_text("server.prompts.crow_memory_bias.description", loc),
            "body": get_text("server.prompts.crow_memory_bias.body_template", loc),
        },
        "crow_evolved_rules": {
            "description": get_text("server.prompts.crow_evolved_rules.description", loc),
            "body": get_text("server.prompts.crow_evolved_rules.body_template", loc),
        },
    }


def get_installer_messages(locale: str | None = None) -> dict:
    """
    Return localized installer messages for install.py / install.ps1.

    Returns:
        dict: All keys under "installer.*" flattened to top-level snake_case keys,
              plus "next_steps" as a list.
    """
    loc = locale or detect_locale()

    def _get(key: str) -> str:
        return get_text(key, loc)

    return {
        "banner_title": _get("installer.banner_title"),
        "step_1_install_deps": _get("installer.step_1_install_deps"),
        "step_2_init_crow": _get("installer.step_2_init_crow"),
        "step_3_vscode_tasks": _get("installer.step_3_vscode_tasks"),
        "step_4_custom_mode": _get("installer.step_4_custom_mode"),
        "step_5_start_server": _get("installer.step_5_start_server"),
        "step_done": _get("installer.step_done"),
        "complete_title": _get("installer.complete_title"),
        "sse_running": _get("installer.sse_running"),
        "next_steps_label": _get("installer.next_steps_label"),
        "next_steps": [
            _get("installer.next_step_1"),
            _get("installer.next_step_2"),
            _get("installer.next_step_3"),
            _get("installer.next_step_4"),
        ],
    }


def get_available_locales() -> list[str]:
    """
    Return a sorted list of all locales for which a translation file exists.

    Scans the i18n/ directory for *.json files.
    """
    available: list[str] = []
    if not _I18N_DIR.is_dir():
        return ["en"]  # at minimum, en should work by get_text fallback
    try:
        for f in _I18N_DIR.iterdir():
            if f.suffix == ".json" and f.stem in SUPPORTED_LOCALES:
                available.append(f.stem)
    except OSError:
        return ["en"]
    return sorted(available) if available else ["en"]
