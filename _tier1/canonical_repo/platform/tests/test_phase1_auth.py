"""Phase 1 — authentication & refresh-token lifecycle (API level)."""
from __future__ import annotations

from jarvis_backend.core import create_token, decode_token


def _register(client, email, username, password="S3cret!pass"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": password}).json()


def test_register_issues_access_and_refresh_tokens(client):
    data = _register(client, "a@example.com", "a")
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 604800  # access tokens are short-lived
    payload = decode_token(data["access_token"])
    assert payload["sub"]  # server-derived user id
    # Access tokens carry no jti (only refresh tokens are jti-tracked/revocable).
    assert "jti" not in payload


def test_refresh_issues_a_new_access_token(client):
    data = _register(client, "a@example.com", "a")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    # The refreshed access token is valid and bound to the same user.
    new = decode_token(body["access_token"])
    old = decode_token(data["access_token"])
    assert new["sub"] == old["sub"]


def test_refresh_rejected_for_invalid_token(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
    assert r.status_code == 401


def test_logout_revokes_refresh_token(client):
    data = _register(client, "a@example.com", "a")
    rt = data["refresh_token"]
    client.post("/api/v1/auth/logout",
                json={"refresh_token": rt},
                headers={"Authorization": f"Bearer {data['access_token']}"})
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 401


def test_expired_access_token_is_rejected(client):
    tok = create_token({"sub": "ghost"}, ttl_hours=-1)  # expired
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_two_users_get_isolated_principals(client):
    a = _register(client, "a@example.com", "a")
    b = _register(client, "b@example.com", "b")
    me_as_a = client.get("/api/v1/auth/me",
                         headers={"Authorization": f"Bearer {a['access_token']}"}).json()
    me_as_b = client.get("/api/v1/auth/me",
                         headers={"Authorization": f"Bearer {b['access_token']}"}).json()
    assert me_as_a["email"] == "a@example.com"
    assert me_as_b["email"] == "b@example.com"
    # A's refresh token cannot mint a token that reads as B.
    assert decode_token(a["refresh_token"])["sub"] != decode_token(b["refresh_token"])["sub"]
