"""Approved semantic renderer registry; implementations are resolved by clients."""

from __future__ import annotations

from typing import Any

from ..capability import CapabilityRegistry, get_registry
from .schemas import (
    CapabilityOutput,
    CapabilityPresentationDefinition,
    EnvironmentBinding,
    EnvironmentDefinition,
    PresentationCapabilityBinding,
    PresentationFallbackChain,
    RendererDefinition,
    VisualizationBinding,
    VisualizationDataRequirement,
    VisualizationDefinition,
)

RENDERERS: tuple[RendererDefinition, ...] = (
    RendererDefinition(
        type="map.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "automotive"],
        supported_primitives=["map", "marker", "route", "status", "text"],
        capabilities=["geospatial", "navigation", "interactive_map"],
        presentation_types=["map", "marker", "route", "status", "text"],
    ),
    RendererDefinition(
        type="image.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "ar", "vr"],
        supported_primitives=["image", "panel", "source", "control"],
        capabilities=["image", "media"],
        presentation_types=["image"],
    ),
    RendererDefinition(
        type="video.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "ar", "vr"],
        supported_primitives=["video", "panel", "source", "control"],
        capabilities=["video", "media"],
        presentation_types=["video"],
    ),
    RendererDefinition(
        type="timeline.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "automotive"],
        supported_primitives=["timeline", "status", "text", "source"],
        capabilities=["activity", "timeline"],
        presentation_types=["timeline", "status"],
    ),
    RendererDefinition(
        type="avatar.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "ar", "vr"],
        supported_primitives=["avatar", "text", "status"],
        capabilities=["assistant_presence"],
        presentation_types=["avatar"],
    ),
    RendererDefinition(
        type="text.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "automotive", "ar", "vr"],
        supported_primitives=["text"],
        capabilities=["conversation", "text"],
        presentation_types=["text"],
    ),
    RendererDefinition(
        type="audio.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "automotive"],
        supported_primitives=["audio", "control", "caption"],
        capabilities=["voice", "audio"],
        presentation_types=["audio"],
    ),
    RendererDefinition(
        type="document.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet"],
        supported_primitives=["document", "text", "source"],
        capabilities=["document", "research"],
        presentation_types=["document"],
    ),
    RendererDefinition(
        type="chart.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "tablet"],
        supported_primitives=["chart", "panel", "source"],
        capabilities=["chart", "structured_data"],
        presentation_types=["chart"],
    ),
    RendererDefinition(
        type="status.renderer",
        version="1.0",
        supported_clients=["web", "desktop", "mobile", "tablet", "automotive"],
        supported_primitives=["status", "text", "panel"],
        capabilities=["status", "runtime"],
        presentation_types=["status"],
    ),
)

FALLBACKS: dict[str, tuple[str, str]] = {
    "globe": ("map.renderer", "A globe renderer is not registered; use a map renderer if supported."),
    "model3d": ("image.renderer", "A 3D model renderer is not registered; use an image renderer if supported."),
    "spatial": ("map.renderer", "Spatial rendering is not registered; use a compatible 2D renderer if supported."),
    "satellite": ("map.renderer", "Satellite imagery is not registered; a standard map renderer is available."),
    "terrain": ("map.renderer", "Terrain rendering is not registered; a standard map renderer is available."),
    "3d_world": ("map.renderer", "3D world rendering is not registered; use a standard map renderer if supported."),
}

