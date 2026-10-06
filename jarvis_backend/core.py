"""JARVIS backend core.

Shared infrastructure for the JARVIS API:
  - a file-backed JSON persistence layer (no external DB required)
  - JWT authentication (registration / login / sessions / API keys)
  - an AI service that routes to the real ProviderGateway (OpenAI / Google /
    NVIDIA / Silverwing / Brain) or a truthful offline status message —
    never a canned or fabricated response
  - the single FastAPI application object and its wiring
"""

from __future__ import annotations

import asyncio
import base64
import datetime as _dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.middleware.base import BaseHTTPMiddleware

from .db import create_db_and_tables, kv_load, kv_save, reset_database
from .secret_config import read_secret

logger = logging.getLogger("jarvis.backend")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "jarvis_data"
UPLOADS_DIR = ROOT / "jarvis_uploads"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# The signing key MUST be provided in production. In dev it is generated
# ephemerally (rotated on every restart) so there is never an insecure
# hardcoded default committed to source.
#
# ``_SECRET_KEY`` is cached at import time for backward-compatibility with
# tests that import it directly (see test_auth.py::test_no_insecure_default_secret).
# At runtime, ``_signing_key()`` reads ``JARVIS_SECRET_KEY`` from ``os.environ``
# on each call so that a key loaded from .env *after* module import (e.g. by
# main.py's load_dotenv() which runs before any request is served) is used
# instead of a stale ephemeral value.
_SECRET_KEY = os.environ.get("JARVIS_SECRET_KEY")
if not _SECRET_KEY:
    _SECRET_KEY = secrets.token_urlsafe(32)
_TOKEN_TTL_HOURS = 1               # access tokens; refresh tokens are separately rotated
_REFRESH_TTL_HOURS = 24 * 60       # refresh tokens (long-lived, revocable)


def _signing_key() -> str:
    """Resolve the JWT signing key at call time.

    Prefers ``JARVIS_SECRET_KEY`` from the live environment (so that a key
    loaded from ``.env`` by ``main.py`` / ``jarvis_api.py`` after this module
    was imported is used) and falls back to the import-time ``_SECRET_KEY``
    cache (ephemeral dev key or a value explicitly set before import, e.g. by
    tests). This keeps token signing consistent across restarts while staying
    transparent to unit tests.
    """
    env_key = read_secret("JARVIS_SECRET_KEY")
    if env_key:
        return env_key
    return _SECRET_KEY


# --------------------------------------------------------------------------- #
# Environment / admin identity configuration
# --------------------------------------------------------------------------- #
_ENV_PRODUCTION = {"production", "prod"}


def is_production() -> bool:
    """True when ``JARVIS_ENV`` is set to a production value.

    Production mode is opt-in (must be explicitly declared). When active,
    insecure development defaults are rejected so the platform fails fast
    rather than silently running with placeholders.
    """
    return os.environ.get("JARVIS_ENV", "").strip().lower() in _ENV_PRODUCTION


def admin_email() -> str:
    """Resolve the admin account email used for the seeded admin login.

    * ``JARVIS_ADMIN_EMAIL`` env var wins when set (development *or* production).
    * In development (the default) the legacy ``admin@jarvis.local`` placeholder
      is used so a fresh install always has a working first sign-in.
    * In production a real org address is **required** — there is no hardcoded
      insecure default — and a clear ``RuntimeError`` is raised so the
      misconfiguration fails fast at startup instead of seeding an unusable
      placeholder admin. This is also asserted by the security regression suite.
    """
    email = (os.environ.get("JARVIS_ADMIN_EMAIL") or "").strip()
    if email:
        return email
    if is_production():
        raise RuntimeError(
            "JARVIS_ADMIN_EMAIL is required in production (set JARVIS_ENV=production "
            "and a real admin email). Refusing to seed the admin account with the "
            "hardcoded development placeholder 'admin@jarvis.local'."
        )
    return "admin@jarvis.local"


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
# The Store layer is backed by SQL (see :mod:`jarvis_backend.db`) rather than
# per-collection JSON files.  Each logical collection (``users``,
# ``sessions``, ``refresh_tokens``, ``chat_sessions`` ...) lives as rows in the
# ``jarvis_kv`` table, so data survives process restarts and can be hosted on
# SQLite (default) or Postgres (``DATABASE_URL``).  The dict/list load()/save()
# contract is preserved so existing call-sites are unaffected.
class Store:
    """SQL-backed collection store preserving the legacy load()/save() API.

    * ``load()`` returns a mutable dict (keyed by id) or list (ordered),
      cached in-process and populated from the SQL backend on first access.
    * ``save()`` flushes the in-memory collection back to SQL.
    * ``save()`` performs a replace-all for the collection (matches the prior
      JSON semantics): the whole collection is reconciled atomically.
    """

    def __init__(self, name: str, default_factory: Optional[callable] = None) -> None:
        self.name = name
        self._default_factory = default_factory or (lambda: {})
        self._is_list = self._default_factory is list
        self._lock = asyncio.Lock()
        self._data: Any = None

    def _load_sync(self) -> Any:
        return kv_load(self.name, self._default_factory)

    def _save_sync(self, data: Any) -> None:
        kv_save(self.name, data)

    def reload(self) -> Any:
        """Refresh this process's snapshot from the shared SQL store."""
        self._data = self._load_sync()
        return self._data

    def save_key(self, key: str, value: Any) -> None:
        """Persist one dictionary record without replacing other writers' data."""
        if self._is_list:
            raise TypeError("save_key is only supported for dictionary stores")
        from .db import kv_set

        kv_set(self.name, str(key), value)
        if isinstance(self._data, dict):
            self._data[str(key)] = value

    def update_key(self, key: str, transform: Any) -> Any:
        """Atomically transform and persist one dictionary record."""
        if self._is_list:
            raise TypeError("update_key is only supported for dictionary stores")
        from .db import kv_update

        updated_value = kv_update(self.name, str(key), transform)
        if isinstance(self._data, dict) and updated_value is not None:
            self._data[str(key)] = updated_value
        return updated_value

    def load(self) -> Any:
        if self._data is None:
            self._data = self._load_sync()
        return self._data

    def save(self) -> None:
        if self._data is not None:
            self._save_sync(self._data)

    def reset(self) -> None:
        """Drop and re-create this collection's rows (used by tests)."""
        self._data = self._default_factory()
        self._save_sync(self._data)


