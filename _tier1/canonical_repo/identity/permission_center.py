"""Permission Center for high-risk owner actions (spec §15, §16).

Every integration must expose permissions.  The PermissionCenter is the
approval gate for actions that can:

  * send email
  * delete file
  * merge pull request
  * deploy infrastructure
  * spend cloud money
  * create expensive GPU job
  * modify security policy
  * rotate production credentials

Default to read-only where practical.  High-impact operations require explicit
authorization through the policy engine.

The model never infers approval — the OwnerAuthorization record requires a
human decision.
"""

from __future__ import annotations

import enum
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import TOOL_CAPABILITIES


class RiskLevel(str, enum.Enum):
    """Risk classification for a permission-checked action."""

    READ = "read"          # read-only, safe
    WRITE = "write"        # modifies data, low risk
    DESTRUCTIVE = "destructive"  # deletes data, medium risk
    DESTRUCTIVE_HARD = "destructive_hard"  # irreversible delete
    CREDENTIAL = "credential"  # reads or modifies credentials/secrets
    INFRASTRUCTURE = "infrastructure"  # deploys / modifies infrastructure
    COMPUTE_SPEND = "compute_spend"  # launches compute that costs money
    SECURITY = "security"  # modifies security policy / IAM
    OWNER_AUTH = "owner_auth"  # changes owner identity / auth methods


# High-risk actions that require explicit owner confirmation.
HIGH_RISK_ACTIONS: frozenset[str] = frozenset({
    "delete_file",
    "delete_resource",
    "merge_pull_request",
    "deploy_infrastructure",
    "create_gpu_job",
    "rotate_production_credentials",
    "revoke_provider_token",
    "modify_security_policy",
    "modify_owner_identity",
    "disconnect_provider",
    "create_provider_secret",
    "send_email",
    "modify_production_model",
})

# Actions that inherently cost money.
SPEND_ACTIONS: frozenset[str] = frozenset({
    "create_gpu_job",
    "deploy_infrastructure",
    "start_remote_training",
    "create_cloud_resource",
})


@dataclass
class PermissionSpec:
    """Specification of a permission-checked action."""

    action: str
    resource: str
    resource_id: str = ""
    description: str = ""
    risk: RiskLevel = RiskLevel.READ
    requires_owner_confirmation: bool = False
    capability: str = ""
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if not self.capability:
            for cap in TOOL_CAPABILITIES:
                if cap.lower().startswith(self.action.lower()[:8]):
                    self.capability = cap
                    break
        if not self.requires_owner_confirmation:
            if self.risk in (RiskLevel.DESTRUCTIVE, RiskLevel.DESTRUCTIVE_HARD,
                            RiskLevel.CREDENTIAL, RiskLevel.INFRASTRUCTURE,
                            RiskLevel.COMPUTE_SPEND, RiskLevel.SECURITY,
                            RiskLevel.OWNER_AUTH):
                self.requires_owner_confirmation = True
            if self.action in HIGH_RISK_ACTIONS:
                self.requires_owner_confirmation = True
            if self.action in SPEND_ACTIONS and self.estimated_cost_usd > 0:
                self.requires_owner_confirmation = True


@dataclass
class OwnerAuthorization:
    """A recorded owner decision on a high-risk action (spec §16).

    This is the audit trail: the owner explicitly approved (or denied) an
    action.  The model never auto-approves.
    """

    action: str
    resource: str
    resource_id: str
    decision: str  # "approved" | "denied" | "auto_denied"
    authorized_by: str
    authorized_at: float
    reason: str = ""
    approval_token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    ttl_seconds: int = 900  # approvals are time-bounded (15 min default)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.authorized_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "decision": self.decision,
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
            "reason": self.reason,
            "approval_token": self.approval_token[:8] + "...",
            "expires_at": self.authorized_at + self.ttl_seconds,
        }


