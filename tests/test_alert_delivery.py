from __future__ import annotations

import hashlib
import hmac
import json
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


def make_alert() -> Alert:
    now = datetime.now()
    return Alert(
        id="alert-test",
        rule_id="rule-test",
        metric_name="queue_depth",
        current_value=12,
        threshold=10,
        severity=AlertSeverity.ERROR,
        status=AlertStatus.ACTIVE,
        message="Queue depth exceeded threshold",
        triggered_at=now,
        last_seen_at=now,
    )


def make_engine(tmp_path, monkeypatch) -> AlertingEngine:
    monkeypatch.setenv("JARVIS_ALERT_STATE_FILE", str(tmp_path / "alerts.json"))
    monkeypatch.delenv("JARVIS_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("JARVIS_ALERT_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("JARVIS_ALERT_WEBHOOK_SECRET_FILE", raising=False)
    return AlertingEngine()


@pytest.mark.asyncio
async def test_missing_webhook_receiver_is_persisted_as_not_configured(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, monkeypatch)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)

    await engine._send_notifications(alert, [NotificationChannel.WEBHOOK])

    assert alert.delivery_status["webhook"]["status"] == "not_configured"
    assert alert.delivery_status["webhook"]["error"] == "ALERT_DELIVERY_NOT_CONFIGURED"
    assert alert.notifications_sent == []
    restored = AlertingEngine()
    assert restored.alerts[alert.id].delivery_status["webhook"]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_signed_webhook_retries_transient_failure_and_persists_success(
    tmp_path, monkeypatch
):
    engine = make_engine(tmp_path, monkeypatch)
    secret = "a-test-signing-secret-that-is-at-least-32-chars"
    monkeypatch.setenv("JARVIS_ALERT_WEBHOOK_URL", "https://alerts.example.com/jarvis")
    monkeypatch.setenv("JARVIS_ALERT_WEBHOOK_SECRET", secret)
    alert = make_alert()
    engine.alerts[alert.id] = alert
    engine.alert_history.append(alert)
    statuses = iter((503, 202))
    requests = []

    def post_webhook(request):
        requests.append(request)
        return next(statuses)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(engine, "_post_webhook", post_webhook)
    monkeypatch.setattr(alerting_system.asyncio, "sleep", no_wait)

    await engine._send_notifications(alert, [NotificationChannel.WEBHOOK])

    assert alert.delivery_status["webhook"]["status"] == "delivered"
    assert alert.delivery_status["webhook"]["attempts"] == 2
    assert alert.delivery_status["webhook"]["http_status"] == 202
    assert alert.notifications_sent == ["webhook"]
    assert len(requests) == 2
    payload = requests[-1].data
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert requests[-1].get_header("X-jarvis-signature") == f"sha256={expected}"
    assert json.loads(payload)["id"] == alert.id
    assert AlertingEngine().alerts[alert.id].delivery_status["webhook"]["status"] == "delivered"


@pytest.mark.asyncio
async def test_repeated_active_rule_updates_one_alert_instead_of_spamming(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, monkeypatch)
    rule = AlertRule(
        id="queue-backlog",
        name="Queue backlog",
        description="Queue depth limit",
        metric_name="queue_depth",
        condition="gt",
        threshold=10,
        severity=AlertSeverity.WARNING,
    )

    await engine._create_alert(rule, 12, {"unit": "jobs"})
    await engine._create_alert(rule, 15, {"unit": "jobs"})

    assert len(engine.alerts) == 1
    alert = next(iter(engine.alerts.values()))
    assert alert.occurrences == 2
    assert alert.current_value == 15
    assert AlertingEngine().alerts[alert.id].occurrences == 2
