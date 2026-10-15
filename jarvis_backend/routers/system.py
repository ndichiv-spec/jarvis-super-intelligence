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
import socket
import time
from typing import Any, Dict, List, Optional
from pathlib import Path, PureWindowsPath
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..core import (
    ROOT, ai_service, get_store, now_iso, get_current_user,
    get_optional_user, is_admin, is_owner,
    _require_auth, _require_admin, _require_owner, _audit_system_action,
)
from ..capability import get_orchestrator as get_cap_orchestrator
from ..platform_identity import get_platform_identity
from ..gateway import _load_silverwing, _silverwing_endpoint, _jarvis_brain_endpoint

logger = logging.getLogger("jarvis.backend.system")

# P0 /system/* contract: real uptime accounting. ``core.py`` owns no startup
# hook, so uptime is tracked here. ``resource`` is unavailable on Windows, so
# memory is measured via psutil (real RSS bytes) with a hard 0 fallback; CPU
# usage is intentionally not sampled during a status probe (a blocking
# psutil.cpu_percent call returns 0.0 on first read with no warmup baseline).
_BACKEND_START = time.time()


def _utc_iso(epoch: float) -> str:
    """ISO-8601 UTC with a trailing ``Z`` (matches ``core.now_iso``)."""
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return now_iso()


def _mem_usage_bytes() -> int:
    """Real process RSS in bytes via psutil; 0 if not measurable."""
    try:
        import psutil  # local import: optional dependency, never blocks startup
        return int(psutil.Process().memory_info().rss)
    except Exception:  # noqa: BLE001 — must never break a status probe
        return 0


def _active_connections() -> int:
    """Real count of tracked chat sessions (0 if unavailable)."""
    try:
        store = get_store("chat_sessions").load()
        return len(store) if store is not None else 0
    except Exception:  # noqa: BLE001
        return 0


router = APIRouter(
    prefix="/api/v1/system",
    tags=["system"],
    dependencies=[Depends(_require_admin)],
)


class ProcessKillIn(BaseModel):
    pid: int
    force: bool = False


class ProviderSettingsIn(BaseModel):
    # Canonical field set mirrors frontend ``ProviderSettings`` (spec §58).
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    huggingface_api_key: Optional[str] = None
    stability_api_key: Optional[str] = None
    replicate_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    tavily_api_key: Optional[str] = None
    serper_api_key: Optional[str] = None
    news_api_key: Optional[str] = None
    openweathermap_api_key: Optional[str] = None


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


def _endpoint_reachable(endpoint: str, timeout: float = 2.0) -> bool:
    """Real TCP liveness probe for an HTTP(S) endpoint.

    Returns True only if an actual socket connection succeeds — never an
    assumption based on whether a URL is configured.
    """
    if not endpoint:
        return False
    from urllib.parse import urlparse as _urlparse
    parsed = _urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _mask_url(url: str) -> str:
    """Mask userinfo credentials in a URL for safe display (SEC-1)."""
    if not url or "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"


@router.get("/status")
async def system_status():
    return {
        "status": "online",
        "version": get_platform_identity().get("version", "3.0.0"),
        "uptime": round(time.time() - _BACKEND_START, 3),
        "start_time": _utc_iso(_BACKEND_START),
        "active_engines": ["ai", "agents", "memory", "knowledge", "voice", "monitoring"],
        "active_connections": _active_connections(),
        "memory_usage": _mem_usage_bytes(),
        "cpu_usage": 0.0,
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "services": ["ai", "agents", "memory", "knowledge", "voice", "monitoring"],
        "timestamp": now_iso(),
        "capabilities": get_cap_orchestrator().get_all_status(),
    }


@router.get("/identity")
async def platform_identity():
    """Real platform identity (spec §12/13).

    Returns live Git repository state, version metadata for backend/frontend/
    Silverwing, active model/provider, and service paths.  All values come
    from real sources — no hardcoded values.
    """
    return get_platform_identity()


# ============================================
# Live Model Registry (Phase F)
# ============================================

