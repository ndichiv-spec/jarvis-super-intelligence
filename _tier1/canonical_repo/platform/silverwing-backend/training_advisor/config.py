"""Configuration for the Gemini-powered Training Advisor.

All configuration is read from environment variables. ``GEMINI_API_KEY`` is
**never** hard-coded anywhere in the codebase: it is read exclusively from the
environment (or a secrets manager in production) at runtime.

The provider abstraction is:

    TrainingAdvisor  (orchestrator)
     ├── GeminiProvider   (Google ``google-genai`` SDK, external LLM)
     └── LocalProvider    (deterministic, dependency-free fallback)

``google.genai`` is imported *lazily* inside the Gemini provider so that the
package and the backend import cleanly even when the optional SDK (or API key)
is absent.  In that case ``GeminiProvider.is_available()`` returns ``False``
and the orchestrator transparently falls back to ``LocalProvider``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _import_gemini_available() -> bool:
    """Lazily probe the ``google-genai`` SDK without forcing a hard dependency."""
    try:
        import google.genai  # noqa: F401
        return True
    except Exception:
        return False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AdvisorConfig:
    """Immutable, environment-sourced configuration.

    Constructed with no arguments (``AdvisorConfig()``) reads all values from
    the environment at construction time; ``get_config()`` is a kept-for-compat
    alias.
    """

    enabled: bool = field(default_factory=lambda: _env_bool("GEMINI_ENABLED", True))
    api_key: str | None = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash")
    timeout_seconds: float = field(default_factory=lambda: _env_float("GEMINI_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _env_int("GEMINI_MAX_RETRIES", 3))
    base_backoff_seconds: float = field(default_factory=lambda: _env_float("GEMINI_BASE_BACKOFF", 0.5))
    max_backoff_seconds: float = field(default_factory=lambda: _env_float("GEMINI_MAX_BACKOFF", 8.0))
    advisory_interval_seconds: float = field(default_factory=lambda: _env_float("GEMINI_ADVISORY_INTERVAL", 60.0))
    analysis_threshold: int = field(default_factory=lambda: _env_int("GEMINI_ANALYSIS_THRESHOLD", 5))
    cache_ttl_seconds: float = field(default_factory=lambda: _env_float("GEMINI_CACHE_TTL", 60.0))
    max_history: int = field(default_factory=lambda: _env_int("GEMINI_MAX_HISTORY", 1000))
    autorun: bool = field(default_factory=lambda: _env_bool("SILVERWING_ADVISOR_AUTORUN", False))
    prompt_version: str = field(default_factory=lambda: os.environ.get("GEMINI_PROMPT_VERSION", "1.0"))
    gemini_available: bool = field(default_factory=lambda: _import_gemini_available())

    @property
    def gemini_authorized(self) -> bool:
        """True only when the Gemini provider can actually be used."""
        return self.enabled and bool(self.api_key) and self.gemini_available


def get_config() -> AdvisorConfig:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    try:
        import google.genai  # noqa: F401
        gemini_available = True
    except Exception:
        gemini_available = False

    return AdvisorConfig()
