"""Runtime health state.

The runtime only reports ``healthy`` after a successful model load AND a
successful warmup inference (specification section 12-13).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class HealthState(StrEnum):
    STARTING = "starting"
    LOADING = "loading"
    WARMUP = "warmup"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"


class HealthStatus(BaseModel):
    status: HealthState = HealthState.STARTING
    model: str = ""
    revision: str = ""
    loaded: bool = False
    device: str = ""
    backend: str = ""
    parameters: int = 0
    warmup_ok: bool = False
    detail: str | None = None


class HealthMonitor:
    """Tracks a single runtime's health; transitions are explicit."""

    def __init__(self) -> None:
        self._status = HealthStatus()

    def set(self, status: HealthStatus) -> None:
        self._status = status

    def current(self) -> HealthStatus:
        return self._status

    def transition(self, state: HealthState, detail: str | None = None, **fields) -> HealthStatus:
        current = self._status.model_copy(update=fields)
        current.status = state
        current.detail = detail
        self._status = current
        return current
