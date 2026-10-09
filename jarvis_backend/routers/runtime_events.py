"""Authenticated runtime snapshot and resumable SSE event stream."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..chat_service import chat_service
from ..core import get_current_user
from ..endpoint_gateway import _authenticate_endpoint
from ..runtime_events import RuntimeEvent, RuntimeHistoryExpiredError, runtime_event_service

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


def _authorized_owner(request: Request, session_id: str) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.startswith("jep_"):
        owner_id, _, _, endpoint = _authenticate_endpoint(request)
        if session_id not in endpoint.get("active_sessions", []):
            raise HTTPException(status_code=403, detail="Endpoint is not attached to this conversation.")
        return owner_id

    user = get_current_user(authorization or None, request)
    owner_id = str(user.get("id") or "")
    if not owner_id:
        raise HTTPException(status_code=403, detail="An authenticated owner identity is required.")
    chat_service.get_session(owner_id, session_id)
    return owner_id


@router.get("/snapshot/{session_id}")
async def runtime_snapshot(
    session_id: str,
    request: Request,
) -> dict:
    owner_id = _authorized_owner(request, session_id)
    return runtime_event_service.snapshot(owner_id, session_id)


@router.get("/resume/{session_id}")
async def runtime_resume(
    session_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict:
    owner_id = _authorized_owner(request, session_id)
    return runtime_event_service.resume(owner_id, session_id, after, limit)


@router.get("/events")
async def runtime_events(
    request: Request,
    session_id: str = Query(min_length=1, max_length=160),
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    owner_id = _authorized_owner(request, session_id)
    resume_after = after
    if last_event_id:
        try:
            resume_after = max(resume_after, int(last_event_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Last-Event-ID must be a sequence number.") from exc

    resume = runtime_event_service.resume(owner_id, session_id, resume_after, limit=1)
    if resume["resyncRequired"]:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "RUNTIME_HISTORY_EXPIRED",
                    "message": "Runtime history expired; fetch the current snapshot and resume.",
                    "oldest_available_sequence": resume["oldestAvailableSequence"],
                    "high_water_sequence": resume["highWaterSequence"],
                },
            },
        )

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in runtime_event_service.subscribe(
                owner_id,
                session_id,
                resume_after,
            ):
                if await request.is_disconnected():
                    break
                yield _sse_frame(event)
        except RuntimeHistoryExpiredError as exc:
            yield (
                "event: resync_required\n"
                f'data: {{"oldestAvailableSequence":{exc.oldest_available},'
                f'"highWaterSequence":{exc.high_water}}}\n\n'
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse_frame(event: RuntimeEvent) -> str:
    return (
        f"id: {event.sequence}\n"
        f"event: {event.type.value}\n"
        f"data: {event.sse_data()}\n\n"
    )
