"""Metrics endpoint tests for the canonical FastAPI application."""


def test_metrics_endpoint_returns_runtime_snapshot(client):
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "timestamp" in body
    assert "system" in body
    assert "active_sessions" in body
    assert isinstance(body["active_sessions"], int)
