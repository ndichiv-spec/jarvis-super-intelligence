"""JARVIS Brain runtime configuration.

Mirrors ``silverwing_runtime.config.RuntimeConfig`` but for the dedicated Brain
runtime on :8011. Everything is configured through environment variables;
secrets are never hard-coded here (spec section 5 / §22).

Environment variables
---------------------
``JARVIS_BRAIN_HOST``           bind host (default ``127.0.0.1`` — localhost only)
``JARVIS_BRAIN_PORT``           bind port (default ``8011``)
``JARVIS_BRAIN_API_KEY``        bearer token used to authenticate inbound
                                requests. Resolved onto the runtime process by
                                ``start_brain.py`` from the secret vault; never
                                hard-coded.
``JARVIS_BRAIN_MODEL``          designated model id (Base or SFT variant)
``JARVIS_BRAIN_MODEL_REPO``     model repository (manifests)
``JARVIS_BRAIN_MODEL_CACHE``    weight cache for downloaded/verified models
``JARVIS_BRAIN_BACKEND``        ``transformers`` (default), ``remote``, or ``stub`` (dev)
``JARVIS_BRAIN_DEVICE``         torch device hint (``auto``, ``cuda``, ``cpu``)
``JARVIS_BRAIN_TIMEOUT``        per-request generation timeout (seconds)
``JARVIS_BRAIN_MAX_TOKENS``     default max-new-tokens cap
``JARVIS_BRAIN_LOCAL_FILES_ONLY`` ``1`` forces the transformers backend to use only
                                the local cache (no HF download). Used by the test
                                suite so ``TransformersBackend.load()`` can be shown
                                to fail fast + offline without pulling 8 GB of
                                shards. Production (GPU host) leaves this unset.
``JARVIS_BRAIN_WARMUP_PROMPT``  startup warmup prompt
``JARVIS_BRAIN_DEBUG``          ``1`` enables debug logging

Remote backend variables (used when ``JARVIS_BRAIN_BACKEND=remote``):
``JARVIS_BRAIN_REMOTE_ENDPOINT``  upstream OpenAI-compatible inference URL
                                 (e.g. https://<inference-host>/v1).  The Brain
                                 runtime forwards chat/generate requests here;
                                 weights are never downloaded locally.
``JARVIS_BRAIN_REMOTE_API_KEY``  credential sent to the remote provider as
                                 ``Authorization: Bearer <remote_api_key>``.
                                 Distinct from ``JARVIS_BRAIN_API_KEY``;
                                 never exposed via the Brain API.
``JARVIS_BRAIN_REMOTE_TIMEOUT``  per-request timeout for remote inference
                                 (seconds, default 120).
``JARVIS_BRAIN_REMOTE_RETRIES``  bounded retries for transient upstream failures
                                 (404/429/5xx/timeouts; default 2) so a
                                 cold-starting provider does not flap health.
``JARVIS_BRAIN_REMOTE_MODEL``    model identifier passed to the remote provider
                                 (defaults to ``JARVIS_BRAIN_MODEL``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Canonical env loader (spec Part Q).  All reads route through ``brain_runtime.env``
# so alias resolution (e.g. ``HUGGINGFACE_API_KEY`` == ``HF_TOKEN``) is centralized
# and no scattered ``os.getenv`` calls leak provider credentials into a model
# context elsewhere.
from brain_runtime.env import get_env as _get_env, get_bool as _get_bool, redact as _redact  # noqa: F401

# Re-exported so downstream modules import canonical readers from one place.
__all__ = [
    "BrainConfig",
    "get_env",
    "get_bool",
    "redact",
]


def get_env(name: str, default: str = "") -> str:
    """Canonical env read (see :mod:`brain_runtime.env` for the alias table)."""
    return _get_env(name, default)


def get_bool(name: str, default: bool = False) -> bool:
    return _get_bool(name, default)


def redact(value: str | None) -> str:
    """Mask a secret for *server-side logs only*; never place in an API response."""
    return _redact(value)


def _env(name: str, default: str = "") -> str:
    """Legacy reader retained for internal config defaults; routes through the
    canonical loader so alias-aware names resolve consistently."""
    return _get_env(name, default)


# Brain model ids are immutable identities; the SFT candidate must NEVER
# overwrite the Base lineage entry (spec section 20). See model_registry.
_DEFAULT_MODEL = "jarvis-brain-qwen3-4b-v1"

# Live-verified NVIDIA NIM chat default, used only when the remote backend
# points at an NVIDIA-hosted endpoint and no explicit model override exists.
_NVIDIA_DEFAULT_REMOTE_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
_NVIDIA_HOSTS = ("integrate.api.nvidia.com", "nvcf.nvidia.com", "nim.nvidia.com")


def _is_nvidia_endpoint(endpoint: str) -> bool:
    ep = (endpoint or "").lower()
    return any(host in ep for host in _NVIDIA_HOSTS)


@dataclass(frozen=True)
class BrainConfig:
    """Runtime configuration for the JARVIS Brain service (port 8011)."""

    host: str = field(default_factory=lambda: _env("JARVIS_BRAIN_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("JARVIS_BRAIN_PORT", "8011")))
    api_key: str = field(default_factory=lambda: _env("JARVIS_BRAIN_API_KEY", ""))
    model: str = field(default_factory=lambda: _env("JARVIS_BRAIN_MODEL", _DEFAULT_MODEL))
    model_repo: Path = field(
        default_factory=lambda: Path(_env("JARVIS_BRAIN_MODEL_REPO", "F:/AI/silverwing-models"))
    )
    model_cache: Path = field(
        default_factory=lambda: Path(_env("JARVIS_BRAIN_MODEL_CACHE", "F:/AI/.sw_cache"))
    )
    backend: str = field(default_factory=lambda: _env("JARVIS_BRAIN_BACKEND", "transformers"))
    device: str = field(default_factory=lambda: _env("JARVIS_BRAIN_DEVICE", "auto"))
    request_timeout: float = field(
        default_factory=lambda: float(_env("JARVIS_BRAIN_TIMEOUT", "600"))
    )
    default_max_tokens: int = field(
        default_factory=lambda: int(_env("JARVIS_BRAIN_MAX_TOKENS", "8192"))
    )
    warmup_prompt: str = field(
        default_factory=lambda: _env("JARVIS_BRAIN_WARMUP_PROMPT", "The capital of France is")
    )
    local_files_only: bool = field(
        default_factory=lambda: _env("JARVIS_BRAIN_LOCAL_FILES_ONLY", "0") == "1"
    )

    # -- Remote backend configuration (JARVIS_BRAIN_BACKEND=remote) ----------
    # JARVIS_BRAIN_REMOTE_ENDPOINT is the upstream inference provider URL
    # (e.g. a Hugging Face Inference Endpoint).  JARVIS_BRAIN_ENDPOINT is the
    # local Brain runtime URL (127.0.0.1:8011) used by the platform gateway.
    remote_endpoint: str = field(
        default_factory=lambda: _env("JARVIS_BRAIN_REMOTE_ENDPOINT", "").rstrip("/")
    )
    remote_api_key: str = field(
        default_factory=lambda: _env("JARVIS_BRAIN_REMOTE_API_KEY", "")
    )
    remote_timeout: float = field(
        default_factory=lambda: float(_env("JARVIS_BRAIN_REMOTE_TIMEOUT", "120"))
    )
    remote_retries: int = field(
        default_factory=lambda: int(_env("JARVIS_BRAIN_REMOTE_RETRIES", "2"))
    )
    remote_model: str = field(
        default_factory=lambda: _env("JARVIS_BRAIN_REMOTE_MODEL", "").strip()
        or (
            _env("JARVIS_NVIDIA_MODEL", _NVIDIA_DEFAULT_REMOTE_MODEL)
            if _is_nvidia_endpoint(_env("JARVIS_BRAIN_REMOTE_ENDPOINT", ""))
            else _env("JARVIS_BRAIN_MODEL", _DEFAULT_MODEL)
        )
    )

    @property
    def remote_provider(self) -> str:
        """Provider label for the configured remote endpoint (never fabricated)."""
        if _is_nvidia_endpoint(self.remote_endpoint):
            return "nvidia"
        return "hf-inference"

    @property
    def is_debug(self) -> bool:
        return _env("JARVIS_BRAIN_DEBUG", "0") == "1"

    @property
    def backend_type(self) -> str:
        """Normalized backend selector.

        Returns one of: ``local`` (transformers/torch), ``remote`` (generic
        OpenAI-compatible endpoint), ``nvidia`` (NVIDIA NIM/NVCF), ``huggingface``
        (a Hugging Face Inference Endpoint), or ``stub`` (dev).  ``nvidia`` and
        ``huggingface`` are *remote* backends with provider-specific defaults
        (spec Part D/E); ``is_remote`` is True for all of them.
        """
        b = self.backend.lower().strip()
        if b in ("transformers", "local", "torch"):
            return "local"
        if b in ("nvidia",):
            return "nvidia"
        if b in ("huggingface",):
            return "huggingface"
        if b in ("remote", "hf", "http"):
            return "remote"
        if b in ("stub", "echo", "dev"):
            return "stub"
        return "local"

    @property
    def is_local(self) -> bool:
        return self.backend_type == "local"

    @property
    def is_remote(self) -> bool:
        """True for any remote (network) backend: generic remote, nvidia, huggingface."""
        return self.backend_type in ("remote", "nvidia", "huggingface")

    @property
    def is_stub(self) -> bool:
        """True only when the explicitly-labeled dev stub is selected."""
        return self.backend_type == "stub"

    @property
    def is_nvidia(self) -> bool:
        """True when the Brain runtime is configured to use an NVIDIA inference path."""
        return self.backend_type == "nvidia" or (
            self.backend_type == "remote" and self.remote_provider == "nvidia"
        )

    @property
    def is_huggingface(self) -> bool:
        """True when the Brain runtime is configured to use a Hugging Face path."""
        return self.backend_type == "huggingface" or (
            self.backend_type == "remote" and self.remote_provider == "hf-inference"
        )

    # -- Provider-specific config (spec Part D/E) --------------------------
    # These resolve credentials through the canonical env loader so the
    # ``HUGGINGFACE_API_KEY`` / ``HF_TOKEN`` alias is honoured here too.
    @property
    def nvidia_endpoint(self) -> str:
        return (_env("JARVIS_NVIDIA_ENDPOINT", "https://integrate.api.nvidia.com/v1")).rstrip("/")

    @property
    def nvidia_api_key(self) -> str:
        return get_env("NVIDIA_API_KEY", "")

    @property
    def nvidia_model(self) -> str:
        return _env("JARVIS_NVIDIA_MODEL", _NVIDIA_DEFAULT_REMOTE_MODEL)

    @property
    def huggingface_endpoint(self) -> str:
        return (_env("JARVIS_HF_INFERENCE_ENDPOINT", "")).rstrip("/")

    @property
    def huggingface_api_key(self) -> str:
        # Canonical alias: HUGGINGFACE_API_KEY == HF_TOKEN == JARVIS_HF_TOKEN
        return get_env("HUGGINGFACE_API_KEY", "")

    @property
    def huggingface_model(self) -> str:
        m = _env("JARVIS_HF_MODEL", "").strip()
        return m or self.model

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    def ensure_dirs(self) -> None:
        self.model_cache.mkdir(parents=True, exist_ok=True)
        self.model_repo.mkdir(parents=True, exist_ok=True)
