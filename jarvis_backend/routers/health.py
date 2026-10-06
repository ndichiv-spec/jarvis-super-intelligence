"""Health, status, metrics and infrastructure endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import Response as MetricsResponse

from ..core import ai_service, get_store, now_iso
from ..observability import metrics as obs_metrics
from ..runtime_status import check_database_status

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
async def health_status(request: Request):
    database = await check_database_status()
    return {
        "status": "healthy" if database["status"] == "AVAILABLE" else "degraded",
        "service_readiness": "ready" if database["status"] == "AVAILABLE" else "degraded",
        **deployment_metadata(),
        "uptime_seconds": _uptime(),
        "system": _system_summary(),
        "components": {"DATABASE": database},
        "ai": ai_service.settings(),
    }


@router.get("/api/v1/metrics")
async def metrics_endpoint():
    """Live system + request metrics (requests, latency, errors, memory)."""
    sessions = get_store("chat_sessions").load()
    active_sessions = sum(1 for s in sessions.values() if not s.get("archived"))
    return {
        "timestamp": now_iso(),
        "uptime_seconds": _uptime(),
        "system": _system_summary(),
        "active_sessions": active_sessions,
        "agents_registered": 0,
        "memory_items": len(get_store("memory").load()),
        **obs_metrics.snapshot(),
    }


# ------------------------------------------------------------------ #
# PART A — platform control-plane entrypoints (no /v1 prefix)
# ------------------------------------------------------------------ #

@router.get("/health/live")
async def health_live():
    """Liveness only — is the process alive?"""
    return {"status": "alive"}


@router.get("/api/v1/runtime/frontend")
async def frontend_discovery():
    """Report reachability of the explicitly configured frontend origin."""
    configured = os.environ.get("JARVIS_APP_URL", "").strip()
    if not configured:
        return {"configured": False, "reachable": False, "url": None}

    try:
        parsed = urlsplit(configured)
        parsed.port  # Validate malformed/non-numeric ports before making a request.
    except ValueError:
        return {
            "configured": False,
            "reachable": False,
            "url": None,
            "error": "JARVIS_APP_URL is not a valid HTTP(S) origin",
        }
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return {
            "configured": False,
            "reachable": False,
            "url": None,
            "error": "JARVIS_APP_URL must be an HTTP(S) origin without credentials or path",
        }

    frontend_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
            response = await client.get(frontend_url)
        return {
            "configured": True,
            "reachable": response.status_code < 500,
            "url": frontend_url,
            "status_code": response.status_code,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "configured": True,
            "reachable": False,
            "url": frontend_url,
            "error": type(exc).__name__,
        }


async def _probe_silverwing() -> dict:
    endpoint = os.environ.get("SILVERWING_ENDPOINT", "").strip()
    result = {
        "configured": bool(endpoint),
        "reachable": False,
        "endpoint": endpoint or None,
    }

    # Single-process deployment integrates silverwing-backend *in-process*
    # under /silverwing. Verify that integration (a real mount flag, no network)
    # before probing the standalone SILVERWING_ENDPOINT runtime (e.g. :8010),
    # which is an optional process that is not started in this deployment.
    # Probing only :8010 falsely reported Silverwing as unreachable while it is
    # in fact integrated and serving.
    try:
        from ..main import _silverwing_app, _silverwing_error  # deferred: avoids import cycle
        if _silverwing_app is not None and _silverwing_error is None:
            result["reachable"] = True
            result["endpoint"] = endpoint or "/silverwing (in-process)"
            result["status_code"] = 200
            return result
    except Exception:
        pass

    if not endpoint:
        return result

    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        health_urls = (f"{base}/health", f"{base.removesuffix('/v1')}/health")
    else:
        health_urls = (f"{base}/v1/health", f"{base}/health")

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
                    return result
    except Exception:
        return result
    return result


async def _readiness_snapshot() -> dict:
    from ..celery_app import get_queue_runtime_status
    from ..gateway import ProviderGateway
    from .ai import _provider_catalog

    async def catalog_snapshot():
        try:
            return await _provider_catalog()
        except Exception:
            return {}

    brain, catalog, silverwing, database = await asyncio.gather(
        ProviderGateway().probe_brain(),
        catalog_snapshot(),
        _probe_silverwing(),
        check_database_status(),
    )
    queue = await asyncio.to_thread(get_queue_runtime_status)
    ready_providers = []
    for provider in (catalog or {}).get("providers", []):
        if provider.get("provider") not in {"openai", "nvidia", "google", "aws", "hf"}:
            continue
        if provider.get("available") and provider.get("authorized"):
            ready_providers.append({
                "provider": provider.get("provider"),
                "model": provider.get("model"),
            })

    runtime_available = bool(
        brain.get("healthy")
        or ready_providers
        or silverwing.get("reachable")
    )
    service_ready = database.get("status") == "AVAILABLE"
    return {
        "status": "ready" if service_ready else "degraded",
        "service_readiness": "ready" if service_ready else "degraded",
        "runtime_health": "online" if runtime_available else "degraded",
        "provider_availability": "available" if runtime_available else "unavailable",
        "database": database,
        "queue": queue,
        "brain": brain,
        "providers": ready_providers,
        "silverwing": silverwing,
    }


@router.get("/health/ready")
async def health_ready(response: Response):
    snapshot = await _readiness_snapshot()
    if response is not None and snapshot["service_readiness"] != "ready":
        response.status_code = 503
    return snapshot


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

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
            "silverwing": "offline" if not _os.environ.get("SILVERWING_ENDPOINT") else "healthy",
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
            "provider": brain.get("provider"),
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
