"""RBAC policy engine for the JARVIS identity layer (spec §12, §53, §54).

Evaluates whether a user (or an API-key principal) holds the permission
required to perform an action.  Built on top of the backend's canonical
role / permission / scope stores (seeded by ``core._seed_canonical_roles``).

Permission model
----------------
  * A ``role`` carries a set of permission strings (``"resource:action"`` or ``"*``").
  * A user holds ``roles`` (resolved from the user record or derived from an
    API-key scope).
  * ``"*"`` in a role's permissions grants everything.
  * API-key principals derive authority from ``scopes`` (never from the owner's
    roles — see ``core._api_key_principal``), preventing privilege escalation.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence


# Canonical resource namespace (spec §12).  Each resource maps to a list of
# concrete actions.  ``*`` on either side means "all".
RESOURCE_ACTIONS: dict[str, list[str]] = {
    "identity": ["read", "write", "delete", "manage"],
    "provider": ["read", "write", "rotate", "revoke", "manage"],
    "model": ["read", "deploy", "delete", "manage"],
    "agent": ["read", "create", "update", "delete", "manage", "execute"],
    "tool": ["read", "create", "update", "delete", "manage"],
    "memory": ["read", "write", "delete"],
    "knowledge": ["read", "write", "delete"],
    "task": ["read", "create", "update", "delete", "manage", "execute"],
    "sandbox": ["execute", "manage"],
    "training": ["read", "create", "delete", "manage"],
    "dataset": ["read", "create", "delete", "manage"],
    "evaluation": ["read", "create", "manage"],
    "secret": ["read", "rotate", "revoke", "manage"],
    "audit": ["read"],
    "system": ["read", "write", "manage"],
    "cost": ["read"],
    "deployment": ["read", "manage"],
    "permission": ["read", "manage"],
    # Data analytics (enforced by research_engine.tool_registry). ``write`` is a
    # separate action so DATA_READ can never imply DATA_WRITE.
    "data": ["discover", "read", "analyze", "export", "write"],
    # Geography (enforced by research_engine.geography_tools). Reading local map
    # data is separated from corpus search so a viewer cannot sweep local files.
    "geography": ["read", "search", "data", "provider"],
    "web": ["read"],
}


class PermissionEngine:
    """Evaluates permission checks against a user + role store.

    Parameters
    ----------
    role_store
        A store with ``load()`` returning ``{id_or_name: {permissions: [...]}}``.
    """

    def __init__(self, role_store: Any) -> None:
        self._role_store = role_store

    def _user_roles(self, user: dict[str, Any]) -> list[str]:
        """Extract role names + IDs from a user (or key-derived principal)."""
        names: list[str] = []
        for r in user.get("roles") or []:
            if isinstance(r, str):
                names.append(r)
        # Also accept role IDs stored as objects {id: "...", name: "..."}.
        if "role_ids" in user:
            for rid in user["role_ids"]:
                names.append(str(rid))
        return names

    def _role_permissions(self, role_names: list[str]) -> set[str]:
        """Resolve the full permission set for a set of role names/IDs."""
        roles = self._role_store.load()
        perms: set[str] = set()
        looked_up: set[str] = set()
        for name in role_names:
            if name in looked_up:
                continue
            looked_up.add(name)
            # Match by name or id.
            role = None
            if name in roles:
                role = roles[name]
            else:
                for r in roles.values():
                    if r.get("name") == name or r.get("id") == name:
                        role = r
                        break
            if role:
                for p in role.get("permissions", []):
                    perms.add(p)
        return perms

    def effective_permissions(self, user: Optional[dict[str, Any]]) -> set[str]:
        """All permissions a user/principal currently holds (for inspection)."""
        if user is None:
            return set()
        perms = self._role_permissions(self._user_roles(user))
        # API-key principals may carry scopes (spec §8 / §54).
        for scope in user.get("scopes", []):
            perms.add(scope)
        return perms

    def has_permission(self, user: Optional[dict[str, Any]], permission: str) -> bool:
        """True iff ``user`` holds ``permission`` (or ``"*"``).

        ``permission`` may be ``"resource:action"`` or ``"resource:*"``.
        """
        if user is None:
            return False
        perms = self.effective_permissions(user)
        if "*" in perms or permission in perms:
            return True
        # Wildcard action: "resource:*" matches any "resource:<action>".
        resource, _, _action = permission.partition(":")
        if f"{resource}:*" in perms:
            return True
        # Wildcard resource: "*:action" — less common but supported.
        _, _, action = permission.partition(":")
        if f"*:{action}" in perms:
            return True
        return False

    def require(self, user: Optional[dict[str, Any]], permission: str) -> None:
        """Raise :class:`PermissionError` if ``user`` lacks ``permission``."""
        if not self.has_permission(user, permission):
            missing = permission
            roles = self._user_roles(user or {})
            raise PermissionError(
                f"access denied: requires '{missing}'; "
                f"user roles={roles}"
            )

    def has_any(self, user: Optional[dict], permissions: Sequence[str]) -> bool:
        """True iff the user holds *any* of the given permissions."""
        return any(self.has_permission(user, p) for p in permissions)

    def require_any(self, user: Optional[dict], permissions: Sequence[str]) -> None:
        for p in permissions:
            if self.has_permission(user, p):
                return
        raise PermissionError(
            f"access denied: requires any of {list(permissions)}; "
            f"user roles={self._user_roles(user or {})}"
        )


# --------------------------------------------------------------------------- #
# Convenience: canonical role set (mirrors core._seed_canonical_roles)
# --------------------------------------------------------------------------- #
CANONICAL_ROLES: dict[str, dict[str, Any]] = {
    "owner": {"permissions": ["*"]},
    "admin": {"permissions": ["*"]},
    "operator": {
        "permissions": [
            "system:read", "monitoring:*", "automation:execute",
            "agent:*", "model:*", "task:*",
            "data:discover", "data:read",
            "geography:read", "geography:search",
        ]
    },
    "developer": {
        "permissions": [
            "system:read", "monitoring:read", "automation:*",
            "connector:*", "tool:*", "extension:*",
            "role:read", "permission:read", "api_key:*",
            "data:discover", "data:read", "data:analyze", "data:export",
            "geography:read", "geography:search", "geography:data",
        ]
    },
    "analyst": {
        "permissions": [
            "system:read", "monitoring:read", "audit:*",
            "knowledge:*", "memory:*",
            "data:discover", "data:read", "data:analyze", "data:export",
            "geography:read", "geography:search", "geography:data",
        ]
    },
    "viewer": {
        "permissions": [
            "system:read", "monitoring:read",
            "agent:read", "knowledge:read", "memory:read",
            # data:read only: every viewer permission must be a read action, so
            # the discover/analyze/export actions stay out of this role.
            "data:read",
            # geography:read only: the pure geodesic capabilities. Local map
            # files (geography:data) and corpus sweeps (geography:search) are
            # deliberately withheld from a viewer.
            "geography:read",
        ]
    },
    "user": {
        "permissions": [
            "read", "chat", "agent:read", "memory:write", "voice:use",
            "web:read",
        ],
    },
}
# NOTE: no canonical role grants "data:write". Ingestion/mutation therefore
# requires an owner/admin wildcard, so DATA_READ can never imply DATA_WRITE.
# NOTE: no canonical role grants "geography:provider". Provider-backed geocoding
# and routing require an owner/admin wildcard, so geography:read can never imply
# a paid or network-backed provider call.