_BUILTIN_BINDINGS: dict[str, dict[str, Any]] = {
    "brain": {
        "environments": [("conversation", "primary", 100)],
        "visualizations": [("text", ["text", "structured_data"], 90)],
        "modalities": ["text"],
    },
    "conversation": {
        "environments": [("conversation", "primary", 100)],
        "visualizations": [("text", ["text"], 100)],
        "modalities": ["text", "voice"],
    },
    "voice": {
        "environments": [("voice", "primary", 100), ("conversation", "secondary", 70)],
        "visualizations": [("audio", ["audio"], 100), ("text", ["text"], 70)],
        "modalities": ["voice", "text", "audio"],
    },
    "vision": {
        "environments": [("visual", "primary", 100), ("conversation", "secondary", 70)],
        "visualizations": [("text", ["text", "structured_data"], 100)],
        "modalities": ["text", "visual", "image"],
    },
    "image.generate": {
        "environments": [("visual", "primary", 100), ("creative", "secondary", 70)],
        "visualizations": [("image", ["image"], 100)],
        "modalities": ["image", "visual", "text"],
    },
    "provider": {
        "environments": [("conversation", "primary", 80), ("observability", "contextual", 50)],
        "visualizations": [("status", ["structured_data", "event"], 80)],
        "modalities": ["text", "visual"],
    },
    "browser": {
        "environments": [("research", "primary", 90), ("conversation", "secondary", 60)],
        "visualizations": [("document", ["document"], 90), ("text", ["text"], 70)],
        "modalities": ["text", "visual"],
        "fallbacks": [("document", ["text"], "Use a textual rendering when document rendering is unavailable.")],
    },
    "location.current": {
        "environments": [("geospatial", "primary", 100), ("conversation", "secondary", 50)],
        "visualizations": [("map", ["location"], 100), ("text", ["location"], 50)],
        "modalities": ["text", "visual", "map"],
        "fallbacks": [("map", ["text"], "Use a truthful conversational response when map rendering is unavailable.")],
    },
    "task": {
        "environments": [("tasks", "primary", 100), ("observability", "secondary", 60)],
        "visualizations": [("timeline", ["task", "event"], 100), ("status", ["task"], 80)],
        "modalities": ["text", "visual"],
        "fallbacks": [("timeline", ["status"], "Use task status when timeline rendering is unavailable.")],
    },
    "memory": {
        "environments": [("knowledge", "primary", 80), ("conversation", "secondary", 60)],
        "visualizations": [("text", ["text", "structured_data"], 80)],
        "modalities": ["text"],
    },
    "knowledge.search": {
        "environments": [("knowledge", "primary", 90), ("research", "secondary", 70)],
        "visualizations": [("document", ["document"], 90), ("text", ["text", "structured_data"], 80)],
        "modalities": ["text", "visual"],
        "fallbacks": [("document", ["text"], "Use a textual summary when document rendering is unavailable.")],
    },
    "tool": {
        "environments": [("observability", "contextual", 70), ("conversation", "secondary", 50)],
        "visualizations": [("status", ["event", "structured_data"], 70)],
        "modalities": ["text", "visual"],
    },
    "research.cortex": {
        "environments": [("research", "primary", 90), ("learning", "secondary", 60)],
        "visualizations": [("document", ["document"], 85), ("timeline", ["event"], 70)],
        "modalities": ["text", "visual"],
    },
    "science.engine": {
        "environments": [("knowledge", "secondary", 60)],
        "visualizations": [("chart", ["structured_data"], 80), ("text", ["text", "structured_data"], 70)],
        "modalities": ["text", "visual"],
    },
    "bio.learner": {
        "environments": [("learning", "primary", 90)],
        "visualizations": [("timeline", ["event", "task"], 80), ("chart", ["structured_data"], 70)],
        "modalities": ["text", "visual"],
    },
    "tech.evolution": {
        "environments": [("learning", "secondary", 60), ("research", "secondary", 60)],
        "visualizations": [("chart", ["structured_data"], 80), ("timeline", ["event"], 70)],
        "modalities": ["text", "visual"],
    },
}


class PresentationRegistry:
    """Validated presentation metadata attached to the existing capability registry."""

    def __init__(
        self,
        capabilities: CapabilityRegistry | None = None,
        renderers: tuple[RendererDefinition, ...] = RENDERERS,
    ) -> None:
        self.capabilities = capabilities or get_registry()
        self.renderers = renderers
        self._renderer_by_type = {renderer.type: renderer for renderer in renderers}
        self._environments: dict[str, EnvironmentDefinition] = {}
        self._visualizations: dict[str, VisualizationDefinition] = {}

    def register_environment(self, definition: EnvironmentDefinition) -> None:
        validated = EnvironmentDefinition.model_validate(definition)
        existing = self._environments.get(validated.id)
        if existing is not None and existing != validated:
            raise ValueError(f"Environment already registered with a different definition: {validated.id}")
        self._environments[validated.id] = validated

    def register_visualization(self, definition: VisualizationDefinition) -> None:
        validated = VisualizationDefinition.model_validate(definition)
        if validated.renderer_id not in self._renderer_by_type:
            raise ValueError(f"Renderer is not approved: {validated.renderer_id}")
        existing = self._visualizations.get(validated.type)
        if existing is not None and existing != validated:
            raise ValueError(
                f"Visualization already registered with a different definition: {validated.type}",
            )
        self._visualizations[validated.type] = validated

    def register_renderer(self, definition: RendererDefinition) -> None:
        validated = RendererDefinition.model_validate(definition)
        existing = self._renderer_by_type.get(validated.type)
        if existing is not None and existing != validated:
            raise ValueError(f"Renderer already registered with a different definition: {validated.type}")
        self._renderer_by_type[validated.type] = validated
        self.renderers = tuple(self._renderer_by_type.values())

    def register_capability_binding(
        self,
        capability_id: str,
        binding: PresentationCapabilityBinding,
    ) -> None:
        capability = self.capabilities.get(capability_id)
        if capability is None:
            raise KeyError(f"Unknown capability: {capability_id}")
        validated = PresentationCapabilityBinding.model_validate(binding)
        metadata = self.capabilities.get_metadata(capability_id)
        declared_outputs = {
            output["type"]
            for output in metadata.get("outputs", [])
            if isinstance(output, dict) and isinstance(output.get("type"), str)
        }
        if not declared_outputs:
            raise ValueError(f"Capability {capability_id} must declare outputs before presentation bindings.")
        used_outputs = {
            output_type
            for visualization in validated.visualizations
            for output_type in (
                visualization.input_types
                + [requirement.output_type for requirement in visualization.data_requirements]
            )
        }
        undeclared_outputs = used_outputs - declared_outputs
        if undeclared_outputs:
            raise ValueError(
                f"Presentation binding references undeclared outputs: {sorted(undeclared_outputs)}",
            )
        registered_types = {
            presentation_type
            for renderer in self.renderers
            for presentation_type in renderer.presentation_types
        }
        unknown = {
            visualization.type
            for visualization in validated.visualizations
            if visualization.type not in registered_types
        }
        if unknown:
            raise ValueError(f"No approved renderer for presentation type(s): {sorted(unknown)}")
        for environment in validated.environments:
            self.register_environment(EnvironmentDefinition(
                id=environment.environment,
                description=f"Environment for capability {capability_id}.",
            ))
        for visualization in validated.visualizations:
            renderer = next(
                renderer
                for renderer in self.renderers
                if visualization.type in renderer.presentation_types
            )
            self.register_visualization(VisualizationDefinition(
                type=visualization.type,
                renderer_id=renderer.type,
                data_requirements=visualization.data_requirements,
            ))
        self.capabilities.register_presentation_binding(capability_id, validated)

    def get_capability_bindings(self, capability_id: str) -> list[PresentationCapabilityBinding]:
        binding = self.capabilities.get_metadata(capability_id).get("presentation")
        return [PresentationCapabilityBinding.model_validate(binding)] if binding else []

    def get_renderer(self, renderer_id: str) -> RendererDefinition | None:
        return self._renderer_by_type.get(renderer_id)

    def definitions(self) -> list[CapabilityPresentationDefinition]:
        definitions: list[CapabilityPresentationDefinition] = []
        for capability_id in self.capabilities.list_all():
            capability = self.capabilities.get(capability_id)
            if capability is None:
                continue
            metadata = self.capabilities.get_metadata(capability_id)
            raw_binding = metadata.get("presentation")
            if raw_binding is None:
                continue
            definitions.append(CapabilityPresentationDefinition(
                id=capability_id,
                version=capability.version,
                name=capability_id,
                description=str(metadata.get("description", capability_id)),
                category=capability.category,
                outputs=metadata.get("outputs", []),
                presentation=PresentationCapabilityBinding.model_validate(raw_binding),
                operational_status=capability.status.value,
            ))
        return definitions


