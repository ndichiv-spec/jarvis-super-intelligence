"""Machine observer for the Teacher Node (spec §17, §18).

Periodically samples system resources (CPU, memory, disk, GPU, process
info) and records findings in :class:`~teacher_node.system_knowledge.SystemKnowledge`
as structured, sanitized observations.

Design:
  * Uses ``psutil`` directly (already a project dependency).
  * All observations are sanitized before storage (spec §23, §55).
  * Samples are **honest** — never rounds up or fabricates values.
  * Can run as a background thread (daemon, cancellable) or on-demand.

The observer reports what *is*, not what *should be*.  Resource governor
decisions are made by :class:`~teacher_node.resource_governor.ResourceGovernor`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import psutil  # type: ignore[import-not-found]
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


@dataclass
class SystemMetrics:
    """Point-in-time system resource metrics."""

    cpu_percent: float
    cpu_count_logical: int
    cpu_count_physical: int
    memory_total: int
    memory_available: int
    memory_percent: float
    disk_total: int
    disk_used: int
    disk_free: int
    disk_percent: float
    bytes_read: int
    bytes_written: int
    process_count: int
    timestamp: float
    gpu_info: list[dict[str, Any]] = field(default_factory=list)


class MachineObserver:
    """Observes and records machine-level resource metrics.

    Parameters
    ----------
    knowledge
        The :class:`SystemKnowledge` store to record observations in.
    interval
        Sampling interval in seconds.
    """

    def __init__(
        self,
        knowledge: Any,
        *,
        interval: float = 30.0,
    ) -> None:
        self._knowledge = knowledge
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------ #
    # Sampling
    # ------------------------------------------------------------------ #
    def sample(self) -> Optional[SystemMetrics]:
        """Take a single point-in-time sample of system resources."""
        if not _HAS_PSUTIL:
            return None

        cpu_percent = psutil.cpu_percent(interval=0.5)
        vmem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        bytes_read, bytes_written = 0, 0
        try:
            io = psutil.disk_io_counters()
            bytes_read = io.read_bytes
            bytes_written = io.write_bytes
        except (AttributeError, RuntimeError):
            pass

        # Optional GPU info (best-effort, no hard dependency).
        gpu_info = []
        try:
            import GPUtil  # type: ignore[import-not-found]
            for gpu in GPUtil.getGPUs():
                gpu_info.append({
                    "id": gpu.id,
                    "name": gpu.name,
                    "load": gpu.load,
                    "vram_used": gpu.memoryUsed,
                    "vram_total": gpu.memoryTotal,
                })
        except ImportError:
            pass

        return SystemMetrics(
            cpu_percent=cpu_percent,
            cpu_count_logical=psutil.cpu_count(logical=True) or 0,
            cpu_count_physical=psutil.cpu_count(logical=False) or 0,
            memory_total=vmem.total,
            memory_available=vmem.available,
            memory_percent=vmem.percent,
            disk_total=disk.total,
            disk_used=disk.used,
            disk_free=disk.free,
            disk_percent=disk.percent,
            bytes_read=bytes_read,
            bytes_written=bytes_written,
            process_count=len(psutil.pids()),
            timestamp=time.time(),
            gpu_info=gpu_info,
        )

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #
    def record(self) -> Optional[Any]:
        """Sample once and record the observation in the knowledge store."""
        metrics = self.sample()
        if metrics is None:
            return None

        entry = self._knowledge.add(
            category="resource",
            key=f"system_metrics_{int(metrics.timestamp)}",
            value={
                "cpu_percent": metrics.cpu_percent,
                "memory_percent": metrics.memory_percent,
                "disk_percent": metrics.disk_percent,
                "process_count": metrics.process_count,
                "gpu_count": len(metrics.gpu_info),
            },
            confidence=1.0,
            tags=["resource", "system", "metrics"],
            source_ref="machine_observer",
        )
        return entry

    # ------------------------------------------------------------------ #
    # Background thread
    # ------------------------------------------------------------------ #
    def start(self, daemon: bool = True) -> threading.Thread:
        """Start the observer in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return self._thread

        def _run() -> None:
            while not self._stop_event.is_set():
                try:
                    self.record()
                except Exception:  # noqa: BLE001 — observer must never crash
                    pass
                self._stop_event.wait(self._interval)

        self._thread = threading.Thread(
            target=_run, name="machine-observer", daemon=daemon
        )
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1.0)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
