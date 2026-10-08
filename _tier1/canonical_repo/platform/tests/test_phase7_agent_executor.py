"""Phase 7 Tests: AgentExecutor.

Tests the canonical agent executor: capability discovery, graph construction,
authorization, execution, retry, idempotency, WAITING_FOR_USER approval,
checkpoint/resume, and verification integration.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest

# Use the same test DB setup as the rest of the suite.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend.core import get_store  # noqa: E402
from jarvis_backend.execution_fabric import (  # noqa: E402
    AgentExecutor,
    ExecutionGraph,
    ExecutionNode,
    ExecutionNodeStatus,
    FailureClass,
    Task,
    TaskStatus,
    build_verified_evidence_pack,
    get_backoff_delay,
    should_retry,
)
from research_engine.capability_tools import build_capability_registry  # noqa: E402
from research_engine.tool_registry import ToolContext  # noqa: E402


@pytest.fixture()
def executor() -> AgentExecutor:
    return AgentExecutor(tool_registry=build_capability_registry())


@pytest.fixture()
def clean_store():
    """Reset the tasks/executions stores before each test."""
    tasks = get_store("tasks")
    tasks.reset()
    executions = get_store("executions")
    executions.reset()
    yield
    tasks.reset()
    executions.reset()


# --------------------------------------------------------------------------- #
# Capability discovery
# --------------------------------------------------------------------------- #

class TestCapabilityDiscovery:

    def test_discover_finds_provider_status(self, executor: AgentExecutor) -> None:
        caps = executor.discover("Check provider status",
                                 include_unavailable=True)
        assert "provider.status" in caps

    def test_discover_finds_job_status(self, executor: AgentExecutor) -> None:
        caps = executor.discover("What JARVIS jobs are currently running?")
        assert "job.status" in caps

    def test_discover_returns_list(self, executor: AgentExecutor) -> None:
        caps = executor.discover("Check the project structure")
        assert isinstance(caps, list)

    def test_discover_never_invents(self, executor: AgentExecutor) -> None:
        """A capability that does not exist must never be returned."""
        caps = executor.discover("Do something completely imaginary")
        assert "fake.capability" not in caps


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #

class TestGraphConstruction:

    def test_build_execution_graph_creates_nodes(self, executor: AgentExecutor) -> None:
        task, graph = executor.build_execution_graph(
            "Check provider health",
            capabilities=["provider.status", "model.status"],
            user_id="test_user",
        )
        assert task.task_id is not None
        assert task.status == TaskStatus.PLANNED
        assert len(graph.nodes) == 2
        node_ids = list(graph.nodes.keys())
        assert "node_0" in node_ids
        assert "node_1" in node_ids

    def test_node_inherits_contract_metadata(self, executor: AgentExecutor) -> None:
        task, graph = executor.build_execution_graph(
            "Check provider health",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        node = graph.nodes["node_0"]
        assert node.capability == "provider.status"
        assert node.risk_level == "read"
        # Idempotency key must be set.
        assert node.idempotency_key is not None
        assert task.task_id in node.idempotency_key

    def test_network_risk_node_gets_waiting_for_user(self, executor: AgentExecutor) -> None:
        """A NETWORK risk capability without confirmation should be WAITING_FOR_USER."""
        task, graph = executor.build_execution_graph(
            "Inspect github repo",
            capabilities=["github.inspect"],
            user_id="test_user",
            execution_mode="online",
        )
        node = graph.nodes["node_0"]
        # github.inspect requires confirmation per DefaultPermissionPolicy.
        assert node.risk_level in ("network", "admin")
        assert node.status == ExecutionNodeStatus.WAITING_FOR_USER

    def test_read_risk_node_not_waiting(self, executor: AgentExecutor) -> None:
        task, graph = executor.build_execution_graph(
            "Check provider status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        node = graph.nodes["node_0"]
        assert node.risk_level == "read"
        assert node.status == ExecutionNodeStatus.PENDING

    def test_build_with_dependencies(self, executor: AgentExecutor) -> None:
        task, graph = executor.build_execution_graph(
            "inspect then check providers",
            capabilities=["project.inspect", "provider.status"],
            user_id="test_user",
        )
        # Manually add a dependency: provider.status depends on project.inspect
        graph.add_edge("node_0", "node_1")
        assert "node_0" in graph.nodes["node_1"].dependencies
        assert graph.nodes["node_1"].is_ready(set()) is False
        assert graph.nodes["node_1"].is_ready({"node_0"}) is True


# --------------------------------------------------------------------------- #
# Authorization boundary
# --------------------------------------------------------------------------- #

class TestAuthorization:

    def test_read_capability_authorized(self, executor: AgentExecutor) -> None:
        ok, reason = executor.tool_registry.authorize("test_user", "provider.status")
        assert ok is True

    def test_network_capability_denied(self, executor: AgentExecutor) -> None:
        ok, reason = executor.tool_registry.authorize("test_user", "github.inspect")
        assert ok is False
        assert reason == "requires_user_confirmation"

    def test_unknown_capability_denied(self, executor: AgentExecutor) -> None:
        ok, reason = executor.tool_registry.authorize("test_user", "fake.cap")
        assert ok is False


# --------------------------------------------------------------------------- #
# Execution / checkpointing
# --------------------------------------------------------------------------- #

class TestTaskExecution:

    @pytest.mark.asyncio
    async def test_execute_read_only_capability(self, executor: AgentExecutor,
                                                clean_store: None) -> None:
        task, graph = executor.build_execution_graph(
            "Check provider health",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        result = await executor.execute_task(task)
        assert result["success"] is True
        assert result["task_status"] == TaskStatus.COMPLETED.value
        node = graph.nodes["node_0"]
        assert node.status == ExecutionNodeStatus.COMPLETED
        assert node.outputs is not None

    @pytest.mark.asyncio
    async def test_execute_multiple_capabilities(self, executor: AgentExecutor,
                                                 clean_store: None) -> None:
        task, graph = executor.build_execution_graph(
            "Inspect project and check providers",
            capabilities=["project.inspect", "provider.status"],
            user_id="test_user",
        )
        result = await executor.execute_task(task)
        assert result["success"] is True
        assert result["progress"]["completed"] == 2

    @pytest.mark.asyncio
    async def test_task_checkpointed_to_store(self, executor: AgentExecutor,
                                              clean_store: None) -> None:
        task, graph = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        stored = get_store("tasks").load()
        assert task.task_id in stored
        data = stored[task.task_id]
        assert data["status"] == "COMPLETED"
        assert data["plan"] is not None
        assert data["plan"]["nodes"]["node_0"]["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_task_reload_from_store(self, executor: AgentExecutor,
                                          clean_store: None) -> None:
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        # Load via the static loader (simulates process restart).
        loaded = Task.load(task.task_id)
        assert loaded is not None
        assert loaded.status == TaskStatus.COMPLETED
        assert loaded.plan is not None
        assert loaded.plan.nodes["node_0"].status == ExecutionNodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_from_dict_roundtrip(self, executor: AgentExecutor,
                                            clean_store: None) -> None:
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["model.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        raw = get_store("tasks").load()[task.task_id]
        restored = Task.from_dict(raw)
        assert restored.task_id == task.task_id
        assert restored.intent == task.intent
        assert restored.status == TaskStatus.COMPLETED
        assert restored.plan is not None


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_resume_completed_returns_existing(self, executor: AgentExecutor,
                                                    clean_store: None) -> None:
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)
        resume_result = await executor.resume(task.task_id)
        assert resume_result["success"] is True
        assert resume_result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_idempotency_key_unique_per_node(self, executor: AgentExecutor) -> None:
        task, graph = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status", "model.status"],
            user_id="test_user",
        )
        keys = {n.idempotency_key for n in graph.nodes.values()}
        assert len(keys) == 2  # no collisions


# --------------------------------------------------------------------------- #
# Retry + recovery
# --------------------------------------------------------------------------- #

class TestRetryRecovery:

    @pytest.mark.asyncio
    async def test_failed_node_records_failure_class(
        self, executor: AgentExecutor, clean_store: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A capability that always fails gets a FAILURE classification."""
        from research_engine.tool_registry import Tool, ToolResult

        class AlwaysFailsTool(Tool):
            name = "test.always_fails"
            description = "Always fails for testing."
            schema = {"type": "object", "properties": {}, "required": []}
            risk = __import__("research_engine.models", fromlist=["RiskLevel"]).RiskLevel.READ

            async def invoke(self, args, ctx):
                return ToolResult(
                    tool_id=ctx.request_id, name=self.name,
                    success=False,
                    error="PROVIDER_UNAVAILABLE: no provider configured",
                )

        executor.tool_registry.register(AlwaysFailsTool())

        task, graph = executor.build_execution_graph(
            "test failure",
            capabilities=["test.always_fails"],
            user_id="test_user",
        )
        # max_attempts=1 for read risk, so no retry
        result = await executor.execute_task(task)
        node = graph.nodes["node_0"]
        assert node.status == ExecutionNodeStatus.FAILED
        assert node.failure_class == FailureClass.PROVIDER_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_transient_failure_retries_then_succeeds(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        """A capability that fails once then succeeds should be retried."""
        from research_engine.tool_registry import Tool, ToolResult
        from research_engine.models import RiskLevel

        call_count = {"n": 0}

        class FlakyTool(Tool):
            name = "test.flaky"
            description = "Fails first call, succeeds second."
            schema = {"type": "object", "properties": {}, "required": []}
            risk = RiskLevel.READ

            async def invoke(self, args, ctx):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return ToolResult(
                        tool_id=ctx.request_id, name=self.name,
                        success=False, error="TRANSIENT: network timeout")
                return ToolResult(
                    tool_id=ctx.request_id, name=self.name,
                    success=True, result="ok")

        executor.tool_registry.register(FlakyTool())

        task, graph = executor.build_execution_graph(
            "flaky task",
            capabilities=["test.flaky"],
            user_id="test_user",
        )
        # Give it retry budget.
        graph.nodes["node_0"].max_attempts = 3
        graph.nodes["node_0"].retry_policy = "backoff_1"

        result = await executor.execute_task(task)
        assert result["success"] is True
        node = graph.nodes["node_0"]
        assert node.status == ExecutionNodeStatus.COMPLETED
        assert node.attempt >= 2
        assert len(node.retry_history) >= 1

    @pytest.mark.asyncio
    async def test_non_retryable_failure_no_retry(
        self, executor: AgentExecutor, clean_store: None, monkeypatch
    ) -> None:
        """An authorization failure should NOT be retried."""
        from research_engine.tool_registry import Tool, ToolResult
        from research_engine.models import RiskLevel

        call_count = {"n": 0}

        class AuthFailTool(Tool):
            name = "test.auth_fail"
            description = "Always auth fails."
            schema = {"type": "object", "properties": {}, "required": []}
            risk = RiskLevel.NETWORK
            requires_confirmation = True

            async def invoke(self, args, ctx):
                call_count["n"] += 1
                return ToolResult(
                    tool_id=ctx.request_id, name=self.name,
                    success=False, error="TOOL_DENIED: requires_user_confirmation")

        executor.tool_registry.register(AuthFailTool())

        task, graph = executor.build_execution_graph(
            "auth fail task",
            capabilities=["test.auth_fail"],
            user_id="test_user",
            confirmations={},  # no confirmation
            execution_mode="online",
        )
        result = await executor.execute_task(task)
        node = graph.nodes["node_0"]
        assert node.failure_class == FailureClass.AUTHORIZATION_FAILURE
        assert call_count["n"] == 1  # only one attempt, no retry


# --------------------------------------------------------------------------- #
# WAITING_FOR_USER approval
# --------------------------------------------------------------------------- #

class TestHumanApproval:

    @pytest.mark.asyncio
    async def test_waiting_for_user_blocks_execution(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, graph = executor.build_execution_graph(
            "inspect github repo",
            capabilities=["github.inspect"],
            user_id="test_user",
            confirmations={},
            execution_mode="online",
        )
        result = await executor.execute_task(task)
        assert result["success"] is False
        assert result["status"] == "WAITING_FOR_USER"
        assert result.get("waiting_for_user") is True
        assert "node_0" in result.get("pending_nodes", [])

    @pytest.mark.asyncio
    async def test_approve_node_transitions_to_pending(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, graph = executor.build_execution_graph(
            "inspect github repo",
            capabilities=["github.inspect"],
            user_id="test_user",
            confirmations={},
            execution_mode="online",
        )
        await executor.execute_task(task)  # → WAITING_FOR_USER

        # Approve it.
        approve_result = executor.approve_node(task.task_id, "node_0", approved=True)
        assert approve_result["approved"] is True

        # Re-execute.
        result = await executor.resume(task.task_id)
        # It may fail (no token) but should not be WAITING_FOR_USER anymore.
        assert result["status"] != "WAITING_FOR_USER"

    @pytest.mark.asyncio
    async def test_reject_node_marks_failed(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, graph = executor.build_execution_graph(
            "inspect github repo",
            capabilities=["github.inspect"],
            user_id="test_user",
            confirmations={},
            execution_mode="online",
        )
        await executor.execute_task(task)

        reject_result = executor.approve_node(task.task_id, "node_0", approved=False)
        assert reject_result["approved"] is False

        loaded = Task.load(task.task_id)
        assert loaded.plan.nodes["node_0"].status == ExecutionNodeStatus.FAILED


# --------------------------------------------------------------------------- #
# Evidence pack builder
# --------------------------------------------------------------------------- #

class TestEvidencePack:

    @pytest.mark.asyncio
    async def test_build_verified_evidence_pack(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, _ = executor.build_execution_graph(
            "Check provider status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        pack = build_verified_evidence_pack(task)
        assert pack["task_id"] == task.task_id
        assert len(pack["executed_nodes"]) >= 1
        assert len(pack["verification_evidence"]) >= 1
        assert "verification_status" in pack


# --------------------------------------------------------------------------- #
# Execution log
# --------------------------------------------------------------------------- #

class TestExecutionLog:

    @pytest.mark.asyncio
    async def test_executions_recorded(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        executions = get_store("executions").load()
        types = {e["event_type"] for e in executions}
        assert "TASK_STARTED" in types
        assert "TASK_COMPLETED" in types


# --------------------------------------------------------------------------- #
# Status retrieval
# --------------------------------------------------------------------------- #

class TestTaskStatus:

    @pytest.mark.asyncio
    async def test_get_task_status(
        self, executor: AgentExecutor, clean_store: None
    ) -> None:
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        status = executor.get_task_status(task.task_id)
        assert status is not None
        assert status["status"] == "COMPLETED"
        assert "graph_progress" in status
        assert status["graph_progress"]["total_nodes"] == 1

    def test_get_status_missing_task(self, executor: AgentExecutor) -> None:
        assert executor.get_task_status("nonexistent") is None
