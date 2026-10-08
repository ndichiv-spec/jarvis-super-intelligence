import pytest

from jarvis_backend.gateway import ProviderGateway
from jarvis_backend.routers import ai, health


@pytest.mark.asyncio
async def test_readiness_accepts_cloud_provider_without_brain(monkeypatch):
    async def fake_probe_brain(self, timeout=15.0):
        return {"configured": True, "healthy": False, "detail": "offline"}

    async def fake_catalog():
        return {
            "providers": [
                {
                    "provider": "google",
                    "available": True,
                    "authorized": True,
                    "inference_verified": True,
                    "model": "gemini-2.5-flash",
                }
            ]
        }

    async def fake_silverwing():
        return {"configured": True, "reachable": False, "endpoint": "http://127.0.0.1:8010"}

    monkeypatch.setattr(ProviderGateway, "probe_brain", fake_probe_brain)
    monkeypatch.setattr(ai, "_provider_catalog", fake_catalog)
    monkeypatch.setattr(health, "_probe_silverwing", fake_silverwing)

    result = await health.health_ready()

    assert result["status"] == "ready"
    assert result["brain"]["healthy"] is False
    assert result["providers"] == [
        {"provider": "google", "model": "gemini-2.5-flash"}
    ]


@pytest.mark.asyncio
async def test_silverwing_reachability_alone_is_not_readiness(monkeypatch):
    async def fake_probe_brain(self, timeout=15.0):
        return {"configured": False, "healthy": False}

    async def fake_catalog():
        return {"providers": []}

    async def fake_silverwing():
        return {
            "configured": True,
            "reachable": True,
            "executable": False,
            "endpoint": "http://127.0.0.1:8010",
        }

    monkeypatch.setattr(ProviderGateway, "probe_brain", fake_probe_brain)
    monkeypatch.setattr(ai, "_provider_catalog", fake_catalog)
    monkeypatch.setattr(health, "_probe_silverwing", fake_silverwing)

    result = await health.health_ready()

    assert result["status"] == "degraded"
    assert result["providers"] == []
    assert result["silverwing"]["reachable"] is True
    assert result["silverwing"]["executable"] is False
