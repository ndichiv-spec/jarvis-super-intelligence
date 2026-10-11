"""Unimplemented connector types must not claim readiness or execution."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.parametrize(
    ("kind", "action"),
    [
        ("calendar", "calendar.list"),
        ("files", "files.list"),
    ],
)
def test_unimplemented_connector_reports_unavailable(
    tmp_path, monkeypatch, kind, action
):
    from jarvis_backend.connectors import registry
    from jarvis_backend.connectors.dispatch import (
        execute_connector_action,
        list_connectors,
    )

    connector_dir = tmp_path / "connectors"
    audit_dir = tmp_path / "audit"
    monkeypatch.setattr(registry, "CONNECTORS_DIR", connector_dir)
    monkeypatch.setattr(registry, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(registry, "AUDIT_FILE", audit_dir / "connectors.jsonl")
    registry.save({
        "kind": kind,
        "owner_user_id": "user-1",
        "enabled": True,
        "capabilities": ["read", "write", "delete"],
    })

    result = asyncio.run(execute_connector_action(kind, action, {}, user_id="user-1"))
    status = next(
        connector for connector in list_connectors(user_id="user-1") if connector["kind"] == kind
    )

    assert result["ok"] is False
    assert "not implemented" in result["error"].lower()
    assert "result" not in result
    assert status["configured"] is False
    assert status["available"] is False
    assert status["connection_status"] == "Unavailable"
    assert status["actions"] == []


def test_user_cannot_list_another_owners_connector(tmp_path, monkeypatch):
    from jarvis_backend.connectors import registry
    from jarvis_backend.connectors.dispatch import list_connectors

    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    registry.save({
        "kind": "email",
        "owner_user_id": "owner-1",
        "password": "test-secret",
        "enabled": True,
    })

    owner_status = next(c for c in list_connectors("owner-1") if c["kind"] == "email")
    other_status = next(c for c in list_connectors("owner-2") if c["kind"] == "email")
    assert owner_status["configured"] is True
    assert other_status["configured"] is False