_MODEL_CATALOG = [
    {"model_id": "gpt-4o", "provider": "openai", "category": "chat", "max_tokens": 16384},
    {"model_id": "gpt-4o-mini", "provider": "openai", "category": "chat", "max_tokens": 16384},
    {"model_id": "gpt-3.5-turbo", "provider": "openai", "category": "chat", "max_tokens": 4096},
    {"model_id": "gpt-4", "provider": "openai", "category": "chat", "max_tokens": 8192},
    {"model_id": "gpt-4-turbo", "provider": "openai", "category": "chat", "max_tokens": 16384},
    {"model_id": "gpt-4o-audio-preview", "provider": "openai", "category": "audio", "max_tokens": 16384},
    {"model_id": "text-embedding-3-small", "provider": "openai", "category": "embedding", "max_tokens": 8191},
    {"model_id": "text-embedding-3-large", "provider": "openai", "category": "embedding", "max_tokens": 8191},
    {"model_id": "dall-e-3", "provider": "openai", "category": "image", "max_tokens": 1024},
    {"model_id": "gemini-2.0-flash", "provider": "google", "category": "chat", "max_tokens": 1000000},
    {"model_id": "gemini-2.0-pro", "provider": "google", "category": "chat", "max_tokens": 2000000},
    {"model_id": "gemini-1.5-flash", "provider": "google", "category": "chat", "max_tokens": 1000000},
    {"model_id": "gemini-1.5-pro", "provider": "google", "category": "chat", "max_tokens": 2000000},
    {"model_id": "gemini-pro-vision", "provider": "google", "category": "vision", "max_tokens": 1000000},
    {"model_id": "text-embedding-004", "provider": "google", "category": "embedding", "max_tokens": 2048},
    {"model_id": "claude-3-sonnet-20240229", "provider": "anthropic", "category": "chat", "max_tokens": 200000},
    {"model_id": "claude-3-opus-20240229", "provider": "anthropic", "category": "chat", "max_tokens": 200000},
    {"model_id": "claude-3-haiku-20240307", "provider": "anthropic", "category": "chat", "max_tokens": 200000},
    {"model_id": "claude-3-5-sonnet-20241022", "provider": "anthropic", "category": "chat", "max_tokens": 200000},
    {"model_id": "nvidia-llama-3.1-70b", "provider": "nvidia", "category": "chat", "max_tokens": 131072},
    {"model_id": "nvidia-llama-3.1-8b", "provider": "nvidia", "category": "chat", "max_tokens": 131072},
    {"model_id": "nvidia-nemotron-4-340b", "provider": "nvidia", "category": "chat", "max_tokens": 131072},
    {"model_id": "nvidia-nv-embedqa-e5-v5", "provider": "nvidia", "category": "embedding", "max_tokens": 4096},
    {"model_id": "nvidia-llamavision-2.0", "provider": "nvidia", "category": "vision", "max_tokens": 32768},
    {"model_id": "llama-3.3-70b-instruct", "provider": "huggingface", "category": "chat", "max_tokens": 131072},
    {"model_id": "Qwen2.5-72B-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 131072},
    {"model_id": "Qwen2.5-7B-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 32768},
    {"model_id": "Qwen2.5-3B-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 32768},
    {"model_id": "Qwen2.5-1.5B-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 32768},
    {"model_id": "Qwen2.5-0.5B-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 32768},
    {"model_id": "qwen2.5-vl-72b", "provider": "huggingface", "category": "vision", "max_tokens": 131072},
    {"model_id": "qwen2.5-vl-7b", "provider": "huggingface", "category": "vision", "max_tokens": 32768},
    {"model_id": "all-MiniLM-L6-v2", "provider": "huggingface", "category": "embedding", "max_tokens": 512},
    {"model_id": "all-mpnet-base-v2", "provider": "huggingface", "category": "embedding", "max_tokens": 512},
    {"model_id": "stabilityai/stable-diffusion-xl-base-1024-v1.0", "provider": "stability", "category": "image", "max_tokens": 1024},
    {"model_id": "stabilityai/sdxl-artist-1024", "provider": "stability", "category": "image", "max_tokens": 1024},
    {"model_id": "stable-diffusion-xl-base-1024-v1-0", "provider": "stability", "category": "image", "max_tokens": 1024},
    {"model_id": "stable-diffusion-v1-5", "provider": "stability", "category": "image", "max_tokens": 512},
    {"model_id": "stable-diffusion-21-base", "provider": "stability", "category": "image", "max_tokens": 512},
    {"model_id": "amazon.nova-pro-v1:0", "provider": "aws", "category": "chat", "max_tokens": 300000},
    {"model_id": "amazon.nova-lite-v1:0", "provider": "aws", "category": "chat", "max_tokens": 300000},
    {"model_id": "amazon.nova-micro-v1:0", "provider": "aws", "category": "chat", "max_tokens": 300000},
    {"model_id": "amazon.titan-text-vite-v1:0", "provider": "aws", "category": "chat", "max_tokens": 4000},
    {"model_id": "amazon.titan-embed-text-v2:0", "provider": "aws", "category": "embedding", "max_tokens": 512},
    {"model_id": "mistralai/Mistral-7B-Instruct-v0.3", "provider": "huggingface", "category": "chat", "max_tokens": 32768},
    {"model_id": "mistralai/Mixtral-8x22B-Instruct-v0.1", "provider": "huggingface", "category": "chat", "max_tokens": 131072},
    {"model_id": "mistralai/Mistral-Large-2-Instruct", "provider": "huggingface", "category": "chat", "max_tokens": 131072},
    {"model_id": "mistralai/pokemon-codellama", "provider": "huggingface", "category": "code", "max_tokens": 4096},
    {"model_id": "codellama/CodeLlama-70b-Instruct-hf", "provider": "huggingface", "category": "code", "max_tokens": 4096},
    {"model_id": "codellama/CodeLlama-13b-Instruct-hf", "provider": "huggingface", "category": "code", "max_tokens": 4096},
    {"model_id": "star-coder2", "provider": "huggingface", "category": "code", "max_tokens": 16384},
    {"model_id": "silverwing-120m-base-v1", "provider": "silverwing", "category": "chat", "max_tokens": 4096},
    {"model_id": "jarvis-brain-qwen3-4b-sft-v1", "provider": "jarvis-brain", "category": "chat", "max_tokens": 16384},
]


@router.get("/models")
async def models():
    """Live model catalog + provider availability (Phase F, spec §8).

    Returns the canonical 53-entry model catalog merged with live provider
    availability from the Silverwing ``ModelManager`` ``auth_status()`` and
    real reachability probes for Silverwing / JARVIS Brain endpoints.
    Availability is measured, never assumed.
    """
    # Build provider availability from live state.
    provider_availability: Dict[str, Dict[str, Any]] = {}

    # Silverwing ModelManager auth status.
    try:
        sw = _load_silverwing()
        if sw is not None:
            mgr = sw.ModelManager()
            status = mgr.auth_status()
            for name, info in status.get("providers", {}).items():
                provider_availability[name] = {
                    "available": info.get("available", False),
                    "authorized": info.get("authorized", False),
                    "configured": info.get("available", False),
                    "model": info.get("model"),
                    "models": [m.model_id for m in sw.list_by_provider(name)] if hasattr(sw, "list_by_provider") else [],
                    "last_checked": now_iso(),
                }
    except Exception:
        pass

    # Live reachability probes for Silverwing and JARVIS Brain.
    sw_ep = _silverwing_endpoint()
    brain_ep = _jarvis_brain_endpoint()
    if sw_ep:
        import asyncio
        sw_up = await asyncio.to_thread(_endpoint_reachable, sw_ep)
        provider_availability.setdefault("silverwing", {})
        provider_availability["silverwing"].update({
            "available": sw_up,
            "authorized": sw_up,
            "configured": True,
            "endpoint": sw_ep,
            "status": "healthy" if sw_up else "unreachable",
            "last_checked": now_iso(),
            "errors": None if sw_up else "runtime not reachable",
        })
    if brain_ep:
        import asyncio
        brain_up = await asyncio.to_thread(_endpoint_reachable, brain_ep)
        provider_availability.setdefault("jarvis-brain", {})
        provider_availability["jarvis-brain"].update({
            "available": brain_up,
            "authorized": brain_up,
            "configured": True,
            "endpoint": brain_ep,
            "status": "healthy" if brain_up else "unreachable",
            "last_checked": now_iso(),
            "errors": None if brain_up else "endpoint not reachable",
        })

    # Annotate each catalog entry with live availability derived from config keys.
    misc = get_store("misc").load()
    settings = misc.get("provider_settings") or {}
    configured_names = [name for _shape, (name, key) in (
        ("key", ("openai", "openai_api_key")),
        ("key", ("google", "google_gemini_api_key")),
        ("key", ("anthropic", "anthropic_api_key")),
        ("key", ("nvidia", "nvidia_api_key")),
        ("key", ("huggingface", "huggingface_api_key")),
        ("key", ("stability", "stability_api_key")),
        ("key", ("aws", "aws_access_key_id")),
    ) if settings.get(key)]

    annotated = []
    for entry in _MODEL_CATALOG:
        p = entry["provider"]
        prov = provider_availability.get(p, {})
        annotated.append({
            **entry,
            "available": prov.get("available", p in configured_names),
            "provider_available": prov.get("available", p in configured_names),
            "provider_authorized": prov.get("authorized", False),
            "provider_status": prov.get("status", "unavailable"),
        })

    active_model = settings.get("ollama_model")
    active_provider = "ollama" if active_model else None
    if not active_provider and sw_ep:
        active_provider = "silverwing"
        active_model = active_model or "silverwing-120m-base-v1"
    if not active_provider and brain_ep:
        active_provider = "jarvis-brain"
        active_model = active_model or "jarvis-brain-qwen3-4b-sft-v1"

    return {
        "timestamp": now_iso(),
        "total_models": len(annotated),
        "providers": provider_availability,
        "catalog": annotated,
        "active_model": active_model,
        "active_provider": active_provider,
        "provider_keys_configured": configured_names,
    }


@router.get("/services")
async def services():
    """Live service orchestration (Phase I, spec §40-43).

    Returns authoritative real-time state for each service in the platform:
    backend, silverwing-runtime, database, redis. All statuses are derived
    from live probes or real configuration — no fabricated values.
    """
    import os
    import socket
    import sqlite3

    services_state: Dict[str, Any] = {}

    # 1. Backend (this API server — if we reached this endpoint, it's up).
    services_state["backend"] = {
        "name": "jarvis-backend",
        "status": "healthy",
        "reachable": True,
        "details": None,
    }

    # 2. Silverwing runtime — reflect the real in-process integration.
    # silverwing-backend is mounted in-process under /silverwing in the
    # single-process deployment (verified by the mount flag); the standalone
    # SILVERWING_ENDPOINT runtime (e.g. :8010) is optional and not started here.
    # Probing only :8010 falsely reported Silverwing as unreachable while it is
    # in fact integrated and serving.
    import asyncio
    sw_ep = _silverwing_endpoint()
    sw_inproc_ok = False
    try:
        from ..main import _silverwing_app, _silverwing_error  # deferred: import cycle
        sw_inproc_ok = _silverwing_app is not None and _silverwing_error is None
    except Exception:
        sw_inproc_ok = False
    if sw_inproc_ok:
        services_state["silverwing-runtime"] = {
            "name": "silverwing-runtime",
            "status": "healthy",
            "reachable": True,
            "endpoint": "/silverwing (in-process mount on :8000)",
            "details": "Integrated in-process; standalone SILVERWING_ENDPOINT runtime not started",
        }
    elif sw_ep:
        sw_up = await asyncio.to_thread(_endpoint_reachable, sw_ep)
        services_state["silverwing-runtime"] = {
            "name": "silverwing-runtime",
            "status": "healthy" if sw_up else "unreachable",
            "reachable": sw_up,
            "endpoint": sw_ep,
            "details": None if sw_up else "Runtime not accepting connections",
        }
    else:
        services_state["silverwing-runtime"] = {
            "name": "silverwing-runtime",
            "status": "not_configured",
            "reachable": False,
            "endpoint": None,
            "details": "Silverwing not integrated and no SILVERWING_ENDPOINT configured",
        }

    # 3. JARVIS Brain — real TCP probe.
    brain_ep = _jarvis_brain_endpoint()
    if brain_ep:
        brain_up = await asyncio.to_thread(_endpoint_reachable, brain_ep)
        services_state["jarvis-brain"] = {
            "name": "jarvis-brain",
            "status": "healthy" if brain_up else "unreachable",
            "reachable": brain_up,
            "endpoint": brain_ep,
            "details": None if brain_up else "Endpoint not accepting connections",
        }
    else:
        services_state["jarvis-brain"] = {
            "name": "jarvis-brain",
            "status": "not_configured",
            "reachable": False,
            "endpoint": None,
            "details": "JARVIS_BRAIN_ENDPOINT not set",
        }

    # 4. Database — real liveness probe via the app's actual SQLAlchemy engine.
    # Honors DATABASE_URL (PostgreSQL in this deployment) and only falls back to
    # SQLite (jarvis_data/jarvis.db). Probing the engine verifies whichever
    # backend the app actually uses instead of a hardcoded path under the wrong
    # data_dir (ROOT/jarvis_backend/data/jarvis.db never matched the real store).
    _db_url = None
    try:
        from ..db import get_engine, database_url as _database_url
        from sqlalchemy import text as _sql_text

        _db_url = _database_url()
        with get_engine().connect() as _conn:
            _conn.execute(_sql_text("SELECT 1"))
        _db_kind = ("postgresql" if "postgres" in _db_url
                    else "sqlite" if "sqlite" in _db_url else "database")
        services_state["database"] = {
            "name": f"{_db_kind}-database",
            "status": "healthy",
            "reachable": True,
            "url": _mask_url(_db_url),
            "details": None,
        }
    except Exception as _e:
        services_state["database"] = {
            "name": "database",
            "status": "unreachable",
            "reachable": False,
            "url": _mask_url(_db_url) if _db_url else None,
            "details": f"Database probe failed: {type(_e).__name__}",
        }

    # 5. Redis — probe the configured URL; otherwise fall back to the default
    # localhost:6379. Redis is live in this environment even when no REDIS_URL
    # / REDIS_HOST is set, so a TCP liveness probe reflects reality instead of
    # misreporting a running cache as "not_configured".
    redis_url = os.environ.get("REDIS_URL", "").strip()
    redis_ep = os.environ.get("REDIS_HOST", "").strip()
    if redis_url:
        from urllib.parse import urlparse as _urlparse

        parsed = _urlparse(redis_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6379
    elif redis_ep:
        host = redis_ep
        port = 6379
    else:
        host = "127.0.0.1"
        port = 6379
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        services_state["redis"] = {
            "name": "redis-cache",
            "status": "healthy",
            "reachable": True,
            "host": host,
            "port": port,
            "details": None if (redis_url or redis_ep) else "reachable on localhost:6379 (REDIS_URL not set; not app-bound)",
        }
    except OSError:
        services_state["redis"] = {
            "name": "redis-cache",
            "status": "unreachable",
            "reachable": False,
            "host": host,
            "port": port,
            "details": "Redis not accepting connections",
        }

    overall = "degraded"
    if services_state["backend"]["status"] == "healthy":
        overall = "operational"
    for s in services_state.values():
        if s["status"] in ("unreachable", "error"):
            overall = "degraded"
            break

    return {
        "timestamp": now_iso(),
        "overall_status": overall,
        "services": services_state,
    }
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


# Canonical per-provider feature labels (spec §58). Used only to populate the
# scrubbed ``providers`` summary on ``/provider-settings`` — never exposes keys.
_PROVIDER_META = {
    "openai": {"label": "OpenAI", "features": ["chat", "embedding", "image", "audio"]},
    "google": {"label": "Google Gemini", "features": ["chat", "embedding", "vision"]},
    "anthropic": {"label": "Anthropic", "features": ["chat"]},
    "nvidia": {"label": "NVIDIA NIM", "features": ["chat", "embedding", "vision"]},
    "huggingface": {"label": "Hugging Face", "features": ["chat", "embedding", "vision", "code"]},
    "stability": {"label": "Stability AI", "features": ["image"]},
    "aws": {"label": "AWS", "features": ["chat", "embedding"]},
    "tavily": {"label": "Tavily", "features": ["search"]},
    "serper": {"label": "Serper", "features": ["search"]},
    "news": {"label": "NewsAPI", "features": ["news"]},
    "openweathermap": {"label": "OpenWeatherMap", "features": ["weather"]},
    "ollama": {"label": "Ollama", "features": ["chat", "embedding", "code", "vision"]},
}


def _provider_settings_response(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Build the scrubbed ProviderSettingsResponse envelope (spec §58).

    Emits the canonical 15 ProviderSettings keys so the UI always receives a
    complete shape; secret-shaped values are masked to ``None`` (credentials
    are never returned). ``providers`` carries real per-provider
    feature/config status derived from the stored (scrubbed) keys.
    """
    safe_settings: Dict[str, Any] = {}
    for key in ProviderSettingsIn.model_fields:
        raw = settings.get(key)
        if any(sk in key.lower() for sk in _SECRET_SHAPES):
            safe_settings[key] = None
        else:
            safe_settings[key] = raw

    providers: Dict[str, Any] = {}
    for name, pkey in _PROVIDER_KEYS:
        configured = bool(settings.get(pkey))
        meta = _PROVIDER_META.get(name, {"label": name, "features": []})
        providers[name] = {
            "label": meta["label"],
            "summary": "Configured" if configured else "Not configured",
            "features": meta["features"],
            "configured": configured,
        }

    env_path = str(ROOT / ".env")
    try:
        env_file_exists = (ROOT / ".env").exists()
    except Exception:  # noqa: BLE001
        env_file_exists = False

    return {
        "success": True,
        "settings": safe_settings,
        "providers": providers,
        "env_file_exists": env_file_exists,
        "env_path": env_path,
    }


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

    _ver = get_platform_identity().get("version", "3.0.0")
    try:
        _tier = int(str(_ver).split(".")[0])
    except (ValueError, TypeError):
        _tier = 3
    return {
        "timestamp": now_iso(),
        "version": _ver,
        "engines": sorted({c[5] for c in _CAPABILITIES}),
        "features": sorted({c[1] for c in _CAPABILITIES}),
        "tier_level": _tier,
        "ai_enabled": ai_enabled,
        "capabilities": [c[0] for c in _CAPABILITIES],
        "registry": registry,
        "providers": {"ai_enabled": ai_enabled, "configured": configured},
        "active_providers": configured,
        "live": {},
        "live_status": _live_capability_status(),
    }


@router.get("/capabilities/runtime")
async def capability_runtime(user: Dict[str, Any] = Depends(_require_auth)):
    """Live inventory from the registered capability runtime and its event bus."""
    from ..capability import get_registry

    registry = get_registry()
    tool_capability = registry.get("tool")
    if tool_capability is None:
        return {
            "status": "unavailable",
            "execution_supported": False,
            "tools": [],
            "events": [],
            "checked_at": now_iso(),
        }

    health = await tool_capability.health()
    health_by_tool = health.get("tools") or {}
    tools = []
    user_roles = user.get("roles") if isinstance(user.get("roles"), list) else []
    user_permissions = user.get("permissions") if isinstance(user.get("permissions"), list) else []
    effective_permissions = {permission for permission in user_permissions if isinstance(permission, str)}
    effective_permissions.add("tool.browser")
    is_admin_user = bool(user.get("is_admin")) or "admin" in user_roles
    for descriptor in await tool_capability.discover_actions():
        tool_id = descriptor["id"]
        tool_health = health_by_tool.get(tool_id) or {
            "status": "unavailable",
            "healthy": False,
            "error": "No health result was reported for this tool.",
        }
        raw_status = str(tool_health.get("status") or "unavailable").lower()
        if tool_health.get("healthy") and raw_status in {"ok", "available", "ready"}:
            status = "ready"
        elif raw_status in {"auth_required", "auth_failed", "unauthorized"}:
            status = "auth_required"
        elif raw_status in {"not_configured", "not_configured"}:
            status = "auth_required" if tool_id in {"github", "postgresql"} else "unavailable"
        elif raw_status in {"degraded", "rate_limited"}:
            status = "degraded"
        else:
            status = "unavailable" if raw_status in {"offline", "unavailable"} else "error"
        safe_health = {
            key: tool_health[key]
            for key in ("status", "healthy", "latency_ms", "last_checked", "tool_count",
                        "connected_servers", "registered_servers", "total_tools")
            if key in tool_health
        }
        safe_health["error"] = (
            None if tool_health.get("healthy") else
            "Authentication is required or was rejected."
            if status == "auth_required" else
            "The connection or health check failed."
        )
        if isinstance(tool_health.get("servers"), dict):
            safe_health["servers"] = {
                name: {
                    "connected": bool(server.get("connected")),
                    "status": server.get("status"),
                    "tool_count": server.get("tool_count", 0),
                    "tools": server.get("tools", []),
                }
                for name, server in tool_health["servers"].items()
            }
        actions = []
        for action in descriptor.get("actions", []):
            action_permissions = action.get("permissions") or []
            authorization_permissions = [
                permission for permission in action_permissions
                if permission != "confirmation"
            ]
            actions.append({
                **action,
                "authorized": is_admin_user or all(
                    permission in effective_permissions
                    for permission in authorization_permissions
                ),
                "requires_confirmation": "confirmation" in action_permissions,
            })
        tools.append({
            **descriptor,
            "actions": actions,
            "status": status,
            "connection": {
                "configured": raw_status not in {"not_configured", "unavailable", "offline"},
                "reachable": bool(tool_health.get("healthy")),
                "authenticated": status == "ready" and tool_id in {"github", "postgresql"},
            },
            "health": safe_health,
            "execution": {"supported": bool(descriptor.get("actions"))},
        })

    owner_id = str(user.get("id") or "")
    recent_events = []
    for event in registry.event_bus.get_events(limit=200):
        if event.get("user_id") != owner_id:
            continue
        payload = event.get("payload") or {}
        safe_payload = {
            key: payload[key]
            for key in ("action", "tool", "success", "error_type")
            if key in payload and isinstance(payload[key], (str, bool))
        }
        recent_events.append({
            "event_id": event.get("event_id"),
            "timestamp": event.get("timestamp"),
            "event_type": event.get("event_type"),
            "capability": event.get("capability"),
            "correlation_id": event.get("correlation_id"),
            "status": event.get("status"),
            "user_id": owner_id,
            "payload": safe_payload,
        })
    recent_events = recent_events[-50:]
    ready_tools = sum(1 for tool in tools if tool["status"] == "ready")
    if not tools:
        runtime_status = "unavailable"
    elif ready_tools == len(tools):
        runtime_status = "ready"
    elif ready_tools:
        runtime_status = "degraded"
    elif all(tool["status"] == "auth_required" for tool in tools):
        runtime_status = "auth_required"
    else:
        runtime_status = "unavailable"
    return {
        "status": runtime_status,
        "execution_supported": any(
            action.get("execution_supported")
            for tool in tools for action in tool.get("actions", [])
        ),
        "available_tool_count": ready_tools,
        "tool_count": len(tools),
        "tools": tools,
        "events": recent_events,
        "checked_at": now_iso(),
    }


@router.get("/readiness")
async def system_readiness(user: Dict[str, Any] = Depends(_require_auth)):
    """Report what the current runtime can actually use and what needs setup."""
    from ..connectors.dispatch import list_connectors

    items: List[Dict[str, Any]] = []

    try:
        graph_store = __import__(
            "jarvis_backend.agents.graph_store",
            fromlist=["AgentGraphStore"],
        ).AgentGraphStore.get_shared()
        graph_ready = graph_store._connected
        graph_detail = (
            "Agent graph connected"
            if graph_ready and graph_store._redis is not None
            else "Agent graph uses an in-memory fallback; graph data may not survive restart"
            if graph_ready
            else "Agent graph has not connected yet"
        )
        items.append({
            "id": "agent-graph",
            "name": "Agent orchestration",
            "status": "available" if graph_ready else "needs_setup",
            "detail": graph_detail,
            "action": "Open orchestration",
            "href": "/dashboard/agents",
        })
    except (ImportError, AttributeError):
        items.append({
            "id": "agent-graph",
            "name": "Agent orchestration",
            "status": "unavailable",
            "detail": "Agent graph runtime is not installed",
            "action": "View orchestration",
            "href": "/dashboard/agents",
        })

    items.extend([
        {
            "id": "browser-http",
            "name": "Browser page fetch",
            "status": "available",
            "detail": "Server-side page fetch and extraction are available; rendered pages use the user's browser iframe",
            "action": "Open browser",
            "href": "/dashboard/embedded-browser",
        },
        {
            "id": "browser-rendered",
            "name": "Rendered browser engines",
            "status": "needs_setup",
            "detail": "No local Chromium/Firefox/WebKit worker is registered; installing a browser package alone does not connect it to JARVIS",
            "action": "Review browser settings",
            "href": "/dashboard/settings",
        },
        {
            "id": "search-duckduckgo",
            "name": "DuckDuckGo web search",
            "status": "available",
            "detail": "DuckDuckGo results are integrated; Google and Bing are offered as external search pages",
            "action": "Open global search",
            "href": "/dashboard/search",
        },
    ])

    remote_enabled = os.environ.get("JARVIS_REMOTE_BROWSER_ENABLED", "false").lower() == "true"
    remote_url = os.environ.get("JARVIS_REMOTE_BROWSER_URL", "")
    items.append({
        "id": "browser-remote",
        "name": "Isolated remote browser worker",
        "status": "partial" if remote_enabled and remote_url else "needs_setup",
        "detail": "Worker endpoint is configured; health has not been verified"
        if remote_enabled and remote_url
        else "Configure JARVIS_REMOTE_BROWSER_ENABLED and JARVIS_REMOTE_BROWSER_URL to use a remote worker",
        "action": "Review browser settings",
        "href": "/dashboard/settings",
    })

    for connector in list_connectors(user_id=str(user.get("id") or "")):
        connection_status = connector.get("connection_status")
        configured = bool(connector.get("configured"))
        active = configured and connector.get("enabled") and connection_status == "Connected"
        items.append({
            "id": f"connector-{connector['kind']}",
            "name": connector.get("label") or connector["kind"],
            "status": "available" if active else "needs_consent" if configured else "needs_setup",
            "detail": (
                f"Connected{': ' + connector['account'] if connector.get('account') else ''}"
                if active
                else connection_status or "Configure provider credentials and consent before use"
            ),
            "action": "Manage connection",
            "href": "/dashboard/connections",
        })

    geocoder_configured = bool(os.environ.get("JARVIS_GEOCODER_URL"))
    geocoder_ready = geocoder_configured and bool(os.environ.get("JARVIS_GEOCODER_USER_AGENT"))
    routing_configured = bool(os.environ.get("JARVIS_ROUTING_URL"))
    items.extend([
        {
            "id": "theme-personalization",
            "name": "Theme personalization",
            "status": "available",
            "detail": "Manual themes are available; conversation mood auto-switching is opt-in",
            "action": "Open dashboard",
            "href": "/dashboard",
        },
        {
            "id": "notifications",
            "name": "System notifications",
            "status": "available",
            "detail": "Persistent, user-scoped notifications are recorded for agent task completion and OAuth connection events",
            "action": "View notifications",
            "href": "/dashboard",
        },
        {
            "id": "geography-map",
            "name": "Map display",
            "status": "partial",
            "detail": "OpenStreetMap embed is available; custom tile layers, including satellite imagery, are not rendered yet",
            "action": "Open map",
            "href": "/dashboard/geography",
        },
        {
            "id": "geography-geocoder",
            "name": "Place search and geocoding",
            "status": "partial" if geocoder_ready else "needs_setup",
            "detail": "Geocoding endpoint is configured; availability is confirmed when a lookup succeeds" if geocoder_ready
            else "Set JARVIS_GEOCODER_URL and an identifiable JARVIS_GEOCODER_USER_AGENT",
            "action": "Open map",
            "href": "/dashboard/geography",
        },
        {
            "id": "geography-routing",
            "name": "Route directions",
            "status": "partial" if routing_configured else "needs_setup",
            "detail": "Routing endpoint is configured; availability is confirmed when a route succeeds" if routing_configured
            else "Set JARVIS_ROUTING_URL to an approved routing API endpoint",
            "action": "Open map",
            "href": "/dashboard/geography",
        },
        {
            "id": "satellite-imagery",
            "name": "Satellite imagery",
            "status": "needs_setup",
            "detail": "Requires a licensed imagery/tile provider and map-layer rendering; JARVIS does not control physical satellites",
            "action": "Open map",
            "href": "/dashboard/geography",
        },
    ])

    items.extend([
        {
            "id": "themes",
            "name": "Interface themes",
            "status": "available",
            "detail": "Built-in interface palettes are available in Settings; external theme services are not connected",
            "action": "Choose a theme",
            "href": "/dashboard/settings",
        },
        {
            "id": "notifications",
            "name": "System-aware notifications",
            "status": "partial",
            "detail": "The interface shows local activity and polled health signals; persistent user-scoped event delivery is not configured",
            "action": "Review notifications",
            "href": "/dashboard/monitoring",
        },
    ])
    return {"items": items, "checked_at": now_iso()}


def _live_capability_status() -> Dict[str, Any]:
    """Best-effort live capability health from the runtime registry.

    Returns an empty dict if the capability runtime has not been initialized
    yet (e.g. before startup registration runs).
    """
    try:
        return get_cap_orchestrator().get_all_status()
    except Exception:  # noqa: BLE001
        return {}


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

    # Live capability health from the capability runtime
    capability_status = {}
    active_executions = []
    try:
        all_status = get_cap_orchestrator().get_all_status()
        capability_status = all_status.get('capabilities', {})
        active_executions = all_status.get('active_executions', [])
    except Exception:  # noqa: BLE001
        pass

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
        "capabilities": capability_status,
        "active_executions": active_executions,
        "recent_actions": recent_actions,
        "resource_pressure": "nominal",
    }


@router.get("/processes")
async def list_processes(user: Dict[str, Any] = Depends(_require_owner),
                         limit: int = Query(50), sort: str = Query("cpu")):
    """List running processes. Requires authentication."""
    _audit_system_action("read", "list_processes", "system/processes",
                         user.get("email", ""))
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status", "create_time", "username"]
        ):
            try:
                info = p.info
                ct = info.get("create_time")
                procs.append({
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "cpu_percent": round(info.get("cpu_percent") or 0, 1),
                    "memory_percent": round(info.get("memory_percent") or 0, 1),
                    "status": info.get("status"),
                    "created_at": _utc_iso(ct) if ct is not None else None,
                    "username": info.get("username"),
                })
            except Exception:  # noqa: BLE001
                continue
        key = {"cpu": lambda x: x["cpu_percent"], "memory": lambda x: x["memory_percent"],
               "name": lambda x: x["name"]}.get(sort, lambda x: x["cpu_percent"])
        procs.sort(key=key, reverse=(sort != "name"))
        return {"processes": procs[:limit], "total": len(procs)}
    except Exception:  # noqa: BLE001
        logger.exception("system:list_processes failed")
        return {"processes": [], "total": 0, "error": "process enumeration unavailable"}


@router.post("/processes/kill")
@router.post("/process/kill")
async def kill_process(body: ProcessKillIn, user: Dict[str, Any] = Depends(_require_owner)):
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
async def get_provider_settings(user: Dict[str, Any] = Depends(_require_owner)):
    """Get provider settings metadata (spec §58).

    Returns the scrubbed ``ProviderSettingsResponse`` envelope. NEVER returns
    raw API key values — secret-shaped fields are masked to ``None``.
    """
    _audit_system_action("read", "get_provider_settings", "system/provider-settings",
                         user.get("email", ""))
    misc = get_store("misc").load()
    settings = misc.get("provider_settings") or {}
    return _provider_settings_response(settings)


@router.put("/provider-settings")
async def update_provider_settings(body: ProviderSettingsIn,
                                     user: Dict[str, Any] = Depends(_require_owner),
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
    # Return the scrubbed envelope (spec §58).
    return _provider_settings_response(settings)


@router.get("/files")
async def list_files(user: Dict[str, Any] = Depends(_require_owner),
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
                st = child.stat()
                is_dir = child.is_dir()
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "size": st.st_size,
                    "type": "directory" if is_dir else "file",
                    "modified_at": _utc_iso(st.st_mtime),
                    "is_directory": is_dir,
                })
            except Exception:  # noqa: BLE001
                continue
        return {"path": str(p), "files": entries, "entries": entries}
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")


class ReadFileIn(BaseModel):
    path: str


@router.post("/files/read")
async def read_file(body: ReadFileIn, user: Dict[str, Any] = Depends(_require_owner)):
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
async def get_clipboard(user: Dict[str, Any] = Depends(_require_owner)):
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
async def set_clipboard(body: ClipboardIn, user: Dict[str, Any] = Depends(_require_owner)):
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
    """SEC-1 §4 — confine file access to ROOT across POSIX and Windows paths."""
    base = ROOT.resolve()
    # Path() follows the host OS rules. Reject Windows drives/UNC paths even
    # when running on POSIX, and treat backslashes as separators so a Windows
    # traversal payload cannot be misclassified as a harmless filename.
    windows_path = PureWindowsPath(requested)
    if windows_path.is_absolute() or windows_path.drive:
        raise HTTPException(
            status_code=403, detail="Path is outside the allowed root"
        )
    normalized = requested.replace("\\", "/")
    raw = Path(normalized)
    candidate = raw.resolve() if raw.is_absolute() else (ROOT / raw).resolve()
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
    # 2) Host process control is reserved for the configured owner.
    user = get_current_user(request.headers.get("authorization"))  # raises 401
    if not is_owner(user):
        _audit_system_action("denied", "launch_app", f"system/launch/{body.app}",
                             user.get("email", "") or "anonymous",
                             "policy:owner_required")
        raise HTTPException(status_code=403, detail="Owner access required")
    executable = next(
        (
            entry["command"] for entry in _APPS
            if entry["command"].lower() == body.app.strip().lower()
        ),
        None,
    )
    if executable is None:
        raise HTTPException(status_code=403, detail="Application is not allowlisted")
    try:
        import subprocess
        args = (body.args or "").split()
        subprocess.Popen([executable, *args], shell=False)
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
async def take_screenshot(body: ScreenshotIn, user: Dict[str, Any] = Depends(_require_owner)):
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
async def list_windows(user: Dict[str, Any] = Depends(_require_owner)):
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
async def file_structure(user: Dict[str, Any] = Depends(_require_owner)):
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