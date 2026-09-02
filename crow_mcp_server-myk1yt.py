#!/usr/bin/env python3
"""
crow_mcp_server-myk1yt.py — DEPRECATED thin re-export shim (AD-8.1, Batch E).

The `-myk1yt` code copies are user-instance branding artifacts, not a functional
fork (AD-8 audit: this file was byte-identical to crow_mcp_server.py before the
Batch C 10->3 tool consolidation). The canonical server now lives in
`crow_mcp_server.py`; this module re-exports it so any external reference to
the `crow_mcp_server-myk1yt.py` filename keeps working.

NOTE: the hyphenated filename is NOT importable via a normal `import`
statement. It is usable via:
  - direct execution:   python crow_mcp_server-myk1yt.py [args...]
  - runpy:             runpy.run_path("crow_mcp_server-myk1yt.py")
  - importlib:         importlib.import_module / SourceFileLoader
Direct execution delegates argv, CROW_STATE_TAG, and the full CLI surface
(--state/--transport/--port/--http-port/--host/--ready-file) to the canonical
server's main() via runpy.run_module. IMPORTING this file has no side effects
(no server start, no lock, no CrowMemory instance).

Migration: update any references to point at crow_mcp_server.py directly.
"""

__deprecated_shim__ = True

from crow_mcp_server import *  # noqa: F401,F403

# Explicit re-exports of the public server surface (crow_mcp_server defines
# no __all__, so `import *` skips underscore names; the admin dispatch
# handlers are also re-exported because external tooling and tests may
# reference them — keep in sync with crow_mcp_server.py).
from crow_mcp_server import (  # noqa: F401
    DEFAULT_STATE_PATH,
    resolve_state_path,
    create_server,
    main,
    _recall,
    _ingest,
    _admin,
    _evolve,
    _diagnostics,
    _drift,
    _manage_prompt,
    _manage_backup,
    _project_info,
    _ok,
    _error,
    _write_ready_file,
    _remove_ready_file,
)


if __name__ == "__main__":
    # Delegate the full invocation to the canonical server. runpy.run_module
    # with alter_sys=False keeps this file's __name__ == "__main__" out of
    # sys.modules and reuses crow_mcp_server's own __main__ handling (Windows
    # UTF-8 reconfigure + selector event loop policy + asyncio.run(main())).
    # argv passes through untouched, so --help and every transport flag work.
    import runpy

    runpy.run_module("crow_mcp_server", run_name="__main__", alter_sys=False)
