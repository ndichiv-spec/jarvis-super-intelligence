"""Provider package — delegation shim onto the authoritative provider fabric.

The canonical JARVIS provider fabric lives at ``<workspace>/providers`` (the
repository this project is checked out into). It is the single owner of the
provider registry, routing policy, secret manager, health probing and the
per-provider adapters (``providers.nvidia``, ``providers.openai``, ...).

This file deliberately contains **no provider logic**. It only makes
``import providers`` resolve to that authoritative package, so the repository
and the workspace share one fabric instead of maintaining a second copy that
silently shadows the real adapters.

Resolution is order-independent: it does not rely on ``sys.path`` ordering, the
current working directory, or a prior ``jarvis_runtime.bootstrap_runtime()``
call, because :attr:`__path__` is redirected here at package-import time.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__: list[str] = []

_PACKAGE_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _PACKAGE_DIR.parent.parent

#: Minimum files that identify a directory as the real fabric rather than a stub.
_FABRIC_MARKERS = ("__init__.py", "base.py", "bootstrap.py", "errors.py")


def _resolve_fabric_dir() -> Path | None:
    """Return the authoritative fabric package directory, if one is present."""
    override = os.environ.get("JARVIS_PROVIDER_FABRIC_PATH")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.append(_WORKSPACE_ROOT / "providers")

    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved == _PACKAGE_DIR:
            # Guard against a self-referential path (e.g. the override pointing
            # back at this shim), which would make the package unimportable.
            continue
        if all((resolved / marker).is_file() for marker in _FABRIC_MARKERS):
            return resolved
    return None


_FABRIC_DIR = _resolve_fabric_dir()

if _FABRIC_DIR is None:  # pragma: no cover - misconfigured deployment
    raise ImportError(
        "The authoritative JARVIS provider fabric was not found. Expected it at "
        f"{_WORKSPACE_ROOT / 'providers'!s} (override with "
        "JARVIS_PROVIDER_FABRIC_PATH). This repository intentionally ships no "
        "second copy of the fabric, because a local copy shadows the real "
        "provider adapters and silently disables all provider routing."
    )

# Submodule imports (``providers.base``, ``providers.nvidia``, ...) must resolve
# against the authoritative fabric. The fabric path is placed first so it always
# wins over any module left in this directory.
__path__ = [
    str(_FABRIC_DIR),
    *[entry for entry in __path__ if Path(entry).resolve() != _FABRIC_DIR],
]

# Execute the authoritative package body in this namespace so that the public
# API, ``__all__`` and ``__version__`` are defined in exactly one place.
_FABRIC_INIT = _FABRIC_DIR / "__init__.py"
exec(  # noqa: S102 - deliberate, single-source package delegation
    compile(_FABRIC_INIT.read_text(encoding="utf-8"), str(_FABRIC_INIT), "exec"),
    globals(),
)

#: Legacy alias. Older call sites raised/imported ``ProviderNotAvailableError``;
#: the fabric names this condition ``ProviderUnavailable``.
ProviderNotAvailableError = ProviderUnavailable

if "ProviderNotAvailableError" not in __all__:
    __all__ = [*__all__, "ProviderNotAvailableError"]
