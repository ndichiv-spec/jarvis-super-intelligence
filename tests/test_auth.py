"""Authentication tests for the active JARVIS backend auth stack."""

from __future__ import annotations

import hashlib
import hmac

from jarvis_backend.core import (
    _SECRET_KEY,
    create_refresh_token,
    create_token,
    decode_token,
    hash_password,
    password_hash_needs_upgrade,
    refresh_access_token,
    revoke_refresh_token,
    verify_password,
)


def test_password_hash_uses_argon2id():
    stored = hash_password("S3cret!pass")
    assert stored.startswith("$argon2id$")
    assert not password_hash_needs_upgrade(stored)
    assert verify_password("S3cret!pass", stored)
    assert not verify_password("wrong-password", stored)


def test_password_hash_uses_unique_salts():
    first = hash_password("same")
    second = hash_password("same")
    assert first != second
    assert verify_password("same", first)
    assert verify_password("same", second)


def test_legacy_password_hashes_remain_verifiable():
    salt = "deadbeef"
    digest = hmac.new(salt.encode(), b"pw", hashlib.sha256).hexdigest()
    assert verify_password("pw", f"{salt}${digest}")
    assert not verify_password("wrong", f"{salt}${digest}")
    assert password_hash_needs_upgrade(f"{salt}${digest}")
    pbkdf2 = hash_password("legacy")
    assert verify_password("legacy", pbkdf2)
    assert not verify_password("pw", "pbkdf2_sha256$bad")
    assert not verify_password("pw", "not-a-valid-hash")


def test_token_roundtrip_expiry_and_refresh_lifecycle():
    token = create_token({"sub": "u1", "sid": "s1"})
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["sid"] == "s1"
    assert payload["exp"] > payload["iat"]
    assert decode_token(create_token({"sub": "u1"}, ttl_hours=-1)) is None

    refresh = create_refresh_token("u1")
    assert decode_token(refresh)["jti"]
    assert refresh_access_token(refresh) is not None
    assert revoke_refresh_token(refresh)
    assert refresh_access_token(refresh) is None


def test_no_insecure_default_signing_secret():
    assert _SECRET_KEY != "jarvis-dev-secret-change-me"
    assert len(_SECRET_KEY) >= 32


def test_registration_requires_email_verification_before_login(
    client, account_email_outbox
):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.test", "username": "a", "password": "S3cret!pass"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "verification_required",
        "email_verified": False,
    }
    assert "access_token" not in response.json()
    assert "verification_token" not in response.json()

    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": "a@example.test", "password": "wrong"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": "a@example.test", "password": "S3cret!pass"},
    ).status_code == 403

    token = account_email_outbox[-1][2]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "a@example.test", "password": "S3cret!pass"},
    )
    assert login.status_code == 200
    assert login.json()["expires_in"] == 3600
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.test"


def test_registration_rejects_duplicate_email(client, account_email_outbox):
    payload = {"email": "a@example.test", "username": "a", "password": "S3cret!pass"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    duplicate = client.post(
        "/api/v1/auth/register",
        json={**payload, "username": "another"},
    )
    assert duplicate.status_code == 409


def test_invalid_token_rejected(client):
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid"},
    ).status_code == 401


def test_verification_token_is_hashed_expiring_and_one_time(
    client, account_email_outbox, monkeypatch
):
    from jarvis_backend.core import get_store
    from jarvis_backend.routers import auth as auth_routes

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "verify@example.test", "username": "verify", "password": "S3cret!pass"},
    )
    assert response.status_code == 200
    token = account_email_outbox[-1][2]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    stored = get_store("email_verification_tokens").load()[token_hash]
    assert stored["expires_at"] > auth_routes.now_iso_timestamp()
    assert token not in get_store("email_verification_tokens").load()
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert get_store("email_verification_tokens").load()[token_hash]["used"]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": "invalid-token"},
    ).status_code == 400

    # Expiry is checked against server time, not caller-provided claims.
    expiring = "expires-soon"
    expiring_hash = hashlib.sha256(expiring.encode()).hexdigest()
    tokens = get_store("email_verification_tokens").load()
    tokens[expiring_hash] = {
        "user_id": stored["user_id"],
        "purpose": "email_verification",
        "expires_at": auth_routes.now_iso_timestamp() - 1,
        "used": False,
    }
    get_store("email_verification_tokens").save()
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": expiring},
    ).status_code == 400


def test_resend_verification_sends_token_out_of_band(
    client, account_email_outbox
):
    client.post(
        "/api/v1/auth/register",
        json={"email": "resend@example.test", "username": "resend", "password": "S3cret!pass"},
    )
    response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend@example.test"},
    )
    assert response.status_code == 200
    assert "verification_token" not in response.json()
    assert account_email_outbox[-1][1] == "verify"


def test_user_payload_includes_verification_state():
    from jarvis_backend.core import make_user_payload

    assert make_user_payload(
        {"id": "1", "email": "test@example.test", "email_verified": True}
    )["email_verified"] is True
