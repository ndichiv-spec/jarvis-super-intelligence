from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis_backend.main import app
from jarvis_backend.observability import metrics


def test_monitoring_metrics_are_mounted_on_canonical_app():
    response = TestClient(app).get("/api/v1/monitoring/metrics")

    assert response.status_code == 200
    assert "available" in response.json()


def test_ai_processing_route_is_mounted_on_canonical_app():
    paths = app.openapi()["paths"]

    assert "/api/v1/ai/process" in paths
    assert metrics.snapshot()["active_requests"] >= 0