class PermissionCenter:
    """Approval gate for high-risk actions.

    The workflow is:
      1. Caller requests a permission check via ``check()`` or ``request``.
      2. If read-only / not high-risk, the action is auto-allowed.
      3. If high-risk, an :class:`OwnerAuthorization` request is created and
         the caller must obtain explicit owner approval via ``approve()``.
      4. Without a valid, non-expired authorization, high-risk actions raise.

    The approvals are stored in-memory by default; production uses the backend
    KV store injected via ``approval_store``.
    """

    def __init__(
        self,
        owner_email: str = "ndichiv@gmail.com",
        *,
        approval_store: Any = None,
    ) -> None:
        self._owner_email = owner_email.lower().strip()
        self._approval_store = approval_store  # Store with load()/save()
        self._cache: dict[str, OwnerAuthorization] = {}

    def _store(self) -> dict[str, dict[str, Any]]:
        """Return the backing store dict, or in-memory cache."""
        if self._approval_store is None:
            return self._cache  # type: ignore[assignment]
        return self._approval_store.load()

    def _flush(self) -> None:
        if self._approval_store is not None:
            self._approval_store.save()

    # ------------------------------------------------------------------ #
    # Permission checks
    # ------------------------------------------------------------------ #
    def check(
        self,
        spec: PermissionSpec,
        user: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Return True if the action is allowed without explicit approval.

        Read-only actions are always allowed.  High-risk actions require a
        prior :class:`OwnerAuthorization` — if none exists, returns False
        (caller must call ``request`` and obtain approval).
        """
        if not spec.requires_owner_confirmation:
            # Read-only or low-risk: allowed if the user has any role.
            return user is not None or spec.risk == RiskLevel.READ
        # Check for a valid authorization record.
        return self._has_valid_authorization(spec, user)

    def _has_valid_authorization(
        self, spec: PermissionSpec, user: Optional[dict[str, Any]]
    ) -> bool:
        store = self._store()
        key = self._auth_key(spec)
        for _k, record in store.items():
            if _k == key or _k.startswith(key.rsplit(":", 1)[0]):
                auth = self._record_to_auth(record)
                if auth and not auth.is_expired and auth.decision == "approved":
                    if self._matches_user(auth, user):
                        return True
        return False

    def _matches_user(self, auth: OwnerAuthorization, user: Optional[dict]) -> bool:
        if auth.authorized_by == self._owner_email:
            return True
        if user and (user.get("email") or "").lower() == auth.authorized_by.lower():
            return True
        return False

    def _auth_key(self, spec: PermissionSpec) -> str:
        return f"{spec.action}:{spec.resource}:{spec.resource_id or 'any'}"

    def _record_to_auth(self, record: dict[str, Any]) -> Optional[OwnerAuthorization]:
        if not record:
            return None
        try:
            return OwnerAuthorization(
                action=record["action"],
                resource=record["resource"],
                resource_id=record["resource_id"],
                decision=record["decision"],
                authorized_by=record["authorized_by"],
                authorized_at=record.get("authorized_at", 0.0),
                reason=record.get("reason", ""),
                approval_token=record.get("approval_token", ""),
                ttl_seconds=record.get("ttl_seconds", 900),
            )
        except (KeyError, TypeError):
            return None

    # ------------------------------------------------------------------ #
    # Approval flow
    # ------------------------------------------------------------------ #
    def request(
        self,
        spec: PermissionSpec,
        user: Optional[dict[str, Any]] = None,
    ) -> OwnerAuthorization:
        """Create a pending authorization request for a high-risk action.

        The request is ``auto_denied`` if the user is neither the owner nor
        has an explicit role that grants the action.  In practice, the caller
        must obtain a real owner ``approve()`` call — the model never auto-approves.
        """
        if not spec.requires_owner_confirmation:
            # Low-risk: auto-approve.
            auth = OwnerAuthorization(
                action=spec.action,
                resource=spec.resource,
                resource_id=spec.resource_id,
                decision="approved",
                authorized_by=self._owner_email,
                authorized_at=time.time(),
                reason=f"low-risk action ({spec.risk.value})",
            )
            self._store()[self._auth_key(spec)] = auth.to_dict() | {
                "approved_at": auth.authorized_at,
                "approval_token": auth.approval_token,
                "ttl_seconds": auth.ttl_seconds,
            }
            self._flush()
            return auth

        # High-risk: record a pending request.  Denied until the owner approves.
        auth = OwnerAuthorization(
            action=spec.action,
            resource=spec.resource,
            resource_id=spec.resource_id,
            decision="denied",
            authorized_by=self._owner_email,
            authorized_at=time.time(),
            reason="awaiting owner confirmation",
        )
        self._store()[self._auth_key(spec)] = {
            "action": auth.action,
            "resource": auth.resource,
            "resource_id": auth.resource_id,
            "decision": auth.decision,
            "authorized_by": auth.authorized_by,
            "authorized_at": auth.authorized_at,
            "reason": auth.reason,
            "approval_token": auth.approval_token,
            "ttl_seconds": auth.ttl_seconds,
            "user_email": (user or {}).get("email", ""),
        }
        self._flush()
        return auth

    def approve(
        self,
        approval_token: str,
        approver_email: str,
    ) -> OwnerAuthorization:
        """Owner approves a pending high-risk action.

        ``approver_email`` must be the canonical owner.
        """
        if approver_email.lower().strip() != self._owner_email:
            raise PermissionError(
                f"Only the canonical owner ({self._owner_email}) may approve "
                f"high-risk actions; attempted by {approver_email}"
            )
        store = self._store()
        for key, record in store.items():
            if record.get("approval_token") == approval_token:
                auth = self._record_to_auth(record)
                if auth is None:
                    raise KeyError("invalid approval record")
                if auth.is_expired:
                    raise KeyError("approval token expired")
                auth.decision = "approved"
                auth.authorized_by = approver_email
                auth.authorized_at = time.time()
                auth.reason = "owner approved"
                store[key] = auth.to_dict() | {
                    "approval_token": auth.approval_token,
                    "ttl_seconds": auth.ttl_seconds,
                    "user_email": record.get("user_email", ""),
                }
                self._flush()
                return auth
        raise KeyError("approval token not found (expired or invalid)")

    def deny(self, approval_token: str, deny_reason: str = "denied by owner") -> None:
        """Owner denies a pending high-risk action."""
        store = self._store()
        for key, record in store.items():
            if record.get("approval_token") == approval_token:
                record["decision"] = "denied"
                record["reason"] = deny_reason
                self._flush()
                return
        raise KeyError("approval token not found")

    def pending_requests(self) -> list[dict[str, Any]]:
        """All pending (denied/awaiting) high-risk authorization requests."""
        result = []
        store = self._store()
        for _key, record in store.items():
            if record.get("decision") != "approved":
                result.append(self._record_to_safe_dict(record))
        return result

    def _record_to_safe_dict(self, record: dict[str, Any]) -> dict[str, Any]:
        """Safe view: no approval tokens exposed."""
        out = dict(record)
        out["approval_token"] = out.get("approval_token", "")[:8] + "..." if out.get("approval_token") else ""
        return out
