"""Shared import-path bootstrap for the canonical platform runtime."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
SILVERWING_BACKEND_ROOT = PROJECT_ROOT / "silverwing-backend"


def ensure_import_paths() -> None:
    """Register the platform and integrated Silverwing source roots once."""
    for path in (PROJECT_ROOT, WORKSPACE_ROOT, SILVERWING_BACKEND_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def bootstrap_runtime() -> None:
    """Prepare canonical package imports without creating runtime services."""
    ensure_import_paths()
