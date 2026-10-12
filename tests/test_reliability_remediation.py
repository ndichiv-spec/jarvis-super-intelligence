from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from jarvis_backend.core import get_current_user
from jarvis_backend.routers import misc, monitoring
from jarvis_backend.ownership import can_access_owner, principal_owner_id, require_owner_access
from jarvis_backend.path_security import resolve_confined_path
from jarvis_backend.routers import health


def _register_verified_user(client, account_email_outbox, email, username):
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "Secure-password-123!",
        },
    )
    assert registered.status_code == 200
    assert registered.json()["status"] == "verification_required"
    token = account_email_outbox[-1][2]
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    ).status_code == 200

    from jarvis_backend.core import get_store

    users = get_store("users")
    user = next(
        item for item in users.load().values()
        if item.get("email", "").lower() == email.lower()
    )
    user["status"] = "active"
    users.save()
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "Secure-password-123!"},
    )
    assert login.status_code == 200
    return login


@pytest.mark.asyncio
async def test_private_routers_reject_anonymous_requests():
    from jarvis_backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        experiments = await client.get("/api/v1/experiments")
        improvements = await client.get("/api/v1/improvements")

    assert experiments.status_code == 401
    assert improvements.status_code == 401


def test_refresh_tokens_rotate_once_and_logout_revokes_session(
    client, account_email_outbox
):
    _register_verified_user(
        client, account_email_outbox, "session-test@example.test", "session-test"
    )
    original_access = client.cookies.get("jarvis_access_token")
    original_refresh = client.cookies.get("jarvis_refresh_token")
    assert original_access and original_refresh
    headers = {"Authorization": f"Bearer {original_access}"}

    sessions = client.get("/api/v1/auth/sessions", headers=headers).json()
    api_keys = client.get("/api/v1/auth/api-keys", headers=headers).json()
    assert len(sessions["sessions"]) == 1
    assert sessions["sessions"][0]["is_current"] is True
    assert api_keys == {"api_keys": []}

    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
        headers={"Origin": "http://localhost:3000"},
    )
    assert rotated.status_code == 200
    tokens = {
        "access_token": client.cookies.get("jarvis_access_token"),
        "refresh_token": client.cookies.get("jarvis_refresh_token"),
    }
    assert tokens["access_token"] and tokens["refresh_token"] != original_refresh
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
        headers={"Origin": "http://localhost:3000"},
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    ).status_code == 200

    assert client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {tokens['access_token']}",
            "Origin": "http://localhost:3000",
        },
        json={"refresh_token": tokens["refresh_token"]},
    ).status_code == 200
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {original_access}"},
    ).status_code == 401


def test_websocket_ticket_is_origin_bound_and_single_use(
    client, account_email_outbox
):
    _register_verified_user(
        client, account_email_outbox, "ws-ticket-test@example.test", "ws-ticket-test"
    )
    headers = {
        "Authorization": f"Bearer {client.cookies.get('jarvis_access_token')}",
        "Origin": "https://jarvis.example.test",
    }
    ticket_response = client.post("/api/v1/auth/ws-ticket", headers=headers)
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]

    with client.websocket_connect(
        f"/ws/health?ticket={ticket}",
        headers={"Origin": "https://jarvis.example.test"},
    ) as websocket:
        websocket.send_text('{"type":"ping"}')
        assert '"event": "ping"' in websocket.receive_text()

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/health?ticket={ticket}",
            headers={"Origin": "https://jarvis.example.test"},
        ):
            pass


