"""Ownership boundaries for authenticated chat sessions."""
from __future__ import annotations

from jarvis_backend.core import create_token, get_store


def _principal_token(user_id):
    users = get_store("users").load()
    users[user_id] = {
        "id": user_id,
        "email": f"{user_id}@example.test",
        "email_verified": True,
        "status": "active",
        "roles": ["user"],
    }
    get_store("users").save()
    return create_token({"sub": user_id})


def _new_session(client, token):
    response = client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_cross_user_send_into_session_is_denied(client):
    token_a = _principal_token("user-a")
    token_b = _principal_token("user-b")
    session_id = _new_session(client, token_a)

    response = client.post(
        "/api/chat",
        json={"message": "hi", "session_id": session_id},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_cross_user_history_is_denied(client):
    token_a = _principal_token("user-a")
    token_b = _principal_token("user-b")
    session_id = _new_session(client, token_a)

    response = client.get(
        f"/api/chat/history/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_cross_user_delete_is_denied(client):
    token_a = _principal_token("user-a")
    token_b = _principal_token("user-b")
    session_id = _new_session(client, token_a)

    response = client.delete(
        f"/api/chat/history/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["category"] == "AUTHORIZATION_ERROR"


def test_unknown_session_returns_404_not_403(client, auth_headers):
    """A missing session has a not-found response without leaking ownership."""
    response = client.get(
        "/api/chat/history/does-not-exist",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["category"] == "INVALID_REQUEST"


def test_users_only_see_own_sessions(client):
    token_a = _principal_token("user-a")
    token_b = _principal_token("user-b")
    _new_session(client, token_a)

    sessions_a = client.get(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    sessions_b = client.get(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()

    assert len(sessions_a["sessions"]) == 1
    assert len(sessions_b["sessions"]) == 0


def test_client_supplied_user_id_is_not_honored(client, auth_headers):
    response = client.post(
        "/api/chat",
        json={"message": "hi", "user_id": "victim-id"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    from jarvis_backend.chat_service import chat_service

    session = chat_service.get_session("testuser", response.json()["session_id"])
    assert session["user_id"] == "testuser"
    assert "victim-id" not in session.values()