# Collection stores keyed by string id
data: Dict[str, Store] = {}

STORES = {
    "users": dict,
    "sessions": dict,
    "refresh_tokens": dict,
    "oauth_identities": dict,
    "api_keys": dict,
    "knowledge": dict,
    "memory": dict,
    "bio_learning": dict,
    "agents": dict,
    "tasks": dict,
    "missions": dict,
    "commands": dict,
    "command_events": list,
    "executions": list,
    # Phase 11 — Laboratory
    "experiments": dict,
    "datasets": dict,
    "evaluation_suites": dict,
    # Phase 12 — Self-Improvement Engine
    "improvements": dict,
    "roles": dict,
    "permissions": dict,
    "audit_logs": list,
    "notes": dict,
    "reminders": dict,
    "chat_sessions": dict,
    "chat_history": dict,
    "collab_tasks": dict,
    "multimodal_files": dict,
    "rss_feeds": dict,
    "tenant": dict,
    "misc": dict,
    # Email verification tokens (never stores raw tokens, only hashed)
    "email_verification_tokens": dict,
    # Browser infrastructure state
    "browser_sessions": dict,
    "browser_tabs": dict,
    "browser_bookmarks": dict,
    "browser_history": list,
    "browser_downloads": list,
    "browser_evidence": list,
    # Browser AI-native execution layer (spec §3–§42)
    "browser_actions": dict,
    "browser_action_queues": dict,
    "browser_page_states": dict,
    "browser_tasks": dict,
    "browser_checkpoints": dict,
    "browser_workspaces": dict,
    "browser_telemetry": list,
    "browser_source_graph": dict,
    "browser_timeline": list,
    # Browser Network Intelligence Layer (spec §51)
    "browser_network_events": list,
    "browser_navigation_timeline": list,
    "browser_health": list,
    # Global Search infrastructure (spec §26-31)
    "search_history": list,          # recent + saved searches (spec §44)
    "browser_semantic_cache": dict,  # cached embedding vectors (spec §49)
}


def get_store(name: str) -> Store:
    if name not in data:
        data[name] = Store(name, STORES.get(name, dict))
    return data[name]


# --------------------------------------------------------------------------- #
# Password hashing (HMAC-SHA256, no external deps)
# --------------------------------------------------------------------------- #
_PBKDF2_ITERATIONS = 200_000
_ARGON2_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    """Hash new passwords with Argon2id; verification retains legacy support.

    Existing PBKDF2 and legacy HMAC hashes remain verifiable and are upgraded
    after a successful login.
    """
    return _ARGON2_PASSWORD_HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2id$"):
        try:
            return _ARGON2_PASSWORD_HASHER.verify(stored, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        _, iterations, salt, digest = parts
        try:
            computed = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
            ).hex()
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(computed, digest)
    # Legacy single-round HMAC-SHA256 fallback (migration path).
    if len(parts) == 2:
        salt, digest = parts
        expected = hmac.new(
            salt.encode(), password.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, digest)
    return False


