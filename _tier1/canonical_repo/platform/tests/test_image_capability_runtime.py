from __future__ import annotations

import asyncio
import base64
import json

import pytest

from jarvis_backend.media_storage import (
    issue_generated_image_reference,
    revoke_media,
)
from research_engine.capability_tools import (
    NOT_CONFIGURED,
    ImageGenerationTool,
    capability_inventory,
)
from research_engine.tool_registry import (
    DefaultPermissionPolicy,
    ToolContext,
    ToolRegistry,
)


class _ProviderResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _ImageProviderClient:
    responses: list[_ProviderResponse] = []
    requests: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append((url, json or {}))
        return self.responses.pop(0)


def _valid_png_base64() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-image").decode("ascii")


def test_image_generation_times_out_and_does_not_retry(monkeypatch, tmp_path):
    import jarvis_backend.media_storage as storage
    import jarvis_backend.routers.media as media

    class _SlowImageProviderClient(_ImageProviderClient):
        async def post(self, url, *, headers=None, json=None, **kwargs):
            self.requests.append((url, json or {}))
            await asyncio.sleep(1)

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setattr(media._httpx, "AsyncClient", _SlowImageProviderClient)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(ImageGenerationTool, "timeout_seconds", 0.01)
    _SlowImageProviderClient.requests = []
    registry = ToolRegistry(DefaultPermissionPolicy({
        "image-timeout:image.generate": True,
    })).register(ImageGenerationTool())

    result = asyncio.run(registry.invoke(
        "image.generate",
        {"prompt": "a blue fox"},
        ToolContext(user_id="image-timeout"),
    ))

    assert not result.success
    assert "timed out" in result.error
    assert len(_SlowImageProviderClient.requests) == 1


