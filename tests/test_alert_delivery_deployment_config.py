"""Production Compose tests for SMTP alert delivery wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_maps_smtp_secrets_and_fail_closed_alert_flag():
    compose_path = ROOT / "deployment" / "production" / "docker-compose.prod.yml"
    with compose_path.open("r", encoding="utf-8") as stream:
        compose = yaml.safe_load(stream)

    environment = compose["services"]["jarvis"]["environment"]

    assert environment["JARVIS_ALERT_EMAIL_SMTP_HOST"] == "${SMTP_HOST:-}"
    assert environment["JARVIS_ALERT_EMAIL_SMTP_PORT"] == "${SMTP_PORT:-587}"
    assert environment["JARVIS_ALERT_EMAIL_SMTP_USER"] == "${SMTP_USER:-}"
    assert environment["JARVIS_ALERT_EMAIL_FROM"] == "${SMTP_FROM:-}"
    assert environment["JARVIS_ALERT_EMAIL_TO"] == "${JARVIS_ALERT_EMAIL_TO:-}"
    assert environment["JARVIS_ALERT_EMAIL_USE_SSL"] == "${SMTP_USE_SSL:-false}"
    assert environment["JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE"] == "/run/secrets/smtp_password"
    assert (
        environment["JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY"]
        == "${JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY:-false}"
    )

    # The exact secret path is defined by Compose, not a committed password.
    assert compose["secrets"]["smtp_password"]["file"] == (
        "${SMTP_PASSWORD_FILE_SOURCE:?Set SMTP_PASSWORD_FILE_SOURCE}"
    )
