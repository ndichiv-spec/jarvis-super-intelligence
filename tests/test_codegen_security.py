"""Security regression tests for code generation and source review endpoints."""


def test_codegen_routes_require_auth(client):
    assert client.post("/api/v1/codegen/generate", json={"description": "demo"}).status_code == 401
    assert client.get("/api/v1/codegen/review", params={"path": "tests/test_codegen_security.py"}).status_code == 401
    assert client.post("/api/v1/codegen/deploy", json={
        "project_path": "project", "platform": "test", "project_name": "demo",
    }).status_code == 401


def test_review_rejects_path_outside_project_root(client, auth_headers):
    response = client.get(
        "/api/v1/codegen/review",
        params={"path": "..\\..\\outside.py"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"


def test_review_only_returns_ai_review_not_source(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import codegen

    async def _review(prompt):
        assert "Security regression tests" in prompt
        return "Looks good"

    monkeypatch.setattr(codegen.ai_service, "chat", _review)
    response = client.get(
        "/api/v1/codegen/review",
        params={"path": "tests/test_codegen_security.py"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"] == "tests/test_codegen_security.py"
    assert body["review"] == "Looks good"
    assert "Security regression tests" not in body["review"]
    assert body["passed"] is None
    assert body["validation"] == "not_run"


def test_deploy_is_admin_only_and_capability_not_configured(client, auth_headers, admin_headers):
    payload = {"project_path": "project", "platform": "test", "project_name": "demo"}
    assert client.post("/api/v1/codegen/deploy", json=payload, headers=auth_headers).status_code == 403

    response = client.post("/api/v1/codegen/deploy", json=payload, headers=admin_headers)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"
