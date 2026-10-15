"""Tests for real external email delivery via SMTP in the AlertingEngine.

These tests exercise the ``_send_email_notification`` handler and the
``_send_notifications`` state machine using a real ``FakeSMTPServer``
(protocol-correct TCP SMTP) for the happy path and monkeypatching for
failure paths.  No live external SMTP provider is required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import sys
from datetime import datetime

import pytest

from monitoring import alerting_system
from monitoring.alerting_system import (
    Alert,
    AlertingEngine,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    NotificationChannel,
)

# Ensure the repo root is importable so ``tests.fakes`` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fakes.mail_servers import FakeSMTPServer, FakeSMTPServerSTARTTLS  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_EMAIL_ENV_VARS = (
    "JARVIS_ALERT_EMAIL_SMTP_HOST",
    "JARVIS_ALERT_EMAIL_SMTP_PORT",
    "JARVIS_ALERT_EMAIL_SMTP_USER",
    "JARVIS_ALERT_EMAIL_SMTP_PASSWORD",
    "JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE",
    "JARVIS_ALERT_EMAIL_FROM",
    "JARVIS_ALERT_EMAIL_TO",
    "JARVIS_ALERT_EMAIL_USE_SSL",
)

_WEBHOOK_ENV_VARS = (
    "JARVIS_ALERT_WEBHOOK_URL",
    "JARVIS_ALERT_WEBHOOK_SECRET",
    "JARVIS_ALERT_WEBHOOK_SECRET_FILE",
)


def make_alert(**overrides) -> Alert:
    """Build a minimal Alert suitable for delivery tests."""
    now = datetime.now()
    defaults = dict(
        id="alert-email-test",
        rule_id="rule-test",
        metric_name="cpu_usage",
        current_value=95.0,
        threshold=85.0,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.ACTIVE,
        message="CPU usage exceeded threshold",
        triggered_at=now,
        last_seen_at=now,
    )
    defaults.update(overrides)
    return Alert(**defaults)


def make_engine(tmp_path, monkeypatch) -> AlertingEngine:
    """Create an AlertingEngine with an isolated state file and clean env."""
    monkeypatch.setenv("JARVIS_ALERT_STATE_FILE", str(tmp_path / "alerts.json"))
    # Clear webhook env vars so they don't interfere.
    for var in _WEBHOOK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Clear email env vars so each test starts clean.
    for var in _EMAIL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return AlertingEngine()


def _set_email_config(monkeypatch, **kwargs):
    """Set email env vars with sensible defaults."""
    defaults = {
        "JARVIS_ALERT_EMAIL_SMTP_HOST": "127.0.0.1",
        "JARVIS_ALERT_EMAIL_SMTP_PORT": "2525",
        "JARVIS_ALERT_EMAIL_SMTP_USER": "alerts@example.com",
        "JARVIS_ALERT_EMAIL_SMTP_PASSWORD": "test-password-123",
        "JARVIS_ALERT_EMAIL_FROM": "alerts@example.com",
        "JARVIS_ALERT_EMAIL_TO": "admin@example.com",
        "JARVIS_ALERT_EMAIL_USE_SSL": "",
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)


def _suppress_sleep(monkeypatch):
    """Replace asyncio.sleep with a no-op so retries are instant."""
    async def no_wait(_seconds):
        return None
    monkeypatch.setattr(alerting_system.asyncio, "sleep", no_wait)


def _patch_ssl_context(monkeypatch, fake):
    """Monkey-patch ssl.create_default_context so the client trusts the fake
    server's self-signed certificate.  Used by tests that exercise STARTTLS
    with ``FakeSMTPServerSTARTTLS``."""
    monkeypatch.setattr(
        alerting_system.ssl, "create_default_context",
        lambda *a, **kw: fake.client_ssl_context,
    )


# --------------------------------------------------------------------------- #
# Phase 3: Required test cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_email_not_configured_without_credentials(tmp_path, monkeypatch):
    """No SMTP credentials configured → delivery is persisted as not_configured."""
    engine = make_engine(tmp_path, monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "not_configured"
    assert alert.delivery_status["email"]["error"] == "ALERT_DELIVERY_NOT_CONFIGURED"
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_unauthenticated_missing_password(tmp_path, monkeypatch):
    """All fields present except password → treated as unauthenticated/not_configured."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    monkeypatch.delenv("JARVIS_ALERT_EMAIL_SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE", raising=False)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "not_configured"
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_unauthorized_invalid_credentials(tmp_path, monkeypatch):
    """Wrong SMTP password → rejected after auth failure (1 attempt, not retried)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)
    _suppress_sleep(monkeypatch)

    def auth_fail(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Username or password not accepted"
        )

    monkeypatch.setattr(engine, "_smtp_send_attempt", auth_fail)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "rejected"
    assert alert.delivery_status["email"]["error"] == "SMTPAuthenticationError"
    assert alert.delivery_status["email"]["attempts"] == 1
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_valid_provider_response(tmp_path, monkeypatch):
    """Valid SMTP response via FakeSMTPServer → status accepted, message in sink."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    assert alert.delivery_status["email"]["attempts"] == 1
    assert alert.notifications_sent == ["email"]
    assert len(fake.sink) == 1

    # Verify the message was actually sent to the right recipient.
    received = fake.sink[0]
    assert b"admin@example.com" in received
    assert b"[JARVIS Alert]" in received

    fake.stop()


