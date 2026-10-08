"""
Task Runtime - Durable agent task management with explicit state machine.

Provides persistent task state, resumable execution, and explicit state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import threading
import logging
import uuid

logger = logging.getLogger("control_plane.task_runtime")


class TaskState(str, Enum):
    """States in the task lifecycle"""
    CREATED = "created"
    AUTHORIZING = "authorizing"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_TOOL = "waiting_tool"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    APPLYING = "applying"
    HEALTH_CHECK = "health_check"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of tasks"""
    CHALLENGE = "challenge"
    RESEARCH = "research"
    CODING = "coding"
    DEBUGGING = "debugging"
    LEARNING = "learning"
    SYSTEM = "system"
    SANDBOX = "sandbox"


@dataclass
class Plan:
    """Execution plan for a task"""
    goal: str
    steps: List[str] = field(default_factory=list)
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": self.steps,
            "current_step": self.current_step,
            "created_at": self.created_at,
        }


@dataclass
class Task:
    """A durable task with full state tracking"""
    task_id: str
    type: TaskType
    instruction: str
    state: TaskState = TaskState.CREATED
    
    # Planning
    plan: Optional[Plan] = None
    current_goal: str = ""
    
    # Execution
    worker_id: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Context
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Results
    result: Optional[str] = None
    result_details: Dict[str, Any] = field(default_factory=dict)
    
    # Tool execution
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    pending_tool: Optional[str] = None
    tool_responses: List[Dict[str, Any]] = field(default_factory=list)
    
    # Change sets
    proposed_changes: List[str] = field(default_factory=list)  # ChangeSet IDs
    applied_changes: List[str] = field(default_factory=list)
    pending_approval: Optional[str] = None  # ChangeSet ID needing approval
    
    # Errors and recovery
    error: Optional[str] = None
    error_trace: Optional[str] = None
    retry_count: int = 0
    checkpoint: Optional[Dict[str, Any]] = None
    
    # Observability
    started_execution_at: Optional[float] = None
    last_updated: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "type": self.type.value,
            "instruction": self.instruction,
            "state": self.state.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "current_goal": self.current_goal,
            "worker_id": self.worker_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "result": self.result,
            "result_details": self.result_details,
            "tool_results": self.tool_results,
            "pending_tool": self.pending_tool,
            "tool_responses": self.tool_responses,
            "proposed_changes": self.proposed_changes,
            "applied_changes": self.applied_changes,
            "pending_approval": self.pending_approval,
            "error": self.error,
            "retry_count": self.retry_count,
            "last_updated": self.last_updated,
            "created_at": self.created_at,
        }


