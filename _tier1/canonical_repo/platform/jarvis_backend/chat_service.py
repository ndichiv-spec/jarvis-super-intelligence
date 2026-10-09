"""JARVIS chat service.

Owns chat session/message lifecycle, idempotency, retry policy, and the
provider boundary.  It deliberately NEVER fabricates a successful assistant
reply: if a provider is unavailable, the assistant message is marked FAILED
with a normalized error category instead of a canned "success".

Design notes
------------
* Message lifecycle: QUEUED -> STREAMING -> COMPLETED | FAILED | CANCELLED.
* Idempotency: a client-supplied ``client_message_id`` makes re-sends safe.
  Re-sending the same id returns the already-produced reply instead of
  duplicating the user message or producing a second assistant turn.
* Retries: transient categories (RATE_LIMITED, PROVIDER_UNAVAILABLE,
  STREAM_INTERRUPTED, INTERNAL_ERROR, UNKNOWN_ERROR) are retried by the caller
  with bounded exponential backoff; fatal categories are not retried.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from infrastructure.audit_events import AuditEvent, AuditEventService
from infrastructure.usage_accounting import get_usage_accountant

from .core import _SYSTEM_PROMPT, ai_service, get_store, now_iso
from .errors import (
    ChatError,
    ErrorCategory,
    normalize_exception,
)
from .gateway import ProviderGateway, provider_gateway

logger = logging.getLogger("jarvis_backend.chat")

# Global caches for infrastructure services (initialized lazily)
_usage_accountant = None
_audit_service = None


def _usage_tokens(usage: dict[str, Any], *keys: str) -> int:
    """Read a token count from a provider usage payload.

    Provider adapters are not consistent about token field names: the
    OpenAI-compatible adapters report ``prompt_tokens``/``completion_tokens``
    while some legacy paths use ``input_tokens``/``output_tokens``. Usage
    accounting must never silently record zero for a request that consumed
    tokens, so the first key actually present wins.
    """
    for key in keys:
        value = usage.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _get_usage_accountant():
    """Get the global usage accountant instance (lazy initialization)."""
    global _usage_accountant
    if _usage_accountant is None:
        _usage_accountant = get_usage_accountant()
    return _usage_accountant


def _get_audit_service():
    """Get the global audit event service (lazy initialization)."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditEventService()
    return _audit_service


# --------------------------------------------------------------------------- #
# Lifecycle + error card helpers
# --------------------------------------------------------------------------- #
QUEUED = "QUEUED"
THINKING = "THINKING"
STREAMING = "STREAMING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

_STOP_WORDS = {"the", "a", "an", "is", "are", "of", "for", "to", "and", "on", "in"}


def _new_message(msg_id: str, role: str, content: str, *, status: str = COMPLETED,
                 model: str | None = None, client_message_id: str | None = None,
                 error: dict[str, Any] | None = None,
                 latency_ms: int | None = None) -> dict[str, Any]:
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "status": status,
        "timestamp": now_iso(),
        "client_message_id": client_message_id,
        "model": model,
        "latency_ms": latency_ms,
        "error": error,
    }


def _error_card(exc: Exception) -> dict[str, Any]:
    """Build the error metadata stored on a FAILED assistant message."""
    if isinstance(exc, ChatError):
        category = exc.category.value
        message = exc.safe_message
        retryable = exc.retryable
        request_id = exc.request_id
    else:
        err = normalize_exception(exc)
        category = err.category.value
        message = err.safe_message
        retryable = err.retryable
        request_id = err.request_id
    return {
        "category": category,
        "message": message,
        "request_id": request_id,
        "retryable": retryable,
    }


# --------------------------------------------------------------------------- #
# Session store helpers (same JSON store used by the legacy chat routes)
# --------------------------------------------------------------------------- #
def _sessions() -> dict[str, Any]:
    return get_store("chat_sessions").load()


def _require_session(sessions: dict[str, Any], session_id: str, user_id: str) -> dict[str, Any]:
    session = sessions.get(session_id)
    if not session:
        raise ChatError(
            ErrorCategory.INVALID_REQUEST, "Session not found.",
            status_code=404,
        )
    if session.get("user_id") and session.get("user_id") != user_id:
        # Authenticated but not the owner: an explicit authorization failure
        # (403) rather than exposing another user's session content.  The
        # session payload itself is never returned.
        raise ChatError(
            ErrorCategory.AUTHORIZATION_ERROR,
            "You are not authorized to access this session.",
            status_code=403,
        )
    return session


