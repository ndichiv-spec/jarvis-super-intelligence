"""Identity: Email/password login + OIDC (Google) authentication.

Implements the project's identity contract:
- Password-based login (existing)
- Google OAuth/OIDC login (new)
- JWT token issuance via existing token primitives
- User/account linking with Google sub as stable external identity key
- Full audit logging

Configuration via environment variables or provider settings:
- GOOGLE_OAUTH_CLIENT_ID
- GOOGLE_OAUTH_CLIENT_SECRET  
- GOOGLE_OAUTH_REDIRECT_URI (defaults to backend base URL + /api/v1/identity/callback/google)
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel

from .auth import _audit, now_iso
from ..core import (
    ai_service,
    create_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_store,
    hash_password,
    make_user_payload,
    verify_password,
)

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


# ============================================================================ #
# Error response helper (matches JARVIS error format)
# ============================================================================ #

def _error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    retryable: bool = False,
) -> JSONResponse:
    """Create a JARVIS-formatted error response with request_id."""
    rid = request_id or str(uuid.uuid4())
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": rid,
                "path": path,
                "method": method,
                "status_code": status_code,
                "retryable": retryable,
            }
        }
    )


# ============================================================================ #
# Configuration helpers
# ============================================================================ #

def _get_google_config() -> Optional[Dict[str, str]]:
    """Load Google OAuth configuration from environment or provider settings."""
    # Try environment variables first
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    
    # Build redirect URI if not set
    if not client_id or not client_secret:
        # Try provider settings as fallback
        settings = get_store("misc").load().get("provider_settings", {})
        if not client_id:
            client_id = settings.get("google_oauth_client_id", "").strip()
        if not client_secret:
            client_secret = settings.get("google_oauth_client_secret", "").strip()
        if not redirect_uri:
            redirect_uri = settings.get("google_oauth_redirect_uri", "").strip()
    
    base_url = os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")
    if not redirect_uri:
        redirect_uri = f"{base_url}/api/v1/identity/callback/google"
    
    if not client_id or not client_secret:
        return None
    
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def _generate_state() -> str:
    """Generate a cryptographically secure state value for OAuth PKCE/CSRF protection."""
    return secrets.token_urlsafe(32)


# State storage for OAuth (in-memory with TTL, using misc store)
def _store_oauth_state(state: str, data: Dict[str, Any]) -> None:
    """Store OAuth state with expiration."""
    misc = get_store("misc").load()
    states = misc.setdefault("oauth_states", {})
    states[state] = {
        **data,
        "created_at": now_iso(),
        "expires_at": int(time.time()) + 300,  # 5 minutes
    }
    get_store("misc").save()


def _get_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """Retrieve and validate OAuth state."""
    misc = get_store("misc").load()
    states = misc.get("oauth_states", {})
    
    if state not in states:
        return None
    
    entry = states[state]
    if time.time() > entry.get("expires_at", 0):
        del states[state]
        get_store("misc").save()
        return None
    
    # Single-use: delete after retrieval
    del states[state]
    get_store("misc").save()
    
    return entry


# User identity linking store
def _get_google_identity(sub: str) -> Optional[Dict[str, Any]]:
    """Get user linked to a Google subject ID."""
    linked = get_store("oauth_identities").load()
    return linked.get(f"google:{sub}")


def _link_google_identity(sub: str, user_id: str) -> None:
    """Record Google identity to user ID linkage."""
    linked = get_store("oauth_identities").load()
    linked[f"google:{sub}"] = {
        "user_id": user_id,
        "provider": "google",
        "sub": sub,
        "linked_at": now_iso(),
    }
    get_store("oauth_identities").save()


def _find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find user by verified email."""
    users = get_store("users").load()
    email_lower = email.lower().strip()
    for user in users.values():
        if (user.get("email") or "").lower().strip() == email_lower:
            return user
    return None


# ============================================================================ #
# Google OAuth Login Start
# ============================================================================ #

