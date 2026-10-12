"""Training API contract tests for the canonical curriculum router."""


def test_training_run_listing_requires_authentication(client):
    response = client.get("/api/v1/training/runs")

    assert response.status_code == 401


def test_training_run_listing_returns_scoped_collection(client, admin_headers):
    response = client.get("/api/v1/training/runs", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["runs"], list)
    assert body["count"] == len(body["runs"])
