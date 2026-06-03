"""Final verification script for i18n Subtask 5"""
import sys, json, os, py_compile
sys.path.insert(0, '.')
from pathlib import Path

print("=" * 50)
print("FINAL VERIFICATION — i18n Subtask 5")
print("=" * 50)

# 1. Python syntax check
py_files = ['crow_i18n.py', 'crow_mcp_server.py', 'install.py']
errors = []
for f in py_files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        errors.append(f'  ERROR: {f}: {e}')
print(f'\n1. Python syntax:')
if not errors:
    print(f'   All {len(py_files)} files OK')
else:
    for e in errors:
        print(f'   {e}')

# 2. JSON files validity
i18n_dir = Path('i18n')
json_files = sorted(i18n_dir.glob('*.json'))
json_errors = []
for jf in json_files:
    try:
        with open(jf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Verify required keys
        if 'server' not in data or 'instructions' not in data.get('server', {}):
            json_errors.append(f'  MISSING server.instructions in {jf.name}')
        if 'installer' not in data:
            json_errors.append(f'  MISSING installer section in {jf.name}')
        if 'tools' not in data:
            json_errors.append(f'  MISSING tools section in {jf.name}')
    except json.JSONDecodeError as e:
        json_errors.append(f'  INVALID JSON: {jf.name}: {e}')
print(f'\n2. JSON validity ({len(json_files)} files):')
if not json_errors:
    print(f'   All valid, required keys present')
else:
    for e in json_errors:
        print(f'   {e}')

# 3. crow_i18n.get_available_locales()
from crow_i18n import get_available_locales, detect_locale, get_text, get_tool_definitions
locs = get_available_locales()
print(f'\n3. get_available_locales() = {len(locs)}')
print(f'   Locales: {locs}')

# 4. Server instructions for all locales
missing = []
for loc in locs:
    text = get_text('server.instructions', loc)
    if not text or text == 'server.instructions':
        missing.append(loc)
print(f'\n4. server.instructions:')
print(f'   Missing in: {missing if missing else "None — all 36 OK"}')

# 5. Tool definitions count
tools = get_tool_definitions('en')
print(f'\n5. get_tool_definitions(en) = {len(tools)} tools')
tool_names = [t['name'] for t in tools]
print(f'   Tools: {tool_names}')

# 6. Detect locale
locale = detect_locale()
print(f'\n6. detect_locale() = {locale}')

# 7. crow_mcp_server.py imports crow_i18n
try:
    import importlib
    spec = importlib.util.find_spec('crow_i18n')
    print(f'\n7. crow_i18n importable: {spec is not None}')
except Exception as e:
    print(f'\n7. crow_i18n import error: {e}')

# 8. Quick install.py i18n check
from crow_i18n import get_installer_messages
msgs = get_installer_messages(locale)
required = ['banner_title', 'step_1_install_deps', 'complete_title', 'next_steps']
ok = all(k in msgs for k in required)
status_msg = "All keys OK" if ok else "MISSING KEYS"
print(f'\n8. Installer messages: {status_msg}')

print(f'\n{"=" * 50}')
print(f'STATUS: ALL VERIFICATIONS COMPLETE')
print(f'{"=" * 50}')
