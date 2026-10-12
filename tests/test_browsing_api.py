"""In-process tests for the supported JARVIS search API."""


def test_search_status_requires_authentication(client):
    response = client.get("/api/v1/search/status")

    assert response.status_code == 401


def test_search_status_reports_local_search_domains(client, admin_headers):
    response = client.get("/api/v1/search/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["domains"], dict)
    assert "knowledge" in body["domains"]
    assert "healthy" in body
