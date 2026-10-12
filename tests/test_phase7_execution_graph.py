"""Phase 7 Tests: ExecutionGraph DAG structure and checkpointing.

Tests the ExecutionGraph data model that powers the universal agentic execution
fabric: node lifecycle, dependency edges, topological readiness, cascading
failure, idempotency keys, and checkpoint/resume round-tripping.
"""
from __future__ import annotations

import pytest

from jarvis_backend.execution_fabric import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionNodeStatus,
    FailureClass,
    GraphEdge,
    get_backoff_delay,
    should_retry,
)


# --------------------------------------------------------------------------- #
# Failure classification + backoff
# --------------------------------------------------------------------------- #

class TestFailureClassification:

    def test_retryable_classes(self) -> None:
        for fc in (FailureClass.TRANSIENT, FailureClass.RATE_LIMITED,
                   FailureClass.NETWORK_FAILURE, FailureClass.PROVIDER_UNAVAILABLE,
                   FailureClass.RESOURCE_UNAVAILABLE):
            assert should_retry(fc, attempt=1, max_attempts=5) is True

    def test_non_retryable_classes(self) -> None:
        for fc in (FailureClass.AUTHENTICATION_FAILURE,
                   FailureClass.AUTHORIZATION_FAILURE,
                   FailureClass.INVALID_INPUT, FailureClass.CAPABILITY_FAILURE,
                   FailureClass.VERIFICATION_FAILURE, FailureClass.PERMANENT):
            assert should_retry(fc, attempt=1, max_attempts=5) is False

    def test_max_attempts_exhausted(self) -> None:
        assert should_retry(FailureClass.TRANSIENT, attempt=5, max_attempts=5) is False
        assert should_retry(FailureClass.TRANSIENT, attempt=4, max_attempts=5) is True

    def test_backoff_is_positive_and_bounded(self) -> None:
        for attempt in range(1, 6):
            delay = get_backoff_delay(attempt, base=1.0, max_delay=60.0)
            assert 0 < delay <= 60.0

    def test_backoff_grows_with_attempt(self) -> None:
        d1 = get_backoff_delay(1, base=1.0, max_delay=60.0)
        d3 = get_backoff_delay(3, base=1.0, max_delay=60.0)
        assert d3 >= d1  # jitter, so use >= not >


# --------------------------------------------------------------------------- #
# ExecutionNode
# --------------------------------------------------------------------------- #

class TestExecutionNode:

    def test_node_defaults(self) -> None:
        node = ExecutionNode(
            node_id="n1", task_id="t1", capability="test.cap")
        assert node.status == ExecutionNodeStatus.PENDING
        assert node.attempt == 0
        assert node.outputs is None
        assert node.dependencies == []
        assert node.dependents == []
        assert node.failure_class is None

    def test_node_is_ready_no_deps(self) -> None:
        node = ExecutionNode(node_id="n1", task_id="t1", capability="test")
        assert node.is_ready(set()) is True
        assert node.is_ready({"x"}) is True

    def test_node_is_ready_with_deps(self) -> None:
        node = ExecutionNode(node_id="n2", task_id="t1", capability="test",
                             dependencies=["n1"])
        assert node.is_ready(set()) is False
        assert node.is_ready({"n1"}) is True

    def test_node_serialization_roundtrip(self) -> None:
        node = ExecutionNode(
            node_id="n1", task_id="t1", capability="provider.status",
            inputs={"query": "health"}, dependencies=["n0"],
            status=ExecutionNodeStatus.COMPLETED, attempt=2,
            max_attempts=3, retry_policy="backoff_1",
            started_at=1000.0, completed_at=1005.0,
            failure_class=FailureClass.TRANSIENT,
            idempotency_key="t1:provider.status:abc",
            risk_level="read",
            retry_history=[{"attempt": 1, "error": "timeout"}],
        )
        d = node.to_dict()
        assert d["node_id"] == "n1"
        assert d["status"] == "COMPLETED"
        assert d["failure_class"] == "TRANSIENT"

        restored = ExecutionNode.from_dict(d)
        assert restored.node_id == "n1"
        assert restored.status == ExecutionNodeStatus.COMPLETED
        assert restored.failure_class == FailureClass.TRANSIENT
        assert restored.retry_history == [{"attempt": 1, "error": "timeout"}]
        assert restored.idempotency_key == "t1:provider.status:abc"

    def test_node_with_invalid_status_deserializes_to_pending(self) -> None:
        node = ExecutionNode(node_id="n1", task_id="t1", capability="test")
        d = node.to_dict()
        d["status"] = "BOGUS_STATUS"
        restored = ExecutionNode.from_dict(d)
        assert restored.status == ExecutionNodeStatus.PENDING


