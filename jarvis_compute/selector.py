"""jarvis_compute.selector - deterministic ComputeSelector (Phase 9 §4/§9/§10).

Reuses the EXISTING routers - no new policy engine:

* ``jarvis_backend.cloud_fabric.select_compute``  (hardware-aware ranking)
* ``providers.routing.ProviderRouter``             (capability + health + cost)

The selector maps a Brain requirement dict to a canonical
:class:`~jarvis_compute.resource.ComputeResource` selection, applies the
OFFLINE/DEGRADED/ONLINE execution-mode filter (Phase 9 §10), and returns a
truthful decision (never fabricates a target).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .resource import (
    AVAILABLE, DEGRADED, NOT_CONFIGURED, OFFLINE, UNAVAILABLE, BLOCKED,
    ComputeResource,
    state_from_chain,
)


@dataclass
class Selection:
    """Result of a compute selection - a selected resource + fallback chain."""

    selected: Optional[ComputeResource] = None
    fallback: list[ComputeResource] = field(default_factory=list)
    reason: str = ""
    decision_state: str = "RESOURCE_UNAVAILABLE"  # AVAILABLE|DEGRADED|RESOURCE_UNAVAILABLE|PLAN_BLOCKED
    requirements: dict[str, Any] = field(default_factory=dict)
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    evaluated: list[dict[str, Any]] = field(default_factory=list)
    cost_estimate: Optional[float] = None  # None == unknown, never fabricated
    timestamp: float = field(default_factory=time.time)
    ttl: float = 30.0

    @property
    def available(self) -> bool:
        return self.decision_state == AVAILABLE


@dataclass
class _Cached:
    value: Any
    expires_at: float


class ComputeSelector:
    """Deterministic, truthful compute selector over the existing fabric."""

    def __init__(self, *, policy: str = "best_quality", ttl: float = 30.0):
        self.policy = policy
        self.ttl = ttl
        self._cache: dict[str, _Cached] = {}

    # -- resource discovery (cached, TTL) -----------------------------------
    def resources(self, *, refresh: bool = False) -> list[ComputeResource]:
        """All real resources with truthful states. TTL-cached (Phase 9 §20)."""
        key = "resources"
        cached = self._cache.get(key)
        if cached and not refresh and cached.expires_at > time.monotonic():
            return cached.value  # type: ignore[return-value]
        resources = self._discover_resources()
        self._cache[key] = _Cached(resources, time.monotonic() + self.ttl)
        return resources

    def resource(self, resource_id: str, *, refresh: bool = False) -> Optional[ComputeResource]:
        for r in self.resources(refresh=refresh):
            if r.resource_id == resource_id:
                return r
        return None

    # -- the deterministic selection ---------------------------------------
    def select(self, requirements: Optional[dict[str, Any]] = None) -> Selection:
        req = dict(requirements or {})
        mode = (req.get("execution_mode") or "ONLINE").upper()
        offline = mode == "OFFLINE" or bool(req.get("offline"))

        # Start from the existing hardware-aware router decision.
        decision = self._cloud_select(req)
        resources = self.resources()

        # Normalize cloud_fabric's selected id + evaluated list into resources.
        selected_res = self._by_id(decision.get("selected"), resources)
        fallback = []
        for e in decision.get("evaluated", []):
            if not e.get("eligible"):
                continue
            rid = e.get("resource_id")
            res = self._by_id(rid, resources)
            if res and res is not selected_res:
                fallback.append(res)

        # OFFLINE/DEGRADED mode filter (Phase 9 §10): only offline-capable
        # resources may be selected; cloud resources are reported as the
        # reason they were excluded (never fabricated as available).
        if offline:
            if selected_res and selected_res.offline_capable:
                state = AVAILABLE
                reason = decision.get("selection_basis") or "offline-allowed local target"
            elif selected_res is None:
                # No offline-capable target at all.
                reason = "PLAN_BLOCKED: no offline-capable resource satisfies the request" \
                         + (f" (requested: {req.get('task')})" if req.get("task") else "")
                return Selection(
                    selected=None, reason=reason, decision_state="PLAN_BLOCKED",
                    requirements=req,
                )
            else:
                # A non-offline-capable resource was selected -> fall to local.
                reason = "PLAN_BLOCKED: selected resource requires network; " \
                         "no offline target available"
                return Selection(
                    selected=None, reason=reason, decision_state="PLAN_BLOCKED",
                    requirements=req,
                )
            state = AVAILABLE
        else:
            if selected_res is None:
                infeasible = decision.get("infeasible_reason")
                reason = (infeasible or "RESOURCE_UNAVAILABLE: no resource satisfies "
                                              "the stated requirements")
                return Selection(
                    selected=None, reason=reason, decision_state="RESOURCE_UNAVAILABLE",
                    requirements=req,
                )
            state = AVAILABLE if selected_res.available else DEGRADED
            reason = decision.get("selection_basis") or "best-fit real resource"

        return Selection(
            selected=selected_res,
            fallback=fallback,
            reason=reason,
            decision_state=state,
            requirements=req,
            selected_provider=selected_res.provider if selected_res else None,
            selected_model=decision.get("selected_model"),
            evaluated=decision.get("evaluated", []),
            cost_estimate=decision.get("cost_estimate"),
        )

    # -- model routing for an inference task (ProviderRouter reuse) ---------
    def route_model(self, task_description: str, *, offline: bool = False) -> dict[str, Any]:
        """Real provider/model routing for a chat/inference task.

        Delegates to ``providers.routing.ProviderRouter`` (health-gated,
        privacy-enforced, with an honest fallback chain). Cost is None when
        unknown (never fabricated).
        """
        if offline:
            # Offline mode: only local/Silverwing inference is permissible.
            from jarvis_backend import brain_fabric as bf

            silverwing = bf.discover_silverwing()
            if silverwing.get("available") or silverwing.get("state") == "available":
                return {
                    "selected_provider": "local:silverwing",
                    "selected_model": silverwing.get("model"),
                    "available": True,
                    "reason": "offline local model",
                    "cost_estimate": None,
                    "fallback": [],
                }
            return {
                "selected_provider": None,
                "selected_model": None,
                "available": False,
                "reason": "OFFLINE: no local inference model configured",
                "cost_estimate": None,
                "fallback": [],
            }
        try:
            from providers.bootstrap import bootstrap_fabric
            from providers.routing import ProviderRouter

            reg = bootstrap_fabric()
            router = ProviderRouter(registry=reg, policy=self.policy)
            decision = router.route_text(task_description)
            return {
                "selected_provider": decision.selected_provider,
                "selected_model": decision.selected_model,
                "available": bool(decision.selected_provider),
                "reason": decision.reason,
                "cost_estimate": decision.cost_estimate,  # None when unknown
                "fallback": decision.fallback_chain,
                "no_ready_providers": not decision.selected_provider,
            }
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return {
                "selected_provider": None, "selected_model": None,
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "cost_estimate": None, "fallback": [],
                "no_ready_providers": True,
            }

    # -- helpers -----------------------------------------------------------
    def _cloud_select(self, req: dict[str, Any]) -> dict[str, Any]:
        try:
            from jarvis_backend import cloud_fabric as cf

            return cf.select_compute(req)
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return {
                "requirements": req, "eligible": [], "selected": None,
                "selected_model": None, "evaluated": [], "infeasible_reason": None,
                "local_viable": False, "local_block_reason": f"{type(exc).__name__}: {exc}",
                "requires_approval": True, "cost_estimate": None,
            }

    def _discover_resources(self) -> list[ComputeResource]:
        try:
            from jarvis_backend import cloud_fabric as cf

            disc = cf.cloud_resources()
        except Exception:  # noqa: BLE001 - fabric unavailable -> empty (honest)
            return []
        out: list[ComputeResource] = []
        for payload in disc.get("resources", []):
            try:
                out.append(ComputeResource.from_cloud_resource(payload))
            except Exception:  # noqa: BLE001
                continue
        return out

    @staticmethod
    def _by_id(rid: Optional[str], resources: list[ComputeResource]) -> Optional[ComputeResource]:
        if not rid:
            return None
        for r in resources:
            if r.resource_id == rid:
                return r
        return None


def execution_mode() -> str:
    """Current operating mode from real connectivity + local hardware limits.

    ONLINE  = at least one authenticated cloud provider is reachable
    DEGRADED = local hardware only (no cloud authenticated) but usable
    OFFLINE = nothing authenticated and no local analysis surface
    """
    sel = ComputeSelector()
    res = sel.resources(refresh=False)
    local = None
    cloud_authenticated = False
    for r in res:
        if r.provider == "local":
            local = r
        if r.state in (AVAILABLE, DEGRADED, AUTHENTICATED, REACHABLE) and r.provider != "local":
            cloud_authenticated = cloud_authenticated or r.available or r.provider in (
                "nvidia", "kaggle", "huggingface"
            ) and bool(r.state_chain.get("authenticated"))
    if not res:
        return OFFLINE
    if cloud_authenticated:
        return "ONLINE"
    if local and local.available:
        return DEGRADED
    return OFFLINE
