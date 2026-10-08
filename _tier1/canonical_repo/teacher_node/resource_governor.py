"""Resource Governor for the Teacher Node (spec §18, §55, §57).

Enforces configurable resource limits for background learning processes
(Teacher Node, Learning Arena, remote training) so they never degrade the
local machine's primary workload.

Policy model:
  * **Thresholds** — CPU, memory, GPU, and disk usage percentages. When a
    threshold is breached, the governor enters a throttle or pause state.
  * **States** — ``IDLE`` → ``RUNNING`` → ``THROTTLED`` → ``PAUSED`` → ``CANCELLED``.
  * **Actions** — pause (suspend all background tasks), throttle (reduce
    concurrency), cancel (kill a specific task), resume.
  * **Config** — via ``JARVIS_LOCAL_MAX_*`` env vars (spec §55).

The governor is a **gate**, not an enforcer — it signals the learning loop
to pause/stop; the loop must poll it.  This keeps the governor testable
without mocking process signals.

Design invariant (spec §55): background learning never degrades the local
machine.  If the machine is under interactive load (foreground user),
all background tasks pause automatically.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

try:
    import psutil  # type: ignore[import-not-found]
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class GovernorState(Enum):
    """Resource governor policy state."""

    IDLE = "idle"
    RUNNING = "running"
    THROTTLED = "throttled"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class ResourceSnapshot:
    """Point-in-time resource usage."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    gpu_percent: float
    gpu_vram_percent: float
    timestamp: float
    # Process counts (for background-learning awareness).
    background_tasks: int = 0


@dataclass
class GovernorConfig:
    """Thresholds and limits (spec §55).

    All limits are environment-configurable via ``JARVIS_LOCAL_MAX_*``.
    """

    max_cpu_percent: float = 70.0
    max_memory_percent: float = 75.0
    max_disk_percent: float = 85.0
    max_gpu_percent: float = 80.0
    max_gpu_vram_percent: float = float("inf")
    max_background_tasks: int = 2
    # If foreground CPU load exceeds this, pause all background tasks.
    foreground_pause_threshold: float = 90.0
    # Throttle concurrency linearly between these thresholds.
    throttle_start: float = 60.0
    throttle_end: float = 85.0
    # Disk space (bytes) below which learning pauses.
    min_disk_bytes: int = 5 * 1024**3  # 5 GB

    @classmethod
    def from_env(cls) -> "GovernorConfig":
        """Build config from ``JARVIS_LOCAL_MAX_*`` env vars (spec §55)."""
        def _f(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, default))
            except (TypeError, ValueError):
                return default

        def _i(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, default))
            except (TypeError, ValueError):
                return default

        return cls(
            max_cpu_percent=_f("JARVIS_LOCAL_MAX_CPU_PERCENT", 70.0),
            max_memory_percent=_f("JARVIS_LOCAL_MAX_MEMORY_PERCENT", 75.0),
            max_disk_percent=_f("JARVIS_LOCAL_MAX_DISK_PERCENT", 85.0),
            max_gpu_percent=_f("JARVIS_LOCAL_MAX_GPU_PERCENT", 80.0),
            max_gpu_vram_percent=_f("JARVIS_LOCAL_MAX_GPU_VRAM_PERCENT", float("inf")),
            max_background_tasks=_i("JARVIS_LOCAL_MAX_BACKGROUND_TASKS", 2),
            foreground_pause_threshold=_f("JARVIS_LOCAL_MAX_FOREGROUND_CPU", 90.0),
            throttle_start=_f("JARVIS_LOCAL_THROTTLE_START", 60.0),
            throttle_end=_f("JARVIS_LOCAL_THROTTLE_END", 85.0),
            min_disk_bytes=_i("JARVIS_LOCAL_MIN_DISK_BYTES", 5 * 1024**3),
        )


