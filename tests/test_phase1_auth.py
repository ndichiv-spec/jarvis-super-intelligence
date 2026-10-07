"""Authentication and refresh-token lifecycle at the active API boundary."""
from __future__ import annotations

import pytest

from jarvis_backend.core import create_token, decode_token


@pytest.fixture(autouse=True)
def reset_auth_state():
    from jarvis_backend.core import get_store

    for collection in (
        "users",
        "sessions",
        "refresh_tokens",
        "email_verification_tokens",
        "audit_logs",
    ):
        get_store(collection).reset()


def _register(client, email, username):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "S3cret!pass"},
    )


def _verified_login(client, email, username, account_email_outbox):
    registered = _register(client, email, username)
    assert registered.status_code == 200
    assert registered.json()["status"] == "verification_required"
    assert "access_token" not in registered.json()
    assert "refresh_token" not in registered.json()

    verification = account_email_outbox[-1][2]
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification},
    ).status_code == 200

    # New accounts require separate owner approval in addition to email proof.
    from jarvis_backend.core import get_store

    users = get_store("users").load()
    user = next(u for u in users.values() if u.get("email") == email)
    user["status"] = "active"
    get_store("users").save()

    return client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "S3cret!pass"},
    )


def test_registration_issues_credentials_only_as_http_only_cookies(
    client, account_email_outbox
):
    registered = _register(client, "a@example.test", "a")
    assert registered.status_code == 200
    assert registered.json()["email_verified"] is False
    assert "access_token" not in registered.json()
    assert "refresh_token" not in registered.json()
    assert "verification_token" not in registered.json()
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "unissued"},
    ).status_code == 401

    login = _verified_login(client, "b@example.test", "b", account_email_outbox)
    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert "access_token" not in login.json()
    assert "refresh_token" not in login.json()
    set_cookie_headers = login.headers.get_list("set-cookie")
    for name in ("jarvis_access_token", "jarvis_refresh_token"):
        cookie = login.cookies.get(name)
        assert cookie
        assert any(
            header.lower().startswith(name.lower() + "=")
            and "httponly" in header.lower()
            for header in set_cookie_headers
        )
    access = login.cookies["jarvis_access_token"]
    payload = decode_token(access)
    assert payload["sub"]
    assert "jti" not in payload


def test_refresh_rotates_http_only_cookies_and_rejects_reuse(
    client, account_email_outbox
):
    login = _verified_login(client, "a@example.test", "a", account_email_outbox)
    assert login.status_code == 200
    old_access = login.cookies["jarvis_access_token"]
    old_refresh = login.cookies["jarvis_refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    new_access = response.cookies["jarvis_access_token"]
    new_refresh = response.cookies["jarvis_refresh_token"]
    assert new_refresh != old_refresh
    assert decode_token(new_access)["sub"] == decode_token(old_access)["sub"]

    assert client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://localhost:3000"},
        cookies={"jarvis_refresh_token": old_refresh},
    ).status_code == 401


def test_refresh_rejected_for_invalid_token(client):
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "garbage"},
    ).status_code == 401


def test_logout_revokes_cookie_session_and_refresh_token(
    client, account_email_outbox
):
    login = _verified_login(client, "a@example.test", "a", account_email_outbox)
    assert login.status_code == 200
    access = login.cookies["jarvis_access_token"]
    refresh = login.cookies["jarvis_refresh_token"]
    session_id = decode_token(access)["sid"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    from jarvis_backend.core import get_store

    assert session_id not in get_store("sessions").load()
    assert client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://localhost:3000"},
        cookies={"jarvis_refresh_token": refresh},
    ).status_code == 401


def test_expired_access_token_is_rejected(client):
    token = create_token({"sub": "ghost"}, ttl_hours=-1)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_users_get_isolated_principals(client, account_email_outbox):
    login_a = _verified_login(client, "a@example.test", "a", account_email_outbox)
    login_b = _verified_login(client, "b@example.test", "b", account_email_outbox)
    assert login_a.status_code == login_b.status_code == 200

    me_a = client.get(
        "/api/v1/auth/me",
        cookies={"jarvis_access_token": login_a.cookies["jarvis_access_token"]},
    )
    me_b = client.get(
        "/api/v1/auth/me",
        cookies={"jarvis_access_token": login_b.cookies["jarvis_access_token"]},
    )

    assert me_a.json()["email"] == "a@example.test"
    assert me_b.json()["email"] == "b@example.test"
    assert decode_token(login_a.cookies["jarvis_access_token"])["sub"] != decode_token(
        login_b.cookies["jarvis_access_token"]
    )["sub"]
