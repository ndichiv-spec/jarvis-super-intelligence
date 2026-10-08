"""
Security Gate Regression Tests.

Tests that verify sensitive control-plane operations cannot be called anonymously.

Classification (as determined by security audit):
- PUBLIC: Health/readiness endpoints, documentation, model discovery
- AUTHENTICATED USER: Chat, agent operations, model registration, knowledge/memory access
- ADMIN/OPERATOR: System control, provider settings, user management
- SERVICE-TO-SERVICE: API key protected endpoints
- INTERNAL ONLY: Host-level operations

These tests verify the boundary between PUBLIC and AUTHENTICATED endpoints.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# --------------------------------------------------------------------------- #
# Public endpoints (should NOT require authentication)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_root_manifest_no_auth(client: AsyncClient):
    """GET / should return service manifest without authentication."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data.get("service") == "JARVIS API"
    assert "component" in data


@pytest.mark.asyncio
async def test_health_live_no_auth(client: AsyncClient):
    """GET /health/live should be public (liveness check)."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json().get("status") == "alive"


@pytest.mark.asyncio
async def test_health_ready_public(client: AsyncClient):
    """GET /health/ready may be public but should reportBrainz health honestly."""
    response = await client.get("/health/ready")
    # May be 200 or 503 depending on Brain availability
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
async def test_health_basic_no_auth(client: AsyncClient):
    """GET /health and related endpoints should be public."""
    response = await client.get("/api/v1/health/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_status_no_auth(client: AsyncClient):
    """GET /api/status should be public."""
    response = await client.get("/api/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_capabilities_no_auth(client: AsyncClient):
    """GET /api/capabilities should be public."""
    response = await client.get("/api/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "chat" in data


@pytest.mark.asyncio
async def test_api_models_list_no_auth(client: AsyncClient):
    """GET /api/models should be public (model discovery)."""
    response = await client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data


@pytest.mark.asyncio
async def test_openapi_docs_no_auth(client: AsyncClient):
    """OpenAPI/Swagger documentation should be public."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    
    response = await client.get("/docs")
    assert response.status_code == 200
    
    response = await client.get("/redoc")
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Endpoints that DO require authentication (should return 401 unauthenticated)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_ai_process_requires_auth(client: AsyncClient):
    """POST /api/v1/ai/process should require authentication."""
    response = await client.post("/api/v1/ai/process", json={"input": "Hello"})
    # Should be 401 Unauthorized or return structured error
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ai_feedback_requires_auth(client: AsyncClient):
    """POST /api/v1/ai/feedback should require authentication."""
    response = await client.post("/api/v1/ai/feedback", json={
        "query": "test",
        "response": "test response",
        "rating": 5
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ai_tasks_create_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/task should require authentication."""
    response = await client.post("/api/v1/agents/task", json={"name": "test", "description": "test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ai_tasks_list_requires_auth(client: AsyncClient):
    """GET /api/v1/ai/tasks should require authentication."""
    response = await client.get("/api/v1/ai/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_toggle_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/tasks/{id}/toggle should require authentication."""
    response = await client.post("/api/v1/agents/tasks/test-id/toggle", json={"enabled": True})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_run_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/tasks/{id}/run should require authentication."""
    response = await client.post("/api/v1/agents/tasks/test-id/run")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_delete_requires_auth(client: AsyncClient):
    """DELETE /api/v1/agents/tasks/{id} should require authentication."""
    response = await client.delete("/api/v1/agents/tasks/test-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_scheduler_toggle_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/scheduler/toggle should require authentication."""
    response = await client.post("/api/v1/agents/scheduler/toggle", json={"running": True})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_collab_task_create_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/collaboration/task/create should require authentication."""
    response = await client.post("/api/v1/agents/collaboration/task/create", json={
        "description": "test",
        "agents_needed": [],
        "collaboration_pattern": "sequential"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_collab_task_execute_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/collaboration/task/execute should require authentication."""
    response = await client.post("/api/v1/agents/collaboration/task/execute", json={"task_id": "test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_model_register_requires_auth(client: AsyncClient):
    """POST /api/v1/models should require authentication for registration."""
    response = await client.post("/api/v1/models", json={
        "model_id": "test/model",
        "provider_id": "test",
        "display_name": "Test Model",
        "lifecycle_status": "registered"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_model_retire_requires_admin(client: AsyncClient):
    """DELETE /api/v1/models/{id} should require admin or authentication."""
    response = await client.delete("/api/v1/models/test-model-id")
    # Could be 401 (not authenticated) or 403 (authenticated but not admin)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_model_update_requires_auth(client: AsyncClient):
    """PATCH /api/v1/models/{id} should require authentication."""
    response = await client.patch("/api/v1/models/test-model-id", json={"display_name": "Updated"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_act_requires_auth(client: AsyncClient):
    """POST /api/v1/agents/{id}/act should require authentication."""
    response = await client.post("/api/v1/agents/jarvis-core/act", json={
        "action": "run_code",
        "code": "print('hello')",
        "language": "python"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exec_list_requires_auth(client: AsyncClient):
    """GET /api/v1/agents/executions should require authentication."""
    response = await client.get("/api/v1/agents/executions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_scheduler_status_requires_auth(client: AsyncClient):
    """GET /api/v1/agents/scheduler/status should require authentication."""
    response = await client.get("/api/v1/agents/scheduler/status")
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Admin-only endpoints (should return 401 or 403 for non-admin users)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_system_processes_kill_requires_admin(client: AsyncClient):
    """POST /api/v1/system/processes/kill should require admin."""
    response = await client.post("/api/v1/system/processes/kill", json={"pid": 12345})
    # Should be 401 or 403
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_system_provider_settings_requires_admin(client: AsyncClient):
    """GET/PUT /api/v1/system/provider-settings should require admin."""
    response = await client.get("/api/v1/system/provider-settings")
    assert response.status_code in (401, 403)
    
    response = await client.put("/api/v1/system/provider-settings", json={})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_system_file_operations_require_auth(client: AsyncClient):
    """POST /api/v1/system/files/read should require authentication."""
    response = await client.post("/api/v1/system/files/read", json={"path": "/etc/passwd"})
    assert response.status_code in (401, 403, 404)


# --------------------------------------------------------------------------- #
# Error response format tests
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_404_error_format(client: AsyncClient):
    """404 responses should have structured error format."""
    response = await client.get("/nonexistent/path")
    assert response.status_code == 404
    data = response.json()
    # Check for structured error format
    assert "error" in data or "detail" in data


@pytest.mark.asyncio
async def test_401_error_format(client: AsyncClient):
    """401 responses should have structured error format."""
    response = await client.post("/api/v1/agents/task", json={"name": "t", "description": "t"})
    assert response.status_code == 401
    data = response.json()
    # The error format is: {"error": {"code": "AUTHENTICATION_ERROR", "message": ..., ...}}
    assert "error" in data or "detail" in data


@pytest.mark.asyncio
async def test_403_error_format(client: AsyncClient):
    """403 responses should have structured error format for admin endpoints."""
    # Test admin endpoint that requires auth - use the file-read endpoint
    response = await client.post("/api/v1/system/files/read", json={"path": "/etc/passwd"})
    # For unauthenticated requests, we expect 401 (auth required)
    assert response.status_code in (401, 403, 404)
    data = response.json()
    assert "error" in data or "detail" in data


# --------------------------------------------------------------------------- #
# Verify model registry integration
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_structured_service_manifest(client: AsyncClient):
    """GET / should return a properly structured service manifest."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    
    # Verify the manifest structure matches spec Part A
    assert "service" in data
    assert "component" in data
    assert "status" in data
    assert "version" in data
    assert "brain" in data
    assert "providers" in data
    assert "documentation" in data
    
    # Verify documentation endpoints
    docs = data["documentation"]
    assert "/docs" in docs.get("swagger", "") or docs.get("swagger") == "/docs"
    assert "/redoc" in docs.get("redoc", "") or docs.get("redoc") == "/redoc"
    assert "/openapi.json" in docs.get("openapi", "") or docs.get("openapi") == "/openapi.json"


@pytest.mark.asyncio
async def test_api_providers_returns_correct_structure(client: AsyncClient):
    """GET /api/providers should return provider registry with live status."""
    response = await client.get("/api/providers")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    # Each provider should have basic status info
    for provider in data["providers"]:
        assert "provider" in provider