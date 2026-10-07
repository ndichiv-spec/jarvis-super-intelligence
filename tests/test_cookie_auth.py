"""Browser cookie authentication regression tests."""

from jarvis_backend.core import create_refresh_token, create_token, decode_token, get_store


def test_access_cookie_authenticates_safe_request_without_origin(client):
    token = create_token({"sub": "testuser"})

    response = client.get(
        "/api/v1/auth/me",
        cookies={"jarvis_access_token": token},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "testuser"


def test_cookie_logout_revokes_session_and_refresh_token(client):
    session_id = "cookie-session"
    sessions = get_store("sessions").load()
    sessions[session_id] = {"id": session_id, "user_id": "testuser"}
    get_store("sessions").save()
    access_token = create_token({"sub": "testuser", "sid": session_id})
    refresh_token = create_refresh_token("testuser", session_id)
    refresh_jti = decode_token(refresh_token)["jti"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:3000"},
        cookies={
            "jarvis_access_token": access_token,
            "jarvis_refresh_token": refresh_token,
        },
    )

    assert response.status_code == 200
    assert session_id not in get_store("sessions").load()
    assert refresh_jti not in get_store("refresh_tokens").load()


def test_cookie_authenticated_mutation_requires_origin(client):
    token = create_token({"sub": "testuser"})

    response = client.post(
        "/api/chat",
        json={"message": "hello"},
        cookies={"jarvis_access_token": token},
    )

    assert response.status_code == 403
