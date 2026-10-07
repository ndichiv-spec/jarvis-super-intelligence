"""Owner identity management for JARVIS (spec §1, §3, §21, §25).

Establishes ``ndichiv@gmail.com`` as the canonical JARVIS owner and provides:
  * OwnerIdentity resolution (email -> user_id, auth methods, MFA state)
  * Secure session creation bound to the owner
  * Account-recovery helpers (lost device, expired token, revoked grant)
  * A strict guard that the Gmail password is NEVER used as any credential

No raw password or credential is ever stored here — only references and
metadata.  The SecretManager vault holds credential values.
"""

from __future__ import annotations

import os
import secrets as _secrets
import time
from typing import Any, Optional

from .models import OwnerAuthMethod, OwnerIdentity

# Canonical owner — the developer who controls JARVIS.
_CANONICAL_OWNER_EMAIL = "ndichiv@gmail.com"

# Env-var names that are checked.  The Gmail password must NEVER be read from
# any of these.  This set is intentionally explicit so the guard can assert
# against accidental credential use.
_FORBIDDEN_PASSWORD_ENV_VARS = frozenset({
    "GMAIL_PASSWORD",
    "GMAIL_APP_PASSWORD",
    "GOOGLE_PASSWORD",
    "JARVIS_GMAIL_PASSWORD",
    "JARVIS_OWNER_PASSWORD",
})


class OwnerError(Exception):
    """Raised when the owner identity cannot be resolved or validated."""


class GmailPasswordLeakGuard:
    """Enforces the critical security principle (spec §26):

    Do NOT use the Gmail password as:
      - JARVIS password
      - Google API credential
      - Cloud credential
      - Provider credential
      - Service credential

    Do NOT store the Gmail password anywhere inside JARVIS.

    Do NOT automate Gmail login by storing the user's mailbox password.
    """

    @staticmethod
    def assert_not_gmail_password(candidate: str, context: str = "") -> None:
        """Refuse to accept or store a value that looks like a Gmail password.

        This is a best-effort guard: we reject known patterns and explicitly
        check forbidden env vars.  The real defense is architectural — the
        Gmail password is never accepted as an input.
        """
        if not candidate:
            return
        if context and "password" in context.lower() and "gmail" in candidate.lower():
            raise OwnerError("Gmail password must never be used as a credential")
        for env_var in _FORBIDDEN_PASSWORD_ENV_VARS:
            if os.environ.get(env_var):
                raise OwnerError(
                    f"{env_var} is set — the Gmail password must never be stored "
                    "or used by JARVIS. Use OIDC / passkey / OAuth instead."
                )


