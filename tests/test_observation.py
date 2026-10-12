"""Observation contract tests for the canonical JARVIS metrics endpoint."""


def test_observation_snapshot_contains_system_and_application_metrics(client):
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["system"], dict)
    assert isinstance(body["active_sessions"], int)
    assert isinstance(body["memory_items"], int)
