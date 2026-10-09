"""The legacy in-memory browser must not report simulated work as real."""


def test_legacy_embedded_browser_requires_authentication(client):
    assert client.get("/api/browser/system/status").status_code == 401
    assert client.post("/api/browser/system/initialize").status_code == 401


def test_legacy_embedded_browser_reports_not_configured(client, auth_headers):
    response = client.get(
        "/api/browser/system/status",
        headers=auth_headers,
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"

    create_response = client.post(
        "/api/browser/create",
        headers=auth_headers,
        json={},
    )
    assert create_response.status_code == 501
    assert create_response.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"
