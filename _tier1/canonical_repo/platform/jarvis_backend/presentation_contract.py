"""Framework-neutral semantic presentation contracts for authorized results."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlsplit

CONTRACT_VERSION = "1.1"
SUPPORTED_CONTRACT_VERSIONS = {"1.0", CONTRACT_VERSION}
SUPPORTED_COMPONENTS = {
    "conversation.markdown",
    "research.source_list",
    "workspace.match_list",
    "geospatial.point_map",
}
MAX_COMPONENTS = 8
MAX_ITEMS = 20
MAX_TEXT = 12_000
_REFERENCE_ID = re.compile(r"^[A-Za-z0-9:_-]{1,256}$")


class PresentationContractError(ValueError):
    """Raised when a presentation contract violates the semantic contract."""


def build_conversation_presentation(
    text: str,
    *,
    request_id: str | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Build an accessible text-first contract for an observed chat response."""
    safe_text = _safe_text(text)
    return validate_presentation_contract({
        "contract_version": CONTRACT_VERSION,
        "presentation_id": str(uuid.uuid4()),
        "objective": "conversation",
        "environment": "conversation",
        "content_hierarchy": ["response"],
        "focus": "response",
        "components": [{
            "id": "response",
            "type": "conversation.markdown",
            "text": safe_text,
        }],
        "assistant_presence": {"mode": "inline", "state": "available"},
        "interactions": [],
        "visualizations": [],
        "modalities": ["text"],
        "accessibility": {
            "reading_order": ["response"],
            "announce_updates": True,
            "non_color_status": True,
        },
        "responsive": {"reflow": "single_column", "minimum_width": "content"},
        "transitions": {
            "on_unsupported": "conversation_fallback",
            "on_error": "retain_observed_text",
        },
        "errors": [],
        "task_state": {
            "status": "completed",
            "message": safe_text,
        },
        "source_provenance": [],
        "media_refs": [],
        "user_preferences": None,
        "view_state": {
            "focus": "response",
            "selected_data_ref": None,
        },
        "fallback": {"type": "conversation.markdown", "text": safe_text},
        "correlation": {
            "request_id": request_id,
            "session_id": session_id,
            "conversation_id": conversation_id or session_id,
            "command_id": None,
            "execution_id": None,
        },
        "data_refs": [],
        "renderer_requirements": {
            "contract_version": CONTRACT_VERSION,
            "supported_contract_versions": sorted(SUPPORTED_CONTRACT_VERSIONS),
            "required_components": ["conversation.markdown"],
            "required_modalities": ["text"],
            "fallback_components": ["conversation.markdown"],
        },
    }, authorized_data_refs=set())


