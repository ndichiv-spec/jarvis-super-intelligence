"""Framework-independent service for validating and advancing presentation intents."""

from __future__ import annotations

from datetime import UTC, datetime

from .event_adapter import presentation_event_adapter
from .events import PresentationEvent
from .lifecycle import LifecycleState, transition_lifecycle
from .schemas import PRESENTATION_VERSION, PresentationEnvelope, PresentationLifecycle
from .validation import validate_envelope


class PresentationService:
    """Validates core-owned intent and applies deterministic lifecycle changes."""

    def validate(self, envelope: PresentationEnvelope) -> PresentationEnvelope:
        return validate_envelope(envelope)

    def created_event(self, envelope: PresentationEnvelope) -> PresentationEvent:
        validated = self.validate(envelope)
        return PresentationEvent(
            protocol="jarvis.presentation",
            version=PRESENTATION_VERSION,
            presentation_id=validated.intent.id,
            session_id=validated.intent.session_id,
            sequence=0,
            type="created",
            occurred_at=datetime.now(UTC),
            payload={
                "environment": validated.intent.environment.type,
                "mode": validated.intent.mode,
            },
        )

    def adapt_runtime_events(
        self,
        envelope: PresentationEnvelope,
        events: list[dict[str, object]],
    ) -> list[PresentationEvent]:
        validated = self.validate(envelope)
        translated = [self.created_event(validated)]
        for sequence, event in enumerate(events, start=1):
            adapted = presentation_event_adapter.adapt(
                event,
                presentation_id=validated.intent.id,
                session_id=validated.intent.session_id,
                sequence=sequence,
            )
            if adapted:
                translated.append(adapted)
        return translated

    def transition(
        self,
        lifecycle: PresentationLifecycle,
        target: LifecycleState,
    ) -> PresentationLifecycle:
        return transition_lifecycle(lifecycle, target)
