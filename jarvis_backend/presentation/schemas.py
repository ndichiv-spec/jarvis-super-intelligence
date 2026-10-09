"""Serializable semantic presentation contract, independent of any client framework."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_camel

PRESENTATION_PROTOCOL = "jarvis.presentation"
PRESENTATION_VERSION = "1.0"

Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")]
CapabilityName = Annotated[str, Field(min_length=1, max_length=160)]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


class DataFreshness(ContractModel):
    required: bool = False
    max_age_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class DataReference(ContractModel):
    source: Literal[
        "runtime", "capability", "connector", "provider", "device",
        "user", "memory", "web", "generated",
    ]
    resource: Annotated[str, Field(min_length=1, max_length=512)]
    query: dict[str, Any] | None = None
    freshness: DataFreshness | None = None
    authorization: Annotated[str, Field(max_length=512)] | None = None

    @model_validator(mode="after")
    def require_authorization_reference_for_restricted_sources(self) -> DataReference:
        if self.source in {"device", "connector"} and not self.authorization:
            raise ValueError(f"{self.source} data references require an authorization context.")
        if self.authorization and re.search(
            r"(bearer\s|api[_-]?key|password|secret|token=)",
            self.authorization,
            re.IGNORECASE,
        ):
            raise ValueError("Data authorization must be an opaque reference, not a credential.")
        return self


class CameraIntent(ContractModel):
    target: str | None = Field(default=None, max_length=256)
    position: dict[str, float] | None = None
    orientation: dict[str, float] | None = None
    zoom: float | None = Field(default=None, ge=0, le=100)


class AnimationIntent(ContractModel):
    type: Literal["fade", "move", "pulse", "draw", "none"]
    duration_ms: int | None = Field(default=None, ge=0, le=60_000)
    easing: Literal["linear", "ease", "ease-in", "ease-out", "ease-in-out"] = "ease"


class VisibilityRule(ContractModel):
    condition: Literal["always", "when_data_available", "when_authorized", "when_focused"] = "always"
    data: DataReference | None = None


SceneNodeType = Literal[
    "group", "text", "image", "video", "map", "globe", "model3d", "chart",
    "timeline", "panel", "avatar", "device", "document", "source", "control",
    "status", "custom",
]


class SceneNode(ContractModel):
    id: Identifier
    type: SceneNodeType
    children: list[SceneNode] = Field(default_factory=list, max_length=100)
    data: DataReference | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    visibility: VisibilityRule | None = None
    interaction: list[Identifier] = Field(default_factory=list, max_length=50)
    animation: AnimationIntent | None = None

    @model_validator(mode="after")
    def validate_composition(self) -> SceneNode:
        if self.type != "group" and self.children:
            raise ValueError("Only group scene nodes can contain children.")
        if self.type in {"image", "video", "map", "globe", "model3d", "chart", "timeline", "device", "document"} and not self.data:
            raise ValueError(f"{self.type} scene nodes must reference real data.")
        return self


SceneNode.model_rebuild()


class SceneGraph(ContractModel):
    root: SceneNode


class EnvironmentIntent(ContractModel):
    id: Identifier
    type: Literal[
        "conversation", "geospatial", "navigation", "research", "communications",
        "visual", "media", "device", "voice", "knowledge", "tasks", "automation",
        "learning", "system", "observability", "creative",
    ]
    title: str | None = Field(default=None, max_length=256)
    purpose: str | None = Field(default=None, max_length=1024)
    persistence: Literal["ephemeral", "session", "persistent"] = "session"
    capabilities: list[CapabilityName] = Field(default_factory=list, max_length=100)
    state: dict[str, Any] = Field(default_factory=dict)


class FocusIntent(ContractModel):
    target: Identifier
    source: DataReference | None = None
    priority: int = Field(default=0, ge=0, le=100)
    reason: str | None = Field(default=None, max_length=1024)
    camera: CameraIntent | None = None


class VisualizationIntent(ContractModel):
    id: Identifier
    type: Literal[
        "map", "satellite", "terrain", "globe", "3d_world", "chart", "timeline",
        "network", "image", "video", "document", "spatial",
    ]
    data: DataReference
    configuration: dict[str, Any] = Field(default_factory=dict)
    camera: CameraIntent | None = None
    overlays: list[OverlayIntent] = Field(default_factory=list, max_length=100)


class MediaControls(ContractModel):
    play: bool = False
    pause: bool = False
    seek: bool = False
    volume: bool = False


class MediaSource(ContractModel):
    kind: Literal["data", "uri"]
    data: DataReference | None = None
    uri: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_source(self) -> MediaSource:
        if (self.kind == "data") != (self.data is not None):
            raise ValueError("Data media sources require data and cannot include a URI.")
        if (self.kind == "uri") != (self.uri is not None):
            raise ValueError("URI media sources require an HTTPS URI and cannot include data.")
        return self


class MediaIntent(ContractModel):
    id: Identifier
    type: Literal["image", "video", "audio", "model3d"]
    source: MediaSource
    presentation: Literal["inline", "focused", "immersive", "background", "spatial"]
    controls: MediaControls | None = None


class OverlayIntent(ContractModel):
    id: Identifier
    type: Literal[
        "marker", "route", "notification", "caption", "source", "measurement",
        "status", "control", "assistant",
    ]
    anchor: Identifier | None = None
    data: DataReference | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class CapabilityAction(ContractModel):
    capability: CapabilityName
    action: CapabilityName
    resource: str | None = Field(default=None, max_length=512)


class InteractionIntent(ContractModel):
    id: Identifier
    type: Literal[
        "select", "focus", "zoom", "pan", "rotate", "navigate", "expand",
        "collapse", "play", "pause", "scrub", "command", "approve", "deny",
        "input", "voice",
    ]
    action: CapabilityAction
    requires_confirmation: bool = True


class AudioPresentationState(ContractModel):
    source: MediaSource | None = None
    synchronized: bool = False


class AssistantPresentationState(ContractModel):
    state: Literal[
        "idle", "listening", "thinking", "searching", "observing", "speaking",
        "working", "creating", "navigating", "learning", "explaining",
        "waiting_for_permission", "alert", "offline",
    ]
    presence: Literal["minimal", "avatar", "full", "spatial"] = "minimal"
    expression: str | None = Field(default=None, max_length=128)
    emphasis: float | None = Field(default=None, ge=0, le=1)
    message: str | None = Field(default=None, max_length=2048)
    audio: AudioPresentationState | None = None


class VoicePresentationIntent(ContractModel):
    enabled: bool
    state: Literal["silent", "listening", "processing", "speaking"]
    transcript: str | None = Field(default=None, max_length=4000)
    emphasis: list[str] = Field(default_factory=list, max_length=100)
    interruption: Literal["allowed", "blocked"] = "allowed"


class SpatialAnchor(ContractModel):
    id: Identifier
    target: str | None = Field(default=None, max_length=256)
    position: dict[str, float] | None = None
    coordinate_system: str | None = Field(default=None, max_length=128)


class SpatialPresentationIntent(ContractModel):
    enabled: bool
    coordinate_system: str | None = Field(default=None, max_length=128)
    anchors: list[SpatialAnchor] = Field(default_factory=list, max_length=100)
    depth: Literal["flat", "layered", "volumetric"] = "flat"
    field_of_view: float | None = Field(default=None, gt=0, le=360)
    world_locked: bool = False


class TransitionIntent(ContractModel):
    source_environment: Identifier | None = None
    target_environment: Identifier | None = None
    type: Literal["fade", "expand", "collapse", "morph", "zoom", "slide", "spatial"]
    duration_ms: int | None = Field(default=None, ge=0, le=60_000)
    reason: str | None = Field(default=None, max_length=1024)


class EmphasisIntent(ContractModel):
    target: Identifier
    level: float = Field(ge=0, le=1)
    reason: str | None = Field(default=None, max_length=512)


class LayoutRegion(ContractModel):
    id: Identifier
    content: Identifier
    priority: int = Field(default=0, ge=0, le=100)


class LayoutIntent(ContractModel):
    strategy: Literal["adaptive", "split", "focus", "stack", "spatial", "freeform"] = "adaptive"
    regions: list[LayoutRegion] = Field(default_factory=list, max_length=32)
    priority: list[Identifier] = Field(default_factory=list, max_length=32)


class PresentationContext(ContractModel):
    task_id: Identifier | None = None
    selected: list[Identifier] = Field(default_factory=list, max_length=100)
    layout: LayoutIntent | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)


class PresentationConstraints(ContractModel):
    required_capabilities: list[CapabilityName] = Field(default_factory=list, max_length=100)
    excluded_capabilities: list[CapabilityName] = Field(default_factory=list, max_length=100)
    max_complexity: Literal["low", "medium", "high"] | None = None
    accessibility: list[CapabilityName] = Field(default_factory=list, max_length=100)


class PresentationLifecycle(ContractModel):
    state: Literal[
        "create", "active", "updating", "transitioning", "suspended",
        "resumed", "completed", "closed",
    ]
    updated_at: datetime | None = None


class PresentationIntent(ContractModel):
    id: Identifier
    session_id: Identifier
    sequence: int = Field(ge=0)
    environment: EnvironmentIntent
    mode: Literal["ambient", "compact", "focused", "immersive", "spatial", "fullscreen"] = "focused"
    focus: FocusIntent | None = None
    scene: SceneGraph | None = None
    visualizations: list[VisualizationIntent] = Field(default_factory=list, max_length=100)
    media: list[MediaIntent] = Field(default_factory=list, max_length=100)
    overlays: list[OverlayIntent] = Field(default_factory=list, max_length=100)
    interactions: list[InteractionIntent] = Field(default_factory=list, max_length=100)
    assistant: AssistantPresentationState | None = None
    voice: VoicePresentationIntent | None = None
    spatial: SpatialPresentationIntent | None = None
    transitions: list[TransitionIntent] = Field(default_factory=list, max_length=32)
    emphasis: list[EmphasisIntent] = Field(default_factory=list, max_length=100)
    context: PresentationContext | None = None
    constraints: PresentationConstraints | None = None
    lifecycle: PresentationLifecycle | None = None


class PresentationSecurity(ContractModel):
    authorization_context: Annotated[str, Field(min_length=1, max_length=512)]
    capabilities: list[CapabilityName] = Field(default_factory=list, max_length=100)


class PresentationSource(ContractModel):
    runtime: Identifier
    request_id: Identifier


class PresentationEnvelope(ContractModel):
    protocol: Literal["jarvis.presentation"]
    version: Annotated[str, Field(min_length=1, max_length=32)]
    intent: PresentationIntent
    issued_at: datetime
    source: PresentationSource
    security: PresentationSecurity

    @field_validator("version")
    @classmethod
    def validate_version_syntax(cls, value: str) -> str:
        if len(value.split(".")) != 2 or not all(part.isdigit() for part in value.split(".")):
            raise ValueError("Presentation version must use major.minor syntax.")
        return value

    @model_validator(mode="after")
    def require_safe_authorization_reference(self) -> PresentationEnvelope:
        reference = self.security.authorization_context
        if re.search(r"(bearer\s|api[_-]?key|password|secret|token=)", reference, re.IGNORECASE):
            raise ValueError("Authorization context must be an opaque reference, not a credential.")
        return self


class PresentationCapabilities(ContractModel):
    client_id: Identifier
    runtime_version: str | None = Field(default=None, max_length=64)
    surfaces: list[CapabilityName] = Field(default_factory=list, max_length=100)
    renderers: list[CapabilityName] = Field(default_factory=list, max_length=100)
    platform: Literal[
        "web", "desktop", "mobile", "tablet", "automotive", "ar", "vr", "unknown",
    ] = "unknown"
    environments: list[CapabilityName] = Field(default_factory=list, max_length=100)
    primitives: list[CapabilityName] = Field(default_factory=list, max_length=200)
    media: list[CapabilityName] = Field(default_factory=list, max_length=100)
    spatial: list[CapabilityName] = Field(default_factory=list, max_length=100)
    input: list[CapabilityName] = Field(default_factory=list, max_length=100)
    output: list[CapabilityName] = Field(default_factory=list, max_length=100)
    constraints: dict[str, Any] = Field(default_factory=dict)
    performance_profile: str | None = Field(default=None, max_length=64)
    accessibility: dict[str, Any] = Field(default_factory=dict)


class RendererDefinition(ContractModel):
    type: Identifier
    version: str
    supported_clients: list[CapabilityName]
    supported_primitives: list[CapabilityName]
    capabilities: list[CapabilityName]
    constraints: dict[str, Any] = Field(default_factory=dict)
    presentation_types: list[CapabilityName] = Field(default_factory=list)
    required_capabilities: list[CapabilityName] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list, max_length=50)
    security_class: Literal["standard", "sensitive", "restricted"] = "standard"


class CapabilityOutput(ContractModel):
    id: Identifier
    type: Literal[
        "text", "structured_data", "image", "video", "audio", "location", "route",
        "document", "device_state", "task", "event", "model", "stream",
    ]
    schema_ref: str | None = Field(default=None, alias="schema", max_length=256)
    sensitivity: Literal["public", "internal", "sensitive", "restricted"] | None = None
    freshness: DataFreshness | None = None


class PresentationCondition(ContractModel):
    field: Annotated[str, Field(min_length=1, max_length=256)]
    operator: Literal[
        "equals", "not_equals", "contains", "available", "unavailable",
        "greater_than", "less_than",
    ]
    value: Any | None = None


class EnvironmentBinding(ContractModel):
    environment: Identifier
    suitability: Literal["primary", "secondary", "contextual"]
    conditions: list[PresentationCondition] = Field(default_factory=list, max_length=32)
    priority: int = Field(default=50, ge=0, le=100)


class EnvironmentDefinition(ContractModel):
    id: Identifier
    description: str = Field(default="", max_length=1024)


class VisualizationDefinition(ContractModel):
    type: str
    renderer_id: Identifier
    data_requirements: list[VisualizationDataRequirement] = Field(default_factory=list, max_length=32)


class VisualizationDataRequirement(ContractModel):
    output_type: str
    required: bool = True
    freshness_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    authorization: list[Identifier] = Field(default_factory=list, max_length=32)
    fallback: str | None = Field(default=None, max_length=128)


VisualizationDefinition.model_rebuild()


class VisualizationBinding(ContractModel):
    type: Literal[
        "map", "satellite", "terrain", "globe", "3d_world", "marker", "route",
        "chart", "timeline", "image", "video", "network", "diagram", "text",
        "document", "audio", "status", "avatar",
    ]
    input_types: list[str] = Field(default_factory=list, max_length=32)
    required_client_capabilities: list[str] = Field(default_factory=list, max_length=32)
    preferred_for: list[PresentationCondition] = Field(default_factory=list, max_length=32)
    data_requirements: list[VisualizationDataRequirement] = Field(default_factory=list, max_length=32)
    priority: int = Field(default=50, ge=0, le=100)


class PresentationFallbackChain(ContractModel):
    preferred: str
    alternatives: list[str] = Field(default_factory=list, max_length=32)
    reason: str
    requirements: list[VisualizationDataRequirement] = Field(default_factory=list, max_length=32)


class PresentationCapabilityBinding(ContractModel):
    environments: list[EnvironmentBinding] = Field(default_factory=list, max_length=32)
    visualizations: list[VisualizationBinding] = Field(default_factory=list, max_length=100)
    modalities: list[Literal[
        "text", "voice", "visual", "image", "video", "map", "3d", "spatial",
        "haptic", "ambient",
    ]] = Field(default_factory=list, max_length=32)
    fallbacks: list[PresentationFallbackChain] = Field(default_factory=list, max_length=32)


class CapabilityPresentationDefinition(ContractModel):
    id: Identifier
    version: str
    name: str
    description: str
    category: str
    outputs: list[CapabilityOutput] = Field(default_factory=list, max_length=100)
    presentation: PresentationCapabilityBinding
    operational_status: str


class PresentationScore(ContractModel):
    relevance: int = Field(ge=0, le=100)
    user_preference: int = Field(ge=0, le=100)
    client_support: int = Field(ge=0, le=100)
    context_fit: int = Field(ge=0, le=100)
    accessibility: int = Field(ge=0, le=100)
    performance: int = Field(ge=0, le=100)
    continuity: int = Field(ge=0, le=100)
    safety: int = Field(ge=0, le=100)


class PresentationOption(ContractModel):
    type: str
    environment: str
    renderer: str | None = None
    score: PresentationScore
    reason: str


class PresentationResolution(ContractModel):
    selected: PresentationOption | None = None
    alternatives: list[PresentationOption] = Field(default_factory=list, max_length=100)
    unavailable: list[PresentationOption] = Field(default_factory=list, max_length=100)
    reasons: list[str] = Field(default_factory=list, max_length=100)


class PresentationFallback(ContractModel):
    requested: CapabilityName
    available: list[CapabilityName] = Field(default_factory=list)
    selected: CapabilityName
    reason: str


class RendererNegotiation(ContractModel):
    client_id: Identifier
    renderers: list[RendererDefinition]
    fallbacks: list[PresentationFallback]


class PresentationFeedback(ContractModel):
    presentation_id: Identifier
    type: Literal[
        "interaction", "viewport_changed", "media_state", "permission_request",
        "capability_error", "user_override", "client_error",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class PresentationError(ContractModel):
    code: Identifier
    message: Annotated[str, Field(min_length=1, max_length=2048)]
    recoverable: bool
    capability: CapabilityName | None = None
    fallback: CapabilityName | None = None
    retryable: bool = False


class PresentationTraceTimestamps(ContractModel):
    created: datetime
    rendered: datetime | None = None
    completed: datetime | None = None


class PresentationTrace(ContractModel):
    presentation_id: Identifier
    request_id: Identifier
    session_id: Identifier
    intent_version: str
    renderer: Identifier | None = None
    capability_sources: list[CapabilityName] = Field(default_factory=list, max_length=100)
    timestamps: PresentationTraceTimestamps
    errors: list[str] = Field(default_factory=list, max_length=100)


class InformationPriority(ContractModel):
    target: Identifier
    priority: int = Field(ge=0, le=100)
    reason: Annotated[str, Field(min_length=1, max_length=1024)]
    visibility: Literal["primary", "secondary", "contextual", "hidden"]


class PresentationPlan(ContractModel):
    objective: Annotated[str, Field(min_length=1, max_length=2048)]
    primary_environment: Identifier
    secondary_environments: list[Identifier] = Field(default_factory=list, max_length=32)
    information_priority: list[InformationPriority] = Field(default_factory=list, max_length=100)
    modalities: list[Literal[
        "text", "voice", "visual", "image", "video", "map", "3d", "spatial",
        "haptic", "ambient",
    ]] = Field(default_factory=list, max_length=32)
    interaction_strategy: str = Field(max_length=2048)
    assistant_presence: AssistantPresentationState
    transition_strategy: dict[str, Any] | None = None
    fallback_strategy: str = Field(max_length=2048)
    user_override: str | None = None


class PresentationComposition(ContractModel):
    primary: PresentationIntent
    secondary: list[PresentationIntent] = Field(default_factory=list, max_length=16)
    overlays: list[PresentationIntent] = Field(default_factory=list, max_length=32)
    ambient: list[PresentationIntent] = Field(default_factory=list, max_length=16)


class UserPresentationProfile(ContractModel):
    density: Literal["minimal", "balanced", "detailed", "technical"] = "balanced"
    visual_preference: Literal["low", "normal", "high", "immersive"] = "normal"
    voice_preference: Literal["off", "minimal", "normal", "continuous"] = "minimal"
    avatar_preference: Literal["hidden", "minimal", "visible", "immersive"] = "minimal"
    motion_preference: Literal["reduced", "normal", "expressive"] = "normal"
    technical_detail: Literal["simple", "standard", "advanced"] = "standard"
    adaptive_presentation: bool = True
    accessibility: dict[str, Any] = Field(default_factory=dict)


class PresentationPreferenceUpdate(ContractModel):
    density: Literal["minimal", "balanced", "detailed", "technical"] | None = None
    visual_preference: Literal["low", "normal", "high", "immersive"] | None = None
    voice_preference: Literal["off", "minimal", "normal", "continuous"] | None = None
    avatar_preference: Literal["hidden", "minimal", "visible", "immersive"] | None = None
    motion_preference: Literal["reduced", "normal", "expressive"] | None = None
    technical_detail: Literal["simple", "standard", "advanced"] | None = None
    adaptive_presentation: bool | None = None
    accessibility: dict[str, Any] | None = None


class PresenceControllerState(ContractModel):
    state: Literal[
        "idle", "listening", "thinking", "searching", "observing", "speaking",
        "working", "creating", "navigating", "learning", "explaining",
        "waiting_for_permission", "alert", "offline",
    ] = "idle"
    expression: str | None = Field(default=None, max_length=128)
    visibility: Literal["hidden", "minimal", "visible", "immersive"] = "minimal"
    focus: str | None = None
    environment: Identifier = "conversation"
