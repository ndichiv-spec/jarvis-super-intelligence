"""
Tests for Agents and System
============================
"""

from datetime import datetime

import pytest
from unittest.mock import Mock, patch


class TestCanonicalAgentExecutor:
    def test_agent_executor_import(self):
        from jarvis_backend.execution_fabric import AgentExecutor

        executor = AgentExecutor(tool_registry=object(), verifier=object())
        assert isinstance(executor, AgentExecutor)


class TestAgentsAPI:
    """Test agents API endpoints."""

    @pytest.mark.asyncio
    async def test_list_agents(self, test_client, auth_headers):
        """Test listing agents."""
        response = await test_client.get("/api/v1/agents", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_agent(self, test_client, auth_headers):
        """Test creating and cleaning up an owned graph agent."""
        payload = {
            "name": "test_agent",
            "role": "researcher",
            "config": {},
        }
        response = await test_client.post(
            "/api/v1/agents/graph/agent",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 200
        agent_id = response.json()["agent_id"]
        cleanup = await test_client.post(
            f"/api/v1/agents/graph/agent/{agent_id}/terminate",
            headers=auth_headers,
        )
        assert cleanup.status_code == 200

    @pytest.mark.asyncio
    async def test_agent_execution(self, test_client, auth_headers):
        """Test agent execution."""
        payload = {
            "agent_id": "test",
            "input": "test input",
        }
        response = await test_client.post(
            "/api/v1/agents/execute",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in [200, 400, 404]

    @pytest.mark.asyncio
    async def test_scheduler_status(self, test_client, auth_headers):
        """Test autonomous scheduler status endpoint."""
        response = await test_client.get(
            "/api/v1/agents/scheduler/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {
            "running": False,
            "status": "NOT_CONFIGURED",
            "next_run": None,
        }

    @pytest.mark.asyncio
    async def test_service_tailoring_status(self, test_client, auth_headers):
        """Test service-tailoring sync status endpoint."""
        response = await test_client.get(
            "/api/v1/agents/service-tailoring",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {
            "enabled": False,
            "status": "NOT_CONFIGURED",
            "services": [],
        }

    @pytest.mark.asyncio
    async def test_custom_scheduler_task_reports_not_configured(self, test_client, auth_headers):
        """The unavailable scheduler must not acknowledge task creation."""
        task_name = f"test_task_{datetime.utcnow().strftime('%H%M%S%f')}"
        payload = {
            "name": task_name,
            "description": "Summarize provider status changes",
            "schedule_type": "interval",
            "schedule_value": "600",
            "priority": "normal",
            "timeout": 120,
            "max_retries": 1,
        }
        create_response = await test_client.post(
            "/api/v1/agents/tasks",
            json=payload,
            headers=auth_headers,
        )
        assert create_response.status_code == 501
        assert create_response.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"


class TestSystemAPI:
    """Test system API endpoints."""

    @pytest.mark.asyncio
    async def test_system_status(self, test_client, admin_headers):
        """Detailed system status is available only to authenticated admins."""
        response = await test_client.get("/api/v1/system/status", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "online"

    @pytest.mark.asyncio
    async def test_system_processes(self, test_client, admin_headers):
        """Host process inventory is reserved for the canonical owner."""
        response = await test_client.get(
            "/api/v1/system/processes?limit=10",
            headers=admin_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_system_metrics(self, test_client):
        """Test system metrics endpoint."""
        response = await test_client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "system" in response.json()


class TestMonitoringAPI:
    """Test monitoring API endpoints."""

    @pytest.mark.asyncio
    async def test_monitoring_status(self, test_client):
        """Test monitoring status."""
        response = await test_client.get("/api/v1/monitoring/health-report")
        assert response.status_code == 200
        assert response.json()["status"] in {"healthy", "degraded", "unavailable"}

    @pytest.mark.asyncio
    async def test_monitoring_metrics(self, test_client):
        """Test monitoring metrics."""
        response = await test_client.get("/api/v1/monitoring/metrics")
        assert response.status_code == 200
        assert "timestamp" in response.json()


class TestAutomationAPI:
    """Test automation API endpoints."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, test_client, auth_headers):
        """Test listing automation tasks."""
        response = await test_client.get("/api/v1/automation", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_run_task(self, test_client, auth_headers):
        """Test running an automation task."""
        payload = {
            "task_name": "test_task",
            "params": {},
        }
        response = await test_client.post(
            "/api/v1/automation/run",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in [200, 400, 404]
