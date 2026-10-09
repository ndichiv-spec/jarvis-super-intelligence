"""Resolve capability output to a supported semantic presentation option."""

from __future__ import annotations

from typing import Any

from .policy import PresentationPolicy, presentation_policy
from .registry import PresentationRegistry, presentation_registry
from .schemas import (
    PresentationCapabilities,
    PresentationOption,
    PresentationResolution,
    PresentationScore,
    VisualizationBinding,
)


class PresentationResolver:
    """Deterministically ranks options backed by real outputs and approved renderers."""

    def __init__(
        self,
        registry: PresentationRegistry = presentation_registry,
        policy: PresentationPolicy = presentation_policy,
    ) -> None:
        self.registry = registry
        self.policy = policy

    async def resolve(
        self,
        capability_id: str,
        outputs: list[str],
        client: PresentationCapabilities,
        *,
        request: str = "",
        current_environment: str | None = None,
        preferences: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PresentationResolution:
        """Resolve only from server-supplied output types, never client-declared data."""
        definitions = {
            definition.id: definition for definition in self.registry.definitions()
        }
        definition = definitions.get(capability_id)
        if definition is None:
            return PresentationResolution(
                reasons=[f"Capability {capability_id} is not registered for presentation."],
            )

        output_types = set(outputs)
        declared_types = {output.type for output in definition.outputs}
        output_types.intersection_update(declared_types)
        if not output_types:
            return PresentationResolution(
                reasons=["No matching real capability outputs were provided to the resolver."],
            )

        preferences = preferences or {}
        context = context or {}
        candidates: list[PresentationOption] = []
        unavailable: list[PresentationOption] = []
        for binding in definition.presentation.visualizations:
            required_outputs = {
                requirement.output_type
                for requirement in binding.data_requirements
                if requirement.required
            } or set(binding.input_types)
            if not (required_outputs & output_types):
                continue

            environments = sorted(
                definition.presentation.environments,
                key=lambda item: (
                    item.environment != current_environment,
                    -item.priority,
                ),
            )
            for environment in environments:
                if not self._conditions_match(environment.conditions, context, client, preferences):
                    continue
                renderer = self._renderer_for(binding, client)
                data_ready = self._requirements_available(binding, output_types, context)
                environment_allowed = self.policy.allow_environment(
                    environment.environment,
                    [capability_id],
                    client,
                )
                reason_parts = [
                    f"Capability output supports {binding.type}.",
                    f"Environment suitability is {environment.suitability}.",
                ]
                if not data_ready:
                    reason_parts.append("Required output or authorization evidence is unavailable.")
                if renderer is None:
                    reason_parts.append("No approved renderer is supported by this client.")
                if not environment_allowed:
                    reason_parts.append("The client or presentation policy does not allow this environment.")

                score = self._score(
                    binding,
                    environment.environment,
                    renderer is not None,
                    request,
                    current_environment,
                    preferences,
                    client,
                )
                option = PresentationOption(
                    type=binding.type,
                    environment=environment.environment,
                    renderer=renderer.type if renderer else None,
                    score=score,
                    reason=" ".join(reason_parts),
                )
                if data_ready and renderer is not None and environment_allowed:
                    candidates.append(option)
                else:
                    unavailable.append(option)

        candidates.sort(
            key=lambda option: (
                -self._total(option.score),
                option.type,
                option.environment,
            )
        )
        selected = candidates[0] if candidates else None
        alternatives = candidates[1:]
        reasons = []
        if selected:
            fallback = next(
                (
                    item
                    for item in definition.presentation.fallbacks
                    if item.preferred in request.lower()
                    and selected.type in item.alternatives
                ),
                None,
            )
            if fallback:
                reasons.append(f"{fallback.reason} {selected.reason}")
            else:
                reasons.append(
                f"Selected {selected.type} in {selected.environment} using {selected.renderer} "
                "from registered capability outputs and client-supported renderers."
                )
        elif unavailable:
            reasons.append("No registered presentation option met all output, policy, and renderer requirements.")
        else:
            reasons.append("No presentation binding matches the actual capability output types.")
        return PresentationResolution(
            selected=selected,
            alternatives=alternatives,
            unavailable=unavailable,
            reasons=reasons,
        )

    def _renderer_for(
        self,
        binding: VisualizationBinding,
        client: PresentationCapabilities,
    ):
        client_platforms = set(client.surfaces)
        if client.platform != "unknown":
            client_platforms.add(client.platform)
        for renderer in self.registry.renderers:
            if binding.type not in renderer.presentation_types:
                continue
            if not client_platforms.intersection(renderer.supported_clients):
                continue
            if client.renderers and renderer.type not in client.renderers:
                continue
            if renderer.security_class == "restricted":
                continue
            supported = set(client.primitives + client.media + client.spatial)
            if not supported.intersection(renderer.supported_primitives):
                continue
            if not set(renderer.required_capabilities).issubset(
                supported | set(client.environments)
            ):
                continue
            if not set(binding.required_client_capabilities).issubset(supported):
                continue
            return renderer
        return None

    @staticmethod
    def _requirements_available(
        binding: VisualizationBinding,
        output_types: set[str],
        context: dict[str, Any],
    ) -> bool:
        for requirement in binding.data_requirements:
            freshness = context.get("output_freshness_ms", {}).get(requirement.output_type)
            if (
                requirement.freshness_ms is not None
                and freshness is not None
                and freshness > requirement.freshness_ms
            ):
                return False
            if requirement.authorization and not set(requirement.authorization).issubset(
                set(context.get("authorizations", []))
            ):
                return False
        required_outputs = {
            requirement.output_type
            for requirement in binding.data_requirements
            if requirement.required
        } or set(binding.input_types)
        return not required_outputs or bool(required_outputs.intersection(output_types))

    @staticmethod
    def _conditions_match(
        conditions: list[Any],
        context: dict[str, Any],
        client: PresentationCapabilities,
        preferences: dict[str, Any],
    ) -> bool:
        root = {"context": context, "client": client.model_dump(), "preferences": preferences}
        for condition in conditions:
            current: Any = root
            for part in condition.field.split("."):
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = getattr(current, part, None)
            expected = condition.value
            if condition.operator == "equals" and current != expected:
                return False
            if condition.operator == "not_equals" and current == expected:
                return False
            if condition.operator == "contains" and (
                current is None or expected not in current
            ):
                return False
            if condition.operator == "available" and current is None:
                return False
            if condition.operator == "unavailable" and current is not None:
                return False
            if condition.operator == "greater_than" and not (
                isinstance(current, (int, float))
                and isinstance(expected, (int, float))
                and current > expected
            ):
                return False
            if condition.operator == "less_than" and not (
                isinstance(current, (int, float))
                and isinstance(expected, (int, float))
                and current < expected
            ):
                return False
        return True

    @staticmethod
    def _score(
        binding: VisualizationBinding,
        environment: str,
        client_supported: bool,
        request: str,
        current_environment: str | None,
        preferences: dict[str, Any],
        client: PresentationCapabilities,
    ) -> PresentationScore:
        lowered = request.lower()
        relevance = min(100, 50 + binding.priority // 2)
        request_terms = {
            "image": ("image", "picture", "visual"),
            "audio": ("voice", "speak", "audio"),
            "document": ("document", "page", "report", "browse"),
            "timeline": ("timeline", "activity", "progress", "doing"),
            "chart": ("chart", "graph", "metric"),
            "map": ("map", "where", "location"),
            "text": ("explain", "tell", "summarize", "answer"),
        }.get(binding.type, (binding.type,))
        if any(term in lowered for term in request_terms):
            relevance = min(100, relevance + 20)

        visual_preference = preferences.get("visual_preference", "normal")
        user_preference = 90 if binding.type in {"text", "audio"} else (
            80 if visual_preference in {"high", "immersive"} else 60
        )
        client_support = 100 if client_supported else 0
        context_fit = 100 if environment == current_environment else 70
        accessibility = 60
        if client.accessibility.get("reducedMotion") and binding.type in {"map", "timeline"}:
            accessibility = 100
        elif client.accessibility:
            accessibility = 80
        performance = 90 if client.performance_profile in {None, "high"} else 70
        continuity = 100 if environment == current_environment else 65
        safety = 100
        return PresentationScore(
            relevance=relevance,
            user_preference=user_preference,
            client_support=client_support,
            context_fit=context_fit,
            accessibility=accessibility,
            performance=performance,
            continuity=continuity,
            safety=safety,
        )

    @staticmethod
    def _total(score: PresentationScore) -> int:
        return (
            score.relevance * 25
            + score.user_preference * 15
            + score.client_support * 20
            + score.context_fit * 10
            + score.accessibility * 10
            + score.performance * 5
            + score.continuity * 5
            + score.safety * 10
        )


presentation_resolver = PresentationResolver()
