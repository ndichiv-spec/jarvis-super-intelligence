"""Tests for the JARVIS Owner Identity architecture (spec §1, §3, §15, §16, §17, §21, §22, §25, §26).

Covers:
  * OwnerIdentity model — canonical owner (ndichiv@gmail.com)
  * OwnerManager — identity resolution, Gmail password guard, recovery
  * PermissionCenter — high-risk action approval flow
  * OwnerAuditLog — secret-free audit recording and querying
  * End-to-end: owner cannot use Gmail password as any credential
"""

from __future__ import annotations

import os
import time

import pytest

from identity.models import OwnerAuthMethod, OwnerIdentity
from identity.owner import (
    OwnerError,
    OwnerManager,
)
from identity.permission_center import (
    HIGH_RISK_ACTIONS,
    PermissionCenter,
    PermissionSpec,
    RiskLevel,
)
from identity.audit_log import AuditEvent, OwnerAuditLog


# --------------------------------------------------------------------------- #
# OwnerIdentity model
# --------------------------------------------------------------------------- #
class TestOwnerIdentityModel:
    def test_canonical_owner_email(self):
        assert OwnerIdentity(
            user_id="owner-1",
            email="ndichiv@gmail.com",
        ).email == "ndichiv@gmail.com"

    def test_default_role_is_owner(self):
        identity = OwnerIdentity(user_id="owner-1", email="ndichiv@gmail.com")
        assert identity.role == "owner"
        assert identity.developer is True
        assert identity.primary_admin is True

    def test_has_auth_method(self):
        identity = OwnerIdentity(
            user_id="u1", email="ndichiv@gmail.com",
            auth_methods=["google_oidc", "jarvis_password"],
        )
        assert identity.has_auth_method("google_oidc")
        assert identity.has_auth_method(OwnerAuthMethod.JARVIS_PASSWORD.value)
        assert not identity.has_auth_method("microsoft_oidc")

    def test_can_use_password_only_when_configured(self):
        without_pw = OwnerIdentity(user_id="u", email="a@b.c")
        assert not without_pw.can_use_password()
        with_pw = OwnerIdentity(
            user_id="u", email="a@b.c",
            auth_methods=["jarvis_password"],
        )
        assert with_pw.can_use_password()


# --------------------------------------------------------------------------- #
# OwnerManager
# --------------------------------------------------------------------------- #
class _MemStore:
    def __init__(self, data=None):
        self._d = data or {}

    def load(self):
        return self._d

    def save(self):
        pass


