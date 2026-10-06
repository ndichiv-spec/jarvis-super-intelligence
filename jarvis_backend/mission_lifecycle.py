"""Phase 10 — Mission Lifecycle state machine.

Explicit, validated state transitions for a Mission.  A mission cannot
become COMPLETED merely because a task succeeded — completion requires
success-criteria verification.

States and legal transitions
-----------------------------

::

    DRAFT
      │  validate → ACTIVE
      │  cancel → CANCELLED
      └─ (any → CANCELLED)
    ACTIVE
      ├── pause → PAUSED
      ├── block → BLOCKED
      ├── needs_approval → WAITING_FOR_APPROVAL
      ├── needs_resource → WAITING_FOR_RESOURCE
    ├...     ├── resume → ACTIVE
      │  verify → VERIFYING
      │  complete → COMPLETED  (only via VERIFYING with verified success criteria)
    ├...     ├── fail → FAILED
      │  cancel → CANCELLED
    PAUSED
      ├── resume → ACTIVE
      ├── cancel → CANCELLED
    BLOCKED
      ├── unblock → ACTIVE
      ├── cancel → CANCELLED
    WAITING_FOR_APPROVAL
      ├── approve → ACTIVE
      ├── reject → FAILED
      ├── cancel → CANCELLED
    WAITING_FOR_RESOURCE
      ├── resource_available → ACTIVE
      ├── timeout → BLOCKED
      ├── cancel → CANCELLED
    VERIFYING
      ├── verify_pass → COMPLETED
      ├── verify_fail → FAILED
      ├── cancel → CANCELLED
    COMPLETED  (terminal)
    FAILED     (terminal)
    CANCELLED  (terminal)

Every transition validates preconditions (e.g. DRAFT→ACTIVE requires
objective + success_criteria).  Illegal transitions raise ``ValueError``.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("jarvis_backend.mission_lifecycle")


class MissionStatus(str, Enum):
    """Full lifecycle states for a Mission."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    WAITING_FOR_RESOURCE = "WAITING_FOR_RESOURCE"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Terminal statuses — once reached, no further transitions are possible.
TERMINAL_STATUSES: frozenset[MissionStatus] = frozenset({
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.CANCELLED,
})

# Non-terminal statuses that can transition to terminal or other states.
NON_TERMINAL_STATUSES: frozenset[MissionStatus] = frozenset({
    MissionStatus.DRAFT,
    MissionStatus.ACTIVE,
    MissionStatus.PAUSED,
    MissionStatus.BLOCKED,
    MissionStatus.WAITING_FOR_APPROVAL,
    MissionStatus.WAITING_FOR_RESOURCE,
    MissionStatus.VERIFYING,
})


class MissionTransitionError(ValueError):
    """Raised when an illegal mission state transition is attempted."""


