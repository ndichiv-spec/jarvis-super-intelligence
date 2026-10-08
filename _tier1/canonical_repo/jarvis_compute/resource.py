"""jarvis_compute.resource - canonical ComputeResource abstraction.

Phase 9 §2. This module is a *thin* canonical abstraction: it does NOT perform
discovery itself and does NOT touch credentials. It normalizes the truthful
state already produced by the existing infrastructure:

* ``jarvis_backend.cloud_fabric``  -> local + cloud resource dicts + state chains
* ``providers.control_center``      -> per-provider truthful health
* ``providers.health``              -> ``HealthStatus`` / ``HealthCache``

A ``ComputeResource`` is AVAILABLE only when its backing state chain is
truthful all the way through (a configured credential alone never implies
AVAILABLE - audit §2). No new registry, secret store or probe is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Canonical resource identifiers reused across the fabric.
LOCAL_CONTROL_NODE = "local:control-node"
REMOTE_EXEC_FALLBACK = "remote_execution_host"
NOT_CONFIGURED_FALLBACK = "NOT_CONFIGURED"

# Canonical truthful states (Phase 9 §2). These map onto the existing
# ``HealthStatus`` vocabulary but are never collapsed: a single resource may be
# CONFIGURED but NOT AUTHENTICATED, or AUTHENTICATED but not HEALTHY.
CONFIGURED = "CONFIGURED"
AUTHENTICATED = "AUTHENTICATED"
REACHABLE = "REACHABLE"
HEALTHY = "HEALTHY"
RESOURCE_VERIFIED = "RESOURCE_VERIFIED"
JOB_VERIFIED = "JOB_VERIFIED"
AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"
OFFLINE = "OFFLINE"
NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class ComputeResource:
    """Canonical, truthful compute resource.

    Built from a real discovery payload (``cloud_fabric`` resource dict or a
    ``ProviderControlCenter`` status dict). ``state`` is derived, never hardcoded.
    """

    resource_id: str
    provider: str
    kind: str
    capabilities: tuple[str, ...] = ()
    state: str = NOT_CONFIGURED
    state_chain: dict[str, Any] = field(default_factory=dict)
    gpu: Optional[str] = None
    gpu_memory_gb: Optional[float] = None
    cpu: Optional[str] = None
    cpu_cores: Optional[int] = None
    memory_gb: Optional[float] = None
    storage_gb: Optional[float] = None
    cost_class: str = "unknown"
    latency_ms: Optional[float] = None
    endpoint: Optional[str] = None
    offline_capable: bool = False
    available: bool = False
    ttl: float = 30.0
    note: Optional[str] = None

    # -- derivation ---------------------------------------------------------
    @classmethod
    def from_cloud_resource(cls, payload: dict[str, Any]) -> "ComputeResource":
        """Build from a ``cloud_fabric.cloud_resources()`` resource dict."""
        chain = dict(payload.get("state_chain") or {})
        state = _state_from_chain(chain)
        caps = tuple(payload.get("capabilities") or [])
        return cls(
            resource_id=payload.get("resource_id")
            or payload.get("provider") or "unknown",
            provider=payload.get("provider") or "unknown",
            kind=payload.get("type") or "service",
            capabilities=caps,
            state=state,
            state_chain=chain,
            gpu=payload.get("gpu"),
            gpu_memory_gb=_to_float(payload.get("gpu_memory_gb")),
            cpu=payload.get("cpu"),
            cpu_cores=_to_int(payload.get("cpu_cores")),
            memory_gb=_to_float(payload.get("memory_gb")),
            storage_gb=_to_float(payload.get("storage_gb")),
            cost_class=payload.get("cost_class") or "unknown",
            latency_ms=payload.get("latency_ms"),
            endpoint=payload.get("endpoint"),
            offline_capable=_offline_for(payload),
            available=state == AVAILABLE,
            note=payload.get("reason") or payload.get("note"),
        )

    @classmethod
    def from_provider_status(cls, status_dict: dict[str, Any],
                             provider: str) -> "ComputeResource":
        """Build a resource view from a ``ProviderControlCenter`` status dict.

        The control center already performs the real probe; this just normalizes
        its truthful fields into the canonical state chain.
        """
        health = (status_dict.get("health_status") or "unknown").lower()
        chain = {
            "configured": bool(status_dict.get("configured")),
            "authenticated": bool(status_dict.get("authenticated")),
            "reachable": bool(status_dict.get("model_list_available")),
            "healthy": health in ("healthy", "degraded"),
            "resource_verified": bool(status_dict.get("ready")),
            "job_verified": bool(status_dict.get("inference_verified")),
        }
        state = _state_from_chain(chain)
        caps = tuple(status_dict.get("capabilities") or [])
        return cls(
            resource_id=f"cloud:{provider}",
            provider=provider,
            kind="gpu_inference" if "nvidia" in provider.lower() else "service",
            capabilities=caps,
            state=state,
            state_chain=chain,
            cost_class="pay_per_token" if provider == "nvidia" else "unknown",
            offline_capable=False,
            available=state == AVAILABLE,
            latency_ms=status_dict.get("latency_ms"),
            note=status_dict.get("errors") or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "provider": self.provider,
            "kind": self.kind,
            "capabilities": list(self.capabilities),
            "state": self.state,
            "state_chain": dict(self.state_chain),
            "gpu": self.gpu,
            "gpu_memory_gb": self.gpu_memory_gb,
            "cpu": self.cpu,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "storage_gb": self.storage_gb,
            "cost_class": self.cost_class,
            "latency_ms": self.latency_ms,
            "endpoint": self.endpoint,
            "offline_capable": self.offline_capable,
            "available": self.available,
            "note": self.note,
        }


def state_from_chain(chain: dict[str, Any]) -> str:
    """Derive the strongest truthful canonical state from a state chain.

    Strict ordering: each stronger gate requires all earlier gates true.
    A configured-but-authenticated-rejected provider is BLOCKED (auth required),
    never AVAILABLE. A credential existing without proof of health is never
    AVAILABLE.
    """
    if not chain:
        return NOT_CONFIGURED
    if chain.get("error"):
        return UNAVAILABLE
    if chain.get("unreachable") is True:
        return UNAVAILABLE
    if chain.get("blocked") is True:
        return BLOCKED

    configured = bool(chain.get("configured"))
    authenticated = bool(chain.get("authenticated"))
    reachable = bool(chain.get("reachable") or chain.get("endpoint_reachable"))
    healthy = bool(chain.get("healthy"))
    resource_verified = bool(chain.get("resource_verified"))
    job_verified = bool(chain.get("job_verified"))
    inference_verified = bool(chain.get("inference_verified"))

    # Creds present but rejected by the provider => auth required (BLOCKED).
    if configured and not authenticated and bool(
        chain.get("auth_failed")
        or "auth" in str(chain.get("error", "")).lower()
    ):
        return BLOCKED

    if not configured:
        return NOT_CONFIGURED
    if not authenticated:
        return CONFIGURED  # has a credential, not yet proven authenticated
    if not reachable:
        return DEGRADED
    if not healthy:
        return DEGRADED
    if not resource_verified:
        return HEALTHY
    if not (job_verified or inference_verified):
        return RESOURCE_VERIFIED
    # Fully truthful all the way through.
    return AVAILABLE


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _offline_for(payload: dict[str, Any]) -> bool:
    """A resource is offline-capable only when it can run without net creds."""
    provider = (payload.get("provider") or "").lower()
    status = (payload.get("status") or "").lower()
    if provider == "local":
        return True
    if provider == "docker" and bool(payload.get("docker")):
        return True
    if status in ("available", "healthy") and provider == "local":
        return True
    return False
