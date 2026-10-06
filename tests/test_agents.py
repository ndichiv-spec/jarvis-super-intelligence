"""
Tests for Agents and System
============================
"""

from datetime import datetime

import pytest
from unittest.mock import Mock, patch


class TestAgentSystem:
    """Test agent system modules."""

    def test_agent_system_import(self):
        """Test agent system can be imported."""
        from core.agent_system import AgentSystem

        agent = AgentSystem()
        assert agent is not None

    def test_agent_executor_import(self):
        """Test agent executor can be imported."""
        from core.agent_executor import AgentExecutor

        executor = AgentExecutor()
        assert executor is not None

    def test_autonomous_engine_import(self):
        """Test autonomous engine can be imported."""
        from core.autonomous_engine import AutonomousEngine

        engine = AutonomousEngine()
        assert engine is not None


class TestCollaboration:
    """Test collaboration modules."""

    def test_collaboration_import(self):
        """Test collaboration can be imported."""
        from core.collaboration import Collaboration

        collab = Collaboration()
        assert collab is not None

    def test_agent_collaboration_import(self):
        """Test agent collaboration can be imported."""
        from core.agent_collaboration import AgentCollaboration

        collab = AgentCollaboration()
        assert collab is not None


class TestAgentsAPI:
    """Test agents API endpoints."""

    @pytest.mark.asyncio
    async def test_list_agents(self, test_client, auth_headers):
        """Test listing agents."""
        response = await test_client.get("/api/v1/agents", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_agent(self, test_client, auth_headers):
        """Test creating an agent."""
        payload = {
            "name": "test_agent",
            "type": "chat",
            "config": {},
        }
        response = await test_client.post(
            "/api/v1/agents",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in [200, 201, 400]

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
        data = response.json()
        assert "running" in data
        assert "total_scheduled" in data

    @pytest.mark.asyncio
    async def test_service_tailoring_status(self, test_client, auth_headers):
        """Test service-tailoring sync status endpoint."""
        response = await test_client.get(
            "/api/v1/agents/service-tailoring",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "current_profile" in data

    @pytest.mark.asyncio
    async def test_create_and_delete_custom_scheduler_task(self, test_client, auth_headers):
        """Test custom autonomous task registration and cleanup."""
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
        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data["success"] is True
        assert create_data["task"]["name"] == task_name

        delete_response = await test_client.delete(
            f"/api/v1/agents/tasks/{task_name}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True


class TestSystemAPI:
    """Test system API endpoints."""

    @pytest.mark.asyncio
    async def test_system_status(self, test_client):
        """Test system status endpoint."""
        response = await test_client.get("/api/v1/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

    @pytest.mark.asyncio
    async def test_system_processes(self, test_client, auth_headers):
        """Test system processes endpoint."""
        response = await test_client.get(
            "/api/v1/system/processes?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_system_metrics(self, test_client):
        """Test system metrics endpoint."""
        response = await test_client.get("/api/v1/system/metrics")
        assert response.status_code == 200


class TestMonitoringAPI:
    """Test monitoring API endpoints."""

    @pytest.mark.asyncio
    async def test_monitoring_status(self, test_client):
        """Test monitoring status."""
        response = await test_client.get("/api/v1/monitoring/status")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_monitoring_metrics(self, test_client):
        """Test monitoring metrics."""
        response = await test_client.get("/api/v1/monitoring/metrics")
        assert response.status_code == 200


class TestAutomation:
    """Test automation modules."""

    def test_automation_engine_import(self):
        """Test automation engine can be imported."""
        from core.automation_engine import AutomationEngine

        engine = AutomationEngine()
        assert engine is not None

    def test_workflow_orchestration_import(self):
        """Test workflow orchestration can be imported."""
        from core.workflow_orchestration import WorkflowOrchestration

        wo = WorkflowOrchestration()
        assert wo is not None


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