# ---------------------------------------------------------------------------
# Explicit transition table:  current_state -> set of allowed next states
# ---------------------------------------------------------------------------
_TRANSITIONS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.DRAFT: frozenset({
        MissionStatus.ACTIVE,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.ACTIVE: frozenset({
        MissionStatus.PAUSED,
        MissionStatus.BLOCKED,
        MissionStatus.WAITING_FOR_APPROVAL,
        MissionStatus.WAITING_FOR_RESOURCE,
        MissionStatus.VERIFYING,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.PAUSED: frozenset({
        MissionStatus.ACTIVE,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.BLOCKED: frozenset({
        MissionStatus.ACTIVE,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.WAITING_FOR_APPROVAL: frozenset({
        MissionStatus.ACTIVE,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.WAITING_FOR_RESOURCE: frozenset({
        MissionStatus.ACTIVE,
        MissionStatus.BLOCKED,
        MissionStatus.CANCELLED,
    }),
    MissionStatus.VERIFYING: frozenset({
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    }),
    # Terminal states have no outgoing transitions.
    MissionStatus.COMPLETED: frozenset(),
    MissionStatus.FAILED: frozenset(),
    MissionStatus.CANCELLED: frozenset(),
}


class MissionLifecycle:
    """Validates mission state transitions and enforces preconditions.

    Usage::

        lifecycle = MissionLifecycle()
        lifecycle.validate_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE,
                                    mission)
    """

    def __init__(self) -> None:
        self._transitions = _TRANSITIONS

    def can_transition(
        self,
        current: MissionStatus,
        target: MissionStatus,
    ) -> bool:
        """Return True if ``current → target`` is a legal transition."""
        if current == target:
            return True  # no-op transition is always allowed
        if current in TERMINAL_STATUSES:
            return False
        allowed = self._transitions.get(current, frozenset())
        return target in allowed

    def validate_transition(
        self,
        current: MissionStatus,
        target: MissionStatus,
        mission: Optional[Any] = None,
    ) -> None:
        """Validate that ``current → target`` is legal.

        If ``mission`` is provided, additional preconditions are checked:
        - DRAFT → ACTIVE requires ``objective``, ``success_criteria``.
        - A mission with active tasks cannot be PAUSED or CANCELLED
          (tasks must drain first).
        - Any state → COMPLETED is rejected (must go through VERIFYING).
        """
        if current == target:
            return  # no-op

        if current in TERMINAL_STATUSES:
            raise MissionTransitionError(
                f"Cannot transition from terminal state {current.value} to "
                f"{target.value}. Terminal missions cannot be modified."
            )

        allowed = self._transitions.get(current, frozenset())
        if target not in allowed:
            raise MissionTransitionError(
                f"Illegal transition: {current.value} → {target.value}. "
                f"Allowed: {sorted(s.value for s in allowed) or '[]'}"
            )

        # --- Preconditions that depend on mission content ---
        if target == MissionStatus.ACTIVE and current == MissionStatus.DRAFT:
            self._check_can_activate(mission)

        if target == MissionStatus.COMPLETED and current != MissionStatus.VERIFYING:
            raise MissionTransitionError(
                f"Mission may only become COMPLETED via VERIFYING. "
                f"Current state: {current.value}"
            )

        if target in (MissionStatus.PAUSED, MissionStatus.CANCELLED) and mission:
            self._check_no_active_tasks(mission)

    # ------------------------------------------------------------------ #
    # Precondition helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_can_activate(mission: Optional[Any]) -> None:
        """DRAFT → ACTIVE requires objective and success criteria."""
        if mission is None:
            return  # cannot validate without the object; allow at call-site
        objective = getattr(mission, "objective", "") or ""
        success_criteria = getattr(mission, "success_criteria", None)
        if not objective.strip():
            raise MissionTransitionError(
                "DRAFT → ACTIVE requires a non-empty objective"
            )
        if not success_criteria:
            raise MissionTransitionError(
                "DRAFT → ACTIVE requires success_criteria to be defined"
            )

    @staticmethod
    def _check_no_active_tasks(mission: Optional[Any]) -> None:
        """PAUSE / CANCEL require no nodes to be actively executing."""
        if mission is None:
            return
        tasks = getattr(mission, "tasks", None)
        if not tasks:
            return
        # If any task is in a running/active state, refuse.
        active = _count_active_tasks(tasks)
        if active > 0:
            raise MissionTransitionError(
                f"Cannot PAUSE/CANCEL with {active} active task(s) — "
                "drain or cancel tasks first"
            )


def _count_active_tasks(tasks: list) -> int:
    """Count tasks whose status indicates active execution."""
    active_statuses = {"RUNNING", "WAITING_FOR_USER", "RETRYING", "AUTHORIZED",
                       "PENDING", "PLANNED", "RECEIVED"}
    count = 0
    for t in tasks:
        if isinstance(t, dict):
            if t.get("status", "").upper() in active_statuses:
                count += 1
        elif hasattr(t, "status"):
            val = getattr(t.status, "value", str(t.status))
            if val.upper() in active_statuses:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------
_lifecycle = MissionLifecycle()


def is_terminal(status: MissionStatus) -> bool:
    """True if *status* is a terminal mission state."""
    return status in TERMINAL_STATUSES


def can_transition(current: MissionStatus, target: MissionStatus) -> bool:
    """Module-level shortcut for :meth:`MissionLifecycle.can_transition`."""
    return _lifecycle.can_transition(current, target)


def validate_transition(
    current: MissionStatus,
    target: MissionStatus,
    mission: Optional[Any] = None,
) -> None:
    """Module-level shortcut for :meth:`MissionLifecycle.validate_transition`."""
    _lifecycle.validate_transition(current, target, mission)


__all__ = [
    "MissionStatus",
    "TERMINAL_STATUSES",
    "NON_TERMINAL_STATUSES",
    "MissionTransitionError",
    "MissionLifecycle",
    "is_terminal",
    "can_transition",
    "validate_transition",
]
