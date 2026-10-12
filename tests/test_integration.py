"""Integration tests for maintained JARVIS backend routes."""

import pytest


@pytest.mark.asyncio
async def test_agent_collaboration_requires_auth_and_lists_agents(test_client, auth_headers):
    response = await test_client.get("/api/v1/agents/collaboration/agents/list")
    assert response.status_code == 401

    response = await test_client.get(
        "/api/v1/agents/collaboration/agents/list",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "agents" in response.json()


def test_health_endpoint_is_mounted(client):
    response = client.get("/api/v1/health/status")

    assert response.status_code == 200
