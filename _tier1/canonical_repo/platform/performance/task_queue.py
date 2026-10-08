"""
Async task queue with worker pool for Jarvis.

Provides an in-process async task queue with priority support,
concurrency limits, delayed execution, retry, and graceful shutdown.
Designed to integrate with Celery for distributed execution when needed.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Coroutine, Dict, List, Optional,
    Set, TypeVar, Generic, Union,
)

from performance.concurrency import AtomicCounter, KeyedLock

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    RETRYING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    TIMED_OUT = auto()


@dataclass
class Task(Generic[T]):
    id: str
    name: str
    coro: Coroutine[Any, Any, T]
    task_factory: Optional[Callable[[], Coroutine[Any, Any, T]]] = None
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[T] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 0
    next_attempt_at: Optional[float] = None
    backoff_seconds: float = 0.0
    backoff_base: float = 1.0
    backoff_cap: float = 60.0
    last_error: Optional[str] = None
    timeout: Optional[float] = None
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class WorkerPool:
    """
    Manages a pool of async workers that consume tasks from a queue.

    Features:
    - Configurable concurrency (number of workers)
    - Priority-based task scheduling
    - Per-task timeout
    - Automatic retry on failure
    - Graceful shutdown via cancellation
    """

    def __init__(
        self,
        name: str = "default",
        min_workers: int = 1,
        max_workers: int = 10,
        queue_maxsize: int = 0,
    ):
        self.name = name
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=queue_maxsize)

        self._workers: Set[asyncio.Task] = set()
        self._delayed_retries: Set[asyncio.Task] = set()
        self._running = False
        self._tasks: Dict[str, Task] = {}
        self._task_lock = KeyedLock()
        self._total_enqueued = AtomicCounter()
        self._total_completed = AtomicCounter()
        self._total_failed = AtomicCounter()

    async def start(self):
        """Start the worker pool with minimum workers."""
        self._running = True
        for _ in range(self._min_workers):
            await self._spawn_worker()
        logger.info(
            "Worker pool '%s' started with %d workers",
            self.name, self._min_workers,
        )

    async def stop(self, wait: bool = True, timeout: float = 30.0):
        """Stop the worker pool gracefully."""
        self._running = False
        if wait:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                pass

        pending = list(self._workers | self._delayed_retries)
        for worker in pending:
            if not worker.done():
                worker.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self._workers.clear()
        self._delayed_retries.clear()
        logger.info("Worker pool '%s' stopped", self.name)

    async def enqueue(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 0,
        timeout: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
        task_factory: Optional[Callable[[], Coroutine[Any, Any, T]]] = None,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> str:
        """
        Enqueue a coroutine for execution.

        Returns the task ID for tracking.
        """
        if max_retries and task_factory is None:
            coro.close()
            raise ValueError("task_factory is required when max_retries is non-zero")
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            name=name or coro.__name__,
            coro=coro,
            task_factory=task_factory,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            tags=tags or {},
            backoff_base=max(0.01, base_backoff),
            backoff_cap=max(max(0.01, base_backoff), max_backoff),
        )
        self._tasks[task_id] = task
        await self._total_enqueued.inc()

        await self._queue.put((-priority.value, task_id))

        if len(self._workers) < self._max_workers:
            await self._spawn_worker()

        return task_id

    async def get_result(self, task_id: str, timeout: Optional[float] = None) -> Optional[T]:
        """Wait for a task to complete and return its result."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT):
                if task.error:
                    raise RuntimeError(task.error)
                return task.result
            if deadline and time.monotonic() >= deadline:
                raise asyncio.TimeoutError(f"Task {task_id} did not complete within {timeout}s")
            await asyncio.sleep(0.01)

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status in {TaskStatus.PENDING, TaskStatus.RETRYING}:
            task.coro.close()
            task.status = TaskStatus.CANCELLED
            task.error = None
            task.completed_at = time.time()
            return True
        return False

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        task = self._tasks.get(task_id)
        return task.status if task else None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "workers": len(self._workers),
            "min_workers": self._min_workers,
            "max_workers": self._max_workers,
            "queue_size": self._queue.qsize(),
            "tasks_enqueued": self._total_enqueued,
            "tasks_completed": self._total_completed,
            "tasks_failed": self._total_failed,
            "running": self._running,
        }

    async def _spawn_worker(self):
        """Spawn a new worker coroutine."""
        worker = asyncio.create_task(self._worker_loop())
        self._workers.add(worker)
        worker.add_done_callback(self._workers.discard)

    async def _worker_loop(self):
        """Main worker loop - continuously consumes tasks from the queue."""
        while self._running:
            try:
                _, task_id = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                if task_id is None:
                    self._queue.task_done()
                    continue
            except asyncio.TimeoutError:
                if len(self._workers) > self._min_workers:
                    break
                continue

            task = self._tasks.get(task_id)
            if task is None or task.status == TaskStatus.CANCELLED:
                self._queue.task_done()
                continue

            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

            try:
                if task.timeout:
                    result = await asyncio.wait_for(task.coro, timeout=task.timeout)
                else:
                    result = await task.coro

                task.result = result
                task.status = TaskStatus.SUCCESS
                await self._total_completed.inc()

            except asyncio.TimeoutError:
                task.status = TaskStatus.TIMED_OUT
                task.error = f"Task timed out after {task.timeout}s"
                await self._total_failed.inc()
                await self._handle_retry(task)

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = f"{type(e).__name__}: {e}"
                logger.warning("Task '%s' failed: %s", task.name, task.error)
                await self._total_failed.inc()
                await self._handle_retry(task)

            finally:
                task.completed_at = time.time()
                self._queue.task_done()

    async def _handle_retry(self, task: Task):
        """Re-enqueue a task if retries remain."""
        if task.retries >= task.max_retries or task.task_factory is None:
            return
        task.retries += 1
        task.status = TaskStatus.RETRYING
        task.last_error = task.error
        task.backoff_seconds = min(
            task.backoff_cap,
            task.backoff_base * (2 ** (task.retries - 1)),
        )
        task.next_attempt_at = time.time() + task.backoff_seconds
        delayed = asyncio.create_task(self._requeue_retry(task))
        self._delayed_retries.add(delayed)
        delayed.add_done_callback(self._delayed_retries.discard)
        logger.info(
            "Retrying task '%s' (attempt %d/%d) after %.2fs",
            task.name, task.retries + 1, task.max_retries + 1,
            task.backoff_seconds,
        )

    async def _requeue_retry(self, task: Task) -> None:
        await asyncio.sleep(task.backoff_seconds)
        if not self._running or task.status == TaskStatus.CANCELLED:
            return
        try:
            task.coro = task.task_factory()
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = f"{type(exc).__name__}: retry factory failed"
            task.last_error = task.error
            task.completed_at = time.time()
            return
        task.status = TaskStatus.PENDING
        task.started_at = None
        task.completed_at = None
        task.error = None
        task.next_attempt_at = None
        await self._queue.put((-task.priority.value, task.id))


class TaskGroup:
    """
    Group multiple tasks and wait for all to complete (fan-out).

    Usage:
        async with TaskGroup(pool) as group:
            t1 = await group.enqueue(coro1)
            t2 = await group.enqueue(coro2)
        results = group.results
    """

    def __init__(self, pool: WorkerPool):
        self._pool = pool
        self._task_ids: List[str] = []
        self.results: List[Any] = []

    async def enqueue(
        self,
        coro: Coroutine,
        *,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> str:
        task_id = await self._pool.enqueue(coro, name=name, priority=priority, timeout=timeout)
        self._task_ids.append(task_id)
        return task_id

    async def wait(self, timeout: Optional[float] = None) -> List[Any]:
        results = []
        for tid in self._task_ids:
            try:
                result = await self._pool.get_result(tid, timeout=timeout)
                results.append(result)
            except Exception as e:
                results.append(e)
        self.results = results
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.wait()
