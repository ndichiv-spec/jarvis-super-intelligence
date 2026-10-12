import asyncio

import pytest
from fastapi import HTTPException

from jarvis_backend.connectors import oauth, registry
from jarvis_backend.routers import connectors


def test_oauth_callback_binds_saved_tokens_and_connector_to_state_owner(
    client, monkeypatch, tmp_path
):
    import json

    from jarvis_backend.connectors.mail.gmail_oauth import GmailOAuthConnector

    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    monkeypatch.setenv("JARVIS_APP_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps({"gmail": {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth.example/token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "is_google": True,
    }}))

    class TokenResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "access_token": "callback-access-token",
                "refresh_token": "callback-refresh-token",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            }

    monkeypatch.setattr(oauth.httpx, "post", lambda *_args, **_kwargs: TokenResponse())
    monkeypatch.setattr(GmailOAuthConnector, "test", lambda _self: {"ok": True})
    owner_id = "oauth-owner-a"
    state = oauth.make_state("gmail", owner_id)

    response = client.get(
        "/api/v1/connectors/oauth/callback/gmail",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://jarvis.example/dashboard/connections?connected=gmail"
    )
    assert "callback-access-token" not in response.text
    owner_config = registry.load("gmail", user_id=owner_id)
    assert owner_config is not None
    assert owner_config["owner_user_id"] == owner_id
    assert owner_config["oauth_user_id"] == owner_id
    assert registry.load("gmail", user_id="oauth-owner-b") is None
    assert oauth.load_tokens("gmail", owner_id)["access_token"] == "callback-access-token"
    assert oauth.load_tokens("gmail", "oauth-owner-b") is None
    assert "callback-access-token" not in json.dumps(registry.public_config(owner_config))
    assert [e["operation"] for e in registry.read_audit(user_id=owner_id)] == ["connected"]
    assert registry.read_audit(user_id="oauth-owner-b") == []


def test_oauth_callback_rejects_invalid_state_without_exchanging_code(
    client, monkeypatch
):
    import json

    monkeypatch.setenv("JARVIS_APP_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps({"gmail": {
        "client_id": "client-id", "client_secret": "client-secret",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth.example/token", "scope": "mail.read",
    }}))
    monkeypatch.setattr(
        oauth.httpx, "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("invalid state exchanged")),
    )
    state = oauth.make_state("gmail", "oauth-owner-invalid")
    payload, _, signature = state.partition(".")
    tampered = f"{payload[:-1]}{'A' if payload[-1] != 'A' else 'B'}.{signature}"

    response = client.get(
        "/api/v1/connectors/oauth/callback/gmail",
        params={"code": "authorization-code", "state": tampered},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        "?oauth_error=invalid_state&provider=gmail"
    )
    assert oauth.load_tokens("gmail", "oauth-owner-invalid") is None


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
