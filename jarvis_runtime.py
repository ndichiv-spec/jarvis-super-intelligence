"""Canonical runtime paths and environment bootstrap for JARVIS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
SILVERWING_BACKEND_ROOT = PROJECT_ROOT / "silverwing-backend"

_FALLBACK_DEFAULTS = {
    "SILVERWING_MODEL": "silverwing-120m-base-v1",
    "SILVERWING_TIMEOUT": "300",
    "SILVERWING_BACKEND": "torch",
    "SILVERWING_PORT": "8010",
    "JARVIS_BRAIN_MODEL": "jarvis-brain-qwen3-4b-sft-v1",
}


def ensure_import_paths() -> None:
    for path in (WORKSPACE_ROOT, PROJECT_ROOT, SILVERWING_BACKEND_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def load_environment() -> None:
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(WORKSPACE_ROOT / ".env")

    try:
        import _env
    except ImportError:
        for key, value in _FALLBACK_DEFAULTS.items():
            os.environ.setdefault(key, value)
    else:
        _env.apply()


def bootstrap_runtime() -> None:
    ensure_import_paths()
    load_environment()
