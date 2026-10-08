"""
Agentic Workflow Engine - DAG-based multi-step orchestration.

Models multi-agent / multi-step tasks as a directed acyclic graph (DAG).
Nodes represent work units (tool calls, decisions, sub-agents); edges express
dependencies and conditional routing.  The engine performs a topological
execution with parallelism for independent branches, mirroring the semantics
of LangGraph and AutoGen workflows.

Key abstractions:
  * :class:`WorkflowNode`  — a unit of work with a callable action.
  * :class:`WorkflowEdge`  — dependency or conditional transition.
  * :class:`Workflow`      — the DAG container with validation.
  * :class:`WorkflowEngine` — executes workflows, tracks state, persists events.

Design:
  * Validates DAG acyclicity on build (rejects cycles).
  * Supports parallel execution of independent nodes via a thread pool.
  * Nodes can fail; the engine applies retry, skip, or abort policies.
  * Integrates with the Event Sourcing store and Circuit Breaker.
  * Honest: a node that cannot proceed returns a structured failure
    rather than fabricating a result.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("control_plane.workflow_engine")


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class NodeType(str, Enum):
    """Types of workflow nodes."""

    ACTION = "action"
    CONDITION = "condition"
    START = "start"
    END = "end"
    PARALLEL = "parallel"
    AGGREGATE = "aggregate"
    TOOL = "tool"
    SUB_AGENT = "sub_agent"
    HUMAN = "human"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class FailurePolicy(str, Enum):
    """What to do when a node fails."""

    FAIL_WORKFLOW = "fail_workflow"
    SKIP_NODE = "skip_node"
    RETRY = "retry"
    CONTINUE = "continue"


@dataclass
class NodeConfig:
    """Configuration for a workflow node."""

    max_retries: int = 3
    retry_delay_sec: float = 1.0
    timeout_sec: float = 60.0
    failure_policy: FailurePolicy = FailurePolicy.FAIL_WORKFLOW
    circuit_id: Optional[str] = None


@dataclass
class WorkflowNode:
    """A single node in a workflow DAG."""

    id: str
    name: str
    node_type: NodeType = NodeType.ACTION
    action: Optional[Callable[..., Any]] = None
    config: NodeConfig = field(default_factory=NodeConfig)
    input_template: Optional[Dict[str, Any]] = None
    depends_on: List[str] = field(default_factory=list)
    conditions: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    attempt: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "config": {
                "max_retries": self.config.max_retries,
                "retry_delay_sec": self.config.retry_delay_sec,
                "timeout_sec": self.config.timeout_sec,
                "failure_policy": self.config.failure_policy.value,
                "circuit_id": self.config.circuit_id,
            },
            "input_template": self.input_template,
            "depends_on": self.depends_on,
            "conditions": self.conditions,
            "metadata": self.metadata,
            "status": self.status.value,
            "attempt": self.attempt,
            "retries": self.retries,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "has_result": self.result is not None,
        }

    def reset_runtime(self) -> None:
        self.status = NodeStatus.PENDING
        self.result = None
        self.error = None
        self.attempt = 0
        self.retries = 0
        self.started_at = None
        self.completed_at = None


@dataclass
class WorkflowEdge:
    """An edge in the workflow DAG (dependency or conditional transition)."""

    from_node: str
    to_node: str
    condition: Optional[str] = None
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_node,
            "to": self.to_node,
            "condition": self.condition,
            "weight": self.weight,
        }


@dataclass
class WorkflowRun:
    """A single execution of a workflow."""

    run_id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    edge_results: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edge_results": self.edge_results,
            "context": self.context,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


@dataclass
class Workflow:
    """A DAG-based workflow definition."""

    workflow_id: str
    name: str
    description: str = ""
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    edges: List[WorkflowEdge] = field(default_factory=list)
    start_nodes: List[str] = field(default_factory=list)
    end_nodes: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "start_nodes": self.start_nodes,
            "end_nodes": self.end_nodes,
            "config": self.config,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    def validate(self) -> List[str]:
        """Validate the workflow DAG. Returns a list of errors (empty = valid)."""
        errors: List[str] = []

        # Check for duplicate node IDs
        seen: Set[str] = set()
        for nid in self.nodes:
            if nid in seen:
                errors.append(f"Duplicate node ID: {nid}")
            seen.add(nid)

        # Check edges reference valid nodes
        for edge in self.edges:
            if edge.from_node not in self.nodes:
                errors.append(f"Edge references unknown node: {edge.from_node}")
            if edge.to_node not in self.nodes:
                errors.append(f"Edge references unknown node: {edge.to_node}")

        # Check start/end nodes exist
        for sn in self.start_nodes:
            if sn not in self.nodes:
                errors.append(f"Start node does not exist: {sn}")
        for en in self.end_nodes:
            if en not in self.nodes:
                errors.append(f"End node does not exist: {en}")

        # Check all nodes are referenced (either as start/end or have edges)
        referenced: Set[str] = set()
        referenced.update(self.start_nodes)
        referenced.update(self.end_nodes)
        for edge in self.edges:
            referenced.add(edge.from_node)
            referenced.add(edge.to_node)

        for nid, node in self.nodes.items():
            if nid not in referenced and len(self.nodes) > 1:
                errors.append(f"Node '{nid}' is not connected: {node.name}")

        # Check for cycles using DFS
        cycle = self._detect_cycle()
        if cycle:
            errors.append(f"Cycle detected: {' -> '.join(cycle)}")

        return errors

    def _detect_cycle(self) -> Optional[List[str]]:
        """Detect cycles using DFS. Returns the cycle path if found."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self.nodes}
        parent: Dict[str, Optional[str]] = {nid: None for nid in self.nodes}

        adj: Dict[str, List[str]] = {}
        for edge in self.edges:
            adj.setdefault(edge.from_node, []).append(edge.to_node)

        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            for neighbor in adj.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle; reconstruct path
                    cycle = [neighbor, node]
                    curr = parent[node]
                    while curr is not None and curr != neighbor:
                        cycle.append(curr)
                        curr = parent[curr]
                    cycle.reverse()
                    cycle.append(neighbor)
                    return cycle
                if color[neighbor] == WHITE:
                    parent[neighbor] = node
                    result = dfs(neighbor)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for nid in self.nodes:
            if color[nid] == WHITE:
                result = dfs(nid)
                if result:
                    return result
        return None

    def topological_sort(self) -> List[str]:
        """Return nodes in topological order."""
        in_degree: Dict[str, int] = {}
        adj: Dict[str, List[str]] = {}

        for nid in self.nodes:
            in_degree[nid] = 0
        for edge in self.edges:
            adj.setdefault(edge.from_node, []).append(edge.to_node)
            in_degree[edge.to_node] = in_degree.get(edge.to_node, 0) + 1

        queue: List[str] = [nid for nid, d in in_degree.items() if d == 0]
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            logger.warning("Workflow %s has a cycle; topological sort incomplete", self.workflow_id)
        return result

    def dependents(self, node_id: str) -> List[str]:
        """Return nodes that depend on *node_id* (i.e., edges from node_id)."""
        return [e.to_node for e in self.edges if e.from_node == node_id]

    def dependencies(self, node_id: str) -> List[str]:
        """Return nodes that *node_id* depends on."""
        return [e.from_node for e in self.edges if e.to_node == node_id]

    def node(self, node_id: str) -> Optional[WorkflowNode]:
        return self.nodes.get(node_id)


