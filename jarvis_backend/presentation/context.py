"""Build presentation context from owned sessions and current runtime evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..capability import get_registry
from ..chat_service import chat_service
from ..core import get_store
from .schemas import PresentationCapabilities

DEFAULT_PROFILE: dict[str, Any] = {
    "density": "balanced",
    "visual_preference": "normal",
    "voice_preference": "minimal",
    "avatar_preference": "minimal",
    "motion_preference": "normal",
    "technical_detail": "standard",
    "adaptive_presentation": True,
    "accessibility": {},
}


class PresentationContextService:
    """Assemble facts for a presentation decision without consulting another AI."""

    def build(
        self,
        user_id: str,
        session_id: str,
        *,
        recent_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        session = chat_service.get_session(user_id, session_id)
        preferences = get_store("presentation_preferences").load().get(user_id, {})
        endpoint_records = get_store("endpoints").reload().values()
        active_endpoints = [
            endpoint
            for endpoint in endpoint_records
            if endpoint.get("owner_id") == user_id
            and session_id in endpoint.get("active_sessions", [])
            and endpoint.get("connectivity") == "connected"
            and (
                datetime.now(UTC)
                - datetime.fromisoformat(endpoint["last_seen"]).astimezone(UTC)
            ).total_seconds() <= 90
        ]
        endpoint = max(active_endpoints, key=lambda item: item["last_seen"], default=None)
        capabilities = (
            endpoint.get("capabilities")
            if endpoint
            else get_store("presentation_client_capabilities").load().get(user_id)
        )
        capability_registry = get_registry()
        messages = session.get("messages") or []
        state = get_store("presentation_state").load().get(
            self.state_key(user_id, session_id),
            {},
        )
        return {
            "user": {"id": user_id, "profile": {**DEFAULT_PROFILE, **preferences}},
            "session": {
                "id": session_id,
                "updated_at": session.get("updated_at"),
                "message_count": len(messages),
            },
            "conversation": {
                "recent_messages": [
                    {
                        "role": message.get("role"),
                        "content": message.get("content"),
                        "status": message.get("status"),
                    }
                    for message in messages[-8:]
                    if message.get("role") in {"user", "assistant"}
                ],
                "last_user_message": next(
                    (
                        message.get("content", "")
                        for message in reversed(messages)
                        if message.get("role") == "user"
                    ),
                    "",
                ),
            },
            "device": capabilities,
            "active_capabilities": capability_registry.list_all(),
            "active_tasks": [state["task_id"]] if state.get("task_id") else [],
            "recent_events": list(recent_events or [])[-50:],
            "environment": state.get("environment", "conversation"),
            "selected": state.get("selected", []),
            "accessibility": preferences.get("accessibility", {}),
            "preferences": {**DEFAULT_PROFILE, **preferences},
        }

    @staticmethod
    def state_key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    def save_client_capabilities(
        self,
        user_id: str,
        capabilities: PresentationCapabilities,
    ) -> None:
        store = get_store("presentation_client_capabilities")
        store.save_key(user_id, capabilities.model_dump(mode="json", by_alias=True))


presentation_context_service = PresentationContextService()