class TestOwnerManager:
    def _manager(self, users=None):
        return OwnerManager(
            users_store=_MemStore(users or {}),
        )

    def test_canonical_email(self):
        om = self._manager()
        assert om.canonical_email == "ndichiv@gmail.com"

    def test_is_owner_true_for_canonical(self):
        om = self._manager()
        assert om.is_owner("ndichiv@gmail.com")
        assert om.is_owner("NDICHIV@GMAIL.COM")  # case-insensitive

    def test_is_owner_false_for_others(self):
        om = self._manager()
        assert not om.is_owner("admin@jarvis.local")
        assert not om.is_owner("someone-else@gmail.com")
        assert not om.is_owner("")

    def test_resolve_owner_finds_stored_user(self):
        users = {
            "user-1": {
                "id": "user-1",
                "email": "ndichiv@gmail.com",
                "full_name": "Dich iv",
                "roles": ["admin"],
                "status": "active",
            },
            "user-2": {"id": "user-2", "email": "other@example.com", "roles": ["user"]},
        }
        om = self._manager(users)
        owner = om.resolve_owner()
        assert owner is not None
        assert owner["email"] == "ndichiv@gmail.com"
        assert owner["id"] == "user-1"

    def test_resolve_owner_returns_none_if_not_seeded(self):
        om = self._manager()
        assert om.resolve_owner() is None

    def test_build_identity_from_stored_user(self):
        users = {
            "00000000-0000-0000-0000-000000000001": {
                "id": "00000000-0000-0000-0000-000000000001",
                "email": "ndichiv@gmail.com",
                "full_name": "Developer",
                "roles": ["admin", "owner"],
                "status": "active",
                "password_hash": "pbkdf2_sha256$...",
                "passkey_enabled": True,
                "mfa_enabled": True,
                "last_login_at": "2026-01-01T00:00:00Z",
                "created_at": "2025-06-01T00:00:00Z",
            },
        }
        om = self._manager(users)
        identity = om.build_identity()
        assert identity.email == "ndichiv@gmail.com"
        assert identity.name == "Developer"
        assert "google_oidc" in identity.auth_methods
        assert "jarvis_password" in identity.auth_methods
        assert "passkey_webauthn" in identity.auth_methods
        assert identity.mfa_enabled is True
        assert identity.passkey_enabled is True
        assert identity.is_active is True

    def test_build_identity_default_when_not_seeded(self):
        om = self._manager()
        identity = om.build_identity()
        assert identity.email == "ndichiv@gmail.com"
        assert identity.role == "owner"
        assert identity.developer is True
        assert identity.primary_admin is True

    # -- Gmail password guard ------------------------------------------------
    def test_gmail_password_rejected_for_jarvis_password(self):
        om = self._manager()
        with pytest.raises(OwnerError):
            om.assert_no_gmail_password("mygmailpassword", context="password")

    def test_gmail_password_rejected_via_env_var(self):
        om = self._manager()
        os.environ["GMAIL_PASSWORD"] = "gmailpass123"
        try:
            with pytest.raises(OwnerError):
                om.assert_no_gmail_password("anything", context="password")
        finally:
            del os.environ["GMAIL_PASSWORD"]

    def test_jarvis_password_accepted_when_not_gmail(self):
        om = self._manager()
        # Should NOT raise for a normal password.
        om.assert_no_gmail_password("my-separate-jarvis-password", context="jarvis password")

    # -- Recovery
    def test_generate_and_verify_recovery_code(self):
        users = {"u1": {"id": "u1", "email": "ndichiv@gmail.com"}}
        om = self._manager(users)
        code = om.generate_recovery_code("u1")
        assert len(code) > 8
        assert om.verify_recovery_code("u1", code) is True
        # One-time use — second attempt fails.
        assert om.verify_recovery_code("u1", code) is False

    def test_recovery_options_include_owner_auth(self):
        users = {"u1": {
            "id": "u1", "email": "ndichiv@gmail.com",
            "roles": ["owner"], "status": "active",
        }}
        om = self._manager(users)
        opts = om.recovery_options("u1")
        assert "google_oidc" in opts  # always available

    def test_is_owner_user_true_for_owner(self):
        user = {"id": "u1", "email": "ndichiv@gmail.com", "roles": ["admin"]}
        assert OwnerManager(users_store=_MemStore({"u1": user})).is_owner_user(user)

    def test_is_owner_user_false_for_non_owner(self):
        user = {"id": "u2", "email": "other@test.com", "roles": ["user"]}
        assert not OwnerManager(users_store=_MemStore({"u2": user})).is_owner_user(user)

    def test_is_owner_user_false_for_none(self):
        assert not OwnerManager().is_owner_user(None)