class WorkflowEngine:
    """
    Executes workflow DAGs with parallelism, retries, and circuit-breaker
    integration.
    """

    _instance: Optional["WorkflowEngine"] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._workflows: Dict[str, Workflow] = {}
        self._runs: Dict[str, WorkflowRun] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls, max_workers: int = 4) -> "WorkflowEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_workers=max_workers)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def register(self, workflow: Workflow) -> Workflow:
        """Register a workflow definition."""
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        with self._lock:
            self._workflows[workflow.workflow_id] = workflow
        logger.info("Registered workflow %s: %s", workflow.workflow_id, workflow.name)
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow:
                # Return a copy so runs can mutate node state independently
                import copy
                return copy.deepcopy(workflow)
        return None

    def list_workflows(self) -> List[Workflow]:
        with self._lock:
            return list(self._workflows.values())

    def run(
        self,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        synchronous: bool = True,
        timeout_sec: Optional[float] = None,
    ) -> WorkflowRun:
        """Execute a workflow by ID."""
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        run = WorkflowRun(
            run_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            nodes={nid: self._copy_node(node) for nid, node in workflow.nodes.items()},
            context=context or {},
            started_at=time.time(),
        )

        # Reset nodes for this run
        for node in run.nodes.values():
            node.reset_runtime()

        with self._lock:
            self._runs[run.run_id] = run

        if synchronous:
            self._execute_sync(workflow, run, timeout_sec)
        else:
            thread = threading.Thread(
                target=self._execute_sync,
                args=(workflow, run, timeout_sec),
                daemon=True,
            )
            thread.start()

        return run

    @staticmethod
    def _copy_node(node: WorkflowNode) -> WorkflowNode:
        """Create a fresh copy of a node for a workflow run."""
        import copy
        new = copy.deepcopy(node)
        new.reset_runtime()
        return new

    def _execute_sync(
        self,
        workflow: Workflow,
        run: WorkflowRun,
        timeout_sec: Optional[float],
    ) -> None:
        """Execute a workflow synchronously in topological order."""
        try:
            self._execute_workflow(workflow, run, timeout_sec)
        except Exception as exc:
            logger.error("Workflow execution error: %s", exc)
            run.status = WorkflowStatus.FAILED
            run.error = str(exc)
            run.completed_at = time.time()

    def _execute_workflow(
        self,
        workflow: Workflow,
        run: WorkflowRun,
        timeout_sec: Optional[float],
    ) -> None:
        """Main execution loop: process ready nodes in topological waves."""
        start_time = time.time()

        # Process start nodes
        ready: List[str] = list(workflow.start_nodes)

        while ready:
            if timeout_sec is not None:
                elapsed = time.time() - start_time
                if elapsed > timeout_sec:
                    run.status = WorkflowStatus.FAILED
                    run.error = f"Timeout after {timeout_sec}s"
                    run.completed_at = time.time()
                    self._record_events(workflow, run, final=True)
                    return

            # Execute all ready nodes (potentially in parallel)
            nodes_to_run = ready[:]
            ready = []

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures: Dict[Any, str] = {}
                for nid in nodes_to_run:
                    node = run.nodes[nid]
                    node.status = NodeStatus.RUNNING
                    node.started_at = time.time()
                    future = executor.submit(self._execute_node, workflow, run, nid)
                    futures[future] = nid

                for future in as_completed(futures, timeout=timeout_sec):
                    nid = futures[future]
                    node = run.nodes[nid]
                    try:
                        success = future.result()
                        if success:
                            node.status = NodeStatus.SUCCEEDED
                        elif node.status != NodeStatus.SKIPPED:
                            node.status = NodeStatus.FAILED
                    except Exception as exc:
                        node.error = str(exc)
                        node.status = NodeStatus.FAILED
                    finally:
                        node.completed_at = time.time()

            # Handle node failures based on failure policy
            for nid in nodes_to_run:
                node = run.nodes[nid]
                if node.status in (NodeStatus.FAILED, NodeStatus.CANCELLED):
                    self._handle_node_failure(workflow, run, node)
                    # If the workflow was marked as failed, return
                    if run.status == WorkflowStatus.FAILED:
                        return
                    # For SKIP_NODE policy, the node is now SKIPPED; continue

            # Find newly ready nodes
            for nid, node in run.nodes.items():
                if node.status == NodeStatus.PENDING:
                    deps = workflow.dependencies(nid)
                    if all(
                        run.nodes.get(d, WorkflowNode(id="", name="")).status
                        in (NodeStatus.SUCCEEDED, NodeStatus.SKIPPED)
                        for d in deps
                    ):
                        ready.append(nid)

        # Check if all nodes completed
        all_done = all(
            n.status in (NodeStatus.SUCCEEDED, NodeStatus.SKIPPED, NodeStatus.FAILED)
            for n in run.nodes.values()
        )

        if all_done:
            any_failed = any(n.status == NodeStatus.FAILED for n in run.nodes.values())
            run.status = WorkflowStatus.FAILED if any_failed else WorkflowStatus.SUCCEEDED
        else:
            run.status = WorkflowStatus.FAILED
            run.error = "Not all nodes completed"

        run.completed_at = time.time()
        self._record_events(workflow, run, final=True)

    def _execute_node(
        self, workflow: Workflow, run: WorkflowRun, node_id: str
    ) -> bool:
        """Execute a single node. Returns True if succeeded."""
        node = run.nodes[node_id]
        node.attempt += 1

        # Check circuit breaker
        if node.config.circuit_id:
            try:
                from .circuit_breaker import circuit_breaker_registry, CircuitBreakerOpen
                registry = circuit_breaker_registry
                breaker = registry.get(node.config.circuit_id)
                if breaker and breaker.state.value == "open":
                    node.error = f"Circuit '{node.config.circuit_id}' is OPEN"
                    logger.warning("Node %s blocked by open circuit: %s", node_id, node.config.circuit_id)
                    return False
            except Exception:
                pass  # Circuit breaker not available; proceed

        action = node.action
        if action is None:
            node.error = "No action defined for node"
            return False

        # Build input from context/template
        node_input: Dict[str, Any] = {}
        if node.input_template:
            for k, v in node.input_template.items():
                if isinstance(v, str) and v.startswith("context:"):
                    key = v[8:]
                    node_input[k] = run.context.get(key)
                elif isinstance(v, str) and v.startswith("result:"):
                    node_id_ref = v[7:]
                    ref_node = run.nodes.get(node_id_ref)
                    node_input[k] = ref_node.result if ref_node else None
                else:
                    node_input[k] = v

        # Retry loop — first attempt is attempt 1; up to max_retries additional retries
        max_attempts = node.config.max_retries + 1
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            node.attempt = attempt
            try:
                result = action(**node_input) if node_input else action()
                node.result = result
                node.retries = attempt - 1
                return True
            except Exception as exc:
                last_exc = exc
                node.error = str(exc)
                logger.warning(
                    "Node %s attempt %d/%d failed: %s", node_id, attempt,
                    max_attempts, exc
                )
                if attempt < max_attempts:
                    delay = min(node.config.retry_delay_sec, 5.0)
                    time.sleep(delay)
                else:
                    node.retries = attempt - 1
                    return False

        return False

    def _handle_node_failure(
        self, workflow: Workflow, run: WorkflowRun, node: WorkflowNode
    ) -> None:
        """Handle a node failure based on its failure policy."""
        if node.config.failure_policy == FailurePolicy.FAIL_WORKFLOW:
            run.status = WorkflowStatus.FAILED
            run.error = f"Node '{node.name}' failed: {node.error}"
            run.completed_at = time.time()
            self._record_events(workflow, run, final=True)
        elif node.config.failure_policy == FailurePolicy.SKIP_NODE:
            logger.info("Skipping failed node '%s' (policy: skip)", node.name)
            node.status = NodeStatus.SKIPPED

    def _record_events(
        self, workflow: Workflow, run: WorkflowRun, *, final: bool = False
    ) -> None:
        """Record workflow events to the Event Sourcing store (best-effort)."""
        try:
            from .event_store import Event, EventType, event_store

            if final:
                etype = (
                    EventType.WORKFLOW_COMPLETED
                    if run.status == WorkflowStatus.SUCCEEDED
                    else EventType.WORKFLOW_FAILED
                )
            else:
                etype = EventType.WORKFLOW_STARTED

            event_store.append(
                Event(
                    aggregate_id=run.run_id,
                    aggregate_type="workflow_run",
                    event_type=etype.value,
                    payload={
                        "workflow_id": workflow.workflow_id,
                        "workflow_name": workflow.name,
                        "status": run.status.value,
                        "node_count": len(run.nodes),
                        "error": run.error,
                        "context": run.context,
                    },
                )
            )
        except Exception as exc:
            logger.debug("Event store unavailable: %s", exc)

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(
        self, workflow_id: Optional[str] = None
    ) -> List[WorkflowRun]:
        with self._lock:
            if workflow_id:
                return [
                    r for r in self._runs.values()
                    if r.workflow_id == workflow_id
                ]
            return list(self._runs.values())

    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            if run.status in (WorkflowStatus.SUCCEEDED, WorkflowStatus.CANCELLED):
                return False
            run.status = WorkflowStatus.CANCELLED
            run.completed_at = time.time()
            for node in run.nodes.values():
                if node.status == NodeStatus.RUNNING:
                    node.status = NodeStatus.CANCELLED
            return True

    def build_workflow(
        self,
        name: str,
        description: str = "",
        **kwargs: Any,
    ) -> Workflow:
        """Helper: create a new workflow stub."""
        return Workflow(
            workflow_id=str(uuid.uuid4()),
            name=name,
            description=description,
            config=kwargs,
        )

    @staticmethod
    def add_node(workflow: Workflow, node: WorkflowNode) -> None:
        """Add a node to a workflow."""
        workflow.nodes[node.id] = node

    @staticmethod
    def add_edge(workflow: Workflow, edge: WorkflowEdge) -> None:
        """Add an edge to a workflow."""
        workflow.edges.append(edge)

    @staticmethod
    def set_start_nodes(workflow: Workflow, node_ids: List[str]) -> None:
        """Set the start nodes for a workflow."""
        workflow.start_nodes = node_ids

    @staticmethod
    def set_end_nodes(workflow: Workflow, node_ids: List[str]) -> None:
        """Set the end nodes for a workflow."""
        workflow.end_nodes = node_ids


workflow_engine = WorkflowEngine.get_instance()


def define_workflow(
    name: str,
    description: str = "",
    **kwargs: Any,
) -> Workflow:
    """Convenience: create a workflow definition."""
    return Workflow(
        workflow_id=str(uuid.uuid4()),
        name=name,
        description=description,
        config=kwargs,
    )
