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
    verification = account_email_outbox[-1][2]
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification},
    ).status_code == 200
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "S3cret!pass"},
    ).json()


def test_registration_issues_no_credentials_until_verified(
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
    assert login["access_token"]
    assert login["refresh_token"]
    assert login["token_type"] == "bearer"
    assert login["expires_in"] == 3600
    payload = decode_token(login["access_token"])
    assert payload["sub"]
    assert "jti" not in payload


def test_refresh_rotates_tokens_and_rejects_reuse(client, account_email_outbox):
    login = _verified_login(client, "a@example.test", "a", account_email_outbox)
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert decode_token(body["access_token"])["sub"] == decode_token(
        login["access_token"]
    )["sub"]
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    ).status_code == 401


def test_refresh_rejected_for_invalid_token(client):
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "garbage"},
    ).status_code == 401


def test_logout_revokes_refresh_token(client, account_email_outbox):
    login = _verified_login(client, "a@example.test", "a", account_email_outbox)
    client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": login["refresh_token"]},
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    ).status_code == 401


def test_expired_access_token_is_rejected(client):
    token = create_token({"sub": "ghost"}, ttl_hours=-1)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_users_get_isolated_principals(client, account_email_outbox):
    a = _verified_login(client, "a@example.test", "a", account_email_outbox)
    b = _verified_login(client, "b@example.test", "b", account_email_outbox)
    me_as_a = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    ).json()
    me_as_b = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    ).json()
    assert me_as_a["email"] == "a@example.test"
    assert me_as_b["email"] == "b@example.test"
    assert decode_token(a["refresh_token"])["sub"] != decode_token(
        b["refresh_token"]
    )["sub"]
