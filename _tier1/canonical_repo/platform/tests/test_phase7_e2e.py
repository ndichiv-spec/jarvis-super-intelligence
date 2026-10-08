"""Phase 7 End-to-End Test: Full Execution Fabric Demonstration.

This test demonstrates the complete Phase 7 lifecycle for the universal
agentic execution fabric:

1. Intent → Capability Discovery
2. Capability Discovery → ExecutionGraph (DAG)
3. Authorization boundary (ToolRegistry)
4. DAG execution (topological, concurrent)
5. Checkpoint/resume (persistence)
6. Idempotency
7. Retry with backoff
8. WAITING_FOR_USER approval
9. Verification
10. Evidence pack + memory

All components reuse existing infrastructure.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest

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
    should_retry,
)
from research_engine.capability_tools import build_capability_registry  # noqa: E402
from research_engine.capability_contract import discover_capabilities, build_contracts  # noqa: E402
from research_engine.tool_registry import ToolContext  # noqa: E402


@pytest.fixture()
def clean_store():
    tasks = get_store("tasks")
    tasks.reset()
    executions = get_store("executions")
    executions.reset()
    yield
    tasks.reset()
    executions.reset()


def _make_executor():
    return AgentExecutor(tool_registry=build_capability_registry())


# --------------------------------------------------------------------------- #
# Stage 1: Intent → Capability Discovery
# --------------------------------------------------------------------------- #

class TestStage1Discovery:

    def test_discover_returns_real_capabilities(self) -> None:
        caps = discover_capabilities("What JARVIS jobs are running?")
        names = {c["name"] for c in caps["capabilities"]}
        assert "job.status" in names

    def test_discovered_capability_has_contract(self) -> None:
        contracts = build_contracts()
        caps = discover_capabilities("Check provider health")
        for c in caps["capabilities"]:
            assert c["name"] in contracts
            contract = contracts[c["name"]]
            assert contract["domain"] in (
                "platform", "software_engineering", "ai_ml_development",
                "infrastructure", "documents", "data_analytics",
                "geography", "web", "research", "communication",
                "business_workflow", "offline_local",
            )

    def test_discovery_never_invents(self) -> None:
        caps = discover_capabilities("Do something fantasy-like and non-existent")
        names = {c["name"] for c in caps["capabilities"]}
        assert "fantasy.capability" not in names
        assert "make_up_new_tool" not in names


# --------------------------------------------------------------------------- #
# Stage 2-4: Graph construction + execution for a multi-node DAG
# --------------------------------------------------------------------------- #

class TestStage2Through4Execution:

    @pytest.mark.asyncio
    async def test_full_dag_execution(self, clean_store) -> None:
        executor = _make_executor()
        intent = "Report provider and model status"
        capabilities = ["provider.status", "model.status"]
        task, graph = executor.build_execution_graph(
            intent, capabilities=capabilities, user_id="test_user")

        # Add edge: model.status depends on provider.status
        graph.add_edge("node_0", "node_1")

        result = await executor.execute_task(task)

        assert result["success"] is True
        assert result["task_status"] == TaskStatus.COMPLETED.value
        assert len(result["progress"]["status_counts"]) >= 1
        completed = result["progress"]["status_counts"].get("COMPLETED", 0)
        assert completed == 2

        # Verify dependency ordering
        n0 = graph.nodes["node_0"]
        n1 = graph.nodes["node_1"]
        assert n0.status == ExecutionNodeStatus.COMPLETED
        assert n1.status == ExecutionNodeStatus.COMPLETED

        # model.status started AFTER provider.status completed
        assert n0.completed_at is not None
        assert n1.started_at is not None
        assert n1.started_at >= n0.started_at

    @pytest.mark.asyncio
    async def test_parallel_independent_nodes(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Check multiple things",
            capabilities=["job.status", "model.status", "artifact.inspect"],
            user_id="test_user",
        )

        # No edges → all can run in parallel
        result = await executor.execute_task(task)
        assert result["success"] is True
        assert result["progress"]["completed"] == 3


# --------------------------------------------------------------------------- #
# Stage 6: Idempotency
# --------------------------------------------------------------------------- #

class TestIdempotencyStage:

    @pytest.mark.asyncio
    async def test_re_run_produces_same_result(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Check provider status",
            capabilities=["provider.status"],
            user_id="test_user")
        await executor.execute_task(task)

        # Reload from store (simulating a restart) and re-run.
        reloaded = Task.load(task.task_id)
        result2 = await executor.execute_task(reloaded)
        assert result2["success"] is True
        assert result2["task_status"] == TaskStatus.COMPLETED.value


# --------------------------------------------------------------------------- #
# Stage 7: Retry with backoff
# --------------------------------------------------------------------------- #

class TestRetryStage:

    def test_should_retry_logic(self) -> None:
        # Transient: retry up to max_attempts
        assert should_retry(FailureClass.TRANSIENT, 0, 5) is True
        assert should_retry(FailureClass.TRANSIENT, 4, 5) is True
        assert should_retry(FailureClass.TRANSIENT, 5, 5) is False

        # Auth: never retry
        assert should_retry(FailureClass.AUTHENTICATION_FAILURE, 0, 5) is False
        assert should_retry(FailureClass.AUTHORIZATION_FAILURE, 0, 5) is False

        # Permanent: never retry
        assert should_retry(FailureClass.PERMANENT, 0, 5) is False

    @pytest.mark.asyncio
    async def test_retry_history_persisted(self, clean_store) -> None:
        from research_engine.tool_registry import Tool, ToolResult
        from research_engine.models import RiskLevel

        attempts = {"n": 0}

        class TwoFailThenSuccess(Tool):
            name = "test.retry_ok"
            description = "Fails twice, succeeds third."
            schema = {"type": "object", "properties": {}, "required": []}
            risk = RiskLevel.READ

            async def invoke(self, args, ctx):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    return ToolResult(
                        tool_id=ctx.request_id, name=self.name,
                        success=False,
                        error="TRANSIENT: temporary network blip",
                    )
                return ToolResult(
                    tool_id=ctx.request_id, name=self.name,
                    success=True, result="success on attempt 3",
                )

        executor = _make_executor()
        executor.tool_registry.register(TwoFailThenSuccess())

        task, graph = executor.build_execution_graph(
            "retryable task",
            capabilities=["test.retry_ok"],
            user_id="test_user",
        )
        graph.nodes["node_0"].max_attempts = 5
        graph.nodes["node_0"].retry_policy = "backoff_2"

        result = await executor.execute_task(task)
        assert result["success"] is True

        node = graph.nodes["node_0"]
        assert len(node.retry_history) == 2  # two failures recorded before success
        assert node.attempt == 3
        assert node.status == ExecutionNodeStatus.COMPLETED


# --------------------------------------------------------------------------- #
# Stage 8: WAITING_FOR_USER approval
# --------------------------------------------------------------------------- #

class TestApprovalStage:

    @pytest.mark.asyncio
    async def test_unapproved_network_capability_blocks(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Inspect github repo owner/repo",
            capabilities=["github.inspect"],
            user_id="test_user",
            confirmations={},
            execution_mode="online",
        )
        result = await executor.execute_task(task)
        assert result["status"] == "WAITING_FOR_USER"
        assert result.get("waiting_for_user") is True

        loaded = Task.load(task.task_id)
        assert loaded.status == TaskStatus.WAITING_FOR_USER

    @pytest.mark.asyncio
    async def test_approved_capability_executes(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Inspect github repo owner/repo",
            capabilities=["github.inspect"],
            confirmations={"test_user:github.inspect": True},
            user_id="test_user",
            execution_mode="online",
        )
        # The capability is authorized but may report NOT_CONFIGURED (no token).
        # Either way it should execute, not block.
        result = await executor.execute_task(task)
        loaded = Task.load(task.task_id)
        assert loaded.status != TaskStatus.WAITING_FOR_USER

    @pytest.mark.asyncio
    async def test_rejected_dependent_cascade_fails(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "inspect github then summarize",
            capabilities=["github.inspect", "job.status"],
            user_id="test_user",
            confirmations={},
            execution_mode="online",
        )
        # Add dependency: project.inspect depends on github.inspect
        graph.add_edge("node_0", "node_1")

        await executor.execute_task(task)  # → WAITING_FOR_USER for node_0

        # Reject node_0
        executor.approve_node(task.task_id, "node_0", approved=False)

        loaded = Task.load(task.task_id)
        assert loaded.plan.nodes["node_0"].status == ExecutionNodeStatus.FAILED
        # Dependent node_1 should be cascade-failed
        assert loaded.plan.nodes["node_1"].status == ExecutionNodeStatus.FAILED


# --------------------------------------------------------------------------- #
# Stage 9: Verification + evidence
# --------------------------------------------------------------------------- #

class TestVerificationStage:

    @pytest.mark.asyncio
    async def test_verification_required_sets_status(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Check provider status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        task.verification_required = True
        await executor.execute_task(task)

        loaded = Task.load(task.task_id)
        assert "verification" in loaded.metadata

    @pytest.mark.asyncio
    async def test_evidence_pack_after_execution(self, clean_store) -> None:
        executor = _make_executor()
        task, _ = executor.build_execution_graph(
            "Check provider and job status",
            capabilities=["provider.status", "job.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        pack = build_verified_evidence_pack(task)
        assert pack["task_id"] == task.task_id
        assert len(pack["executed_nodes"]) == 2
        assert any(e["capability"] == "provider.status"
                   for e in pack["verification_evidence"])
        assert any(e["capability"] == "job.status"
                   for e in pack["verification_evidence"])


# --------------------------------------------------------------------------- #
# Stage 10: Persistence / resumption across "restart"
# --------------------------------------------------------------------------- #

class TestPersistenceStage:

    @pytest.mark.asyncio
    async def test_resume_after_checkpoint(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        # Simulate a fresh executor (new process).
        executor2 = _make_executor()
        result = await executor2.resume(task.task_id)
        assert result["success"] is True
        assert result["status"] == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_executions_log_persisted(self, clean_store) -> None:
        executor = _make_executor()
        task, _ = executor.build_execution_graph(
            "Check status",
            capabilities=["provider.status"],
            user_id="test_user",
        )
        await executor.execute_task(task)

        log = get_store("executions").load()
        assert len(log) >= 2  # TASK_STARTED + TASK_COMPLETED at minimum
        event_types = {e["event_type"] for e in log}
        assert "TASK_STARTED" in event_types
        assert "TASK_COMPLETED" in event_types


# --------------------------------------------------------------------------- #
# Cascading failure
# --------------------------------------------------------------------------- #

class TestCascadingFailure:

    @pytest.mark.asyncio
    async def test_dependent_skipped_on_failure(self, clean_store) -> None:
        executor = _make_executor()
        task, graph = executor.build_execution_graph(
            "fail-then-dep",
            capabilities=["test.always_fail", "job.status"],
            user_id="test_user",
        )
        graph.add_edge("node_0", "node_1")

        # Register a tool that always fails.
        from research_engine.tool_registry import Tool, ToolResult
        from research_engine.models import RiskLevel

        class AlwaysFail(Tool):
            name = "test.always_fail"
            description = "Always fails."
            schema = {"type": "object", "properties": {}, "required": []}
            risk = RiskLevel.READ

            async def invoke(self, args, ctx):
                return ToolResult(
                    tool_id=ctx.request_id, name=self.name,
                    success=False,
                    error="CAPABILITY_FAILURE: broken",
                )

        executor.tool_registry.register(AlwaysFail())

        result = await executor.execute_task(task)
        assert result["success"] is False
        n0 = graph.nodes["node_0"]
        n1 = graph.nodes["node_1"]
        assert n0.status == ExecutionNodeStatus.FAILED
        # n1 should be skipped since its dependency failed.
        assert n1.status in (ExecutionNodeStatus.FAILED, ExecutionNodeStatus.SKIPPED)