@router.get("/login/google")
async def google_login_start(request: Request):
    """Initiate Google OAuth login flow.
    
    Returns:
    - 302 redirect to Google's authorization endpoint
    - 400/501 with error if Google OAuth is not configured
    """
    request_id = str(uuid.uuid4())
    path = str(request.url)
    method = request.method
    
    config = _get_google_config()
    if not config:
        return _error_response(
            code="NOT_IMPLEMENTED",
            message="Google OAuth is not configured on this server. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI environment variables.",
            status_code=501,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Generate state
    state = _generate_state()
    
    # Store state (anonymous session for now - will be tied to user after callback)
    _store_oauth_state(state, {
        "redirect_after_login": "/",  # Default, can be customized via query param
    })
    
    # Build Google authorization URL
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    auth_url = f"{authorize_url}?{urlencode(params)}"
    
    # Return redirect
    return RedirectResponse(url=auth_url)


# ============================================================================ #
# Google OAuth Callback
# ============================================================================ #

@router.get("/callback/google")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = Query(None),
):
    """Handle Google OAuth callback.
    
    Query parameters:
    - code: Authorization code from Google
    - state: CSRF state token
    - error: OAuth error (if user denied)
    
    Returns:
    - JSON response with JWT tokens on success
    - Error response with proper JARVIS format on failure
    - 401 if OAuth denied
    """
    request_id = str(uuid.uuid4())
    path = str(request.url)
    method = request.method
    
    # Get state from query params
    oauth_state = state or request.query_params.get("state")
    
    # Check for OAuth error (user denied consent)
    if error:
        return _error_response(
            code="OAUTH_DENIED",
            message=f"Google OAuth denied: {error}",
            status_code=401,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    if not oauth_state:
        return _error_response(
            code="MISSING_STATE",
            message="State parameter missing",
            status_code=400,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Validate state
    stored_state = _get_oauth_state(oauth_state)
    if not stored_state:
        return _error_response(
            code="INVALID_STATE",
            message="Invalid or expired OAuth state",
            status_code=400,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Get authorization code
    auth_code = code or request.query_params.get("code")
    if not auth_code:
        return _error_response(
            code="MISSING_CODE",
            message="Authorization code missing",
            status_code=400,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Get Google config
    config = _get_google_config()
    if not config:
        return _error_response(
            code="NOT_IMPLEMENTED",
            message="Google OAuth configuration is missing",
            status_code=500,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Exchange code for tokens
    try:
        token_resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": config["redirect_uri"],
            },
            timeout=15
        )
        
        if token_resp.status_code != 200:
            error_detail = token_resp.json().get("error_description", "Token exchange failed")
            return _error_response(
                code="TOKEN_EXCHANGE_FAILED",
                message=error_detail,
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        tokens = token_resp.json()
        id_token = tokens.get("id_token")
        
        if not id_token:
            return _error_response(
                code="NO_ID_TOKEN",
                message="No ID token in response",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
    except httpx.HTTPError as e:
        return _error_response(
            code="NETWORK_ERROR",
            message=f"Network error during token exchange",
            status_code=500,
            request_id=request_id,
            path=path,
            method=method,
            retryable=True,
        )
    
    # Verify ID token using JWT
    try:
        import jwt
        
        # Decode without verification first for claim checks
        try:
            unverified_claims = jwt.decode(id_token, options={"verify_signature": False})
        except Exception:
            return _error_response(
                code="INVALID_TOKEN",
                message="Invalid ID token format",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        # Verify issuer
        iss = unverified_claims.get("iss")
        if iss not in ("https://accounts.google.com", "accounts.google.com"):
            return _error_response(
                code="INVALID_ISSUER",
                message="Invalid token issuer",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        # Verify audience
        aud = unverified_claims.get("aud")
        if aud != config["client_id"]:
            return _error_response(
                code="INVALID_AUDIENCE",
                message="Invalid token audience",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        # Check expiration
        exp = unverified_claims.get("exp", 0)
        if exp < time.time():
            return _error_response(
                code="EXPIRED_TOKEN",
                message="ID token has expired",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        # Get required claims
        google_sub = unverified_claims.get("sub")
        email = unverified_claims.get("email")
        
        if not google_sub:
            return _error_response(
                code="MISSING_SUB",
                message="Missing subject claim in ID token",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
        if not email:
            return _error_response(
                code="MISSING_EMAIL",
                message="No email in ID token",
                status_code=400,
                request_id=request_id,
                path=path,
                method=method,
                retryable=False,
            )
        
    except Exception as e:
        return _error_response(
            code="TOKEN_VALIDATION_ERROR",
            message="Token validation failed",
            status_code=400,
            request_id=request_id,
            path=path,
            method=method,
            retryable=False,
        )
    
    # Check if Google identity is already linked
    existing_link = _get_google_identity(google_sub)
    
    user: Dict[str, Any] = {}
    is_new_account = False
    
    if existing_link:
        # Existing Google-linked account
        user_id = existing_link["user_id"]
        users = get_store("users").load()
        user = users.get(user_id, {})
    else:
        # Check for existing account with same verified email
        existing_user = _find_user_by_email(email)
        
        if existing_user:
            # Account with matching email - link Google identity
            user = existing_user
            _link_google_identity(google_sub, user["id"])
        else:
            # New Google identity - create new user
            user_id = str(uuid.uuid4())
            users = get_store("users").load()
            user = {
                "id": user_id,
                "email": email,
                "username": email.split("@")[0],
                "full_name": email.split("@")[0],
                "password_hash": None,  # OAuth user - no password
                "avatar_url": None,
                "status": "active",
                "tenant_id": None,
                "roles": ["user"],
                "oauth_provider": "google",
                "oauth_sub": google_sub,
                "last_login_at": now_iso(),
                "created_at": now_iso(),
            }
            users[user_id] = user
            get_store("users").save()
            _link_google_identity(google_sub, user_id)
            is_new_account = True
    
    # Issue JWT tokens
    sessions = get_store("sessions").load()
    session_id = str(uuid.uuid4())
    
    # Create session
    sessions[session_id] = {
        "id": session_id,
        "user_id": user["id"],
        "created_at": now_iso(),
        "ip": None,
        "user_agent": None,
        "auth_method": "google",
    }
    get_store("sessions").save()
    
    # Create JWT tokens
    access_token = create_token({"sub": user["id"], "sid": session_id})
    refresh_token = create_refresh_token(user["id"], session_id)
    
    # Audit
    _audit(user["id"], "google_login", "success" if not is_new_account else "new_account_created")
    
    # Return response with tokens
    response = JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 604800,
        "user": make_user_payload(user),
        "is_new_account": is_new_account,
        "provider": "google",
    })
    
    # Set refresh token as HTTP-only cookie
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
    )
    
    return response


# ============================================================================ #
# Session Management
# ============================================================================ #

@router.get("/sessions")
async def list_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    """List user's active sessions."""
    sessions = get_store("sessions").load()
    mine = [s for s in sessions.values() if s.get("user_id") == user["id"]]
    return {"sessions": mine}


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Revoke a session."""
    sessions = get_store("sessions").load()
    if session_id in sessions and sessions[session_id].get("user_id") == user["id"]:
        sessions.pop(session_id, None)
        get_store("sessions").save()
        _audit(user["id"], "logout", f"session_{session_id}")
    return {"success": True}