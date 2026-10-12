"""Tests for the canonical authenticated search API."""


def test_search_status_requires_authentication(client):
    response = client.get("/api/v1/search/status")

    assert response.status_code == 401


def test_search_status_reports_local_domains(client, admin_headers):
    response = client.get("/api/v1/search/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert "knowledge" in body["domains"]
    assert "healthy" in body