def build_execution_presentation(
    *,
    operation: str,
    success: bool,
    message: str,
    artifacts: list[dict[str, Any]],
    tool_result: str,
    request_id: str | None,
    session_id: str | None,
    conversation_id: str | None,
    command_id: str | None,
    execution_id: str | None,
    requested_modality: str | None = None,
) -> dict[str, Any]:
    """Plan presentation only from the actual result and approved primitives."""
    refs: list[dict[str, str]] = []
    components: list[dict[str, Any]] = []
    interactions: list[dict[str, Any]] = []
    safe_message = _safe_text(message)
    errors: list[str] = []
    modalities = ["text"]
    source_provenance: list[dict[str, str]] = []
    objective = "conversation"

    if requested_modality and requested_modality not in {"text", "links"}:
        errors.append(f"Unsupported requested modality: {requested_modality}.")
        safe_message = (
            f"{safe_message}\n\n"
            f"{requested_modality} presentation is unavailable; showing text instead."
        ).strip()

    if success and operation in {"web.search", "media.discovery"}:
        objective = "research"
        sources = []
        if execution_id:
            for index, artifact in enumerate(artifacts[:MAX_ITEMS]):
                title = _safe_text(str(artifact.get("title") or ""), 300).strip()
                url = _public_https_url(artifact.get("url"))
                snippet = _safe_text(str(artifact.get("snippet") or ""), 600).strip()
                if not title or not url:
                    continue
                reference_id = f"execution:{execution_id}:artifact:{index}"
                refs.append({"id": reference_id, "kind": "public_source"})
                source_provenance.append({
                    "data_ref": reference_id,
                    "source_type": "public_web",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                })
                interactions.append({
                    "id": f"open-source-{index}",
                    "type": "external_source_navigation",
                    "data_ref": reference_id,
                    "required_permissions": ["web:read"],
                    "user_gesture_required": True,
                })
                sources.append({
                    "data_ref": reference_id,
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })
        if sources:
            components.append({
                "id": "sources",
                "type": "research.source_list",
                "title": "Observed sources",
                "items": sources,
            })
            modalities.append("links")
        else:
            errors.append("Execution completed without renderable public sources.")
            safe_message = safe_message or "No public source was observed."
    elif success and operation == "workspace.search":
        objective = "workspace_search"
        payload = _json_object(tool_result)
        matches = payload.get("matches") if payload else None
        count = payload.get("match_count") if payload else None
        if execution_id and isinstance(matches, list) and type(count) is int:
            rendered_matches = []
            for row in matches[:MAX_ITEMS]:
                if not isinstance(row, dict):
                    continue
                path = _safe_workspace_path(row.get("file"))
                line = row.get("line")
                if not path or type(line) is not int or line < 1:
                    continue
                rendered_matches.append({
                    "path": path,
                    "line": line,
                    "text": _safe_text(str(row.get("text") or ""), 600).strip(),
                })
            if rendered_matches:
                reference_id = f"execution:{execution_id}:result"
                refs.append({"id": reference_id, "kind": "workspace_result"})
                source_provenance.append({
                    "data_ref": reference_id,
                    "source_type": "authorized_workspace",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                })
                for row in rendered_matches:
                    row["data_ref"] = reference_id
            components.append({
                "id": "matches",
                "type": "workspace.match_list",
                "title": f"Observed workspace matches ({count})",
                "items": rendered_matches,
            })
        else:
            errors.append("Execution completed without valid workspace result data.")
            safe_message = safe_message or "Workspace results are unavailable."
    elif success and operation == "geography.coordinates.map":
        payload = _json_object(tool_result)
        latitude = payload.get("latitude") if payload else None
        longitude = payload.get("longitude") if payload else None
        if (
            execution_id
            and type(latitude) in (int, float)
            and -90 <= latitude <= 90
            and type(longitude) in (int, float)
            and -180 <= longitude <= 180
        ):
            reference_id = f"execution:{execution_id}:coordinate"
            refs.append({
                "id": reference_id,
                "kind": "user_provided_coordinates",
            })
            source_provenance.append({
                "data_ref": reference_id,
                "source_type": "user_provided_coordinates",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            })
            components.append({
                "id": "map",
                "type": "geospatial.point_map",
                "title": "Map of user-provided coordinates",
                "items": [{
                    "data_ref": reference_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "label": f"{latitude:.5f}, {longitude:.5f}",
                    "units": {
                        "latitude": "degrees_north",
                        "longitude": "degrees_east",
                    },
                    "location_type": "user_provided",
                }],
            })
            modalities.append("map")
            safe_message = (
                "I validated the coordinates you provided. This is not a live "
                "device location."
            )
        else:
            errors.append("Execution returned no valid coordinate pair.")
            safe_message = safe_message or (
                "A map cannot be presented because no validated coordinates "
                "were returned."
            )

    if not components:
        components = [{
            "id": "response",
            "type": "conversation.markdown",
            "text": safe_message or "The operation returned no displayable result.",
        }]
    elif safe_message:
        components.insert(0, {
            "id": "response",
            "type": "conversation.markdown",
            "text": safe_message,
        })
    primary_component_ids = [component["id"] for component in components]
    if len(components) > 1:
        objective_hierarchy = ["response", *primary_component_ids[1:]]
    else:
        objective_hierarchy = primary_component_ids

    modalities = list(dict.fromkeys(modalities))
    allowed_refs = {item["id"] for item in refs}
    task_status = (
        "completed" if success else
        "unsupported" if operation == "media.playback" else "error"
    )
    focus = objective_hierarchy[0]
    return validate_presentation_contract({
        "contract_version": CONTRACT_VERSION,
        "presentation_id": str(uuid.uuid4()),
        "objective": objective,
        "environment": "conversation",
        "content_hierarchy": objective_hierarchy,
        "focus": objective_hierarchy[0],
        "components": components[:MAX_COMPONENTS],
        "assistant_presence": {
            "mode": "inline",
            "state": "available" if success else "error",
        },
        "interactions": interactions,
        "visualizations": [],
        "modalities": modalities,
        "accessibility": {
            "reading_order": objective_hierarchy,
            "announce_updates": True,
            "non_color_status": True,
        },
        "responsive": {"reflow": "single_column", "minimum_width": "content"},
        "transitions": {
            "on_unsupported": "conversation_fallback",
            "on_error": "retain_observed_text",
        },
        "errors": errors,
        "task_state": {
            "status": task_status,
            "message": safe_message or "No operation result was observed.",
        },
        "source_provenance": source_provenance,
        "media_refs": [],
        "user_preferences": None,
        "view_state": {
            "focus": focus,
            "selected_data_ref": None,
        },
        "fallback": {
            "type": "conversation.markdown",
            "text": safe_message or "The operation did not produce a displayable result.",
        },
        "correlation": {
            "request_id": request_id,
            "session_id": session_id,
            "conversation_id": conversation_id or session_id,
            "command_id": command_id,
            "execution_id": execution_id,
        },
        "data_refs": refs,
        "renderer_requirements": {
            "contract_version": CONTRACT_VERSION,
            "supported_contract_versions": sorted(SUPPORTED_CONTRACT_VERSIONS),
            "required_components": [
                component["type"] for component in components
            ],
            "required_modalities": (
                ["text", "map"] if "map" in modalities else ["text"]
            ),
            "fallback_components": ["conversation.markdown"],
        },
    }, authorized_data_refs=allowed_refs, expected_correlation={
        "request_id": request_id,
        "session_id": session_id,
        "conversation_id": conversation_id or session_id,
        "command_id": command_id,
        "execution_id": execution_id,
    })


