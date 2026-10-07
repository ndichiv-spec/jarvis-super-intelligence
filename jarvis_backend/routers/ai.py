"""AI processing, generation, feedback, tasks, and LLM endpoints."""

from __future__ import annotations

import asyncio
import socket
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import _require_auth, ai_service, get_store, now_iso

router = APIRouter(prefix="/api/v1", tags=["ai"])

# --------------------------------------------------------------------------- #
# Task Lifecycle States (Phase 6)
# --------------------------------------------------------------------------- #
TASK_STATES = [
    "RECEIVED",      # Task created, awaiting processing
    "UNDERSTOOD",    # Intent detected and understood
    "PLANNED",       # Plan generated with capabilities
    "AUTHORIZATION_REQUIRED",  # Waiting for user authorization
    "AUTHORIZED",    # User has approved the plan
    "RUNNING",       # Task is executing
    "WAITING",       # Task waiting for external resources
    "COMPLETED",     # Task finished (may need verification)
    "VERIFIED",      # Task output has been verified
    "PARTIAL",       # Task completed with partial results
    "FAILED",        # Task failed
    "CANCELLED",     # Task was cancelled
]

# Default task status
DEFAULT_TASK_STATUS = "RECEIVED"


class ProcessIn(BaseModel):
    input: Optional[str] = None
    message: Optional[str] = None
    mode: str = "chat"
    model: Optional[str] = None
    stream: bool = False
    session_id: Optional[str] = None
    verify: bool = False  # True -> draft/verification/correction loop + sources


class GenerateIn(BaseModel):
    prompt: str
    max_tokens: int = 500


class FeedbackIn(BaseModel):
    query: str
    response: str
    rating: int


class TaskIn(BaseModel):
    """Request to create a Phase 6 task with full lifecycle support."""
    type: str = Field(..., description="Task type: chat, analyze, verify, etc.")
    input: str = Field(..., description="Task input/prompt")
    # Optional Phase 6 fields
    intent: Optional[str] = Field(None, description="Detected intent")
    capabilities: Optional[List[str]] = Field(None, description="Required capabilities")
    plan: Optional[List[str]] = Field(None, description="Execution plan steps")
    execution_mode: str = Field(default="ONLINE", description="ONLINE|DEGRADED|OFFLINE")
    risk_level: Optional[str] = Field(None, description="risk: low|medium|high")
    verification_required: bool = Field(default=True, description="Whether output needs verification")
    # Existing fields for backward compatibility
    session_id: Optional[str] = Field(None, description="Associated chat session")


class TaskUpdate(BaseModel):
    """Update an existing task's state and metadata."""
    status: Optional[str] = Field(None, description="New task status")
    result: Optional[Any] = Field(None, description="Task result")
    evidence: Optional[List[Dict]] = Field(None, description="Verification evidence")
    verification: Optional[Dict] = Field(None, description="Verification metadata")
    current_step: Optional[int] = Field(None, description="Current step in plan")
    total_steps: Optional[int] = Field(None, description="Total steps in plan")


class LlmChatIn(BaseModel):
    input: str
    provider: Optional[str] = None


def _endpoint_reachable(endpoint: str, timeout: float = 1.5) -> bool:
    """Return True only if a TCP connection to the endpoint actually succeeds.

    Used instead of "the env var is set" so Brain / Silverwing availability
    reflects a real liveness probe, never an assumption.
    """
    if not endpoint:
        return False
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _probe_endpoint(endpoint: str) -> bool:
    return await asyncio.to_thread(_endpoint_reachable, endpoint)


async def _probe_silverwing_chat(endpoint: str) -> bool:
    """Probe whether the Silverwing runtime can actually serve chat completions.

    A TCP-open /v1/health returning 200 is NOT proof the runtime can infer.
    This sends a tiny real inference request with a short timeout and
    returns True only when the runtime returns a parseable response.
    """
    if not endpoint:
        return False
    if endpoint.lower().endswith("/v1") or endpoint.lower().endswith("/chat/completions"):
        post_url = endpoint.rstrip("/") + "/chat/completions"
    elif endpoint.lower().endswith("/v1/chat/completions"):
        post_url = endpoint
    else:
        post_url = endpoint.rstrip("/") + "/v1/chat/completions"

    import httpx
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = await client.post(post_url, json={
                "model": "silverwing-120m-base-v1",
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 1,
            }, headers={"Content-Type": "application/json"})
            if resp.status_code < 500:
                data = resp.json()
                choices = data.get("choices") or []
                if choices and (choices[0].get("message") or {}).get("content"):
                    return True
    except Exception:
        pass
    return False


