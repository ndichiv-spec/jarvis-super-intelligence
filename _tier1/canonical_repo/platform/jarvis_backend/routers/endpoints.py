from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import get_current_user
from ..endpoint_registry import EndpointRegistry
from ..presentation_contract import (
    PresentationContractError,
    adapt_presentation_for_endpoint,
)
from ..runtime import PresentationRevisionConflictError, runtime

router = APIRouter(prefix="/api/v1", tags=["endpoints"])


class EndpointRegistrationIn(BaseModel):
    name: Optional[str] = None
    endpoint_type: str = "browser"
    endpoint_url: Optional[str] = None
    session_id: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list, max_length=64)
    supported_modalities: List[str] = Field(default_factory=lambda: ["text"])
    presentation_contract_versions: List[str] = Field(default_factory=lambda: ["1.1"])
    owner_id: Optional[str] = None
    viewport: Dict[str, Any] = Field(default_factory=dict)
    input_capabilities: List[str] = Field(default_factory=list)
    output_capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EndpointHeartbeatIn(BaseModel):
    status: Optional[str] = None
    capabilities: Optional[List[str]] = None
    supported_modalities: Optional[List[str]] = None
    presentation_contract_versions: Optional[List[str]] = None
    viewport: Optional[Dict[str, Any]] = None
    input_capabilities: Optional[List[str]] = None
    output_capabilities: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class EndpointNegotiateIn(BaseModel):
    advertised_capabilities: Optional[List[str]] = None
    supported_modalities: Optional[List[str]] = None
    presentation_contract_versions: Optional[List[str]] = None


class PresentationRecoveryIn(BaseModel):
    endpoint_id: str
    idempotency_key: str = Field(min_length=1, max_length=255)


@router.get("/endpoints")
async def list_registered_endpoints(user: Dict[str, Any] = Depends(get_current_user)):
    return {"endpoints": EndpointRegistry().list_endpoints(user["id"]) }


@router.post("/endpoints/register")
async def register_endpoint(payload: EndpointRegistrationIn, user: Dict[str, Any] = Depends(get_current_user)):
    if payload.owner_id and payload.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_id is server-authoritative and cannot be overridden")
    try:
        return {"endpoint": EndpointRegistry().register_endpoint(
            user_id=user["id"],
            endpoint_id=None,
            name=payload.name,
            endpoint_type=payload.endpoint_type,
            endpoint_url=payload.endpoint_url,
            session_id=payload.session_id,
            capabilities=payload.capabilities,
            supported_modalities=payload.supported_modalities,
            presentation_contract_versions=payload.presentation_contract_versions,
            metadata={
                **payload.metadata,
                "viewport": payload.viewport,
                "input_capabilities": payload.input_capabilities,
                "output_capabilities": payload.output_capabilities,
            },
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        return {"endpoint": EndpointRegistry().get_endpoint(endpoint_id, user_id=user["id"]) }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/endpoints/{endpoint_id}/heartbeat")
async def endpoint_heartbeat(
    endpoint_id: str,
    payload: EndpointHeartbeatIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        metadata = dict(payload.metadata or {})
        if payload.viewport is not None:
            metadata["viewport"] = payload.viewport
        if payload.input_capabilities is not None:
            metadata["input_capabilities"] = payload.input_capabilities
        if payload.output_capabilities is not None:
            metadata["output_capabilities"] = payload.output_capabilities
        return {"endpoint": EndpointRegistry().heartbeat(
            user_id=user["id"],
            endpoint_id=endpoint_id,
            status=payload.status,
            capabilities=payload.capabilities,
            supported_modalities=payload.supported_modalities,
            presentation_contract_versions=payload.presentation_contract_versions,
            metadata=metadata,
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/endpoints/{endpoint_id}/disconnect")
async def disconnect_endpoint(endpoint_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        return {"endpoint": EndpointRegistry().heartbeat(
            user_id=user["id"], endpoint_id=endpoint_id, status="disconnected",
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/endpoints/{endpoint_id}/select")
async def select_endpoint(endpoint_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        return {"endpoint": EndpointRegistry().select_endpoint(
            user_id=user["id"], endpoint_id=endpoint_id,
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/endpoints/{endpoint_id}/negotiate")
async def endpoint_negotiation(
    endpoint_id: str,
    payload: EndpointNegotiateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        return {"negotiation": EndpointRegistry().negotiate_capabilities(
            user_id=user["id"],
            endpoint_id=endpoint_id,
            advertised_capabilities=payload.advertised_capabilities,
            supported_modalities=payload.supported_modalities,
            presentation_contract_versions=payload.presentation_contract_versions,
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/endpoints/{endpoint_id}/revoke")
async def revoke_endpoint(endpoint_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        return {"endpoint": EndpointRegistry().revoke_endpoint(user_id=user["id"], endpoint_id=endpoint_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/endpoints/{endpoint_id}/events")
async def endpoint_events(
    endpoint_id: str,
    limit: int = 100,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        return {"events": EndpointRegistry().list_audit_events(
            user_id=user["id"], endpoint_id=endpoint_id, limit=limit,
        )}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/presentations/{task_id}/revisions")
async def presentation_revisions(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return {
        "revisions": runtime.list_presentation_revisions(
            task_id, owner_id=user["id"],
        )
    }


@router.post("/presentations/{task_id}/recover")
async def recover_presentation(
    task_id: str,
    payload: PresentationRecoveryIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    revisions = runtime.list_presentation_revisions(
        task_id, owner_id=user["id"],
    )
    if not revisions:
        raise HTTPException(status_code=404, detail="presentation task not found")
    try:
        endpoint = EndpointRegistry().get_endpoint(
            payload.endpoint_id, user["id"],
        )
        if endpoint["status"] != "connected":
            raise HTTPException(
                status_code=409,
                detail="endpoint must reconnect and negotiate before recovery",
            )
        latest = revisions[-1]
        data_refs = {
            item["id"] for item in latest["presentation"].get("data_refs", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        presentation, compatibility = adapt_presentation_for_endpoint(
            latest["presentation"],
            endpoint,
            authorized_data_refs=data_refs,
        )
        revision = runtime.create_presentation_revision(
            task_id=task_id,
            owner_id=user["id"],
            request_id=latest["request_id"],
            conversation_id=latest["conversation_id"],
            command_id=latest["command_id"],
            execution_id=latest["execution_id"],
            endpoint_id=endpoint["endpoint_id"],
            presentation=presentation,
            expected_revision=latest["revision"],
            idempotency_key=payload.idempotency_key,
            compatibility=compatibility,
            fallback_reason=compatibility["fallback_reason"],
        )
        compatibility = revision["compatibility"]
        return {"revision": revision, "compatibility": compatibility}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PresentationContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PresentationRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
