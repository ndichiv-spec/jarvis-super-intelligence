"""Browser service contract tests against the canonical ASGI application."""


def test_browser_status_requires_authentication(client):
    response = client.get("/api/v1/browser/status")

    assert response.status_code == 401


def test_browser_status_is_scoped_to_authenticated_user(client, admin_headers):
    response = client.get("/api/v1/browser/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "test-admin"
    assert body["sessions"] == 0
    assert body["active_sessions"] == []
