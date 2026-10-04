"""Path bootstrap for the lightweight notebooks.

Resolves `scripts/lakehouse.py` from the repo root regardless of where
Jupyter / Python was launched from.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    _HERE = Path(__file__).resolve().parent
except Exception:
    _HERE = Path.cwd()

_DOCKER = Path("/workspace/scripts")
_LOCAL = _HERE / "scripts"
if not _LOCAL.exists():
    _LOCAL = _HERE.parent / "scripts"

_TARGET = _DOCKER if _DOCKER.exists() else _LOCAL
if str(_TARGET) not in sys.path:
    sys.path.insert(0, str(_TARGET))
