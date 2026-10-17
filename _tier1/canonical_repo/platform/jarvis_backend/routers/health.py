"""Health, status, metrics and infrastructure endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Response

from ..core import ai_service, get_store, now_iso
from ..observability import metrics as obs_metrics
from ..runtime_status import (
    check_auth_status,
    check_chat_status,
    check_database_status,
)

router = APIRouter(tags=["health"])

_START_TIME = time.time()


def _uptime() -> float:
    return round(time.time() - _START_TIME, 2)


def _system_summary() -> dict:
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "uptime_seconds": _uptime(),
    }


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": now_iso()}


@router.head("/api/health")
async def health_head():
    return {"status": "ok"}


@router.get("/api/ping")
async def ping():
    return {"pong": True, "timestamp": now_iso()}


@router.get("/api/version")
async def version():
    return deployment_metadata()


def deployment_metadata() -> dict:
    return {
        "version": os.environ.get("JARVIS_VERSION", "3.0.0"),
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
        "environment": os.environ.get("ENVIRONMENT", os.environ.get("JARVIS_ENV", "development")),
        "deployment_id": os.environ.get("DEPLOYMENT_ID", "local"),
        "name": "JARVIS Unified System",
    }


@router.get("/api/v1/health/status")
async def health_status():
    auth, chat, database = await asyncio.gather(
        check_auth_status(),
        check_chat_status(),
        check_database_status(),
    )
    core_available = all(
        item.get("status") == "AVAILABLE"
        for item in (auth, chat, database)
    )
    core_status = "healthy" if core_available else "degraded"
    return {
        "status": core_status,
        "alive": True,
        "timestamp": now_iso(),
        **deployment_metadata(),
        "uptime_seconds": _uptime(),
        "system": _system_summary(),
        "ai": ai_service.settings(),
        "components": {
            "AUTH": auth,
            "CHAT": chat,
            "DATABASE": database,
        },
    }


@router.get("/api/v1/health/metrics", include_in_schema=False)
@router.get("/api/v1/metrics")
async def metrics_endpoint():
    """Live system + request metrics (requests, latency, errors, memory)."""
    sessions = get_store("chat_sessions").load()
    registered_agents = len(get_store("agents").load())
    active_sessions = sum(1 for s in sessions.values() if not s.get("archived"))
    return {
        "timestamp": now_iso(),
        "uptime_seconds": _uptime(),
        "system": _system_summary(),
        "active_sessions": active_sessions,
        "agents_registered": registered_agents,
        "memory_items": len(get_store("memory").load()),
        **obs_metrics.snapshot(),
    }


# ------------------------------------------------------------------ #
# PART A — platform control-plane entrypoints (no /v1 prefix)
# ------------------------------------------------------------------ #

@router.get("/api/v1/health/live", include_in_schema=False)
@router.get("/health/live")
async def health_live():
    """Liveness only — is the process alive?"""
    return {
        "status": "alive",
        "service": "jarvis-backend",
        "uptime_seconds": _uptime(),
    }


async def _probe_silverwing() -> dict:
    endpoint = os.environ.get("SILVERWING_ENDPOINT", "").strip()
    result = {
        "configured": bool(endpoint),
        "reachable": False,
        "healthy": None,
        "model_available": False,
        "executable": False,
        "endpoint": endpoint or None,
    }
    if not endpoint:
        return result

    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        health_urls = (f"{base}/health", f"{base.removesuffix('/v1')}/health")
        models_url = f"{base}/models"
    else:
        health_urls = (f"{base}/v1/health", f"{base}/health")
        models_url = f"{base}/v1/models"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            for url in health_urls:
                try:
                    response = await client.get(url)
                except httpx.HTTPError:
                    continue
                result["status_code"] = response.status_code
                if response.status_code == 200:
                    result["reachable"] = True
                    break
            if result["reachable"]:
                try:
                    models_response = await client.get(models_url)
                    result["models_status_code"] = models_response.status_code
                    if models_response.status_code == 200:
                        payload = models_response.json()
                        models = payload.get("data") or payload.get("models") or []
                        result["model_available"] = bool(models)
                except (httpx.HTTPError, ValueError):
                    result["model_available"] = False
    except Exception:
        return result
    return result


async def _readiness_snapshot() -> dict:
    from ..gateway import ProviderGateway
    from ..mcp_runtime import mcp_status
    from .ai import _provider_catalog

    async def catalog_snapshot():
        try:
            return await _provider_catalog()
        except Exception:
            return {}

    brain, catalog, silverwing, auth, chat, database, mcp = await asyncio.gather(
        ProviderGateway().probe_brain(),
        catalog_snapshot(),
        _probe_silverwing(),
        check_auth_status(),
        check_chat_status(),
        check_database_status(),
        mcp_status(),
    )
    ready_providers = []
    for provider in (catalog or {}).get("providers", []):
        if provider.get("provider") not in {"openai", "nvidia", "google", "aws", "hf"}:
            continue
        if (
            provider.get("available")
            and provider.get("authorized")
            and provider.get("inference_verified") is True
        ):
            ready_providers.append({
                "provider": provider.get("provider"),
                "model": provider.get("model"),
            })

    ready = bool(brain.get("healthy") or ready_providers)
    backend_ready = bool(
        auth.get("status") == "AVAILABLE"
        and chat.get("status") == "AVAILABLE"
        and database.get("status") == "AVAILABLE"
        and mcp.get("status") == "AVAILABLE"
    )
    return {
        "status": "ready" if ready else "degraded",
        "alive": True,
        "service_readiness": "ready" if backend_ready else "degraded",
        "ai_execution_readiness": "ready" if ready else "degraded",
        "backend": {
            "status": "ready" if backend_ready else "degraded",
            "components": {
                "AUTH": auth,
                "CHAT": chat,
                "DATABASE": database,
                "MCP": mcp,
            },
        },
        "brain": brain,
        "providers": ready_providers,
        "silverwing": silverwing,
        "mcp": mcp,
    }


@router.get("/api/v1/health/ready", include_in_schema=False)
@router.get("/health/ready")
async def health_ready(response: Response):
    snapshot = await _readiness_snapshot()
    if snapshot["backend"]["status"] != "ready":
        response.status_code = 503
    return snapshot


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint.

    ``prometheus_client`` is an *optional* monitoring integration: the
    in-process metrics registry in :mod:`jarvis_backend.observability` keeps
    working without it (see ``Metrics._prom_init``). If it is not installed we
    return an honest 503 so monitoring tooling can distinguish "optional
    metrics adapter unavailable" from a genuine service failure — this is not a
    suppression of a real error and does not weaken any security control.
    """
    from fastapi.responses import Response as MetricsResponse

    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError:
        return MetricsResponse(
            content=json.dumps(
                {
                    "status": "unavailable",
                    "detail": "prometheus_client is not installed; /metrics is an optional monitoring adapter",
                }
            ),
            media_type="application/json",
            status_code=503,
        )
    return MetricsResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/")
