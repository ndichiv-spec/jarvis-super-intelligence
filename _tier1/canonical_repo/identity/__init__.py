"""JARVIS unified identity layer (spec §12, §15, §53, §54).

Provides:
  * OIDC login for Google, Microsoft, and GitHub (spec §53)
  * Local JARVIS account (password) — the default
  * Owner identity: ndichiv@gmail.com as canonical OWNER / DEVELOPER
  * Session management with HttpOnly cookies, CSRF, PKCE, and refresh-token
    rotation (spec §12, §54)
  * Account linking (one JARVIS user ↔ multiple provider identities, spec §53)
  * RBAC permission engine (spec §54)
  * Permission Center: approval gate for high-risk actions (spec §15, §16)
  * Owner audit log (spec §17 — no raw secrets recorded)
  * Provider Connection Center (spec §15) — inspect and manage every provider
    connection without ever exposing credentials
"""

from __future__ import annotations

from .linking import AccountLinker
from .models import (
    AccountLink,
    ConnectionStatus,
    IdentityProvider,
    IdentitySession,
    LoginAttempt,
    OidcConfig,
    OidcUserInfo,
    OwnerAuthMethod,
    OwnerIdentity,
    ProviderConnection,
    TOOL_CAPABILITIES,
)
from .oidc import OidcClient, OidcError, code_challenge, generate_code_verifier, generate_state, verify_state
from .owner import OwnerError, OwnerManager, get_owner_manager
from .permission_center import (
    HIGH_RISK_ACTIONS,
    OwnerAuthorization,
    PermissionCenter,
    PermissionSpec,
    RiskLevel,
)
from .audit_log import AuditEvent, OwnerAuditLog
from .provider_center import (
    ProviderConnectionManager,
    _PROVIDER_META,
)
from .rbac import CANONICAL_ROLES, PermissionEngine, RESOURCE_ACTIONS
from .router import configure_oidc_providers, router
from .session import (
    LoginAttemptTracker,
    MemorySessionStore,
    SessionManager,
)

__version__ = "0.1.0"

__all__ = [
    "AccountLinker",
    "AccountLink",
    "AuditEvent",
    "CANONICAL_ROLES",
    "ConnectionStatus",
    "HIGH_RISK_ACTIONS",
    "IdentityProvider",
    "IdentitySession",
    "LoginAttempt",
    "LoginAttemptTracker",
    "MemorySessionStore",
    "OidcClient",
    "OidcConfig",
    "OidcError",
    "OidcUserInfo",
    "OwnerAuditLog",
    "OwnerAuthMethod",
    "OwnerError",
    "OwnerIdentity",
    "OwnerAuthorization",
    "OwnerManager",
    "PermissionCenter",
    "PermissionEngine",
    "PermissionSpec",
    "ProviderConnectionManager",
    "ProviderConnection",
    "RESOURCE_ACTIONS",
    "RiskLevel",
    "TOOL_CAPABILITIES",
    "SessionManager",
    "code_challenge",
    "configure_oidc_providers",
    "generate_code_verifier",
    "generate_state",
    "get_owner_manager",
    "router",
    "verify_state",
]