class ResourceGovernor:
    """Enforces resource limits for background learning (spec §18, §55).

    Usage::

        governor = ResourceGovernor()
        if governor.can_start_task():
            task = start_learning_task()
            governor.register_task(task.id)
        # Periodically poll:
        if not governor.check().state == GovernorState.RUNNING:
            governor.pause_all()
    """

    def __init__(self, config: Optional[GovernorConfig] = None) -> None:
        self._config = config or GovernorConfig.from_env()
        self._state = GovernorState.IDLE
        self._task_ids: set[str] = set()
        self._last_snapshot: Optional[ResourceSnapshot] = None
        self._cancelled: set[str] = set()

    # ------------------------------------------------------------------ #
    # Resource sampling
    # ------------------------------------------------------------------ #
    def sample(self, *, background_tasks: int = 0) -> ResourceSnapshot:
        """Take a resource snapshot using psutil (or injected values)."""
        if _HAS_PSUTIL:
            snap = ResourceSnapshot(
                cpu_percent=psutil.cpu_percent(interval=0.5),
                memory_percent=psutil.virtual_memory().percent,
                disk_percent=psutil.disk_usage("/").percent,
                gpu_percent=0.0,
                gpu_vram_percent=0.0,
                timestamp=time.time(),
                background_tasks=background_tasks,
            )
            # Optional GPU stats (best-effort — no GPUtil dependency).
            try:
                import GPUtil  # type: ignore[import-not-found]
                gpus = GPUtil.getGPUs()
                if gpus:
                    snap.gpu_percent = gpus[0].load * 100
                    snap.gpu_vram_percent = (gpus[0].memoryUtil or 0) * 100
            except ImportError:
                pass
            self._last_snapshot = snap
            return snap
        else:
            # Fallback: injectable via subclass or test override.
            return self._last_snapshot or ResourceSnapshot(
                cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0,
                gpu_percent=0.0, gpu_vram_percent=0.0, timestamp=time.time(),
                background_tasks=background_tasks,
            )

    @property
    def last_snapshot(self) -> Optional[ResourceSnapshot]:
        return self._last_snapshot

    # ------------------------------------------------------------------ #
    # Policy evaluation
    # ------------------------------------------------------------------ #
    def check(self, snapshot: Optional[ResourceSnapshot] = None) -> GovernorState:
        """Evaluate current resource state and return the resulting governor state.

        The caller should then call ``pause_all()``, ``throttle_concurrency()``,
        etc. based on the returned state.
        """
        snap = snapshot or self.sample(background_tasks=len(self._task_ids))

        # 1. Cancel takes priority.
        if self._state == GovernorState.CANCELLED:
            return self._state

        # 2. Disk space check (absolute, before anything else).
        if _HAS_PSUTIL:
            disk = psutil.disk_usage("/")
            if disk.free < self._config.min_disk_bytes:
                self._state = GovernorState.PAUSED
                return self._state

        # 3. Foreground load — if interactive CPU is high, pause everything.
        #    psutil.cpu_percent counts ALL cpu (including background), so we
        #    use a heuristic: if background tasks are running and the overall
        #    CPU exceeds the foreground threshold, assume interactive load.
        if snap.cpu_percent > self._config.foreground_pause_threshold:
            self._state = GovernorState.PAUSED
            return self._state

        # 4. Per-resource threshold checks.
        if (
            snap.cpu_percent > self._config.max_cpu_percent
            or snap.memory_percent > self._config.max_memory_percent
            or snap.disk_percent > self._config.max_disk_percent
            or snap.gpu_percent > self._config.max_gpu_percent
            or snap.gpu_vram_percent > self._config.max_gpu_vram_percent
        ):
            self._state = GovernorState.THROTTLED
            return self._state

        # 5. If under thresholds and we have background tasks, we're running.
        if self._task_ids:
            self._state = GovernorState.RUNNING
            return self._state

        # 6. No tasks, all clear.
        self._state = GovernorState.IDLE
        return self._state

    # ------------------------------------------------------------------ #
    # Concurrency throttling (spec §55 — linear ramp between throttle_start/end)
    # ------------------------------------------------------------------ #
    def allowed_concurrency(self, snapshot: Optional[ResourceSnapshot] = None) -> int:
        """Current allowed concurrency for background tasks."""
        snap = snapshot or self._last_snapshot
        if snap is None:
            return self._config.max_background_tasks
        cpu = snap.cpu_percent
        if cpu < self._config.throttle_start:
            return self._config.max_background_tasks
        if cpu > self._config.throttle_end:
            return 1
        # Linear interpolation between throttle_start and throttle_end.
        fraction = (cpu - self._config.throttle_start) / (
            self._config.throttle_end - self._config.throttle_start
        )
        fraction = max(0.0, min(1.0, fraction))
        allowed = self._config.max_background_tasks * (1 - fraction)
        return max(1, int(allowed))

    # ------------------------------------------------------------------ #
    # Task lifecycle
    # ------------------------------------------------------------------ #
    def can_start_task(self, snapshot: Optional[ResourceSnapshot] = None) -> bool:
        """True iff the governor allows starting a new background task."""
        if self._state == GovernorState.CANCELLED:
            return False
        snap = snapshot or self.sample(background_tasks=len(self._task_ids))
        state = self.check(snap)
        if state in (GovernorState.PAUSED,):
            return False
        if len(self._task_ids) >= self._config.max_background_tasks:
            return False
        return True

    def register_task(self, task_id: str, snapshot: Optional[ResourceSnapshot] = None) -> bool:
        """Register a new background task. Returns False if rejected."""
        if not self.can_start_task(snapshot):
            return False
        self._task_ids.add(task_id)
        if self._state in (GovernorState.IDLE, GovernorState.THROTTLED):
            self._state = GovernorState.RUNNING
        return True

    def unregister_task(self, task_id: str) -> None:
        self._task_ids.discard(task_id)

    @property
    def active_tasks(self) -> int:
        return len(self._task_ids)

    @property
    def state(self) -> GovernorState:
        return self._state

    # ------------------------------------------------------------------ #
    # Control actions
    # ------------------------------------------------------------------ #
    def pause_all(self) -> GovernorState:
        """Pause all background tasks immediately (spec §57 — interactive gate)."""
        self._state = GovernorState.PAUSED
        return self._state

    def resume(self) -> GovernorState:
        """Resume background tasks (only if resources allow)."""
        snap = self.sample(background_tasks=len(self._task_ids))
        self._state = GovernorState.RUNNING if self._task_ids else GovernorState.IDLE
        return self.check(snap)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task (remove from active set)."""
        self._cancelled.add(task_id)
        self._task_ids.discard(task_id)
        return True

    def is_task_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled by the governor."""
        return task_id in self._cancelled

    def throttle_concurrency(self) -> int:
        """Return the currently allowed concurrency given live resource state."""
        snap = self.sample(background_tasks=len(self._task_ids))
        self.check(snap)
        return self.allowed_concurrency(snap)