@router.post("/ai/process")
async def ai_process(body: ProcessIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Provider-backed chat bridge (Silverwing-first).

    The web chat posts here. Route through ProviderGateway so the trained
    Silverwing runtime answers when SILVERWING_ENDPOINT is set; otherwise
    fail honestly with 502 (never a canned answer presented as a model).
    """
    import os as _os

    from ..gateway import ChatError, provider_gateway

    text = (body.message or body.input or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty message")
    model = (body.model or "").strip() or None
    if model in ("auto", "ollama", "local-rule"):
        model = None  # Silverwing default (own trained runtime)
    # Detect a Phase 6 provider:model prefix (e.g. "nvidia:meta/llama-3.3-70b-instruct").
    # When present, bypass the JARVIS Brain and Silverwing runtime tiers so the
    # request is routed through the Phase 6 fabric directly.
    _bypass = bool(model and ":" in model and model.split(":", 1)[0] in ("openai", "nvidia", "google", "aws", "hf"))
    if body.verify or (body.mode or "").strip().lower() == "verify":
        from ..verify import verified_chat

        try:
            result = await verified_chat(text, model=model)
        except ChatError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"AI backend failure: {e}")
        return {
            "response": result["content"],
            "model": result.get("model"),
            "provider": result.get("provider", "silverwing"),
            "latency_ms": result.get("latency_ms"),
            "tokens_used": (result.get("usage") or {}).get("total_tokens"),
            "session_id": body.session_id,
            "sources": result.get("sources", []),
            "math": result.get("math", []),
            "verification": result.get("verification", "unverified"),
        }
    # Route through ChatService so the session is created/managed, the message
    # is persisted, and the full conversation history is passed to the provider
    # (maintaining continuity across turns). Previously this called
    # provider_gateway.chat with only the current message, so the model never
    # saw prior turns in the session.
    from ..chat_service import chat_service

    session_id = body.session_id or str(uuid.uuid4())
    user_id = user["id"]
    chat_service.create_session(user_id, session_id, text)

    try:
        result = await chat_service.send_message(
            user_id, session_id, text,
            model=model,
            client_message_id=getattr(body, "client_message_id", None),
        )
    except ChatError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI backend failure: {e}")
    return {
        "response": result.get("message"),
        "model": result.get("model"),
        "provider": result.get("provider", "silverwing"),
        "latency_ms": result.get("latency_ms"),
        "tokens_used": (result.get("usage") or {}).get("total_tokens") or 0,
        "session_id": session_id,
        "message_id": result.get("message_id"),
        "status": result.get("status", "COMPLETED"),
    }


@router.post("/ai/generate")
async def ai_generate(body: GenerateIn):
    raise HTTPException(
        status_code=410,
        detail=(
            "/api/v1/ai/generate is deprecated and no longer returns canned "
            "responses. Use POST /api/chat for authenticated, provider-backed "
            "completion."
        ),
    )


@router.post("/ai/feedback")
async def ai_feedback(body: FeedbackIn, user: Dict[str, Any] = Depends(_require_auth)):
    feedback = get_store("misc").load().setdefault("feedback", [])
    feedback.append({
        "id": str(uuid.uuid4()),
        "query": body.query,
        "response": body.response,
        "rating": body.rating,
        "timestamp": now_iso(),
    })
    get_store("misc").save()
    return {"success": True, "rating": body.rating}


async def _provider_catalog() -> Dict[str, Any]:
    """Build the JARVIS provider/model catalog from the Silverwing runtime.

    Merges the JARVIS Brain (remote) and the Silverwing native runtime into the
    provider list surfaced by :class:`ModelManager` so the frontend can render a
    single provider -> model selector.  Availability is derived from live auth
    checks (env vars / SDK presence) and never from a static list.
    """
    import os as _os

    from ..gateway import _load_silverwing

    catalog: Dict[str, Any] = {
        "providers": [],
        "default_provider": None,
        "default_model": None,
    }
    try:
        sw = _load_silverwing()
        mgr = sw.ModelManager()
        status = mgr.auth_status()
        default_model = mgr.default_model()
        catalog["default_model"] = default_model
        catalog["default_provider"] = "jarvis-brain" if _os.environ.get("JARVIS_BRAIN_ENDPOINT") else (
            "silverwing" if _os.environ.get("SILVERWING_ENDPOINT") else "auto"
        )
        for name, info in status["providers"].items():
            entry: Dict[str, Any] = {
                "provider": name,
                "available": info["available"],
                "authorized": info["authorized"],
                "model": info["model"],
                "models": [m.model_id for m in sw.list_by_provider(name)],
            }
            catalog["providers"].append(entry)
    except Exception:
        # Silverwing not importable yet — still report Brain / Silverwing runtime
        # stubs so the UI can present them (they may be configured at runtime).
        pass

    # JARVIS Brain (remote OpenAI-compatible endpoint on Kaggle GPU host).
    # Availability requires a real reachability probe, not just a configured URL.
    brain_ep = _os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    brain_up = await _probe_endpoint(brain_ep) if brain_ep else False
    catalog["providers"].append({
        "provider": "jarvis-brain",
        "available": False,
        "authorized": brain_up,
        "configured": bool(brain_ep),
        "inference_verified": False,
        "model": _os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1"),
        "models": [_os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1")],
        "health_status": "reachable_unverified" if brain_up else "unreachable",
        "errors": None if brain_up else "endpoint did not accept a connection",
    })

    # Silverwing native runtime (own trained 120M weights).
    sw_ep = _os.environ.get("SILVERWING_ENDPOINT", "").strip()
    sw_up = await _probe_endpoint(sw_ep) if sw_ep else False
    catalog["providers"].append({
        "provider": "silverwing",
        "available": False,
        "authorized": sw_up,
        "configured": bool(sw_ep),
        "inference_verified": False,
        "model": _os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
        "models": [_os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1")],
        "health_status": "reachable_unverified" if sw_up else "unreachable",
        "errors": None if sw_up else "endpoint did not accept a connection",
    })

    # Phase 6: real provider fabric (OpenAI, NVIDIA, Google, AWS, HuggingFace).
    # Override Silverwing's static provider entries with live health/auth status.
    # Build the de-dup dict with Silverwing entries first.
    seen: Dict[str, Dict[str, Any]] = {}
    for _entry in catalog["providers"]:
        seen[_entry["provider"]] = _entry
    _fabric_providers: set[str] = set()

    try:
        from ..gateway import (
            _ensure_provider_fabric_import_path,
            verified_streaming_providers,
        )
        _ensure_provider_fabric_import_path()
        from providers.control_center import ProviderControlCenter  # type: ignore[import-not-found]
        from providers.bootstrap import bootstrap_fabric  # type: ignore[import-not-found]
        _fabric = bootstrap_fabric()
        cc = ProviderControlCenter()
        _fabric_providers = set(cc.list_providers())
        _streaming_verified = verified_streaming_providers()
        for pid in _fabric_providers:
            try:
                st = cc.check_provider(pid)
            except Exception:
                continue
            # Get real model list from the adapter
            _adapter = _fabric._adapters.get(pid)
            _models = [m.model_id for m in _adapter.models] if _adapter and _adapter.models else []
            _default_model = _models[0] if _models else None
            # A model-list probe proves configuration and reachability, not
            # inference. Only a successful provider response marks it available.
            _healthy = st.health_status in ("healthy", "degraded")
            _serves_chat = any(
                c in ("chat", "streaming", "reasoning")
                for c in (st.capabilities or [])
            )
            _available = bool(
                st.configured and _healthy and st.inference_verified and _serves_chat
            )
            entry: Dict[str, Any] = {
                "provider": pid,
                "display_name": st.display_name,
                "available": _available,
                # Credential accepted for authenticated calls (model listing is
                # itself an authenticated probe for these providers) or a prior
                # verified inference.
                "authorized": bool(
                    st.inference_authorized or (st.configured and st.model_list_available)
                ),
                "healthy": _healthy,
                "configured": st.configured,
                "model_list_available": st.model_list_available,
                "inference_verified": st.inference_verified,
                "streaming_verified": pid in _streaming_verified,
                "model": _default_model,
                "models": _models,
                "capabilities": st.capabilities,
                "latency_ms": st.latency_ms,
                "health_status": st.health_status,
                "errors": st.errors,
                "last_checked": st.last_checked,
                "actions": st.actions,
            }
            seen[pid] = entry
    except Exception:
        # Phase 6 fabric not available — degrade gracefully.
        pass

    # Entries that the real fabric does not back (Silverwing static stubs such
    # as "local"/"local-rule", anthropic, groq, ollama, ...) are never offered
    # as selectable models: their availability claims come from a static list,
    # not a live probe, and some are rule-based responders rather than models.
    # This prevents the UI from advertising fake/unverified providers as ready.
    for _pid, _entry in seen.items():
        if _pid in _fabric_providers:
            continue
        if _pid in ("jarvis-brain", "silverwing"):
            continue  # handled with real reachability probes above
        if _entry.get("available"):
            _entry["errors"] = "not backed by the live provider fabric"
        _entry["available"] = False
        _entry["authorized"] = False

    catalog["providers"] = list(seen.values())
    return catalog


def _provider_catalog_sync() -> Dict[str, Any]:
    """Synchronous wrapper over :func:`_provider_catalog` for tool code.

    Document/model tooling runs outside the event loop, so it needs a blocking
    accessor to the SAME catalog - not a second, divergent implementation.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Inside a loop: run in a dedicated thread with its own loop.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(_provider_catalog())).result()
    return asyncio.run(_provider_catalog())


