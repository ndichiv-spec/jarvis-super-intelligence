"""Load Silverwing's sandbox without colliding with other top-level modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "_jarvis_silverwing_sandbox"
_SANDBOX_PATH = Path(__file__).with_name("sandbox.py")


def load_sandbox() -> ModuleType:
    """Return the Silverwing sandbox implementation from this directory."""
    loaded = sys.modules.get(_MODULE_NAME)
    if loaded is not None:
        return loaded

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SANDBOX_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Silverwing sandbox from {_SANDBOX_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    return module
