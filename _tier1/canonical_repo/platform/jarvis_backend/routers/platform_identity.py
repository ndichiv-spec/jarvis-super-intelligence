"""Platform Identity resource (spec §2) + editable notification config.

Real platform state, persisted in the ``platform_identity`` store. Provider
secrets are NEVER exposed or accepted here -- only configured-provider names
and presence flags. Identity writes are audit-logged (spec §6 / §14).
"""
from __future__ import annotations

import os
import platform as _platform
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..core import ai_service, get_store, now_iso, _require_admin
from .system import _PROVIDER_KEYS

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

# Keys shaped like secrets are rejected on PUT (spec §12 invariant: this
# layer never accepts/echoes provider credentials, even accidentally).
_SECRET_SHAPES = ("key", "secret", "token", "password", "credential", "private_key")
_ALLOWED_TRANSPORT: set[str] = {"smtp", "none", "unavailable"}


class IdentityUpdateIn(BaseModel):
    production_email_identity: str | None = None
    developer_identity: str | None = None
    environment: str | None = None
    notification_configuration: dict[str, Any] | None = None


def _smtp_available() -> bool:
    """Truthful SMTP availability: derived from env, never fabricated."""
    return bool(os.environ.get("SMTP_HOST") or os.environ.get("SMTP_USER"))


def _configured_providers() -> list[str]:
    """Provider names with a stored credential -- values are NOT exposed."""
    settings = get_store("misc").load().get("provider_settings") or {}
    return [name for name, key in _PROVIDER_KEYS if settings.get(key)]


def _load_identity() -> dict[str, Any]:
    """Current persisted identity (a real dict store, empty on first run)."""
    data = get_store("platform_identity").load()
    return data if isinstance(data, dict) else {}


def _build_identity() -> dict[str, Any]:
    raw = _load_identity()
    configured = _configured_providers()
    notify_raw = raw.get("notification_configuration") or {}
    transport = notify_raw.get("transport") or ("smtp" if _smtp_available() else "unavailable")
    verified = bool(raw.get("production_email_identity")) or bool(configured)
    return {
        "platform_name": "JARVIS Unified System",
        "environment": raw.get("environment") or os.environ.get("JARVIS_ENV", "development"),
        "instance_id": _platform.node(),
        "version": "3.0.0",
        "production_email_identity": raw.get("production_email_identity"),
        "developer_identity": raw.get("developer_identity"),
        # Derived, not fabricated: verified only when identity or a provider exists.
        "verification_status": "verified" if verified else "unverified",
        "notification_configuration": {
            "transport": transport,
            "email_enabled": bool(raw.get("production_email_identity")) and transport == "smtp",
            "default_recipient": notify_raw.get("default_recipient"),
        },
        "ai_enabled": bool(getattr(ai_service, "enabled", False)),
        # Configured provider NAMES only -- secrets stay in the credential
        # store and are never mediated through the identity/resource layer.
        "configured_providers": configured,
        "provider_count": len(configured),
        "provenance": "jarvis_backend/routers/platform_identity.py",
        "last_checked": now_iso(),
    }


def _audit_identity(action: str, fields: list[str]) -> None:
    """Append an identity event to the existing audit trail (spec §6/#14)."""
    try:
        log = get_store("audit_logs").load()
        if not isinstance(log, list):
            log = []
        log.append({
            "ts": now_iso(),
            "kind": "identity",
            "action": action,
            "actor": "api",
            "fields": fields,
        })
        get_store("audit_logs").save()
    except Exception:  # noqa: BLE001 -- audit must never break a request
        pass


@router.get("/identity")
async def get_identity():
    """Platform Identity resource (spec §2). Read-only view of real state."""
    return _build_identity()


@router.put("/identity")
async def update_identity(request: Request, user: Dict[str, Any] = Depends(_require_admin)):
    """Persist editable identity fields; audit-logged (spec §6 / #14)."""
    try:
        raw_body = await request.json()
    except Exception:
        raw_body = {}
    if not isinstance(raw_body, dict):
        raw_body = {}

    # Inspect the RAW body before any Pydantic binding: this layer must never
    # accept secret-shaped keys (spec §12 invariant), so we gate ahead of
    # ``IdentityUpdateIn``, which would otherwise silently drop unknown fields.
    for k in raw_body:
        if any(s in k.lower() for s in _SECRET_SHAPES):
            raise HTTPException(
                status_code=400,
                detail=f"Refusing secret-shaped field '{k}' via identity API",
            )

    body = IdentityUpdateIn(**raw_body)
    payload = body.model_dump(exclude_none=True)

    notify = payload.get("notification_configuration")
    if notify is not None:
        transport = notify.get("transport") or ("smtp" if _smtp_available() else "unavailable")
        if transport not in _ALLOWED_TRANSPORT:
            raise HTTPException(
                status_code=400,
                detail="notification_configuration.transport must be smtp|none|unavailable",
            )
        payload["notification_configuration"] = {
            "transport": transport,
            "default_recipient": notify.get("default_recipient"),
        }

    raw = _load_identity()
    raw.update(payload)
    get_store("platform_identity").save()
    _audit_identity("updated", list(payload.keys()))
    return _build_identity()