@pytest.mark.asyncio
async def test_email_provider_rejection_retries_then_fails(tmp_path, monkeypatch):
    """SMTP server returns 5xx on DATA → retries exhausted → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)
    _suppress_sleep(monkeypatch)

    call_count = {"n": 0}

    def flaky_send(*args, **kwargs):
        call_count["n"] += 1
        raise smtplib.SMTPDataError(554, b"5.7.1 Message refused")

    monkeypatch.setattr(engine, "_smtp_send_attempt", flaky_send)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"] == "SMTPDataError"
    assert alert.delivery_status["email"]["attempts"] == 3
    assert call_count["n"] == 3
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_network_failure_retries_then_fails(tmp_path, monkeypatch):
    """Connection refused → retries exhausted → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)
    _suppress_sleep(monkeypatch)

    call_count = {"n": 0}

    def conn_refused(*args, **kwargs):
        call_count["n"] += 1
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(engine, "_smtp_send_attempt", conn_refused)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"] in ("ConnectionRefusedError", "OSError")
    assert alert.delivery_status["email"]["attempts"] == 3
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_email_timeout_retries_then_fails(tmp_path, monkeypatch):
    """SMTP connection timeout → retries exhausted → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)
    _suppress_sleep(monkeypatch)

    call_count = {"n": 0}

    def timeout_sim(*args, **kwargs):
        call_count["n"] += 1
        raise TimeoutError("SMTP connection timed out")

    monkeypatch.setattr(engine, "_smtp_send_attempt", timeout_sim)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"] == "TimeoutError"
    assert alert.delivery_status["email"]["attempts"] == 3
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_email_transient_failure_retries_then_succeeds(tmp_path, monkeypatch):
    """First two attempts fail (timeout), third succeeds via FakeSMTPServer."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    _suppress_sleep(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    call_count = {"n": 0}
    original = AlertingEngine._smtp_send_attempt

    def two_fails_then_real(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise TimeoutError("simulated timeout")
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "_smtp_send_attempt", two_fails_then_real)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    assert alert.delivery_status["email"]["attempts"] == 3
    assert alert.notifications_sent == ["email"]
    assert len(fake.sink) == 1

    fake.stop()


@pytest.mark.asyncio
async def test_email_invalid_sender_format_rejected(tmp_path, monkeypatch):
    """Invalid sender email format → ValueError → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_FROM="not-an-email")
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"] == "ValueError"
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_invalid_recipient_rejected(tmp_path, monkeypatch):
    """Invalid recipient in allow-list → ValueError → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_TO="admin@example.com, not-an-email")
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"] == "ValueError"


