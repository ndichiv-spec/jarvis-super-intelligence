"""Monitoring, health-report, optimization, system diagnostics."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..core import now_iso

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def _sample() -> Dict[str, Any]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        return {
            "available": True,
            "cpu_percent": cpu,
            "memory": {
                "total": vm.total,
                "used": vm.used,
                "available": vm.available,
                "percent": vm.percent,
            },
            "disk": psutil.disk_usage(".").percent,
            "processes": len(psutil.pids()),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "Host metrics collection is unavailable."}


@router.get("/health-report")
async def health_report():
    s = _sample()
    if not s.get("available"):
        return {
            "timestamp": now_iso(),
            "health_score": None,
            "status": "unavailable",
            "system": s,
            "checks": [],
        }
    score = max(0, min(100, round(
        100 - s["cpu_percent"] * 0.4
        - s["memory"]["percent"] * 0.4
        - s["disk"] * 0.2
    )))
    return {
        "timestamp": now_iso(),
        "health_score": score,
        "status": "healthy" if score >= 60 else "degraded",
        "system": s,
        "checks": [
            {"name": "cpu", "status": "ok" if s.get("cpu_percent", 0) < 80 else "warn"},
            {"name": "memory", "status": "ok" if s.get("memory", {}).get("percent", 0) < 85 else "warn"},
            {"name": "disk", "status": "ok" if s.get("disk", 0) < 90 else "warn"},
        ],
    }


@router.get("/metrics")
async def monitoring_metrics():
    return {"timestamp": now_iso(), **_sample()}


@router.get("/optimization-report")
async def optimization_report():
    raise HTTPException(501, "Optimization analysis is not implemented for this deployment.")


@router.post("/optimize")
async def optimize():
    raise HTTPException(501, "System optimization is not implemented for this deployment.")


@router.get("/system/diagnostics")
async def system_diagnostics():
    diagnostics = _sample()
    return {
        "timestamp": now_iso(),
        "diagnostics": diagnostics,
        "healthy": diagnostics.get("available") is True,
    }


@router.get("/recovery-history")
async def recovery_history():
    raise HTTPException(501, "Recovery history is not available for this deployment.")


@router.post("/trigger-recovery")
async def trigger_recovery():
    raise HTTPException(501, "Automated recovery is not implemented for this deployment.")


@router.get("/health")
async def monitoring_health():
    report = await health_report()
    return {
        "status": report["status"],
        "health_score": report["health_score"],
        "timestamp": report["timestamp"],
    }
