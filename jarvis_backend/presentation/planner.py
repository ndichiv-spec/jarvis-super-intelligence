"""Evidence-bound presentation planning over the existing JARVIS runtime."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from ..core import get_store
from .context import PresentationContextService, presentation_context_service
from .policy import PresentationPolicy, presentation_policy
from .presence import PresenceController
from .schemas import (
    AssistantPresentationState,
    DataFreshness,
    DataReference,
    EmphasisIntent,
    EnvironmentIntent,
    FocusIntent,
    InformationPriority,
    LayoutIntent,
    PresentationCapabilities,
    PresentationEnvelope,
    PresentationIntent,
    PresentationLifecycle,
    PresentationPlan,
    PresentationSecurity,
    PresentationSource,
    PresentationTrace,
    PresentationTraceTimestamps,
    TransitionIntent,
    VisualizationIntent,
    VoicePresentationIntent,
)
from .service import PresentationService

_ENVIRONMENT_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("geospatial", ("location", "geography", "map", "navigation", "routing")),
    ("communications", ("email", "message", "calendar", "communication")),
    ("visual", ("image", "vision", "media", "generation")),
    ("device", ("device", "computer", "desktop")),
    ("research", ("search", "browser", "web", "research")),
    ("learning", ("learning", "training", "study")),
    ("tasks", ("task", "agent", "automation")),
    ("knowledge", ("knowledge", "memory")),
)

_PREFERENCE_COMMANDS = {
    "minimal": ("make yourself minimal", "make this minimal", "keep it minimal"),
    "detailed": ("show more detail", "show me everything", "give me the details"),
    "technical": ("technical details", "show raw technical information"),
    "visual": ("make this visual", "make it more visual"),
    "compact": ("make it compact", "compact view"),
    "hide_avatar": ("hide the avatar", "stop showing the avatar"),
    "speak_only": ("only speak",),
    "silent": ("stop speaking", "keep quiet"),
}


def _real_success(event: dict[str, Any]) -> bool:
    return str(event.get("status", "")).lower() in {"completed", "success", "succeeded"}


def _environment_from_evidence(
    events: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    active_capabilities: list[str],
    client: PresentationCapabilities | None,
    policy: PresentationPolicy,
) -> tuple[str, list[str]]:
    evidence_names = [
        str(event.get(key, ""))
        for event in events
        if _real_success(event)
        for key in ("capability_id", "capability", "event_type")
    ]
    evidence_names.extend(
        str(call.get("name", ""))
        for call in tool_calls
        if str(call.get("status", "")).lower() == "completed"
    )

    # A capability result is evidence only when an actual runtime event/tool
    # completed. A registry entry alone never makes a capability appear used.
    evidence = [name for name in evidence_names if name]
    for environment, signals in _ENVIRONMENT_SIGNALS:
        if (
            any(signal in name.lower() for signal in signals for name in evidence)
            and policy.allow_environment(environment, active_capabilities, client)
        ):
            return environment, evidence
    return "conversation", evidence


def _intent_mode(request: str, density: str) -> str:
    text = request.lower()
    if any(command in text for command in _PREFERENCE_COMMANDS["compact"]):
        return "compact"
    if "fullscreen" in text or "full screen" in text:
        return "fullscreen"
    if density == "minimal":
        return "compact"
    return "focused"


def _requested_override(request: str) -> str | None:
    lowered = request.lower()
    for preference, commands in _PREFERENCE_COMMANDS.items():
        if any(command in lowered for command in commands):
            return preference
    return None


class PresentationPlanner:
    """Builds plans only from observed execution results, user preference and client claims."""

    def __init__(
        self,
        context_service: PresentationContextService = presentation_context_service,
        policy: PresentationPolicy = presentation_policy,
        runtime: PresentationService | None = None,
    ) -> None:
        self.context_service = context_service
        self.policy = policy
        self.runtime = runtime or PresentationService()

    def plan(
        self,
        user_id: str,
        session_id: str,
        request: str,
        response: str,
        *,
        request_id: str,
        status: str,
        runtime_events: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        location_data_reference: bool = False,
    ) -> dict[str, Any]:
        events = list(runtime_events or [])
        calls = list(tool_calls or [])
        context = self.context_service.build(user_id, session_id, recent_events=events)
        context = self.policy.filter_context(context)
        client = self._client(context.get("device"))
        profile = context["preferences"]
        environment_type, evidence = _environment_from_evidence(
            events,
            calls,
            context["active_capabilities"] + [
                str(event.get("capability_id") or event.get("capability") or "")
                for event in events
                if _real_success(event)
            ],
            client,
            self.policy,
        )

        if status != "COMPLETED":
            environment_type = "conversation"
        environment_id = environment_type
        previous_environment = context.get("environment") or "conversation"
        mode = _intent_mode(request, str(profile.get("density", "balanced")))
        user_override = _requested_override(request)
        if user_override == "minimal":
            profile["density"] = "minimal"
            profile["avatar_preference"] = "minimal"
            mode = "compact"
        elif user_override == "detailed":
            profile["density"] = "detailed"
        elif user_override == "technical":
            profile["technical_detail"] = "advanced"
        elif user_override == "compact":
            mode = "compact"
        elif user_override == "hide_avatar":
            profile["avatar_preference"] = "hidden"
        elif user_override == "speak_only":
            profile["visual_preference"] = "low"
            profile["voice_preference"] = "continuous"
        elif user_override == "silent":
            profile["voice_preference"] = "off"
        self._persist_explicit_preference(user_id, user_override)

        event_evidence = bool(events or calls)
        activity_request = bool(re.search(r"\b(what are you doing|show me what|activity|progress)\b", request, re.I))
        if activity_request and event_evidence:
            environment_type = "observability"
            environment_id = "observability"
        if not self.policy.allow_environment(
            environment_type,
            context["active_capabilities"] + evidence,
            client,
        ):
            environment_type = "conversation"
            environment_id = "conversation"
        location_map_available = (
            environment_type == "geospatial"
            and location_data_reference
            and client is not None
            and "map.renderer" in client.renderers
            and self.policy.allow_visualization("map", client)
        )
        if environment_type == "geospatial" and not location_map_available:
            environment_type = "conversation"
            environment_id = "conversation"

        modality = ["text"]
        real_voice_event = any(
            str(event.get("event_type", "")).startswith("voice.")
            for event in events
        )
        if profile.get("voice_preference") in {"normal", "continuous"} or real_voice_event:
            modality.append("voice")
        if environment_type != "conversation" and client and set(
            client.primitives + client.media + client.spatial
        ):
            modality.append("visual")

        priority = [
            {
                "target": "assistant_response",
                "priority": 100,
                "reason": "The response was produced by the current chat turn.",
                "visibility": "primary",
            },
        ]
        if event_evidence:
            priority.append({
                "target": "runtime_activity",
                "priority": 80 if activity_request else 40,
                "reason": "Backed by runtime events or completed tool calls from this turn.",
                "visibility": "primary" if activity_request else "contextual",
            })

        timestamp = datetime.now(UTC)
        presentation_id = f"presentation-{uuid.uuid4().hex}"
        assistant_state = (
            "alert" if status != "COMPLETED"
            else "explaining" if response
            else "idle"
        )
        presence = PresenceController()
        presence.set_state(assistant_state)
        presence.set_visibility(
            "minimal" if profile.get("avatar_preference") in {"hidden", "minimal"} else "visible",
        )
        presence.transition(environment_type)
        intent = PresentationIntent(
            id=presentation_id,
            session_id=session_id,
            sequence=int(context["session"]["message_count"]),
            environment=EnvironmentIntent(
                id=environment_id,
                type=environment_type,
                purpose="Present the current JARVIS response and observed runtime results.",
                persistence="session",
                capabilities=evidence,
                state={"source": "observed_runtime" if evidence else "conversation"},
            ),
            mode=mode,
            focus=(
                FocusIntent(
                    target="current_location",
                    source=DataReference(
                        source="runtime",
                        resource=f"/api/v1/presentation/location/{presentation_id}",
                        freshness=DataFreshness(required=True, max_age_ms=120_000),
                    ),
                    priority=100,
                    reason="Authorized current location received during this chat request.",
                )
                if location_map_available
                else None
            ),
            visualizations=(
                [
                    VisualizationIntent(
                        id="current-location-map",
                        type="map",
                        data=DataReference(
                            source="runtime",
                            resource=f"/api/v1/presentation/location/{presentation_id}",
                            freshness=DataFreshness(required=True, max_age_ms=120_000),
                        ),
                        configuration={
                            "focus": "current_location",
                            "overlays": ["authorized_location_marker", "accuracy_radius"],
                            "interactions": ["zoom", "pan", "recenter"],
                        },
                    )
                ]
                if location_map_available
                else []
            ),
            assistant=AssistantPresentationState(
                state=presence.state.state,
                presence=(
                    "minimal" if profile.get("avatar_preference") in {"hidden", "minimal"}
                    else "avatar"
                ),
                message=response[:2048] if response else None,
            ),
            voice=VoicePresentationIntent(
                enabled=profile.get("voice_preference") != "off" or real_voice_event,
                state=(
                    "speaking" if any(event.get("event_type") == "voice.speaking.started" for event in events)
                    else "listening" if any(event.get("event_type") == "voice.state.listening" for event in events)
                    else "processing" if real_voice_event
                    else "silent"
                ),
                interruption="allowed",
            ),
            transitions=(
                [TransitionIntent(
                    source_environment=previous_environment,
                    target_environment=environment_id,
                    type="morph",
                    duration_ms=250,
                    reason="Environment selected from this turn's completed runtime evidence.",
                )]
                if environment_id != previous_environment
                else []
            ),
            emphasis=[
                EmphasisIntent(target=item["target"], level=item["priority"] / 100, reason=item["reason"])
                for item in priority
            ],
            context={
                "task_id": context["active_tasks"][0] if context["active_tasks"] else None,
                "selected": context.get("selected", []),
                "layout": LayoutIntent(
                    strategy="focus" if mode in {"focused", "immersive", "fullscreen"} else "adaptive",
                    priority=["assistant_response", "runtime_activity"],
                ),
                "preferences": {
                    "density": profile.get("density"),
                    "technicalDetail": profile.get("technical_detail"),
                    "visualPreference": profile.get("visual_preference"),
                    "avatarPreference": profile.get("avatar_preference"),
                },
            },
            lifecycle=PresentationLifecycle(state="active", updated_at=timestamp),
        )

        security_context = f"authctx-{uuid.uuid4().hex}"
        envelope = PresentationEnvelope(
            protocol="jarvis.presentation",
            version="1.0",
            intent=intent,
            issued_at=timestamp,
            source=PresentationSource(runtime="jarvis-core", request_id=request_id),
            security=PresentationSecurity(
                authorization_context=security_context,
                capabilities=evidence,
            ),
        )
        self.runtime.validate(envelope)

        plan = PresentationPlan(
            objective="Present JARVIS's response and observed results.",
            primary_environment=environment_type,
            secondary_environments=["conversation"] if environment_type != "conversation" else [],
            information_priority=[
                InformationPriority(
                    target=item["target"],
                    priority=item["priority"],
                    reason=item["reason"],
                    visibility=item["visibility"],
                )
                for item in priority
            ],
            modalities=modality,
            interaction_strategy="Use only client-supported interactions; backend policy remains authoritative.",
            assistant_presence=intent.assistant or AssistantPresentationState(state="idle"),
            fallback_strategy="Return to conversation when capability evidence or renderer support is absent.",
            user_override=user_override,
        )
        trace = PresentationTrace(
            presentation_id=intent.id,
            request_id=request_id,
            session_id=session_id,
            intent_version="1.0",
            capability_sources=evidence,
            timestamps=PresentationTraceTimestamps(created=timestamp),
        )
        presentation_events = self.runtime.adapt_runtime_events(envelope, events)

        self._persist(user_id, session_id, intent, previous_environment, request, user_override)
        return {
            "plan": plan.model_dump(mode="json", by_alias=True),
            "envelope": envelope.model_dump(mode="json", by_alias=True),
            "trace": trace.model_dump(mode="json", by_alias=True),
            "events": [
                event.model_dump(mode="json", by_alias=True)
                for event in presentation_events
            ],
        }

    @staticmethod
    def _persist_explicit_preference(user_id: str, override: str | None) -> None:
        if override is None:
            return
        from .schemas import PresentationPreferenceUpdate
        from .state import presentation_state_manager

        updates = {
            "minimal": {"density": "minimal", "avatar_preference": "minimal"},
            "detailed": {"density": "detailed"},
            "technical": {"technical_detail": "advanced"},
            "visual": {"visual_preference": "high"},
            "compact": {"density": "minimal"},
            "hide_avatar": {"avatar_preference": "hidden"},
            "speak_only": {"visual_preference": "low", "voice_preference": "continuous"},
            "silent": {"voice_preference": "off"},
        }
        values = updates.get(override)
        if values:
            presentation_state_manager.update_preferences(
                user_id,
                PresentationPreferenceUpdate.model_validate(values),
            )

    @staticmethod
    def _client(value: Any) -> PresentationCapabilities | None:
        if not isinstance(value, dict):
            return None
        try:
            return PresentationCapabilities.model_validate(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _persist(
        user_id: str,
        session_id: str,
        intent: PresentationIntent,
        previous_environment: str,
        reason: str,
        user_override: str | None,
    ) -> None:
        state_store = get_store("presentation_state")
        state_key = f"{user_id}:{session_id}"
        state_store.save_key(state_key, {
            "presentation_id": intent.id,
            "environment": intent.environment.type,
            "task_id": intent.context.task_id if intent.context else None,
            "selected": intent.context.selected if intent.context else [],
            "updated_at": datetime.now(UTC).isoformat(),
        })
        history_store = get_store("presentation_history")
        history_key = state_key
        history = history_store.load().get(history_key, [])
        history.append({
            "presentation_id": intent.id,
            "environment": intent.environment.type,
            "from_environment": previous_environment,
            "reason": reason[:512],
            "started_at": datetime.now(UTC).isoformat(),
            "user_override": user_override is not None,
        })
        history_store.save_key(history_key, history[-100:])


presentation_planner = PresentationPlanner()
