"""Framework-neutral controller for JARVIS presence state."""

from __future__ import annotations

from typing import Literal

from .schemas import PresenceControllerState

AssistantState = Literal[
    "idle", "listening", "thinking", "searching", "observing", "speaking",
    "working", "creating", "navigating", "learning", "explaining",
    "waiting_for_permission", "alert", "offline",
]
PresenceLevel = Literal["hidden", "minimal", "visible", "immersive"]


class PresenceController:
    def __init__(self) -> None:
        self._state = PresenceControllerState()

    @property
    def state(self) -> PresenceControllerState:
        return self._state

    def set_state(self, state: AssistantState) -> PresenceControllerState:
        self._state = PresenceControllerState.model_validate({
            **self._state.model_dump(),
            "state": state,
        })
        return self._state

    def set_expression(self, expression: str | None) -> PresenceControllerState:
        self._state = PresenceControllerState.model_validate({
            **self._state.model_dump(),
            "expression": expression,
        })
        return self._state

    def set_visibility(self, level: PresenceLevel) -> PresenceControllerState:
        self._state = PresenceControllerState.model_validate({
            **self._state.model_dump(),
            "visibility": level,
        })
        return self._state

    def focus(self, target: str | None) -> PresenceControllerState:
        self._state = PresenceControllerState.model_validate({
            **self._state.model_dump(),
            "focus": target,
        })
        return self._state

    def transition(self, environment: str) -> PresenceControllerState:
        self._state = PresenceControllerState.model_validate({
            **self._state.model_dump(),
            "environment": environment,
        })
        return self._state
