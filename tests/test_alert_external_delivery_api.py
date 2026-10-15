"""API security tests for admin-triggered external alert delivery."""
from __future__ import annotations

import time

import pytest

from jarvis_backend.routers import alert_delivery
from monitoring.alerting_system import NotificationChannel


class FakeAlertingEngine:
    def __init__(self, delivery_state: str = "accepted"):
        self.delivery_state = delivery_state
        self.calls = []

    async def _send_notifications(self, alert, channels, authorized=False):
        self.calls.append((alert, list(channels), authorized))
        alert.delivery_status[NotificationChannel.EMAIL.value] = {
            "status": self.delivery_state,
            "attempts": 1,
        }


@pytest.fixture(autouse=True)
def reset_endpoint_rate_limit():
    with alert_delivery._attempts_lock:
        alert_delivery._attempts.clear()
    yield
    with alert_delivery._attempts_lock:
        alert_delivery._attempts.clear()


def capture_audit(monkeypatch):
    entries = []

    def record(*args, **kwargs):
        entries.append((args, kwargs))

    monkeypatch.setattr(alert_delivery, "_audit_system_action", record)
    return entries


def test_requires_authentication(client, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine()
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)

    response = client.post("/api/v1/alerts/test-delivery")

    assert response.status_code == 401
    assert engine.calls == []


def test_requires_admin(client, auth_headers, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine()
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)

    response = client.post("/api/v1/alerts/test-delivery", headers=auth_headers)

    assert response.status_code == 403
    assert engine.calls == []


@pytest.mark.parametrize("value", [None, "", "1", "yes", "on", "false", "0"])
def test_feature_flag_fails_closed(client, admin_headers, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", raising=False)
    else:
        monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", value)
    engine = FakeAlertingEngine()
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)
    audit = capture_audit(monkeypatch)

    response = client.post("/api/v1/alerts/test-delivery", headers=admin_headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "EXTERNAL_ALERT_DELIVERY_DISABLED"
    assert engine.calls == []
    assert audit


def test_admin_can_trigger_delivery_when_enabled(client, admin_headers, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine("accepted")
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)
    audit = capture_audit(monkeypatch)

    response = client.post("/api/v1/alerts/test-delivery", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    assert response.json()["smtp_accepted"] is True
    assert len(engine.calls) == 1
    alert, channels, authorized = engine.calls[0]
    assert channels == [NotificationChannel.EMAIL]
    assert authorized is True
    assert alert.details == {"source": "admin_test_endpoint"}
    assert audit
    # The diagnostic alert must not be registered as a real monitoring alert.
    assert not hasattr(engine, "alerts")


def test_delivery_failure_is_sanitized(client, admin_headers, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine("failed")
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)

    response = client.post("/api/v1/alerts/test-delivery", headers=admin_headers)

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ALERT_EMAIL_DELIVERY_FAILED"
    assert "password" not in response.text.lower()
    assert len(engine.calls) == 1


def test_missing_smtp_configuration_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine("not_configured")
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)

    response = client.post("/api/v1/alerts/test-delivery", headers=admin_headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ALERT_EMAIL_DELIVERY_NOT_CONFIGURED"


def test_endpoint_rate_limit_blocks_extra_dispatch(client, admin_headers, monkeypatch):
    monkeypatch.setenv("JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY", "true")
    engine = FakeAlertingEngine()
    monkeypatch.setattr(alert_delivery, "get_alerting_engine", lambda: engine)
    now = time.monotonic()
    with alert_delivery._attempts_lock:
        alert_delivery._attempts.extend([now] * alert_delivery._REQUEST_LIMIT)

    response = client.post("/api/v1/alerts/test-delivery", headers=admin_headers)

    assert response.status_code == 429
    assert response.headers.get("retry-after")
    assert engine.calls == []
