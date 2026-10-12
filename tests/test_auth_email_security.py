from __future__ import annotations

import hashlib

from fastapi import HTTPException

from jarvis_backend.core import get_store
from jarvis_backend.routers import auth as auth_routes


def _capture_auth_mail(monkeypatch):
    deliveries: list[tuple[str, str, str]] = []

    async def deliver(email: str, action: str, token: str) -> None:
        deliveries.append((email, action, token))

    monkeypatch.setattr(auth_routes, "_ensure_account_email_configured", lambda: None)
    monkeypatch.setattr(auth_routes, "_send_account_email", deliver)
    return deliveries


def _register(client, email: str, username: str):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "S3cret!pass"},
    )


def _authorize_user(email: str) -> None:
    user = next(
        user for user in get_store("users").load().values()
        if user.get("email", "").lower() == email.lower()
    )
    user["status"] = "active"
    get_store("users").save()


def test_registration_delivers_token_out_of_band_and_requires_verification(
    client, monkeypatch
):
    deliveries = _capture_auth_mail(monkeypatch)
    response = _register(client, "pending@example.test", "pending-user")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "verification_required",
        "email_verified": False,
    }
    assert "access_token" not in response.json()
    assert "verification_token" not in response.json()
    assert len(deliveries) == 1
    email, action, token = deliveries[0]
    assert (email, action) == ("pending@example.test", "verify")

    stored = get_store("email_verification_tokens").load()
    assert hashlib.sha256(token.encode()).hexdigest() in stored
    assert token not in stored
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "S3cret!pass"},
    ).status_code == 403

    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    _authorize_user(email)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "S3cret!pass"},
    )
    assert login.status_code == 200
    assert login.json()["expires_in"] == 3600


def test_forgot_password_hides_token_and_reset_expires_consumes_and_revokes(
    client, monkeypatch
):
    deliveries = _capture_auth_mail(monkeypatch)
    registration = _register(client, "recover@example.test", "recover-user")
    assert registration.status_code == 200
    verification_token = deliveries.pop()[2]
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    ).status_code == 200
    _authorize_user("recover@example.test")
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "recover@example.test", "password": "S3cret!pass"},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "recover@example.test"},
    )
    assert response.status_code == 200
    assert "reset_token" not in response.json()
    _, action, reset_token = deliveries.pop()
    assert action == "reset"

    hashed = hashlib.sha256(reset_token.encode()).hexdigest()
    entry = get_store("misc").load()["reset_tokens"][hashed]
    assert isinstance(entry, dict)
    assert "user_id" in entry and "expires_at" in entry
    assert reset_token not in get_store("misc").load()["reset_tokens"]

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "N3w!Passphrase"},
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "Another!Pass"},
    ).status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": "recover@example.test", "password": "N3w!Passphrase"},
    ).status_code == 200


def test_registration_fails_closed_when_account_email_is_unconfigured(client, monkeypatch):
    def unavailable():
        raise HTTPException(
            status_code=503,
            detail={"code": "EMAIL_DELIVERY_NOT_CONFIGURED"},
        )

    monkeypatch.setattr(auth_routes, "_ensure_account_email_configured", unavailable)
    response = _register(client, "no-mail@example.test", "no-mail-user")

    assert response.status_code == 503
    assert "no-mail-user" not in get_store("users").load()