# --------------------------------------------------------------------------- #
# ExecutionGraph — structure
# --------------------------------------------------------------------------- #

class TestExecutionGraphStructure:

    def test_empty_graph(self) -> None:
        g = ExecutionGraph("t1")
        assert g.nodes == {}
        assert g.root_nodes == []
        assert g.leaf_nodes == []
        assert g.get_ready_nodes() == []

    def test_add_node_sets_roots_leaves(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        g.add_node(n0)
        g.add_node(n1)
        assert set(g.root_nodes) == {"n0"}
        assert set(g.leaf_nodes) == {"n1"}
        assert n0.dependents == ["n1"]
        assert n1.dependencies == ["n0"]

    def test_add_edge_creates_dependency(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b")
        g.add_node(n0)
        g.add_node(n1)
        g.add_edge("n0", "n1")
        assert "n0" in n1.dependencies
        assert "n1" in n0.dependents
        assert len(g.edges) == 1
        assert isinstance(g.edges[0], GraphEdge)


# --------------------------------------------------------------------------- #
# ExecutionGraph — readiness / scheduling
# --------------------------------------------------------------------------- #

class TestExecutionGraphScheduling:

    def test_ready_nodes_respect_dependencies(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        g.add_node(n0)
        g.add_node(n1)

        ready = g.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].node_id == "n0"

        g.mark_completed("n0")
        ready = g.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].node_id == "n1"
        # n1 is now ready but not yet completed.
        assert n1.status == ExecutionNodeStatus.PENDING

    def test_running_nodes_excluded_from_ready(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        g.add_node(n0)
        n0.status = ExecutionNodeStatus.RUNNING
        assert g.get_ready_nodes() == []
        assert len(g.get_running_nodes()) == 1

    def test_terminal_nodes_excluded_from_ready(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b")
        g.add_node(n0)
        g.add_node(n1)
        g.mark_completed("n0")
        g.mark_failed("n1", "boom", FailureClass.CAPABILITY_FAILURE)
        ready = g.get_ready_nodes()
        assert ready == []

    def test_waiting_for_user_excluded_from_ready(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "dangerous.net")
        n0.status = ExecutionNodeStatus.WAITING_FOR_USER
        g.add_node(n0)
        assert g.get_ready_nodes() == []

    def test_retrying_excluded_from_ready(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n0.status = ExecutionNodeStatus.RETRYING
        g.add_node(n0)
        assert g.get_ready_nodes() == []

    def test_has_active_work_false_when_empty(self) -> None:
        g = ExecutionGraph("t1")
        assert g.has_active_work() is False

    def test_has_active_work_true_with_running(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n0.status = ExecutionNodeStatus.RUNNING
        g.add_node(n0)
        assert g.has_active_work() is True

    def test_has_active_work_true_with_ready(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        g.add_node(n0)
        assert g.has_active_work() is True


# --------------------------------------------------------------------------- #
# ExecutionGraph — progress tracking / cascading
# --------------------------------------------------------------------------- #

class TestExecutionGraphProgress:

    def test_progress_counts_completed(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b")
        g.add_node(n0)
        g.add_node(n1)
        g.mark_completed("n0")

        p = g.progress()
        assert p["total_nodes"] == 2
        assert p["completed"] == 1
        assert p["failed"] == 0
        assert p["progress"] == 0.5

    def test_cascading_skip_marks_dependents_failed(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        n2 = ExecutionNode("n2", "t1", "cap.c", dependencies=["n1"])
        n3 = ExecutionNode("n3", "t1", "cap.d")
        for n in (n0, n1, n2, n3):
            g.add_node(n)

        skipped = g.skip_dependent_of("n0")
        assert "n0" in skipped
        assert "n1" in skipped
        assert "n2" in skipped
        assert "n3" not in skipped  # no dependency on n0 chain
        assert g.nodes["n1"].status == ExecutionNodeStatus.FAILED
        assert g.nodes["n2"].status == ExecutionNodeStatus.FAILED
        assert g.nodes["n3"].status == ExecutionNodeStatus.PENDING

    def test_skip_dependent_idempotent(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        g.add_node(n0)
        g.add_node(n1)
        first = g.skip_dependent_of("n0")
        assert first == {"n0", "n1"}
        # Second call should be a no-op — nodes already terminal.
        second = g.skip_dependent_of("n0")
        assert second == set()
        assert g.nodes["n1"].status == ExecutionNodeStatus.FAILED

    def test_failed_root_still_cascades_to_pending_descendants(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        n2 = ExecutionNode("n2", "t1", "cap.c", dependencies=["n1"])
        for node in (n0, n1, n2):
            g.add_node(node)
        g.mark_failed("n0", "capability failed", FailureClass.CAPABILITY_FAILURE)

        skipped = g.skip_dependent_of("n0")

        assert skipped == {"n0", "n1", "n2"}
        assert g.nodes["n0"].error == "capability failed"
        assert g.nodes["n1"].status == ExecutionNodeStatus.FAILED
        assert g.nodes["n2"].status == ExecutionNodeStatus.FAILED
        assert g.skip_dependent_of("n0") == set()

    def test_completed_root_does_not_cascade_failure(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"])
        g.add_node(n0)
        g.add_node(n1)
        g.mark_completed("n0")

        assert g.skip_dependent_of("n0") == set()
        assert g.nodes["n1"].status == ExecutionNodeStatus.PENDING


# --------------------------------------------------------------------------- #
# ExecutionGraph — checkpoint / resume
# --------------------------------------------------------------------------- #

class TestExecutionGraphCheckpoint:

    def test_graph_roundtrip(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        n1 = ExecutionNode("n1", "t1", "cap.b", dependencies=["n0"],
                           status=ExecutionNodeStatus.COMPLETED,
                           outputs={"result": "42"})
        g.add_node(n0)
        g.add_node(n1)
        g.add_edge("n0", "n1")

        d = g.to_dict()
        restored = ExecutionGraph.from_dict(d)
        assert restored.task_id == "t1"
        assert set(restored.nodes) == {"n0", "n1"}
        assert restored.nodes["n1"].dependencies == ["n0"]
        assert restored.nodes["n1"].status == ExecutionNodeStatus.COMPLETED
        assert restored.nodes["n1"].outputs == {"result": "42"}
        assert len(restored.edges) == 1

    def test_checkpoint_preserves_retry_history(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a", retry_history=[
            {"attempt": 1, "error": "timeout", "failure_class": "TRANSIENT"}])
        g.add_node(n0)

        restored = ExecutionGraph.from_dict(g.to_dict())
        assert restored.nodes["n0"].retry_history[0]["error"] == "timeout"

    def test_mark_node_updates_timestamps(self) -> None:
        g = ExecutionGraph("t1")
        n0 = ExecutionNode("n0", "t1", "cap.a")
        g.add_node(n0)
        g.mark_completed("n0", {"value": 1})
        assert g.nodes["n0"].completed_at is not None
        assert g.nodes["n0"].outputs == {"value": 1}
        assert g.nodes["n0"].status == ExecutionNodeStatus.COMPLETED


# --------------------------------------------------------------------------- #
# GraphEdge
# --------------------------------------------------------------------------- #

class TestGraphEdge:

    def test_edge_roundtrip(self) -> None:
        e = GraphEdge(from_node="n0", to_node="n1")
        d = e.to_dict()
        assert d == {"from": "n0", "to": "n1"}
        restored = GraphEdge.from_dict(d)
        assert restored.from_node == "n0"
        assert restored.to_node == "n1"
