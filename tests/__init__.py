"""Test package bootstrap helpers."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package in src/ is importable without installing it first.
_SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))