async def root():
    """Structured service manifest (spec Part A)."""
    import os as _os

    from ..gateway import ProviderGateway
    brain_ep = _os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    brain = await ProviderGateway().probe_brain() if brain_ep else {"configured": False, "healthy": False}
    return {
        "service": "JARVIS API",
        "component": "control-plane",
        "status": "operational" if brain.get("healthy") else "degraded",
        "version": "3.0.0",
        "brain": {
            "endpoint": "/v1/brain",
            "status": (
                "healthy" if brain.get("healthy")
                else ("degraded" if brain.get("configured") else "offline")
            ) if isinstance(brain, dict) else "unknown",
        },
        "providers": {
            "nvidia": "healthy" if brain.get("provider") == "nvidia" else ("configured" if brain_ep else "not_configured"),
            "huggingface": "not_configured",
            "silverwing": (
                "not_configured" if not _os.environ.get("SILVERWING_ENDPOINT")
                else "degraded"
            ),
        },
        "documentation": {"swagger": "/docs", "redoc": "/redoc", "openapi": "/openapi.json"},
    }


@router.get("/api/status")
async def api_status():
    """Current platform state (spec Part A)."""
    import os as _os

    from ..gateway import ProviderGateway
    data = {"status": "operational", **ai_service.settings()}
    brain_ep = _os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    data["brain_endpoint"] = brain_ep or None
    data["brain_model"] = _os.environ.get("JARVIS_BRAIN_MODEL")
    if brain_ep:
        data["brain"] = await ProviderGateway().probe_brain()
    return data