def password_hash_needs_upgrade(stored: str) -> bool:
    if not stored.startswith("$argon2id$"):
        return True
    try:
        return _ARGON2_PASSWORD_HASHER.check_needs_rehash(stored)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# JWT (minimal, no external deps)
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_token(payload: Dict[str, Any], ttl_hours: int = _TOKEN_TTL_HOURS) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["iat"] = int(time.time())
    body["exp"] = int(time.time()) + ttl_hours * 3600
    seg_header = _b64url(json.dumps(header).encode())
    seg_body = _b64url(json.dumps(body).encode())
    signing_input = f"{seg_header}.{seg_body}".encode()
    sig = _b64url(hmac.new(_signing_key().encode(), signing_input, hashlib.sha256).digest())
    return f"{seg_header}.{seg_body}.{sig}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        signing_input = f"{header}.{body}".encode()
        expected = _b64url(hmac.new(_signing_key().encode(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Refresh tokens (rotating, revocable; access tokens are short-lived)
# --------------------------------------------------------------------------- #
def create_refresh_token(user_id: str, session_id: Optional[str] = None) -> str:
    """Issue a revocable refresh token bound to a user (and optional session)."""
    jti = secrets.token_urlsafe(32)
    payload = {"sub": user_id, "jti": jti}
    if session_id:
        payload["sid"] = session_id
    store = get_store("refresh_tokens").load()
    store[jti] = {
        "user_id": user_id,
        "session_id": session_id,
        "exp": int(time.time()) + _REFRESH_TTL_HOURS * 3600,
    }
    get_store("refresh_tokens").save()
    return create_token(payload, ttl_hours=_REFRESH_TTL_HOURS)


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Mint a new access token from a valid, non-expired refresh token."""
    payload = decode_token(refresh_token)
    if not payload or not payload.get("jti"):
        return None
    jti = payload["jti"]
    store = get_store("refresh_tokens").load()
    entry = store.get(jti)
    if not entry or entry.get("exp", 0) < int(time.time()):
        store.pop(jti, None)
        get_store("refresh_tokens").save()
        return None
    access = {"sub": entry["user_id"]}
    if entry.get("session_id"):
        access["sid"] = entry["session_id"]
    return create_token(access, ttl_hours=_TOKEN_TTL_HOURS)


def rotate_refresh_token(refresh_token: str) -> Optional[tuple[str, str]]:
    """Validate and consume a refresh token, issuing a new access/refresh pair."""
    payload = decode_token(refresh_token)
    if not payload or not payload.get("jti"):
        return None
    jti = payload["jti"]
    store = get_store("refresh_tokens").load()
    entry = store.get(jti)
    if not entry or entry.get("exp", 0) < int(time.time()):
        return None

    account = get_store("users").load().get(entry.get("user_id"))
    if account and (
        account.get("email_verified") is False
        or account.get("status") in {"disabled", "suspended", "deleted"}
    ):
        store.pop(jti, None)
        get_store("refresh_tokens").save()
        return None

    session_id = entry.get("session_id")
    if session_id:
        session = get_store("sessions").load().get(session_id)
        if not session or session.get("user_id") != entry.get("user_id"):
            store.pop(jti, None)
            get_store("refresh_tokens").save()
            return None

    store.pop(jti, None)
    get_store("refresh_tokens").save()
    access_claims = {"sub": entry["user_id"]}
    if session_id:
        access_claims["sid"] = session_id
    return (
        create_token(access_claims, ttl_hours=_TOKEN_TTL_HOURS),
        create_refresh_token(entry["user_id"], session_id),
    )


def revoke_refresh_token(refresh_token: str) -> bool:
    """Invalidate a refresh token (used on logout)."""
    payload = decode_token(refresh_token)
    if not payload:
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    store = get_store("refresh_tokens").load()
    if jti in store:
        store.pop(jti, None)
        get_store("refresh_tokens").save()
        return True
    return False
def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[7:].strip()
    # API-key bearer tokens ("jarvis_..."): one-way hash verification. Raw keys
    # are never persisted or recoverable from the KV store (sections 8/14/20).
    if token.startswith(API_KEY_PREFIX):
        key = find_api_key(token)
        if not key or is_api_key_expired(key):
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        return _api_key_principal(key)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    users = get_store("users").load()
    user = users.get(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    if user.get("email_verified") is False:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "EMAIL_VERIFICATION_REQUIRED",
                "message": "Verify your email address before using this account.",
            },
        )
    if user.get("status") in {"disabled", "suspended", "deleted"}:
        raise HTTPException(status_code=403, detail="Account is disabled")
    session_id = payload.get("sid")
    if session_id:
        session = get_store("sessions").load().get(session_id)
        if not session or session.get("user_id") != user.get("id"):
            raise HTTPException(status_code=401, detail="Session is revoked or expired")
    return user


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None


# --------------------------------------------------------------------------- #
# Centralized authorization helpers (SEC-1 — unified security boundary)
# --------------------------------------------------------------------------- #
def _require_auth(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Any authenticated user may access the endpoint."""
    return user


def is_admin(user: Dict[str, Any]) -> bool:
    """True when ``user`` holds the admin role or an owner wildcard (``*``).

    Single source of truth for the privileged-host tier (SEC-1 unified
    authorization boundary). ``_require_admin`` delegates here so admin
    resolution is never duplicated. Preserves the historical logic (admin role
    / explicit ``is_admin`` / owner ``*`` permission) for behavioural parity.
    """
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return True
    role_names = set(names)
    for role in get_store("roles").load().values():
        if role.get("name") in role_names or role.get("id") in role_names:
            if "*" in (role.get("permissions") or []):
                return True
    return False


def is_developer(user: Dict[str, Any]) -> bool:
    """True when ``user`` is a developer, admin, or owner (automation tier)."""
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "developer" in names or "admin" in names or user.get("is_admin"):
        return True
    return is_admin(user)


def _require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Gate a route to users holding the admin role (privileged-host tier).

    Delegates to :func:`is_admin` (the single source of truth) so API-key
    principals whose ``is_admin`` is derived from their admin scope are treated
    identically across routers. Behaviour is identical to the prior inline
    implementation.
    """
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _require_owner(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Gate a route to the canonical owner only."""
    owner_email = admin_email().lower().strip()
    if (user.get("email") or "").lower().strip() == owner_email:
        return user
    raise HTTPException(status_code=403, detail="Owner access required")


# --------------------------------------------------------------------------- #
# System audit helper (SEC-1 — audit every sensitive action)
# --------------------------------------------------------------------------- #
def _audit_system_action(status: str, action: str, resource: str,
                         user_email: str = "", detail: str = "") -> None:
    """Append a system-security audit entry (no secrets ever recorded)."""
    try:
        log = get_store("audit_logs").load()
        if not isinstance(log, list):
            log = []
        log.append({
            "ts": now_iso(),
            "kind": "system_security",
            "status": status,
            "action": action,
            "resource": resource,
            "user": user_email,
            "detail": detail,
        })
        get_store("audit_logs").save()
    except Exception:  # noqa: BLE001 — audit must never break a request
        pass


def _migrate_legacy_provider_secrets() -> int:
    """SEC-1 §6 — encrypt any plaintext provider secrets at rest.

    ``provider-settings`` PUT rejects secret-shaped fields, so no *new*
    plaintext is written. This migrates *legacy* plaintext values that may
    already sit in ``misc.provider_settings`` into Fernet ciphertext via
    :mod:`jarvis_backend.connectors.crypto`, preserving the existing
    ``fernet:`` format so legacy ciphertext stays readable. Truthiness is
    preserved (a ``fernet:...`` token is non-empty) so capability/dashboard
    "configured" presence checks are unaffected, and no plaintext value is
    ever returned by the scrubbed provider-settings API.
    """
    try:
        from .connectors.crypto import encrypt_secret
    except Exception:  # noqa: BLE001 — crypto backend optional at this layer
        return 0
    try:
        misc = get_store("misc").load()
    except Exception:  # noqa: BLE001
        return 0
    settings = misc.get("provider_settings")
    if not isinstance(settings, dict):
        return 0
    secret_shape = ("key", "secret", "token", "password")
    migrated = 0
    for key, value in list(settings.items()):
        if not isinstance(value, str) or not value:
            continue
        if value.startswith("fernet:") or value.startswith("env:"):
            continue  # already canonical
        lkey = key.lower()
        if any(s in lkey for s in secret_shape):
            settings[key] = encrypt_secret(value)
            migrated += 1
    if migrated:
        get_store("misc").save()
    return migrated


def make_user_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "email_verified": user.get("email_verified", False),
        "email_verified_at": user.get("email_verified_at"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "avatar_url": user.get("avatar_url"),
        "status": user.get("status", "active"),
        "tenant_id": user.get("tenant_id"),
        "last_login_at": user.get("last_login_at"),
        "created_at": user.get("created_at"),
    }


def now_iso() -> str:
    # Timezone-aware UTC. ``datetime.utcnow()`` is deprecated in 3.12+ and
    # returns a naive datetime that can silently be mis-compared against
    # timezone-aware values. We keep the legacy ``Z`` suffix so existing
    # parsers (and tests) that accept ISO-8601-UTC are unaffected.
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def now() -> _dt.datetime:
    # Timezone-aware UTC (see now_iso). ``_dt.utcnow()`` is deprecated.
    return _dt.datetime.now(_dt.timezone.utc)


def _iso_to_epoch(value: Any) -> float:
    """Parse a timestamp that may be an ISO-8601 string *or* a numeric epoch.

    Robust to: ``Z`` / ``+00:00`` suffixes, naive strings, and bare numbers.
    Returns ``0.0`` for anything unparseable so callers can treat failure as
    "not expired / unknown" rather than crashing.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    norm = s.replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(norm).timestamp()
    except ValueError:
        return 0.0


def iso_expire_at(days: int) -> str:
    """Future ISO-8601 UTC timestamp `days` from now (minimum 1 day)."""
    days = max(1, int(days or 0))
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")


def is_api_key_expired(key: Dict[str, Any], grace_seconds: float = 0.0) -> bool:
    """True if a stored API key record's ``expires_at`` is in the past.

    A key with no ``expires_at`` is treated as non-expiring. ``grace_seconds``
    lets callers treat near-expiry keys as expired (used by the listing API to
    flag keys about to roll over).
    """
    exp = key.get("expires_at")
    if exp is None:
        return False
    return _iso_to_epoch(exp) < time.time() + grace_seconds


# --------------------------------------------------------------------------- #
# API-key at-rest protection (spec sections 8 / 14 / 20)
# --------------------------------------------------------------------------- #
# Raw API keys are NEVER persisted. We store a one-way PBKDF2-HMAC-SHA256 hash
# (the project existing, stdlib-only password-hashing mechanism -- see
# hash_password / verify_password above). Argon2id would be preferred but is
# unavailable in this runtime (argon2-cffi not installed); per section 3 we
# reuse the existing approved PBKDF2 stack rather than introducing redundant
# cryptography. Each key gets a unique random salt (via hash_password).
API_KEY_PREFIX = "jarvis_"
_API_KEY_HEX_LEN = 32            # 256 bits of entropy after the prefix
_API_KEY_PREFIX_HEX = 8          # safe display/identification prefix (first 8 hex)


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns (raw_key, key_hash). The caller shows raw_key to the admin ONCE
    and discards it; only key_hash is persisted.
    """
    raw = API_KEY_PREFIX + secrets.token_hex(_API_KEY_HEX_LEN)
    return raw, hash_api_key(raw)


def hash_api_key(raw_key: str) -> str:
    """One-way hash of a raw API key for at-rest storage (PBKDF2-HMAC-SHA256)."""
    return hash_password(raw_key)


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time verification of a supplied API key against its stored hash."""
    if not stored_hash or not str(stored_hash).startswith("pbkdf2_sha256$"):
        return False
    return verify_password(raw_key, stored_hash)


def api_key_prefix(raw_key: str) -> str:
    """Safe display/identification prefix, e.g. jarvis_ab12cd34.

    Only the prefix is stored/shown in admin and audit logs; the full key is
    never persisted, and the prefix is NOT used for authentication (section 5).
    """
    body = raw_key[len(API_KEY_PREFIX):] if raw_key.startswith(API_KEY_PREFIX) else raw_key
    return API_KEY_PREFIX + body[:_API_KEY_PREFIX_HEX]


def _api_key_principal(key_record: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve an authenticated API-key record to a user principal.

    Authority comes from the key scopes (e.g. ["admin"]), NOT from the owning
    user roles -- a low-scope key cannot escalate by borrowing its owner admin
    role. The principal carries the owner identity so routes that lookup
    user["id"] keep working.
    """
    users = get_store("users").load()
    owner_id = key_record.get("owner") or key_record.get("user_id") or ""
    owner = users.get(owner_id) if owner_id else None
    principal: Dict[str, Any] = dict(owner or {})
    if owner is None:
        principal.setdefault("id", owner_id or key_record.get("key_id"))
        principal.setdefault("email", "api-key")
        principal.setdefault("username", "api-key")
    principal["roles"] = []  # keys derive authority from scopes, not owner roles
    principal["is_admin"] = "admin" in (key_record.get("scopes") or [])
    principal["api_key_id"] = key_record.get("key_id") or key_record.get("id")
    principal["scopes"] = key_record.get("scopes") or []
    return principal


def find_api_key(supplied: str) -> Optional[Dict[str, Any]]:
    """Resolve a supplied raw API key to its record, verifying the hash.

    Candidate lookup is prefix-based (section 5); the real authentication is
    the constant-time hash comparison. Revoked/disabled/expired keys are never
    returned. Legacy plaintext records (stray "key" field, no "hash") are
    verified with hmac.compare_digest and lazily migrated to a hash, after
    which the plaintext is dropped -- never logged or re-persisted (section 12).
    """
    if not supplied or not supplied.startswith(API_KEY_PREFIX):
        return None
    keys = get_store("api_keys").load()
    for record in keys.values():
        if record.get("status", "active") in ("revoked", "disabled"):
            continue
        if is_api_key_expired(record):
            continue
        stored_hash = record.get("hash")
        prefix = record.get("prefix") or ""
        if stored_hash and prefix and supplied.startswith(prefix):
            if verify_api_key(supplied, stored_hash):
                return record
        elif not stored_hash and record.get("key"):
            legacy_key = record["key"]
            legacy_prefix = api_key_prefix(legacy_key)
            if supplied.startswith(legacy_prefix) and hmac.compare_digest(supplied, legacy_key):
                record["hash"] = hash_api_key(legacy_key)
                record["prefix"] = legacy_prefix
                record["status"] = "active"
                record.setdefault("owner", record.get("user_id"))
                record.pop("key", None)
                get_store("api_keys").save()
                _audit_api_key("api_key_migrated", record.get("owner"), record.get("prefix", ""))
                return record
    return None


def _audit_api_key(action: str, actor_id: Optional[str], detail: str = "") -> None:
    """Append an audit entry for API-key lifecycle events (no secrets logged)."""
    logs = get_store("audit_logs").load()
    logs.append({
        "id": str(uuid.uuid4()),
        "actor_id": actor_id,
        "action": action,
        "resource_type": "auth",
        "timestamp": now_iso(),
        "detail": detail,
    })
    get_store("audit_logs").save()


def _strip_key_secrets(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of record with every secret field removed (section 14)."""
    return {k: v for k, v in record.items() if k not in ("key", "hash", "raw_key", "secret", "token")}


# --------------------------------------------------------------------------- #
# AI service (graceful provider abstraction + local fallback)
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "You are JARVIS, a helpful and capable AI assistant. Provide clear, "
    "concise, and technically accurate answers."
)


class AIService:
    def __init__(self) -> None:
        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1")
        self.provider = os.environ.get("JARVIS_AI_PROVIDER", "auto")
        self.enabled = (os.environ.get("JARVIS_AI_ENABLED", "0") == "1")
        # Bounded retries for transient provider failures (exponential backoff + jitter).
        self.max_retries = int(os.environ.get("JARVIS_AI_MAX_RETRIES", "2"))

    def settings(self) -> Dict[str, Any]:
        return {
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "provider": self.provider,
            "enabled": self.enabled,
        }

    def _try_ollama(self, prompt: str, system: Optional[str] = None) -> Optional[str]:
        try:
            import httpx
            res = httpx.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": f"{system or _SYSTEM_PROMPT}\n\n{prompt}",
                    "stream": False,
                },
                timeout=30,
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("response")
        except Exception:  # noqa: BLE001
            pass
        return None

    async def chat(self, prompt: str, system: Optional[str] = None,
             session_id: Optional[str] = None) -> str:
        """Generate a response using real providers, never a canned fallback.

        Routing order:
        1. ProviderGateway (OpenAI / Google / NVIDIA / Silverwing / Brain) —
           the same honest routing used by ``/api/chat/stream``.
        2. Local Ollama (``OLLAMA_BASE_URL``) when ``JARVIS_AI_ENABLED=1``.
        3. A **truthful** offline message (never a canned/fabricated answer).

        All callers are async endpoints, so this method is ``async`` to allow
        direct ``await`` of the gateway.
        """
        from .gateway import ProviderGateway  # lazy import avoids cycle

        # 1. Real provider gateway (shared with the streaming chat path).
        try:
            gw = ProviderGateway()
            result = await gw.chat(
                [{"role": "user", "content": prompt or ""}],
                model=self.provider if self.provider not in ("auto", "") else None,
                system=system,
            )
            if content := (result.get("content") or "").strip():
                return content
        except Exception:  # noqa: BLE001 — fall through to Ollama / truthful msg
            logger.debug("AIService.chat: ProviderGateway unavailable, continuing.")

        # 2. Local Ollama when explicitly enabled.
        if self.enabled:
            result = self._try_ollama(prompt, system)
            if result:
                return result

        # 3. Truthful offline message — never a canned answer.
        return self._fallback(prompt)

    def _fallback(self, prompt: str) -> str:
        """Truthful offline response — never fabricates a provider answer.

        When no real AI provider can be reached (no API keys, no Ollama,
        JARVIS_AI_ENABLED=0), the service MUST NOT return a canned answer
        that masquerades as model output.  Instead it returns a short,
        truthful status message so the caller can surface an honest
        OFFLINE / PROVIDER_UNAVAILABLE state to the user.
        """
        logger.warning(
            "AIService._fallback invoked — no real provider was available. "
            "Returning truthful status instead of a canned response."
        )
        return (
            "All AI providers are currently unavailable. No API key or "
            "local model is configured. Real responses require a provider "
            "key (OPENAI_API_KEY, GOOGLE_API_KEY, NVIDIA_API_KEY) or a "
            "running local model (OLLAMA_BASE_URL). This message is a "
            "truthful status, not a model-generated answer."
        )


ai_service = AIService()

# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="JARVIS Unified System",
    description="JARVIS backend API + integrated Silverwing AI backend (single service).",
    version="3.0.0",
)

allow_origins_raw = os.environ.get("JARVIS_CORS_ORIGINS")
if allow_origins_raw:
    allow_origins = [o.strip() for o in allow_origins_raw.split(",") if o.strip()]
else:
    allow_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:3003",
    ]
if is_production() and not allow_origins_raw and any(
    ("localhost" in o or "127.0.0.1" in o) for o in allow_origins
):
    raise RuntimeError(
        "JARVIS_CORS_ORIGINS must be set in production; refusing the insecure "
        "localhost development default (SEC-1 §9 transport/CORS invariant)."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """SEC-1 §9 — defensive security headers on every response.

    A single thin ASGI layer (reuses Starlette ``BaseHTTPMiddleware``); no
    second middleware stack is introduced. HSTS is emitted only in production
    (behind TLS) so local plain-HTTP dev is unaffected.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        if is_production():
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


def start_backend() -> None:
    """Initialize persistent collections with sensible defaults."""
    if is_production():
        admin_email()
        signing_key = read_secret("JARVIS_SECRET_KEY")
        admin_password = read_secret("JARVIS_ADMIN_PASSWORD")
        database = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_FILE")
        if not signing_key or len(signing_key) < 32:
            raise RuntimeError(
                "Production requires JARVIS_SECRET_KEY with at least 32 characters."
            )
        if not admin_password or len(admin_password) < 16:
            raise RuntimeError(
                "Production requires JARVIS_ADMIN_PASSWORD with at least 16 characters."
            )
        if not database or not database.startswith(("postgresql://", "postgresql+")):
            from .db import database_url

            database = database_url()
            if not database.startswith(("postgresql://", "postgresql+")):
                raise RuntimeError("Production requires PostgreSQL via DATABASE_URL.")
        if not os.environ.get("JARVIS_CORS_ORIGINS"):
            raise RuntimeError("Production requires explicit JARVIS_CORS_ORIGINS.")
    # Warn if the runtime signing key is still the ephemeral fallback — tokens
    # will break on the next restart. This check runs AFTER main.py / 
    # jarvis_api.py have loaded .env, so a properly configured env sees no warning.
    if not read_secret("JARVIS_SECRET_KEY"):
        logger.warning(
            "JARVIS_SECRET_KEY is not set; using an ephemeral random secret. "
            "Tokens will not survive a restart. Set JARVIS_SECRET_KEY in .env "
            "for a persistent dev environment."
        )
    # Ensure the SQL persistence schema exists (creates jarvis_kv if missing).
    create_db_and_tables()
    # Seed roles / permissions
    roles = get_store("roles").load()
    if not roles:
        roles["admin"] = {
            "id": "role-admin",
            "name": "admin",
            "description": "Full system access",
            "permissions": ["*"],
            "created_at": now_iso(),
        }
        roles["user"] = {
            "id": "role-user",
            "name": "user",
            "description": "Standard user",
            "permissions": ["read", "chat", "agent:read", "memory:write", "voice:use"],
            "created_at": now_iso(),
        }
        roles["viewer"] = {
            "id": "role-viewer",
            "name": "viewer",
            "description": "Read-only access",
            "permissions": ["read"],
            "created_at": now_iso(),
        }
        get_store("roles").save()

    perms = get_store("permissions").load()
    if not perms:
        resources = [
            "user", "role", "tenant", "agent", "task", "memory", "knowledge",
            "voice", "system", "monitoring", "automation", "api_key", "multimodal",
        ]
        perms["*"] = {"resource": "*", "actions": ["*"], "description": "All permissions"}
        for r in resources:
            perms[r] = {
                "resource": r,
                "actions": ["create", "read", "update", "delete", "execute"],
                "description": f"Manage {r}",
            }
        get_store("permissions").save()

    _seed_canonical_roles()
    _migrate_legacy_provider_secrets()  # SEC-1 §6: encrypt legacy plaintext at rest

    # Resolve + validate the admin identity BEFORE any password handling. In
    # production this raises a clear RuntimeError if JARVIS_ADMIN_EMAIL is unset
    # (fail-fast: no hardcoded insecure default). Dev/test fall back to the
    # legacy admin@jarvis.local placeholder so first sign-in always works.
    admin_email_address = admin_email()

    # ---------------------------------------------------------------------------
    # Seed a deterministic dev admin so the *first* login always succeeds on a
    # fresh database. ``JARVIS_ADMIN_PASSWORD`` is supplied by the platform
    # launcher (start_all.ps1) — never logged here. Idempotent: skipped when an
    # admin account with this email already exists, so existing accounts are
    # never clobbered. Tests run with JARVIS_TEST_MODE and don't invoke startup,
    # so this does not interfere with the per-test fixtures.
    admin_pw = read_secret("JARVIS_ADMIN_PASSWORD")
    if admin_pw:
        users = get_store("users").load()
        if not any(u.get("email") == admin_email_address for u in users.values()):
            uid = "00000000-0000-0000-0000-000000000001"
            users[uid] = {
                "id": uid,
                "email": admin_email_address,
                "username": "admin",
                "password_hash": hash_password(admin_pw),
                "full_name": "Administrator",
                "avatar_url": None,
                "status": "active",
                "tenant_id": None,
                "roles": ["admin"],
                "last_login_at": None,
                "created_at": now_iso(),
            }
            get_store("users").save()
            logger.info("Seeded default admin account.")

    # ---------------------------------------------------------------------------
    # Ensure the canonical owner identity is present (spec §1).
    # If the owner user does not exist, create it with the canonical owner metadata.
    # This is idempotent: existing owner records are never clobbered.
    _ensure_canonical_owner(admin_email_address)


def _ensure_canonical_owner(owner_email: str) -> None:
    """Idempotently ensure the canonical JARVIS owner user exists.

    The owner user is the platform's OWNER / DEVELOPER account, sourced from
    ``JARVIS_ADMIN_EMAIL`` (no literal address in source).  If the user already
    exists, their metadata is updated
    to reflect the canonical owner role.  If not, a new record is created.
    
    Raises RuntimeError if JARVIS_ADMIN_PASSWORD is not set (unsafe empty
    password would be hashed). Tests use JARVIS_TEST_MODE and bypass this check.
    """
    users = get_store("users").load()
    owner_email = (owner_email or "").lower().strip()
    if not owner_email:
        return

    existing_id = None
    for uid, u in users.items():
        if isinstance(u, dict) and (u.get("email") or "").lower().strip() == owner_email:
            existing_id = uid
            break

    if existing_id is not None:
        # Update existing user to ensure canonical owner metadata.
        user = users[existing_id]
        if "owner" not in (user.get("roles") or []):
            user["roles"] = list((user.get("roles") or [])) + ["owner"]
        user.setdefault("developer", True)
        user.setdefault("is_admin", True)
        user.setdefault("full_name", user.get("full_name") or owner_email.split("@")[0])
        user.setdefault("status", "active")
        user.setdefault("email_verified", True)  # Owner is always email verified
        get_store("users").save()
        logger.info("Updated canonical owner identity.")
        return

    # Require a non-empty admin password - never create owner with empty password
    admin_pw = (read_secret("JARVIS_ADMIN_PASSWORD") or "").strip()
    if not admin_pw:
        # Allow empty password only in test mode (dev with explicit test password)
        if os.environ.get("JARVIS_TEST_MODE") == "1":
            admin_pw = "test-password-for-testing"
        else:
            raise RuntimeError(
                "JARVIS_ADMIN_PASSWORD is required to create the canonical owner. "
                "Set JARVIS_ADMIN_PASSWORD in .env before starting. "
                "This prevents creating an owner with an empty/weak password."
            )
    
    uid = "00000000-0000-0000-0000-000000000001"
    users[uid] = {
        "id": uid,
        "email": owner_email,
        "email_verified": True,  # Owner is always email verified
        "username": "owner",
        "password_hash": hash_password(admin_pw),
        "full_name": owner_email.split("@")[0],
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": ["owner", "admin"],
        "last_login_at": None,
        "created_at": now_iso(),
        "developer": True,
        "is_admin": True,
    }
    get_store("users").save()
    logger.info("Seeded canonical owner identity.")


def _seed_canonical_roles() -> None:
    """Idempotently ensure the Developer Control Center role set (spec #44).

    Never clobbers existing roles -- only inserts the canonical roles that are
    missing, so real admins/users/roles on a running install are untouched.
    'admin' already maps to OWNER/ADMIN (full access via ['*']).
    """
    roles = get_store("roles").load()
    canonical: Dict[str, Dict[str, Any]] = {
        "owner": {
            "id": "role-owner", "name": "owner",
            "description": "Full system access (superuser)", "permissions": ["*"],
        },
        "admin": {
            "id": "role-admin", "name": "admin",
            "description": "Full system access", "permissions": ["*"],
        },
        "operator": {
            "id": "role-operator", "name": "operator",
            "description": "Run / operate the system (no user or connector secrets)",
            "permissions": ["system:read", "monitoring:*", "automation:execute",
                            "agent:*", "model:*", "task:*",
                            "data:discover", "data:read"],
        },
        "developer": {
            "id": "role-developer", "name": "developer",
            "description": "Configure integrations, tools, connectors, feature flags",
            "permissions": ["system:read", "monitoring:read", "automation:*",
                            "connector:*", "tool:*", "extension:*",
                            "role:read", "permission:read", "api_key:*",
                            "data:discover", "data:read", "data:analyze",
                            "data:export"],
        },
        "analyst": {
            "id": "role-analyst", "name": "analyst",
            "description": "Read telemetry, audit, knowledge and memory (no write)",
            "permissions": ["system:read", "monitoring:read", "audit:*",
                            "knowledge:*", "memory:*",
                            "data:discover", "data:read", "data:analyze",
                            "data:export"],
        },
        "viewer": {
            "id": "role-viewer", "name": "viewer",
            "description": "Read-only access",
            "permissions": ["system:read", "monitoring:read",
                            "agent:read", "knowledge:read", "memory:read",
                            "data:read"],
        },
    }
    # No canonical role grants "data:write": ingestion/mutation is reserved for
    # the owner/admin wildcard, so DATA_READ never implies DATA_WRITE.
    changed = False
    for name, spec in canonical.items():
        if name not in roles:
            roles[name] = {**spec, "created_at": now_iso()}
            changed = True
        else:
            existing = roles[name]
            # Additive merge: grant any missing canonical permission without
            # ever removing a permission an operator added by hand.
            have = set(existing.get("permissions") or ())
            want = list(spec.get("permissions") or ())
            if existing.get("permissions") is None:
                existing["permissions"] = want
                existing["description"] = spec["description"]
                changed = True
            else:
                have_now = set(existing["permissions"])
                missing = [p for p in want if p not in have_now]
                if missing and "*" not in have_now:
                    existing["permissions"] = list(existing["permissions"]) + missing
                    changed = True
                if existing.get("description") != spec["description"]:
                    existing["description"] = spec["description"]
                    changed = True
            if "id" not in existing:
                existing["id"] = spec["id"]
                changed = True
    if changed:
        get_store("roles").save()
    return None
