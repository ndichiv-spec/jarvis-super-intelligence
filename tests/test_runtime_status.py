"""Tests for the canonical runtime-status claims."""
from __future__ import annotations

import asyncio


def test_provider_status_distinguishes_configuration_from_inference(monkeypatch):
    from jarvis_backend.routers import ai
    from jarvis_backend import runtime_status

    async def catalog():
        return {
            "providers": [{
                "provider": "google",
                "configured": True,
                "available": False,
                "inference_verified": False,
                "streaming_verified": False,
                "capabilities": ["chat", "streaming"],
            }],
        }

    monkeypatch.setattr(ai, "_provider_catalog", catalog)

    result = asyncio.run(runtime_status._provider_runtime_status())

    assert result["status"] == "CONFIGURED"
    assert result["providers"][0]["status"] == "CONFIGURED"
    assert result["verified_count"] == 0


def test_streaming_status_requires_successful_stream_in_this_process(monkeypatch):
    from jarvis_backend import runtime_status

    configured_provider = {
        "provider": "google",
        "configured": True,
        "streaming_verified": False,
        "capabilities": ["streaming"],
    }
    status = {"providers": [configured_provider]}
    unverified = asyncio.run(runtime_status._streaming_runtime_status(status))
    assert unverified["status"] == "CONFIGURED"
    assert unverified["streaming_verified"] is False

    configured_provider["streaming_verified"] = True
    verified = asyncio.run(runtime_status._streaming_runtime_status(status))
    assert verified["status"] == "AVAILABLE"
    assert verified["streaming_verified"] is True


def test_canonical_status_covers_requested_runtime_components(monkeypatch):
    from jarvis_backend import runtime_status as status

    def result(value):
        async def get_result(*args, **kwargs):
            return value
        return get_result

    available = {"status": "AVAILABLE"}
    unconfigured = {"status": "UNCONFIGURED"}
    configured_providers = {
        "status": "CONFIGURED",
        "providers": [{
            "provider": "google",
            "status": "CONFIGURED",
            "configured": True,
            "inference_verified": False,
            "streaming_verified": False,
            "capabilities": ["chat", "streaming"],
        }],
        "configured_count": 1,
        "verified_count": 0,
    }
    for name in (
        "check_auth_status",
        "check_chat_status",
        "check_database_status",
        "check_openai_status",
        "check_google_status",
        "check_nvidia_status",
        "check_brain_status",
        "check_silverwing_status",
        "check_kaggle_status",
        "check_huggingface_status",
        "_command_runtime_status",
    ):
        monkeypatch.setattr(status, name, result(available))
    monkeypatch.setattr(
        status,
        "check_brain_status",
        result({"status": "UNCONFIGURED"}),
    )
    monkeypatch.setattr(
        status,
        "check_silverwing_status",
        result({"status": "UNREACHABLE"}),
    )
    monkeypatch.setattr(status, "_provider_runtime_status", result(configured_providers))
    monkeypatch.setattr(status, "_celery_runtime_status", result(unconfigured))
    monkeypatch.setattr(status, "_memory_runtime_status", result(available))
    monkeypatch.setattr(status, "_voice_runtime_status", result(unconfigured))
    monkeypatch.setattr(status, "_tool_runtime_status", result(available))
    monkeypatch.setattr(status, "_agent_runtime_status", result(unconfigured))
    monkeypatch.setattr(status, "_redis_runtime_status", result(unconfigured))
    monkeypatch.setattr(status, "_streaming_runtime_status", result(unconfigured))
    monkeypatch.setattr(
        status,
        "_modality_runtime_status",
        result({"VISION": unconfigured, "IMAGE_GENERATION": unconfigured}),
    )

    response = asyncio.run(status.build_canonical_runtime_status())

    required = {
        "BACKEND", "DATABASE", "REDIS", "CELERY", "PROVIDER_GATEWAY",
        "PROVIDERS", "CONVERSATION", "STREAMING", "MEMORY", "VOICE",
        "VISION", "IMAGE_GENERATION", "TOOLS", "AGENTS", "SILVERWING",
    }
    assert required <= response["components"].keys()
    assert response["status"] == "DEGRADED"
    assert response["components"]["PROVIDERS"][0]["status"] == "CONFIGURED"


def test_grpc_shutdown_closes_embedded_server(monkeypatch):
    from jarvis_backend import grpc_server

    class StubServer:
        stopped = False
        terminated = False

        async def stop(self, grace):
            self.stopped = grace == 0

        async def wait_for_termination(self):
            self.terminated = True

    server = StubServer()
    monkeypatch.setattr(grpc_server, "_SERVER", server)
    asyncio.run(grpc_server.stop_grpc_server(grace=0))

    assert server.stopped is True
    assert server.terminated is True
    assert grpc_server._SERVER is None


def test_vision_health_does_not_equate_credentials_with_verified_inference(monkeypatch):
    from jarvis_backend.capabilities.vision import VisionCapability

    monkeypatch.setenv("GOOGLE_API_KEY", "presence-only-test-value")
    result = asyncio.run(VisionCapability()._check_health())

    assert result["status"].value == "configured"
    assert result["configured"] is True
    assert result["healthy"] is False
    assert result["inference_verified"] is False


def test_image_generation_health_does_not_equate_key_with_generation(monkeypatch):
    from jarvis_backend.capabilities.image_generation import ImageGenerationCapability
    from jarvis_backend.persistence import ProviderStateRepository

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("STABILITY_API_KEY", "presence-only-test-value")
    monkeypatch.setattr(
        ProviderStateRepository,
        "update_state",
        lambda *args, **kwargs: None,
    )
    result = asyncio.run(ImageGenerationCapability()._check_health())

    assert result["status"].value == "configured"
    assert result["configured"] is True
    assert result["healthy"] is False
    assert result["generation_verified"] is False
