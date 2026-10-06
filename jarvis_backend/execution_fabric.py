"""Universal Agentic Execution Fabric - Phase 7 Implementation.

Turns requests into execution graphs with proper verification, recovery,
and idempotency.

Architecture:

    REQUEST
      ↓
    INTEND        (discover_capabilities → capability selection)
      ↓
    TASK          (lifecycle states, idempotent, checkpointed)
      ↓
    PLAN          (ExecutionGraph — DAG of capability nodes)
      ↓
    NODE          (capability invocation via ToolRegistry)
      ↓
    EXECUTION     (authorize → invoke → scrub → capture result)
      ↓
    RETRY/RECOVERY (bounded backoff by FailureClass)
      ↓
    VERIFICATION  (VerificationEngine)
      ↓
    EVIDENCE / ARTIFACTS
      ↓
    MEMORY / LEARNING

Design principles
-----------------
* Reuses the EXISTING ToolRegistry authorization + secret-scrubbing boundary.
* Reuses the EXISTING discover_capabilities() for capability discovery.
* Reuses the EXISTING VerificationEngine for claim verification.
* Reuses the EXISTING get_store("tasks") for persistent task state.
* Never fabricates execution results — a node that cannot run is FAILED,
  not silently skipped with a fabricated success.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso

logger = logging.getLogger("jarvis_backend.execution_fabric")


# =============================================================================
# Failure Classification for Retry/Recovery
# =============================================================================

class FailureClass(str, Enum):
    """Failure classifications that determine retry behavior."""

    TRANSIENT = "TRANSIENT"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"

    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"

    INVALID_INPUT = "INVALID_INPUT"
    CAPABILITY_FAILURE = "CAPABILITY_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"

    PERMANENT = "PERMANENT"


_RETRYABLE = frozenset({
    FailureClass.TRANSIENT,
    FailureClass.RATE_LIMITED,
    FailureClass.NETWORK_FAILURE,
    FailureClass.PROVIDER_UNAVAILABLE,
    FailureClass.RESOURCE_UNAVAILABLE,
})


def should_retry(failure_class: FailureClass, attempt: int,
                 max_attempts: int = 5) -> bool:
    """Return True when ``failure_class`` is retryable and attempts remain."""
    return attempt < max_attempts and failure_class in _RETRYABLE


def get_backoff_delay(attempt: int, base: float = 1.0,
                      max_delay: float = 60.0) -> float:
    """Exponential backoff with jitter."""
    import random
    delay = min(base * (2 ** (attempt - 1)), max_delay)
    return delay * (0.5 + random.random() * 0.5)


# =============================================================================
# Execution Node Model (DAG Structure)
# =============================================================================

class ExecutionNodeStatus(str, Enum):
    """Status of an execution node in the graph."""
    PENDING = "PENDING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"


# Node statuses that count as terminal (no further execution).
_TERMINAL_NODE_STATUSES = frozenset({
    ExecutionNodeStatus.COMPLETED,
    ExecutionNodeStatus.FAILED,
    ExecutionNodeStatus.SKIPPED,
    ExecutionNodeStatus.VERIFIED,
    ExecutionNodeStatus.CANCELLED,
})

# Node statuses that count as "done" for dependency scheduling.
_DONE_NODE_STATUSES = frozenset({
    ExecutionNodeStatus.COMPLETED,
    ExecutionNodeStatus.VERIFIED,
})


@dataclass
class ExecutionNode:
    """A node in the execution graph (a single capability invocation)."""

    node_id: str
    task_id: str
    capability: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Optional[dict[str, Any]] = None
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    status: ExecutionNodeStatus = ExecutionNodeStatus.PENDING
    attempt: int = 0
    max_attempts: int = 5
    retry_policy: str = "none"
    timeout: int = 30
    idempotency_key: Optional[str] = None
    authorization_required: bool = True
    risk_level: str = "read"
    artifact_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None
    failure_class: Optional[FailureClass] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    verified: bool = False
    verification_result: Optional[dict[str, Any]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    retry_history: list[dict[str, Any]] = field(default_factory=list)
    updated: float = field(default_factory=time.time)

    def is_ready(self, completed: set[str]) -> bool:
        """True when all dependencies are done (or no dependencies)."""
        if not self.dependencies:
            return True
        return all(dep in completed for dep in self.dependencies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "task_id": self.task_id,
            "capability": self.capability,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "status": self.status.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "retry_policy": self.retry_policy,
            "timeout": self.timeout,
            "idempotency_key": self.idempotency_key,
            "authorization_required": self.authorization_required,
            "risk_level": self.risk_level,
            "artifact_ids": list(self.artifact_ids),
            "error": self.error,
            "failure_class": (self.failure_class.value
                              if self.failure_class else None),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "verified": self.verified,
            "verification_result": self.verification_result,
            "provider": self.provider,
            "model": self.model,
            "retry_history": list(self.retry_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionNode":
        fc = None
        if data.get("failure_class"):
            try:
                fc = FailureClass(data["failure_class"])
            except ValueError:
                fc = None
        try:
            status = ExecutionNodeStatus(data.get("status", "PENDING"))
        except ValueError:
            status = ExecutionNodeStatus.PENDING
        return cls(
            node_id=data["node_id"],
            task_id=data["task_id"],
            capability=data["capability"],
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs"),
            dependencies=list(data.get("dependencies", [])),
            dependents=list(data.get("dependents", [])),
            status=status,
            attempt=data.get("attempt", 0),
            max_attempts=data.get("max_attempts", 5),
            retry_policy=data.get("retry_policy", "none"),
            timeout=data.get("timeout", 30),
            idempotency_key=data.get("idempotency_key"),
            authorization_required=data.get("authorization_required", True),
            risk_level=data.get("risk_level", "read"),
            artifact_ids=list(data.get("artifact_ids", [])),
            error=data.get("error"),
            failure_class=fc,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            verified=data.get("verified", False),
            verification_result=data.get("verification_result"),
            provider=data.get("provider"),
            model=data.get("model"),
            retry_history=list(data.get("retry_history", [])),
            updated=data.get("updated", time.time()),
        )


# =============================================================================
# Execution Graph (DAG)
# =============================================================================

@dataclass
class GraphEdge:
    """An edge in the DAG: ``from_node`` → ``to_node``."""
    from_node: str
    to_node: str

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.from_node, "to": self.to_node}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        return cls(from_node=data["from"], to_node=data["to"])


class ExecutionGraph:
    """A directed acyclic graph of execution nodes for one task.

    Nodes are executed in dependency order. The graph is checkpointed via
    ``to_dict`` / ``from_dict`` so it can be resumed after a crash.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.nodes: dict[str, ExecutionNode] = {}
        self.edges: list[GraphEdge] = []
        self.root_nodes: list[str] = []
        self.leaf_nodes: list[str] = []
        self.created_at = time.time()
        self.updated_at = time.time()

    def add_node(self, node: ExecutionNode) -> "ExecutionGraph":
        self.nodes[node.node_id] = node
        self.updated_at = time.time()
        for dep_id in node.dependencies:
            if dep_id in self.nodes:
                if node.node_id not in self.nodes[dep_id].dependents:
                    self.nodes[dep_id].dependents.append(node.node_id)
        self._recompute_roots_leaves()
        return self

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a dependency edge: ``from_node`` must complete before ``to_node``."""
        edge = GraphEdge(from_node=from_node, to_node=to_node)
        self.edges.append(edge)
        to_node_obj = self.nodes.get(to_node)
        from_node_obj = self.nodes.get(from_node)
        if to_node_obj and from_node_obj:
            if from_node not in to_node_obj.dependencies:
                to_node_obj.dependencies.append(from_node)
            if to_node not in from_node_obj.dependents:
                from_node_obj.dependents.append(to_node)
        self._recompute_roots_leaves()
        self.updated_at = time.time()

    def _recompute_roots_leaves(self) -> None:
        if not self.nodes:
            self.root_nodes = []
            self.leaf_nodes = []
            return
        node_ids = set(self.nodes)
        self.root_nodes = sorted(
            nid for nid in node_ids if not self.nodes[nid].dependencies
        )
        self.leaf_nodes = sorted(
            nid for nid in node_ids if not self.nodes[nid].dependents
        )

    def get_ready_nodes(self) -> list[ExecutionNode]:
        """Return nodes whose dependencies are all completed and that are not
        already in a terminal or running state."""
        completed = self._completed_ids()
        ready: list[ExecutionNode] = []
        for node in self.nodes.values():
            if node.status in _TERMINAL_NODE_STATUSES:
                continue
            if node.status == ExecutionNodeStatus.RUNNING:
                continue
            if node.status == ExecutionNodeStatus.RETRYING:
                continue
            if node.status == ExecutionNodeStatus.WAITING_FOR_USER:
                continue
            if not node.is_ready(completed):
                continue
            ready.append(node)
        return ready

    def get_running_nodes(self) -> list[ExecutionNode]:
        return [n for n in self.nodes.values()
                if n.status == ExecutionNodeStatus.RUNNING]

    def _completed_ids(self) -> set[str]:
        return {nid for nid, n in self.nodes.items()
                if n.status in _DONE_NODE_STATUSES}

    def _failed_ids(self) -> set[str]:
        return {nid for nid, n in self.nodes.items()
                if n.status == ExecutionNodeStatus.FAILED}

    def has_active_work(self) -> bool:
        """True if any node is running, retrying, or could still run."""
        for node in self.nodes.values():
            if node.status in (ExecutionNodeStatus.RUNNING,
                               ExecutionNodeStatus.RETRYING):
                return True
        return bool(self.get_ready_nodes())

    def mark_node(
        self,
        node_id: str,
        status: ExecutionNodeStatus,
        outputs: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        failure_class: Optional[FailureClass] = None,
    ) -> None:
        """Transition a node to ``status`` and update bookkeeping."""
        node = self.nodes.get(node_id)
        if node is None:
            return
        node.status = status
        node.updated = time.time()
        if outputs is not None:
            node.outputs = outputs
        if error is not None:
            node.error = error
        if failure_class is not None:
            node.failure_class = failure_class
        if status in _DONE_NODE_STATUSES:
            node.completed_at = time.time()
        self.updated_at = time.time()

    def mark_completed(self, node_id: str,
                       result: Optional[dict[str, Any]] = None) -> None:
        self.mark_node(node_id, ExecutionNodeStatus.COMPLETED,
                       outputs=result)

    def mark_failed(self, node_id: str, error: str,
                    failure_class: FailureClass) -> None:
        self.mark_node(node_id, ExecutionNodeStatus.FAILED,
                       error=error, failure_class=failure_class)

    def mark_skipped(self, node_id: str) -> None:
        """Skip a node because a dependency failed."""
        self.mark_node(node_id, ExecutionNodeStatus.SKIPPED,
                       error="dependency failed")

    def skip_dependent_of(self, node_id: str) -> set[str]:
        """Cascading skip: mark ``node_id`` and all its downstream nodes FAILED."""
        skipped: set[str] = set()
        queue = [node_id]
        while queue:
            cur = queue.pop()
            if cur in skipped or cur not in self.nodes:
                continue
            n = self.nodes[cur]
            if n.status in _TERMINAL_NODE_STATUSES:
                continue
            n.status = ExecutionNodeStatus.FAILED
            n.error = f"skipped: dependency chain broken at {node_id}"
            n.failure_class = FailureClass.CAPABILITY_FAILURE
            n.completed_at = time.time()
            skipped.add(cur)
            queue.extend(n.dependents)
        self.updated_at = time.time()
        return skipped

    def progress(self) -> dict[str, Any]:
        """Summary of graph progress."""
        counts: dict[str, int] = {}
        for n in self.nodes.values():
            counts[n.status.value] = counts.get(n.status.value, 0) + 1
        total = len(self.nodes)
        done = sum(counts.get(s, 0) for s in ("COMPLETED", "VERIFIED"))
        failed = counts.get("FAILED", 0) + counts.get("CANCELLED", 0)
        skipped = counts.get("SKIPPED", 0)
        return {
            "total_nodes": total,
            "completed": done,
            "failed": failed,
            "skipped": skipped,
            "status_counts": counts,
            "progress": (done / total) if total else 0.0,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "root_nodes": list(self.root_nodes),
            "leaf_nodes": list(self.leaf_nodes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionGraph":
        graph = cls(task_id=data["task_id"])
        for nid, ndata in data.get("nodes", {}).items():
            node = ExecutionNode.from_dict(ndata)
            graph.nodes[node.node_id] = node
        for edata in data.get("edges", []):
            graph.edges.append(GraphEdge.from_dict(edata))
        graph.root_nodes = list(data.get("root_nodes", []))
        graph.leaf_nodes = list(data.get("leaf_nodes", []))
        graph.created_at = data.get("created_at", time.time())
        graph.updated_at = data.get("updated_at", time.time())
        return graph


# =============================================================================
# Task Model with Full Lifecycle
# =============================================================================

class TaskStatus(str, Enum):
    """Full lifecycle states for a task."""
    RECEIVED = "RECEIVED"
    UNDERSTOOD = "UNDERSTOOD"
    PLANNED = "PLANNED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """A task in the agentic execution fabric — persisted via get_store."""

    task_id: str
    intent: str
    user_id: str
    status: TaskStatus = TaskStatus.RECEIVED
    priority: TaskPriority = TaskPriority.NORMAL
    plan: Optional[ExecutionGraph] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    execution_mode: str = "online"
    verification_required: bool = False
    result: Optional[dict[str, Any]] = None
    evidence: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "intent": self.intent,
            "user_id": self.user_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "request_id": self.request_id,
            "execution_mode": self.execution_mode,
            "verification_required": self.verification_required,
            "result": self.result,
            "evidence": list(self.evidence),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        plan = None
        if data.get("plan"):
            plan = ExecutionGraph.from_dict(data["plan"])
        try:
            status = TaskStatus(data.get("status", "RECEIVED"))
        except ValueError:
            status = TaskStatus.RECEIVED
        try:
            priority = TaskPriority(data.get("priority", "normal"))
        except ValueError:
            priority = TaskPriority.NORMAL
        return cls(
            task_id=data["task_id"],
            intent=data["intent"],
            user_id=data["user_id"],
            status=status,
            priority=priority,
            plan=plan,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            request_id=data.get("request_id"),
            execution_mode=data.get("execution_mode", "online"),
            verification_required=data.get("verification_required", False),
            result=data.get("result"),
            evidence=list(data.get("evidence", [])),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=dict(data.get("metadata", {})),
        )

    def save(self) -> None:
        """Checkpoint this task to the persistent task store."""
        store = get_store("tasks")
        tasks = store.load()
        tasks[self.task_id] = self.to_dict()
        store.save()

    @staticmethod
    def load(task_id: str) -> Optional["Task"]:
        """Load a task from the persistent store, or None if not found."""
        store = get_store("tasks")
        tasks = store.reload()
        raw = tasks.get(task_id)
        if raw is None:
            return None
        return Task.from_dict(raw)


# =============================================================================
# Agent Executor
# =============================================================================

class AgentExecutor:
    """Canonical agent executor for the execution fabric.

    Integrates with the EXISTING ToolRegistry, discover_capabilities(),
    VerificationEngine, and get_store() for persistence.

    Responsibilities:
      - Intent → capability discovery → ExecutionGraph (DAG) construction
      - Authorization of every node through ToolRegistry.authorize()
      - Execution of nodes via ToolRegistry.invoke() (which scrubs secrets)
      - Bounded-retry with backoff based on FailureClass
      - Checkpointing / resumption via get_store("tasks")
      - Idempotency keys per capability invocation
      - WAITING_FOR_USER approval for high-risk nodes
      - Verification of completed graph
    """

    def __init__(self, tool_registry=None, verifier=None,
                 max_concurrency: int = 4):
        """Initialize the agent executor.

        Args:
            tool_registry: ToolRegistry for executing capabilities.
                If None, a default registry is built from capability_tools.
            verifier: VerificationEngine for final verification.
                If None, a default one is constructed.
            max_concurrency: max parallel nodes.
        """
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            from research_engine.capability_tools import build_capability_registry

            self.tool_registry = build_capability_registry()
        self.max_concurrency = max_concurrency

        if verifier is not None:
            self.verifier = verifier
        else:
            from research_engine.verification import VerificationEngine

            self.verifier = VerificationEngine()

        self._executions: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Task persistence
    # ------------------------------------------------------------------ #

    def save_task(self, task: Task) -> None:
        task.updated_at = time.time()
        task.save()
        logger.debug("task %s checkpointed: status=%s", task.task_id,
                     task.status.value)

    def load_task(self, task_id: str) -> Optional[Task]:
        return Task.load(task_id)

    def _record_execution(self, event_type: str, task_id: str,
                          data: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "task_id": task_id,
            "timestamp": now_iso(),
            "data": data,
        }
        self._executions.append(event)
        store = get_store("executions")
        items = store.load()
        items.append(event)
        store.save()

    def register_observer(self, callback: Any) -> None:
        """Register a callback for execution events (currently best-effort)."""
        # The executor records all events to the executions store; observers
        # can read from there or be wired in here.
        logger.debug("observer registered (recorded to executions store)")

    # ------------------------------------------------------------------ #
    # Capability discovery → graph construction
    # ------------------------------------------------------------------ #

    def discover(self, intent: str, *, mode: str = "online",
                 include_unavailable: bool = False) -> list[str]:
        """Ask discover_capabilities() which capabilities suit ``intent``.

        Returns a list of capability names, ranked best-first.
        """
        from research_engine.capability_contract import discover_capabilities

        results = discover_capabilities(
            intent, mode=mode,
            include_unavailable=include_unavailable,
        )
        return [c["name"] for c in results.get("capabilities", [])]

    def build_execution_graph(
        self,
        intent: str,
        capabilities: Optional[list[str]] = None,
        *,
        task_id: Optional[str] = None,
        mode: str = "online",
        execution_mode: str = "online",
        user_id: str = "anonymous",
        confirmations: Optional[dict[str, bool]] = None,
        claim: Optional[str] = None,
    ) -> tuple[Task, ExecutionGraph]:
        """Build a Task + ExecutionGraph from an intent.

        If ``capabilities`` is provided it is used as-is; otherwise
        discover_capabilities() resolves them from the intent.

        The graph is a flat DAG of capability nodes (dependencies can be added
        by the caller before ``execute_task`` is invoked). Each node is
        authorized through the ToolRegistry at execution time.
        """
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        if capabilities is None:
            capabilities = self.discover(intent, mode=mode)

        graph = ExecutionGraph(task_id)
        confirmations = confirmations or {}

        # Resolve contracts once to populate node metadata.
        contracts: dict[str, dict] = {}
        try:
            from research_engine.capability_contract import build_contracts

            contracts = build_contracts(self.tool_registry)
        except Exception:  # noqa: BLE001
            pass

        for i, cap in enumerate(capabilities):
            contract = contracts.get(cap, {})
            node = ExecutionNode(
                node_id=f"node_{i}",
                task_id=task_id,
                capability=cap,
                inputs={},
                dependencies=[],
                risk_level=contract.get("risk_level", "read"),
                retry_policy=contract.get("retry_policy", "none"),
                timeout=contract.get("timeout", 30),
                idempotency_key=f"{task_id}:{cap}:{uuid.uuid4().hex[:8]}",
                max_attempts=(5 if contract.get("retry_policy") in
                              ("backoff_1", "backoff_2") else 1),
                authorization_required=contract.get(
                    "authentication_required", True),
            )
            # NETWORK / ADMIN risk levels require confirmation.
            if node.risk_level in ("network", "admin"):
                confirmed = confirmations.get(
                    f"{user_id}:{cap}", False)
                if not confirmed:
                    node.status = ExecutionNodeStatus.WAITING_FOR_USER
            graph.add_node(node)

        # Compute roots/leaves.
        graph._recompute_roots_leaves()

        task = Task(
            task_id=task_id,
            intent=intent,
            user_id=user_id,
            status=TaskStatus.PLANNED,
            plan=graph,
            execution_mode=execution_mode,
            metadata={
                "capabilities": list(capabilities),
                "mode": mode,
                "claim": claim or intent,
            },
        )
        return task, graph

    # ------------------------------------------------------------------ #
    # Node execution
    # ------------------------------------------------------------------ #

    async def execute_node(
        self,
        node: ExecutionNode,
        task: Task,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a single node through the ToolRegistry boundary."""
        # Idempotency: if already completed, return cached output.
        if node.status in _DONE_NODE_STATUSES and node.outputs is not None:
            return {"success": True, "output": node.outputs,
                    "source": "checkpoint"}

        # Authorization.
        if node.authorization_required or node.risk_level in ("network", "admin"):
            ok, reason = self.tool_registry.authorize(
                task.user_id, node.capability,
                permissions=permissions, principal=principal)
            if not ok:
                node.status = ExecutionNodeStatus.FAILED
                node.error = f"TOOL_DENIED: {reason}"
                node.failure_class = FailureClass.AUTHORIZATION_FAILURE
                node.completed_at = time.time()
                self._record_execution("NODE_DENIED", task.task_id, {
                    "node_id": node.node_id,
                    "capability": node.capability,
                    "reason": reason,
                })
                return {"success": False,
                        "error": f"TOOL_DENIED: {reason}",
                        "failure_class": FailureClass.AUTHORIZATION_FAILURE.value}

        node.status = ExecutionNodeStatus.AUTHORIZED
        node.attempt += 1
        node.started_at = time.time()

        # Build ToolContext for the registry (it resolves secrets internally).
        from research_engine.tool_registry import ToolContext

        ctx = ToolContext(
            request_id=node.idempotency_key or node.node_id,
            user_id=task.user_id,
            permissions=permissions,
            principal=principal,
        )

        try:
            timeout = min(node.timeout, 120)
            result = await asyncio.wait_for(
                self.tool_registry.invoke(node.capability, node.inputs, ctx),
                timeout=timeout)
        except asyncio.TimeoutError:
            node.failure_class = FailureClass.TRANSIENT
            node.error = f"timeout after {timeout}s"
            self._record_execution("NODE_TIMEOUT", task.task_id, {
                "node_id": node.node_id,
                "capability": node.capability,
            })
        except Exception as exc:  # noqa: BLE001
            node.failure_class = FailureClass.TRANSIENT
            node.error = f"{type(exc).__name__}: {exc}"
            self._record_execution("NODE_ERROR", task.task_id, {
                "node_id": node.node_id,
                "capability": node.capability,
            })
        else:
            # Map ToolResult → node output.
            if result.success:
                node.outputs = {
                    "result": result.result,
                    "metrics": dict(result.metrics),
                    "artifacts": [dict(a) for a in result.artifacts],
                    "redacted_secrets": result.redacted_secrets,
                }
                node.provider = result.metrics.get("provider")
                node.completed_at = time.time()
                self._record_execution("NODE_COMPLETED", task.task_id, {
                    "node_id": node.node_id,
                    "capability": node.capability,
                    "duration_ms": round(result.duration_ms, 2),
                })
                return {"success": True, "output": node.outputs}
            else:
                node.failure_class = self._classify_failure(result.error)
                node.error = result.error
                self._record_execution("NODE_FAILED", task.task_id, {
                    "node_id": node.node_id,
                    "capability": node.capability,
                    "error": result.error,
                })

        # If we reach here, the node failed.
        if node.failure_class is None:
            node.failure_class = FailureClass.TRANSIENT
        node.status = ExecutionNodeStatus.FAILED
        self.save_task(task)
        return {"success": False,
                "error": node.error or "unknown error",
                "failure_class": (node.failure_class.value
                                  if node.failure_class else None)}

    def _classify_failure(self, error: str) -> FailureClass:
        """Classify an error string into a FailureClass for retry policy."""
        if not error:
            return FailureClass.TRANSIENT
        low = error.lower()
        if "tool_denied" in low or "permission_denied" in low or "requires_user_confirmation" in low:
            return FailureClass.AUTHORIZATION_FAILURE
        if "rate limit" in low or "429" in low or "too many requests" in low:
            return FailureClass.RATE_LIMITED
        if "timeout" in low:
            return FailureClass.TRANSIENT
        if "unavailable" in low or "503" in low:
            return FailureClass.PROVIDER_UNAVAILABLE
        if "network" in low or "connection" in low or "dns" in low:
            return FailureClass.NETWORK_FAILURE
        if "invalid_request" in low or "validation" in low:
            return FailureClass.INVALID_INPUT
        return FailureClass.TRANSIENT

    # ------------------------------------------------------------------ #
    # Retry wrapper
    # ------------------------------------------------------------------ #

    async def _execute_with_retry(
        self,
        node: ExecutionNode,
        task: Task,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, Optional[dict[str, Any]]]:
        """Execute ``node`` with retry according to its retry policy.

        Returns (success, outputs).
        """
        max_attempts = max(node.max_attempts, 1)
        while True:
            node.status = (ExecutionNodeStatus.RETRYING if node.attempt > 0
                           else ExecutionNodeStatus.RUNNING)
            result = await self.execute_node(
                node, task, permissions=permissions, principal=principal)

            if result["success"]:
                node.status = ExecutionNodeStatus.COMPLETED
                node.completed_at = time.time()
                return True, result["output"]

            failure_class = FailureClass(result.get("failure_class") or "TRANSIENT")
            node.failure_class = failure_class

            if not should_retry(failure_class, node.attempt, max_attempts):
                # Exhausted retries — permanent failure.
                node.status = ExecutionNodeStatus.FAILED
                node.completed_at = time.time()
                self.save_task(task)
                return False, None

            # Retryable: back off and loop.
            delay = get_backoff_delay(node.attempt)
            node.retry_history.append({
                "attempt": node.attempt,
                "error": node.error,
                "failure_class": failure_class.value,
                "retry_at": time.time() + delay,
            })
            node.status = ExecutionNodeStatus.RETRYING
            self.save_task(task)
            await asyncio.sleep(delay)

    # ------------------------------------------------------------------ #
    # Top-level task execution
    # ------------------------------------------------------------------ #

    async def execute_task(
        self,
        task: Task,
        *,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute all nodes in the task's execution graph (DAG).

        Nodes are scheduled in topological order, respecting dependencies and
        authorization. High-risk nodes that require confirmation are held in
        WAITING_FOR_USER until ``approve_node`` is called.
        """
        if task.plan is None:
            return {"success": False, "error": "no execution plan"}

        self.save_task(task)
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or time.time()
        self._record_execution("TASK_STARTED", task.task_id,
                               {"status": task.status.value})

        pending_approval = [
            nid for nid, n in task.plan.nodes.items()
            if n.status == ExecutionNodeStatus.WAITING_FOR_USER
        ]

        if pending_approval:
            task.status = TaskStatus.WAITING_FOR_USER
            self.save_task(task)
            self._record_execution("TASK_WAITING_FOR_USER", task.task_id,
                                   {"nodes": pending_approval})
            return {
                "success": False,
                "status": task.status.value,
                "waiting_for_user": True,
                "pending_nodes": pending_approval,
            }

        # Main scheduling loop.
        while task.plan.has_active_work():
            ready = task.plan.get_ready_nodes()
            if not ready:
                # Nothing ready and nothing running → done (or all blocked).
                break

            # Execute ready nodes concurrently (bounded).
            running = task.plan.get_running_nodes()
            slots = self.max_concurrency - len(running)
            batch = ready[:max(slots, 0)]

            coros = [
                self._execute_with_retry(
                    n, task, permissions=permissions, principal=principal)
                for n in batch
            ]
            results = await asyncio.gather(*coros, return_exceptions=True)

            for node, res in zip(batch, results):
                if isinstance(res, Exception):
                    node.status = ExecutionNodeStatus.FAILED
                    node.error = f"{type(res).__name__}: {res}"
                    node.failure_class = FailureClass.PERMANENT
                    node.completed_at = time.time()
                    self.plan_failed_dependents(task, node.node_id)
                elif not res[0]:
                    # Retry-exhausted failure.
                    self.plan_failed_dependents(task, node.node_id)
                # On success, node is already COMPLETED.

            self.save_task(task)

        # Determine terminal task status.
        done = task.plan.progress()
        if done["failed"] > 0 and done["completed"] > 0:
            task.status = TaskStatus.PARTIAL
        elif done["failed"] > 0:
            task.status = TaskStatus.FAILED
            task.error = f"{done['failed']} node(s) failed"
        elif done["completed"] == done["total_nodes"]:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.FAILED
            task.error = "execution did not complete all nodes"

        task.completed_at = time.time()
        task.result = {
            "progress": done,
            "outputs": {
                nid: n.outputs
                for nid, n in task.plan.nodes.items()
                if n.status in _DONE_NODE_STATUSES and n.outputs
            },
        }

        # Verify if requested.
        if task.verification_required:
            await self._verify_task(task)

        self.save_task(task)
        self._record_execution("TASK_COMPLETED", task.task_id, {
            "status": task.status.value,
            "progress": done,
        })
        return {
            "success": task.status in (TaskStatus.COMPLETED,
                                       TaskStatus.PARTIAL,
                                       TaskStatus.VERIFIED),
            "task_status": task.status.value,
            "progress": done,
            "result": task.result,
        }

    def plan_failed_dependents(self, task: Task, node_id: str) -> None:
        """Cascade-skip all downstream nodes of a failed node."""
        skipped = task.plan.skip_dependent_of(node_id)
        if skipped:
            self._record_execution("NODE_CASCADE_SKIP", task.task_id,
                                   {"skipped": sorted(skipped)})

    # ------------------------------------------------------------------ #
    # Human-in-the-loop approval
    # ------------------------------------------------------------------ #

    def approve_node(self, task_id: str, node_id: str,
                     approved: bool = True) -> dict[str, Any]:
        """Approve or reject a WAITING_FOR_USER node.

        If approved, the node transitions to PENDING and becomes eligible for
        scheduling on the next ``execute_task`` call.
        If rejected, the node and its dependents are FAILED.
        """
        task = Task.load(task_id)
        if task is None or task.plan is None:
            return {"error": "task not found"}
        node = task.plan.nodes.get(node_id)
        if node is None:
            return {"error": "node not found"}
        if node.status != ExecutionNodeStatus.WAITING_FOR_USER:
            return {"error": f"node not waiting (status={node.status.value})"}
        if approved:
            node.status = ExecutionNodeStatus.PENDING
            task.status = TaskStatus.RUNNING
            self.save_task(task)
            self._record_execution("NODE_APPROVED", task_id,
                                   {"node_id": node_id})
            return {"approved": True, "node_id": node_id}
        else:
            self.plan_failed_dependents(task, node_id)
            self.save_task(task)
            self._record_execution("NODE_REJECTED", task_id,
                                   {"node_id": node_id})
            return {"approved": False, "node_id": node_id,
                    "cascade_failed": sorted(task.plan._failed_ids())}

    # ------------------------------------------------------------------ #
    # Resumption from checkpoint
    # ------------------------------------------------------------------ #

    async def resume(self, task_id: str, *,
                     permissions: Optional[set[str]] = None,
                     principal: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Resume or re-execute a previously checkpointed task.

        - COMPLETED/VERIFIED: returns the existing result (no re-execution).
        - FAILED/PARTIAL/WAITING_FOR_USER/RUNNING: re-executes from the
          last checkpoint, picking up any nodes that were in-flight or
          waiting for approval.
        """
        task = Task.load(task_id)
        if task is None:
            return {"success": False, "error": "task not found"}
        if task.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED):
            return {
                "success": True,
                "status": task.status.value,
                "result": task.result,
                "note": "task already completed; no re-execution",
            }
        return await self.execute_task(task, permissions=permissions,
                                       principal=principal)

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #

    async def _verify_task(self, task: Task) -> None:
        """Run verification on the completed task's results."""
        from research_engine.models import VerificationStatus

        claim = task.metadata.get("claim", task.intent)
        results = []
        for nid, node in task.plan.nodes.items():
            if node.status == ExecutionNodeStatus.COMPLETED and node.outputs:
                results.append(
                    self.verifier.classify_tool_result(
                        node.capability,
                        {"success": True, "output": node.outputs.get("result")},
                    )
                )
        if results and all(
            r in (VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED)
            for r in results
        ):
            task.status = TaskStatus.VERIFIED
            task.metadata["verification"] = "verified"
        elif results and all(
            r == VerificationStatus.FAILED for r in results
        ):
            task.status = TaskStatus.FAILED
            task.metadata["verification"] = "failed"
        else:
            task.metadata["verification"] = "unverified"

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get a serialized view of a task's status."""
        task = self.load_task(task_id)
        if task is None:
            return None
        out = task.to_dict()
        out["graph_progress"] = (task.plan.progress()
                                 if task.plan else {"total_nodes": 0})
        return out


