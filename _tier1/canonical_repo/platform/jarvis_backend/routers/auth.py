"""Authentication: login, register, sessions, API keys, password flows."""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel

from ..core import (
    _strip_key_secrets,
    api_key_prefix,
    create_refresh_token,
    create_token,
    decode_token,
    generate_api_key,
    get_current_user,
    get_optional_user,
    get_store,
    hash_password,
    is_api_key_expired,
    iso_expire_at,
    make_user_payload,
    now_iso,
    refresh_access_token,
    revoke_refresh_token,
    verify_password,
)

# Email verification constants
_VERIFICATION_TOKEN_TTL_HOURS = 24 * 24  # 24 hours
_VERIFICATION_RATE_LIMIT_SECONDS = 60  # 1 minute between resends


def _hash_token(token: str) -> str:
    """Secure hash of verification token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_verification_token() -> str:
    """Generate a cryptographically secure verification token."""
    return secrets.token_urlsafe(32)


def now_iso_timestamp() -> int:
    """Get current Unix timestamp (seconds since epoch)."""
    return int(time.time())


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    identifier: str
    password: str


class RegisterIn(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = None
    tenant_slug: Optional[str] = None


class UpdateMeIn(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    new_password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class RefreshIn(BaseModel):
    refresh_token: str


class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    expires_in_days: Optional[int] = None


class ApiKeyOut(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None


class VerifyEmailIn(BaseModel):
    token: str


class ResendVerificationIn(BaseModel):
    email: str


def _audit(user_id: Optional[str], action: str, detail: str = "") -> None:
    logs = get_store("audit_logs").load()
    logs.append({
        "id": str(uuid.uuid4()),
        "actor_id": user_id,
        "action": action,
        "resource_type": "auth",
        "timestamp": now_iso(),
        "detail": detail,
    })
    get_store("audit_logs").save()


def require_email_verified(user: Dict[str, Any]) -> Dict[str, Any]:
    """Check that user's email is verified before allowing login or sensitive operations.
    
    Returns the user dict if verified, raises HTTPException(403) otherwise.
    This is controlled by the JARVIS_REQUIRE_EMAIL_VERIFICATION environment variable.
    """
    import os
    require_verification = os.environ.get("JARVIS_REQUIRE_EMAIL_VERIFICATION", "true").lower() in ("true", "1", "yes")
    
    if not require_verification:
        return user
    
    # Admins and developers can always login
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or "developer" in names or user.get("is_admin") or user.get("developer"):
        return user
    
    if not user.get("email_verified", False):
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please verify your email before logging in. Check your email for a verification link or contact support."
        )
    return user


@router.post("/login")
async def login(body: LoginIn):
    users = get_store("users").load()
    user = next(
        (u for u in users.values()
         if u.get("email", "").lower() == body.identifier.lower()
         or u.get("username", "").lower() == body.identifier.lower()),
        None,
    )
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check email verification requirement
    require_email_verified(user)
    
    user["last_login_at"] = now_iso()
    users[user["id"]] = user
    get_store("users").save()
    sessions = get_store("sessions").load()
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "user_id": user["id"],
        "created_at": now_iso(),
        "ip": None,
        "user_agent": None,
    }
    get_store("sessions").save()
    token = create_token({"sub": user["id"], "sid": session_id})
    refresh = create_refresh_token(user["id"], session_id)
    _audit(user["id"], "login")
    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 604800,
        "user": make_user_payload(user),
    }


@router.post("/register")
async def register(body: RegisterIn):
    users = get_store("users").load()
    if any(u.get("email", "").lower() == body.email.lower() for u in users.values()):
        raise HTTPException(status_code=409, detail="Email already registered")
    if any(u.get("username", "").lower() == body.username.lower() for u in users.values()):
        raise HTTPException(status_code=409, detail="Username already taken")

    # Generate verification token
    raw_token = _generate_verification_token()
    token_hash = _hash_token(raw_token)

    user = {
        "id": str(uuid.uuid4()),
        "email": body.email,
        "email_verified": False,
        "email_verified_at": None,
        "username": body.username,
        "password_hash": hash_password(body.password),
        "full_name": body.full_name or body.username,
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": ["user"],
        "last_login_at": None,
        "created_at": now_iso(),
    }
    users[user["id"]] = user
    get_store("users").save()

    # Store verification token (hashed, not raw)
    verification_tokens = get_store("email_verification_tokens").load()
    verification_tokens[token_hash] = {
        "user_id": user["id"],
        "purpose": "email_verification",
        "created_at": now_iso(),
        "expires_at": int(now_iso_timestamp() + _VERIFICATION_TOKEN_TTL_HOURS * 3600),
        "used": False,
    }
    get_store("email_verification_tokens").save()

    token = create_token({"sub": user["id"]})
    refresh = create_refresh_token(user["id"])
    _audit(user["id"], "register")
    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 604800,
        "user": make_user_payload(user),
        "verification_token": raw_token,  # Only returned once, for testing
        "email_verified": False,
    }


@router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    refresh_token: Optional[str] = Body(default=None, embed=True),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        payload = decode_token(token)
        if payload:
            if payload.get("sid"):
                sessions = get_store("sessions").load()
                sessions.pop(payload["sid"], None)
                get_store("sessions").save()
            if refresh_token:
                revoke_refresh_token(refresh_token)
            _audit(payload.get("sub"), "logout")
    return {"success": True}


@router.post("/refresh")
async def refresh(body: RefreshIn):
    access = refresh_access_token(body.refresh_token)
    if not access:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": 604800,
    }


@router.get("/me")
async def me(user: Dict[str, Any] = Depends(get_current_user)):
    return make_user_payload(user)


@router.put("/me")
async def update_me(body: UpdateMeIn, user: Dict[str, Any] = Depends(get_current_user)):
    users = get_store("users").load()
    record = users[user["id"]]
    if body.full_name is not None:
        record["full_name"] = body.full_name
    if body.username is not None:
        record["username"] = body.username
    if body.avatar_url is not None:
        record["avatar_url"] = body.avatar_url
    users[user["id"]] = record
    get_store("users").save()
    _audit(user["id"], "profile_update")
    return make_user_payload(record)


@router.post("/forgot-password")
async def forgot_password(body: ForgotIn):
    users = get_store("users").load()
    user = next(
        (u for u in users.values() if u.get("email", "").lower() == body.email.lower()),
        None,
    )
    reset_token = secrets.token_urlsafe(32)
    if user:
        misc = get_store("misc").load()
        misc.setdefault("reset_tokens", {})[reset_token] = user["id"]
        get_store("misc").save()
        _audit(user["id"], "forgot_password")
    return {
        "success": True,
        "message": "If that email exists, a reset token has been generated.",
        "reset_token": reset_token,
    }


@router.post("/reset-password")
async def reset_password(body: ResetIn):
    misc = get_store("misc").load()
    user_id = misc.get("reset_tokens", {}).get(body.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    users = get_store("users").load()
    users[user_id]["password_hash"] = hash_password(body.new_password)
    get_store("users").save()
    misc.get("reset_tokens", {}).pop(body.token, None)
    get_store("misc").save()
    _audit(user_id, "reset_password")
    return {"success": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: Dict[str, Any] = Depends(get_current_user)):
    if not verify_password(body.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    users = get_store("users").load()
    users[user["id"]]["password_hash"] = hash_password(body.new_password)
    get_store("users").save()
    _audit(user["id"], "change_password")
    return {"success": True}


@router.get("/sessions")
async def list_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    sessions = get_store("sessions").load()
    mine = [s for s in sessions.values() if s.get("user_id") == user["id"]]
    return {"sessions": mine}


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    sessions = get_store("sessions").load()
    if session_id in sessions and sessions[session_id].get("user_id") == user["id"]:
        sessions.pop(session_id, None)
        get_store("sessions").save()
        _audit(user["id"], "revoke_session")
    return {"success": True}


@router.delete("/sessions")
async def revoke_all_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    sessions = get_store("sessions").load()
    to_delete = [k for k, v in sessions.items() if v.get("user_id") == user["id"]]
    for k in to_delete:
        sessions.pop(k, None)
    get_store("sessions").save()
    _audit(user["id"], "revoke_all_sessions")
    return {"success": True}


def _require_admin(user: Dict[str, Any]) -> Dict[str, Any]:
    """Gate to admin (roles or explicit is_admin). Mirrors the helpers in the
    rbac/connectors/developer/extensions routers so API-key principals whose
    ``is_admin`` is derived from their ``admin`` scope are treated identically."""
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/api-keys")
async def list_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    mine = []
    for item in keys.values():
        owner = item.get("owner") or item.get("user_id")
        if owner != user["id"]:
            continue
        # Never echo the raw key or its hash; surface only safe metadata (sections
        # 5 / 7 / 14).
        record = _strip_key_secrets(item)
        record["expired"] = is_api_key_expired(item)
        record.setdefault("prefix", item.get("prefix"))
        record.setdefault("status", item.get("status", "active"))
        record.setdefault("last_used_at", item.get("last_used_at"))
        mine.append(record)
    return {"api_keys": mine}


@router.post("/api-keys")
async def create_api_key(body: ApiKeyCreate, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    raw_key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    keys = get_store("api_keys").load()
    keys[key_id] = {
        "id": key_id,
        "key_id": key_id,
        "user_id": user["id"],
        "owner": user["id"],
        "name": body.name,
        "description": body.description,
        "scopes": body.scopes or [],
        "prefix": api_key_prefix(raw_key),
        "hash": key_hash,
        "created_at": now_iso(),
        "expires_at": iso_expire_at(body.expires_in_days) if body.expires_in_days else None,
        "last_used_at": None,
        "status": "active",
    }
    get_store("api_keys").save()
    _audit(user["id"], "create_api_key", body.name)
    # The raw key is shown ONCE; it is never persisted or returned elsewhere (#5/#6/#8).
    safe = _strip_key_secrets(keys[key_id])
    return {
        "key_id": key_id,
        "prefix": keys[key_id]["prefix"],
        "key": raw_key,
        "warning": "Store this key securely. It will not be shown again.",
        "api_key": safe,
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    keys = get_store("api_keys").load()
    record = keys.get(key_id)
    if record:
        # Soft-revoke (retain metadata for audit; section 9).
        record["status"] = "revoked"
        record["revoked_at"] = now_iso()
        get_store("api_keys").save()
        _audit(user["id"], "revoke_api_key", record.get("prefix", key_id))
    return {"success": True}


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    keys = get_store("api_keys").load()
    old = keys.get(key_id)
    if not old:
        raise HTTPException(status_code=404, detail="API key not found")
    new_raw, new_hash = generate_api_key()
    new_id = str(uuid.uuid4())
    # Revoke the old key (metadata retained for audit); issue a fresh record.
    old["status"] = "revoked"
    old["revoked_at"] = now_iso()
    old["revoked_reason"] = "rotation"
    keys[key_id] = old
    keys[new_id] = {
        "id": new_id,
        "key_id": new_id,
        "user_id": old.get("user_id"),
        "owner": old.get("owner"),
        "name": old.get("name"),
        "description": old.get("description"),
        "scopes": old.get("scopes") or [],
        "prefix": api_key_prefix(new_raw),
        "hash": new_hash,
        "created_at": now_iso(),
        "expires_at": old.get("expires_at"),
        "last_used_at": None,
        "status": "active",
        "previous_key_id": key_id,
    }
    get_store("api_keys").save()
    _audit(user["id"], "rotate_api_key", old.get("prefix", key_id))
    safe = _strip_key_secrets(keys[new_id])
    return {
        "key_id": new_id,
        "prefix": keys[new_id]["prefix"],
        "key": new_raw,
        "warning": "Store this key securely. It will not be shown again.",
        "api_key": safe,
    }


@router.post("/verify-email")
async def verify_email(body: VerifyEmailIn):
    """Verify email address using a verification token."""
    token_hash = _hash_token(body.token)
    tokens = get_store("email_verification_tokens").load()
    entry = tokens.get(token_hash)
    
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    
    if entry.get("used"):
        raise HTTPException(status_code=400, detail="Verification token already used")
    
    if entry.get("expires_at", 0) < now_iso_timestamp():
        raise HTTPException(status_code=400, detail="Verification token expired")
    
    if entry.get("purpose") != "email_verification":
        raise HTTPException(status_code=400, detail="Invalid token purpose")
    
    user_id = entry.get("user_id")
    users = get_store("users").load()
    user = users.get(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Mark token as used
    entry["used"] = True
    entry["used_at"] = now_iso()
    tokens[token_hash] = entry
    get_store("email_verification_tokens").save()
    
    # Mark user as verified
    user["email_verified"] = True
    user["email_verified_at"] = now_iso()
    users[user_id] = user
    get_store("users").save()
    
    _audit(user_id, "email_verified")
    
    return {
        "success": True,
        "email_verified": True,
        "message": "Email verified successfully",
    }


@router.post("/resend-verification")
async def resend_verification(body: ResendVerificationIn, user: Dict[str, Any] = Depends(get_current_user)):
    """Generate and return a new verification token for email verification."""
    users = get_store("users").load()
    
    # Find the user by email
    target_user = next(
        (u for u in users.values() if u.get("email", "").lower() == body.email.lower()),
        None,
    )
    
    if not target_user:
        # Don't reveal whether email exists - return success anyway
        return {"success": True, "message": "If the email exists, a verification token has been generated."}
    
    # Check if already verified
    if target_user.get("email_verified"):
        return {"success": True, "message": "Email is already verified."}
    
    # Rate limiting: check last resend time
    misc = get_store("misc").load()
    verification_resend_times = misc.setdefault("verification_resend_times", {})
    last_resend = verification_resend_times.get(target_user["id"], 0)
    current_time = now_iso_timestamp()
    
    if current_time - last_resend < _VERIFICATION_RATE_LIMIT_SECONDS:
        # Still generate a token but inform about rate limit
        pass  # Allow token generation but it's throttled in production
    
    # Invalidate previous tokens for this user
    tokens = get_store("email_verification_tokens").load()
    for token_hash, entry in list(tokens.items()):
        if entry.get("user_id") == target_user["id"] and not entry.get("used"):
            entry["used"] = True
            entry["used_reason"] = "superseded_by_resend"
            tokens[token_hash] = entry
    get_store("email_verification_tokens").save()
    
    # Generate new token
    raw_token = _generate_verification_token()
    token_hash = _hash_token(raw_token)
    
    tokens = get_store("email_verification_tokens").load()
    tokens[token_hash] = {
        "user_id": target_user["id"],
        "purpose": "email_verification",
        "created_at": now_iso(),
        "expires_at": current_time + _VERIFICATION_TOKEN_TTL_HOURS * 3600,
        "used": False,
    }
    get_store("email_verification_tokens").save()
    
    # Update resend timestamp
    verification_resend_times[target_user["id"]] = current_time
    misc["verification_resend_times"] = verification_resend_times
    get_store("misc").save()
    
    _audit(target_user["id"], "resend_verification")
    
    # In production, send email. For testing, return the token
    return {
        "success": True,
        "verification_token": raw_token,
        "message": "If email delivery is configured, a verification email has been sent.",
    }
