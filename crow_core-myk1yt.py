#!/usr/bin/env python3
"""
crow_core-myk1yt.py — DEPRECATED thin re-export shim (AD-8.1, Batch E).

The `-myk1yt` code copies are user-instance branding artifacts, not a functional
fork (AD-8 audit: this file differed from crow_core.py only in a docstring
version string). The canonical implementation now lives in `crow_core.py`;
this module simply re-exports it so any external reference to the
`crow_core-myk1yt.py` filename (direct execution, runpy.run_path, or
importlib on the hyphenated path) keeps working.

NOTE: the hyphenated filename is NOT importable via a normal `import`
statement (`import crow_core-myk1yt` is a syntax error). It is usable via:
  - direct execution:   python crow_core-myk1yt.py
  - runpy:             runpy.run_path("crow_core-myk1yt.py")
  - importlib:         importlib.import_module / SourceFileLoader
This shim has no import-time side effects beyond importing crow_core
(constants + class definitions only; CrowMemory instances are not created
here, no lock is taken, no server starts).

Migration: update any references to point at crow_core.py directly.
"""

__deprecated_shim__ = True

from crow_core import *  # noqa: F401,F403

# Explicit re-exports of the public API surface (crow_core defines no __all__,
# so `import *` above skips underscore names; the names below are the ones
# external code and tests reference — keep in sync with crow_core.py).
from crow_core import (  # noqa: F401
    DIM,
    EMBED_DIM,
    MAX_SV,
    VALUE_BANK_MAX,
    SIM_CUTOFF,
    CROSS_PROJECT_CUTOFF,
    PROJECT_BOOST,
    NEG_DAMPEN,
    NEG_DAMPEN_DEFAULT,
    NEG_DAMPEN_BY_REGISTER,
    REGISTERS,
    DOMAINS,
    CODE_REGISTERS,
    LIFE_REGISTERS,
    CrowMemory,
)


if __name__ == "__main__":
    # Direct execution of the shim: prove the re-export pipeline works and exit.
    print("crow_core-myk1yt.py is a deprecated re-export shim (AD-8.1).")
    print(f"Delegates to crow_core.py (CrowMemory={CrowMemory.__module__}, "
          f"REGISTERS={len(REGISTERS)} registers, SIM_CUTOFF={SIM_CUTOFF}).")
    print("Update references to import crow_core directly.")
