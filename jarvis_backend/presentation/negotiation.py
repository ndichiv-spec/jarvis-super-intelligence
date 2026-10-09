"""Capability negotiation between semantic intents and approved renderers."""

from __future__ import annotations

from .registry import FALLBACKS, PresentationRegistry, presentation_registry
from .schemas import (
    PresentationCapabilities,
    PresentationFallback,
    RendererDefinition,
    RendererNegotiation,
)


def negotiate_renderers(
    client: PresentationCapabilities,
    registry: PresentationRegistry = presentation_registry,
) -> RendererNegotiation:
    client_primitives = set(client.primitives) | set(client.media) | set(client.spatial)
    client_features = client_primitives | set(client.environments)
    renderers: list[RendererDefinition] = []
    supported_names: set[str] = set()
    client_platforms = set(client.surfaces)
    if client.platform != "unknown":
        client_platforms.add(client.platform)
    for renderer in registry.renderers:
        if not client_platforms.intersection(renderer.supported_clients):
            continue
        if client.renderers and renderer.type not in client.renderers:
            continue
        supported_primitives = client_primitives.intersection(renderer.supported_primitives)
        if not supported_primitives:
            continue
        supported_names.update(supported_primitives)
        supported_names.update(
            presentation_type
            for presentation_type in renderer.presentation_types
            if presentation_type in client_primitives
        )
        renderers.append(renderer.model_copy(update={
            "supported_primitives": sorted(supported_primitives),
            "capabilities": sorted(client_features.intersection(renderer.capabilities)),
        }))

    fallbacks: list[PresentationFallback] = []
    for requested in sorted(client.environments + client.primitives + client.media + client.spatial):
        if requested in supported_names:
            continue
        fallback = FALLBACKS.get(requested)
        if fallback is None:
            continue
        selected, reason = fallback
        matching = next((renderer for renderer in renderers if renderer.type == selected), None)
        if matching:
            fallbacks.append(PresentationFallback(
                requested=requested,
                available=matching.supported_primitives,
                selected=selected,
                reason=reason,
            ))

    return RendererNegotiation(
        client_id=client.client_id,
        renderers=renderers,
        fallbacks=fallbacks,
    )
