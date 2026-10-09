"""Deterministic lifecycle transitions for presentation instances."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from .schemas import PresentationLifecycle


class LifecycleState(StrEnum):
    CREATE = "create"
    ACTIVE = "active"
    UPDATING = "updating"
    TRANSITIONING = "transitioning"
    SUSPENDED = "suspended"
    RESUMED = "resumed"
    COMPLETED = "completed"
    CLOSED = "closed"


_ALLOWED: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.CREATE: {LifecycleState.ACTIVE, LifecycleState.CLOSED},
    LifecycleState.ACTIVE: {
        LifecycleState.UPDATING, LifecycleState.TRANSITIONING, LifecycleState.SUSPENDED,
        LifecycleState.COMPLETED, LifecycleState.CLOSED,
    },
    LifecycleState.UPDATING: {
        LifecycleState.ACTIVE, LifecycleState.TRANSITIONING, LifecycleState.SUSPENDED,
        LifecycleState.COMPLETED, LifecycleState.CLOSED,
    },
    LifecycleState.TRANSITIONING: {
        LifecycleState.ACTIVE, LifecycleState.SUSPENDED, LifecycleState.COMPLETED,
        LifecycleState.CLOSED,
    },
    LifecycleState.SUSPENDED: {
        LifecycleState.RESUMED, LifecycleState.CLOSED,
    },
    LifecycleState.RESUMED: {
        LifecycleState.ACTIVE, LifecycleState.UPDATING, LifecycleState.CLOSED,
    },
    LifecycleState.COMPLETED: {LifecycleState.CLOSED},
    LifecycleState.CLOSED: set(),
}


def transition_lifecycle(
    current: PresentationLifecycle,
    target: LifecycleState,
) -> PresentationLifecycle:
    state = LifecycleState(current.state)
    if target not in _ALLOWED[state]:
        raise ValueError(f"Invalid presentation lifecycle transition: {state} -> {target}.")
    return PresentationLifecycle(state=target, updated_at=datetime.now(UTC))
