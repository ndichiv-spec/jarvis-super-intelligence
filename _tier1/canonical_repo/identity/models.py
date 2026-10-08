"""Domain models for the JARVIS unified identity layer (spec §12, §53, §54).

These dataclasses are pure data — no persistence, no I/O — so they can be unit
tested in isolation and shared by the OIDC client, session manager, account
linker, RBAC engine, and the FastAPI router without circular dependencies.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class IdentityProvider(str, enum.Enum):
    """Supported identity providers for platform login (spec §53).

    ``LOCAL`` is the JARVIS-native account (password).  The others are
    standardized OIDC/OAuth identity providers.
    """

    LOCAL = "local"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"


class ConnectionStatus(str, enum.Enum):
    """Provider connection status states (spec §15/§38)."""

    CONNECTED = "connected"
    NOT_CONNECTED = "not_connected"
    EXPIRED = "expired"
    ERROR = "error"
    TESTING = "testing"


# Capability strings for tool authorization (spec §17/§69).  These are the
# fine-grained permissions a model request must pass through the policy engine.
TOOL_CAPABILITIES = frozenset(
    {
        "EMAIL_SEND",
        "EMAIL_READ",
        "DRIVE_READ",
        "DRIVE_WRITE",
        "CALENDAR_READ",
        "CALENDAR_WRITE",
        "REPO_READ",
        "REPO_WRITE",
        "CI_READ",
        "WORKFLOW_READ",
        "CHAT_READ",
        "COMPUTE_RUN",
    }
)


@dataclass
class OidcConfig:
    """OIDC client configuration for one identity provider.

    ``client_secret`` is always resolved through the SecretManager at runtime —
    it is never hardcoded and never returned by any API (spec §16/§69).
    """

    provider: IdentityProvider
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    issuer: str = ""
    # Well-known discovery URL — fetched lazily on first use (spec §7).
    discovery_url: Optional[str] = None
    # Discovered endpoints (populated by :meth:`OidcClient.discover`).
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    jwks_uri: Optional[str] = None
    # Whether the provider returns an id_token (typical for OIDC providers).
    supports_id_token: bool = True

    def is_configured(self) -> bool:
        """True iff the minimum fields needed to start a login flow are present."""
        return bool(self.client_id and self.redirect_uri)


@dataclass
class OidcUserInfo:
    """Normalized identity claims from an OIDC provider userinfo / id_token."""

    sub: str
    email: Optional[str] = None
    email_verified: bool = False
    name: Optional[str] = None
    preferred_username: Optional[str] = None
    avatar_url: Optional[str] = None
    raw: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.preferred_username:
            return self.preferred_username
        if self.email:
            return self.email.split("@")[0]
        return self.sub


@dataclass
class AccountLink:
    """Links an OIDC provider identity to a local JARVIS user account (spec §53).

    A single JARVIS user may have multiple linked identities (account linking)
    rather than duplicate users per provider.
    """

    provider: str  # IdentityProvider.value e.g. "google"
    provider_user_id: str  # ``sub`` claim from the provider
    jarvis_user_id: str
    email: Optional[str] = None
    created_at: str = ""
    last_seen_at: str = ""
    # Token metadata (NOT the token itself — that lives in the secret vault).
    access_token_ref: Optional[str] = None  # vault key name, not the token value
    refresh_token_ref: Optional[str] = None


@dataclass
class IdentitySession:
    """A platform session record (spec §54).

    Sessions are short-lived access sessions backed by rotating refresh tokens.
    """

    id: str
    user_id: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: float = 0.0
    last_seen_at: float = 0.0
    expires_at: float = 0.0
    revoked: bool = False
    auth_method: str = "password"  # password | oidc:<provider>
    csrf_token: Optional[str] = None  # bound to the session for CSRF protection


@dataclass
class LoginAttempt:
    """Record of a login attempt for anomaly detection (spec §54)."""

    ip: str
    identifier: str  # email or username attempted
    success: bool
    timestamp: float
    user_id: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class ProviderConnection:
    """Runtime status of a provider connection in the Provider Center (spec §15).

    This is a *view model* — it never carries the raw credential.  Credential
    state lives only in :class:`~providers.secrets.SecretManager`.
    """

    provider_id: str
    display_name: str
    connected: bool
    status: ConnectionStatus
    capabilities: list[str] = field(default_factory=list)
    model_count: int = 0
    detail: str = ""
    last_tested: Optional[str] = None
    expires_at: Optional[str] = None
    configured: bool = False


class OwnerAuthMethod(str, enum.Enum):
    """The canonical set of authentication methods an owner may use."""

    GOOGLE_OIDC = "google_oidc"
    MICROSOFT_OIDC = "microsoft_oidc"
    PASSKEY_WEBAUTHN = "passkey_webauthn"
    JARVIS_PASSWORD = "jarvis_password"


@dataclass
class OwnerIdentity:
    """Canonical JARVIS owner identity (spec §1 — OWNER / DEVELOPER).

    This is the single human who controls JARVIS configuration, provider
    connections, model management, training, learning, security, cloud
    connections, and deployment.

    The owner's email (``ndichiv@gmail.com``) is the canonical identifier.
    It is NOT used as a password or API credential — authentication is via
    OIDC (Google), passkeys/WebAuthn, or a JARVIS-specific password that is
    separate from the email/gmail password.
    """

    user_id: str
    email: str
    name: str = ""
    role: str = "owner"
    developer: bool = True
    primary_admin: bool = True
    auth_methods: list[str] = field(default_factory=list)
    mfa_enabled: bool = False
    passkey_enabled: bool = False
    is_active: bool = True
    created_at: float = 0.0
    last_authenticated_at: Optional[float] = None

    def has_auth_method(self, method: str) -> bool:
        """True iff the owner may authenticate via ``method``."""
        return method in self.auth_methods

    def can_use_password(self) -> bool:
        """True iff a JARVIS-specific password is configured for this owner."""
        return OwnerAuthMethod.JARVIS_PASSWORD.value in self.auth_methods
