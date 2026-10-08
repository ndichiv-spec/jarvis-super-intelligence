"""Authentication tests targeting jarvis_backend.core + /api/v1/auth.

Replaces the previous test_auth.py which imported the legacy ``api.middleware``
stack (bcrypt/pwd_context) that does not exist in this architecture.
"""
from __future__ import annotations

import hashlib
import hmac

from jarvis_backend.core import (
    _PBKDF2_ITERATIONS,
    _SECRET_KEY,
    create_refresh_token,
    create_token,
    decode_token,
    hash_password,
    refresh_access_token,
    revoke_refresh_token,
    verify_password,
)


def test_password_hash_is_pbkdf2():
    h = hash_password("S3cret!pass")
    assert h.startswith("pbkdf2_sha256$")
    assert h.split("$")[1] == str(_PBKDF2_ITERATIONS)
    assert verify_password("S3cret!pass", h)
    assert not verify_password("wrong-password", h)


def test_password_hash_uses_unique_salt():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b  # different salt each call
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_verify_supports_legacy_hmac_fallback():
    salt = "deadbeef"
    digest = hmac.new(salt.encode(), b"pw", hashlib.sha256).hexdigest()
    legacy = f"{salt}${digest}"
    assert verify_password("pw", legacy)
    assert not verify_password("no", legacy)


def test_verify_rejects_malformed_store():
    assert verify_password("pw", "not-a-valid-hash") is False
    assert verify_password("pw", "pbkdf2_sha256$bad") is False


def test_token_roundtrip_and_claims():
    tok = create_token({"sub": "u1", "sid": "s1"})
    payload = decode_token(tok)
    assert payload["sub"] == "u1"
    assert payload["sid"] == "s1"
    assert payload["exp"] > payload["iat"]


def test_expired_token_rejected():
    tok = create_token({"sub": "u1"}, ttl_hours=-1)  # already expired
    assert decode_token(tok) is None


def test_refresh_token_lifecycle():
    rt = create_refresh_token("u1", "s1")
    assert decode_token(rt)["jti"]  # has a jti
    assert refresh_access_token(rt) is not None  # mints access
    assert revoke_refresh_token(rt) is True
    assert refresh_access_token(rt) is None  # revoked


def test_no_insecure_default_secret():
    assert _SECRET_KEY != "jarvis-dev-secret-change-me"
    assert len(_SECRET_KEY) >= 32


def test_register_login_me_via_api(client):
    reg = client.post("/api/v1/auth/register", json={
        "email": "a@example.com", "username": "a", "password": "S3cret!pass",
    }).json()
    assert reg["access_token"]
    assert reg["refresh_token"]
    assert reg["token_type"] == "bearer"

    me = client.get("/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {reg['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"


def test_login_invalid_credentials_rejected(client):
    client.post("/api/v1/auth/register", json={
        "email": "a@example.com", "username": "a", "password": "S3cret!pass"})
    r = client.post("/api/v1/auth/login", json={
        "identifier": "a@example.com", "password": "WRONG"})
    assert r.status_code == 401


def test_register_rejects_duplicate(client):
    client.post("/api/v1/auth/register", json={
        "email": "a@example.com", "username": "a", "password": "S3cret!pass"})
    r = client.post("/api/v1/auth/register", json={
        "email": "a@example.com", "username": "b", "password": "S3cret!pass"})
    assert r.status_code == 409


def test_invalid_token_rejected(client):
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": "Bearer garbage.token.here"})
    assert r.status_code == 401


# Email Verification Flow Tests

def test_register_creates_email_verification_token(client):
    """Test that registration creates a verification token."""
    import hashlib
    from jarvis_backend.core import get_store
    
    reg = client.post("/api/v1/auth/register", json={
        "email": "verify@example.com", "username": "verify", "password": "S3cret!pass",
    }).json()
    
    assert "access_token" in reg  # Registration succeeded
    assert reg.get("email_verified") == False
    
    # Check verification token was created
    tokens = get_store("email_verification_tokens").load()
    assert len(tokens) > 0, "Verification token should be created"
    
    # Check user has email_verified = False
    users = get_store("users").load()
    user = next((u for u in users.values() if u.get("email") == "verify@example.com"), None)
    assert user is not None
    assert user.get("email_verified") == False


def test_verify_email_endpoint(client):
    """Test email verification endpoint."""
    from jarvis_backend.core import get_store
    
    # Register a user
    reg = client.post("/api/v1/auth/register", json={
        "email": "verify2@example.com", "username": "verify2", "password": "S3cret!pass",
    }).json()
    
    verification_token = reg.get("verification_token")
    assert verification_token is not None, "Registration should return verification token"
    
    # Verify email
    r = client.post("/api/v1/auth/verify-email", json={"token": verification_token})
    assert r.status_code == 200
    result = r.json()
    assert result["success"] == True
    assert result["email_verified"] == True
    
    # Check user is now verified
    users = get_store("users").load()
    user = next((u for u in users.values() if u.get("email") == "verify2@example.com"), None)
    assert user is not None
    assert user.get("email_verified") == True
    
    # Check token is marked as used
    tokens = get_store("email_verification_tokens").load()
    token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
    assert tokens[token_hash]["used"] == True


def test_verify_email_invalid_token(client):
    """Test that invalid verification token is rejected."""
    r = client.post("/api/v1/auth/verify-email", json={"token": "invalid-token"})
    assert r.status_code == 400


def test_verify_email_already_used(client):
    """Test that used verification token is rejected."""
    
    # Register a user
    reg = client.post("/api/v1/auth/register", json={
        "email": "verify3@example.com", "username": "verify3", "password": "S3cret!pass",
    }).json()
    
    verification_token = reg.get("verification_token")
    
    # Verify email first time
    r1 = client.post("/api/v1/auth/verify-email", json={"token": verification_token})
    assert r1.status_code == 200
    
    # Try to verify again - should fail
    r2 = client.post("/api/v1/auth/verify-email", json={"token": verification_token})
    assert r2.status_code == 400  # Token already used / invalid


def test_resend_verification_endpoint(client):
    """Test that resend-verification can be called (requires auth)."""
    # Register a user first
    reg = client.post("/api/v1/auth/register", json={
        "email": "resend@example.com", "username": "resend", "password": "S3cret!pass",
    }).json()
    
    access_token = reg.get("access_token")
    assert access_token is not None
    
    # Resend verification (requires auth)
    r = client.post("/api/v1/auth/resend-verification", 
                    json={"email": "resend@example.com"},
                    headers={"Authorization": f"Bearer {access_token}"})
    
    # Should succeed (even if email delivery not configured)
    assert r.status_code == 200
    result = r.json()
    assert result.get("success") == True


def test_email_verified_field_in_user_payload(client):
    """Test that make_user_payload includes email_verified field."""
    from jarvis_backend.core import make_user_payload
    
    user = {"id": "1", "email": "test@example.com", "email_verified": True}
    payload = make_user_payload(user)
    assert "email_verified" in payload
    assert payload["email_verified"] == True
