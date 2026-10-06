"""Backend smoke tests for the jarvis_backend application.

Replaces the previous test_backend.py which imported the legacy ``api.main``
stack and spawned a Flask server (``No module named 'flask'``).  This version
targets the real runnable backend and asserts the integration points that
Phase 1 depends on.
"""
from __future__ import annotations


def test_app_title(app):
    assert app.title == "JARVIS Unified System"


def test_app_singleton(app):
    import jarvis_backend.main as m
    assert m.app is app


def test_chat_endpoint_requires_auth(client):
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_me_endpoint_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_deprecated_ai_routes_return_410(client, auth_headers):
    # ai/generate and llm/chat no longer return canned/fabricated responses.
    # ai/process was re-activated as the provider-backed chat bridge
    # (Silverwing-first); it must answer or fail honestly, never 410.
    assert client.post("/api/v1/ai/generate", json={"prompt": "x"}).status_code == 410
    assert client.post("/api/v1/llm/chat", json={"input": "x"}).status_code == 410
    r = client.post("/api/v1/ai/process", json={"input": "x"}, headers=auth_headers)
    assert r.status_code in (200, 502)
    if r.status_code == 200:
        assert "response" in r.json()


def test_unified_status_endpoint(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "JARVIS Unified System"
    assert "silverwing" in body


def test_silverwing_is_mounted(client):
    # Silverwing is integrated as a mounted sub-application (see main.py).
    r = client.get("/api/v1/status")
    assert r.json()["silverwing"]["integrated"] is True
