"""Phase 1 — data ownership & cross-user access denial.

Spec (section 2): "Never trust client `user_id`."  Every chat/note/reminder
route derives the caller identity from the bearer token; sessions are keyed to
the authenticated user and cross-user access returns an authorization failure.
"""
from __future__ import annotations


def _register(client, email, username, password="S3cret!pass"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": password}).json()


def _new_session(client, token):
    r = client.post("/api/chat", json={"message": "hello"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_cross_user_send_into_session_is_denied(client):
    a = _register(client, "a@example.com", "a")
    b = _register(client, "b@example.com", "b")
    sid = _new_session(client, a["access_token"])
    # User B attempts to send a message into A's session.
    r = client.post("/api/chat", json={"message": "hi", "session_id": sid},
                    headers={"Authorization": f"Bearer {b['access_token']}"})
    assert r.status_code == 403
    assert r.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_cross_user_history_is_denied(client):
    a = _register(client, "a@example.com", "a")
    b = _register(client, "b@example.com", "b")
    sid = _new_session(client, a["access_token"])
    r = client.get(f"/api/chat/history/{sid}",
                   headers={"Authorization": f"Bearer {b['access_token']}"})
    assert r.status_code == 403
    assert r.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_cross_user_delete_is_denied(client):
    a = _register(client, "a@example.com", "a")
    b = _register(client, "b@example.com", "b")
    sid = _new_session(client, a["access_token"])
    r = client.delete(f"/api/chat/history/{sid}",
                      headers={"Authorization": f"Bearer {b['access_token']}"})
    assert r.status_code == 403
    assert r.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_unknown_session_returns_404_not_403(client, auth_headers):
    """Genuine not-found is INVALID_REQUEST/404 (no existence leak)."""
    r = client.get("/api/chat/history/does-not-exist", headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["error"]["category"] == "INVALID_REQUEST"


def test_users_only_see_own_sessions(client):
    a = _register(client, "a@example.com", "a")
    b = _register(client, "b@example.com", "b")
    _new_session(client, a["access_token"])
    sa = client.get("/api/chat/sessions",
                    headers={"Authorization": f"Bearer {a['access_token']}"}).json()
    sb = client.get("/api/chat/sessions",
                    headers={"Authorization": f"Bearer {b['access_token']}"}).json()
    assert len(sa["sessions"]) == 1
    assert len(sb["sessions"]) == 0


def test_client_supplied_user_id_is_not_honored(client, auth_headers):
    """ChatIn has no user_id field; an injected user_id must not impersonate."""
    r = client.post("/api/chat", json={"message": "hi", "user_id": "victim-id"},
                    headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    from jarvis_backend.chat_service import chat_service

    session = chat_service.get_session("testuser", data["session_id"])
    assert session["user_id"] == "testuser"
    assert "victim-id" not in session.values()
