"""Legacy chat, notes, reminders, and embedded browser endpoints."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core import get_current_user, get_store, now_iso
from ..chat_service import FAILED, chat_service
from ..errors import ErrorCategory

logger = logging.getLogger("jarvis_backend.legacy")

router = APIRouter(tags=["legacy"])

# --------------------------------------------------------------------------- #
# Chat (authenticated, per-user session ownership, full lifecycle)
# --------------------------------------------------------------------------- #
class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    stream: bool = False
    model: Optional[str] = None
    client_message_id: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    location_error: Optional[Literal[
        "permission_denied",
        "unsupported",
        "position_unavailable",
        "timeout",
    ]] = None


def _chat_result_to_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a ChatService result into the wire payload the UI understands."""
    payload = {
        "session_id": result.get("session_id"),
        "reply": result.get("message"),
        "message": result.get("message"),
        "model": result.get("model"),
        "provider": result.get("provider"),
        "usage": result.get("usage"),
        "latency_ms": result.get("latency_ms"),
        "sources": result.get("sources"),
        "status": result.get("status", "COMPLETED"),
        "metadata": result.get("metadata") or {},
        "execution_status": result.get("execution_status"),
        "tool_calls": result.get("tool_calls") or [],
        "runtime_events": result.get("runtime_events") or [],
        "error": result.get("error"),
        "resumed": result.get("resumed", False),
        "message_id": result.get("message_id"),
        "request_id": result.get("request_id"),
        "timestamp": now_iso(),
        "presentation": result.get("presentation"),
        "presentation_events": result.get("presentation_events") or [],
    }
    return payload


