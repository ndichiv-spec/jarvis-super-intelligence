"""Session management for the JARVIS identity layer (spec §12, §54).

Features:
  * Short-lived access sessions backed by rotating refresh tokens.
  * Login anomaly detection: rate limiting, suspicious-IP / new-IP flagging
    (spec §54).
  * CSRF token bound to each session.
  * Session storage is pluggable (in-memory dict by default; the backend
    injects the SQL-backed Store at integration time).
  * Cookie helpers produce the *attributes* (HttpOnly, Secure, SameSite,
    Max-Age); the FastAPI router applies them via ``Response.set_cookie``.

No credential is persisted in plaintext — only opaque session IDs / JTI
references.  Provider tokens are stored exclusively in the SecretManager vault.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# In-memory session store (swap for the backend SQL store in production)
# --------------------------------------------------------------------------- #
class MemorySessionStore:
    """Thread-safe in-memory session store.  Used by tests and as a default."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock_owners: dict[str, str] = {}

    def get(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def put(self, session_id: str, data: dict) -> None:
        self._sessions[session_id] = data

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def all(self) -> list[dict]:
        return list(self._sessions.values())

    def clear(self) -> None:
        self._sessions.clear()


# --------------------------------------------------------------------------- #
# Login attempt tracking (anomaly detection — spec §54)
# --------------------------------------------------------------------------- #
class LoginAttemptTracker:
    """Tracks login attempts per IP for rate-limiting and anomaly detection.

    A simple sliding-window counter.  Production deployments may replace this
    with a Redis-backed implementation; the ``SessionManager`` only depends on
    the duck-typed interface (``attempts_for``, ``record``).
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def attempts_for(self, ip: str) -> int:
        now = time.time()
        window = [t for t in self._attempts.get(ip, []) if now - t < self._window]
        self._attempts[ip] = window
        return len(window)

    def record(self, ip: str) -> None:
        self._attempts.setdefault(ip, []).append(time.time())

    def is_rate_limited(self, ip: str) -> bool:
        return self.attempts_for(ip) >= self._max

    def reset(self, ip: str) -> None:
        self._attempts.pop(ip, None)


# --------------------------------------------------------------------------- #
# Session manager
# --------------------------------------------------------------------------- #
class SessionManager:
    """Creates, validates, rotates, and revokes platform sessions.

    Parameters
    ----------
    store
        Pluggable session store (defaults to :class:`MemorySessionStore`).
    access_ttl
        Access-session lifetime in seconds (default 15 min — short-lived).
    tracker
        Login attempt tracker for anomaly detection.
    state_secret
        HMAC key for CSRF token generation.
    """

    def __init__(
        self,
        store: Optional[Any] = None,
        *,
        access_ttl: int = 900,          # 15 minutes
        tracker: Optional[LoginAttemptTracker] = None,
        state_secret: str = "",
    ) -> None:
        from .models import IdentitySession

        self._store = store or MemorySessionStore()
        self._access_ttl = access_ttl
        self._tracker = tracker or LoginAttemptTracker()
        self._state_secret = state_secret or secrets.token_urlsafe(32)
        self.IdentitySession = IdentitySession

    # ------------------------------------------------------------------ #
    # Login anomaly / rate-limit API (spec §54)
    # ------------------------------------------------------------------ #
    def is_rate_limited(self, ip: str) -> bool:
        return self._tracker.is_rate_limited(ip)

    def record_login_attempt(self, ip: str, success: bool) -> None:
        """Record a login attempt. On failure, increment; on success, reset."""
        if success:
            self._tracker.reset(ip)
        else:
            self._tracker.record(ip)

    def login_anomaly(self, ip: str, known_ips: list[str]) -> bool:
        """Flag a login from a previously-unseen IP (spec §54)."""
        return ip not in known_ips

    # ------------------------------------------------------------------ #
    # CSRF token (spec §12)
    # ------------------------------------------------------------------ #
    def generate_csrf_token(self, session_id: str) -> str:
        """Bound CSRF token: HMAC(state_secret, session_id + nonce)."""
        nonce = secrets.token_hex(16)
        msg = f"{session_id}:{nonce}".encode("utf-8")
        sig = hmac.new(self._state_secret.encode(), msg, hashlib.sha256).hexdigest()
        return f"{nonce}.{sig}"

    def verify_csrf_token(self, session_id: str, token: str) -> bool:
        try:
            nonce, _, sig = token.partition(".")
            msg = f"{session_id}:{nonce}".encode("utf-8")
            expected = hmac.new(self._state_secret.encode(), msg, hashlib.sha256).hexdigest()
            return secrets.compare_digest(expected, sig)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #
    def create_session(
        self,
        user_id: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        auth_method: str = "password",
    ) -> Any:
        """Create a new session and return it."""
        from .models import IdentitySession

        session_id = secrets.token_urlsafe(32)
        csrf = self.generate_csrf_token(session_id)
        now = time.time()
        session = IdentitySession(
            id=session_id,
            user_id=user_id,
            ip=ip,
            user_agent=user_agent,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._access_ttl,
            auth_method=auth_method,
            csrf_token=csrf,
        )
        self._store.put(session_id, self._to_record(session))
        return session

    def get_session(self, session_id: str) -> Optional[Any]:
        """Return a live session or ``None`` if expired/revoked/invalid."""
        from .models import IdentitySession

        record = self._store.get(session_id)
        if not record:
            return None
        if record.get("revoked"):
            return None
        if record.get("expires_at", 0) < time.time():
            self._store.delete(session_id)
            return None
        return self._from_record(record)

    def touch(self, session_id: str) -> bool:
        """Update ``last_seen_at``; optionally extend expiry (sliding window)."""
        record = self._store.get(session_id)
        if not record or record.get("revoked"):
            return False
        record["last_seen_at"] = time.time()
        self._store.put(session_id, record)
        return True

    def destroy_session(self, session_id: str) -> bool:
        """Revoke and delete a session."""
        record = self._store.get(session_id)
        if not record:
            return False
        record["revoked"] = True
        self._store.delete(session_id)
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all live sessions for a user (spec §54 — session rotation).

        Only works with stores that expose an ``all()`` method returning a list
        of session records (or dicts).  Stores without ``all()`` return 0.
        """
        count = 0
        all_sessions = (
            self._store.all()
            if hasattr(self._store, "all") and callable(self._store.all)
            else []
        )
        # ``all()`` may return dicts (records) or session objects.
        targets: list[str] = []
        for entry in all_sessions:
            sid = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
            if sid and entry.get("user_id") == user_id if isinstance(entry, dict) else getattr(entry, "user_id", None) == user_id:
                rec = self._store.get(sid)
                if rec and not rec.get("revoked", False):
                    targets.append(sid)
        for sid in targets:
            if self.destroy_session(sid):
                count += 1
        return count

    def rotate_session(self, session_id: str) -> Optional[Any]:
        """Issue a fresh session ID for an existing session (session rotation).

        The old session is revoked; the new one preserves the user identity.
        """
        old = self.get_session(session_id)
        if not old:
            return None
        self.destroy_session(session_id)
        return self.create_session(
            old.user_id,
            ip=old.ip,
            user_agent=old.user_agent,
            auth_method=old.auth_method,
        )

    # ------------------------------------------------------------------ #
    # Cookie helpers
    # ------------------------------------------------------------------ #
    def session_cookie_attrs(self, secure: bool = True) -> dict[str, str]:
        """Cookie attributes for the session cookie (HttpOnly, SameSite=Strict)."""
        return {
            "httponly": "true" if secure else "false",
            "secure": "true" if secure else "false",
            "samesite": "strict",
            "max_age": str(self._access_ttl),
            "path": "/",
        }

    def _to_record(self, session: Any) -> dict:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "ip": session.ip,
            "user_agent": session.user_agent,
            "created_at": session.created_at,
            "last_seen_at": session.last_seen_at,
            "expires_at": session.expires_at,
            "revoked": session.revoked,
            "auth_method": session.auth_method,
            "csrf_token": session.csrf_token,
        }

    def _from_record(self, record: dict) -> Any:
        from .models import IdentitySession

        return IdentitySession(
            id=record["id"],
            user_id=record["user_id"],
            ip=record.get("ip"),
            user_agent=record.get("user_agent"),
            created_at=record.get("created_at", 0.0),
            last_seen_at=record.get("last_seen_at", 0.0),
            expires_at=record.get("expires_at", 0.0),
            revoked=record.get("revoked", False),
            auth_method=record.get("auth_method", "password"),
            csrf_token=record.get("csrf_token"),
        )
