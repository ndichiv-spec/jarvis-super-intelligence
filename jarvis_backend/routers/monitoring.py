"""Monitoring, health-report, optimization, system diagnostics."""

from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..core import now_iso

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def _sample() -> Dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {"available": False, "reason": "psutil_not_installed"}
    try:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(".")
        network = psutil.net_io_counters()
        return {
            "available": True,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory": {
                "total": vm.total,
                "used": vm.used,
                "available": vm.available,
                "percent": vm.percent,
            },
            "disk": disk.percent,
            "processes": len(psutil.pids()),
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_received": network.bytes_recv,
            },
            "uptime_seconds": max(0, time.time() - psutil.boot_time()),
        }
    except (OSError, RuntimeError) as exc:
        return {"available": False, "reason": type(exc).__name__}


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
    score = max(0, 100 - round(
        s["cpu_percent"] * 0.4
        + s["memory"]["percent"] * 0.4
        + s["disk"] * 0.2
    ))
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


@router.get("/traces")
async def traces_endpoint():
    """Expose OpenTelemetry trace data and correlation context.

    This endpoint merges the existing in-memory metrics snapshot with
    OpenTelemetry tracer state, so operators can see both counters and
    active trace/span information in one place (matching the observability
    pattern used by OpenAI Codex's ``otel-trace-websocket``).
    """
    from ..observability import metrics, get_tracer
    from opentelemetry import trace as otel_trace

    snapshot = metrics.snapshot()

    # Gather current span/trace context from the active tracer
    tracer = get_tracer()
    otel_info = {"available": True, "tracer": str(tracer)}

    try:
        provider = otel_trace.get_tracer_provider()
        otel_info["tracer_provider"] = type(provider).__name__
    except Exception:
        otel_info["available"] = False
        otel_info["tracer_provider"] = "none"

    return {
        "timestamp": now_iso(),
        "metrics": snapshot,
        "opentelemetry": otel_info,
        "gateway": _gateway_otel_summary(),
    }


def _gateway_otel_summary() -> Dict[str, Any]:
    """Summarise the model-gateway telemetry (inference events)."""
    try:
        from ..observability import gateway_metrics_snapshot
        return gateway_metrics_snapshot()
    except Exception:
        return {}


@router.get("/metrics/prometheus")
async def prometheus_metrics():
    """Prometheus-format metrics export endpoint.

    Serves the same metrics as :func:`monitoring_metrics` but in the
    Prometheus text exposition format, so Prometheus can scrape it.
    Falls back to JSON if prometheus_client is not installed.
    """
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY
        from fastapi.responses import Response

        body = generate_latest(REGISTRY)
        return Response(
            content=body,
            media_type=CONTENT_TYPE_LATEST,
            headers={"X-Request-ID": "monitoring-prometheus"},
        )
    except Exception:
        # Fall back to JSON if prometheus_client is unavailable
        return {"timestamp": now_iso(), **_sample()}


@router.get("/optimization-report")
async def optimization_report():
    return {
        "timestamp": now_iso(),
        "status": "NOT_IMPLEMENTED",
        "suggestions": [],
        "optimized_components": [],
    }


@router.post("/optimize")
async def optimize():
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Automated system optimization is not available."},
    )


@router.get("/system/diagnostics")
async def system_diagnostics():
    sample = _sample()
    if not sample.get("available"):
        return {
            "timestamp": now_iso(),
            "status": "unavailable",
            "diagnostics": sample,
            "healthy": None,
        }
    checks = {
        "cpu": sample["cpu_percent"] < 90,
        "memory": sample["memory"]["percent"] < 90,
        "disk": sample["disk"] < 95,
    }
    return {
        "timestamp": now_iso(),
        "status": "healthy" if all(checks.values()) else "degraded",
        "diagnostics": sample,
        "checks": checks,
        "healthy": all(checks.values()),
    }


@router.get("/recovery-history")
async def recovery_history():
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Persisted recovery history is not available."},
    )


@router.post("/trigger-recovery")
async def trigger_recovery():
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Automated recovery is not available."},
    )


@router.get("/health")
async def monitoring_health():
    sample = _sample()
    if not sample.get("available"):
        return {
            "status": "unavailable",
            "timestamp": now_iso(),
            "sample_available": False,
        }
    healthy = (
        sample["cpu_percent"] < 90
        and sample["memory"]["percent"] < 90
        and sample["disk"] < 95
    )
    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": now_iso(),
        "sample_available": True,
    }
