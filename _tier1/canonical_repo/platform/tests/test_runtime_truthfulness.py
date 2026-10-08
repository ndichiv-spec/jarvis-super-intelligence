from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.mark.asyncio
async def test_kaggle_missing_cli_is_not_available(monkeypatch):
    from jarvis_backend import runtime_status

    monkeypatch.setenv("KAGGLE_USERNAME", "configured-user")
    monkeypatch.setenv("KAGGLE_KEY", "configured-key")

    def missing_cli(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(runtime_status.subprocess, "run", missing_cli)
    status = await runtime_status.check_kaggle_status(probe=True)

    assert status["status"] == "CONFIGURED"
    assert status["configured"] is True
    assert status["cli_installed"] is False
    assert status["executable"] is False


def test_unimplemented_connector_actions_never_report_success(monkeypatch):
    from jarvis_backend.connectors import registry
    from jarvis_backend.connectors.dispatch import execute_connector_action

    monkeypatch.setattr(
        registry, "load",
        lambda kind: {
            "kind": kind,
            "enabled": True,
            "capabilities": ["read", "write", "delete"],
        },
    )
    monkeypatch.setattr(registry, "audit", lambda _event: None)
    for kind, action in (
        ("calendar", "calendar.list"),
        ("files", "files.list"),
    ):
        result = asyncio.run(execute_connector_action(kind, action, {}))
        assert result["ok"] is False
        assert result["status"] == "NOT_IMPLEMENTED"


def test_registered_capabilities_are_not_reported_as_executable(monkeypatch):
    from research_engine import capability_tools

    monkeypatch.setattr(capability_tools, "live_provider_status", lambda: {})
    monkeypatch.setattr(
        capability_tools, "_registry_snapshot",
        lambda *_args: {"state": "UNAVAILABLE", "count": 0},
    )
    monkeypatch.setattr(
        capability_tools, "_registered_risks",
        lambda: {"unprobed.capability": "read"},
    )
    monkeypatch.setattr(
        capability_tools._GitHubBase, "_token",
        staticmethod(lambda: ("configured", "GITHUB_TOKEN")),
    )

    inventory = capability_tools.capability_inventory()
    assert inventory["unprobed.capability"]["state"] == "DEGRADED"
    assert inventory["github.inspect"]["state"] == "CONFIGURED"


@pytest.mark.asyncio
@pytest.mark.parametrize(("inference_verified", "expected_available"), [
    (False, False),
    (True, True),
])
async def test_provider_catalog_requires_verified_inference(
    monkeypatch, inference_verified, expected_available,
):
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
    monkeypatch.delenv("SILVERWING_ENDPOINT", raising=False)
    from jarvis_backend import gateway
    from jarvis_backend.routers import ai, health
    from providers import bootstrap, control_center

    class Silverwing:
        class ModelManager:
            def auth_status(self):
                return {"providers": {}}

            def default_model(self):
                return None

        @staticmethod
        def list_by_provider(_provider):
            return []

    class ProviderControlCenter:
        def list_providers(self):
            return ["openai"]

        def check_provider(self, _provider):
            return SimpleNamespace(
                health_status="healthy",
                capabilities=["chat"],
                configured=True,
                model_list_available=True,
                inference_verified=inference_verified,
                inference_authorized=True,
                display_name="OpenAI",
                errors=None,
                last_checked=1.0,
                actions=["chat"],
                latency_ms=1.0,
            )

    class Adapter:
        base_url = "https://provider.invalid"

        @property
        def models(self):
            return [SimpleNamespace(model_id="model-one")]

    monkeypatch.setattr(gateway, "_load_silverwing", lambda: Silverwing)
    monkeypatch.setattr(gateway, "_ensure_provider_fabric_import_path", lambda: "")
    monkeypatch.setattr(bootstrap, "bootstrap_fabric", lambda: SimpleNamespace(
        _adapters={"openai": Adapter()},
    ))
    monkeypatch.setattr(control_center, "ProviderControlCenter", ProviderControlCenter)
    monkeypatch.setattr(ai, "_probe_endpoint", lambda _endpoint: None)

    async def no_silverwing_probe():
        return {"reachable": False, "model_available": False}

    monkeypatch.setattr(health, "_probe_silverwing", no_silverwing_probe)
    catalog = await ai._provider_catalog()
    openai = next(item for item in catalog["providers"] if item["provider"] == "openai")

    assert openai["inference_verified"] is inference_verified
    assert openai["available"] is expected_available


@pytest.mark.asyncio
async def test_voice_endpoints_do_not_claim_unavailable_audio_processing(monkeypatch):
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "_TTS_AVAILABLE", False)
    speech = await voice.speak(voice.SpeakIn(text="test"))
    listening = await voice.listen(voice.ListenIn())
    status = await voice.voice_status()

    assert speech["success"] is False
    assert speech["status"] == "NOT_IMPLEMENTED"
    assert listening["success"] is False
    assert listening["status"] == "NOT_IMPLEMENTED"
    assert status["status"] == "DEGRADED"
    assert status["audio_streaming_available"] is False