def validate_presentation_contract(
    contract: dict[str, Any],
    *,
    authorized_data_refs: set[str] | None = None,
    expected_correlation: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Validate contract version, semantic primitives, data scope and correlation."""
    if not isinstance(contract, dict):
        raise PresentationContractError("presentation contract must be an object")
    contract_version = contract.get("contract_version")
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise PresentationContractError("unsupported presentation contract version")
    required_fields = {
        "contract_version", "presentation_id", "objective", "environment", "content_hierarchy",
        "focus", "components", "assistant_presence", "interactions",
        "visualizations", "modalities", "accessibility", "responsive",
        "transitions", "errors", "fallback", "correlation", "data_refs",
        "renderer_requirements",
    }
    v1_1_fields = {
        "task_state", "source_provenance", "media_refs",
        "user_preferences", "view_state",
    }
    expected_fields = (
        required_fields | v1_1_fields
        if contract_version == CONTRACT_VERSION else required_fields
    )
    if set(contract) != expected_fields:
        raise PresentationContractError("presentation contract is incomplete")
    if contract.get("environment") not in {"conversation", "web", "map", "image"}:
        raise PresentationContractError("unsupported presentation environment")
    if contract.get("objective") not in {
        "conversation", "research", "workspace_search",
    }:
        raise PresentationContractError("unsupported presentation objective")
    if not isinstance(contract.get("presentation_id"), str):
        raise PresentationContractError("invalid presentation identifier")
    try:
        uuid.UUID(contract["presentation_id"])
    except ValueError as exc:
        raise PresentationContractError("invalid presentation identifier") from exc
    components = contract.get("components")
    if not isinstance(components, list) or not 1 <= len(components) <= MAX_COMPONENTS:
        raise PresentationContractError("invalid presentation component list")
    component_ids: set[str] = set()
    referenced_ids: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise PresentationContractError("presentation component must be an object")
        component_id = component.get("id")
        component_type = component.get("type")
        if (
            not isinstance(component_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", component_id)
            or component_id in component_ids
        ):
            raise PresentationContractError("invalid or duplicate component id")
        component_ids.add(component_id)
        if component_type not in SUPPORTED_COMPONENTS:
            raise PresentationContractError("unsupported semantic component")
        if component_type == "conversation.markdown":
            _check_keys(component, {"id", "type", "text"})
            if not isinstance(component.get("text"), str) or len(component["text"]) > MAX_TEXT:
                raise PresentationContractError("invalid conversation text")
        else:
            _check_keys(component, {"id", "type", "title", "items"})
            if not isinstance(component.get("title"), str) or len(component["title"]) > 300:
                raise PresentationContractError("invalid component title")
            items = component.get("items")
            if not isinstance(items, list) or len(items) > MAX_ITEMS:
                raise PresentationContractError("invalid component items")
            for item in items:
                if not isinstance(item, dict):
                    raise PresentationContractError("component item must be an object")
                if component_type == "research.source_list":
                    _check_keys(item, {"data_ref", "title", "url", "snippet"})
                    if (
                        not isinstance(item.get("title"), str)
                        or not isinstance(item.get("snippet"), str)
                        or _public_https_url(item.get("url")) is None
                        or len(item.get("title", "")) > 300
                        or len(item.get("snippet", "")) > 600
                        or _contains_secret(item.get("title", ""))
                        or _contains_secret(item.get("snippet", ""))
                    ):
                        raise PresentationContractError("invalid public source reference")
                elif component_type == "workspace.match_list":
                    _check_keys(item, {"data_ref", "path", "line", "text"})
                    if (
                        not _safe_workspace_path(item.get("path"))
                        or type(item.get("line")) is not int
                        or item["line"] < 1
                        or not isinstance(item.get("text"), str)
                        or len(item.get("text", "")) > 600
                        or _contains_secret(item.get("text", ""))
                    ):
                        raise PresentationContractError("invalid workspace result reference")
                else:
                    _check_keys(item, {
                        "data_ref", "latitude", "longitude", "label",
                        "units", "location_type",
                    })
                    if (
                        type(item.get("latitude")) not in (int, float)
                        or not -90 <= item["latitude"] <= 90
                        or type(item.get("longitude")) not in (int, float)
                        or not -180 <= item["longitude"] <= 180
                        or not isinstance(item.get("label"), str)
                        or len(item["label"]) > 120
                        or _contains_secret(item["label"])
                        or item.get("units") != {
                            "latitude": "degrees_north",
                            "longitude": "degrees_east",
                        }
                        or item.get("location_type") != "user_provided"
                    ):
                        raise PresentationContractError(
                            "invalid user-provided map coordinate"
                        )
                reference = item.get("data_ref")
                if not isinstance(reference, str) or not _REFERENCE_ID.fullmatch(reference):
                    raise PresentationContractError("invalid presentation data reference")
                if (
                    authorized_data_refs is None
                    or reference not in authorized_data_refs
                ):
                    raise PresentationContractError("unauthorized presentation data reference")
                referenced_ids.add(reference)

    data_refs = contract.get("data_refs")
    if not isinstance(data_refs, list) or len(data_refs) > MAX_ITEMS:
        raise PresentationContractError("invalid presentation data reference list")
    if len({item.get("id") for item in data_refs if isinstance(item, dict)}) != len(data_refs):
        raise PresentationContractError("duplicate presentation data reference")
    allowed_refs = authorized_data_refs or set()
    for reference in data_refs:
        if (
            not isinstance(reference, dict)
            or set(reference) != {"id", "kind"}
            or not isinstance(reference.get("id"), str)
            or reference["id"] not in allowed_refs
            or reference.get("kind") not in {
                "public_source", "workspace_result",
                "user_provided_coordinates",
            }
        ):
            raise PresentationContractError("unauthorized presentation data reference")
    if referenced_ids != {item["id"] for item in data_refs}:
        raise PresentationContractError("unreferenced or undeclared presentation data")

    if contract_version == CONTRACT_VERSION:
        _validate_v1_1_fields(contract, data_refs, referenced_ids)

    correlation = contract.get("correlation")
    correlation_fields = {
        "request_id", "session_id", "conversation_id", "command_id",
        "execution_id",
    }
    if not isinstance(correlation, dict) or set(correlation) != correlation_fields:
        raise PresentationContractError("invalid presentation correlation")
    for key, value in correlation.items():
        if value is not None and (
            not isinstance(value, str) or len(value) > 256 or "\n" in value
        ):
            raise PresentationContractError("invalid correlation identifier")
    if expected_correlation:
        for key, expected in expected_correlation.items():
            if key in correlation and correlation[key] != expected:
                raise PresentationContractError(
                    f"presentation {key} does not match the authorized request"
                )

    hierarchy = contract.get("content_hierarchy")
    if (
        not isinstance(hierarchy, list)
        or not hierarchy
        or len(set(hierarchy)) != len(hierarchy)
        or any(component_id not in component_ids for component_id in hierarchy)
        or contract.get("focus") not in component_ids
    ):
        raise PresentationContractError("invalid content hierarchy or focus")
    interactions = contract.get("interactions")
    if not isinstance(interactions, list) or len(interactions) > MAX_ITEMS:
        raise PresentationContractError("invalid presentation interactions")
    source_ids = {
        item["id"] for item in data_refs if item["kind"] == "public_source"
    }
    interaction_ids: set[str] = set()
    for interaction in interactions:
        if (
            not isinstance(interaction, dict)
            or set(interaction) != {
                "id", "type", "data_ref", "required_permissions",
                "user_gesture_required",
            }
            or not isinstance(interaction.get("id"), str)
            or interaction.get("id") in interaction_ids
            or interaction.get("type") != "external_source_navigation"
            or interaction.get("data_ref") not in source_ids
            or interaction.get("required_permissions") != ["web:read"]
            or interaction.get("user_gesture_required") is not True
        ):
            raise PresentationContractError(
                "unsupported interaction; consequential actions must use backend authorization"
            )
        interaction_ids.add(interaction["id"])
    if contract.get("visualizations") != []:
        raise PresentationContractError("no visualization capability is registered")
    modalities = contract.get("modalities")
    if (
        not isinstance(modalities, list)
        or not modalities
        or any(item not in {"text", "links", "map"} for item in modalities)
    ):
        raise PresentationContractError("unsupported presentation modality")
    if (
        not isinstance(contract.get("assistant_presence"), dict)
        or set(contract["assistant_presence"]) != {"mode", "state"}
        or contract["assistant_presence"].get("mode") != "inline"
        or contract["assistant_presence"].get("state") not in {"available", "error"}
    ):
        raise PresentationContractError("invalid assistant presence")
    if (
        not isinstance(contract.get("accessibility"), dict)
        or set(contract["accessibility"]) != {
            "reading_order", "announce_updates", "non_color_status",
        }
        or contract["accessibility"].get("reading_order") != hierarchy
        or type(contract["accessibility"].get("announce_updates")) is not bool
        or type(contract["accessibility"].get("non_color_status")) is not bool
    ):
        raise PresentationContractError("accessibility constraints are required")
    if (
        not isinstance(contract.get("responsive"), dict)
        or set(contract["responsive"]) != {"reflow", "minimum_width"}
        or contract["responsive"].get("reflow") != "single_column"
    ):
        raise PresentationContractError("responsive constraints are required")
    if (
        not isinstance(contract.get("transitions"), dict)
        or set(contract["transitions"]) != {"on_unsupported", "on_error"}
        or contract["transitions"].get("on_unsupported") != "conversation_fallback"
        or contract["transitions"].get("on_error") != "retain_observed_text"
    ):
        raise PresentationContractError("transition behavior is required")
    if (
        not isinstance(contract.get("errors"), list)
        or any(not isinstance(error, str) or len(error) > 300
               for error in contract["errors"])
        or any(_contains_secret(error) for error in contract["errors"])
    ):
        raise PresentationContractError("invalid presentation errors")
    fallback = contract.get("fallback")
    if (
        not isinstance(fallback, dict)
        or set(fallback) != {"type", "text"}
        or fallback.get("type") != "conversation.markdown"
        or not isinstance(fallback.get("text"), str)
        or len(fallback.get("text", "")) > MAX_TEXT
        or _contains_secret(fallback.get("text", ""))
    ):
        raise PresentationContractError("a conversation fallback is required")
    requirements = contract.get("renderer_requirements")
    if (
        not isinstance(requirements, dict)
        or set(requirements) != (
            {
                "contract_version", "required_components", "fallback_components",
            }
            if contract_version == "1.0"
            else {
                "contract_version", "supported_contract_versions",
                "required_components", "required_modalities",
                "fallback_components",
            }
        )
        or requirements.get("contract_version") != contract_version
        or (
            contract_version == CONTRACT_VERSION
            and requirements.get("supported_contract_versions")
            != sorted(SUPPORTED_CONTRACT_VERSIONS)
        )
        or not isinstance(requirements.get("required_components"), list)
        or any(value not in SUPPORTED_COMPONENTS
               for value in requirements["required_components"])
        or (
            contract_version == CONTRACT_VERSION
            and (
                not isinstance(requirements.get("required_modalities"), list)
                or not requirements["required_modalities"]
                or any(value not in {"text", "links", "map"}
                       for value in requirements["required_modalities"])
            )
        )
        or requirements.get("fallback_components") != ["conversation.markdown"]
        or requirements.get("required_components") != [
            component["type"] for component in components
        ]
    ):
        raise PresentationContractError("invalid renderer compatibility requirements")
    return json.loads(json.dumps(contract, ensure_ascii=True))


def _validate_v1_1_fields(
    contract: dict[str, Any],
    data_refs: list[dict[str, Any]],
    referenced_ids: set[str],
) -> None:
    task_state = contract.get("task_state")
    if (
        not isinstance(task_state, dict)
        or set(task_state) != {"status", "message"}
        or task_state.get("status") not in {
            "completed", "partial", "error", "unsupported",
        }
        or not isinstance(task_state.get("message"), str)
        or len(task_state["message"]) > MAX_TEXT
        or _contains_secret(task_state["message"])
    ):
        raise PresentationContractError("invalid canonical task state")

    source_provenance = contract.get("source_provenance")
    ref_kinds = {item["id"]: item["kind"] for item in data_refs}
    if (
        not isinstance(source_provenance, list)
        or len(source_provenance) > MAX_ITEMS
    ):
        raise PresentationContractError("invalid source provenance")
    provenance_refs: set[str] = set()
    for item in source_provenance:
        if (
            not isinstance(item, dict)
            or set(item) != {"data_ref", "source_type", "observed_at"}
            or item.get("data_ref") not in referenced_ids
            or item.get("data_ref") in provenance_refs
            or item.get("source_type") not in {
                "public_web", "authorized_workspace",
                "user_provided_coordinates",
            }
            or (
                item["source_type"] == "public_web"
                and ref_kinds.get(item["data_ref"]) != "public_source"
            )
            or (
                item["source_type"] == "authorized_workspace"
                and ref_kinds.get(item["data_ref"]) != "workspace_result"
            )
            or (
                item["source_type"] == "user_provided_coordinates"
                and ref_kinds.get(item["data_ref"])
                != "user_provided_coordinates"
            )
            or not isinstance(item.get("observed_at"), str)
        ):
            raise PresentationContractError("invalid source provenance")
        try:
            observed_at = datetime.fromisoformat(
                item["observed_at"].replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise PresentationContractError(
                "invalid source observation timestamp"
            ) from exc
        if observed_at.tzinfo is None:
            raise PresentationContractError(
                "source observation timestamp must include a timezone"
            )
        provenance_refs.add(item["data_ref"])
    if provenance_refs != referenced_ids:
        raise PresentationContractError(
            "every referenced result must retain source provenance"
        )

    if contract.get("media_refs") != []:
        raise PresentationContractError(
            "media references require an authorized media service"
        )
    if contract.get("user_preferences") is not None:
        raise PresentationContractError(
            "user presentation preferences are not configured"
        )
    view_state = contract.get("view_state")
    if (
        not isinstance(view_state, dict)
        or set(view_state) != {"focus", "selected_data_ref"}
        or view_state.get("focus") != contract.get("focus")
        or (
            view_state.get("selected_data_ref") is not None
            and view_state.get("selected_data_ref") not in referenced_ids
        )
    ):
        raise PresentationContractError("invalid presentation view state")


def render_presentation_text(
    contract: dict[str, Any],
    *,
    authorized_data_refs: set[str],
) -> str:
    """Small non-web renderer for the same semantic contract."""
    valid = validate_presentation_contract(
        contract, authorized_data_refs=authorized_data_refs,
    )
    output: list[str] = []
    components_by_id = {
        component["id"]: component for component in valid["components"]
    }
    for component_id in valid["content_hierarchy"]:
        component = components_by_id[component_id]
        component_type = component["type"]
        if component_type == "conversation.markdown":
            output.append(component["text"])
        elif component_type == "research.source_list":
            output.append(component["title"])
            output.extend(
                f"- {item['title']}: {item['url']}"
                + (f" — {item['snippet']}" if item["snippet"] else "")
                for item in component["items"]
            )
        elif component_type == "workspace.match_list":
            output.append(component["title"])
            output.extend(
                f"- {item['path']}:{item['line']}: {item['text']}"
                for item in component["items"]
            )
        elif component_type == "geospatial.point_map":
            output.append(component["title"])
            output.extend(
                f"- {item['label']} (user-provided coordinates; "
                "not live device location)"
                for item in component["items"]
            )
    return "\n\n".join(part for part in output if part)


def _check_keys(value: dict[str, Any], allowed: set[str]) -> None:
    if set(value) != allowed:
        raise PresentationContractError("semantic component contains unsupported fields")


def _safe_text(value: str, limit: int = MAX_TEXT) -> str:
    from research_engine.tool_registry import scrub_secrets

    text, _ = scrub_secrets(str(value or ""))
    return text[:limit]


def _contains_secret(value: str) -> bool:
    from research_engine.tool_registry import scrub_secrets

    scrubbed, redacted = scrub_secrets(value)
    return redacted or scrubbed != value


def _public_https_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or re.search(r"[\s<>\"'`\\]", value)
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
            or any(
                re.search(r"(?:token|secret|password|credential|auth|session|signature|^key$|^sig$)",
                          key, re.IGNORECASE)
                for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
            )
        ):
            return None
        return value
    except ValueError:
        return None


def _safe_workspace_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 512:
        return None
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or re.search(r"[\r\n`<>]", normalized)
    ):
        return None
    return normalized


def _json_object(value: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def adapt_presentation_for_endpoint(
    contract: dict[str, Any],
    endpoint: dict[str, Any],
    *,
    authorized_data_refs: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Adapt a durable contract to endpoint claims without granting authority."""
    validated = validate_presentation_contract(
        contract, authorized_data_refs=authorized_data_refs,
    )
    supported_versions = set(endpoint.get("presentation_contract_versions") or ())
    compatible_versions = sorted(
        SUPPORTED_CONTRACT_VERSIONS & supported_versions,
        key=lambda version: tuple(int(part) for part in version.split(".")),
        reverse=True,
    )
    if not compatible_versions:
        raise PresentationContractError(
            "endpoint has no compatible presentation contract version"
        )
    modalities = set(endpoint.get("supported_modalities") or ())
    capabilities = set(endpoint.get("validated_capabilities") or ())
    capabilities.update(
        f"presentation.{modality}"
        for modality in modalities
        if f"presentation.{modality}" in {
            "presentation.text", "presentation.links", "presentation.image",
            "presentation.audio", "presentation.map", "presentation.video",
            "presentation.voice",
        }
    )
    component_capabilities = {
        "conversation.markdown": "presentation.text",
        "research.source_list": "presentation.links",
        "workspace.match_list": "presentation.text",
        "geospatial.point_map": "presentation.map",
    }
    required_components = {
        component["type"] for component in validated["components"]
    }
    missing_components = sorted(
        component for component in required_components
        if component_capabilities.get(component) not in capabilities
    )
    missing_modalities = sorted(
        set(validated["modalities"]) - modalities
    )
    selected_version = compatible_versions[0]
    version_downgrade = (
        selected_version == "1.0"
        and validated["contract_version"] == CONTRACT_VERSION
    )
    fallback_used = bool(
        missing_components or missing_modalities or version_downgrade
    )
    result = json.loads(json.dumps(validated, ensure_ascii=True))
    fallback_reason = None
    if fallback_used:
        reasons = []
        if missing_components or missing_modalities:
            reasons.append("renderer components or modalities are unsupported")
        if version_downgrade:
            reasons.append("endpoint supports only contract v1.0")
        fallback_reason = "Endpoint " + " and ".join(reasons) + "; preserved the result as text."
        if selected_version == "1.0":
            rendered = render_presentation_text(
                validated, authorized_data_refs=authorized_data_refs,
            )
            provenance = validated.get("source_provenance") or []
            if provenance:
                lines = [
                    f"- {item['source_type']} observed at {item['observed_at']}"
                    for item in provenance
                ]
                rendered = f"{rendered}\n\nSource provenance:\n" + "\n".join(lines)
            correlation = validated["correlation"]
            result = build_conversation_presentation(
                rendered,
                request_id=correlation["request_id"],
                session_id=correlation["session_id"],
                conversation_id=correlation["conversation_id"],
            )
    if selected_version == "1.0" and result["contract_version"] == CONTRACT_VERSION:
        for field in (
            "task_state", "source_provenance", "media_refs",
            "user_preferences", "view_state",
        ):
            result.pop(field, None)
    result["contract_version"] = selected_version
    result["renderer_requirements"]["contract_version"] = selected_version
    result["renderer_requirements"]["required_components"] = [
        component["type"] for component in result["components"]
    ]
    if selected_version == CONTRACT_VERSION:
        result["renderer_requirements"]["supported_contract_versions"] = sorted(
            SUPPORTED_CONTRACT_VERSIONS
        )
        result["renderer_requirements"]["required_modalities"] = result["modalities"]
    else:
        result["renderer_requirements"].pop(
            "supported_contract_versions", None,
        )
        result["renderer_requirements"].pop("required_modalities", None)
    adapted = validate_presentation_contract(
        result, authorized_data_refs=authorized_data_refs,
    )
    compatibility = {
        "decision": "text_fallback" if fallback_used else "compatible",
        "contract_version": selected_version,
        "required_components": sorted(required_components),
        "missing_components": missing_components,
        "required_modalities": sorted(set(validated["modalities"])),
        "missing_modalities": missing_modalities,
        "fallback_reason": fallback_reason,
        "authorization_granted": False,
        "verified_operational": False,
    }
    return adapted, compatibility


__all__ = [
    "CONTRACT_VERSION",
    "PresentationContractError",
    "adapt_presentation_for_endpoint",
    "build_conversation_presentation",
    "build_execution_presentation",
    "render_presentation_text",
    "validate_presentation_contract",
]
