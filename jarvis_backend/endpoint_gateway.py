"""Authenticated endpoint registration and session attachment."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .chat_service import chat_service
from .core import get_current_user, get_store
from .db import kv_insert_if_absent
from .presentation.negotiation import negotiate_renderers
from .presentation.schemas import PresentationCapabilities
from .runtime_events import (
    EventSensitivity,
    RuntimeEventSource,
    RuntimeEventType,
    runtime_event_service,
)

router = APIRouter(prefix="/api/v1/endpoints", tags=["endpoints"])
_IDENTIFIER = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")]


class EndpointRegistration(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    device_identity: _IDENTIFIER
    runtime_version: str | None = Field(default=None, max_length=64)
    capabilities: PresentationCapabilities
    session_id: _IDENTIFIER


class EndpointHeartbeat(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    session_id: _IDENTIFIER | None = None


def _endpoint_token(endpoint_id: str) -> str:
    return f"jep_{endpoint_id}.{secrets.token_urlsafe(32)}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _require_endpoint_manager(user: dict[str, Any]) -> str:
    if user.get("api_key_id") and not (
        any(
            scope in {"endpoints:manage", "endpoints:*", "admin"}
            for scope in (user.get("scopes") or [])
            if isinstance(scope, str)
        )
    ):
        raise HTTPException(status_code=403, detail="Endpoint management permission is required.")
    owner_id = str(user.get("id") or "")
    if not owner_id:
        raise HTTPException(status_code=403, detail="An authenticated owner identity is required.")
    return owner_id


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _credential_expiry() -> str:
    return (datetime.now(UTC) + timedelta(days=365)).isoformat()


def _store():
    return get_store("endpoints")


def _audit_endpoint_action(
    *,
    action: str,
    owner_id: str,
    endpoint_id: str,
    request_id: str | None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    from infrastructure.audit_events import get_audit_service

    get_audit_service().record(
        event_type=f"endpoint.{action}",
        category="security",
        action=action,
        user_id=owner_id,
        resource_type="endpoint",
        resource_id=endpoint_id,
        request_id=request_id or "",
        session_id=session_id or "",
        metadata=metadata or {},
    )


def _endpoint_key(owner_id: str, device_identity: str) -> str:
    return f"{owner_id}:{device_identity}"


def _find_owned_endpoint(owner_id: str, endpoint_id: str) -> tuple[str, dict[str, Any]]:
    records = _store().reload()
    for key, record in records.items():
        if record.get("endpoint_id") == endpoint_id:
            if record.get("owner_id") != owner_id:
                break
            return key, record
    raise HTTPException(status_code=404, detail="Endpoint not found.")


def _authenticate_endpoint(request: Request) -> tuple[str, str, str, dict[str, Any]]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.startswith("jep_"):
        raise HTTPException(status_code=401, detail="Endpoint authentication required.")
    try:
        endpoint_id = token[4:].split(".", 1)[0]
    except (IndexError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid endpoint credential.")
    for key, record in _store().reload().items():
        if record.get("endpoint_id") != endpoint_id:
            continue
        candidate_hash = _token_hash(token)
        credentials = record.get("credentials") or []
        valid = any(
            credential.get("expires_at", "") > _now()
            and hmac.compare_digest(str(credential.get("hash") or ""), candidate_hash)
            for credential in credentials
            if isinstance(credential, dict)
        )
        if not valid:
            break
        if record.get("state") in {"unauthorized", "unhealthy"}:
            raise HTTPException(status_code=403, detail="Endpoint is not authorized.")
        return str(record["owner_id"]), key, endpoint_id, record
    raise HTTPException(status_code=401, detail="Invalid endpoint credential.")


def _public_endpoint(record: dict[str, Any]) -> dict[str, Any]:
    last_seen = datetime.fromisoformat(record["last_seen"])
    age_seconds = max(0, (datetime.now(UTC) - last_seen.astimezone(UTC)).total_seconds())
    connected = record.get("connectivity") == "connected" and age_seconds <= 90
    state = record.get("state") or (
        "connected" if connected else "disconnected"
    )
    if state == "connected" and not connected:
        state = "disconnected"
    return {
        "endpointId": record["endpoint_id"],
        "runtimeVersion": record.get("runtime_version"),
        "capabilities": record["capabilities"],
        "state": state,
        "connectivity": state,
        "securityState": "authenticated",
        "activeSessions": list(record.get("active_sessions", [])),
        "lastSeen": record["last_seen"],
    }


def _emit_endpoint_event(
    *,
    event_type: RuntimeEventType,
    owner_id: str,
    session_id: str,
    endpoint_id: str,
    request_id: str | None = None,
    platform: str | None = None,
    connectivity: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    data: dict[str, Any] = {"endpointId": endpoint_id}
    if platform:
        data["platform"] = platform
    if connectivity:
        data["connectivity"] = connectivity
    if details:
        data.update(details)
    runtime_event_service.emit(
        event_type=event_type,
        user_id=owner_id,
        session_id=session_id,
        source=RuntimeEventSource.DEVICE_RUNTIME,
        event_id=(
            str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jarvis:endpoint:{endpoint_id}:{session_id}:{event_type.value}:{request_id}",
            ))
            if request_id else None
        ),
        request_id=request_id,
        state=None,
        data=data,
        sensitivity=EventSensitivity.USER,
    )


@router.post("/register")
async def register_endpoint(
    registration: EndpointRegistration,
    http_request: Request,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    owner_id = _require_endpoint_manager(user)
    session = chat_service.get_session(owner_id, registration.session_id)
    if session.get("archived", False):
        raise HTTPException(status_code=409, detail="Archived conversations cannot attach endpoints.")
    key = _endpoint_key(owner_id, registration.device_identity)
    store = _store()
    now = _now()
    endpoint_id = str(uuid.uuid4())
    endpoint_token = _endpoint_token(endpoint_id)
    initial = {
        "endpoint_id": endpoint_id,
        "owner_id": owner_id,
        "device_identity": registration.device_identity,
        "runtime_version": registration.runtime_version,
        "capabilities": registration.capabilities.model_dump(mode="json", by_alias=True),
        "credentials": [{
            "hash": _token_hash(endpoint_token),
            "expires_at": _credential_expiry(),
        }],
        "state": "registered",
        "connectivity": "disconnected",
        "active_sessions": [],
        "last_seen": now,
        "created_at": now,
    }

    created = kv_insert_if_absent(store.name, key, initial)
    if created:
        record = initial
    else:
        existing = store.reload().get(key)
        if existing is None:
            raise HTTPException(status_code=503, detail="Endpoint registration could not be persisted.")
        endpoint_id = str(existing["endpoint_id"])
        endpoint_token = _endpoint_token(endpoint_id)

        def refresh(existing: dict[str, Any]) -> dict[str, Any]:
            credentials = [
                item for item in existing.get("credentials", [])
                if isinstance(item, dict) and item.get("expires_at", "") > now
            ]
            if not credentials and existing.get("credential_hash"):
                credentials.append({
                    "hash": existing["credential_hash"],
                    "expires_at": now,
                })
            credentials.append({
                "hash": _token_hash(endpoint_token),
                "expires_at": _credential_expiry(),
            })
            return {
                **existing,
                "runtime_version": registration.runtime_version,
                "capabilities": registration.capabilities.model_dump(mode="json", by_alias=True),
                "credentials": credentials[-10:],
                "state": "registered",
                "connectivity": "disconnected",
                "last_seen": now,
            }

        record = store.update_key(key, refresh)
        if record is None:
            raise HTTPException(status_code=503, detail="Endpoint registration could not be persisted.")

    _emit_endpoint_event(
        event_type=(
            RuntimeEventType.DEVICE_DISCOVERED
            if created
            else RuntimeEventType.DEVICE_STATE_UPDATED
        ),
        owner_id=owner_id,
        session_id=registration.session_id,
        endpoint_id=record["endpoint_id"],
        request_id=getattr(http_request.state, "request_id", None),
        platform=registration.capabilities.platform,
        connectivity="registered" if created else "connecting",
    )
    _audit_endpoint_action(
        action="registered" if created else "credential_rotated",
        owner_id=owner_id,
        endpoint_id=record["endpoint_id"],
        request_id=getattr(http_request.state, "request_id", None),
        session_id=registration.session_id,
        metadata={"device_identity": registration.device_identity},
    )
    negotiated = negotiate_renderers(registration.capabilities)
    return {
        "endpoint": _public_endpoint(record),
        "endpointToken": endpoint_token,
        "runtimeCapabilities": negotiated.model_dump(mode="json", by_alias=True),
    }


@router.get("")
async def list_endpoints(
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict[str, list[dict[str, Any]]]:
    owner_id = _require_endpoint_manager(user)
    records = _store().reload()
    return {
        "endpoints": [
            _public_endpoint(record)
            for record in records.values()
            if record.get("owner_id") == owner_id
        ],
    }


@router.post("/{endpoint_id}/heartbeat")
async def heartbeat_endpoint(
    endpoint_id: _IDENTIFIER,
    heartbeat: EndpointHeartbeat,
    request: Request,
) -> dict[str, Any]:
    owner_id, key, authenticated_endpoint_id, prior_record = _authenticate_endpoint(request)
    if authenticated_endpoint_id != endpoint_id:
        raise HTTPException(status_code=404, detail="Endpoint not found.")
    if heartbeat.session_id:
        session = chat_service.get_session(owner_id, heartbeat.session_id)
        if session.get("archived", False):
            raise HTTPException(status_code=409, detail="Archived conversations cannot attach endpoints.")

    now = _now()

    def refresh(existing: dict[str, Any]) -> dict[str, Any]:
        if existing.get("owner_id") != owner_id or existing.get("endpoint_id") != endpoint_id:
            return existing
        return {
            **existing,
            "state": "connected",
            "connectivity": "connected",
            "last_seen": now,
        }

    record = _store().update_key(key, refresh)
    if record is None or record.get("owner_id") != owner_id or record.get("endpoint_id") != endpoint_id:
        raise HTTPException(status_code=404, detail="Endpoint not found.")
    if prior_record.get("connectivity") != "connected":
        _audit_endpoint_action(
            action="connected",
            owner_id=owner_id,
            endpoint_id=endpoint_id,
            request_id=getattr(request.state, "request_id", None),
            session_id=heartbeat.session_id,
        )
    return {"endpoint": _public_endpoint(record)}


@router.post("/{endpoint_id}/sessions/{session_id}")
async def attach_session(
    endpoint_id: _IDENTIFIER,
    session_id: _IDENTIFIER,
    request: Request,
) -> dict[str, Any]:
    owner_id, key, authenticated_endpoint_id, _endpoint = _authenticate_endpoint(request)
    if authenticated_endpoint_id != endpoint_id:
        raise HTTPException(status_code=404, detail="Endpoint not found.")
    session = chat_service.get_session(owner_id, session_id)
    if session.get("archived", False):
        raise HTTPException(status_code=409, detail="Archived conversations cannot attach endpoints.")

    def attach(existing: dict[str, Any]) -> dict[str, Any]:
        if existing.get("owner_id") != owner_id or existing.get("endpoint_id") != endpoint_id:
            return existing
        sessions = list(existing.get("active_sessions", []))
        if session_id not in sessions:
            sessions.append(session_id)
        return {
            **existing,
            "active_sessions": sessions[-20:],
            "last_seen": _now(),
        }

    record = _store().update_key(key, attach)
    if record is None or record.get("owner_id") != owner_id or record.get("endpoint_id") != endpoint_id:
        raise HTTPException(status_code=404, detail="Endpoint not found.")
    _emit_endpoint_event(
        event_type=RuntimeEventType.DEVICE_STATE_UPDATED,
        owner_id=owner_id,
        session_id=session_id,
        endpoint_id=endpoint_id,
        request_id=getattr(request.state, "request_id", None),
        connectivity=record.get("state"),
        details={"lifecycle": "session_attached"},
    )
    _audit_endpoint_action(
        action="session_attached",
        owner_id=owner_id,
        endpoint_id=endpoint_id,
        request_id=getattr(request.state, "request_id", None),
        session_id=session_id,
    )
    return {"endpoint": _public_endpoint(record)}


@router.delete("/{endpoint_id}")
async def disconnect_endpoint(
    endpoint_id: _IDENTIFIER,
    request: Request,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict[str, bool]:
    owner_id = _require_endpoint_manager(user)
    key, record = _find_owned_endpoint(owner_id, endpoint_id)

    def disconnect(existing: dict[str, Any]) -> dict[str, Any]:
        if existing.get("owner_id") != owner_id:
            return existing
        return {
            **existing,
            "state": "disconnected",
            "connectivity": "disconnected",
            "active_sessions": [],
            "last_seen": _now(),
        }

    updated = _store().update_key(key, disconnect)
    if updated is None or updated.get("owner_id") != owner_id:
        raise HTTPException(status_code=404, detail="Endpoint not found.")
    for session_id in record.get("active_sessions", []):
        _emit_endpoint_event(
            event_type=RuntimeEventType.DEVICE_STATE_UPDATED,
            owner_id=owner_id,
            session_id=session_id,
            endpoint_id=endpoint_id,
            request_id=getattr(request.state, "request_id", None),
            connectivity="disconnected",
        )
    _audit_endpoint_action(
        action="disconnected",
        owner_id=owner_id,
        endpoint_id=endpoint_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return {"disconnected": True}
