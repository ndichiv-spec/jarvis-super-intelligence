"""Tier4, Cascade AI, enterprise SSO, components, subsystem status, widgets."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import ai_service, get_store, now_iso

router = APIRouter(prefix="/api/v1", tags=["misc"])


@router.get("/tier4/status")
async def tier4_status():
    return {
        "status": "unavailable",
        "tier": 4,
        "features_enabled": False,
        "capabilities": {},
        "reason": "No enterprise control plane is configured for this deployment.",
    }


class SsoTestIn(BaseModel):
    provider: str


@router.post("/enterprise/sso/test")
async def sso_test(body: SsoTestIn):
    raise HTTPException(
        status_code=501,
        detail={
            "service": body.provider,
            "operation": "identity_provider_test",
            "reason": "No enterprise identity provider validation is configured for this deployment.",
        },
    )


@router.get("/cascade-ai/health")
async def cascade_health():
    return {
        "status": "unavailable",
        "service": "cascade-ai",
        "reason": "No Cascade AI runtime is configured.",
        "timestamp": now_iso(),
    }


@router.post("/cascade-ai/initialize")
async def cascade_initialize():
    raise HTTPException(status_code=501, detail="No Cascade AI runtime is configured.")


@router.post("/cascade-ai/test-error")
async def cascade_test_error():
    raise HTTPException(status_code=501, detail="No Cascade AI runtime is configured.")


@router.post("/cascade-ai/fix/{error_id}")
async def cascade_fix(error_id: str):
    raise HTTPException(status_code=501, detail="No Cascade AI remediation runtime is configured.")


@router.get("/cascade-ai/status")
async def cascade_status():
    return {
        "status": "unavailable",
        "health": "unknown",
        "errors_handled": None,
        "reason": "No Cascade AI runtime is configured.",
    }


# ---- components (drive engine) ----

@router.get("/components")
async def list_components():
    return {
        "components": [],
        "status": "unavailable",
        "reason": "No dynamic component registry is configured.",
    }


@router.post("/components/start-all")
async def start_all():
    raise HTTPException(status_code=501, detail="No dynamic component controller is configured.")


@router.post("/components/stop-all")
async def stop_all():
    raise HTTPException(status_code=501, detail="No dynamic component controller is configured.")


@router.post("/components/{component_id}/{action}")
async def component_action(component_id: str, action: str):
    raise HTTPException(
        status_code=501,
        detail=f"Component control is not configured (component={component_id}, action={action}).",
    )


# ---- subsystem status ----

@router.get("/{subsystem}/status")
async def subsystem_status(subsystem: str):
    allowed = {"swarm", "causal", "optimizer", "quantum", "neuro_symbolic", "memory"}
    if subsystem not in allowed:
        raise HTTPException(status_code=404, detail="Unknown subsystem")
    return {
        "subsystem": subsystem,
        "status": "unavailable",
        "healthy": None,
        "reason": "No runtime is registered for this subsystem.",
        "timestamp": now_iso(),
    }


# ---- dashboard widgets ----

@router.get("/dashboard/widgets/data/system-metrics")
async def system_metrics_widget():
    from .monitoring import _sample

    sample = _sample()
    return {
        "status": "available" if sample.get("available") else "unavailable",
        "cpu": sample.get("cpu_percent"),
        "memory": (sample.get("memory") or {}).get("percent"),
        "disk": sample.get("disk"),
        "uptime_seconds": sample.get("uptime_seconds"),
        "reason": sample.get("reason"),
    }


@router.get("/dashboard/widgets/data/memory-stats")
async def memory_stats_widget():
    mem = get_store("memory").load()
    return {
        "total": len(mem),
        "short_term": sum(1 for m in mem.values() if m.get("layer") == "short_term"),
        "long_term": sum(1 for m in mem.values() if m.get("layer") == "long_term"),
    }


@router.get("/dashboard/widgets/data/ai-status")
async def ai_status_widget():
    settings = ai_service.settings()
    return {
        "status": "configured" if settings.get("enabled") else "unavailable",
        "provider": settings.get("provider"),
        "model": settings.get("model"),
        "live_probe": False,
    }


@router.get("/dashboard/widgets/data/agent-status")
async def agent_status_widget():
    agents = get_store("agents").load()
    active = sum(1 for a in agents.values() if a.get("status") == "active")
    return {"total": len(agents), "active": active}


@router.get("/dashboard/knowledge-graph/sample")
async def knowledge_graph_sample():
    items = list(get_store("knowledge").load().values())
    nodes = [{"id": i.get("key"), "label": i.get("key")} for i in items]
    return {"nodes": nodes, "edges": []}
