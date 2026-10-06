import pytest
from starlette.responses import Response

from jarvis_backend.gateway import ProviderGateway
from jarvis_backend.routers import ai, health, system


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
                    "model": "gemini-2.5-flash",
                }
            ]
        }

    async def fake_silverwing():
        return {"configured": True, "reachable": False, "endpoint": "http://127.0.0.1:8010"}

    monkeypatch.setattr(ProviderGateway, "probe_brain", fake_probe_brain)
    monkeypatch.setattr(ai, "_provider_catalog", fake_catalog)
    monkeypatch.setattr(health, "_probe_silverwing", fake_silverwing)

    result = await health.health_ready(Response())

    assert result["status"] == "ready"
    assert result["brain"]["healthy"] is False
    assert result["providers"] == [
        {"provider": "google", "model": "gemini-2.5-flash"}
    ]


@pytest.mark.asyncio
async def test_readiness_accepts_silverwing_without_cloud_or_brain(monkeypatch):
    async def fake_probe_brain(self, timeout=15.0):
        return {"configured": False, "healthy": False}

    async def fake_catalog():
        return {"providers": []}

    async def fake_silverwing():
        return {"configured": True, "reachable": True, "endpoint": "http://127.0.0.1:8010"}

    monkeypatch.setattr(ProviderGateway, "probe_brain", fake_probe_brain)
    monkeypatch.setattr(ai, "_provider_catalog", fake_catalog)
    monkeypatch.setattr(health, "_probe_silverwing", fake_silverwing)

    result = await health.health_ready(Response())

    assert result["status"] == "ready"
    assert result["providers"] == []
    assert result["silverwing"]["reachable"] is True


@pytest.mark.asyncio
async def test_system_readiness_marks_unprobed_providers_partial(monkeypatch):
    monkeypatch.setenv("JARVIS_GEOCODER_URL", "https://geo.example/search")
    monkeypatch.setenv("JARVIS_GEOCODER_USER_AGENT", "JARVIS test contact")
    monkeypatch.setenv("JARVIS_ROUTING_URL", "https://routes.example/route/v1/driving")
    monkeypatch.setenv("JARVIS_MAP_TILE_URL", "https://tiles.example/{z}/{x}/{y}.png")
    monkeypatch.setenv("JARVIS_MAP_ATTRIBUTION", "Licensed tiles")
    monkeypatch.setenv("JARVIS_SATELLITE_IMAGERY_LICENSE_CONFIRMED", "true")

    result = await system.system_readiness(user={"id": "readiness-test"})
    statuses = {item["id"]: item["status"] for item in result["items"]}

    assert statuses["geography-map"] == "partial"
    assert statuses["geography-geocoder"] == "partial"
    assert statuses["geography-routing"] == "partial"
    assert statuses["satellite-imagery"] == "needs_setup"
