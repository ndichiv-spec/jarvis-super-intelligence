"""Brain runtime health state (spec sections 12, 13).

Mirrors ``silverwing_runtime.health`` but adds the Brain-specific ``stub`` and
``production_health`` flags so the gateway can never mistake a labeled dev stub
for a production model endpoint (spec section 13): a stub runtime answers HTTP
but must NOT report ``healthy=true`` / ``available=true``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class BrainHealthState(StrEnum):
    STARTING = "starting"
    LOADING = "loading"
    WARMUP = "warmup"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    STUB = "stub"  # explicitly-labeled dev stub: never production-healthy


class BrainHealthStatus(BaseModel):
    """Status exposed at ``GET /health`` (unauthenticated)."""

    status: BrainHealthState = BrainHealthState.STARTING
    model: str = ""
    revision: str = ""
    loaded: bool = False
    device: str = ""
    backend: str = ""
    provider: str = ""
    parameters: int = 0
    warmup_ok: bool = False
    # Brain-specific honesty flags.
    stub: bool = False
    available: bool = False  # only True for a real, loaded, warmed-up model
    authorized: bool = False  # whether a valid bearer key was required & present
    production_health: bool = False  # True iff stub=False AND available=True
    # Capability flags surfaced on /health for the control plane (spec Part O/P).
    stream_support: bool = False  # whether the serving backend streams tokens
    models: list[str] = []  # model ids discoverable from the serving backend
    detail: str | None = None


class BrainHealthMonitor:
    """Tracks a single Brain runtime's health; transitions are explicit."""

    def __init__(self) -> None:
        self._status = BrainHealthStatus()

    def set(self, status: BrainHealthStatus) -> None:
        self._status = status

    def current(self) -> BrainHealthStatus:
        return self._status

    def transition(self, state: BrainHealthState, detail: str | None = None, **fields) -> BrainHealthStatus:
        current = self._status.model_copy(update=fields)
        current.status = state
        current.detail = detail
        self._status = current
        return current