class TaskManager:
    """
    Manages durable agent tasks with explicit state machine transitions.
    """
    
    _instance: Optional["TaskManager"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._handlers: Dict[TaskState, Callable[[Task], bool]] = {}
    
    @classmethod
    def get_instance(cls) -> "TaskManager":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance"""
        with cls._lock:
            cls._instance = None
    
    def create_task(
        self,
        task_type: TaskType,
        instruction: str,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> Task:
        """Create a new durable task"""
        task_id = str(uuid.uuid4())
        
        task = Task(
            task_id=task_id,
            type=task_type,
            instruction=instruction,
            user_id=user_id,
            workspace_id=workspace_id,
            metadata=metadata or {},
        )
        
        self._tasks[task_id] = task
        logger.info(f"Created task {task_id}: {task_type.value}")
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        return self._tasks.get(task_id)
    
    def get_tasks(
        self,
        state: Optional[TaskState] = None,
        user_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[Task]:
        """Get tasks filtered by criteria"""
        tasks = list(self._tasks.values())
        
        if state:
            tasks = [t for t in tasks if t.state == state]
        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]
        if task_type:
            tasks = [t for t in tasks if t.type == task_type]
        
        return tasks
    
    def get_active_tasks(self) -> List[Task]:
        """Get all non-terminal tasks"""
        terminal_states = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
        return [t for t in self._tasks.values() if t.state not in terminal_states]
    
    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Transition a task to a new state"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        old_state = task.state
        
        # Validate transition is allowed
        if not self._is_valid_transition(old_state, new_state):
            logger.warning(f"Invalid state transition: {old_state} -> {new_state}")
            return False
        
        # Apply transition
        task.state = new_state
        task.last_updated = time.time()
        
        if data:
            for key, value in data.items():
                if hasattr(task, key):
                    setattr(task, key, value)
        
        logger.debug(f"Task {task_id}: {old_state.value} -> {new_state.value}")
        return True
    
    def _is_valid_transition(self, from_state: TaskState, to_state: TaskState) -> bool:
        """Check if a state transition is valid"""
        # Define valid transitions
        valid_transitions = {
            TaskState.CREATED: {TaskState.AUTHORIZING, TaskState.FAILED, TaskState.CANCELLED},
            TaskState.AUTHORIZING: {TaskState.FAILED, TaskState.PLANNING, TaskState.WAITING_APPROVAL},
            TaskState.PLANNING: {TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED},
            TaskState.EXECUTING: {
                TaskState.WAITING_TOOL, TaskState.VERIFYING, TaskState.FAILED,
                TaskState.ROLLING_BACK, TaskState.CANCELLED
            },
            TaskState.WAITING_TOOL: {TaskState.EXECUTING, TaskState.FAILED},
            TaskState.WAITING_APPROVAL: {TaskState.EXECUTING, TaskState.CANCELLED},
            TaskState.VERIFYING: {TaskState.APPLYING, TaskState.FAILED, TaskState.ROLLING_BACK},
            TaskState.APPLYING: {TaskState.HEALTH_CHECK, TaskState.FAILED, TaskState.ROLLING_BACK},
            TaskState.HEALTH_CHECK: {TaskState.COMMITTED, TaskState.ROLLING_BACK, TaskState.FAILED},
            TaskState.COMMITTED: {TaskState.COMPLETED},
            TaskState.ROLLING_BACK: {TaskState.COMMITTED, TaskState.FAILED},
            TaskState.FAILED: {TaskState.EXECUTING, TaskState.CANCELLED},  # Retry
            TaskState.CANCELLED: set(),  # Terminal
            TaskState.COMPLETED: set(),  # Terminal
        }
        
        return to_state in valid_transitions.get(from_state, set())
    
    def save_checkpoint(self, task_id: str) -> bool:
        """Save a checkpoint for task recovery"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        import json
        task.checkpoint = {
            "state": task.state.value,
            "plan": task.plan.to_dict() if task.plan else None,
            "current_goal": task.current_goal,
            "tool_results": task.tool_results,
            "metadata": task.metadata,
            "saved_at": time.time(),
        }
        
        logger.info(f"Saved checkpoint for task {task_id}")
        return True
    
    def restore_from_checkpoint(self, task_id: str) -> bool:
        """Restore task from checkpoint"""
        task = self.get_task(task_id)
        if not task or not task.checkpoint:
            return False
        
        checkpoint = task.checkpoint
        
        # Restore state
        task.state = TaskState(checkpoint.get("state", "created"))
        if checkpoint.get("plan"):
            task.plan = Plan(**checkpoint.get("plan"))
        task.current_goal = checkpoint.get("current_goal", "")
        task.tool_results = checkpoint.get("tool_results", [])
        task.metadata = checkpoint.get("metadata", {})
        
        logger.info(f"Restored task {task_id} from checkpoint")
        return True
    
    def increment_retry(self, task_id: str) -> int:
        """Increment retry count for a task"""
        task = self.get_task(task_id)
        if task:
            task.retry_count += 1
            return task.retry_count
        return 0
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            return False
        
        task.state = TaskState.CANCELLED
        task.completed_at = time.time()
        task.last_updated = time.time()
        
        logger.info(f"Cancelled task {task_id}")
        return True
    
    def set_result(
        self,
        task_id: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Set result for a completed task"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        task.result = result
        task.result_details = details or {}
        task.state = TaskState.COMPLETED
        task.completed_at = time.time()
        task.last_updated = time.time()
        
        logger.info(f"Task {task_id} completed with result")
        return True
    
    def set_error(
        self,
        task_id: str,
        error: str,
        trace: Optional[str] = None,
        retry: bool = True,
    ) -> bool:
        """Set error for a failed task"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        task.error = error
        task.error_trace = trace
        task.last_updated = time.time()
        
        if retry and task.retry_count < 3:
            task.state = TaskState.FAILED
            logger.warning(f"Task {task_id} failed (attempt {task.retry_count}): {error}")
        else:
            task.state = TaskState.CANCELLED if task.retry_count >= 3 else TaskState.FAILED
            if task.retry_count >= 3:
                logger.error(f"Task {task_id} cancelled after max retries: {error}")
            else:
                logger.error(f"Task {task_id} failed: {error}")
        
        return True
    
    def export_state(self) -> Dict[str, Any]:
        """Export full task manager state for persistence"""
        return {
            "timestamp": time.time(),
            "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
        }
    
    def import_state(self, state: Dict[str, Any]) -> None:
        """Import task manager state from persistence"""
        if "tasks" in state:
            for tid, tdata in state["tasks"].items():
                task = Task(**tdata)
                self._tasks[tid] = task
        
        logger.info(f"Imported {len(self._tasks)} tasks")


# Global task manager instance
task_manager = TaskManager.get_instance()