def test_owner_identity_and_legacy_records_are_isolated(monkeypatch):
    monkeypatch.setattr("jarvis_backend.ownership.is_admin", lambda _user: False)
    user = {"id": "user-a", "email": "a@example.test", "roles": ["user"]}

    assert principal_owner_id(user) == "user-a"
    assert can_access_owner("user-a", user)
    assert not can_access_owner("user-b", user)
    assert not can_access_owner("system", user)
    with pytest.raises(HTTPException) as error:
        require_owner_access("user-b", user)
    assert getattr(error.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_experiment_listing_is_scoped_to_authenticated_owner(monkeypatch):
    from jarvis_backend.experiment import Experiment
    from jarvis_backend.main import app

    user = {"id": "user-a", "email": "a@example.test", "roles": ["user"]}
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr("jarvis_backend.ownership.is_admin", lambda _user: False)
    monkeypatch.setattr(
        Experiment,
        "list_all",
        staticmethod(
            lambda: [
                SimpleNamespace(owner="user-a", to_dict=lambda: {"id": "owned"}),
                SimpleNamespace(owner="user-b", to_dict=lambda: {"id": "private"}),
                SimpleNamespace(owner="system", to_dict=lambda: {"id": "legacy"}),
            ]
        ),
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/experiments")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == [{"id": "owned"}]


@pytest.mark.asyncio
async def test_improvement_creation_ignores_caller_supplied_owner(monkeypatch):
    from jarvis_backend.main import app
    from jarvis_backend.self_improvement import SelfImprovementCycle

    user = {"id": "user-a", "email": "a@example.test", "roles": ["user"]}
    captured: dict[str, object] = {}

    def create_cycle(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            improvement_id="impr_test",
            status="identified",
            target_capability=kwargs["target_capability"],
        )

    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(SelfImprovementCycle, "create", create_cycle)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/improvements/create",
                json={"target_capability": "chat", "owner": "user-b"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert captured["owner"] == "user-a"


@pytest.mark.asyncio
async def test_readiness_does_not_depend_on_model_provider(monkeypatch):
    from jarvis_backend.gateway import ProviderGateway
    from jarvis_backend.routers import ai

    monkeypatch.setattr(ProviderGateway, "probe_brain", AsyncMock(return_value={"healthy": False}))
    monkeypatch.setattr(ai, "_provider_catalog", AsyncMock(return_value={"providers": []}))
    monkeypatch.setattr(health, "_probe_silverwing", AsyncMock(return_value={"reachable": False}))
    monkeypatch.setattr(
        health,
        "check_database_status",
        AsyncMock(return_value={"status": "AVAILABLE"}),
    )
    monkeypatch.setattr(
        "jarvis_backend.celery_app.get_queue_runtime_status",
        lambda: {"worker_probe": "unavailable"},
    )

    snapshot = await health._readiness_snapshot()

    assert snapshot["status"] == "ready"
    assert snapshot["provider_availability"] == "unavailable"


@pytest.mark.asyncio
async def test_frontend_discovery_uses_only_configured_origin(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return SimpleNamespace(status_code=404)

    import httpx

    monkeypatch.setenv("JARVIS_APP_URL", "https://jarvis.example.test")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await health.frontend_discovery()

    assert result == {
        "configured": True,
        "reachable": True,
        "url": "https://jarvis.example.test",
        "status_code": 404,
    }


@pytest.mark.asyncio
async def test_frontend_discovery_rejects_credentials_and_paths(monkeypatch):
    monkeypatch.setenv("JARVIS_APP_URL", "http://user:password@example.test/private")

    result = await health.frontend_discovery()

    assert result["configured"] is False
    assert result["reachable"] is False
    assert result["url"] is None


@pytest.mark.asyncio
async def test_unconfigured_cascade_never_reports_success():
    health_result = await misc.cascade_health()
    assert health_result["status"] == "unavailable"
    with pytest.raises(HTTPException) as error:
        await misc.cascade_initialize()
    assert error.value.status_code == 501


@pytest.mark.asyncio
async def test_monitoring_health_score_uses_measured_values(monkeypatch):
    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {
            "available": True,
            "cpu_percent": 50,
            "memory": {"percent": 60},
            "disk": 50,
        },
    )

    report = await monitoring.health_report()

    assert report["health_score"] == 46


@pytest.mark.asyncio
async def test_monitoring_never_reports_unimplemented_recovery_as_success():
    with pytest.raises(HTTPException) as optimize_error:
        await monitoring.optimize()
    assert optimize_error.value.status_code == 501
    assert optimize_error.value.detail["code"] == "NOT_IMPLEMENTED"

    with pytest.raises(HTTPException) as recovery_error:
        await monitoring.trigger_recovery()
    assert recovery_error.value.status_code == 501
    assert recovery_error.value.detail["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_diagnostics_health_is_derived_from_actual_metrics(monkeypatch):
    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {
            "available": True,
            "cpu_percent": 97,
            "memory": {"percent": 60},
            "disk": 50,
        },
    )

    report = await monitoring.system_diagnostics()

    assert report["status"] == "degraded"
    assert report["healthy"] is False
    assert report["checks"]["cpu"] is False


@pytest.mark.asyncio
async def test_monitoring_health_reports_measured_degradation(monkeypatch):
    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {
            "available": True,
            "cpu_percent": 97,
            "memory": {"percent": 60},
            "disk": 50,
        },
    )

    assert (await monitoring.monitoring_health())["status"] == "degraded"


def test_cognitive_memory_requires_auth_and_is_scoped_to_its_owner(client, auth_headers):
    from uuid import uuid4

    from jarvis_backend.core import create_token, get_store

    assert client.get("/api/v1/cognitive/memory/recall").status_code == 401
    stored = client.post(
        "/api/v1/cognitive/memory/store",
        json={"content": "owner-only phrase", "layer": "short_term"},
        headers=auth_headers,
    )
    assert stored.status_code == 200

    other_id = f"memory-owner-{uuid4()}"
    users = get_store("users").load()
    users[other_id] = {
        "id": other_id,
        "email": f"{other_id}@test.local",
        "is_active": True,
        "roles": ["user"],
    }
    get_store("users").save()
    other_headers = {"Authorization": f"******"}

    other_headers.update({
        "Authorization": f"Bearer {create_token({'sub': other_id, 'user_id': other_id})}"
    })
    recall = client.get(
        "/api/v1/cognitive/memory/recall",
        headers=other_headers,
    )
    assert recall.status_code == 200
    assert recall.json()["results"] == []
    assert client.get(
        f"/api/v1/cognitive/user/{other_id}/profile",
        headers=auth_headers,
    ).status_code == 404

    processed = client.post(
        "/api/v1/cognitive/process",
        json={
            "user_input": "question",
            "ai_response": "answer",
            "user_id": other_id,
        },
        headers=auth_headers,
    )
    assert processed.status_code == 200
    owner_record = get_store("memory").load()[processed.json()["memory_id"]]
    assert owner_record["user_id"] == "testuser"


def test_voice_asr_never_returns_synthetic_empty_success(client, auth_headers):
    result = client.post(
        "/api/v1/voice/listen",
        json={"timeout": 1},
        headers=auth_headers,
    )
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

    status = client.get("/api/v1/voice/status")
    assert status.status_code == 200
    assert status.json()["asr_status"] == "NOT_CONFIGURED"
    assert status.json()["streaming_available"] is False


def test_self_improvement_owner_survives_serialization():
    from jarvis_backend.self_improvement import SelfImprovementCycle

    cycle = SelfImprovementCycle(
        improvement_id="impr_test",
        mission_id="",
        target_capability="chat",
        baseline_model="test-model",
        baseline_revision="main",
        problem_statement="",
        owner="user-a",
    )

    assert SelfImprovementCycle.from_dict(cycle.to_dict()).owner == "user-a"


def test_user_paths_must_resolve_inside_configured_data_roots(tmp_path, monkeypatch):
    data_file = tmp_path / "dataset.jsonl"
    data_file.write_text('{"text":"sample"}\n', encoding="utf-8")
    monkeypatch.setenv("JARVIS_ALLOWED_DATA_ROOTS", str(tmp_path))

    assert resolve_confined_path(str(data_file)) == data_file.resolve()
    monkeypatch.setenv("JARVIS_ALLOWED_DATA_ROOTS", str(tmp_path / "different-root"))
    with pytest.raises(ValueError, match="outside configured"):
        resolve_confined_path(str(data_file))