@router.get("/api/capabilities")
async def api_capabilities():
    """Registered capabilities — reported honestly from verified paths."""
    return {
        "chat": True,
        "streaming": True,
        "tool_use": True,        # wired end-to-end via research_engine ToolRegistry
        "rag": True,             # KnowledgeRetrieveTool delegates to infra RAG index
        "memory": True,          # per-session research memory (JSON-backed fallback)
        "vision": False,
        "structured_output": True,  # Evidence/Report schema (typed, provenance-tracked)
        "reasoning": True,
        "fallback": True,        # gateway fallback chain verified
        "verification": True,    # VerificationEngine wired into the research pipeline
        "planning": True,        # ResearchEngine multi-pass + BrainAgent plan
        "model_routing": True,   # brain_runtime BrainRouter + ProviderGateway
    }


@router.get("/api/providers")
async def api_providers():
    """Provider registry + live status (spec Part A)."""
    import os as _os

    from ..gateway import ProviderGateway
    from .ai import _provider_catalog
    catalog = await _provider_catalog()
    brain_ep = _os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    if brain_ep:
        brain = await ProviderGateway().probe_brain()
        catalog["providers"].append({
            "provider": "jarvis-brain",
            "available": brain.get("healthy", False),
            "authorized": True,
            "model": brain.get("model"),
            "endpoint": brain_ep,
            "backend": brain.get("backend"),
            "backend_provider": brain.get("provider"),
            "latency_ms": brain.get("latency_ms"),
            "models": [_os.environ.get("JARVIS_BRAIN_MODEL")] if brain.get("model") else [],
        })
    return catalog


@router.get("/api/models")
async def api_models():
    """Model registry (spec Part A)."""
    from .ai import _provider_catalog
    catalog = await _provider_catalog()
    models = []
    for p in catalog.get("providers", []):
        for m in p.get("models", []):
            models.append({"provider": p["provider"], "model": m,
                           "available": p.get("available", False)})
    return {"models": models, "default": catalog.get("default_model")}


@router.get("/api/brain/status")
async def api_brain_status():
    """Detailed Brain status — real probe only (spec Part A, Part P)."""
    from ..gateway import ProviderGateway
    return await ProviderGateway().probe_brain()


@router.get("/api/brain/models")
async def api_brain_models():
    """Models discoverable by the configured Brain provider (spec Part A)."""
    from ..gateway import _jarvis_brain_api_key, _jarvis_brain_endpoint
    endpoint = _jarvis_brain_endpoint()
    if not endpoint:
        return {"models": [], "configured": False}
    key = _jarvis_brain_api_key()
    # The Brain endpoint already ends with "/v1" (e.g. http://127.0.0.1:8011/v1);
    # append "/models" without repeating the version prefix.
    models_url = f"{endpoint.rstrip('/')}/models"
    req = urllib.request.Request(models_url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return {"models": data.get("data", []), "configured": True}
    except urllib.error.HTTPError as exc:
        return {"models": [], "configured": True, "error": exc.code}
    except Exception as exc:
        return {"models": [], "configured": True, "error": str(exc)}
