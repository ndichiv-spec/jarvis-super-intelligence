"""Phase 2.1 — SQL persistence tests.

Verifies the SQL-backed Store (replacing core's ephemeral JSON-file store)
keeps sessions / messages / refresh-tokens / user data durable across an
in-process "restart" (cache cleared, DB retained), that backend selection
respects ``DATABASE_URL`` / ``JARVIS_TEST_MODE``, and that the migration
script creates the ``jarvis_kv`` schema.
"""
from __future__ import annotations

import os


# --------------------------------------------------------------------------- #
# Backend / URL selection (pure, no engine connection attempted)
# --------------------------------------------------------------------------- #
def test_default_database_is_sqlite_file(monkeypatch):
    from jarvis_backend import db

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)
    monkeypatch.delenv("JARVIS_TEST_MODE", raising=False)
    url = db.database_url()
    assert url.startswith("sqlite:///")
    assert "jarvis.db" in url


def test_test_mode_uses_in_memory(monkeypatch):
    from jarvis_backend import db

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)
    assert db.database_url() == "sqlite://"


def test_postgres_url_is_selected_via_env(monkeypatch):
    from jarvis_backend import db

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@host:5432/jarvis")
    url = db.database_url()
    assert url.startswith("postgresql")


# --------------------------------------------------------------------------- #
# Migration / schema
# --------------------------------------------------------------------------- #
def test_migration_creates_kv_table():
    from sqlalchemy import inspect

    from jarvis_backend import db

    db.create_db_and_tables()
    tables = inspect(db.get_engine()).get_table_names()
    assert "jarvis_kv" in tables


def test_reset_database_clears_persisted_data():
    from jarvis_backend import core, db

    core.data.clear()
    db.reset_database()
    core.get_store("users").load()  # touch to initialise cache
    core.get_store("users").load()["u-x"] = {"id": "u-x", "email": "x@example.com"}
    core.get_store("users").save()
    assert db.kv_load("users") == {"u-x": {"id": "u-x", "email": "x@example.com"}}

    # A full reset (cache + db) must leave the store empty.
    core.data.clear()
    db.reset_database()
    assert core.get_store("users").load() == {}


# --------------------------------------------------------------------------- #
# Durability across an in-process "restart" (cache dropped, DB retained)
# --------------------------------------------------------------------------- #
def test_user_data_survives_restart():
    from jarvis_backend import core

    users = core.get_store("users").load()
    users["u-1"] = {
        "id": "u-1", "email": "a@example.com", "username": "a",
        "roles": ["user"], "created_at": core.now_iso(),
    }
    core.get_store("users").save()

    # Simulate a process restart: the in-process Store cache is lost, but the
    # SQL backend persists.
    core.data.clear()
    reloaded = core.get_store("users").load()
    assert reloaded["u-1"]["email"] == "a@example.com"
    assert reloaded["u-1"]["roles"] == ["user"]


def test_refresh_token_survives_restart():
    from jarvis_backend import core

    refresh = core.create_refresh_token("user-abc", session_id="sid-1")
    core.data.clear()  # cache lost; DB retains the jti

    access = core.refresh_access_token(refresh)
    assert access is not None
    payload = core.decode_token(access)
    assert payload["sub"] == "user-abc"
    assert payload["sid"] == "sid-1"


def test_chat_session_with_messages_survives_restart():
    from jarvis_backend import chat_service, core

    svc = chat_service.ChatService()
    svc.create_session("user-1", "sess-restart", "Restart test")
    # Persist a message into the session (mirrors send_message's store usage).
    sessions = core.get_store("chat_sessions").load()
    sessions["sess-restart"]["messages"].append(
        {"id": "m1", "role": "user", "content": "hello", "status": "COMPLETED"}
    )
    core.get_store("chat_sessions").save()

    core.data.clear()
    svc2 = chat_service.ChatService()
    session = svc2.get_session("user-1", "sess-restart")
    assert session["title"] == "Restart test"
    assert session["messages"][0]["content"] == "hello"


def test_list_store_preserves_order_and_durability():
    from jarvis_backend import core

    logs = core.get_store("audit_logs").load()
    logs.extend([{"a": 1}, {"a": 2}, {"a": 3}])
    core.get_store("audit_logs").save()

    core.data.clear()
    reloaded = core.get_store("audit_logs").load()
    assert reloaded == [{"a": 1}, {"a": 2}, {"a": 3}]