@router.get("/ai/models")
async def ai_models():
    """Return the live provider/model catalog.

    Each entry carries ``provider``, ``available``, ``authorized``, the default
    ``model`` for that provider, and a ``models`` list.  The frontend renders a
    provider -> model selector from this payload; the chosen ``provider:model``
    string is sent back on ``POST /ai/process`` as ``model``.
    """
    catalog = await _provider_catalog()
    # Default selection: prefer a Phase 6 provider that is actually ready
    # (available + authorized) — a live cloud provider gives the user the best
    # first experience.  Only fall back to the JARVIS Brain / Silverwing
    # runtime stubs when no Phase 6 provider is reachable.
    _phase6 = {"openai", "nvidia", "google", "aws", "hf"}
    default_provider = catalog["default_provider"]
    default_model = catalog["default_model"]

    # Phase 6 providers are preferred over local stubs when they are live.
    _chosen: Optional[Dict[str, Any]] = None
    for p in catalog["providers"]:
        if (
            p["provider"] in _phase6
            and p.get("available")
            and p.get("authorized")
        ):
            _chosen = p
            break

    if _chosen is not None:
        default_provider = _chosen["provider"]
        default_model = _chosen["model"]
    elif default_provider == "auto":
        # No Phase 6 provider is ready — fall back to Brain / Silverwing stubs.
        for p in catalog["providers"]:
            if p["provider"] in ("jarvis-brain", "silverwing") and p["available"]:
                default_provider = p["provider"]
                default_model = p["model"]
                break
        else:
            for p in catalog["providers"]:
                if p["available"]:
                    default_provider = p["provider"]
                    default_model = p["model"]
                    break

    catalog["default_provider"] = default_provider
    catalog["default_model"] = default_model
    return catalog


