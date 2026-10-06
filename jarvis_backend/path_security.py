"""Confine user-selected dataset and checkpoint paths to approved roots."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOTS = (
    PROJECT_ROOT / "Dataset",
    PROJECT_ROOT / "jarvis_data",
    PROJECT_ROOT / "jarvis_uploads",
    PROJECT_ROOT / "models",
)


def resolve_confined_path(raw_path: str, *, must_be_directory: bool = False) -> Path:
    """Resolve an existing path and reject traversal or symlink escapes."""
    if not raw_path or not raw_path.strip():
        raise ValueError("A path is required")
    candidate = Path(raw_path).expanduser().resolve(strict=True)
    if must_be_directory and not candidate.is_dir():
        raise ValueError("The selected checkpoint path is not a directory")
    if not must_be_directory and not candidate.is_file():
        raise ValueError("The selected data path is not a file")

    configured_roots = os.environ.get("JARVIS_ALLOWED_DATA_ROOTS", "")
    roots = list(DEFAULT_DATA_ROOTS)
    if configured_roots:
        roots.extend(Path(root).expanduser() for root in configured_roots.split(os.pathsep) if root)

    for root in roots:
        try:
            resolved_root = root.resolve(strict=True)
        except OSError:
            continue
        if candidate == resolved_root or resolved_root in candidate.parents:
            return candidate
    raise ValueError("The selected path is outside configured JARVIS data roots")
