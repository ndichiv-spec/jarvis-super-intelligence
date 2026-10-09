"""Presentation safety policy; it never authorizes execution or grants permissions."""

from __future__ import annotations

from typing import Any

from .schemas import DataReference, PresentationCapabilities

_ENVIRONMENT_CAPABILITY = {
    "geospatial": ("location", "geography", "map"),
    "navigation": ("navigation", "routing", "map"),
    "research": ("search", "browser", "research", "web"),
    "communications": ("email", "message", "calendar", "communication"),
    "visual": ("image", "vision", "media"),
    "media": ("image", "video", "audio", "media"),
    "device": ("device", "computer"),
    "voice": ("voice", "speech"),
    "knowledge": ("knowledge", "memory"),
    "tasks": ("task", "agent"),
    "automation": ("automation",),
    "learning": ("learning", "training", "research"),
    "system": ("system", "runtime"),
    "observability": ("monitor", "observability", "runtime", "tool"),
    "creative": ("image", "media", "creative"),
}
_ENVIRONMENT_PRIMITIVE = {
    "geospatial": ("map",),
    "navigation": ("map",),
    "visual": ("image", "video"),
    "media": ("image", "video"),
    "device": ("device", "status"),
    "observability": ("timeline", "status"),
    "voice": ("avatar", "text"),
}


class PresentationPolicy:
    """Filters expression choices against real data and the negotiated client."""

    def allow_environment(
        self,
        environment: str,
        active_capabilities: list[str],
        client: PresentationCapabilities | None,
    ) -> bool:
        if environment == "conversation":
            return True
        if client and client.environments and environment not in client.environments:
            return False
        required_primitives = _ENVIRONMENT_PRIMITIVE.get(environment, ())
        if client and required_primitives and not set(required_primitives).intersection(
            client.primitives + client.media + client.spatial
        ):
            return False
        terms = _ENVIRONMENT_CAPABILITY.get(environment, ())
        return any(
            term in capability.lower()
            for term in terms
            for capability in active_capabilities
        )

    def allow_visualization(
        self,
        visualization: str,
        client: PresentationCapabilities | None,
    ) -> bool:
        if client is None:
            return False
        return visualization in set(client.primitives + client.media + client.spatial)

    def allow_data_source(self, reference: DataReference) -> bool:
        if reference.source in {"device", "connector"}:
            return bool(reference.authorization)
        return reference.source in {
            "runtime", "capability", "provider", "user", "memory", "web", "generated",
        }

    def allow_interaction(
        self,
        action: str,
        client: PresentationCapabilities | None,
    ) -> bool:
        if client is None:
            return False
        return action in set(client.input + client.output + client.primitives)

    def require_confirmation(self, _action: str) -> bool:
        return True

    def filter_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Expose a sanitized, bounded context to planning and downstream diagnostics."""
        return {
            **context,
            "recent_events": context.get("recent_events", [])[-50:],
            "active_capabilities": context.get("active_capabilities", [])[:500],
        }


presentation_policy = PresentationPolicy()
