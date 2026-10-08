"""Live integration tests for NVIDIA NIM (spec §36).

These hit the real ``https://integrate.api.nvidia.com/v1`` endpoint and are
skipped whenever no NVIDIA credential is present (``NVIDIA_API_KEY`` or
``JARVIS_NVIDIA_API_KEY`` in ``F:\\AI\\.env`` or the process environment).
They verify, with the real service:

* discovery — ``/v1/models`` is reachable and the documented default model
  exists on the live catalog;
* connection — a tiny real chat completion returns a non-empty answer from a
  live-verified model.

No stub is accepted as success (spec §37): a response is only green when the
real NVIDIA endpoint produced it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _load_nvidia_key() -> str:
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("JARVIS_NVIDIA_API_KEY") or ""
    if key:
        return key.strip()
    env_file = _WORKSPACE_ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        if k.strip() in ("NVIDIA_API_KEY", "JARVIS_NVIDIA_API_KEY") and v.strip():
            return v.strip()
    return ""


NVIDIA_KEY = _load_nvidia_key()
pytestmark = [
    pytest.mark.skipif(
        not NVIDIA_KEY,
        reason="live NVIDIA test: no NVIDIA_API_KEY/JARVIS_NVIDIA_API_KEY present",
    )
]

from providers.base import Message, ProviderRequest  # noqa: E402
from providers.nvidia.client import NvidiaAdapter  # noqa: E402
from providers.nvidia.config import NvidiaConfig  # noqa: E402
from providers.nvidia.models import NVIDIA_DEFAULT_MODEL, NVIDIA_MODELS  # noqa: E402
from providers.secrets import SecretManager  # noqa: E402

_CONFIG = NvidiaConfig(
    api_key=NVIDIA_KEY,
    endpoint="https://integrate.api.nvidia.com/v1",
)


def _adapter() -> NvidiaAdapter:
    return NvidiaAdapter(config=_CONFIG, secrets=SecretManager(env={}))


class TestNvidiaLiveDiscovery:
    def test_models_endpoint_reachable_and_default_present(self):
        adapter = _adapter()
        models = adapter.list_models(refresh=True)
        ids = [m.model_id for m in models]
        # The live catalog is the source of truth: we must see real discovery
        # (the hosted endpoint advertises ~80 models), not a baseline fallback.
        assert len(ids) > len(NVIDIA_MODELS), (
            "live /v1/models did NOT drive discovery (silently fell back to baseline?)"
        )
        assert NVIDIA_DEFAULT_MODEL in ids, (
            f"documented default {NVIDIA_DEFAULT_MODEL!r} missing from live catalog"
        )

    def test_health_reports_healthy_with_models(self):
        from providers.health import HealthStatus

        adapter = _adapter()
        health = adapter.health(force=True)
        assert health.status is HealthStatus.HEALTHY
        assert health.models_found and health.models_found > 0
        assert health.provider == "nvidia"


class TestNvidiaLiveConnection:
    def test_real_chat_completion_returns_answer(self):
        adapter = _adapter()
        request = ProviderRequest(
            messages=[Message.user("Respond with exactly: JARVIS NVIDIA CONNECTION OK.")],
            model=NVIDIA_DEFAULT_MODEL,
            max_tokens=32,
            temperature=0.0,
        )
        response = adapter.chat(request)
        assert response.provider == "nvidia"
        assert response.model == NVIDIA_DEFAULT_MODEL
        assert response.text.strip(), "live NVIDIA completion returned empty text"
        assert response.latency_ms is not None and response.latency_ms >= 0