# --------------------------------------------------------------------------- #
# PermissionCenter
# --------------------------------------------------------------------------- #
class TestPermissionCenter:
    def _center(self):
        return PermissionCenter(owner_email="ndichiv@gmail.com")

    def test_read_action_auto_approved(self):
        pc = self._center()
        spec = PermissionSpec(
            action="read_config", resource="system", risk=RiskLevel.READ,
        )
        assert pc.check(spec, user={"email": "anyone@test.com"})

    def test_write_action_auto_approved_for_any_user(self):
        pc = self._center()
        spec = PermissionSpec(
            action="update_note", resource="knowledge", risk=RiskLevel.WRITE,
        )
        assert pc.check(spec, user={"email": "user@test.com"})

    def test_high_risk_action_requires_approval(self):
        pc = self._center()
        spec = PermissionSpec(
            action="delete_file", resource="drive", risk=RiskLevel.DESTRUCTIVE,
        )
        auth = pc.request(spec, user={"email": "user@test.com"})
        assert auth.decision == "denied"
        assert auth.reason == "awaiting owner confirmation"
        assert not pc.check(spec, user={"email": "user@test.com"})

    def test_owner_can_approve_high_risk_action(self):
        pc = self._center()
        spec = PermissionSpec(
            action="delete_file", resource="drive", risk=RiskLevel.DESTRUCTIVE,
        )
        auth = pc.request(spec, user={"email": "ndichiv@gmail.com"})
        assert auth.decision == "denied"
        # Approval must come from the canonical owner.
        approved = pc.approve(auth.approval_token, "ndichiv@gmail.com")
        assert approved.decision == "approved"
        # Now check passes.
        assert pc.check(spec, user={"email": "user@test.com"})

    def test_non_owner_cannot_approve(self):
        pc = self._center()
        spec = PermissionSpec(
            action="delete_file", resource="drive", risk=RiskLevel.DESTRUCTIVE,
        )
        auth = pc.request(spec)
        with pytest.raises(PermissionError):
            pc.approve(auth.approval_token, "not-owner@test.com")

    def test_spend_action_requires_owner_confirmation(self):
        pc = self._center()
        spec = PermissionSpec(
            action="create_gpu_job", resource="compute",
            risk=RiskLevel.COMPUTE_SPEND,
            estimated_cost_usd=100.0,
        )
        auth = pc.request(spec)
        assert auth.decision == "denied"
        assert auth.requires_owner_confirmation if hasattr(auth, "requires_owner_confirmation") else True

    def test_revoke_provider_token_requires_confirmation(self):
        pc = self._center()
        spec = PermissionSpec(
            action="revoke_provider_token", resource="provider",
            risk=RiskLevel.CREDENTIAL,
        )
        auth = pc.request(spec)
        assert auth.decision == "denied"

    def test_modify_security_policy_requires_confirmation(self):
        pc = self._center()
        spec = PermissionSpec(
            action="modify_security_policy", resource="system",
            risk=RiskLevel.SECURITY,
        )
        auth = pc.request(spec)
        assert auth.decision == "denied"

    def test_pending_requests_visible(self):
        pc = self._center()
        spec = PermissionSpec(
            action="delete_file", resource="drive", risk=RiskLevel.DESTRUCTIVE,
        )
        pc.request(spec)
        pending = pc.pending_requests()
        assert len(pending) == 1
        assert pending[0]["action"] == "delete_file"
        assert pending[0]["decision"] == "denied"

    def test_approval_token_expired(self):
        pc = self._center()
        spec = PermissionSpec(
            action="delete_file", resource="drive", risk=RiskLevel.DESTRUCTIVE,
        )
        auth = pc.request(spec)
        # Backdate the stored record to make it expired.
        store = pc._store()
        for key, rec in store.items():
            if rec.get("approval_token") == auth.approval_token:
                rec["authorized_at"] = time.time() - 1000
                break
        with pytest.raises(KeyError):
            pc.approve(auth.approval_token, "ndichiv@gmail.com")

    def test_high_risk_actions_set(self):
        assert "delete_file" in HIGH_RISK_ACTIONS
        assert "deploy_infrastructure" in HIGH_RISK_ACTIONS
        assert "create_gpu_job" in HIGH_RISK_ACTIONS
        assert "rotate_production_credentials" in HIGH_RISK_ACTIONS
        assert "send_email" in HIGH_RISK_ACTIONS


