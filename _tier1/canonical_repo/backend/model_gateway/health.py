"""Gateway-side health reporting (spec sections 13, 28).

The gateway performs its own health check of the Silverwing runtime and, on
failure, makes the decision that the model router may fall back to an approved
provider.  Fallback decisions are always recorded (spec section 28) and are
never silently presented as Silverwing output.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class HealthLevel(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class GatewayHealth(BaseModel):
    status: HealthLevel = HealthLevel.UNKNOWN
    model: str = ""
    revision: str = ""
    loaded: bool = False
    device: str = ""
    backend: str = ""
    parameters: int = 0
    warmup_ok: bool = False
    detail: str | None = None
    checked_at: float = 0.0
    available: bool = False
    latency_ms: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthLevel.HEALTHY
