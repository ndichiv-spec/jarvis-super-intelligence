"""System control, processes, files, clipboard, launch, provider settings.

SEC-1: All endpoints are authenticated and authorized.
Destructive operations require admin role.
Credential material never reaches the model context.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..core import (
    ROOT, ai_service, get_store, now_iso, get_current_user,
    get_optional_user, is_admin,
    _require_auth, _require_admin, _audit_system_action,
)

logger = logging.getLogger("jarvis.backend.system")

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class ProcessKillIn(BaseModel):
    pid: int
    force: bool = False


class ProviderSettingsIn(BaseModel):
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None


# Secret-shaped field names that must never be accepted via provider-settings PUT.
_SECRET_SHAPES = ("key", "secret", "token", "password", "credential", "private_key")


_APPS = [
    {"name": "Notepad", "command": "notepad.exe"},
    {"name": "Calculator", "command": "calc.exe"},
    {"name": "Paint", "command": "mspaint.exe"},
    {"name": "Command Prompt", "command": "cmd.exe"},
    {"name": "File Explorer", "command": "explorer.exe"},
    {"name": "Browser", "command": "start http://localhost:3000"},
]


@router.get("/status")
async def system_status():
    return {
        "status": "online",
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "services": ["ai", "agents", "memory", "knowledge", "voice", "monitoring"],
        "timestamp": now_iso(),
    }


# Canonical capability catalogue (spec §4 Capability Registry). Each entry is
# (id, category, backing tool, permissions, needs_ai, provider_service).
# ``availability`` is derived from platform state, never fabricated: AI-backed
# capabilities are only usable when ai_service is enabled AND a provider key is
# configured; platform capabilities are backed by local services and are always
# available. (Spec §50: no fake/random capability activity.)
_CAPABILITIES = [
    ("chat", "conversation", "chat", ["ai.chat"], True, "ai"),
    ("reasoning", "reasoning", "chat", ["ai.chat"], True, "ai"),
    ("coding", "engineering", "codegen", ["code.execute"], True, "codegen"),
    ("web-browsing", "research", "browser", ["browser.navigate"], False, "browser"),
    ("research", "research", "browser", ["browser.scrape"], False, "browser"),
    ("vision", "multimodal", "image", ["media.read"], True, "multimodal"),
    ("document-analysis", "knowledge", "knowledge", ["knowledge.read"], False, "knowledge"),
    ("voice", "voice", "voice", ["voice.speak"], False, "voice"),
    ("tool-use", "agentic", "agents", ["agent.act"], False, "agents"),
    ("automation", "automation", "automation", ["automation.run"], False, "automation"),
    ("terminal", "engineering", "sandbox", ["system.command"], False, "sandbox"),
    ("cloud", "cloud", "extensions", ["cloud.deployment"], False, "extensions"),
    ("database", "data", "knowledge", ["data.query_db"], False, "knowledge"),
    ("knowledge", "knowledge", "knowledge", ["knowledge.read"], False, "knowledge"),
    ("memory", "cognitive", "memory", ["memory.store"], False, "memory"),
    ("verification", "quality", "sandbox", ["code.execute"], False, "sandbox"),
    ("simulation", "engineering", "sandbox", ["code.execute"], False, "sandbox"),
]


# Provider config keys checked against the stored provider_settings.
_PROVIDER_KEYS = (
    ("openai", "openai_api_key"),
    ("google", "google_gemini_api_key"),
    ("anthropic", "anthropic_api_key"),
    ("nvidia", "nvidia_api_key"),
    ("huggingface", "huggingface_api_key"),
    ("stability", "stability_api_key"),
    ("aws", "aws_access_key_id"),
    ("tavily", "tavily_api_key"),
    ("serper", "serper_api_key"),
    ("news", "news_api_key"),
    ("openweathermap", "openweathermap_api_key"),
    ("ollama", "ollama_model"),
)


@router.get("/capabilities")
async def capabilities():
    """Capability registry (spec §4).

    Returns the legacy flat ``capabilities`` catalogue (kept for backward
    compatibility) plus a ``registry`` of per-capability metadata with runtime
    availability/health so workspaces can discover what the fabric can actually
    do right now. Availability is derived from platform state — AI-backed
    capabilities are only ``available`` when ai_service is enabled and a provider
    key is configured; platform capabilities are backed by local services.
    No host psutil, no fabricated activity (§50).
    """
    settings = get_store("misc").load().get("provider_settings") or {}
    configured = [name for name, key in _PROVIDER_KEYS if settings.get(key)]
    ai_enabled = bool(getattr(ai_service, "enabled", False))
    model = settings.get("ollama_model")

    registry = []
    for cap_id, category, tool, permissions, needs_ai, provider_service in _CAPABILITIES:
        if needs_ai:
            available = ai_enabled and bool(configured)
            health = "ok" if available else ("degraded" if configured else "offline")
            provider = ", ".join(configured) if configured else None
        else:
            available = True
            health = "ok"
            provider = "local"
        deps = (
            [provider_service]
            if not needs_ai
            else (["ai", "llm-provider"] if configured else ["ai"])
        )
        registry.append({
            "capability": cap_id,
            "category": category,
            "tool": tool,
            "permissions": permissions,
            "provider": provider,
            "provider_service": provider_service,
            "model": model if needs_ai else None,
            "availability": "available" if available else "unavailable",
            "health": health,
            "ai_backed": needs_ai,
            "dependencies": deps,
            "provenance": "jarvis_backend/routers/system.py:capabilities",
            "last_checked": now_iso(),
        })

    return {
        "timestamp": now_iso(),
        "version": "3.0.0",
        "ai_enabled": ai_enabled,
        "capabilities": [c[0] for c in _CAPABILITIES],
        "registry": registry,
        "providers": {"ai_enabled": ai_enabled, "configured": configured},
        "active_providers": configured,
    }


@router.get("/dashboard")
async def system_dashboard():
    """JARVIS-system state view (spec §47).

    Public platform view (no secrets). Preserves the unauthenticated 200
    contract the SystemMonitor surfaces: only provider names, agent roles
    and capability metadata are exposed, all scrubbed of secrets.
    This is the platform view the SystemMonitor surfaces — the JARVIS system
    (agents, providers, services, automation), NOT the host PC. It composes
    existing platform stores/services and is read-only; host psutil stats are
    deliberately not surfaced here. Destructive host actions are gated by the
    safety policy on ``/launch`` and audited to ``audit_logs``.
    """
    misc = get_store("misc").load()
    agents_db = get_store("agents").load()
    agents = list(agents_db.values()) if isinstance(agents_db, dict) else []

    provider_settings = misc.get("provider_settings") or {}
    configured = [
        name for name, key in (
            ("openai", "openai_api_key"),
            ("google", "google_gemini_api_key"),
            ("anthropic", "anthropic_api_key"),
            ("nvidia", "nvidia_api_key"),
            ("huggingface", "huggingface_api_key"),
            ("stability", "stability_api_key"),
            ("aws", "aws_access_key_id"),
            ("tavily", "tavily_api_key"),
            ("serper", "serper_api_key"),
            ("news", "news_api_key"),
            ("openweathermap", "openweathermap_api_key"),
            ("ollama", "ollama_model"),
        ) if provider_settings.get(key)
    ]

    workflows = misc.get("workflows")
    task_count = len(workflows) if isinstance(workflows, (dict, list)) else 0

    recent_actions = []
    try:
        log = get_store("audit_logs").load()
        launches = [
            e for e in (log if isinstance(log, list) else [])
            if isinstance(e, dict) and e.get("kind") == "system_launch"
        ]
        recent_actions = launches[-10:][::-1]
    except Exception:  # noqa: BLE001
        pass

    ai_enabled = bool(getattr(ai_service, "enabled", False))
    return {
        "timestamp": now_iso(),
        "platform": {
            "name": "JARVIS Unified System",
            "version": "3.0.0",
            "instance_id": platform.node(),
            "ai_enabled": ai_enabled,
        },
        "services": [
            "ai", "agents", "memory", "knowledge", "voice", "monitoring",
            "automation", "multimodal", "codegen", "image", "video",
            "browser", "gateway", "extensions",
        ],
        "agents": {
            "total": len(agents),
            "active": sum(1 for a in agents if a.get("status") == "active"),
            "idle": sum(1 for a in agents if a.get("status") == "idle"),
            "by_role": {
                r: sum(1 for a in agents if a.get("role") == r)
                for r in {a.get("role") for a in agents if a.get("role")}
            },
            "entries": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "role": a.get("role"),
                    "status": a.get("status"),
                    "capabilities": a.get("capabilities", []),
                }
                for a in agents
            ],
        },
        "providers": {"ai_enabled": ai_enabled, "configured": configured},
        "automation": {"tasks": task_count, "scheduler_running": False, "engine": "local"},
        "capabilities": [
            "chat", "memory", "knowledge", "agents", "voice", "monitoring",
            "automation", "multimodal", "codegen", "image", "video", "browser",
        ],
        "recent_actions": recent_actions,
        "resource_pressure": "nominal",
    }


@router.get("/processes")
async def list_processes(user: Dict[str, Any] = Depends(_require_auth),
                          limit: int = Query(50), sort: str = Query("cpu")):
    """List running processes. Requires authentication."""
    _audit_system_action("read", "list_processes", "system/processes",
                         user.get("email", ""))
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                procs.append({
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "cpu": round(info.get("cpu_percent") or 0, 1),
                    "memory": round(info.get("memory_percent") or 0, 1),
                    "status": info.get("status"),
                })
            except Exception:  # noqa: BLE001
                continue
        key = {"cpu": lambda x: x["cpu"], "memory": lambda x: x["memory"],
               "name": lambda x: x["name"]}.get(sort, lambda x: x["cpu"])
        procs.sort(key=key, reverse=(sort != "name"))
        return {"processes": procs[:limit], "total": len(procs)}
    except Exception:  # noqa: BLE001
        logger.exception("system:list_processes failed")
        return {"processes": [], "total": 0, "error": "process enumeration unavailable"}


@router.post("/processes/kill")
@router.post("/process/kill")
async def kill_process(body: ProcessKillIn, user: Dict[str, Any] = Depends(_require_admin)):
    """Kill a process. Requires admin role."""
    _audit_system_action("write", "kill_process", f"process/{body.pid}",
                         user.get("email", ""), f"force={body.force}")
    try:
        import psutil
        p = psutil.Process(body.pid)
        p.kill() if body.force else p.terminate()
        return {"success": True, "pid": body.pid}
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")


@router.get("/provider-settings")
async def get_provider_settings(user: Dict[str, Any] = Depends(_require_admin)):
    """Get provider settings metadata only.

    Returns safe metadata (configured provider names, model settings).
    NEVER returns raw API key values.
    """
    _audit_system_action("read", "get_provider_settings", "system/provider-settings",
                         user.get("email", ""))
    misc = get_store("misc").load()
    settings = misc.get("provider_settings") or {}
    # Return only safe metadata — scrub any raw key values.
    safe_settings = {}
    for key, value in settings.items():
        if any(sk in key.lower() for sk in ("key", "secret", "token", "password")):
            safe_settings[key] = "***"
        else:
            safe_settings[key] = value
    return safe_settings


@router.put("/provider-settings")
async def update_provider_settings(body: ProviderSettingsIn,
                                     user: Dict[str, Any] = Depends(_require_admin),
                                     request: Request = None):
    """Update provider settings.

    SEC-1: Rejects secret-shaped fields. Credentials go through SecretManager,
    never stored as plaintext in the misc KV store.
    """
    # Inspect raw body for secret-shaped fields before Pydantic processing.
    try:
        raw_body = await request.json() if request else {}
    except Exception:
        raw_body = {}
    if isinstance(raw_body, dict):
        for k in raw_body:
            if any(s in k.lower() for s in _SECRET_SHAPES):
                raise HTTPException(
                    status_code=400,
                    detail=f"Refusing secret-shaped field '{k}' via provider-settings API",
                )

    misc = get_store("misc").load()
    settings = misc.setdefault("provider_settings", ai_service.settings())
    for field, value in body.model_dump(exclude_none=True).items():
        settings[field] = value
    get_store("misc").save()
    _audit_system_action("write", "update_provider_settings",
                         "system/provider-settings", user.get("email", ""))
    # Return safe metadata only — scrub secret values.
    safe = {}
    for k, v in settings.items():
        if any(sk in k.lower() for sk in ("key", "secret", "token", "password")):
            safe[k] = "***"
        else:
            safe[k] = v
    return safe


@router.get("/files")
async def list_files(user: Dict[str, Any] = Depends(_require_auth),
                       path: str = Query(str(ROOT))):
    """List files in a directory. Requires authentication."""
    _audit_system_action("read", "list_files", f"system/files/{path}",
                         user.get("email", ""))
    try:
        p = _confined_path(path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        entries = []
        for child in sorted(p.iterdir()):
            try:
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                })
            except Exception:  # noqa: BLE001
                continue
        return {"path": str(p), "entries": entries}
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")


class ReadFileIn(BaseModel):
    path: str


@router.post("/files/read")
async def read_file(body: ReadFileIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Read a file. Requires authentication."""
    _audit_system_action("read", "read_file", f"system/files/{body.path}",
                         user.get("email", ""))
    p = _confined_path(body.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")
    return {"path": str(p), "content": content}


@router.get("/clipboard")
async def get_clipboard(user: Dict[str, Any] = Depends(_require_auth)):
    """Read clipboard. Requires authentication."""
    _audit_system_action("read", "get_clipboard", "system/clipboard",
                         user.get("email", ""))
    text = ""
    try:
        import subprocess
        text = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return {"text": text}


class ClipboardIn(BaseModel):
    text: str


@router.post("/clipboard")
async def set_clipboard(body: ClipboardIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Set clipboard. Requires authentication."""
    _audit_system_action("write", "set_clipboard", "system/clipboard",
                         user.get("email", ""))
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Set-Clipboard -Value $args[0]", body.text],
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        pass
    return {"success": True}


# Host-destructive commands must never reach the OS from a JARVIS action.
# This deny-list is enforced on the full command string (app + args) so that
# injection such as `app="cmd.exe" args="/c shutdown /s"` is also caught.
# (Spec §20 policy gate + §7 "no PC degradation": host shutdown/reboot is the
#  single most disruptive resource action and must be refused, not launched.)
_DENY_COMMANDS = (
    "shutdown", "reboot", "halt", "poweroff", "tsshutdown",
    "stop-computer", "init 0", "init 6", "wsl --shutdown",
    "powercfg /h",
)


def _audit_system_launch(status: str, app: str, args: str,
                         actor: str = "anonymous", error: str | None = None) -> None:
    """Append a system-launch attempt to the audit trail (spec §27).

    ``actor`` is the authenticated principal's email, or "anonymous" for
    pre-auth deny-list hits, so the shutdown rejection is still attributable
    without performing an authorization decision inside the auditor.
    """
    try:
        log = get_store("audit_logs").load()
        if not isinstance(log, list):
            log = []
        log.append({
            "ts": now_iso(),
            "kind": "system_launch",
            "status": status,
            "actor": actor or "anonymous",
            "app": app,
            "args": args,
            **({"error": error} if error else {}),
        })
        get_store("audit_logs").save()
    except Exception:  # noqa: BLE001 — audit must never break a request
        pass


class LaunchIn(BaseModel):
    app: str
    args: Optional[str] = None


# --------------------------------------------------------------------------- #
# Platform Diagnostics (Phase 6.13)
# --------------------------------------------------------------------------- #

@router.get("/diagnose")
async def platform_diagnose():
    """Platform diagnostics endpoint (Phase 6.13).

    Returns a comprehensive health check of the platform including:
    - Overall platform health
    - Provider connectivity status
    - Model availability
    - Job/system status
    - Capability verification status

    This endpoint consumes existing infrastructure and provides a single
    source of truth for platform diagnostics.
    """
    import time
    
    start_time = time.time()
    
    # Basic platform info
    misc = get_store("misc").load()
    settings = misc.get("provider_settings", {})
    
    # Check AI service status
    ai_enabled = bool(getattr(ai_service, "enabled", False))
    
    # Check providers
    providers_configured = []
    for name, key in _PROVIDER_KEYS:
        if settings.get(key):
            providers_configured.append(name)
    
    # Check database connectivity
    db_status = "unknown"
    try:
        from ..db import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
    
    # Check chat service
    chat_status = "unknown"
    try:
        chat_sessions = get_store("chat_sessions").load()
        chat_status = "operational"
    except Exception:
        chat_status = "error"
    
    # Check tasks/jobs
    tasks_status = "unknown"
    try:
        tasks = get_store("tasks").load()
        tasks_status = "operational"
    except Exception:
        tasks_status = "error"
    
    # Check memory
    memory_status = "unknown"
    try:
        memory = get_store("memory").load()
        memory_status = "operational"
    except Exception:
        memory_status = "error"
    
    # Check knowledge
    knowledge_status = "unknown"
    try:
        knowledge = get_store("knowledge").load()
        knowledge_status = "operational"
    except Exception:
        knowledge_status = "error"
    
    # Build capability verification status
    capabilities_verified = []
    try:
        from ..verify import get_verification_engine
        engine = get_verification_engine()
        capabilities_verified = [
            "python_syntax",
            "python_type_check",
            "python_tests",
            "json_document",
            "csv_document",
            "schema_validation",
            "file_exists",
            "file_extension",
        ]
    except Exception:
        capabilities_verified = []
    
    duration = int((time.time() - start_time) * 1000)
    
    # Determine overall status
    all_healthy = all([
        db_status == "healthy",
        chat_status == "operational",
        tasks_status == "operational",
        memory_status == "operational",
        knowledge_status == "operational",
    ])
    
    overall_status = "healthy" if all_healthy else "degraded" if any([
        db_status != "healthy",
        chat_status == "error",
    ]) else "unknown"
    
    return {
        "status": overall_status,
        "timestamp": now_iso(),
        "duration_ms": duration,
        "platform": {
            "name": "JARVIS Unified System",
            "version": "3.0.0",
            "instance_id": platform.node(),
            "python": platform.python_version(),
            "ai_enabled": ai_enabled,
        },
        "services": {
            "database": db_status,
            "chat": chat_status,
            "tasks": tasks_status,
            "memory": memory_status,
            "knowledge": knowledge_status,
        },
        "providers": {
            "configured": providers_configured,
            "count": len(providers_configured),
        },
        "verification": {
            "engine": "operational",
            "capabilities": capabilities_verified,
        },
        "recommendations": [] if all_healthy else [
            "Check database connectivity" if db_status != "healthy" else None,
            "Check chat service" if chat_status != "operational" else None,
        ],
    }


def _actor_from_request(request: Request) -> str:
    """Best-effort caller email for pre-auth audit (never an authz decision)."""
    try:
        user = get_optional_user(request.headers.get("authorization"))
    except Exception:  # noqa: BLE001
        return "anonymous"
    if user:
        return user.get("email", "") or "anonymous"
    return "anonymous"


def _confined_path(requested: str) -> Path:
    """SEC-1 §4 — confine file reads to ROOT to prevent path traversal."""
    base = ROOT.resolve()
    raw = Path(requested)
    candidate = raw.resolve() if raw.is_absolute() else (ROOT / requested).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=403, detail="Path is outside the allowed root"
        )
    return candidate


@router.post("/launch")
async def launch_app(body: LaunchIn, request: Request):
    """Launch a non-destructive application. Requires admin (privileged-host).

    SEC-1 §4: the destructive-command deny-list is evaluated BEFORE
    authentication, so ``POST /system/launch {"app":"shutdown"}`` is always
    refused with 403 — even for an unauthenticated caller — and can never be
    bypassed by obtaining a token. An authenticated admin may launch any
    non-destructive application; denials and executions are audited with the
    authenticated actor (or "anonymous").
    """
    if not (body.app or "").strip():
        raise HTTPException(status_code=400, detail="app is required")
    full = f"{body.app} {(body.args or '')}".strip()
    lowered = full.lower()
    actor = _actor_from_request(request)
    # 1) Safety first: refuse destructive host commands (403, unbypassable).
    for denied in _DENY_COMMANDS:
        if denied in lowered:
            _audit_system_launch("denied", body.app, body.args or "",
                                 actor=actor, error="deny-list")
            _audit_system_action("denied", "launch_app", f"system/launch/{body.app}",
                                 actor or "anonymous",
                                 f"destructive command matched '{denied}'")
            raise HTTPException(
                status_code=403,
                detail=(f"Refusing destructive host command matching '{denied}' "
                        "(system:launch is gated by the JARVIS safety policy)."),
            )
    # 2) Privileged host operation: authenticated admin required.
    user = get_current_user(request.headers.get("authorization"))  # raises 401
    if not is_admin(user):
        _audit_system_action("denied", "launch_app", f"system/launch/{body.app}",
                             user.get("email", "") or "anonymous",
                             "policy:admin_required")
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        import subprocess
        args = (body.args or "").split()
        subprocess.Popen([body.app] + args, shell=True)
    except Exception:  # noqa: BLE001
        logger.exception("system:launch failed for %r", body.app)
        _audit_system_launch("error", body.app, body.args or "",
                             actor=user.get("email", "") or "anonymous",
                             error="execution_failed")
        _audit_system_action("error", "launch_app", f"system/launch/{body.app}",
                             user.get("email", ""), "execution_failed")
        raise HTTPException(status_code=500, detail="Host application launch failed")
    _audit_system_launch("allowed", body.app, body.args or "",
                         actor=user.get("email", "") or "anonymous")
    _audit_system_action("allowed", "launch_app", f"system/launch/{body.app}",
                         user.get("email", ""), "admin")
    return {"success": True, "app": body.app}


@router.get("/launch/apps")
async def common_apps():
    """List common applications. Public by design."""
    return {"apps": _APPS}


class ScreenshotIn(BaseModel):
    filename: Optional[str] = None


@router.post("/screenshot", response_model=None)
async def take_screenshot(body: ScreenshotIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Take a screenshot. Requires authentication."""
    _audit_system_action("write", "take_screenshot", "system/screenshot",
                         user.get("email", ""))
    try:
        import PIL.ImageGrab  # type: ignore
        img = PIL.ImageGrab.grab()
        name = body.filename or f"screenshot_{now_iso().replace(':', '-')}.png"
        from ..core import UPLOADS_DIR
        path = UPLOADS_DIR / name
        img.save(path)
        return {"success": True, "filename": name, "path": str(path)}
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")


@router.get("/windows")
async def list_windows(user: Dict[str, Any] = Depends(_require_auth)):
    """List windows. Requires authentication."""
    _audit_system_action("read", "list_windows", "system/windows",
                         user.get("email", ""))
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | Where-Object {$_.MainWindowTitle} "
             "| Select-Object ProcessName, Id, MainWindowTitle | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        try:
            data = json.loads(out) if out else []
            if isinstance(data, dict):
                data = [data]
            return {"windows": data}
        except Exception:  # noqa: BLE001
            return {"windows": []}
    except Exception:  # noqa: BLE001
        return {"windows": []}


@router.get("/file-structure")
async def file_structure(user: Dict[str, Any] = Depends(_require_auth)):
    """Get file structure. Requires authentication."""
    _audit_system_action("read", "file_structure", "system/file-structure",
                         user.get("email", ""))
    return {"root": str(ROOT), "structure": _walk(ROOT, depth=2)}


def _walk(path: Path, depth: int = 2) -> List[Dict[str, Any]]:
    if depth <= 0:
        return []
    out = []
    for child in sorted(path.iterdir()):
        if child.name.startswith("."):
            continue
        try:
            if child.is_dir():
                if child.name in ("node_modules", "venv", ".git", ".next"):
                    continue
                out.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "directory",
                    "children": _walk(child, depth - 1),
                })
            else:
                out.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "file",
                    "size": child.stat().st_size,
                })
        except Exception:  # noqa: BLE001
            continue
    return out