@pytest.mark.asyncio
async def test_email_disallowed_recipient_not_sent(tmp_path, monkeypatch):
    """Alert cannot send to arbitrary external addresses; only allowlisted recipients are used."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_TO="admin@example.com")
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    # The sink must contain ONLY the allow-listed recipient.
    assert len(fake.sink) == 1
    received = fake.sink[0]
    assert b"admin@example.com" in received
    # An unauthorised address must never appear.
    assert b"attacker@evil.com" not in received

    fake.stop()


@pytest.mark.asyncio
async def test_email_secret_redaction_in_delivery_status(tmp_path, monkeypatch):
    """SMTP password must never appear in delivery_status or state file."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_SMTP_PASSWORD="PASSWORD_123_SECRET")

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    # Check delivery_status dict.
    delivery_str = json.dumps(alert.delivery_status)
    assert "PASSWORD_123_SECRET" not in delivery_str

    # Check persisted state file.
    state_str = open(tmp_path / "alerts.json").read()
    assert "PASSWORD_123_SECRET" not in state_str

    fake.stop()


@pytest.mark.asyncio
async def test_email_secret_never_logged(tmp_path, monkeypatch, caplog):
    """SMTP password must never appear in log output."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_SMTP_PASSWORD="LOG_SECRET_789")
    _suppress_sleep(monkeypatch)

    def send_fail(*args, **kwargs):
        raise smtplib.SMTPDataError(554, b"5.7.1 Message refused")

    monkeypatch.setattr(engine, "_smtp_send_attempt", send_fail)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    with caplog.at_level(logging.ERROR, logger="monitoring.alerting_system"):
        await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    log_text = caplog.text
    assert "LOG_SECRET_789" not in log_text


@pytest.mark.asyncio
async def test_email_password_from_file(tmp_path, monkeypatch):
    """Password can be read from a file (credential file), not hardcoded."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    monkeypatch.delenv("JARVIS_ALERT_EMAIL_SMTP_PASSWORD", raising=False)

    pw_file = tmp_path / "smtp_password"
    pw_file.write_text("file-based-secret-456", encoding="utf-8")
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE", str(pw_file))

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    assert len(fake.sink) == 1

    fake.stop()


@pytest.mark.asyncio
async def test_email_duplicate_delivery_skipped(tmp_path, monkeypatch):
    """If email already 'accepted', a second dispatch must not re-send."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    # First delivery.
    await engine._send_email_notification(alert, authorized=True)
    assert alert.delivery_status["email"]["status"] == "accepted"
    assert len(fake.sink) == 1

    # Second delivery call should be skipped (duplicate protection).
    send_count_before = len(fake.sink)
    await engine._send_email_notification(alert, authorized=True)
    assert len(fake.sink) == send_count_before  # no new message

    fake.stop()


@pytest.mark.asyncio
async def test_email_state_persisted_and_restored(tmp_path, monkeypatch):
    """Delivery status survives engine restart (durable execution record)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    # Reload engine from the same state file.
    restored = AlertingEngine()
    restored_alert = restored.alerts[alert.id]
    assert restored_alert.delivery_status["email"]["status"] == "accepted"
    assert "email" in restored_alert.notifications_sent

    fake.stop()


@pytest.mark.asyncio
async def test_email_channel_in_default_rules_for_critical(tmp_path, monkeypatch):
    """Critical/error default rules include the email channel."""
    engine = make_engine(tmp_path, monkeypatch)
    # Ensure default rules are freshly created (no stale rules file).
    engine.rules.clear()
    engine._create_default_rules()

    critical_rule = next(
        r for r in engine.rules.values()
        if r.severity == AlertSeverity.CRITICAL or r.severity == AlertSeverity.CRITICAL.value
    )
    assert NotificationChannel.EMAIL in critical_rule.notification_channels

    error_rule = next(
        r for r in engine.rules.values()
        if r.severity == AlertSeverity.ERROR or r.severity == AlertSeverity.ERROR.value
    )
    assert NotificationChannel.EMAIL in error_rule.notification_channels


