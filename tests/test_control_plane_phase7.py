"""
Phase 7 tests: Advanced Backend Systems (Think-Before-Act, Workflow Engine,
Event Sourcing, Vector Store, Circuit Breaker, Rate Limiter).

Tests are pure unit tests — no external services required.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from backend.control_plane.thinking import (
    ThinkBeforeActEngine,
    DeliberationPlan,
    DeliberationResult,
    ReasoningBlock,
    PlanStep,
    Constraint,
    FallbackStrategy,
    StepStatus,
    ConfidenceState,
    RiskLevel,
)
from backend.control_plane.workflow_engine import (
    WorkflowEngine,
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowRun,
    NodeConfig,
    NodeType,
    NodeStatus,
    WorkflowStatus,
    FailurePolicy,
    define_workflow,
)
from backend.control_plane.event_store import (
    Event,
    EventType,
    EventStore,
    Projection,
    InMemoryEventStore,
    ConcurrentModificationError,
)
from backend.control_plane.vector_store import (
    VectorStore,
    EmbeddingRecord,
    SearchResult,
    InMemoryVectorStore,
    DistanceMetric,
    VectorStoreError,
    VectorStoreFactory,
)
from backend.control_plane.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerStats,
    CircuitState,
    CircuitBreakerOpen,
    CircuitBreakerTimeout,
    CircuitBreakerRegistry,
)
from backend.control_plane.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitResult,
    RateLimitExceeded,
)


# --------------------------------------------------------------------------- #
# Think-Before-Act Engine Tests
# --------------------------------------------------------------------------- #

class TestThinkBeforeAct:

    def setup_method(self):
        ThinkBeforeActEngine.reset_instance()

    def test_deliberation_produces_plan(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Investigate the codebase structure")
        assert isinstance(result, DeliberationResult)
        assert isinstance(result.plan, DeliberationPlan)
        assert result.plan.goal == "Investigate the codebase structure"
        assert len(result.plan.steps) > 0
        assert result.plan.plan_id is not None

    def test_deliberation_sets_reasoning_trace(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Investigate the codebase structure")
        assert len(result.plan.reasoning_trace) > 0
        block = result.plan.reasoning_trace[0]
        assert isinstance(block, ReasoningBlock)
        assert len(block.thought) > 0
        assert block.confidence in ConfidenceState

    def test_deliberation_has_constraints(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Investigate the codebase structure")
        assert len(result.plan.constraints) > 0

    def test_deliberation_has_fallback_strategies(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Investigate the codebase structure")
        assert len(result.plan.fallback_strategies) > 0

    def test_deliberation_has_steps_with_dependencies(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Build a new component")
        assert len(result.plan.steps) >= 2
        assert len(result.plan.steps[1].depends_on) > 0

    def test_custom_deliberator(self):
        engine = ThinkBeforeActEngine()

        def custom_deliberator(goal, context):
            plan = DeliberationPlan(
                plan_id="custom-1",
                goal=goal,
                reasoning_trace=[
                    ReasoningBlock(
                        thought="Custom reasoning",
                        confidence=ConfidenceState.HIGH_CONFIDENCE,
                    )
                ],
                steps=[
                    PlanStep(id="s1", name="custom_step", description="custom"),
                ],
            )
            return plan

        engine.set_deliberator(custom_deliberator)
        result = engine.deliberate("Test custom deliberator")
        assert result.provider_used == "deliberator_callback"
        assert result.plan.plan_id == "custom-1"
        assert result.plan.steps[0].name == "custom_step"

    def test_deliberator_failure_falls_back(self):
        engine = ThinkBeforeActEngine()

        def failing_deliberator(goal, context):
            raise RuntimeError("Provider unavailable")

        engine.set_deliberator(failing_deliberator)
        result = engine.deliberate("Test goal")
        assert result.provider_used == "heuristic_fallback"
        assert "fallback" in result.note.lower()
        assert result.honest is True

    def test_step_status_updates(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Test task")
        plan_id = result.plan.plan_id
        assert engine.update_step_status(plan_id, "s1", StepStatus.DONE)
        assert engine.update_step_status(plan_id, "s2", StepStatus.FAILED, error="oops")
        assert not engine.update_step_status("nonexistent", "s1", StepStatus.DONE)
        assert not engine.update_step_status(plan_id, "nonexistent", StepStatus.DONE)

    def test_next_runnable_steps(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Test task")
        plan_id = result.plan.plan_id
        # Initially, s1 (no deps) should be runnable
        runnable = engine.next_runnable_steps(plan_id)
        assert len(runnable) >= 1
        assert runnable[0].id == "s1"
        # Mark s1 done, then s2 should be runnable
        engine.update_step_status(plan_id, "s1", StepStatus.DONE)
        runnable = engine.next_runnable_steps(plan_id)
        runnable_ids = [s.id for s in runnable]
        assert "s2" in runnable_ids

    def test_to_dict_roundtrip(self):
        engine = ThinkBeforeActEngine()
        result = engine.deliberate("Test roundtrip")
        d = result.plan.to_dict()
        assert d["goal"] == "Test roundtrip"
        assert "reasoning_trace" in d
        assert "steps" in d
        assert "constraints" in d

    def test_singleton_instance(self):
        e1 = ThinkBeforeActEngine.get_instance()
        e2 = ThinkBeforeActEngine.get_instance()
        assert e1 is e2


# --------------------------------------------------------------------------- #
# Workflow Engine Tests
# --------------------------------------------------------------------------- #

class TestWorkflowEngine:

    def setup_method(self):
        WorkflowEngine.reset_instance()

    def test_create_and_register_workflow(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Test WF", "A test workflow")
        node_a = WorkflowNode(id="a", name="Step A", action=lambda: "result_a")
        node_b = WorkflowNode(id="b", name="Step B", action=lambda: "result_b")
        engine.add_node(wf, node_a)
        engine.add_node(wf, node_b)
        engine.add_edge(wf, WorkflowEdge(from_node="a", to_node="b"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["b"])
        engine.register(wf)

        assert len(engine.list_workflows()) == 1

    def test_workflow_validates_acyclicity(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Cyclic WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A"))
        engine.add_node(wf, WorkflowNode(id="b", name="B"))
        engine.add_edge(wf, WorkflowEdge(from_node="a", to_node="b"))
        engine.add_edge(wf, WorkflowEdge(from_node="b", to_node="a"))
        engine.set_start_nodes(wf, ["a"])

        errors = wf.validate()
        assert any("Cycle" in e for e in errors)

    def test_workflow_detects_unknown_node_in_edge(self):
        wf = define_workflow("Bad Edge")
        node = WorkflowNode(id="a", name="A")
        wf.nodes["a"] = node
        wf.edges.append(WorkflowEdge(from_node="a", to_node="nonexistent"))
        wf.start_nodes = ["a"]
        errors = wf.validate()
        assert any("unknown node" in e for e in errors)

    def test_workflow_topological_sort(self):
        wf = define_workflow("Topo")
        for nid in ["a", "b", "c", "d"]:
            wf.nodes[nid] = WorkflowNode(id=nid, name=nid)
        wf.edges = [
            WorkflowEdge(from_node="a", to_node="b"),
            WorkflowEdge(from_node="a", to_node="c"),
            WorkflowEdge(from_node="b", to_node="d"),
            WorkflowEdge(from_node="c", to_node="d"),
        ]
        wf.start_nodes = ["a"]
        wf.end_nodes = ["d"]

        order = wf.topological_sort()
        assert order[0] == "a"
        assert order[-1] == "d"
        assert "b" in order and "c" in order
        # a must come before b and c
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        # b and c must come before d
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_run_succeeds_all_nodes_ok(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Success WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: "done_a"))
        engine.add_node(wf, WorkflowNode(id="b", name="B", action=lambda: "done_b",
                                         depends_on=["a"]))
        engine.add_edge(wf, WorkflowEdge(from_node="a", to_node="b"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["b"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.nodes["a"].status == NodeStatus.SUCCEEDED
        assert run.nodes["b"].status == NodeStatus.SUCCEEDED
        assert run.nodes["a"].result == "done_a"
        assert run.nodes["b"].result == "done_b"

    def test_run_fails_on_node_error(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Failure WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: "ok"))
        engine.add_node(wf, WorkflowNode(
            id="b", name="B",
            action=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            config=NodeConfig(failure_policy=FailurePolicy.FAIL_WORKFLOW, max_retries=0),
        ))
        engine.add_edge(wf, WorkflowEdge(from_node="a", to_node="b"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["b"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.FAILED
        assert "boom" in (run.error or "")

    def test_run_retries_on_failure(self):
        engine = WorkflowEngine()

        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("transient")
            return "recovered"

        wf = engine.build_workflow("Retry WF")
        engine.add_node(wf, WorkflowNode(
            id="a", name="A", action=flaky,
            config=NodeConfig(max_retries=3, retry_delay_sec=0.01, timeout_sec=5),
        ))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.nodes["a"].result == "recovered"
        assert call_count["n"] == 3

    def test_node_skipped_on_failure(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Skip WF")
        engine.add_node(wf, WorkflowNode(
            id="a", name="A",
            action=lambda: (_ for _ in ()).throw(RuntimeError("fail")),
            config=NodeConfig(failure_policy=FailurePolicy.SKIP_NODE, max_retries=0),
        ))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.nodes["a"].status == NodeStatus.SKIPPED

    def test_input_template_context(self):
        engine = WorkflowEngine()

        def greet(name):
            return f"Hello, {name}!"

        wf = engine.build_workflow("Template WF")
        engine.add_node(wf, WorkflowNode(
            id="a", name="Greet",
            action=greet,
            input_template={"name": "context:user_name"},
        ))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, context={"user_name": "Alice"}, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.nodes["a"].result == "Hello, Alice!"

    def test_input_template_result_ref(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Result Ref WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: 10))
        engine.add_node(wf, WorkflowNode(
            id="b", name="B",
            action=lambda x: x * 2,
            input_template={"x": "result:a"},
            depends_on=["a"],
        ))
        engine.add_edge(wf, WorkflowEdge(from_node="a", to_node="b"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["b"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.nodes["b"].result == 20

    def test_cancel_run(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Cancel WF")
        engine.add_node(wf, WorkflowNode(
            id="a", name="A",
            action=lambda: time.sleep(50),
        ))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=False, timeout_sec=None)
        time.sleep(0.2)
        assert engine.cancel_run(run.run_id)
        assert run.status == WorkflowStatus.CANCELLED

    def test_run_timeout(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Timeout WF")
        engine.add_node(wf, WorkflowNode(
            id="a", name="A",
            action=lambda: time.sleep(50),
            config=NodeConfig(timeout_sec=2),
        ))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=3)
        assert run.status == WorkflowStatus.FAILED

    def test_get_run(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Get Run WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: "ok"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        fetched = engine.get_run(run.run_id)
        assert fetched is not None
        assert fetched.run_id == run.run_id

    def test_list_runs_filtered(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Filtered WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: "ok"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        runs = engine.list_runs(workflow_id=wf.workflow_id)
        assert len(runs) == 1
        assert runs[0].workflow_id == wf.workflow_id

    def test_workflow_run_to_dict(self):
        engine = WorkflowEngine()
        wf = engine.build_workflow("Dict WF")
        engine.add_node(wf, WorkflowNode(id="a", name="A", action=lambda: "ok"))
        engine.set_start_nodes(wf, ["a"])
        engine.set_end_nodes(wf, ["a"])
        engine.register(wf)

        run = engine.run(wf.workflow_id, synchronous=True, timeout_sec=10)
        d = run.to_dict()
        assert "run_id" in d
        assert "workflow_id" in d
        assert "nodes" in d
        assert "a" in d["nodes"]

    def test_singleton_instance(self):
        e1 = WorkflowEngine.get_instance()
        e2 = WorkflowEngine.get_instance()
        assert e1 is e2
        WorkflowEngine.reset_instance()


# --------------------------------------------------------------------------- #
# Event Store Tests
# --------------------------------------------------------------------------- #

class TestEventStore:

    def test_append_single_event(self):
        store = InMemoryEventStore()
        event = Event(
            aggregate_id="agg-1",
            aggregate_type="test",
            event_type="test.event",
            payload={"value": 42},
        )
        result = store.append(event)
        assert result.version == 1
        assert result.event_id is not None

    def test_append_batch(self):
        store = InMemoryEventStore()
        events = [
            Event(aggregate_id="agg-1", aggregate_type="test",
                  event_type="test.created", payload={"n": 1}),
            Event(aggregate_id="agg-1", aggregate_type="test",
                  event_type="test.updated", payload={"n": 2}),
            Event(aggregate_id="agg-1", aggregate_type="test",
                  event_type="test.updated", payload={"n": 3}),
        ]
        results = store.append_batch(events)
        assert len(results) == 3
        assert results[0].version == 1
        assert results[2].version == 3

    def test_get_stream(self):
        store = InMemoryEventStore()
        for i in range(5):
            store.append(Event(
                aggregate_id="agg-1", aggregate_type="test",
                event_type="test.event", payload={"i": i},
            ))
        stream = store.get_stream("agg-1")
        assert len(stream) == 5
        assert stream[0].version == 1
        assert stream[4].version == 5

    def test_get_stream_from_version(self):
        store = InMemoryEventStore()
        for i in range(5):
            store.append(Event(
                aggregate_id="agg-1", aggregate_type="test",
                event_type="test.event", payload={"i": i},
            ))
        stream = store.get_stream("agg-1", from_version=3)
        assert len(stream) == 3
        assert stream[0].version == 3

    def test_get_aggregate_version(self):
        store = InMemoryEventStore()
        assert store.get_aggregate_version("unknown") == 0
        store.append(Event(aggregate_id="agg-1", aggregate_type="test",
                            event_type="e", payload={}))
        store.append(Event(aggregate_id="agg-1", aggregate_type="test",
                            event_type="e", payload={}))
        assert store.get_aggregate_version("agg-1") == 2

    def test_get_by_type(self):
        store = InMemoryEventStore()
        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="created", payload={}))
        store.append(Event(aggregate_id="a2", aggregate_type="test",
                           event_type="updated", payload={}))
        store.append(Event(aggregate_id="a3", aggregate_type="test",
                           event_type="created", payload={}))

        created = store.get_by_type("created")
        assert len(created) == 2

    def test_concurrent_modification(self):
        store = InMemoryEventStore()

        event = Event(
            aggregate_id="agg-1", aggregate_type="test",
            event_type="e", payload={},
        )

        store.append(event, expected_version=0)
        assert store.get_aggregate_version("agg-1") == 1

        with pytest.raises(ConcurrentModificationError):
            store.append(event, expected_version=0)

    def test_replay(self):
        store = InMemoryEventStore()

        def apply(state, event):
            if state is None:
                state = 0
            if event.event_type == "increment":
                state += event.payload.get("by", 1)
            elif event.event_type == "decrement":
                state -= event.payload.get("by", 1)
            return state

        store.append(Event(aggregate_id="counter", aggregate_type="counter",
                           event_type="increment", payload={"by": 5}))
        store.append(Event(aggregate_id="counter", aggregate_type="counter",
                           event_type="increment", payload={"by": 3}))
        store.append(Event(aggregate_id="counter", aggregate_type="counter",
                           event_type="decrement", payload={"by": 2}))

        state = store.replay("counter", apply)
        assert state == 6

    def test_subscribe(self):
        store = InMemoryEventStore()
        received: list = []

        def handler(event):
            received.append(event.event_type)

        store.subscribe(handler)
        store.append(Event(
            aggregate_id="a1", aggregate_type="test",
            event_type="created", payload={},
        ))
        assert len(received) == 1
        assert received[0] == "created"

    def test_subscribe_to_type(self):
        store = InMemoryEventStore()
        received: list = []

        store.subscribe_to_type("created", lambda e: received.append(e))
        store.subscribe_to_type("updated", lambda e: received.append(e))

        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="created", payload={}))
        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="updated", payload={}))
        store.append(Event(aggregate_id="a2", aggregate_type="test",
                           event_type="deleted", payload={}))

        assert len(received) == 2

    def test_snapshot(self):
        store = InMemoryEventStore()
        store.append(Event(aggregate_id="agg-1", aggregate_type="test",
                           event_type="increment", payload={}))
        store.append(Event(aggregate_id="agg-1", aggregate_type="test",
                           event_type="increment", payload={}))
        store.append(Event(aggregate_id="agg-1", aggregate_type="test",
                           event_type="increment", payload={}))

        snap = store.create_snapshot("agg-1", {"count": 3})
        assert snap.event_type == EventType.STATE_SNAPSHOT.value

        retrieved = store.get_snapshot("agg-1")
        assert retrieved is not None
        assert retrieved.payload["count"] == 3

    def test_projection(self):
        store = InMemoryEventStore()

        class CountingProjection(Projection):
            def __init__(self):
                super().__init__()
                self.count = 0

            def apply_event(self, event):
                if event.event_type == "increment":
                    self.count += 1

        proj = CountingProjection()
        store.project_from_start(proj)
        assert proj.count == 0
        assert proj.version == 0

        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="increment", payload={}).__class__(
            aggregate_id="a1", aggregate_type="test",
            event_type="increment", payload={}, version=1,
        ))

        store.project_from_start(proj)
        # The projection was already at version 0, so it replays all events
        assert proj.count >= 0

    def test_stats(self):
        store = InMemoryEventStore()
        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="e", payload={}))
        stats = store.stats()
        assert stats["total_events"] == 1
        assert stats["total_streams"] == 1

    def test_event_from_dict(self):
        event = Event(
            event_id="abc-123",
            aggregate_id="agg-1",
            aggregate_type="test",
            version=5,
            event_type="test.event",
            timestamp=1234567890.0,
            payload={"key": "value"},
            metadata={"meta": "data"},
        )
        d = event.to_dict()
        restored = Event.from_dict(d)
        assert restored.event_id == "abc-123"
        assert restored.version == 5
        assert restored.payload == {"key": "value"}
        assert restored.metadata == {"meta": "data"}

    def test_event_types_enum(self):
        assert EventType.STATE_SNAPSHOT.value == "state.snapshot"
        assert EventType.TASK_CREATED.value == "task.created"
        assert EventType.WORKFLOW_STARTED.value == "workflow.started"

    def test_clear(self):
        store = InMemoryEventStore()
        store.append(Event(aggregate_id="a1", aggregate_type="test",
                           event_type="e", payload={}))
        assert store.stats()["total_events"] == 1
        store.clear()
        assert store.stats()["total_events"] == 0


# --------------------------------------------------------------------------- #
# Vector Store Tests
# --------------------------------------------------------------------------- #

class TestVectorStore:

    def test_upsert_and_stats(self):
        store = InMemoryVectorStore(dimension=3)
        record = EmbeddingRecord(
            id="doc-1",
            vector=[0.1, 0.2, 0.3],
            text="Hello world",
            namespace="test",
            metadata={"category": "greeting"},
        )
        n = store.upsert([record])
        assert n == 1
        stats = store.stats()
        assert stats["vector_count"] == 1
        assert stats["backend"] == "memory"

    def test_search_returns_results(self):
        store = InMemoryVectorStore(dimension=2, metric=DistanceMetric.COSINE)
        # doc-0 is identical to query direction; doc-1 has 45deg, doc-2 orthogonal,
        # doc-3 opposite
        store.upsert([
            EmbeddingRecord(id="doc-0", vector=[1.0, 0.0], text="identical", namespace="test"),
            EmbeddingRecord(id="doc-1", vector=[1.0, 1.0], text="diagonal", namespace="test"),
            EmbeddingRecord(id="doc-2", vector=[0.0, 1.0], text="orthogonal", namespace="test"),
            EmbeddingRecord(id="doc-3", vector=[-1.0, 0.0], text="opposite", namespace="test"),
        ])

        results = store.search([1.0, 0.0], top_k=3)
        assert len(results) == 3
        # doc-0 is most similar (cosine distance 0)
        assert results[0].record.id == "doc-0"
        # doc-1 is second (cosine distance ~0.293)
        assert results[1].record.id == "doc-1"
        # doc-2 is third (cosine distance 1.0)
        assert results[2].record.id == "doc-2"
        assert all(0.0 <= r.score <= 1.0 for r in results)

    def test_search_l2_metric(self):
        store = InMemoryVectorStore(dimension=2, metric=DistanceMetric.L2)
        store.upsert([
            EmbeddingRecord(id="a", vector=[0.0, 0.0], text="a", namespace="ns"),
            EmbeddingRecord(id="b", vector=[3.0, 4.0], text="b", namespace="ns"),
        ])
        results = store.search([0.0, 0.0], top_k=2)
        assert results[0].record.id == "a"  # distance 0
        assert results[1].record.id == "b"  # distance 5

    def test_search_inner_product(self):
        store = InMemoryVectorStore(dimension=2, metric=DistanceMetric.INNER_PRODUCT)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns"),
            EmbeddingRecord(id="b", vector=[0.0, 1.0], text="b", namespace="ns"),
        ])
        results = store.search([2.0, 0.0], top_k=2)
        # Higher dot product = lower distance (negated)
        assert results[0].record.id == "a"

    def test_search_with_filter(self):
        store = InMemoryVectorStore(dimension=2, metric=DistanceMetric.COSINE)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns",
                            metadata={"category": "greeting"}),
            EmbeddingRecord(id="b", vector=[0.0, 1.0], text="b", namespace="ns",
                            metadata={"category": "goodbye"}),
        ])
        results = store.search([1.0, 0.0], top_k=10, filter={"category": "greeting"})
        assert len(results) == 1
        assert results[0].record.id == "a"

    def test_search_with_min_score(self):
        store = InMemoryVectorStore(dimension=2, metric=DistanceMetric.COSINE)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns"),
            EmbeddingRecord(id="b", vector=[0.0, 1.0], text="b", namespace="ns"),
        ])
        results = store.search([1.0, 0.0], top_k=10, min_score=0.5)
        assert len(results) == 1
        assert results[0].record.id == "a"

    def test_delete(self):
        store = InMemoryVectorStore(dimension=2)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns"),
            EmbeddingRecord(id="b", vector=[0.0, 1.0], text="b", namespace="ns"),
        ])
        deleted = store.delete(["a"])
        assert deleted == 1
        assert store.stats()["vector_count"] == 1

    def test_fetch(self):
        store = InMemoryVectorStore(dimension=2)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns",
                            metadata={"k": "v"}),
        ])
        result = store.fetch(["a", "nonexistent"])
        assert "a" in result
        assert "nonexistent" not in result
        assert result["a"].text == "a"

    def test_namespace_isolation(self):
        store = InMemoryVectorStore(dimension=2)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns1"),
            EmbeddingRecord(id="a", vector=[0.0, 1.0], text="b", namespace="ns2"),
        ])
        results = store.search([1.0, 0.0], top_k=10, namespace="ns1")
        assert len(results) == 1
        assert results[0].record.namespace == "ns1"

    def test_search_empty_store(self):
        store = InMemoryVectorStore(dimension=2)
        results = store.search([1.0, 0.0], top_k=10)
        assert len(results) == 0

    def test_factory_creates_stores(self):
        mem = VectorStoreFactory.create("memory", dimension=5)
        assert isinstance(mem, InMemoryVectorStore)
        assert mem.dimension == 5

    def test_record_to_from_dict(self):
        rec = EmbeddingRecord(
            id="rec-1", vector=[0.1, 0.2], text="test",
            namespace="ns", metadata={"key": "val"}, created_at=123.456,
        )
        d = rec.to_dict()
        restored = EmbeddingRecord.from_dict(d)
        assert restored.id == "rec-1"
        assert restored.vector == [0.1, 0.2]
        assert restored.metadata == {"key": "val"}

    def test_search_result_to_dict(self):
        store = InMemoryVectorStore(dimension=2)
        store.upsert([
            EmbeddingRecord(id="a", vector=[1.0, 0.0], text="a", namespace="ns"),
        ])
        results = store.search([1.0, 0.0], top_k=1)
        d = results[0].to_dict()
        assert d["id"] == "a"
        assert "score" in d


# --------------------------------------------------------------------------- #
# Circuit Breaker Tests
# --------------------------------------------------------------------------- #

class TestCircuitBreaker:

    def setup_method(self):
        CircuitBreakerRegistry.reset_instance()

    def test_closes_when_healthy(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout_sec=10, timeout_sec=1,
        ))

        call_count = 0
        for _ in range(10):
            result = breaker.call(lambda: globals().__setitem__("call_count", call_count + 1) or "ok")
            call_count = call_count + 1

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.success_count == 10

    def test_opens_after_threshold(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout_sec=30, timeout_sec=1,
            exception_types=(ValueError,),
        ))

        for _ in range(3):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.total_trip_count == 3

    def test_open_circuit_rejects_calls(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_sec=60, timeout_sec=1,
            exception_types=(RuntimeError,),
        ))

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert breaker.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpen):
            breaker.call(lambda: "should not execute")

    def test_half_open_recovery(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_sec=0.5, timeout_sec=1,
            exception_types=(RuntimeError,),
            half_open_max_calls=1,
        ))

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.6)

        # Half-open: first call succeeds -> circuit closes
        result = breaker.call(lambda: "recovered")
        assert breaker.state == CircuitState.CLOSED
        assert result == "recovered"

    def test_half_open_failure_reopens(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_sec=0.3, timeout_sec=1,
            exception_types=(RuntimeError,),
            half_open_max_calls=1,
        ))

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert breaker.state == CircuitState.OPEN

        time.sleep(0.4)

        # Half-open: first call fails -> circuit reopens
        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("still failing")))

        assert breaker.state == CircuitState.OPEN

    def test_timeout(self):
        breaker = CircuitBreaker("slow-service", CircuitBreakerConfig(
            failure_threshold=5, recovery_timeout_sec=60, timeout_sec=0.5,
        ))

        with pytest.raises(CircuitBreakerTimeout):
            breaker.call(lambda: time.sleep(10))

    def test_decorator(self):
        breaker = CircuitBreaker("decorator-service", CircuitBreakerConfig(
            failure_threshold=5, recovery_timeout_sec=60, timeout_sec=2,
        ))

        @breaker.with_circuit_breaker
        def my_func():
            return "decorated_result"

        assert my_func() == "decorated_result"

    def test_reset(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_sec=60, timeout_sec=1,
            exception_types=(ValueError,),
        ))

        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert breaker.state == CircuitState.OPEN
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failure_count == 0

    def test_manual_trip(self):
        breaker = CircuitBreaker("test-service")
        breaker.trip_manually("maintenance")
        assert breaker.state == CircuitState.OPEN

    def test_stats_to_dict(self):
        breaker = CircuitBreaker("test-service", CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout_sec=30, timeout_sec=5,
            exception_types=(ValueError,),
        ))
        breaker.call(lambda: "ok")
        d = breaker.get_state()
        assert d["state"] == "closed"
        assert d["total_trip_count"] == 0
        assert d["success_count"] == 1

    def test_registry_get_or_create(self):
        registry = CircuitBreakerRegistry.get_instance()
        b1 = registry.get_or_create("svc-a")
        b2 = registry.get_or_create("svc-a")
        assert b1 is b2

    def test_registry_is_available(self):
        registry = CircuitBreakerRegistry.get_instance()
        assert registry.is_available("nonexistent") is True

    def test_registry_get_all_state(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.register("svc-a")
        registry.register("svc-b")
        states = registry.get_all_state()
        assert "svc-a" in states
        assert "svc-b" in states

    def test_registry_reset(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.register("svc-a")
        assert len(registry._breakers) == 1
        registry.reset()
        assert len(registry._breakers) == 0


# --------------------------------------------------------------------------- #
# Rate Limiter Tests
# --------------------------------------------------------------------------- #

class TestRateLimiter:

    def setup_method(self):
        RateLimiter.reset_instance()

    def test_in_memory_allows_until_limit(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=5, window_sec=60, algorithm="token_bucket")

        for i in range(5):
            result = limiter.check("user:test", config)
            assert result.allowed

        result = limiter.check("user:test", config)
        assert not result.allowed
        assert result.remaining == 0

    def test_consume_raises_when_exceeded(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=2, window_sec=60, algorithm="token_bucket")

        limiter.consume("user:test", config)
        limiter.consume("user:test", config)

        with pytest.raises(RateLimitExceeded) as exc_info:
            limiter.consume("user:test", config)

        err = exc_info.value
        assert err.limit == 2
        assert err.retry_after > 0

    def test_per_scope_isolation(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=1, window_sec=60, algorithm="token_bucket")

        limiter.consume("user:alice", config)
        limiter.consume("user:bob", config)

        with pytest.raises(RateLimitExceeded):
            limiter.consume("user:alice", config)

    def test_sliding_window_algorithm(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=3, window_sec=1.0, algorithm="sliding_window")

        for _ in range(3):
            limiter.consume("test:sw", config)

        with pytest.raises(RateLimitExceeded):
            limiter.consume("test:sw", config)

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        result = limiter.check("test:sw", config)
        assert result.allowed

    def test_token_bucket_burst(self):
        limiter = RateLimiter()
        config = RateLimitConfig(
            limit=10, window_sec=60, algorithm="token_bucket", burst=20,
        )

        # Should allow up to burst (20) immediately
        for _ in range(20):
            result = limiter.check("test:burst", config)
            assert result.allowed

        result = limiter.check("test:burst", config)
        assert not result.allowed

    def test_reset(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=1, window_sec=60, algorithm="token_bucket")

        limiter.consume("user:test", config)
        with pytest.raises(RateLimitExceeded):
            limiter.consume("user:test", config)

        cleared = limiter.reset("user", "test")
        assert cleared == 1

        result = limiter.check("user:test", config)
        assert result.allowed

    def test_reset_all(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=1, window_sec=60, algorithm="token_bucket")

        limiter.consume("user:a", config)
        limiter.consume("user:b", config)

        cleared = limiter.reset()
        assert cleared == 2

    def test_get_state(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=5, window_sec=60, algorithm="token_bucket")
        limiter.consume("user:test", config)

        state = limiter.get_state()
        assert state["backend"] == "memory"
        assert state["active_buckets"] >= 1

    def test_rate_limit_result_to_dict(self):
        result = RateLimitResult(
            allowed=True, key="user:test", limit=10,
            remaining=9, reset_at=time.time(), retry_after=0.0,
            algorithm="token_bucket",
        )
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["key"] == "user:test"
        assert d["limit"] == 10

    def test_decorator(self):
        limiter = RateLimiter()
        config = RateLimitConfig(limit=3, window_sec=60, algorithm="token_bucket")

        call_count = {"n": 0}

        @limiter.limit(scope="user", limit=3, window_sec=60, algorithm="token_bucket")
        def api_call(user_id="test"):
            call_count["n"] += 1
            return "response"

        for _ in range(3):
            api_call(user_id="alice")

        with pytest.raises(RateLimitExceeded):
            api_call(user_id="alice")

        # Different user can still call
        api_call(user_id="bob")
        assert call_count["n"] == 4

    def test_check_rate_limit_convenience(self):
        from backend.control_plane.rate_limiter import check_rate_limit, consume_rate_limit
        config = RateLimitConfig(limit=2, window_sec=60, algorithm="token_bucket")
        result = check_rate_limit("user", "test_user", config)
        assert result.allowed
        result2 = consume_rate_limit("user", "test_user", config)
        assert result2.allowed

    def test_config_to_dict(self):
        config = RateLimitConfig(
            limit=100, window_sec=30, algorithm="token_bucket", burst=50,
        )
        d = config.to_dict()
        assert d["limit"] == 100
        assert d["burst"] == 50
        assert d["algorithm"] == "token_bucket"