def test_image_generation_propagates_cancellation(monkeypatch, tmp_path):
    import jarvis_backend.media_storage as storage
    import jarvis_backend.routers.media as media

    async def exercise_cancellation():
        request_started = asyncio.Event()
        requests = []

        class _BlockingImageProviderClient(_ImageProviderClient):
            async def post(self, url, *, headers=None, json=None, **kwargs):
                requests.append(url)
                request_started.set()
                await asyncio.Event().wait()

        monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
        monkeypatch.setattr(
            media._httpx, "AsyncClient", _BlockingImageProviderClient,
        )
        monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
        registry = ToolRegistry(DefaultPermissionPolicy({
            "image-cancel:image.generate": True,
        })).register(ImageGenerationTool())
        task = asyncio.create_task(registry.invoke(
            "image.generate",
            {"prompt": "a blue fox"},
            ToolContext(user_id="image-cancel"),
        ))
        await asyncio.wait_for(request_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(requests) == 1

    asyncio.run(exercise_cancellation())


def test_image_generation_uses_existing_tool_authorization_and_reports_missing_config(
    monkeypatch,
):
    for name in (
        "OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI",
        "REPLICATE_API_KEY", "STABILITY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    inventory = capability_inventory()["image.generate"]
    assert inventory["state"] == NOT_CONFIGURED
    assert inventory["availability"] == "not_configured"
    assert inventory["health"] == "unknown"
    assert inventory["operational"] is False

    policy = DefaultPermissionPolicy({
        "image-owner:image.generate": True,
    })
    registry = ToolRegistry(policy=policy).register(ImageGenerationTool())
    result = asyncio.run(registry.invoke(
        "image.generate",
        {"prompt": "a blue fox"},
        ToolContext(user_id="image-owner"),
    ))

    assert not result.success
    assert "Set OPENAI_API_KEY" in result.error
    assert not _ImageProviderClient.requests


def test_configured_image_provider_is_unverified_consistently(
    client, auth_headers, monkeypatch,
):
    import research_engine.capability_tools as capability_tools

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    for name in ("JARVIS_API_KEY_OPENAI", "REPLICATE_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(capability_tools, "live_provider_status", lambda: {})

    inventory = capability_inventory()["image.generate"]
    response = client.get("/api/v1/image/providers", headers=auth_headers)

    assert response.status_code == 200, response.text
    openai = response.json()["providers"]["openai"]
    assert inventory["state"] == "DEGRADED"
    assert inventory["availability"] == openai["availability"] == "configured_unverified"
    assert inventory["health"] == "unknown"
    assert inventory["operational"] is False
    assert inventory["configured_providers"] == ["openai"]
    assert openai["configured"] is True
    assert "not been verified" in openai["summary"]
    assert "fixture-key" not in response.text


def test_image_capability_requires_confirmation_and_blocks_credential_prompts(
    monkeypatch,
):
    import jarvis_backend.routers.media as media

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setattr(media._httpx, "AsyncClient", _ImageProviderClient)
    _ImageProviderClient.requests = []
    _ImageProviderClient.responses = [
        _ProviderResponse(200, {"data": [{"b64_json": _valid_png_base64()}]}),
    ]
    registry = ToolRegistry().register(ImageGenerationTool())
    denied = asyncio.run(registry.invoke(
        "image.generate",
        {"prompt": "a blue fox"},
        ToolContext(user_id="image-owner"),
    ))
    assert not denied.success
    assert "requires_user_confirmation" in denied.error
    assert not _ImageProviderClient.requests

    policy = DefaultPermissionPolicy({
        "image-owner:image.generate": True,
    })
    registry = ToolRegistry(policy=policy).register(ImageGenerationTool())
    rejected_prompt = asyncio.run(registry.invoke(
        "image.generate",
        {"prompt": "api_key=secret-value"},
        ToolContext(user_id="image-owner"),
    ))
    assert not rejected_prompt.success
    assert "credential-shaped" in rejected_prompt.error
    assert not _ImageProviderClient.requests


def test_authenticated_chat_executes_and_presents_provider_generated_image(
    client, auth_headers, monkeypatch, tmp_path,
):
    import jarvis_backend.media_storage as storage
    import jarvis_backend.routers.media as media
    import research_engine.capability_tools as capability_tools

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    for name in ("JARVIS_API_KEY_OPENAI", "REPLICATE_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(media._httpx, "AsyncClient", _ImageProviderClient)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(
        capability_tools, "live_provider_status", lambda: {},
    )
    _ImageProviderClient.requests = []
    _ImageProviderClient.responses = [
        _ProviderResponse(200, {"data": [{"b64_json": _valid_png_base64()}]}),
    ]

    chat_request = {
        "session_id": "image-runtime-conversation",
        "client_message_id": "image-runtime-request",
        "message": "Generate an image of a blue fox under the northern lights.",
    }
    response = client.post("/api/chat", headers=auth_headers, json=chat_request)

    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["status"] == "COMPLETED", reply
    command_response = client.get(
        f"/api/v1/commands/{reply['runtime_command_id']}",
        headers=auth_headers,
    )
    assert command_response.status_code == 200, command_response.text
    command = command_response.json()
    assert command["selected_capability_id"] == "image.generate", command
    assert "Generated 1 image" in reply["message"], {
        "command_result": command.get("result"),
        "errors": command.get("errors"),
    }
    assert reply["presentation"]["contract_version"] == "1.1"
    assert reply["presentation"]["environment"] == "image"
    assert reply["presentation"]["correlation"]["request_id"] == (
        "image-runtime-request"
    )
    assert reply["presentation"]["correlation"]["conversation_id"] == (
        "image-runtime-conversation"
    )
    command_id = reply["runtime_command_id"]
    assert reply["presentation"]["correlation"]["command_id"] == command_id
    assert reply["presentation"]["correlation"]["execution_id"]
    assert len(_ImageProviderClient.requests) == 1
    assert _ImageProviderClient.requests[0][0] == (
        "https://api.openai.com/v1/images/generations"
    )
    replay = client.post("/api/chat", headers=auth_headers, json=chat_request)
    assert replay.status_code == 200, replay.text
    assert replay.json()["resumed"] is True
    assert replay.json()["runtime_command_id"] == command_id
    assert len(_ImageProviderClient.requests) == 1

    media_ref = reply["presentation"]["media_refs"][0]
    image_item = reply["presentation"]["components"][1]["items"][0]
    assert image_item["media_ref"] == media_ref["id"]
    assert media_ref["url"].startswith("/api/v1/media/")
    assert "fixture-key" not in json.dumps(reply["presentation"])
    assert client.get(media_ref["url"]).content.startswith(b"\x89PNG\r\n\x1a\n")
    assert issue_generated_image_reference(
        asset_id=media_ref["id"],
        owner_id="another-owner",
    ) is None
    assert not revoke_media(
        asset_id=media_ref["id"],
        owner_id="another-owner",
    )

    revision_response = client.get(
        f"/api/v1/presentations/{command_id}/revisions",
        headers=auth_headers,
    )
    assert revision_response.status_code == 200
    revisions = revision_response.json()["revisions"]
    assert len(revisions) == 1
    assert revisions[0]["presentation"]["presentation_id"] == (
        reply["presentation"]["presentation_id"]
    )

    events_response = client.get(
        f"/api/v1/commands/{command_id}/events",
        headers=auth_headers,
    )
    assert events_response.status_code == 200
    event_names = [
        event.get("type") or event.get("event") or event.get("event_type")
        for event in events_response.json()["events"]
    ]
    assert event_names.index("world.execution.selected") < event_names.index(
        "world.execution.started"
    )
    assert event_names.index("world.execution.completed") < event_names.index(
        "world.result.observed"
    )
    assert event_names.index("world.result.observed") < event_names.index(
        "presentation.updated"
    )
    assert client.delete(
        f"/api/v1/media/{media_ref['id']}",
        headers=auth_headers,
    ).status_code == 200
    assert client.get(media_ref["url"]).status_code == 404


def test_authenticated_chat_reports_bad_provider_output_without_success(
    client, auth_headers, monkeypatch, tmp_path,
):
    import jarvis_backend.media_storage as storage
    import jarvis_backend.routers.media as media
    import research_engine.capability_tools as capability_tools

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setattr(media._httpx, "AsyncClient", _ImageProviderClient)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(
        capability_tools, "live_provider_status", lambda: {},
    )
    _ImageProviderClient.requests = []
    _ImageProviderClient.responses = [
        _ProviderResponse(200, {"data": [{"b64_json": "not-base64"}]}),
    ]

    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={
            "session_id": "image-invalid-output",
            "client_message_id": "image-invalid-output-request",
            "message": "Create a picture of a blue fox.",
        },
    )

    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["status"] != "COMPLETED"
    assert reply["presentation"]["task_state"]["status"] == "error"
    assert "No result is claimed" in reply["message"]