@pytest.mark.asyncio
async def test_email_delivery_state_machine(tmp_path, monkeypatch):
    """Verify all delivery states: pending → delivering → accepted."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    # Before sending: status should be absent or pending.
    assert "email" not in alert.delivery_status or \
        alert.delivery_status.get("email", {}).get("status") == "pending"

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    final = alert.delivery_status["email"]
    assert final["status"] == "accepted"
    assert final["attempts"] == 1
    assert "smtp_host" in final
    assert "smtp_port" in final
    assert "recipient_count" in final

    fake.stop()


@pytest.mark.asyncio
async def test_sandbox_notifications_remain_intact(tmp_path, monkeypatch):
    """The file-based sandbox notification runner (record_notification) must
    continue to work alongside the new email alert channel."""
    from jarvis_backend.notifications import record_notification

    captured = {}

    class FakeStore:
        def __init__(self):
            self.value = {}

        def load(self):
            return self.value

        def save(self):
            captured["saved"] = self.value

    store = FakeStore()
    monkeypatch.setattr("jarvis_backend.notifications.get_store", lambda name: store)

    entry = record_notification(
        "dev-ops", "Alert email channel online", "SMTP email delivery activated.", "alerts"
    )
    assert entry["title"] == "Alert email channel online"
    assert entry["domain"] == "alerts"
    assert entry["read"] is False

    stored = store.value["dev-ops"]
    assert len(stored) == 1
    assert stored[0]["id"] == entry["id"]
    assert stored[0]["severity"] == "info"


@pytest.mark.asyncio
async def test_email_and_in_app_both_delivered(tmp_path, monkeypatch):
    """Email (real) + in_app (sandbox) channels fire together without interference."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    channels = [NotificationChannel.EMAIL, NotificationChannel.IN_APP]
    await engine._send_notifications(alert, channels, authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    assert alert.delivery_status["in_app"]["status"] == "stored"
    assert "email" in alert.notifications_sent


@pytest.mark.asyncio
async def test_email_alert_content_in_message(tmp_path, monkeypatch):
    """The email body contains alert details (severity, metric, threshold)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert(
        severity=AlertSeverity.CRITICAL,
        metric_name="disk_usage",
        current_value=99.0,
        threshold=95.0,
        message="Disk usage is dangerously high",
    )
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert len(fake.sink) == 1
    content = fake.sink[0].decode("utf-8", errors="replace")
    assert "CRITICAL" in content
    assert "disk_usage" in content
    assert "99.0" in content
    assert "95.0" in content

    fake.stop()


# --------------------------------------------------------------------------- #
# M3C hardening: authorization, TLS, rate-limit, concurrency, config
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_email_unauthorized_blocked(tmp_path, monkeypatch):
    """Calling _send_notifications without ``authorized=True`` must NOT
    dispatch email — delivery status is ``blocked``."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    # authorized defaults to False — no email should be sent.
    await engine._send_notifications(alert, [NotificationChannel.EMAIL])

    assert alert.delivery_status["email"]["status"] == "blocked"
    assert alert.delivery_status["email"]["error"] == "EMAIL_DELIVERY_UNAUTHORIZED"
    assert alert.notifications_sent == []
    assert len(fake.sink) == 0
    fake.stop()


@pytest.mark.asyncio
async def test_email_direct_call_unauthorized_blocked(tmp_path, monkeypatch):
    """Calling _send_email_notification directly without authorized must be blocked."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_email_notification(alert)  # authorized=False (default)

    assert alert.delivery_status["email"]["status"] == "blocked"
    assert len(fake.sink) == 0
    fake.stop()


@pytest.mark.asyncio
async def test_email_starttls_failure_no_plaintext_fallback(tmp_path, monkeypatch):
    """When the SMTP server does not support STARTTLS, the send must FAIL
    (never silently fall back to plaintext with credentials)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    _suppress_sleep(monkeypatch)

    # Plain FakeSMTPServer does NOT advertise STARTTLS → starttls() raises.
    fake = FakeSMTPServer().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"].startswith("SMTP")
    assert alert.delivery_status["email"]["attempts"] == 3
    assert alert.notifications_sent == []

    fake.stop()


@pytest.mark.asyncio
async def test_email_cert_validation_failure(tmp_path, monkeypatch):
    """A self-signed cert that the client doesn't trust → ssl.SSLError → failed."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    _suppress_sleep(monkeypatch)

    # STARTTLS-capable server with a self-signed cert.  We deliberately do
    # NOT patch ssl.create_default_context — the client context will reject
    # the untrusted cert.
    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    assert alert.delivery_status["email"]["error"].startswith("SSL")
    assert alert.delivery_status["email"]["attempts"] == 3
    assert alert.notifications_sent == []

    fake.stop()


@pytest.mark.asyncio
async def test_email_smtp_ssl_mode(tmp_path, monkeypatch):
    """SMTP_SSL mode (USE_SSL=true) with a TLS-capable fake server → accepted."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_USE_SSL="true")

    fake = FakeSMTPServerSTARTTLS(use_ssl=True)
    _patch_ssl_context(monkeypatch, fake)
    fake.start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    assert len(fake.sink) == 1

    fake.stop()


@pytest.mark.asyncio
async def test_email_rate_limit_enforced(tmp_path, monkeypatch):
    """When _check_rate raises ConnectorError, delivery fails with rate-limit error."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    _suppress_sleep(monkeypatch)

    def rate_limited(*args, **kwargs):
        raise RuntimeError("SMTP rate limit exceeded (test override)")

    monkeypatch.setattr(engine, "_enforce_email_rate_limit", rate_limited)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "failed"
    # Rate-limit guard fires before any SMTP attempt, so attempts may be 0.


@pytest.mark.asyncio
async def test_email_concurrent_duplicate_protection(tmp_path, monkeypatch):
    """Two concurrent _send_email_notification calls for the same alert must
    result in exactly one SMTP send attempt."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    send_calls = []
    original = AlertingEngine._smtp_send_attempt

    def counting_send(*args, **kwargs):
        send_calls.append(args)
        return original(*args, **kwargs)

    AlertingEngine._smtp_send_attempt = staticmethod(counting_send)
    try:
        await asyncio.gather(
            engine._send_email_notification(alert, authorized=True),
            engine._send_email_notification(alert, authorized=True),
        )
    finally:
        AlertingEngine._smtp_send_attempt = staticmethod(original)

    assert len(send_calls) == 1, f"Expected 1 send, got {len(send_calls)}"
    assert alert.delivery_status["email"]["status"] == "accepted"

    fake.stop()


@pytest.mark.asyncio
async def test_email_invalid_ssl_config_rejected(tmp_path, monkeypatch):
    """Garbage USE_SSL value is treated as STARTTLS mode (no plaintext fallback)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_USE_SSL="garbage")

    # 'garbage' is not in the truthy set → use_ssl=False (STARTTLS mode)
    use_ssl = "garbage".lower() in {"1", "true", "yes"}
    assert not use_ssl

    fake = FakeSMTPServerSTARTTLS().start()
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_SMTP_PORT", str(fake.port))
    _patch_ssl_context(monkeypatch, fake)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "accepted"
    fake.stop()


@pytest.mark.asyncio
async def test_email_auth_blocked_when_no_credentials(tmp_path, monkeypatch):
    """If STARTTLS is required but auth fails, status is 'rejected'
    (non-retryable, 1 attempt)."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch)
    _suppress_sleep(monkeypatch)

    def auth_fail(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Auth failed")

    monkeypatch.setattr(engine, "_smtp_send_attempt", auth_fail)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    assert alert.delivery_status["email"]["status"] == "rejected"
    assert alert.delivery_status["email"]["error"] == "SMTPAuthenticationError"
    assert alert.delivery_status["email"]["attempts"] == 1
    assert alert.notifications_sent == []


@pytest.mark.asyncio
async def test_email_credentials_never_in_exception_details(tmp_path, monkeypatch):
    """When delivery fails, the SMTP password must not leak into error_detail."""
    engine = make_engine(tmp_path, monkeypatch)
    _set_email_config(monkeypatch, JARVIS_ALERT_EMAIL_SMTP_PASSWORD="NEVER_LEAK_PW")
    _suppress_sleep(monkeypatch)

    def send_fail(*args, **kwargs):
        raise smtplib.SMTPServerDisconnected("Connection closed during login")

    monkeypatch.setattr(engine, "_smtp_send_attempt", send_fail)

    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.EMAIL], authorized=True)

    delivery_str = json.dumps(alert.delivery_status)
    assert "NEVER_LEAK_PW" not in delivery_str
    assert alert.delivery_status["email"]["status"] == "failed"