# =============================================================================
# Verification / Evidence-pack helper
# =============================================================================

def build_verified_evidence_pack(
    task: Task,
    tool_registry: Any = None,
) -> dict[str, Any]:
    """Build an evidence pack from a completed task's graph.

    Integrates with the existing VerificationEngine to classify outcomes.
    """
    from research_engine.verification import VerificationEngine
    from research_engine.models import VerificationStatus

    verifier = VerificationEngine()

    executed_nodes = []
    verification_evidence = []
    artifacts = []
    provenance = []

    if task.plan:
        for node_id, node in task.plan.nodes.items():
            if node.status in _DONE_NODE_STATUSES and node.outputs:
                entry = {
                    "node_id": node_id,
                    "capability": node.capability,
                    "provider": node.provider,
                    "model": node.model,
                    "attempt": node.attempt,
                    "duration_ms": (node.completed_at - node.started_at
                                    if node.started_at and node.completed_at
                                    else 0),
                }
                executed_nodes.append(entry)
                artifacts.extend(node.artifact_ids)
                if node.outputs.get("artifacts"):
                    for a in node.outputs["artifacts"]:
                        provenance.append({
                            "node_id": node_id,
                            "capability": node.capability,
                            "source": a.get("source", "") if isinstance(a, dict) else str(a),
                        })
                verification_status = verifier.classify_tool_result(
                    node.capability,
                    {"success": True, "output": node.outputs.get("result", "")},
                )
                verification_evidence.append({
                    "node_id": node_id,
                    "capability": node.capability,
                    "status": verification_status.value,
                })

    if verification_evidence and all(
        e["status"] in ("VERIFIED", "PARTIALLY_VERIFIED")
        for e in verification_evidence
    ):
        overall = VerificationStatus.VERIFIED
    elif any(e["status"] == "FAILED" for e in verification_evidence):
        overall = VerificationStatus.FAILED
    else:
        overall = VerificationStatus.UNVERIFIED

    return {
        "task_id": task.task_id,
        "verification_status": overall.value,
        "executed_nodes": executed_nodes,
        "verification_evidence": verification_evidence,
        "artifacts": artifacts,
        "provenance": provenance,
        "evidence": list(task.evidence),
        "result": task.result,
    }


# =============================================================================
# Module exports
# =============================================================================

__all__ = [
    "FailureClass",
    "should_retry",
    "get_backoff_delay",

    "ExecutionNode",
    "ExecutionNodeStatus",
    "ExecutionGraph",
    "GraphEdge",

    "Task",
    "TaskStatus",
    "TaskPriority",

    "AgentExecutor",
    "build_verified_evidence_pack",
]
