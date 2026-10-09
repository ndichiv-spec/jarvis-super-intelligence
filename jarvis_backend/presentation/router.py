"""Authenticated presentation contract discovery and client capability negotiation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from ..core import get_current_user, has_permission
from .context import presentation_context_service
from .negotiation import negotiate_renderers
from .registry import presentation_registry
from .schemas import (
    PRESENTATION_PROTOCOL,
    PRESENTATION_VERSION,
    PresentationCapabilities,
    PresentationPreferenceUpdate,
    RendererNegotiation,
    UserPresentationProfile,
)
from .state import presentation_state_manager
from .location_data import ephemeral_location_data

router = APIRouter(prefix="/api/v1/presentation", tags=["presentation"])


class MapInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["zoom", "pan", "recenter"]


@router.get("/location/authorization")
async def check_location_authorization(
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict[str, bool]:
    return {"authorized": has_permission(user, "location:read")}


@router.get("/contract")
async def get_presentation_contract(_user: dict = Depends(get_current_user)):  # noqa: B008
    return {
        "protocol": PRESENTATION_PROTOCOL,
        "version": PRESENTATION_VERSION,
        "renderers": [
            renderer.model_dump(mode="json", by_alias=True)
            for renderer in presentation_registry.renderers
        ],
        "intentOwner": "jarvis_core",
        "executionAuthority": "backend_policy",
    }


@router.get("/capabilities")
async def get_presentation_capabilities(_user: dict = Depends(get_current_user)):  # noqa: B008
    return {
        "capabilities": [
            definition.model_dump(mode="json", by_alias=True)
            for definition in presentation_registry.definitions()
        ],
    }


@router.get("/renderers")
async def get_presentation_renderers(_user: dict = Depends(get_current_user)):  # noqa: B008
    return {
        "renderers": [
            renderer.model_dump(mode="json", by_alias=True)
            for renderer in presentation_registry.renderers
        ],
    }


@router.get("/environments")
async def get_presentation_environments(_user: dict = Depends(get_current_user)):  # noqa: B008
    environments: dict[str, dict] = {}
    for definition in presentation_registry.definitions():
        for binding in definition.presentation.environments:
            entry = environments.setdefault(binding.environment, {
                "id": binding.environment,
                "capabilities": [],
                "suitability": [],
            })
            entry["capabilities"].append(definition.id)
            entry["suitability"].append(binding.suitability)
    return {"environments": list(environments.values())}


@router.post("/clients/register")
async def register_presentation_client(
    capabilities: PresentationCapabilities,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    presentation_context_service.save_client_capabilities(str(user["id"]), capabilities)
    negotiated = negotiate_renderers(capabilities)
    return {
        "clientId": negotiated.client_id,
        "protocolVersion": PRESENTATION_VERSION,
        "accepted": True,
        "runtimeCapabilities": negotiated.model_dump(mode="json", by_alias=True),
    }


@router.post("/negotiate", response_model=RendererNegotiation)
async def negotiate_presentation(
    capabilities: PresentationCapabilities,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> RendererNegotiation:
    presentation_context_service.save_client_capabilities(str(user["id"]), capabilities)
    return negotiate_renderers(capabilities)


@router.get("/preferences", response_model=UserPresentationProfile)
async def get_preferences(user: dict = Depends(get_current_user)):  # noqa: B008
    return presentation_state_manager.get_preferences(str(user["id"]))


@router.put("/preferences", response_model=UserPresentationProfile)
async def update_preferences(
    update: PresentationPreferenceUpdate,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> UserPresentationProfile:
    return presentation_state_manager.update_preferences(str(user["id"]), update)


@router.get("/state/{session_id}")
async def get_presentation_state(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
):
    from ..chat_service import chat_service

    chat_service.get_session(str(user["id"]), session_id)
    return {
        "state": presentation_state_manager.get_state(str(user["id"]), session_id),
        "history": presentation_state_manager.get_history(str(user["id"]), session_id),
    }


@router.get("/location/{presentation_id}")
async def get_location_presentation_data(
    presentation_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    from ..chat_service import chat_service

    if not has_permission(user, "location:read"):
        raise HTTPException(status_code=403, detail="Location access is not authorized.")
    entry = ephemeral_location_data.get_for_presentation(
        presentation_id,
        user_id=str(user["id"]),
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Location presentation not found or expired.")
    chat_service.get_session(str(user["id"]), entry["session_id"])
    value = dict(entry["value"])
    captured_at = datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
    age_seconds = max(0, (datetime.now(UTC) - captured_at.astimezone(UTC)).total_seconds())
    if age_seconds > 120:
        raise HTTPException(status_code=410, detail="The current-location result has expired.")
    value["freshness"] = {
        "capturedAt": captured_at.astimezone(UTC).isoformat(),
        "ageSeconds": round(age_seconds, 3),
    }
    return value


@router.post("/location/{presentation_id}/rendered")
async def report_location_map_rendered(
    presentation_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    from ..chat_service import chat_service
    from ..runtime_events import (
        EventSensitivity,
        RuntimeEventSource,
        RuntimeEventType,
        RuntimeState,
        emit_runtime_event,
    )

    user_id = str(user["id"])
    if not has_permission(user, "location:read"):
        raise HTTPException(status_code=403, detail="Location access is not authorized.")
    entry = ephemeral_location_data.get_for_presentation(
        presentation_id,
        user_id=user_id,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Location presentation not found or expired.")
    chat_service.get_session(user_id, entry["session_id"])
    rendered = ephemeral_location_data.mark_rendered(
        presentation_id,
        user_id=user_id,
        session_id=entry["session_id"],
    )
    if rendered is None:
        raise HTTPException(status_code=404, detail="Location presentation not found or expired.")
    if not rendered["already_rendered"]:
        emit_runtime_event(
            event_type=RuntimeEventType.MAP_CREATED,
            user_id=user_id,
            session_id=entry["session_id"],
            request_id=entry["request_id"],
            source=RuntimeEventSource.PRESENTATION_RUNTIME,
            capability_id="location.current",
            execution_id=entry["execution_id"],
            presentation_id=presentation_id,
            state=RuntimeState.COMPLETED,
            sensitivity=EventSensitivity.SENSITIVE,
            data={"renderer": "map.renderer"},
        )
    return {"created": not rendered["already_rendered"]}


@router.post("/location/{presentation_id}/interactions")
async def report_location_map_interaction(
    presentation_id: str,
    interaction: MapInteraction,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    from ..chat_service import chat_service
    from ..runtime_events import (
        EventSensitivity,
        RuntimeEventSource,
        RuntimeEventType,
        RuntimeState,
        emit_runtime_event,
    )

    user_id = str(user["id"])
    if not has_permission(user, "location:read"):
        raise HTTPException(status_code=403, detail="Location access is not authorized.")
    entry = ephemeral_location_data.get_for_presentation(
        presentation_id,
        user_id=user_id,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Location presentation not found or expired.")
    chat_service.get_session(user_id, entry["session_id"])
    if not entry["rendered"]:
        raise HTTPException(status_code=409, detail="The location map has not been rendered.")
    emit_runtime_event(
        event_type=RuntimeEventType.MAP_UPDATED,
        user_id=user_id,
        session_id=entry["session_id"],
        request_id=entry["request_id"],
        source=RuntimeEventSource.PRESENTATION_RUNTIME,
        capability_id="location.current",
        execution_id=entry["execution_id"],
        presentation_id=presentation_id,
        state=RuntimeState.COMPLETED,
        sensitivity=EventSensitivity.SENSITIVE,
        data={"interaction": interaction.action},
    )
    return {"updated": True}
