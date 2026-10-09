"""Resolve world intents through registered, authorized execution surfaces."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

_RESULT_SELECTION = re.compile(
    r"\b(?:open|visit|go\s+to|show)\s+(?:the\s+)?"
    r"(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|[1-5])"
    r"(?:\s+(?:one|result|link))?\b",
    re.IGNORECASE,
)
_ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2,
    "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
}


@dataclass(frozen=True)
class WorldIntent:
    """A validated intent with the capability operation it requires."""

    kind: str
    subject: str
    query: str
    operation: str
    domain: str
    result_caveat: str = ""
    empty_result_message: str = ""
    plan_summary: str = "Execute the selected capability for this request."
    step_summary: str = "Retrieve an observed result from the selected source."
    completion_condition_type: str | None = None
    completion_expected: str = ""
    selectable_results: bool = False
    result_renderer: str = "public_links"
    result_count_path: str | None = None


@dataclass(frozen=True)
class ExecutionSelection:
    """A selected registered capability, or an explicit resolution failure."""

    operation: str
    status: str
    capability_id: str | None = None
    execution_surface: str | None = None
    reason: str | None = None
    contract: dict[str, Any] | None = None
    alternatives: tuple[ExecutionSelection, ...] = ()
    network_state: str = "unknown"


def resolve_execution_surface(
    operation: str,
    registry: Any,
    contracts: dict[str, dict[str, Any]],
    *,
    user_id: str,
    permissions: set[str] | None = None,
    principal: dict[str, Any] | None = None,
    network_available: bool | None = None,
    endpoint_capabilities: set[str] | None = None,
    authenticated_services: set[str] | None = None,
    acceptable_cost_models: set[str] | None = None,
) -> ExecutionSelection:
    """Select an operation-compatible, observable, authorized registered surface."""
    endpoints = endpoint_capabilities or set()
    candidates = [
        (name, contract)
        for name, contract in contracts.items()
        if operation in contract.get("operations", [])
    ]
    if not candidates:
        return ExecutionSelection(
            operation, "unavailable",
            reason=f"No registered execution surface provides {operation}.",
        )

    ranked: list[tuple[tuple[Any, ...], str, dict[str, Any]]] = []
    rejected: list[str] = []
    for name, contract in candidates:
        operation_arguments = (
            contract.get("operation_arguments") or {}
        ).get(operation)
        if not isinstance(operation_arguments, dict) or not operation_arguments:
            rejected.append(f"{name} has no input mapping for {operation}")
            continue
        if not _input_mapping_compatible(
            operation_arguments, contract.get("input_schema") or {},
        ):
            rejected.append(f"{name} input mapping is incompatible with its schema")
            continue
        output_schema = contract.get("output_schema") or {}
        required_output = (
            contract.get("operation_output_requirements") or {}
        ).get(operation, ())
        if any(not _schema_contains_path(output_schema, path) for path in required_output):
            rejected.append(f"{name} output schema cannot provide required evidence")
            continue
        if contract.get("execution_surface") in (None, "", "unknown"):
            rejected.append(f"{name} has no declared execution surface")
            continue
        if contract.get("observability") in (None, "", "unknown", "none"):
            rejected.append(f"{name} has no declared execution observability")
            continue
        availability = str(contract.get("availability", "UNKNOWN")).upper()
        if availability not in {"AVAILABLE", "DEGRADED"}:
            rejected.append(contract.get("availability_reason") or f"{name} is {availability.lower()}")
            continue
        health = str(contract.get("health", "unknown")).lower()
        if health == "unavailable":
            rejected.append(f"{name} is unhealthy")
            continue
        if (
            contract.get("network_requirements") == "required"
            and network_available is False
        ):
            rejected.append(f"{name} requires a network connection")
            continue
        if contract.get("authentication_required") is True:
            required_services = set(contract.get("service_dependencies") or [])
            if (
                not required_services
                or authenticated_services is None
                or not required_services.issubset(authenticated_services)
            ):
                rejected.append(
                    f"{name} requires verified authentication for its service"
                )
                continue
        required_endpoints = set(contract.get("endpoint_requirements") or [])
        if not required_endpoints.issubset(endpoints):
            rejected.append(f"{name} requires unavailable endpoint capabilities")
            continue
        cost_model = str(contract.get("cost_model", "unknown"))
        if acceptable_cost_models is not None and cost_model not in acceptable_cost_models:
            rejected.append(f"{name} exceeds the accepted cost policy")
            continue
        authorized, reason = registry.authorize(
            user_id,
            name,
            permissions=permissions,
            principal=principal,
        )
        if not authorized:
            rejected.append(f"{name} is not authorized: {reason}")
            continue

        latency = contract.get("latency_ms")
        quality_score = contract.get("quality_score")
        quality = (
            {"healthy": 0, "unknown": 1, "degraded": 2}.get(health, 3),
            -float(quality_score)
            if isinstance(quality_score, (int, float)) else float("inf"),
            float(latency) if isinstance(latency, (int, float)) else float("inf"),
            name,
        )
        ranked.append((quality, name, contract))

    if not ranked:
        reason = "; ".join(dict.fromkeys(rejected)) or (
            f"No authorized execution surface provides {operation}."
        )
        return ExecutionSelection(
            operation,
            "unavailable",
            reason=reason,
            network_state=(
                "online" if network_available is True
                else "offline" if network_available is False
                else "unknown"
            ),
        )

    ranked.sort(key=lambda item: item[0])
    _, capability_id, contract = ranked[0]
    return ExecutionSelection(
        operation=operation,
        status="selected",
        capability_id=capability_id,
        execution_surface=str(contract.get("execution_surface") or "unknown"),
        contract=contract,
        network_state=(
            "online" if network_available is True
            else "offline" if network_available is False
            else "unknown"
        ),
        alternatives=tuple(
            ExecutionSelection(
                operation=operation,
                status="selected",
                capability_id=alternative_id,
                execution_surface=str(
                    alternative_contract.get("execution_surface") or "unknown"
                ),
                contract=alternative_contract,
            )
            for _, alternative_id, alternative_contract in ranked[1:]
        ),
    )


def resolve_world_intent(
    request: str,
    contracts: dict[str, dict[str, Any]] | None = None,
) -> WorldIntent | None:
    """Match registered intent metadata; leave unsupported or ambiguous chat alone."""
    text = re.sub(r"\s+", " ", (request or "")).strip()
    if not text:
        return None
    if contracts is None:
        from research_engine.capability_contract import build_contracts
        from research_engine.capability_tools import build_capability_registry

        registry = build_capability_registry()
        contracts = build_contracts(registry, inventory={})

    for contract in contracts.values():
        for operation, intent_spec in (contract.get("operation_intents") or {}).items():
            patterns = intent_spec.get("match_patterns") or ()
            if not patterns or not all(
                re.search(pattern, text, re.IGNORECASE) for pattern in patterns
            ):
                continue
            subject_pattern = intent_spec.get("subject_pattern")
            match = re.fullmatch(subject_pattern, text, re.IGNORECASE) if subject_pattern else None
            subject = (match.groupdict().get("subject") if match else None)
            if not subject:
                continue
            subject = subject.strip(" \t\r\n.,!?\"'")
            if (
                not subject
                or len(subject) > 160
                or "://" in subject
                or "\n" in subject
                or not re.fullmatch(r"[\w\s.'’:,!?&-]+", subject, flags=re.UNICODE)
            ):
                continue
            template = intent_spec.get("query_template", "{subject}")
            query = template.format(subject=subject)
            return WorldIntent(
                kind=str(intent_spec.get("semantic_type") or operation),
                subject=subject,
                query=query,
                operation=operation,
                domain=str(contract.get("domain") or "platform"),
                result_caveat=str(intent_spec.get("result_caveat") or ""),
                empty_result_message=str(
                    intent_spec.get("empty_result_message") or
                    "The selected execution surface returned no usable results."
                ),
                plan_summary=str(
                    intent_spec.get("plan_summary") or
                    "Execute the selected capability for this request."
                ),
                step_summary=str(
                    intent_spec.get("step_summary") or
                    "Retrieve an observed result from the selected source."
                ),
                completion_condition_type=intent_spec.get("completion_condition_type"),
                completion_expected=str(intent_spec.get("completion_expected") or ""),
                selectable_results=bool(intent_spec.get("selectable_results", False)),
                result_renderer=str(intent_spec.get("result_renderer") or "public_links"),
                result_count_path=intent_spec.get("result_count_path"),
            )
    return None


def _input_mapping_compatible(
    mapping: dict[str, Any], schema: dict[str, Any],
) -> bool:
    """Check static operation argument mappings against a JSON-schema subset."""
    if schema.get("type") not in (None, "object"):
        return False
    properties = schema.get("properties") or {}
    required = schema.get("required") or ()
    if not set(required).issubset(mapping):
        return False
    for key, value in mapping.items():
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            return False
        expected = property_schema.get("type")
        if isinstance(value, str) and value.startswith("$"):
            if expected not in (None, "string"):
                return False
        elif expected == "string" and not isinstance(value, str):
            return False
        elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            return False
        elif expected == "number" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            return False
        elif expected == "boolean" and not isinstance(value, bool):
            return False
        elif expected == "object" and not isinstance(value, dict):
            return False
        elif expected == "array" and not isinstance(value, list):
            return False
    return True


def _schema_contains_path(schema: dict[str, Any], path: str) -> bool:
    current = schema
    for part in path.split("."):
        if current.get("type") == "array":
            current = current.get("items") or {}
        properties = current.get("properties") or {}
        if part not in properties:
            return False
        current = properties[part]
    return bool(current)


def is_result_selection_request(request: str) -> bool:
    return _RESULT_SELECTION.search(request or "") is not None


def resolve_result_followup(
    request: str, messages: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Select a sourced HTTPS link from a completed operation in this session."""
    match = _RESULT_SELECTION.search(request or "")
    if not match:
        return None
    number = int(match.group(1)) if match.group(1).isdigit() else _ORDINALS[match.group(1).lower()]
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        calls = message.get("tool_calls") or []
        if not any(
            isinstance(call, dict)
            and (
                call.get("selectable_results") is True
                or str(call.get("operation") or "").endswith(".discovery")
                or call.get("name") == "search_web"
            )
            and call.get("status") == "completed"
            for call in calls
        ):
            continue
        links = re.findall(
            r"\[([^\]\r\n]+)\]\((https://[^)\s]+)\)",
            str(message.get("content") or ""),
        )
        if number <= len(links):
            title, url = links[number - 1]
            if _is_public_https_url(url):
                return title, url
        return None
    return None


