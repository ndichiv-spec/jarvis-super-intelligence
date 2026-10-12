from __future__ import annotations

import pytest

from jarvis_backend import db


def test_postgresql_engine_uses_bounded_health_checked_pool(monkeypatch):
    captured = {}
    engine = object()

    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(
        db, "database_url",
        lambda: "postgresql+psycopg2://jarvis@example.test/jarvis?sslmode=require",
    )

    def capture_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return engine

    monkeypatch.setattr(db, "create_engine", capture_create_engine)
    assert db.get_engine() is engine

    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 5
    assert captured["max_overflow"] == 5
    assert captured["pool_timeout"] == 10
    assert captured["pool_recycle"] == 1800
    assert captured["connect_args"] == {"connect_timeout": 10}
    assert "sslmode=require" in captured["url"]


def test_postgresql_pool_settings_are_configurable(monkeypatch):
    monkeypatch.setenv("JARVIS_DB_POOL_SIZE", "3")
    monkeypatch.setenv("JARVIS_DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv("JARVIS_DB_POOL_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("JARVIS_DB_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("JARVIS_DB_CONNECT_TIMEOUT_SECONDS", "6")

    assert db._postgres_engine_options() == {
        "pool_pre_ping": True,
        "pool_size": 3,
        "max_overflow": 0,
        "pool_timeout": 4,
        "pool_recycle": 900,
        "connect_args": {"connect_timeout": 6},
    }


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_invalid_postgresql_pool_setting_fails_clearly(monkeypatch, value):
    monkeypatch.setenv("JARVIS_DB_POOL_SIZE", value)
    with pytest.raises(RuntimeError, match="JARVIS_DB_POOL_SIZE"):
        db._postgres_engine_options()