def test_voice_processing_requires_a_started_durable_execution():
    from jarvis_backend.websocket import _voice_request_processed

    assert not _voice_request_processed("FAILED", None)
    assert not _voice_request_processed(
        "FAILED", {"started_at": None},
    )
    assert _voice_request_processed(
        "FAILED", {"started_at": 1.0},
    )


@pytest.mark.asyncio
async def test_unimplemented_agent_scheduler_is_not_reported_running():
    from fastapi import HTTPException

    from jarvis_backend.routers.agents import scheduler_status, toggle_scheduler

    status = await scheduler_status(user={})
    assert status["running"] is False
    assert status["status"] == "NOT_IMPLEMENTED"
    with pytest.raises(HTTPException) as error:
        await toggle_scheduler(body={"running": True}, user={})
    assert error.value.status_code == 501


@pytest.mark.asyncio
async def test_health_status_reflects_database_failure(monkeypatch):
    from jarvis_backend.routers import health

    async def available():
        return {"status": "AVAILABLE"}

    async def unavailable():
        return {"status": "UNAVAILABLE"}

    monkeypatch.setattr(health, "check_auth_status", available)
    monkeypatch.setattr(health, "check_chat_status", available)
    monkeypatch.setattr(health, "check_database_status", unavailable)

    status = await health.health_status()
    assert status["status"] == "degraded"
    assert status["components"]["DATABASE"]["status"] == "UNAVAILABLE"


def test_live_command_events_replay_only_for_the_owner():
    import uuid

    from jarvis_backend.core import create_token, get_store
    from jarvis_backend.runtime import runtime
    from jarvis_backend.websocket import router as websocket_router

    command_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    users = get_store("users").load()
    for user_id in (owner_id, other_id):
        users[user_id] = {"id": user_id, "status": "active"}
    get_store("users").save()

    commands = get_store("commands").load()
    commands[command_id] = {
        "command_id": command_id,
        "user_id": owner_id,
        "status": "EXECUTING",
        "events": [],
    }
    get_store("commands").save()
    runtime.append_event(
        command_id=command_id,
        event_type="command.started",
        payload={"safe": True},
    )

    app = FastAPI()
    app.include_router(websocket_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/commands/{command_id}?after_sequence=0",
            headers={
                "Authorization": f"Bearer {create_token({'sub': owner_id})}",
            },
        ) as socket:
            message = socket.receive_json()
            assert message["type"] == "runtime_event"
            assert message["event"]["type"] == "command.started"
            assert message["event"]["sequence"] == 1

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/ws/commands/{command_id}?after_sequence=0",
            headers={
                "Authorization": f"Bearer {create_token({'sub': other_id})}",
            },
        ):
            pass