def has_prior_world_results(messages: list[dict[str, Any]]) -> bool:
    return any(
        message.get("role") == "assistant"
        and any(
            isinstance(call, dict)
            and (
                call.get("selectable_results") is True
                or str(call.get("operation") or "").endswith(".discovery")
                or call.get("name") == "search_web"
            )
            and call.get("status") == "completed"
            for call in (message.get("tool_calls") or [])
        )
        for message in messages
    )


def resolve_media_followup(
    request: str, messages: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Backward-compatible alias for result selection."""
    return resolve_result_followup(request, messages)


def has_prior_media_results(messages: list[dict[str, Any]]) -> bool:
    """Backward-compatible alias for completed discovery results."""
    return has_prior_world_results(messages)


def _is_public_https_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme != "https"
            or not hostname
            or re.search(r"[\s<>\"'`\\]", url)
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or hostname == "localhost"
            or hostname.endswith((".localhost", ".local", ".internal"))
        ):
            return False
        try:
            if not ipaddress.ip_address(hostname).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def resolve_presentation(intent: WorldIntent, artifacts: list[dict[str, Any]]) -> dict[str, str]:
    """Choose the existing conversation renderer from the intent and observed result."""
    if any(
        isinstance(artifact, dict)
        and _is_public_https_url(str(artifact.get("url") or "").strip())
        and str(artifact.get("title") or "").strip()
        for artifact in artifacts
    ):
        return {
            "environment": "conversation",
            "renderer": "conversation_links",
            "semantic_type": intent.kind,
        }
    return {
        "environment": "conversation",
        "renderer": "conversation_text",
        "semantic_type": intent.kind,
    }


def render_world_results(
    intent: WorldIntent,
    artifacts: list[dict[str, Any]],
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Render observed operation output in the existing conversation."""
    sources: list[str] = []
    lines: list[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        original_url = str(artifact.get("url") or "").strip()
        if not _is_public_https_url(original_url) or original_url in seen:
            continue
        seen.add(original_url)
        url = quote(original_url, safe=":/?&=#%+@-._~")
        title = re.sub(
            r"[\[\]\r\n]+", " ",
            str(artifact.get("title") or ""),
        ).strip()
        if not title:
            continue
        sources.append(url)
        snippet = re.sub(r"\s+", " ", str(artifact.get("snippet") or "")).strip()
        line = f"- [{title}]({url})"
        if snippet:
            line += f" - {snippet[:400]}"
        lines.append(line)

    if not lines and intent.result_renderer == "workspace_matches":
        return _render_workspace_matches(intent, evidence or []), []
    if not lines and intent.result_renderer == "geospatial_point_map":
        return _render_coordinate_result(intent, evidence or []), []
    if not lines:
        return intent.empty_result_message, []

    message = (
        f"I found these results for **{intent.subject}**:\n\n"
        + "\n".join(lines)
    )
    if intent.result_caveat:
        message += "\n\n" + intent.result_caveat
    return message, sources


def _render_coordinate_result(
    intent: WorldIntent,
    evidence: list[dict[str, Any]],
) -> str:
    raw = next(
        (str(item.get("result") or "") for item in evidence if item.get("success")),
        "",
    )
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return "The coordinate parser returned a result that could not be safely read."
    if (
        not isinstance(payload, dict)
        or payload.get("result_available") is not True
        or type(payload.get("latitude")) not in (int, float)
        or type(payload.get("longitude")) not in (int, float)
    ):
        return "The supplied coordinates could not be validated; no map is shown."
    return (
        f"I validated the user-provided coordinates "
        f"({payload['latitude']:.5f}, {payload['longitude']:.5f}). "
        "This map is not a live device location."
    )


def _render_workspace_matches(intent: WorldIntent, evidence: list[dict[str, Any]]) -> str:
    """Render only the bounded, workspace-confined matches returned by the tool."""
    raw = next(
        (str(item.get("result") or "") for item in evidence if item.get("result")),
        "",
    )
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return "The workspace search completed, but its result could not be parsed safely."
    if not isinstance(payload, dict):
        return "The workspace search completed, but returned an unsupported result shape."

    count = payload.get("match_count")
    matches = payload.get("matches")
    if type(count) is not int or not isinstance(matches, list):
        return "The workspace search completed, but returned incomplete match data."
    subject = re.sub(r"[\r\n`*]+", " ", intent.subject).strip()
    if count == 0:
        return f"I searched the configured JARVIS workspace for **{subject}** and found no matches."

    lines = []
    for match in matches[:10]:
        if not isinstance(match, dict):
            continue
        path = re.sub(r"[\r\n`]+", " ", str(match.get("file") or "")).strip()
        text = re.sub(r"[\r\n`]+", " ", str(match.get("text") or "")).strip()
        line = match.get("line")
        if not path or type(line) is not int or line < 1:
            continue
        rendered = f"- `{path}:{line}`"
        if text:
            rendered += f" — `{text[:240]}`"
        lines.append(rendered)
    if not lines:
        return (
            f"I searched the configured JARVIS workspace for **{subject}** "
            f"and observed {count} matches, but could not safely render them."
        )
    suffix = "\n\nAdditional matches were omitted." if count > len(lines) else ""
    return (
        f"I searched the configured JARVIS workspace for **{subject}** "
        f"and found {count} match{'es' if count != 1 else ''}:\n\n"
        + "\n".join(lines)
        + suffix
    )


def observed_result_count(
    intent: WorldIntent,
    evidence: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> int:
    """Count results using the operation's declared result field, if any."""
    if intent.result_count_path:
        for item in evidence:
            if not item.get("success"):
                continue
            try:
                value: Any = json.loads(str(item.get("result") or ""))
            except (TypeError, ValueError):
                continue
            for part in intent.result_count_path.split("."):
                if not isinstance(value, dict) or part not in value:
                    value = None
                    break
                value = value[part]
            if type(value) is int and value >= 0:
                return value
    return len(artifacts)


def render_media_results(intent: WorldIntent, artifacts: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Backward-compatible alias for the generalized conversation renderer."""
    return render_world_results(intent, artifacts)


class WorldResolverAdapter:
    """Deterministic Brain proposal for a resolved registered operation."""

    def __init__(
        self,
        intent: WorldIntent,
        selection: ExecutionSelection,
        on_select: Any = None,
    ):
        self.intent = intent
        self.selection = selection
        self.on_select = on_select
        self._selections = (selection, *selection.alternatives)
        self._selection_index = 0

    async def propose(self, brain_input: Any, budget: Any) -> Any:
        del budget
        from jarvis_brain.contract import (
            BrainIntent as ContractIntent,
        )
        from jarvis_brain.contract import (
            BrainOutput,
            CapabilityRequest,
            CompletionCondition,
            ConfidenceState,
            Plan,
            PlanStep,
        )

        if self._selection_index >= len(self._selections):
            return BrainOutput(
                intent=ContractIntent(
                    domain=self.intent.domain,
                    task=brain_input.request,
                    confidence=ConfidenceState.INSUFFICIENT_EVIDENCE,
                ),
                plan=Plan(
                    summary="No further authorized execution surface is available."
                ),
                capability_requests=[],
                confidence_state=ConfidenceState.INSUFFICIENT_EVIDENCE,
                model_ref="world-resolver",
                provenance={"adapter": "WorldResolverAdapter"},
                summary="No further authorized execution surface is available.",
            )

        selection = self._selections[self._selection_index]
        self._selection_index += 1
        if self.on_select is not None:
            self.on_select(selection)
        if selection.status != "selected" or not selection.capability_id:
            reason = selection.reason or "No authorized execution surface is available."
            return BrainOutput(
                intent=ContractIntent(
                    domain=self.intent.domain,
                    task=brain_input.request,
                    confidence=ConfidenceState.INSUFFICIENT_EVIDENCE,
                ),
                plan=Plan(summary=reason),
                capability_requests=[],
                confidence_state=ConfidenceState.INSUFFICIENT_EVIDENCE,
                model_ref="world-resolver",
                provenance={
                    "adapter": "WorldResolverAdapter",
                    "operation": self.intent.operation,
                    "resolution": "unavailable",
                },
                summary=reason,
            )

        operation_arguments = (
            (selection.contract or {}).get("operation_arguments") or {}
        ).get(self.intent.operation) or {}
        args = {
            key: self.intent.query if value == "$query" else value
            for key, value in operation_arguments.items()
        }
        if not args and "query" in (
            ((selection.contract or {}).get("input_schema") or {})
            .get("properties", {})
        ):
            args["query"] = self.intent.query
        return BrainOutput(
            intent=ContractIntent(
                domain=self.intent.domain,
                task=self.intent.kind,
                confidence=ConfidenceState.SUFFICIENT_INFORMATION,
            ),
            plan=Plan(
                summary=self.intent.plan_summary,
                steps=[PlanStep(
                    id=f"world-{self.intent.operation.replace('.', '-')}",
                    capability=selection.capability_id,
                    summary=self.intent.step_summary,
                    args=args,
                )],
            ),
            capability_requests=[CapabilityRequest(
                capability=selection.capability_id,
                args=args,
                reason=f"User explicitly requested {self.intent.operation}.",
            )],
            completion_conditions=(
                [CompletionCondition(
                    type=self.intent.completion_condition_type,
                    target=self.intent.subject,
                    expected=self.intent.completion_expected,
                )]
                if self.intent.completion_condition_type else []
            ),
            confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
            model_ref="world-resolver",
            provenance={
                "adapter": "WorldResolverAdapter",
                "intent": self.intent.kind,
                "capability": selection.capability_id,
                "execution_surface": selection.execution_surface,
            },
            summary="Resolve the request using the selected discovery surface.",
        )


__all__ = [
    "WorldIntent",
    "ExecutionSelection",
    "WorldResolverAdapter",
    "is_result_selection_request",
    "has_prior_media_results",
    "has_prior_world_results",
    "render_media_results",
    "render_world_results",
    "resolve_media_followup",
    "resolve_result_followup",
    "resolve_presentation",
    "resolve_execution_surface",
    "resolve_world_intent",
]
