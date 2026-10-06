"""Load Docker-mounted *_FILE secrets before service modules read settings."""

from __future__ import annotations

import os
from pathlib import Path


def read_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\r\n")
    return None


def load_file_secrets() -> None:
    """Populate conventional environment settings from mounted secret files."""
    for file_setting, path in tuple(os.environ.items()):
        if not file_setting.endswith("_FILE") or not path.startswith("/run/secrets/"):
            continue
        value = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
        setting = file_setting[:-5]
        if not os.environ.get(setting):
            os.environ[setting] = value