@router.get("/ai/status")
async def ai_status():
    import os as _os

    data = {"status": "degraded", **ai_service.settings()}
    catalog = await _provider_catalog()
    configured_providers = [
        provider for provider in catalog["providers"] if provider.get("configured")
    ]
    verified_providers = [
        provider for provider in configured_providers
        if provider.get("inference_verified") and provider.get("available")
    ]
    data["configured_provider_count"] = len(configured_providers)
    data["provider_available"] = bool(verified_providers)
    data["providers"] = [
        {
            "provider": provider["provider"],
            "status": (
                "AVAILABLE" if provider in verified_providers
                else "CONFIGURED" if provider.get("configured")
                else "UNCONFIGURED"
            ),
            "inference_verified": bool(provider.get("inference_verified")),
        }
        for provider in catalog["providers"]
    ]
    if verified_providers:
        data["provider"] = verified_providers[0]["provider"]
        data["enabled"] = True
    # The platform's own trained model needs no cloud key: report the chat
    # path as enabled only when the Silverwing runtime is actually reachable.
    # Availability must be based on a real TCP probe, not just a configured URL.
    sw_endpoint = _os.environ.get("SILVERWING_ENDPOINT", "").strip()
    data["silverwing_endpoint_configured"] = bool(sw_endpoint)
    data["silverwing_model"] = _os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1")
    # Silverwing is integrated in-process under /silverwing in the single-process
    # deployment; verify that mount (real flag) before the standalone :8010
    # runtime, which is optional and not started here. Otherwise AI is reported
    # as inactive despite the Silverwing backend being live.
    sw_up = bool(sw_endpoint) and await _probe_endpoint(sw_endpoint)
    if not sw_up:
        try:
            from ..main import _silverwing_app, _silverwing_error  # deferred
            sw_up = _silverwing_app is not None and _silverwing_error is None
        except Exception:
            sw_up = False
    # A TCP-reachable runtime is not necessarily able to serve chat: the
    # Silverwing :8010 health endpoint returns 200 while /v1/chat/completions
    # can hang indefinitely. Probe the actual chat endpoint so "healthy"
    # is only reported when a real inference is possible.
    sw_can_chat = await _probe_silverwing_chat(sw_endpoint) if sw_up else False
    data["silverwing"] = {
        "configured": bool(sw_endpoint),
        "reachable": sw_up,
        "healthy": sw_can_chat,
        "status": "healthy" if sw_can_chat else ("reachable" if sw_up else "unreachable"),
        "last_checked": now_iso() if sw_up else None,
        "errors": None if sw_can_chat else ("runtime /v1/chat/completions not responding" if sw_up else ("runtime not reachable" if sw_endpoint else "not configured")),
        "model": _os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
    }
    # JARVIS BRAIN (remote Qwen3-4B) — configured endpoint only; liveness is
    # measured by a real probe, never assumed.  Healthy only after the probe
    # succeeds.
    brain_endpoint = _os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    data["brain_endpoint_configured"] = bool(brain_endpoint)
    data["brain_model"] = _os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1")
    from ..gateway import ProviderGateway, _jarvis_brain_api_key_configured
    data["brain_api_key_configured"] = _jarvis_brain_api_key_configured()
    if brain_endpoint:
        probe = await ProviderGateway().probe_brain()
        if isinstance(probe, dict):
            probe.pop("endpoint", None)
        data["brain"] = probe
        if probe.get("healthy"):
            data["provider_available"] = True
            for provider in data["providers"]:
                if provider["provider"] == "jarvis-brain":
                    provider["status"] = "AVAILABLE"
                    provider["inference_verified"] = True
    else:
        data["brain"] = {"configured": False, "healthy": False}
    # Online status requires a successful inference, not only model-list or
    # endpoint reachability.
    brain_verified = bool(data.get("brain", {}).get("healthy"))
    _real_provider = bool(verified_providers) or sw_can_chat or brain_verified
    data["enabled"] = _real_provider
    data["provider"] = (
        verified_providers[0]["provider"] if verified_providers
        else "silverwing" if sw_can_chat
        else "jarvis-brain" if brain_verified
        else "auto"
    )
    data["platform_status"] = "online" if _real_provider else "degraded"
    data["status"] = "ready" if _real_provider else "degraded"
    return data


