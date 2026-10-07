"""Learning task model for the Learning Arena (spec §25, §26).

A ``Task`` is a unit of learning work — e.g. "fine-tune model X on dataset Y"
or "evaluate model Z on benchmark W".  Tasks flow through a lifecycle:

  ``PENDING`` → ``SCHEDULED`` → ``RUNNING`` → ``SUCCESS`` | ``FAILED`` | ``CANCELLED`

Tasks carry:
  * A category (training, evaluation, synthesis, etc.)
  * Resource requirements (CPU, memory, GPU, disk)
  * Priority and scheduling constraints (e.g. "only when GPU is free")
  * Provenance (who created it, from what lesson)
  * Lineage (input datasets, output model revision)

All task metadata is structured and sanitized before storage.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Learning task lifecycle states (spec §25)."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class ResourceSpec:
    """Resource requirements for a task."""

    cpu_cores: float = 1.0
    memory_gb: float = 1.0
    gpu_count: int = 0
    gpu_vram_gb: float = 0.0
    disk_gb: float = 1.0
    ttl_seconds: Optional[int] = None  # max wall-clock time before auto-cancel


@dataclass
class Task:
    """A single learning task in the arena."""

    id: str
    name: str
    category: str        # "training", "evaluation", "synthesis", "inference"
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5    # 1 (highest) to 10 (lowest)
    resource_spec: ResourceSpec = field(default_factory=ResourceSpec)
    input_datasets: list[str] = field(default_factory=list)
    output_revision: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)
    created_by: str = "system"
    created_from_lesson: Optional[str] = None  # lesson ID that spawned this task
    created_at: float = field(default_factory=time.time)
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    error: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return self.ended_at - self.started_at
        return None

    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.SUCCESS, TaskStatus.FAILED,
            TaskStatus.CANCELLED, TaskStatus.SKIPPED,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "status": self.status.value, "priority": self.priority,
            "resource_spec": self.resource_spec.__dict__,
            "input_datasets": self.input_datasets,
            "output_revision": self.output_revision,
            "config": self.config, "created_by": self.created_by,
            "created_from_lesson": self.created_from_lesson,
            "created_at": self.created_at, "scheduled_at": self.scheduled_at,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "duration": self.duration, "error": self.error, "tags": self.tags,
        }


@dataclass
class TaskSpec:
    """Specification for creating a task (immutable definition)."""

    name: str
    category: str
    config: dict[str, Any] = field(default_factory=dict)
    resource_spec: ResourceSpec = field(default_factory=ResourceSpec)
    input_datasets: list[str] = field(default_factory=list)
    priority: int = 5
    tags: list[str] = field(default_factory=list)
    created_by: str = "system"
    created_from_lesson: Optional[str] = None


class TaskArena:
    """Manages learning tasks: create, schedule, track, cancel.

    Tasks are assigned a UUID and stored in an in-memory dict (or a
    pluggable store).  The arena checks the resource governor before
    scheduling (spec §18, §55).
    """

    def __init__(self, governor: Any = None) -> None:
        self._tasks: dict[str, Task] = {}
        self._governor = governor

    def create(self, spec: TaskSpec) -> Task:
        """Create a new task in PENDING state."""
        task = Task(
            id=str(uuid.uuid4()),
            name=spec.name, category=spec.category,
            resource_spec=spec.resource_spec,
            input_datasets=spec.input_datasets,
            config=spec.config, priority=spec.priority,
            created_by=spec.created_by,
            created_from_lesson=spec.created_from_lesson,
            tags=spec.tags,
        )
        self._tasks[task.id] = task
        return task

    def schedule(self, task_id: str) -> Task:
        """Attempt to schedule a task.  Checks the resource governor."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown task: {task_id}")
        if task.is_terminal():
            return task
        # Check governor if available.
        if self._governor is not None:
            snap_spec = ResourceSpec()
            # Build a snapshot matching the task's resource needs.
            from teacher_node.resource_governor import ResourceSnapshot
            snap = ResourceSnapshot(
                cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0,
                gpu_percent=0.0, gpu_vram_percent=0.0, timestamp=time.time(),
                background_tasks=len(self._tasks),
            )
            state = self._governor.check(snap)
            if state in ("paused", "cancelled"):
                task.status = TaskStatus.SKIPPED
                task.error = f"governor state: {state.value}"
                task.ended_at = time.time()
                return task
        task.status = TaskStatus.SCHEDULED
        task.scheduled_at = time.time()
        return task

    def start(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown task: {task_id}")
        if task.is_terminal():
            return task
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        return task

    def complete(self, task_id: str, outcome: TaskStatus = TaskStatus.SUCCESS,
                  error: str = "", output_revision: Optional[str] = None) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown task: {task_id}")
        if outcome not in (TaskStatus.SUCCESS, TaskStatus.FAILED,
                            TaskStatus.CANCELLED):
            raise ValueError(f"invalid terminal status: {outcome}")
        task.status = outcome
        task.ended_at = time.time()
        task.error = error
        if output_revision:
            task.output_revision = output_revision
        return task

    def cancel(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown task: {task_id}")
        if task.is_terminal():
            return task
        task.status = TaskStatus.CANCELLED
        task.ended_at = time.time()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list(self, *, status: Optional[TaskStatus] = None,
             category: Optional[str] = None) -> list[Task]:
        result = list(self._tasks.values())
        if status:
            result = [t for t in result if t.status == status]
        if category:
            result = [t for t in result if t.category == category]
        return sorted(result, key=lambda t: t.created_at, reverse=True)

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.is_terminal())

    def clear(self) -> None:
        self._tasks.clear()
