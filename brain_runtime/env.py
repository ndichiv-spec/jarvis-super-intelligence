"""Canonical environment loader for the JARVIS Brain runtime (spec Part Q).

Centralizes *all* env reads so the codebase stops scattering ``os.getenv``
calls with ad-hoc aliases.  The canonical name always wins; each canonical
name may carry a stack of legacy/alias names that are consulted in order.

Canonical names and their alias stack (first set value wins, trailing blanks
ignored):

* ``NVIDIA_API_KEY`` -> ``NVIDIA_API_KEY`` | ``JARVIS_NVIDIA_API_KEY``
* ``HUGGINGFACE_API_KEY`` -> ``HUGGINGFACE_API_KEY`` | ``HF_TOKEN`` |
  ``JARVIS_HF_TOKEN``
* ``JARVIS_BRAIN_API_KEY`` -> ``JARVIS_BRAIN_API_KEY``
* ``JARVIS_BRAIN_REMOTE_API_KEY`` -> ``JARVIS_BRAIN_REMOTE_API_KEY``

``redact`` is the single helper used to render a secret for *logs/metrics*
only: it never appears in an API response.  Secrets are never logged by name
with their value; only a masked prefix/suffix is emitted server-side.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

# Mapping of canonical env name -> ordered alias list (canonical first).
_ALIASES: dict[str, tuple[str, ...]] = {
    "NVIDIA_API_KEY": ("NVIDIA_API_KEY", "JARVIS_NVIDIA_API_KEY"),
    "HUGGINGFACE_API_KEY": ("HUGGINGFACE_API_KEY", "HF_TOKEN", "JARVIS_HF_TOKEN"),
    "JARVIS_BRAIN_API_KEY": ("JARVIS_BRAIN_API_KEY",),
    "JARVIS_BRAIN_REMOTE_API_KEY": ("JARVIS_BRAIN_REMOTE_API_KEY",),
    "JARVIS_OPENAI_API_KEY": ("JARVIS_OPENAI_API_KEY", "OPENAI_API_KEY"),
}


def get_env(name: str, default: str = "") -> str:
    """Return the canonical-or-alias value for ``name``, stripped of blanks.

    ``name`` may be a canonical name (resolved through its alias stack) or a
    plain env var name.  Returns ``default`` when no value is set (or the only
    value is blank).
    """
    candidates: tuple[str, ...] = _ALIASES.get(name, (name,))
    for key in candidates:
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()
    return default


def get_bool(name: str, default: bool = False) -> bool:
    """Boolean env helper: ``1``/``true``/``yes``/``on`` -> True."""
    val = get_env(name)
    if not val:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def get_int(name: str, default: int) -> int:
    val = get_env(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_float(name: str, default: float) -> float:
    val = get_env(name)
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def aliases_for(name: str) -> tuple[str, ...]:
    """Return the alias stack consulted for ``name``."""
    return _ALIASES.get(name, (name,))


def redact(value: str | None) -> str:
    """Render a secret for *server-side logs only*.

    Never call this when building an API response — the secret value must
    never reach a client.  Output shape: ``abc...xy`` (or ``<none>`` /
    ``****`` for short values), matching the existing BrainRemoteBackend mask.
    """
    if not value:
        return "<none>"
    if len(value) <= 6:
        return "****"
    return value[:3] + "..." + value[-2:]


# --------------------------------------------------------------------------- #
# Canonical .env loader (spec Part Q / Part 21)
# --------------------------------------------------------------------------- #
# The brain runtime must be self-sufficient: ``python -m brain_runtime.server``
# reads ``.env`` from the repository root so the process never diverges from
# the platform (which ``jarvis_api.py`` loads the same way).  This populates
# ``os.environ`` with *setdefault* semantics only — a real environment value
# ALWAYS wins, and ``get_env`` is unchanged (os.environ-only) so the test suite
# is unaffected (it never calls ``main()``).  No secret values are returned or
# logged; only key presence is ever surfaced to callers.
_DOTEENV_SEARCH = (
    lambda: Path(".").resolve() / ".env",
    lambda: Path(__file__).resolve().parents[1] / ".env",
    lambda: Path(__file__).resolve().parents[2] / ".env",
)


def _find_dotenv() -> Path | None:
    """Locate the first existing ``.env`` along the canonical search path."""
    for candidate in _DOTEENV_SEARCH:
        try:
            p = candidate()
        except Exception:  # noqa: BLE001 - best effort
            continue
        if p and p.is_file():
            return p
    return None


def _parse_dotenv(path: Path) -> list[tuple[str, str]]:
    """Parse a ``.env`` file into (key, value) pairs (quote-aware, blank-safe)."""
    pairs: list[tuple[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"').strip()
                # Inline comments are only stripped for unquoted values.
                if value and value != line.split("=", 1)[1].strip():
                    value = value
                if key and value:
                    pairs.append((key, value))
    except OSError:
        pass
    return pairs


def load_env_file(path: str | Path | None = None) -> int:
    """Apply ``.env`` into ``os.environ`` (setdefault only; never clobbers).

    Idempotent and side-effect-free w.r.t. ``get_env``: it only mutates
    ``os.environ`` so subsequent ``get_env`` reads (which consult
    ``os.environ`` first) pick up the canonical file.  Returns the number of
    variables applied.  Used by the brain runtime entrypoint so the runtime is
    self-sufficient and consistent with the platform.
    """
    target = Path(path) if path else (_find_dotenv() or Path("/nonexistent/.env"))
    applied = 0
    for key, value in _parse_dotenv(target):
        os.environ.setdefault(key, value)
        applied += 1
    return applied


__all__ = [
    "get_env",
    "get_bool",
    "get_int",
    "get_float",
    "redact",
    "aliases_for",
    "load_env_file",
]