@router.post("/ai/tasks")
async def create_ai_task(body: TaskIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Create a Phase 6 task with full lifecycle support.
    
    Tasks go through states: RECEIVED -> UNDERSTOOD -> PLANNED -> RUNNING -> COMPLETED -> VERIFIED
    """
    tasks = get_store("tasks").load()
    task_id = str(uuid.uuid4())
    
    task = {
        "id": task_id,
        "type": body.type,
        "input": body.input,
        "status": DEFAULT_TASK_STATUS,
        "user_id": user.get("id") or user.get("email"),
        "session_id": body.session_id,
        "created_at": now_iso(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "intent": body.intent,
        "capabilities": body.capabilities or [],
        "plan": body.plan or [],
        "current_step": 0,
        "total_steps": len(body.plan) if body.plan else 0,
        "execution_mode": body.execution_mode,
        "risk_level": body.risk_level or "low",
        "verification_required": body.verification_required,
        "verification": None,
        "evidence": [],
        "error": None,
    }
    
    tasks[task_id] = task
    get_store("tasks").save()
    return task


@router.get("/ai/tasks")
async def list_ai_tasks(user: Dict[str, Any] = Depends(_require_auth)):
    """List tasks for the authenticated user."""
    tasks = get_store("tasks").load()
    user_tasks = {
        tid: t for tid, t in tasks.items() 
        if isinstance(t, dict) and t.get("user_id") == user.get("id")
    }
    return {"tasks": list(user_tasks.values())}


@router.get("/ai/tasks/{task_id}")
async def get_ai_task(
    task_id: str,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Get a specific task by ID (ownership protected)."""
    tasks = get_store("tasks").load()
    task = tasks.get(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Ownership protection
    if isinstance(task, dict) and task.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return task


@router.patch("/ai/tasks/{task_id}")
async def update_ai_task(
    task_id: str,
    body: TaskUpdate,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Update a task's state and metadata.
    
    Supports state transitions with validation.
    """
    tasks = get_store("tasks").load()
    task = tasks.get(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Ownership protection
    if task.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate status is a valid state
    if body.status and body.status not in TASK_STATES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status: {body.status}. Valid: {TASK_STATES}"
        )
    
    # Update task
    if body.status:
        task["status"] = body.status
        if body.status in ("COMPLETED", "VERIFIED") and not task.get("started_at"):
            task["started_at"] = now_iso()
        if body.status in ("COMPLETED", "VERIFIED", "FAILED", "CANCELLED"):
            task["completed_at"] = now_iso()
    
    if body.result is not None:
        task["result"] = body.result
    
    if body.evidence:
        task["evidence"] = body.evidence
    
    if body.verification:
        task["verification"] = body.verification
    
    if body.current_step is not None:
        task["current_step"] = body.current_step
    
    if body.total_steps is not None:
        task["total_steps"] = body.total_steps
    
    tasks[task_id] = task
    get_store("tasks").save()
    return task


@router.post("/ai/tasks/{task_id}/cancel")
async def cancel_ai_task(
    task_id: str,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Cancel a running task."""
    tasks = get_store("tasks").load()
    task = tasks.get(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Ownership protection
    if task.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Only cancel if not already completed/failed/cancelled
    if task["status"] not in ("RUNNING", "WAITING", "PLANNED"):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel task in status: {task['status']}"
        )
    
    task["status"] = "CANCELLED"
    task["completed_at"] = now_iso()
    task["error"] = "Task cancelled by user"
    
    tasks[task_id] = task
    get_store("tasks").save()
    return {"success": True, "task_id": task_id, "status": "CANCELLED"}


@router.post("/llm/chat")
async def llm_chat(body: LlmChatIn):
    raise HTTPException(
        status_code=410,
        detail=(
            "/llm/chat is deprecated and no longer returns canned responses. "
            "Use POST /api/chat for authenticated, provider-backed chat."
        ),
    )


@router.get("/llm/status")
async def llm_status():
    return {"status": "ready", **ai_service.settings()}


@router.get("/holographic/state")
async def holographic_state():
    """Canonical read model for Holographics UI.

    Aggregates real state from:
    1. AI status (providers, models, capabilities)
    2. Provider catalog (health, availability)
    3. System monitors
    4. Job/task state
    5. Conversation/session state
    6. Authentication/authorization state
    7. Audit events
    8. Resource usage metrics

    This endpoint provides a single source of truth for the Holographic UI.
    Every visual state comes from real backend/platform state.
    """
    import os as _os
    from datetime import datetime, timezone

    # Get AI status from our fixed endpoint
    ai_status_data = await ai_status()

    # Get provider catalog
    catalog = await _provider_catalog()

    # Get system health
    misc = get_store("misc").load()

    # Get conversation/session stats
    chat_sessions = get_store("chat_sessions").load()
    session_count = len(chat_sessions) if isinstance(chat_sessions, dict) else 0

    # Get task/agent stats
    tasks = get_store("tasks").load()
    task_count = len(tasks) if isinstance(tasks, dict) else 0
    agents = get_store("agents").load()
    agent_count = len(agents) if isinstance(agents, dict) else 0

    # Get audit log stats
    audit_logs = get_store("audit_logs").load()
    audit_count = len(audit_logs) if isinstance(audit_logs, list) else 0

    # Get knowledge/RAG stats
    knowledge = get_store("knowledge").load()
    knowledge_count = len(knowledge) if isinstance(knowledge, dict) else 0

    # Get memory stats
    memory = get_store("memory").load()
    memory_count = len(memory) if isinstance(memory, dict) else 0

    # Get browser sessions
    browser_sessions = get_store("browser_sessions").load()
    browser_count = len(browser_sessions) if isinstance(browser_sessions, dict) else 0

    # Get reminders/notes
    reminders = get_store("reminders").load()
    notes = get_store("notes").load()
    reminder_count = len(reminders) if isinstance(reminders, dict) else 0
    note_count = len(notes) if isinstance(notes, dict) else 0

    # Get RSS feeds
    rss_feeds = get_store("rss_feeds").load()
    feed_count = len(rss_feeds) if isinstance(rss_feeds, dict) else 0

    from ..runtime_status import check_database_status
    from ..celery_app import get_queue_runtime_status

    database_status, queue_status = await asyncio.gather(
        check_database_status(),
        asyncio.to_thread(get_queue_runtime_status),
    )
    provider_online = any(
        provider.get("available") and provider.get("authorized")
        for provider in catalog.get("providers", [])
    )
    brain_online = bool((ai_status_data.get("brain") or {}).get("healthy"))
    silverwing_online = bool((ai_status_data.get("silverwing") or {}).get("healthy"))
    ai_enabled = provider_online or brain_online or silverwing_online
    service_online = (
        database_status.get("status") == "AVAILABLE"
        and queue_status.get("broker_reachable")
        and queue_status.get("worker_probe") == "ok"
        and ai_enabled
    )
    ai_provider = (
        ai_status_data.get("provider")
        or catalog.get("default_provider")
        or "none"
    ) if ai_enabled else "none"

    # Build the holographic state response
    return {
        "version": _os.environ.get("JARVIS_VERSION", "3.0.0"),
        "timestamp": now_iso(),
        "deployment": {
            "git_sha": _os.environ.get("GIT_SHA", "unknown"),
            "build_time": _os.environ.get("BUILD_TIME", "unknown"),
            "environment": _os.environ.get("ENVIRONMENT", _os.environ.get("JARVIS_ENV", "development")),
            "deployment_id": _os.environ.get("DEPLOYMENT_ID", "local"),
        },
        "platform": {
            "status": "online" if service_online else "degraded",
            "uptime_seconds": misc.get("platform_uptime_seconds", 0),
            "started_at": misc.get("platform_started_at"),
            "environment": _os.environ.get("JARVIS_ENV", "development"),
        },
        "system_health": {
            "backend": "healthy",
            "database": "connected" if database_status.get("status") == "AVAILABLE" else "unavailable",
            "queue": "online" if queue_status.get("broker_reachable") and queue_status.get("worker_probe") == "ok" else "degraded",
            "disk_usage": "not_reported",
        },
        "ai": {
            "enabled": ai_enabled,
            "provider": ai_provider,
            "platform_status": "online" if ai_enabled else "degraded",
            "capabilities": ai_status_data.get("capabilities", ["chat", "analysis"]),
            "silverwing": ai_status_data.get("silverwing", {
                "configured": False,
                "reachable": False,
                "healthy": False,
                "status": "unreachable",
                "errors": "not configured",
            }),
            "brain": ai_status_data.get("brain", {
                "configured": False,
                "healthy": False,
            }),
            "models": catalog.get("default_model"),
            "default_provider": catalog.get("default_provider"),
        },
        "providers": catalog.get("providers", []),
        "platform_state": {
            "sessions": session_count,
            "active_tasks": task_count,
            "agents": agent_count,
            "audit_events": audit_count,
            "knowledge_base": knowledge_count,
            "memory_entries": memory_count,
            "browser_sessions": browser_count,
            "reminders": reminder_count,
            "notes": note_count,
            "rss_feeds": feed_count,
        },
        "security": {
            "authenticated": False,
        },
    }
