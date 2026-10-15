"""Admin-only external alert-delivery test endpoint.

External dispatch is opt-in and guarded by admin authorization, request
throttling, SMTP delivery controls, and security audit logging.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, status

from monitoring.alerting_system import (
    Alert,
    AlertSeverity,
    AlertStatus,
    NotificationChannel,
    get_alerting_engine,
)

from ..core import _audit_system_action, _require_admin

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

# Process-local defense in depth. Production multi-worker deployments must
# also enforce a shared limit at the gateway or through a shared store.
_REQUEST_LIMIT = 5
_WINDOW_SECONDS = 15 * 60
_attempts: deque[float] = deque()
_attempts_lock = threading.Lock()
_RESOURCE = "/api/v1/alerts/test-delivery"
_ACTION = "alert_email_test_delivery"


def _consume_request_slot() -> bool:
    now = time.monotonic()
    with _attempts_lock:
        while _attempts and now - _attempts[0] >= _WINDOW_SECONDS:
            _attempts.popleft()
        if len(_attempts) >= _REQUEST_LIMIT:
            return False
        _attempts.append(now)
        return True


def _actor_label(admin: dict) -> str:
    """Return an audit identity without recording credentials or tokens."""
    for key in ("email", "id", "sub", "user_id"):
        value = admin.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:254]
    return "authenticated-admin"


@router.post("/test-delivery")
async def test_alert_email_delivery(admin: dict = Depends(_require_admin)):  # noqa: B008
    """Send one test alert to the recipient configured in the SMTP allow-list."""
    actor = _actor_label(admin)

    # Fail closed: only the literal value "true" enables external dispatch.
    if os.environ.get("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "").strip().lower() != "true":
        _audit_system_action(
            "blocked", _ACTION, _RESOURCE, user_email=actor,
            detail="external_delivery_disabled",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "EXTERNAL_ALERT_DELIVERY_DISABLED"},
        )

    if not _consume_request_slot():
        _audit_system_action(
            "rate_limited", _ACTION, _RESOURCE, user_email=actor,
            detail="endpoint_rate_limit_exceeded",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "EXTERNAL_ALERT_DELIVERY_RATE_LIMITED"},
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )

    # Ephemeral alert: do not register this diagnostic event as a real
    # monitoring alert or leave a fake active alert in persisted alert state.
    alert = Alert(
        id=f"external-delivery-test-{uuid.uuid4()}",
        rule_id="manual_external_delivery_test",
        metric_name="smtp_delivery_test",
        current_value=0.0,
        threshold=0.0,
        severity=AlertSeverity.INFO,
        status=AlertStatus.ACTIVE,
        message="JARVIS administrator-requested email delivery test",
        details={"source": "admin_test_endpoint"},
    )

    _audit_system_action(
        "attempted", _ACTION, _RESOURCE, user_email=actor, detail="dispatch_started",
    )
    try:
        await get_alerting_engine()._send_notifications(
            alert, [NotificationChannel.EMAIL], authorized=True,
        )
    except Exception as exc:
        _audit_system_action(
            "failed", _ACTION, _RESOURCE, user_email=actor,
            detail=f"dispatch_exception={type(exc).__name__}",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "ALERT_EMAIL_DELIVERY_FAILED"},
        ) from None

    delivery = alert.delivery_status.get(NotificationChannel.EMAIL.value, {})
    state = delivery.get("status", "failed")
    if state == "accepted":
        _audit_system_action(
            "succeeded", _ACTION, _RESOURCE, user_email=actor,
            detail="smtp_server_accepted_message",
        )
        return {
            "status": "accepted",
            "alert_id": alert.id,
            "smtp_accepted": True,
            "message": (
                "The SMTP server accepted the test message; mailbox delivery is not verified."
            ),
        }

    _audit_system_action(
        "not_configured" if state == "not_configured" else "failed",
        _ACTION, _RESOURCE, user_email=actor, detail=f"delivery_status={str(state)[:40]}",
    )
    code = (
        "ALERT_EMAIL_DELIVERY_NOT_CONFIGURED"
        if state == "not_configured"
        else "ALERT_EMAIL_DELIVERY_FAILED"
    )
    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if state == "not_configured"
        else status.HTTP_502_BAD_GATEWAY
    )
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "status": state},
    )
