"""In-process smoke tests for the canonical JARVIS API."""


def test_health_status_is_available(client):
    response = client.get("/api/v1/health/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"healthy", "degraded"}
    assert body["service_readiness"] in {"ready", "degraded"}


def test_system_status_returns_runtime_summary(client, admin_headers):
    response = client.get("/api/v1/system/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "online"
    assert isinstance(body["services"], list)
    assert "timestamp" in body


def test_process_listing_requires_administrator(client):
    unauthenticated = client.get("/api/v1/system/processes")
    assert unauthenticated.status_code == 401


def test_knowledge_search_requires_authentication(client):
    response = client.get("/api/v1/cognitive/knowledge/search")

    assert response.status_code == 401
