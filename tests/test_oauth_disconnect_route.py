import asyncio

import pytest
from fastapi import HTTPException

from jarvis_backend.connectors import oauth, registry
from jarvis_backend.routers import connectors


def test_oauth_disconnect_removes_only_local_credentials(monkeypatch):
    deleted = []
    audit_events = []
    monkeypatch.setattr(connectors, "_require_admin", lambda user: user)
    monkeypatch.setattr(
        registry,
        "load",
        lambda kind, user_id=None: (
            {"oauth_user_id": "another-user"}
            if kind == "gmail" and user_id == "user-1"
            else None
        ),
    )
    monkeypatch.setattr(
        registry,
        "delete",
        lambda kind, user_id=None: deleted.append((kind, user_id)) or True,
    )
    monkeypatch.setattr(oauth, "delete_tokens", lambda kind, user_id: user_id == "user-1")
    monkeypatch.setattr(oauth, "audit_record", lambda **event: audit_events.append(event))

    response = asyncio.run(connectors.oauth_disconnect(
        "gmail",
        {"id": "user-1", "username": "admin"},
    ))

    assert response == {"success": True, "local_credentials_removed": True}
    assert deleted == []
    assert audit_events[0]["operation"] == "disconnect"
    assert audit_events[0]["user_id"] == "user-1"


def test_oauth_disconnect_rejects_non_oauth_connector(monkeypatch):
    monkeypatch.setattr(connectors, "_require_admin", lambda user: user)

    with pytest.raises(HTTPException) as error:
        asyncio.run(connectors.oauth_disconnect(
            "email",
            {"id": "user-1", "username": "admin"},
        ))

    assert error.value.status_code == 404


def test_oauth_consent_denial_redirects_safely_and_audits_user(monkeypatch):
    audit_events = []
    monkeypatch.setattr(oauth, "verify_state", lambda state: ("gmail", "user-1"))
    monkeypatch.setattr(oauth, "audit_record", lambda **event: audit_events.append(event))
    monkeypatch.setenv("JARVIS_APP_URL", "https://jarvis.example")

    response = asyncio.run(connectors.oauth_callback(
        "gmail", state="valid-state", error="access_denied"))

    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://jarvis.example/dashboard/connections?oauth_error=access_denied&provider=gmail"
    )
    assert audit_events[0]["user_id"] == "user-1"
    assert audit_events[0]["detail"] == "provider consent was not granted"


def test_oauth_exchange_failure_redirects_without_leaking_provider_details(monkeypatch):
    audit_events = []
    monkeypatch.setattr(oauth, "client_config", lambda kind: {"scope": "mail.read"})
    monkeypatch.setattr(oauth, "verify_state", lambda state: ("gmail", "user-1"))
    monkeypatch.setattr(
        oauth, "exchange_code",
        lambda *args: (_ for _ in ()).throw(oauth.OAuthError("provider response included private data")),
    )
    monkeypatch.setattr(oauth, "audit_record", lambda **event: audit_events.append(event))
    monkeypatch.setenv("JARVIS_APP_URL", "https://jarvis.example")

    response = asyncio.run(connectors.oauth_callback(
        "gmail", code="authorization-code", state="valid-state"))

    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://jarvis.example/dashboard/connections?oauth_error=exchange_failed&provider=gmail"
    )
    assert audit_events[0]["user_id"] == "user-1"
