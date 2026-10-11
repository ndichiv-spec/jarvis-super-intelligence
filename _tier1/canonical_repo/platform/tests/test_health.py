"""
Tests for Health Endpoints
===========================
"""

import pytest
from httpx import ASGITransport, AsyncClient

from jarvis_backend.main import app


@pytest.fixture
def client(event_loop):
    """Test client fixture."""
    async def _create_client():
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")
        await client.__aenter__()
        return client

    client = event_loop.run_until_complete(_create_client())
    try:
        yield client
    finally:
        event_loop.run_until_complete(client.__aexit__(None, None, None))


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Test root endpoint returns app info."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "JARVIS API"
        assert data["status"] in {"operational", "degraded"}
        assert data["documentation"]["swagger"] == "/docs"

    @pytest.mark.asyncio
    async def test_health_status(self, client):
        """Test health status endpoint."""
        response = await client.get("/api/v1/health/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"healthy", "degraded"}
        assert data["alive"] is True
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_live(self, client):
        """Test liveness probe."""
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_ready(self, client):
        """Test readiness probe."""
        response = await client.get("/api/v1/health/ready")
        assert response.status_code in {200, 503}
        data = response.json()
        assert data["status"] in {"ready", "degraded"}

    @pytest.mark.asyncio
    async def test_health_metrics(self, client):
        """Test health metrics endpoint."""
        response = await client.get("/api/v1/health/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "uptime_seconds" in data
        assert "timestamp" in data
