"""Real orchestration-path integration tests; these do not mock execution."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_backend.core import get_current_user
from jarvis_backend.routers import commands


def test_provider_unavailable_command_persists_failure_and_events(monkeypatch):
    from providers.secrets import get_secret_manager

    secrets = get_secret_manager()
    if any(
        secrets.get(name)
        for name in (
            "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
            "NVIDIA_API_KEY", "NVIDIA_API_TOKEN", "NIM_API_KEY",
            "HF_TOKEN", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
            "MISTRAL_API_KEY", "COHERE_API_KEY", "TOGETHER_API_KEY",
            "DEEPSEEK_API_KEY", "brain_api_key",
        )
    ):
        pytest.skip("Configured provider credentials require a separate live E2E.")

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    for name in (
        "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
        "NVIDIA_API_KEY", "NVIDIA_API_TOKEN", "NIM_API_KEY",
        "JARVIS_BRAIN_ENDPOINT", "SILVERWING_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)

    user = {"id": "runtime-integration-user", "roles": []}
    app = FastAPI()
    app.include_router(commands.router)
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/commands",
            json={"goal": "Answer using the configured provider."},
        )
        assert response.status_code == 202
        command_id = response.json()["command_id"]

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/v1/commands/{command_id}").json()
            if snapshot["status"] in {
                "COMPLETED", "PARTIAL", "FAILED", "CANCELLED",
                "RECOVERY_REQUIRED",
            }:
                break
            time.sleep(0.02)

        assert snapshot["status"] == "FAILED"
        executions = client.get(
            f"/api/v1/commands/{command_id}/executions",
        ).json()["executions"]
        assert len(executions) == 1
        assert executions[0]["status"] == "FAILED"
        replay = client.get(
            f"/api/v1/commands/{command_id}/events",
        ).json()["events"]
        assert replay
        assert [event["sequence"] for event in replay] == sorted(
            {event["sequence"] for event in replay}
        )