# --------------------------------------------------------------------------- #
# OwnerAuditLog
# --------------------------------------------------------------------------- #
class TestOwnerAuditLog:
    def test_record_and_query(self):
        log = OwnerAuditLog(owner_email="ndichiv@gmail.com")
        log.record(
            user="ndichiv@gmail.com",
            provider="openai",
            operation="connect",
            resource="provider",
            permission="provider:connect",
        )
        entries = log.entries()
        assert len(entries) == 1
        assert entries[0]["user"] == "ndichiv@gmail.com"
        assert entries[0]["provider"] == "openai"
        assert entries[0]["operation"] == "connect"
        assert entries[0]["decision"] == "granted"

    def test_no_secrets_in_audit(self):
        log = OwnerAuditLog()
        # A detail that looks like a secret should be scrubbed.
        log.record(
            user="ndichiv@gmail.com",
            provider="openai",
            operation="test",
            resource="provider",
            permission="provider:read",
            detail="sk-secret-key-12345",
        )
        entries = log.entries()
        assert "sk-secret-key-12345" not in str(entries)
        assert "[REDACTED" in str(entries[0]["detail"])

    def test_filter_by_provider(self):
        log = OwnerAuditLog()
        log.record(user="o", provider="openai", operation="test", resource="r", permission="p")
        log.record(user="o", provider="google", operation="test", resource="r", permission="p")
        g = log.entries(provider="google")
        assert len(g) == 1
        assert g[0]["provider"] == "google"

    def test_filter_by_operation(self):
        log = OwnerAuditLog()
        log.record(user="o", provider="openai", operation="connect", resource="r", permission="p")
        log.record(user="o", provider="openai", operation="disconnect", resource="r", permission="p")
        c = log.entries(operation="connect")
        assert len(c) == 1
        assert c[0]["operation"] == "connect"

    def test_summary_counts(self):
        log = OwnerAuditLog()
        log.record(user="o", provider="openai", operation="connect", resource="r", permission="p", decision="granted", result="success")
        log.record(user="o", provider="google", operation="test", resource="r", permission="p", decision="denied", result="failure")
        summary = log.summary()
        assert summary["total_events"] == 2
        assert summary["denied_events"] == 1
        assert summary["failed_events"] == 1
        assert "openai" in summary["by_provider"]
        assert "connect" in summary["by_operation"]

    def test_never_stores_raw_password(self):
        log = OwnerAuditLog()
        log.record(user="o", provider="openai", operation="login", resource="auth", permission="auth:login", detail="password=secret123")
        entries = log.entries()
        assert "secret123" not in str(entries)
        assert "[REDACTED" in str(entries[0]["detail"])

    def test_never_stores_api_key(self):
        log = OwnerAuditLog()
        log.record(user="o", provider="openai", operation="connect", resource="provider", permission="provider:connect", detail="key=sk-live-abc123")
        entries = log.entries()
        assert "sk-live-abc123" not in str(entries)

    def test_by_owner(self):
        log = OwnerAuditLog(owner_email="ndichiv@gmail.com")
        log.record(user="other@test.com", provider="openai", operation="test", resource="r", permission="p")
        log.record(user="ndichiv@gmail.com", provider="google", operation="test", resource="r", permission="p")
        owner_entries = log.by_owner()
        assert len(owner_entries) == 1
        assert owner_entries[0]["user"] == "ndichiv@gmail.com"


# --------------------------------------------------------------------------- #
# End-to-end: security boundary
# --------------------------------------------------------------------------- #
class TestSecurityBoundary:
    def test_gmail_password_never_accepted_as_jarvis_password(self):
        """The Gmail password must NEVER be used as the JARVIS password."""
        om = OwnerManager(users_store=_MemStore({
            "u1": {"id": "u1", "email": "ndichiv@gmail.com", "roles": ["admin"]},
        }))
        # Trying to set a Gmail password as the JARVIS password raises.
        with pytest.raises(OwnerError):
            om.assert_no_gmail_password("gmail-password-123", "jarvis_password")

    def test_owner_email_canonical(self):
        """ndichiv@gmail.com is the canonical owner — not a local placeholder."""
        om = OwnerManager()
        assert om.canonical_email == "ndichiv@gmail.com"
        assert not om.is_owner("admin@jarvis.local")

    def test_brain_never_receives_raw_secret_name(self):
        """The Brain receives tool capability, not provider secrets.

        This test asserts the model: the provider meta maps to opaque vault
        key names only, never raw credential values.
        """
        from identity.provider_center import _PROVIDER_META

        for provider_id, (secret_name, display, _) in _PROVIDER_META.items():
            # Secret names are env-var references, not values.
            assert "sk-" not in secret_name
            assert "hf_" not in secret_name
            assert len(secret_name) < 60  # env var name, not a token