_BUILTIN_OUTPUTS: dict[str, tuple[str, ...]] = {
        "brain": ("text", "structured_data"),
        "conversation": ("text",),
        "voice": ("audio", "text"),
        "vision": ("text", "structured_data"),
        "image.generate": ("image",),
        "provider": ("structured_data", "event"),
        "browser": ("document", "text"),
        "location.current": ("location",),
        "task": ("task", "event"),
        "memory": ("text", "structured_data"),
        "knowledge.search": ("text", "structured_data"),
        "tool": ("structured_data", "event"),
        "research.cortex": ("document", "event"),
        "science.engine": ("structured_data", "text"),
        "bio.learner": ("task", "event", "structured_data"),
        "tech.evolution": ("event", "structured_data"),
}


def register_builtin_capability_bindings(
    capabilities: CapabilityRegistry | None = None,
) -> None:
    registry = PresentationRegistry(capabilities)
    for capability_id, definition in _BUILTIN_BINDINGS.items():
        if registry.capabilities.get(capability_id) is None:
            continue
        metadata = registry.capabilities.get_metadata(capability_id)
        if not metadata.get("outputs"):
            sensitivity = "sensitive" if capability_id in {"memory", "voice"} else "internal"
            registry.capabilities.register_output_contract(
                capability_id,
                [
                    CapabilityOutput(
                        id=f"{capability_id}.{output_type}",
                        type=output_type,
                        sensitivity=sensitivity,
                    )
                    for output_type in _BUILTIN_OUTPUTS.get(capability_id, ("structured_data",))
                ],
            )
        if registry.get_capability_bindings(capability_id):
            continue
        environments = [
            EnvironmentBinding(environment=environment, suitability=suitability, priority=priority)
            for environment, suitability, priority in definition["environments"]
        ]
        visualizations = [
            VisualizationBinding(
                type=visualization,
                input_types=output_types,
                data_requirements=[
                    VisualizationDataRequirement(output_type=output_type, required=True)
                    for output_type in output_types
                ],
                priority=priority,
            )
            for visualization, output_types, priority in definition["visualizations"]
        ]
        registry.register_capability_binding(
            capability_id,
            PresentationCapabilityBinding(
                environments=environments,
                visualizations=visualizations,
                modalities=definition["modalities"],
                fallbacks=[
                    PresentationFallbackChain(
                        preferred=preferred,
                        alternatives=alternatives,
                        reason=reason,
                        requirements=[
                            VisualizationDataRequirement(output_type=output_type, required=True)
                            for alternative in alternatives
                            for output_type in next(
                                (
                                    outputs
                                    for visualization, outputs, _priority in definition["visualizations"]
                                    if visualization == alternative
                                ),
                                [],
                            )
                        ],
                    )
                    for preferred, alternatives, reason in definition.get("fallbacks", [])
                ],
            ),
        )


presentation_registry = PresentationRegistry()
