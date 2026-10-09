"""Regression coverage for persisted image generation artifacts."""
import base64
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis_backend.capabilities import image_generation
from jarvis_backend.capability import ExecutionContext


@pytest.mark.asyncio
async def test_openai_image_generation_persists_real_artifact_without_prompt_telemetry(
    monkeypatch,
    tmp_path,
):
    image_bytes = b"real-provider-image-bytes"
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    captured_artifacts = []
    captured_audit = []
    captured_events = []

    class FakeOpenAIClient:
        def __init__(self, *, api_key):
            assert api_key == "configured-test-key"
            self.images = SimpleNamespace(
                generate=lambda **_: SimpleNamespace(
                    data=[SimpleNamespace(b64_json=encoded_image)],
                ),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "configured-test-key")
    monkeypatch.setenv("JARVIS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=FakeOpenAIClient),
    )
    monkeypatch.setattr(
        image_generation.ArtifactRepository,
        "store_artifact",
        lambda **artifact: captured_artifacts.append(artifact) or "artifact-id",
    )
    monkeypatch.setattr(
        image_generation.AuditLog,
        "log",
        lambda **event: captured_audit.append(event),
    )
    monkeypatch.setattr(
        image_generation.ProviderStateRepository,
        "update_state",
        lambda *_args, **_kwargs: None,
    )

    capability = image_generation.ImageGenerationCapability()
    monkeypatch.setattr(
        capability._event_bus,
        "emit",
        lambda **event: captured_events.append(event),
    )

    result = await capability.execute(
        {
            "prompt": "a private prompt that must not enter telemetry",
            "provider": "openai",
            "model": "dall-e-3",
        },
        ExecutionContext(user_id="user-1", session_id="session-1"),
    )

    assert result.success is True
    assert len(result.artifacts) == 1
    saved = Path(result.artifacts[0]["file_path"])
    assert saved.read_bytes() == image_bytes
    assert captured_artifacts[0]["session_id"] == "session-1"
    assert captured_artifacts[0]["metadata"]["owner_id"] == "user-1"
    assert "prompt" not in captured_events[0]["payload"]
    assert "private prompt" not in str(captured_audit[0])
    completed = captured_events[-1]
    assert completed["event_type"] == "image.generation.completed"
    assert completed["user_id"] == "user-1"
    assert completed["session_id"] == "session-1"
    assert completed["payload"]["execution_id"]
    assert completed["payload"]["artifact_ids"] == ["artifact-id"]
    assert "prompt" not in completed["payload"]


@pytest.mark.asyncio
async def test_image_generation_failure_emits_failed_event(monkeypatch):
    captured_events = []
    monkeypatch.setattr(
        image_generation.AuditLog,
        "log",
        lambda **_event: None,
    )
    capability = image_generation.ImageGenerationCapability()
    monkeypatch.setattr(
        capability._event_bus,
        "emit",
        lambda **event: captured_events.append(event),
    )

    async def fail_generation(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(capability, "_generate_image", fail_generation)
    result = await capability.execute(
        {"prompt": "an image prompt"},
        ExecutionContext(user_id="user-1", session_id="session-1"),
    )

    assert result.success is False
    assert captured_events[-1]["event_type"] == "image.generation.failed"
    assert captured_events[-1]["status"] == "failed"
    assert captured_events[-1]["user_id"] == "user-1"
    assert captured_events[-1]["session_id"] == "session-1"