# --------------------------------------------------------------------------- #
# ChatService
# --------------------------------------------------------------------------- #
class ChatService:
    """Conversation orchestration between the HTTP layer and the provider."""

    def __init__(self, gateway: ProviderGateway | None = None) -> None:
        self.max_retries = int(getattr(ai_service, "max_retries", 0))
        # Inject the provider gateway (the Silverwing boundary). Defaults to
        # the real gateway; tests may inject a fake to drive chat logic without
        # a live provider.
        self.gateway = gateway or provider_gateway

    @staticmethod
    def _persist_presentation_revision(
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        assistant_message: dict[str, Any],
        presentation: dict[str, Any],
    ) -> None:
        from .runtime import runtime

        command_id = assistant_message.get("runtime_command_id")
        task_id = command_id or assistant_message["id"]
        previous = runtime.list_presentation_revisions(
            task_id, owner_id=user_id,
        )
        if (
            previous
            and previous[-1].get("presentation", {}).get("presentation_id")
            == presentation.get("presentation_id")
        ):
            assistant_message["canonical_task_id"] = task_id
            assistant_message["presentation_revision_id"] = previous[-1]["revision_id"]
            return
        revision = runtime.create_presentation_revision(
            task_id=task_id,
            owner_id=user_id,
            request_id=request_id,
            conversation_id=session_id,
            command_id=command_id,
            presentation=presentation,
            expected_revision=previous[-1]["revision"] if previous else 0,
            idempotency_key=f"chat-presentation:{assistant_message['id']}",
            compatibility={"decision": "canonical_contract"},
        )
        assistant_message["canonical_task_id"] = task_id
        assistant_message["presentation_revision_id"] = revision["revision_id"]

    # -- session CRUD ------------------------------------------------------- #
    def create_session(self, user_id: str, session_id: str | None = None,
                       title: str = "New conversation") -> dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        sessions = _sessions()
        if sid not in sessions:
            sessions[sid] = {
                "id": sid,
                "user_id": user_id,
                "title": (title or "New conversation")[:80],
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "archived": False,
                "metadata": {},
                "messages": [],
            }
        get_store("chat_sessions").save()
        return sessions[sid]

    def list_sessions(self, user_id: str, *, limit: int = 100, offset: int = 0,
                      q: str | None = None, search_messages: bool = False) -> dict[str, Any]:
        """Paginated, optionally search-filtered session list for a user.
        
        When search_messages=True, q also matches against message content
        (not just session titles). This enables full-text conversation search
        while respecting user ownership boundaries.
        """
        sessions = _sessions()
        mine = [
            s for s in sessions.values()
            if s.get("user_id") == user_id and not s.get("archived", False)
        ]
        mine.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "", reverse=True)

        q = (q or "").strip().lower()
        if q:
            if search_messages:
                # Full-text search: match title OR any message content
                mine = [
                    s for s in mine
                    if q in (s.get("title") or "").lower() or 
                       any(
                           q in (m.get("content") or "").lower()
                           for m in s.get("messages") or []
                       )
                ]
            else:
                # Title-only search (legacy behavior)
                mine = [s for s in mine if q in (s.get("title") or "").lower()]

        total = len(mine)
        page = mine[offset:offset + limit]
        return {
            "sessions": [self._summary(s) for s in page],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
        }

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        sessions = _sessions()
        session = _require_session(sessions, session_id, user_id)
        return session

    def rename_session(self, user_id: str, session_id: str, title: str) -> dict[str, Any]:
        sessions = _sessions()
        session = _require_session(sessions, session_id, user_id)
        session["title"] = (title or "New conversation")[:80]
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()
        return self._summary(session)

    def set_archived(self, user_id: str, session_id: str, archived: bool) -> dict[str, Any]:
        sessions = _sessions()
        session = _require_session(sessions, session_id, user_id)
        session["archived"] = bool(archived)
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()
        return self._summary(session)

    def delete_session(self, user_id: str, session_id: str) -> None:
        sessions = _sessions()
        _require_session(sessions, session_id, user_id)
        sessions.pop(session_id, None)
        get_store("chat_sessions").save()

    def export_session(self, user_id: str, session_id: str, fmt: str = "json") -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        messages = session.get("messages") or []
        if fmt == "markdown":
            lines = [f"# {session.get('title', 'Conversation')}", ""]
            for m in messages:
                prefix = "**You:**" if m.get("role") == "user" else "**JARVIS:**"
                lines.append(f"{prefix}\n\n{m.get('content', '')}\n")
            return {"format": "markdown", "session_id": session_id, "content": "\n\n".join(lines)}
        return {
            "format": "json",
            "session_id": session_id,
            "title": session.get("title"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "messages": messages,
        }

    # -- message handling --------------------------------------------------- #
    def _find_by_client_id(self, messages: list[dict[str, Any]], client_message_id: str) -> dict[str, Any]:
        for m in messages:
            if m.get("client_message_id") == client_message_id:
                return m
        return {}

    def _find_assistant_after(self, messages: list[dict[str, Any]], user_msg_id: str) -> dict[str, Any]:
        """Find the assistant reply that follows the user message with `user_msg_id`."""
        found_user = False
        for m in messages:
            if m.get("id") == user_msg_id:
                found_user = True
                continue
            if found_user and m.get("role") == "assistant":
                return m
        return {}

    def resume_from_client_id(self, user_id: str, session_id: str, client_message_id: str) -> dict[str, Any]:
        """Idempotent resume: return the existing reply for a re-sent client id, or {}."""
        session = self.get_session(user_id, session_id)
        user_msg = self._find_by_client_id(session.get("messages") or [], client_message_id)
        if not user_msg:
            return {}
        reply = self._find_assistant_after(session.get("messages") or [], user_msg.get("id", ""))
        if not reply:
            return {}
        return {
            "session_id": session_id,
            "message": reply.get("content"),
            "model": reply.get("model"),
            "revision": reply.get("revision"),
            "backend": reply.get("backend"),
            "device": reply.get("device"),
            "latency_ms": reply.get("latency_ms"),
            "sources": reply.get("sources"),
            "tool_calls": reply.get("tool_calls"),
            "presentation": reply.get("presentation"),
            "canonical_task_id": reply.get("canonical_task_id"),
            "presentation_revision_id": reply.get("presentation_revision_id"),
            "runtime_command_id": reply.get("runtime_command_id"),
            "status": reply.get("status"),
            "error": reply.get("error"),
            "resumed": True,
            "message_id": reply.get("id"),
        }

    def load_history(self, user_id: str, session_id: str, *, limit: int = 200,
                     offset: int = 0) -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        messages = session.get("messages") or []
        return {
            "session": self._summary(session),
            "messages": messages[offset:offset + limit],
            "total": len(messages),
            "offset": offset,
            "limit": limit,
        }

    def _summary(self, session: dict[str, Any]) -> dict[str, Any]:
        messages = session.get("messages") or []
        last = messages[-1] if messages else None
        pending = [m for m in messages if m.get("status") in (QUEUED, STREAMING)]
        return {
            "id": session.get("id"),
            "title": session.get("title", "New conversation"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "archived": session.get("archived", False),
            "message_count": len(messages),
            "pending_count": len(pending),
            "last_message": last.get("content") if last else None,
            "last_role": last.get("role") if last else None,
            "last_status": last.get("status") if last else None,
        }

    @staticmethod
    def _derive_title(current: str | None, content: str) -> str:
        """Generate a title from message content if needed."""
        if current and current not in ("New conversation",):
            return current
        words = [w for w in re.findall(r"\w+", content.lower()) if w not in _STOP_WORDS]
        return " ".join(words[:6]).capitalize() or "New conversation"

    # -- memory / knowledge context for the system prompt ---------------------- #
    def _recall_context(self, user_id: str, content: str, limit: int = 8) -> str:
        """Recruit the user's memories + globally-indexed knowledge relevant to
        the current ``content`` to ground the system prompt.

        Only the *user's own* memories (and memories with no owner) are
        considered, so one user can never leak another user's context to the
        provider.  Relevance is a cheap term-overlap + importance score,
        bounded to ``limit`` memories plus matching knowledge items.
        """
        query = (content or "").lower()
        terms = [t for t in re.split(r"\W+", query) if t and t not in _STOP_WORDS]
        terms = terms or ([query] if query else [])

        memories = get_store("memory").load()
        scored: list[tuple[float, str]] = []
        for m in memories.values():
            owner = m.get("user_id")
            if owner and owner != user_id:
                continue  # ownership-safe: skip another user's memories
            mcontent = (m.get("content") or "").lower()
            if not mcontent:
                continue
            hits = sum(1 for t in terms if t in mcontent)
            if not hits:
                continue
            importance = float(m.get("importance", 0.5))
            score = (0.5 + 0.5 * (hits / len(terms))) * importance
            scored.append((score, mcontent))
        scored.sort(reverse=True)
        top = scored[:limit]

        knowledge = get_store("knowledge").load()
        kmatches: list[str] = []
        for item in knowledge.values():
            key = (item.get("key") or "").lower()
            val = (item.get("value") or "").lower()
            if not key and not val:
                continue
            if any(t in key or t in val for t in terms):
                kmatches.append(f"- {item.get('key')}: {item.get('value')}")

        parts: list[str] = []
        if top:
            parts.append("## Relevant memories")
            parts.extend(f"- {c}" for _, c in top)
        if kmatches:
            parts.append("## Relevant knowledge")
            parts.extend(kmatches)
        return "\n".join(parts) if parts else ""

    def _system_with_context(self, user_id: str, content: str) -> str:
        """Base system prompt + recalled memory/knowledge context, if any."""
        block = self._recall_context(user_id, content)
        return (_SYSTEM_PROMPT + "\n\n" + block) if block else _SYSTEM_PROMPT

    async def _project_context(self, prompt: str, user_id: str,
                               request_id: str,
                               activity: Optional[list[dict[str, Any]]] = None
                               ) -> str:
        """Project-intelligence evidence block, or '' for ordinary chat.

        Runs the read-only project tools through the existing ToolRegistry and
        returns a bounded, secret-scrubbed evidence block for the model.  This is
        the only hook into the chat path; it is skipped entirely unless the
        request is genuinely about the JARVIS implementation.
        """
        from .project_intel import (
            build_evidence_pack,
            detect_project_intent,
            render_evidence_block,
            select_capabilities,
        )

        # Either a project-scoped question OR a request that maps to a concrete
        # capability. Ordinary chat matches neither and never runs a tool.
        focus = detect_project_intent(prompt)
        routed = select_capabilities(prompt)
        if focus is None and not routed:
            return ""
        if focus is None:
            focus = "capability"
        try:
            pack = await build_evidence_pack(
                prompt, focus, user_id=user_id, request_id=request_id,
                activity=activity,
            )
        except Exception as exc:  # noqa: BLE001
            # Truthful degradation: never fail the chat because inspection did.
            logger.warning("project intelligence unavailable: %s", exc)
            return (
                "\n\n[Project intelligence unavailable: "
                f"{type(exc).__name__}. No project evidence is available, so do "
                "not make claims about the JARVIS implementation.]"
            )
        block = render_evidence_block(pack)
        self._record_project_audit(pack, user_id, request_id)
        return block

    async def _prepare_system(self, user_id: str, prompt: str, request_id: str,
                              activity: Optional[list[dict[str, Any]]] = None
                              ) -> str:
        """System prompt + memory context + (when relevant) project evidence.

        Shared by the buffered path (``_generate``) and the live SSE streaming
        path (``stream_message``) so both ground answers identically.
        """
        system_prompt = self._system_with_context(user_id, prompt)
        project_block = await self._project_context(
            prompt, user_id, request_id, activity=activity,
        )
        if project_block:
            system_prompt = f"{system_prompt}\n\n{project_block}"
        return system_prompt

    def _record_project_audit(self, pack: dict[str, Any], user_id: str,
                              request_id: str) -> None:
        """Record project-tool activity through the existing audit system."""
        try:
            from infrastructure.audit_events import get_audit_service
        except Exception:  # noqa: BLE001
            return
        audit = get_audit_service()
        inventory = pack.get("capability_inventory") or {}
        for tool in pack.get("tools_used") or []:
            risk = (inventory.get(tool) or {}).get("risk")
            state = (inventory.get(tool) or {}).get("state")
            try:
                audit.record(
                    event_type="capability_execution",
                    category="capability",
                    action=f"capability:{tool}",
                    result="success",
                    user_id=user_id,
                    request_id=request_id,
                    resource_type="capability",
                    resource_id=tool,
                    duration_ms=pack.get("duration_ms"),
                    metadata={
                        "capability": tool,
                        "risk_level": risk,
                        "availability": state,
                        "focus": pack.get("focus"),
                        "scope": "workspace",
                        "warnings": pack.get("warnings") or [],
                    },
                )
            except Exception:  # noqa: BLE001
                logger.debug("capability audit record failed for %s", tool,
                             exc_info=True)

    async def _world_resolution_reply(
        self,
        prompt: str,
        user_id: str,
        session_id: str,
        request_id: str,
        principal: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        from .world_resolver import (
            has_prior_world_results,
            is_result_selection_request,
            render_world_results,
            resolve_result_followup,
            resolve_world_intent,
        )

        intent = resolve_world_intent(prompt)
        if intent is None and not is_result_selection_request(prompt):
            return None

        session = self.get_session(user_id, session_id)
        messages = session.get("messages") or []
        if intent is None and has_prior_world_results(messages):
            selected = resolve_result_followup(prompt, messages)
            if selected is not None:
                title, url = selected
                return {
                    "message": (
                        f"Here is the selected result: [{title}]({url}). "
                        "This link hands off to the external site; JARVIS has "
                        "not navigated or performed an authenticated action there."
                    ),
                    "sources": [url],
                    "tool_calls": [],
                    "provider": "world_resolver",
                    "presentation": None,
                }
            return {
                "message": (
                    "I couldn't select that result from the most recent completed "
                    "discovery in this conversation. Ask me to search again to "
                    "refresh the links."
                ),
                "sources": [],
                "tool_calls": [],
                "provider": "world_resolver",
                "presentation": None,
            }

        if intent is None:
            return None

        from .routers.commands import CommandCreate, _commands, _create_command

        caller = principal or get_store("users").load().get(user_id)
        if not isinstance(caller, dict) or str(caller.get("id") or "") != str(user_id):
            raise ChatError(
                ErrorCategory.INVALID_REQUEST,
                "The authenticated identity could not be verified for execution.",
            )

        started = time.monotonic()
        command = await _create_command(
            CommandCreate(
                goal=prompt,
                conversation_id=session_id,
                request_id=request_id,
                autonomy="SUPERVISED",
            ),
            caller,
        )
        command_id = str(command["command_id"])
        deadline = time.monotonic() + 105
        current: dict[str, Any] | None = None
        terminal_states = {
            "COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "RECOVERY_REQUIRED",
        }
        while time.monotonic() < deadline:
            current = _commands().get(command_id)
            if current and current.get("status") in terminal_states:
                break
            await asyncio.sleep(0.05)

        if not current or current.get("status") not in terminal_states:
            capability_name = (
                (current or {}).get("selected_capability_id") or intent.operation
            )
            return {
                "message": (
                    "The requested operation has not completed yet. No result "
                    "is being claimed. Its durable runtime command is "
                    f"{command_id}."
                ),
                "sources": [],
                "tool_calls": [{
                    "name": capability_name,
                    "operation": intent.operation,
                    "arguments": {},
                    "status": "running",
                }],
                "provider": "world_resolver",
                "status": "RUNNING",
                "latency_ms": int((time.monotonic() - started) * 1000),
                "runtime_command_id": command_id,
            }

        command_result = current.get("result") or {}
        evidence = command_result.get("evidence") or []
        selected_capability = current.get("selected_capability_id")
        search_result = next(
            (item for item in evidence
             if isinstance(item, dict)
             and item.get("name") == selected_capability
             and item.get("success")),
            {},
        )
        artifacts = [
            item for item in (search_result.get("artifacts") or [])
            if isinstance(item, dict)
        ]
        if current.get("status") == "COMPLETED" and search_result.get("success"):
            message, sources = render_world_results(
                intent, artifacts, evidence=[search_result],
            )
            tool_status = "completed"
        elif current.get("resolution_status") != "selected":
            reason = current.get("resolution_reason") or (
                "No authorized execution surface is currently available."
            )
            message = (
                f"I couldn't perform {intent.operation}: {reason} "
                "I cannot provide sourced results."
            )
            sources = []
            tool_status = "failed"
        else:
            message = (
                f"I couldn't complete {intent.operation} because the selected "
                "execution surface was unavailable or returned an execution "
                "error. No result is claimed."
            )
            sources = []
            tool_status = "failed"

        presentation = (current.get("result") or {}).get("presentation")
        return {
            "message": message,
            "sources": sources,
            "presentation": presentation,
            "status": "COMPLETED" if tool_status == "completed" else "FAILED",
            "tool_calls": [{
                "name": current.get("selected_capability_id") or intent.operation,
                "operation": intent.operation,
                "arguments": {"query": intent.query},
                "status": tool_status,
                "selectable_results": intent.selectable_results,
            }],
            "provider": "world_resolver",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "runtime_command_id": command_id,
        }

    # -- provider call (the ONLY place a real provider answer is produced) -- #
    async def _generate(self, prompt: str, model: str | None, user_id: str,
                        session_id: str, request_id: str | None = None,
                        principal: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call the provider; raise ChatError on any failure.

        This method must never return a fabricated "success".  If the provider
        cannot produce a real answer, the caller will mark the message FAILED.

        Transient categories are retried with exponential backoff + jitter,
        up to ``ai_service.max_retries`` attempts.
        
        After successful inference, records usage accounting and audit events.
        """
        # Generate a request_id if not provided (for exactly-once recording)
        if request_id is None:
            request_id = str(uuid.uuid4())

        world_result = await self._world_resolution_reply(
            prompt, user_id, session_id, request_id, principal,
        )
        if world_result is not None:
            return world_result
        
        retries = self.max_retries
        attempt = 0

        # Project-intelligence hook: only runs for requests genuinely about the
        # JARVIS implementation. Ordinary chat never inspects the repository.
        system_prompt = await self._prepare_system(user_id, prompt, request_id)

        while True:
            started = time.monotonic()
            try:
                result = await self.gateway.chat(
                    self._history(user_id, session_id),
                    model=model,
                    system=system_prompt,
                    timeout=self.gateway.timeout,
                )
            except ChatError as exc:
                error = exc
                # Record audit event for failure (only on final attempt)
                if not error.retryable or attempt >= retries:
                    self._record_audit_failure(error, user_id, request_id, session_id, model, attempt)
            except TimeoutError as exc:
                error = ChatError(
                    ErrorCategory.TIMEOUT,
                    "The AI provider did not respond within the time limit. "
                    "Please try again.",
                )
                # Record audit event for failure (only on final attempt)
                if not error.retryable or attempt >= retries:
                    self._record_audit_failure(error, user_id, request_id, session_id, model, attempt)
            except Exception as exc:
                error = normalize_exception(exc)
                # Record audit event for failure (only on final attempt)
                if not error.retryable or attempt >= retries:
                    self._record_audit_failure(error, user_id, request_id, session_id, model, attempt)
            else:
                latency_ms = int((time.monotonic() - started) * 1000)
                text = (result.get("content") or "").strip()
                if not text:
                    error = ChatError(
                        ErrorCategory.PROVIDER_UNAVAILABLE,
                        "The AI provider is currently unavailable. Your request was not "
                        "sent to any model and no response was generated. Please try again.",
                    )
                    # Record audit event for failure (only on final attempt)
                    if not error.retryable or attempt >= retries:
                        self._record_audit_failure(error, user_id, request_id, session_id, model, attempt)
                elif self._looks_fabricated(text):
                    error = ChatError(
                        ErrorCategory.PROVIDER_UNAVAILABLE,
                        "The AI provider could not generate a real response. Your request "
                        "was not answered by a model. Please try again.",
                    )
                    # Record audit event for failure (only on final attempt)
                    if not error.retryable or attempt >= retries:
                        self._record_audit_failure(error, user_id, request_id, session_id, model, attempt)
                else:
                    # Success path - record usage and audit events
                    provider = result.get("provider")
                    usage = result.get("usage") or {}
                    # Provider adapters report OpenAI-style token names
                    # (prompt_tokens/completion_tokens). Older adapters used
                    # input_tokens/output_tokens. Accept both rather than
                    # silently recording zero usage for every request.
                    input_tokens = _usage_tokens(usage, "prompt_tokens", "input_tokens")
                    output_tokens = _usage_tokens(usage, "completion_tokens", "output_tokens")
                    total_cost = usage.get("total_cost_usd", 0.0) or 0.0

                    # Record usage accounting (only once)
                    self._record_usage(provider, model, user_id, request_id, 
                                       input_tokens, output_tokens, total_cost, latency_ms)
                    
                    # Record audit event for success (only once)
                    self._record_audit_success(user_id, request_id, session_id, 
                                                provider, model, latency_ms,
                                                input_tokens, output_tokens)
                    
                    return {
                        "message": text,
                        "model": result.get("model") or model
                        or ai_service.ollama_model,
                        "provider": provider,
                        "revision": result.get("revision"),
                        "backend": result.get("backend"),
                        "device": result.get("device"),
                        "usage": usage,
                        "latency_ms": latency_ms,
                        "status": COMPLETED,
                        "request_id": request_id,
                    }

            # Retry only transient categories; fatal ones propagate immediately.
            if not error.retryable or attempt >= retries:
                raise error
            attempt += 1
            delay = (2 ** attempt) * 0.25 + (0.25 * (time.monotonic() % 1))
            await asyncio.sleep(delay)

    def _record_usage(self, provider: str | None, model: str | None, user_id: str,
                      request_id: str, input_tokens: int, output_tokens: int,
                      total_cost_usd: float, latency_ms: int) -> None:
        """Record inference usage to PostgreSQL if provider is available."""
        if provider is None or not provider.strip():
            return
        try:
            accountant = _get_usage_accountant()
            accountant.record_inference(
                provider_id=provider,
                model_id=model or "unknown",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                user_id=user_id if user_id else None,
                request_id=request_id,
                metadata={"latency_ms": latency_ms}
            )
        except Exception:
            # Never fail the request if accounting fails - but do not hide the
            # loss, otherwise usage silently under-reports real token spend.
            logger.exception("failed to record inference usage")

    def _record_audit_success(self, user_id: str, request_id: str, session_id: str,
                               provider: str | None, model: str | None, 
                               latency_ms: int,
                               input_tokens: int = 0,
                               output_tokens: int = 0) -> None:
        """Record successful inference audit event."""
        try:
            audit = _get_audit_service()
            audit.record(
                event_type="inference_complete",
                category="inference",
                severity="info",
                action="chat",
                result="success",
                user_id=user_id,
                request_id=request_id,
                session_id=session_id,
                resource_type="inference",
                resource_id=request_id,
                message="Successful inference completed",
                duration_ms=float(latency_ms),
                metadata={
                    "provider": provider or "unknown",
                    "model": model or "unknown",
                    "input_tokens": int(input_tokens or 0),
                    "output_tokens": int(output_tokens or 0),
                }
            )
        except Exception:
            # Never fail the request if audit fails - but do not hide the loss.
            logger.exception("failed to record inference_complete audit event")

    def _record_audit_failure(self, error: ChatError, user_id: str, request_id: str,
                               session_id: str, model: str | None, attempt: int) -> None:
        """Record inference failure audit event."""
        try:
            audit = _get_audit_service()
            audit.record(
                event_type="inference_failed",
                category="inference",
                severity="warning" if error.retryable else "error",
                action="chat",
                result="failure",
                user_id=user_id,
                request_id=request_id,
                session_id=session_id,
                resource_type="inference",
                resource_id=request_id,
                message=error.safe_message,
                metadata={
                    "model": model or "unknown",
                    "category": error.category.value,
                    "attempt": attempt + 1,
                }
            )
        except Exception:
            # Never fail the request if audit fails - but do not hide the loss.
            logger.exception("failed to record inference_failed audit event")

    @staticmethod
    def _looks_fabricated(text: str) -> bool:
        """Detect the old rule-based fallback strings so they never masquerade."""
        lowered = (text or "").strip().lower()
        markers = [
            "hello! i'm jarvis. how can i help you today?",
            "the backend is online and all integrations are active",
            "i am jarvis, an integrated super-intelligence backend",
            "set jarvis_ai_enabled=1",
            "i can chat & answer questions, manage agents and tasks",
        ]
        return any(marker in lowered for marker in markers) or (
            lowered.startswith("understood. i've processed your request")
        )

    # -- provider conversation history -------------------------------------- #
    def _history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        """Build the OpenAI-format message list from the session history.

        Ownership is enforced by ``get_session`` (raises for non-owners) so a
        user can never feed another user's context to the provider.  The user
        turn already persisted by ``send_message``/``stream_message`` is
        included here as the final user message.
        """
        session = self.get_session(user_id, session_id)
        out: list[dict[str, Any]] = []
        for m in session.get("messages") or []:
            role = m.get("role")
            if role in ("user", "assistant"):
                out.append({"role": role, "content": m.get("content") or ""})
        return out

    # -- non-streaming send -------------------------------------------------- #
    async def send_message(self, user_id: str, session_id: str, content: str,
                           *, model: str | None = None,
                           client_message_id: str | None = None,
                           principal: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        messages: list[dict[str, Any]] = session.setdefault("messages", [])

        if client_message_id:
            existing = self._find_by_client_id(messages, client_message_id)
            if existing:
                reply = self._find_assistant_after(messages, existing.get("id", ""))
                if reply:
                    return {
                        "session_id": session_id,
                        "message": reply.get("content"),
                        "model": reply.get("model"),
                        "revision": reply.get("revision"),
                        "backend": reply.get("backend"),
                        "device": reply.get("device"),
                        "latency_ms": reply.get("latency_ms"),
                        "sources": reply.get("sources"),
                        "tool_calls": reply.get("tool_calls"),
                        "presentation": reply.get("presentation"),
                        "canonical_task_id": reply.get("canonical_task_id"),
                        "presentation_revision_id": reply.get("presentation_revision_id"),
                        "runtime_command_id": reply.get("runtime_command_id"),
                        "status": reply.get("status"),
                        "error": reply.get("error"),
                        "resumed": True,
                        "message_id": reply.get("id"),
                    }

        user_msg_id = str(uuid.uuid4())
        messages.append(_new_message(
            user_msg_id, "user", content,
            status=COMPLETED,
            client_message_id=client_message_id,
        ))
        session["title"] = self._derive_title(session.get("title"), content)
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()

        assistant_id = str(uuid.uuid4())
        assistant_msg = _new_message(
            assistant_id, "assistant", "", status=QUEUED, model=model,
            client_message_id=client_message_id,
        )
        request_id = client_message_id or str(uuid.uuid4())
        assistant_msg["request_id"] = request_id
        messages.append(assistant_msg)
        get_store("chat_sessions").save()

        try:
            result = await self._generate(
                content, model, user_id, session_id,
                request_id=request_id, principal=principal,
            )
            if result.get("presentation") is None and result.get("message"):
                from .presentation_contract import build_conversation_presentation

                result["presentation"] = build_conversation_presentation(
                    result["message"],
                    request_id=request_id,
                    session_id=session_id,
                    conversation_id=session_id,
                )
            assistant_msg.update({
                "content": result["message"],
                "status": result.get("status", COMPLETED),
                "model": result.get("model"),
                "revision": result.get("revision"),
                "backend": result.get("backend"),
                "device": result.get("device"),
                "usage": result.get("usage"),
                "provider": result.get("provider"),
                "latency_ms": result.get("latency_ms"),
                "sources": result.get("sources"),
                "tool_calls": result.get("tool_calls"),
                "runtime_command_id": result.get("runtime_command_id"),
                "presentation": result.get("presentation"),
            })
            if result.get("presentation"):
                self._persist_presentation_revision(
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    assistant_message=assistant_msg,
                    presentation=result["presentation"],
                )
        except ChatError as exc:
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(exc)
        except Exception as exc:
            err = normalize_exception(exc)
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(err)

        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()

        return {
            "session_id": session_id,
            "message": assistant_msg.get("content"),
            "model": assistant_msg.get("model"),
            "provider": assistant_msg.get("provider"),
            "revision": assistant_msg.get("revision"),
            "backend": assistant_msg.get("backend"),
            "device": assistant_msg.get("device"),
            "latency_ms": assistant_msg.get("latency_ms"),
            "usage": assistant_msg.get("usage"),
            "sources": assistant_msg.get("sources"),
            "tool_calls": assistant_msg.get("tool_calls"),
            "presentation": assistant_msg.get("presentation"),
            "canonical_task_id": assistant_msg.get("canonical_task_id"),
            "presentation_revision_id": assistant_msg.get("presentation_revision_id"),
            "runtime_command_id": assistant_msg.get("runtime_command_id"),
            "status": assistant_msg.get("status"),
            "error": assistant_msg.get("error"),
            "resumed": False,
            "message_id": assistant_id,
        }

    # -- streaming send ------------------------------------------------------ #
    async def stream_message(self, user_id: str, session_id: str, content: str,
                             *, model: str | None = None,
                             client_message_id: str | None = None,
                             principal: dict[str, Any] | None = None,
                             ) -> AsyncIterator[dict[str, Any]]:
        session = self.get_session(user_id, session_id)
        messages: list[dict[str, Any]] = session.setdefault("messages", [])

        if client_message_id:
            existing = self._find_by_client_id(messages, client_message_id)
            if existing:
                reply = self._find_assistant_after(messages, existing.get("id", ""))
                if reply:
                    yield {
                        "type": "complete",
                        "session_id": session_id,
                        "content": reply.get("content"),
                        "status": reply.get("status"),
                        "error": reply.get("error"),
                        "sources": reply.get("sources"),
                        "tool_calls": reply.get("tool_calls"),
                        "presentation": reply.get("presentation"),
                        "canonical_task_id": reply.get("canonical_task_id"),
                        "presentation_revision_id": reply.get("presentation_revision_id"),
                        "runtime_command_id": reply.get("runtime_command_id"),
                        "resumed": True,
                        "message_id": reply.get("id"),
                    }
                    return

        user_msg_id = str(uuid.uuid4())
        messages.append(_new_message(
            user_msg_id, "user", content,
            status=COMPLETED,
            client_message_id=client_message_id,
        ))
        session["title"] = self._derive_title(session.get("title"), content)
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()

        assistant_id = str(uuid.uuid4())
        assistant_msg = _new_message(
            assistant_id, "assistant", "", status=STREAMING, model=model,
            client_message_id=client_message_id,
        )
        messages.append(assistant_msg)
        get_store("chat_sessions").save()

        request_id_for_audit = client_message_id or str(uuid.uuid4())
        assistant_msg["request_id"] = request_id_for_audit
        get_store("chat_sessions").save()

        yield {
            "type": "meta",
            "session_id": session_id,
            "message_id": assistant_id,
            "request_id": request_id_for_audit,
        }

        try:
            from .world_resolver import (
                has_prior_media_results,
                is_result_selection_request,
                resolve_world_intent,
            )

            if resolve_world_intent(content) is not None or (
                is_result_selection_request(content)
                and has_prior_media_results(messages)
            ):
                world_result = await self._generate(
                    content, model, user_id, session_id,
                    request_id=request_id_for_audit, principal=principal,
                )
                full_text = world_result["message"]
                presentation = world_result.get("presentation")
                if presentation is None and full_text:
                    from .presentation_contract import build_conversation_presentation

                    presentation = build_conversation_presentation(
                        full_text,
                        request_id=request_id_for_audit,
                        session_id=session_id,
                        conversation_id=session_id,
                    )
                assistant_msg.update({
                    "content": full_text,
                    "status": world_result.get("status", COMPLETED),
                    "provider": world_result.get("provider"),
                    "latency_ms": world_result.get("latency_ms"),
                    "sources": world_result.get("sources"),
                    "tool_calls": world_result.get("tool_calls"),
                    "runtime_command_id": world_result.get("runtime_command_id"),
                    "presentation": presentation,
                })
                if presentation:
                    self._persist_presentation_revision(
                        user_id=user_id,
                        session_id=session_id,
                        request_id=request_id_for_audit,
                        assistant_message=assistant_msg,
                        presentation=presentation,
                    )
                session["updated_at"] = now_iso()
                get_store("chat_sessions").save()
                yield {
                    "type": "complete",
                    "session_id": session_id,
                    "content": full_text,
                    "status": world_result.get("status", COMPLETED),
                    "message_id": assistant_id,
                    "sources": world_result.get("sources"),
                    "tool_calls": world_result.get("tool_calls"),
                    "runtime_command_id": world_result.get("runtime_command_id"),
                    "presentation": presentation,
                    "canonical_task_id": assistant_msg.get("canonical_task_id"),
                    "presentation_revision_id": assistant_msg.get("presentation_revision_id"),
                    "request_id": request_id_for_audit,
                }
                return

            streamed = False
            reasoning_parts: list[str] = []
            content_parts: list[str] = []
            terminal: dict[str, Any] | None = None

            # Project-intelligence hook for the live SSE path.  Real tool
            # activity is emitted as it happens; ordinary chat emits nothing.
            project_activity: list[dict[str, Any]] = []
            streaming_system = await self._prepare_system(
                user_id, content, request_id_for_audit,
                activity=project_activity,
            )
            for step in project_activity:
                yield {
                    "type": "activity",
                    "stage": step.get("stage"),
                    "tool": step.get("tool"),
                    "status": step.get("status"),
                    "message_id": assistant_id,
                }

            # Honour an injected/overridden gateway (tests and app overrides)
            # exactly as the buffered path does.  A gateway that cannot stream
            # falls through to the buffered result, reported honestly with
            # streamed=False rather than fabricated deltas.
            gateway = self.gateway
            can_stream = hasattr(gateway, "stream_chat")

            try:
                if can_stream:
                    async for event in gateway.stream_chat(
                        content, model=model, user_id=user_id,
                        session_id=session_id, system=streaming_system,
                    ):
                        kind = event.get("type")
                        if kind == "reasoning":
                            reasoning_parts.append(event.get("text") or "")
                            assistant_msg["reasoning"] = "".join(reasoning_parts)
                            assistant_msg["status"] = THINKING
                            get_store("chat_sessions").save()
                            yield {
                                "type": "reasoning",
                                "text": event.get("text") or "",
                                "message_id": assistant_id,
                            }
                        elif kind == "delta":
                            streamed = True
                            content_parts.append(event.get("text") or "")
                            assistant_msg["content"] = "".join(content_parts)
                            assistant_msg["status"] = STREAMING
                            get_store("chat_sessions").save()
                            yield {
                                "type": "chunk",
                                "content": event.get("text") or "",
                                "text": event.get("text") or "",
                                "message_id": assistant_id,
                            }
                        elif kind == "done":
                            terminal = event
                            break
            except ChatError:
                raise
            except Exception as exc:
                # A mid-stream transport failure must not be reported as a
                # completed answer, and must not be replaced by a fallback.
                raise ChatError(
                    ErrorCategory.STREAM_INTERRUPTED,
                    "The response stream was interrupted before the model finished. "
                    "Part of the answer may be missing.",
                    detail=f"{exc.__class__.__name__}: {exc}",
                    retryable=True,
                ) from exc

            if terminal is not None:
                full_text = terminal.get("content") or "".join(content_parts)
                result = {
                    "message": full_text,
                    "model": terminal.get("model"),
                    "provider": terminal.get("provider"),
                    "usage": terminal.get("usage"),
                    "latency_ms": terminal.get("latency_ms"),
                    "finish_reason": terminal.get("finish_reason"),
                }
            else:
                # No provider in the fabric could stream. Fall back to the
                # buffered path so non-streaming providers still work; this is
                # reported honestly as streamed=False rather than faked.
                result = await self._generate(
                    content, model, user_id, session_id,
                    request_id=request_id_for_audit, principal=principal,
                )
                full_text = result["message"]
                result["streamed"] = False
                if full_text:
                    assistant_msg["content"] = full_text
                    get_store("chat_sessions").save()
                    yield {
                        "type": "chunk",
                        "content": full_text,
                        "text": full_text,
                        "message_id": assistant_id,
                    }

            assistant_msg.update({
                "content": full_text,
                "status": COMPLETED,
                "model": result.get("model"),
                "revision": result.get("revision"),
                "backend": result.get("backend"),
                "device": result.get("device"),
                "usage": result.get("usage"),
                "provider": result.get("provider"),
                "latency_ms": result.get("latency_ms"),
                "sources": result.get("sources"),
                "tool_calls": result.get("tool_calls"),
                "runtime_command_id": result.get("runtime_command_id"),
            })
            if result.get("message"):
                from .presentation_contract import build_conversation_presentation

                result["presentation"] = build_conversation_presentation(
                    result["message"],
                    request_id=request_id_for_audit,
                    session_id=session_id,
                    conversation_id=session_id,
                )
                assistant_msg["presentation"] = result["presentation"]
                self._persist_presentation_revision(
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id_for_audit,
                    assistant_message=assistant_msg,
                    presentation=result["presentation"],
                )
            get_store("chat_sessions").save()
            session["updated_at"] = now_iso()
            get_store("chat_sessions").save()

            input_tokens = _usage_tokens(result.get("usage") or {},
                                        "prompt_tokens", "input_tokens")
            output_tokens = _usage_tokens(result.get("usage") or {},
                                         "completion_tokens", "output_tokens")
            self._record_usage(
                result.get("provider"), result.get("model"), user_id,
                request_id_for_audit or str(uuid.uuid4()),
                input_tokens, output_tokens,
                (result.get("usage") or {}).get("total_cost_usd", 0.0) or 0.0,
                int(result.get("latency_ms") or 0),
            )
            self._record_audit_success(
                user_id, request_id_for_audit or "", session_id,
                result.get("provider"), result.get("model"),
                int(result.get("latency_ms") or 0), input_tokens, output_tokens,
            )

            yield {
                "type": "complete",
                "session_id": session_id,
                "content": full_text,
                "status": COMPLETED,
                "message_id": assistant_id,
                "streamed": bool(streamed),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "usage": result.get("usage"),
                "latency_ms": result.get("latency_ms"),
                "request_id": request_id_for_audit,
                "presentation": result.get("presentation"),
                "canonical_task_id": assistant_msg.get("canonical_task_id"),
                "presentation_revision_id": assistant_msg.get("presentation_revision_id"),
            }
        except ChatError as exc:
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(exc)
            session["updated_at"] = now_iso()
            get_store("chat_sessions").save()
            yield {
                "type": "error",
                "category": exc.category.value,
                "message": exc.safe_message,
                "request_id": exc.request_id,
                "retryable": exc.retryable,
                "status": FAILED,
                "message_id": assistant_id,
            }
        except Exception as exc:
            err = normalize_exception(exc)
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(err)
            session["updated_at"] = now_iso()
            get_store("chat_sessions").save()
            yield {
                "type": "error",
                "category": err.category.value,
                "message": err.safe_message,
                "request_id": err.request_id,
                "retryable": err.retryable,
                "status": FAILED,
                "message_id": assistant_id,
            }

    def regenerate(self, user_id: str, session_id: str, message_id: str,
                   *, model: str | None = None) -> dict[str, Any]:  # noqa: ARG002
        session = self.get_session(user_id, session_id)
        messages: list[dict[str, Any]] = session.get("messages") or []
        target = next((m for m in messages if m.get("id") == message_id and m.get("role") == "user"), None)
        if not target:
            raise ChatError(ErrorCategory.INVALID_REQUEST, "Message not found.", status_code=404)
        idx = messages.index(target)
        # Truncate everything after the user message, then let the caller re-run.
        del messages[idx + 1:]
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()
        return {
            "session_id": session_id,
            "message": target.get("content"),
            "client_message_id": target.get("client_message_id"),
            "truncated": True,
        }

    def record_feedback(self, user_id: str, session_id: str, message_id: str,
                        rating: int, comment: str | None = None) -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        messages = session.get("messages") or []
        target = next((m for m in messages if m.get("id") == message_id), None)
        if not target:
            raise ChatError(ErrorCategory.INVALID_REQUEST, "Message not found.", status_code=404)
        feedback = target.setdefault("feedback", {})
        feedback.update({"rating": rating})
        if comment is not None:
            feedback["comment"] = comment
        feedback["updated_at"] = now_iso()
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()
        return {"success": True, "rating": rating}

    def edit_message(self, user_id: str, session_id: str, message_id: str,
                     new_content: str, *, model: str | None = None,
                     client_message_id: str | None = None) -> dict[str, Any]:
        """Edit a user message and regenerate the assistant response.
        
        This operation:
        1. Verifies the message belongs to the user's session
        2. Updates the user message content
        3. Truncates any assistant response that followed
        4. Returns the edited message and allows re-sending
        
        The conversation history remains internally consistent - the old
        assistant response is preserved but superseded.
        
        Idempotency: if client_message_id is provided, this is safe to retry
        (returns cached results if the same eddits were already processed).
        """
        session = self.get_session(user_id, session_id)
        messages: list[dict[str, Any]] = session.setdefault("messages", [])
        
        # Find the target user message
        target_idx = None
        for i, m in enumerate(messages):
            if m.get("id") == message_id and m.get("role") == "user":
                target_idx = i
                break
        
        if target_idx is None:
            raise ChatError(
                ErrorCategory.INVALID_REQUEST,
                "Message not found or is not a user message.",
                status_code=404,
            )
        
        # Update the user message content
        messages[target_idx]["content"] = new_content
        messages[target_idx]["updated_at"] = now_iso()
        
        # Truncate everything after the user message (supersede old assistant response)
        # This preserves the edit history while making the conversation consistent
        del messages[target_idx + 1:]
        
        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()
        
        # Return the state needed to regenerate/resend
        return {
            "session_id": session_id,
            "message_id": message_id,
            "content": new_content,
            "client_message_id": client_message_id or str(uuid.uuid4()),
            "status": QUEUED,
        }

    async def edit_and_resend(self, user_id: str, session_id: str, message_id: str, new_content: str,
                              *, model: str | None = None,
                              client_message_id: str | None = None) -> dict[str, Any]:
        """Edit a user message and immediately generate a fresh assistant reply.

        This is the atomic "edit + resend" flow:
        1. ``edit_message`` updates the user message content and truncates any
           following assistant reply (ownership is verified there).
        2. Checks for idempotency - if a response with the same client_message_id
           already exists, returns it without generating a new one.
        3. Creates a new assistant message with QUEUED status.
        4. ``_generate`` produces a new assistant response from the edited prompt.
        5. Updates the assistant message with the result and returns it.

        Returns the generated assistant message dict.
        """
        # 1. Edit + truncate (verifies ownership, raises ChatError on 403/404).
        edit_result = self.edit_message(
            user_id, session_id, message_id, new_content,
            client_message_id=client_message_id
        )
        
        cm_id = edit_result.get("client_message_id") or client_message_id
        
        session = self.get_session(user_id, session_id)
        messages: list[dict[str, Any]] = session.get("messages") or []
        
        # 2. Check for idempotency - if there's already a response for this client_message_id
        if cm_id:
            existing = self._find_by_client_id(messages, cm_id)
            if existing:
                reply = self._find_assistant_after(messages, existing.get("id", ""))
                if reply:
                    return {
                        "session_id": session_id,
                        "message": reply.get("content"),
                        "model": reply.get("model"),
                        "revision": reply.get("revision"),
                        "backend": reply.get("backend"),
                        "device": reply.get("device"),
                        "latency_ms": reply.get("latency_ms"),
                        "sources": reply.get("sources"),
                        "status": reply.get("status"),
                        "error": reply.get("error"),
                        "resumed": True,
                        "message_id": reply.get("id"),
                    }

        # 3. Create a new assistant message with QUEUED status
        assistant_id = str(uuid.uuid4())
        assistant_msg = _new_message(
            assistant_id, "assistant", "", status=QUEUED, model=model,
            client_message_id=cm_id,
        )
        messages.append(assistant_msg)
        get_store("chat_sessions").save()

        # 4. Generate a fresh assistant response from the edited prompt.
        try:
            result = await self._generate(new_content, model, user_id, session_id)
            # 5. Update the assistant message with the result
            assistant_msg.update({
                "content": result.get("message"),
                "status": COMPLETED,
                "model": result.get("model"),
                "revision": result.get("revision"),
                "backend": result.get("backend"),
                "device": result.get("device"),
                "usage": result.get("usage"),
                "provider": result.get("provider"),
                "latency_ms": result.get("latency_ms"),
            })
        except ChatError as exc:
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(exc)
        except Exception as exc:
            err = normalize_exception(exc)
            assistant_msg["status"] = FAILED
            assistant_msg["error"] = _error_card(err)

        session["updated_at"] = now_iso()
        get_store("chat_sessions").save()

        return {
            "session_id": session_id,
            "message": assistant_msg.get("content"),
            "model": assistant_msg.get("model"),
            "provider": assistant_msg.get("provider"),
            "revision": assistant_msg.get("revision"),
            "backend": assistant_msg.get("backend"),
            "device": assistant_msg.get("device"),
            "latency_ms": assistant_msg.get("latency_ms"),
            "usage": assistant_msg.get("usage"),
            "sources": assistant_msg.get("sources"),
            "status": assistant_msg.get("status"),
            "error": assistant_msg.get("error"),
            "resumed": False,
            "message_id": assistant_id,
        }


chat_service = ChatService()
