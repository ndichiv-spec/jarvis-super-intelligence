"""Integration checks for the canonical JARVIS runtime boundaries."""

import pytest
from fastapi.testclient import TestClient

from infrastructure.errors import ErrorHandler, JarvisError, error_response
from jarvis_backend.chat_service import ChatService
from jarvis_backend.main import app


class FakeGateway:
    timeout = 1
    max_retries = 0

    async def chat(self, messages, model=None, system=None, timeout=None):
        return {
            "content": "Integration response",
            "model": "test:model",
            "provider": "test",
            "latency_ms": 1,
            "usage": {},
        }


@pytest.mark.asyncio
async def test_chat_service_processes_a_message_through_the_provider_contract():
    service = ChatService(gateway=FakeGateway())
    service.create_session("integration-user", "integration-chat")

    result = await service.send_message(
        "integration-user", "integration-chat", "Hello, JARVIS"
    )

    assert result["status"] == "COMPLETED"
    assert result["message"] == "Integration response"
    assert result["provider"] == "test"


def test_structured_error_contract_preserves_safe_error_fields():
    result = error_response(
        JarvisError(message="Test error", subsystem="integration_test")
    )

    assert result["error"] is True
    assert result["message"] == "Test error"
    assert result["subsystem"] == "integration_test"


def test_asgi_error_handler_is_constructible():
    async def empty_app(scope, receive, send):
        return None

    assert ErrorHandler(empty_app) is not None


def test_canonical_health_endpoint_is_available():
    response = TestClient(app).get("/api/v1/health/status")

    assert response.status_code == 200
    assert response.json()["alive"] is True


def test_unsupported_omega_endpoint_is_not_advertised_as_available():
    response = TestClient(app).get("/api/v1/omega/status")

    assert response.status_code == 404
