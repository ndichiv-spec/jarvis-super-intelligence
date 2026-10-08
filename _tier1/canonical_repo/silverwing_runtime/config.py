"""Runtime configuration.

Everything is configured through environment variables (never hard-coded
secrets, per platform policy).

Environment variables
--------------------
``SILVERWING_MODEL_CACHE``   - directory for downloaded/verified weights
                               (default ``./.sw_cache``)
``SILVERWING_MODEL_REPO``    - directory of model repository (manifests)
                               (default ``./silverwing-models``)
``SILVERWING_REGISTRY_PATH`` - JSON file backing the registry
                               (default ``./silverwing_registry.json``)
``SILVERWING_STORAGE_BACKEND``- default storage backend for downloads
                               (``local``, ``huggingface``, ``s3``, ``gcs``,
                               ``azure``; default ``local``)
``SILVERWING_API_KEY``       - optional shared bearer token for the API
``SILVERWING_DEVICE``        - torch device hint (``auto``, ``cuda``, ``cpu``)
``SILVERWING_BACKEND``       - inference backend (``torch`` default, ``echo``
                               for tests/development)
``SILVERWING_WARMUP_PROMPT`` - warmup prompt used at startup healthy check
``SILVERWING_REQUEST_TIMEOUT``- per-request generation timeout (seconds)
``SILVERWING_MAX_TOKENS``    - default max new tokens cap (default 2048)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class RuntimeConfig:
    model_cache_dir: Path = field(
        default_factory=lambda: Path(_env("SILVERWING_MODEL_CACHE", ".sw_cache"))
    )
    model_repo: Path = field(
        default_factory=lambda: Path(_env("SILVERWING_MODEL_REPO", "silverwing-models"))
    )
    registry_path: Path = field(
        default_factory=lambda: Path(_env("SILVERWING_REGISTRY_PATH", "silverwing_registry.json"))
    )
    storage_backend: str = field(
        default_factory=lambda: _env("SILVERWING_STORAGE_BACKEND", "local")
    )
    api_key: str = field(default_factory=lambda: _env("SILVERWING_API_KEY", ""))
    device: str = field(default_factory=lambda: _env("SILVERWING_DEVICE", "auto"))
    backend: str = field(default_factory=lambda: _env("SILVERWING_BACKEND", "torch"))
    warmup_prompt: str = field(
        default_factory=lambda: _env("SILVERWING_WARMUP_PROMPT", "The capital of France is")
    )
    request_timeout: float = field(
        default_factory=lambda: float(_env("SILVERWING_REQUEST_TIMEOUT", "120"))
    )
    default_max_tokens: int = field(
        default_factory=lambda: int(_env("SILVERWING_MAX_TOKENS", "2048"))
    )
    allow_path_traversal: bool = False  # always False; storage URIs are scoped

    @property
    def is_debug(self) -> bool:
        return _env("SILVERWING_DEBUG", "0") == "1"

    def ensure_dirs(self) -> None:
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_repo.mkdir(parents=True, exist_ok=True)