@router.post("/api/chat")
async def legacy_chat(
    body: ChatIn,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = user["id"]
    session_id = body.session_id or str(uuid.uuid4())
    chat_service.create_session(user_id, session_id, body.message)
    result = await chat_service.send_message(
        user_id, session_id, body.message,
        model=body.model,
        client_message_id=body.client_message_id,
        request_id=getattr(request.state, "request_id", None),
        principal=user,
        location=body.location,
        location_error=body.location_error,
    )
    return _chat_result_to_payload(result)


@router.post("/api/chat/stream")
async def legacy_chat_stream(
    body: ChatIn,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = user["id"]
    session_id = body.session_id or str(uuid.uuid4())
    request_id = getattr(request.state, "request_id", None)
    chat_service.create_session(user_id, session_id, body.message)

    async def gen():
        try:
            async for event in chat_service.stream_message(
                user_id, session_id, body.message,
                model=body.model,
                client_message_id=body.client_message_id,
                request_id=request_id,
                principal=user,
                location=body.location,
                location_error=body.location_error,
            ):
                yield "data: " + json.dumps(event, default=str) + "\n\n"
        except Exception:
            # The generator died before emitting a terminal event. Tell the
            # client the stream was interrupted so it can offer recovery
            # instead of waiting forever on a half-open response.
            logger.exception("chat stream aborted for session %s", session_id)
            yield "data: " + json.dumps({
                "type": "error",
                "category": ErrorCategory.STREAM_INTERRUPTED.value,
                "message": (
                    "The response stream ended unexpectedly. "
                    "Your message was saved - you can retry."
                ),
                "retryable": True,
                "status": FAILED,
                "session_id": session_id,
                "request_id": request_id,
            }, default=str) + "\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/chat/sessions")
async def chat_sessions(
    limit: int = 100,
    offset: int = 0,
    q: Optional[str] = None,
    search_messages: bool = False,
    include_archived: bool = False,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List sessions with optional search.
    
    Query parameters:
    - q: search query (matches title)
    - search_messages: when true, also search message content
    - include_archived: when true, include archived conversations
    """
    return chat_service.list_sessions(
        user["id"],
        limit=limit,
        offset=offset,
        q=q,
        search_messages=search_messages,
    )


@router.post("/api/chat/sessions")
async def create_chat_session(user: Dict[str, Any] = Depends(get_current_user)):
    session = chat_service.create_session(user["id"])
    return chat_service.get_session(user["id"], session["id"])


@router.patch("/api/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, body: dict,
                              user: Dict[str, Any] = Depends(get_current_user)):
    if "title" in body:
        return chat_service.rename_session(user["id"], session_id, str(body["title"]))
    if "archived" in body:
        return chat_service.set_archived(user["id"], session_id, bool(body["archived"]))
    raise HTTPException(status_code=400, detail="Unsupported field")


@router.put("/api/chat/sessions/{session_id}/restore")
async def restore_chat_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Explicit restore endpoint for an archived conversation.
    
    This is equivalent to PATCH /api/chat/sessions/{id} with archived=false,
    but provides a more discoverable API for the UI.
    """
    return chat_service.set_archived(user["id"], session_id, False)


@router.get("/api/chat/sessions/{session_id}/export")
async def export_chat_session(session_id: str, format: str = "json",
                              user: Dict[str, Any] = Depends(get_current_user)):
    return chat_service.export_session(user["id"], session_id, fmt=format)


@router.get("/api/chat/history/{session_id}")
async def chat_history(session_id: str, limit: int = 200, offset: int = 0,
                       user: Dict[str, Any] = Depends(get_current_user)):
    return chat_service.load_history(user["id"], session_id, limit=limit, offset=offset)


@router.delete("/api/chat/history/{session_id}")
async def delete_chat_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    chat_service.delete_session(user["id"], session_id)
    return {"success": True}


@router.post("/api/chat/messages/{session_id}/{message_id}/regenerate")
async def regenerate_chat_message(session_id: str, message_id: str, body: dict,
                                  user: Dict[str, Any] = Depends(get_current_user)):
    pre = chat_service.regenerate(
        user["id"], session_id, message_id,
        model=body.get("model"),
    )
    result = await chat_service.send_message(
        user["id"], session_id, pre["message"],
        model=body.get("model"),
        client_message_id=pre.get("client_message_id"),
    )
    return _chat_result_to_payload(result)


# -- message edit/resend (Phase 5) ------------------------------------------ #
class MessageEditIn(BaseModel):
    content: str
    model: Optional[str] = None
    client_message_id: Optional[str] = None


class MessageResendIn(BaseModel):
    new_content: Optional[str] = None
    model: Optional[str] = None
    client_message_id: Optional[str] = None


@router.patch("/api/chat/messages/{session_id}/{message_id}")
async def edit_chat_message(session_id: str, message_id: str, body: MessageEditIn,
                            user: Dict[str, Any] = Depends(get_current_user)):
    """Edit a user message and return state for regeneration.
    
    The edited message content is updated and any following assistant
    response is superseded. Use regenerate endpoint to send the new
    prompt and receive a fresh response.
    """
    pre = chat_service.edit_message(
        user["id"], session_id, message_id, body.content,
        model=body.model,
    )
    return {
        "session_id": pre["session_id"],
        "message_id": pre["message_id"],
        "content": pre["content"],
        "client_message_id": pre.get("client_message_id"),
        "ready_for_regeneration": True,
    }


@router.post("/api/chat/messages/{session_id}/{message_id}/resend")
async def resend_chat_message(session_id: str, message_id: str, body: MessageResendIn,
                              user: Dict[str, Any] = Depends(get_current_user)):
    """Edit a user message and send a fresh assistant response.
    
    This is the atomic edit + resend operation:
    1. Edits the user message content
    2. Truncates any superseded assistant response
    3. Generates a new assistant response
    4. Records usage/audit for the new inference
    
    Idempotent: if client_message_id is provided and already processed,
    returns the cached response.
    """
    result = await chat_service.edit_and_resend(
        user["id"], session_id, message_id, body.new_content or body.content,
        model=body.model,
        client_message_id=body.client_message_id,
    )
    # Shape the response for the frontend
    return {
        "session_id": session_id,
        "message": result.get("message"),
        "model": result.get("model"),
        "provider": result.get("provider"),
        "usage": result.get("usage"),
        "latency_ms": result.get("latency_ms"),
        "sources": result.get("sources"),
        "status": result.get("status", "COMPLETED"),
        "error": result.get("error"),
        "resumed": result.get("resumed", False),
        "message_id": result.get("message_id"),
        "timestamp": now_iso(),
    }


@router.post("/api/chat/messages/{session_id}/{message_id}/feedback")
async def chat_message_feedback(session_id: str, message_id: str, body: dict,
                                user: Dict[str, Any] = Depends(get_current_user)):
    return chat_service.record_feedback(
        user["id"], session_id, message_id,
        int(body.get("rating", 0)),
        comment=body.get("comment"),
    )


class SwitchIn(BaseModel):
    model: str


@router.post("/api/chat/switch")
async def chat_switch(body: SwitchIn):
    misc = get_store("misc").load()
    misc["active_model"] = body.model
    get_store("misc").save()
    return {"model": body.model, "active_model": body.model, "active": True}


# --------------------------------------------------------------------------- #
# Notes (authenticated, per-user ownership)
# --------------------------------------------------------------------------- #
class NoteIn(BaseModel):
    title: str
    content: str
    tags: List[str] = []


@router.get("/api/notes")
async def list_notes(user: Dict[str, Any] = Depends(get_current_user)):
    notes = get_store("notes").load()
    mine = [n for n in notes.values() if n.get("user_id") == user["id"]]
    mine.sort(key=lambda n: n.get("updated_at") or n.get("created_at") or "", reverse=True)
    return {"notes": mine}


@router.post("/api/notes")
async def create_note(body: NoteIn, user: Dict[str, Any] = Depends(get_current_user)):
    notes = get_store("notes").load()
    nid = str(uuid.uuid4())
    notes[nid] = {
        "id": nid, "user_id": user["id"], "title": body.title, "content": body.content,
        "tags": body.tags, "created_at": now_iso(), "updated_at": now_iso(),
    }
    get_store("notes").save()
    return notes[nid]


@router.patch("/api/notes/{note_id}")
async def update_note(note_id: str, body: NoteIn, user: Dict[str, Any] = Depends(get_current_user)):
    notes = get_store("notes").load()
    note = notes.get(note_id)
    if not note or note.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Note not found")
    note.update({
        "title": body.title, "content": body.content, "tags": body.tags,
        "updated_at": now_iso(),
    })
    get_store("notes").save()
    return note


@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    notes = get_store("notes").load()
    note = notes.get(note_id)
    if not note or note.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Note not found")
    notes.pop(note_id, None)
    get_store("notes").save()
    return {"success": True}


# --------------------------------------------------------------------------- #
# Reminders (authenticated, per-user ownership)
# --------------------------------------------------------------------------- #
class ReminderIn(BaseModel):
    title: str
    due_date: Optional[str] = None
    tags: List[str] = []


@router.get("/api/reminders")
async def list_reminders(user: Dict[str, Any] = Depends(get_current_user)):
    rems = get_store("reminders").load()
    mine = [r for r in rems.values() if r.get("user_id") == user["id"]]
    mine.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"reminders": mine}


@router.post("/api/reminders")
async def create_reminder(body: ReminderIn, user: Dict[str, Any] = Depends(get_current_user)):
    rems = get_store("reminders").load()
    rid = str(uuid.uuid4())
    rems[rid] = {
        "id": rid, "user_id": user["id"], "title": body.title, "due_date": body.due_date,
        "tags": body.tags, "completed": False, "created_at": now_iso(),
    }
    get_store("reminders").save()
    return rems[rid]


@router.patch("/api/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, body: dict, user: Dict[str, Any] = Depends(get_current_user)):
    rems = get_store("reminders").load()
    rem = rems.get(reminder_id)
    if not rem or rem.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Reminder not found")
    for k, v in body.items():
        rem[k] = v
    get_store("reminders").save()
    return rem


@router.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    rems = get_store("reminders").load()
    rem = rems.get(reminder_id)
    if not rem or rem.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Reminder not found")
    rems.pop(reminder_id, None)
    get_store("reminders").save()
    return {"success": True}


@router.post("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    rems = get_store("reminders").load()
    rem = rems.get(reminder_id)
    if not rem or rem.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Reminder not found")
    rem["completed"] = True
    get_store("reminders").save()
    return rem


# --------------------------------------------------------------------------- #
# Deprecated embedded-browser endpoints. The former in-memory implementation
# did not browse or execute scripts; keep the routes explicit and truthful.
# --------------------------------------------------------------------------- #
class BrowserCreateIn(BaseModel):
    window_id: Optional[str] = None


class BrowserActionIn(BaseModel):
    window_id: str
    url: Optional[str] = None
    html: Optional[str] = None
    base_url: Optional[str] = None
    script: Optional[str] = None


def _embedded_browser_not_configured() -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "CAPABILITY_NOT_CONFIGURED",
            "message": "The legacy embedded browser is not implemented. Use the authenticated browser capability.",
        },
    )


@router.post("/api/browser/system/initialize")
async def browser_init(user: Dict[str, Any] = Depends(get_current_user)):
    _embedded_browser_not_configured()


@router.get("/api/browser/system/status")
async def browser_status(user: Dict[str, Any] = Depends(get_current_user)):
    _embedded_browser_not_configured()


@router.post("/api/browser/create")
async def browser_create(
    body: BrowserCreateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.post("/api/browser/navigate")
async def browser_navigate(
    body: BrowserActionIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.post("/api/browser/load-content")
async def browser_load_content(
    body: BrowserActionIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.post("/api/browser/execute-script")
async def browser_execute_script(
    body: BrowserActionIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.post("/api/browser/{window_id}/show")
async def browser_show(
    window_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.post("/api/browser/{window_id}/hide")
async def browser_hide(
    window_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()


@router.delete("/api/browser/{window_id}")
async def browser_destroy(
    window_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _embedded_browser_not_configured()
