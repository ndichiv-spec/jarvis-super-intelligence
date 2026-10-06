"""Health endpoint tests for the canonical JARVIS FastAPI application."""

from jarvis_backend.main import app


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client, monkeypatch):
        monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
        assert client.app is app
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "JARVIS API"
        assert data["component"] == "control-plane"
        assert data["status"] == "degraded"
        assert data["documentation"]["swagger"] == "/docs"
        assert data["documentation"]["openapi"] == "/openapi.json"

    def test_health_status(self, client):
        response = client.get("/api/v1/health/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service_readiness"] == "ready"
        assert "uptime_seconds" in data

    def test_health_live(self, client):
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_health_ready(self, client):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert response.json()["service_readiness"] == "ready"

    def test_health_metrics(self, client):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "system" in data
        assert "active_sessions" in data