class OwnerManager:
    """Manages the canonical JARVIS owner identity.

    Parameters
    ----------
    users_store
        The backend user store (Store with load()/save()) used to look up the
        owner's full user record.  Tests may inject a fake.
    secrets
        The SecretManager (or compatible) used to check for the JARVIS password
        credential reference.  The raw password is never returned — only a
        boolean ``is_set`` / ``verified`` check.
    """

    def __init__(
        self,
        users_store: Any = None,
        secrets: Any = None,
        *,
        canonical_email: str = _CANONICAL_OWNER_EMAIL,
        state_secret: str = "",
    ) -> None:
        self._users_store = users_store
        self._secrets = secrets
        self._canonical_email = canonical_email.lower().strip()
        self._state_secret = state_secret or _secrets.token_urlsafe(32)
        self._recovery_codes: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ #
    # Canonical identity
    # ------------------------------------------------------------------ #
    @property
    def canonical_email(self) -> str:
        return self._canonical_email

    def is_owner(self, email: str) -> bool:
        """True iff ``email`` is the canonical JARVIS owner."""
        return (email or "").lower().strip() == self._canonical_email

    def is_owner_user(self, user: Optional[dict[str, Any]]) -> bool:
        """True iff the user record belongs to the canonical owner."""
        if user is None:
            return False
        return self.is_owner(user.get("email", ""))

    # ------------------------------------------------------------------ #
    # Owner identity resolution
    # ------------------------------------------------------------------ #
    def resolve_owner(self) -> Optional[dict[str, Any]]:
        """Look up the owner user record from the user store.

        Returns ``None`` if the owner has not been provisioned yet.
        """
        if self._users_store is None:
            return None
        users = self._users_store.load()
        for _uid, user in users.items():
            if isinstance(user, dict) and self.is_owner(user.get("email", "")):
                return {"id": _uid, **user}
        return None

    def build_identity(self, user: Optional[dict[str, Any]] = None) -> OwnerIdentity:
        """Construct an :class:`OwnerIdentity` from the stored user record.

        Auth methods are derived from what is *configured*:
          * Google OIDC is available always (the owner's Gmail is a Google
            account).  Whether it is *connected* is checked at login time.
          * JARVIS password is available only if a password hash exists on the
            user record.
          * Passkey is available if the user has ``passkey_enabled``.
        """
        user = user or self.resolve_owner() or {}
        uid = user.get("id") or "owner"
        email = user.get("email") or self._canonical_email
        name = user.get("full_name") or email.split("@")[0] or "Owner"

        methods: list[str] = [OwnerAuthMethod.GOOGLE_OIDC.value]
        if user.get("password_hash"):
            methods.append(OwnerAuthMethod.JARVIS_PASSWORD.value)
        if user.get("passkey_enabled"):
            methods.append(OwnerAuthMethod.PASSKEY_WEBAUTHN.value)

        now = user.get("last_login_at") or 0.0
        created = user.get("created_at") or 0.0
        # Parse ISO strings to epoch if needed.
        try:
            import datetime as _dt
            if isinstance(created, str):
                created = _dt.datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                ).timestamp()
        except Exception:
            pass
        try:
            import datetime as _dt
            if isinstance(now, str):
                now = _dt.datetime.fromisoformat(
                    now.replace("Z", "+00:00")
                ).timestamp()
        except Exception:
            now = 0.0

        return OwnerIdentity(
            user_id=uid,
            email=email,
            name=name,
            role=user.get("roles", ["owner"])[0] if user.get("roles") else "owner",
            developer=user.get("developer", True),
            primary_admin=user.get("is_admin", True),
            auth_methods=methods,
            mfa_enabled=bool(user.get("mfa_enabled", False)),
            passkey_enabled=bool(user.get("passkey_enabled", False)),
            is_active=user.get("status", "active") == "active",
            created_at=created,
            last_authenticated_at=now,
        )

    # ------------------------------------------------------------------ #
    # Gmail password guard
    # ------------------------------------------------------------------ #
    @staticmethod
    def assert_no_gmail_password(password: str, context: str = "password") -> None:
        """Reject any Gmail-password usage (spec §26 — CRITICAL SECURITY)."""
        GmailPasswordLeakGuard.assert_not_gmail_password(password, context)
        for env_var in _FORBIDDEN_PASSWORD_ENV_VARS:
            val = os.environ.get(env_var, "")
            if val:
                raise OwnerError(
                    f"Refusing to start: {env_var} is set. The Gmail password "
                    "must NEVER be stored in JARVIS. Use OIDC / passkey / OAuth."
                )

    # ------------------------------------------------------------------ #
    # Account recovery (spec §25)
    # ------------------------------------------------------------------ #
    def generate_recovery_code(self, user_id: str) -> str:
        """Generate a single-use recovery code for the owner.

        Recovery is possible via:
          * Passkey / WebAuthn (new device)
          * JARVIS-specific password (separate from Gmail)
          * A pre-generated recovery code (one-time use)
        """
        code = _secrets.token_urlsafe(16)
        self._recovery_codes.setdefault(user_id, []).append(code)
        return code

    def verify_recovery_code(self, user_id: str, code: str) -> bool:
        """Verify and consume a one-time recovery code."""
        codes = self._recovery_codes.get(user_id, [])
        if code in codes:
            codes.remove(code)
            self._recovery_codes[user_id] = codes
            return True
        return False

    def recovery_options(self, user_id: str) -> list[str]:
        """List available recovery methods for the owner."""
        identity = self.build_identity()
        opts = [OwnerAuthMethod.GOOGLE_OIDC.value]
        if identity.passkey_enabled:
            opts.append(OwnerAuthMethod.PASSKEY_WEBAUTHN.value)
        if identity.can_use_password():
            opts.append(OwnerAuthMethod.JARVIS_PASSWORD.value)
        if self._recovery_codes.get(user_id):
            opts.append("recovery_code")
        return opts

    # ------------------------------------------------------------------ #
    # Owner session
    # ------------------------------------------------------------------ #
    def create_owner_session(self, session_manager: Any, ip: str, user_agent: str) -> Any:
        """Create a platform session bound to the canonical owner.

        Requires that the owner user exists in the store.
        """
        from .session import SessionManager  # type: ignore

        if not isinstance(session_manager, SessionManager):
            raise OwnerError("session_manager must be a SessionManager instance")
        owner = self.resolve_owner()
        if owner is None:
            raise OwnerError("Owner user record not found in user store")
        return session_manager.create_session(
            user_id=owner["id"],
            ip=ip,
            user_agent=user_agent,
            auth_method=OwnerAuthMethod.GOOGLE_OIDC.value,
        )


def get_owner_manager(
    users_store: Any = None,
    secrets: Any = None,
) -> OwnerManager:
    """Build an OwnerManager wired to the platform's stores.

    Falls back to lazy resolution of the backend stores at call time.
    """
    if users_store is None or secrets is None:
        from jarvis_backend.core import get_store  # type: ignore[import-not-found]
        from providers.secrets import get_secret_manager  # type: ignore[import-not-found]

        users_store = users_store or get_store("users")
        secrets = secrets or get_secret_manager()
    return OwnerManager(users_store=users_store, secrets=secrets)
