"""Brain Context Engine — bounded context packs (Phase 8 §9).

The control plane, NOT the Brain, decides what context reaches the model.
:class:`ContextEngine` builds a small, relevance-scored slice of the world:

    * task-relevant capabilities (via ``discover_capabilities``, capped)
    * task-relevant artifacts (passed in, capped + redacted)
    * recent memory (passed in or recalled by the registry)
    * real Brain/Silverwing/provider availability state

It never hands the model the full capability catalog (spec §9 honesty): the
pack is bounded by ``max_capabilities`` and ``max_artifacts`` and is scrubbed of
any secret-shaped material before leaving this module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from research_engine.tool_registry import scrub_secrets
from .budget import CostKind


def _brain_health() -> dict[str, Any]:
    """Read real Brain availability from the environment / cached facts.

    Reports OFFLINE when no endpoint is configured and never claims the Brain is
    active simply because model files exist (spec §1).
    """
    endpoint = os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    if not endpoint:
        return {"brain": "OFFLINE", "endpoint_configured": False,
                "reason": "JARVIS_BRAIN_ENDPOINT not configured"}
    return {"brain": "ONLINE", "endpoint_configured": True,
            "endpoint": endpoint, "model": os.environ.get("JARVIS_BRAIN_MODEL", "")}


def _silverwing_state() -> dict[str, Any]:
    endpoint = os.environ.get("SILVERWING_ENDPOINT", "").strip()
    if not endpoint:
        return {"silverwing": "UNAVAILABLE", "reason": "SILVERWING_ENDPOINT not configured"}
    return {"silverwing": "AVAILABLE", "endpoint": endpoint,
            "model": os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1")}


@dataclass
class ContextPack:
    """A bounded, scrubbed slice of context handed to the Brain."""

    request: str = ""
    execution_mode: str = "ONLINE"
    available_capabilities: list[dict[str, Any]] = field(default_factory=list)
    relevant_artifacts: list[dict[str, Any]] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    token_budget: int = 2048  # soft token cap for the pack's textual payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "execution_mode": self.execution_mode,
            "available_capabilities": [dict(c) for c in self.available_capabilities],
            "relevant_artifacts": [dict(a) for a in self.relevant_artifacts],
            "memory": [dict(m) for m in self.memory],
            "environment": dict(self.environment),
        }


@dataclass
class ContextLimits:
    max_capabilities: int = 12
    max_artifacts: int = 8
    max_memory: int = 8
    max_artifact_tokens: int = 800
    token_budget: int = 2048  # soft token cap for the pack's textual payload


class ContextEngine:
    """Builds bounded, scrubbed context packs (Phase 8 §9)."""

    def __init__(self, limits: Optional[ContextLimits] = None):
        self.limits = limits or ContextLimits()

    # ------------------------------------------------------------------ #
    def build(
        self,
        request: str,
        *,
        execution_mode: str = "ONLINE",
        artifacts: Optional[list[dict[str, Any]]] = None,
        memory: Optional[list[dict[str, Any]]] = None,
        task_state: Optional[dict[str, Any]] = None,
        capability_query: Optional[str] = None,
    ) -> ContextPack:
        from research_engine.capability_contract import (
            discover_capabilities, ONLINE, DEGRADED, OFFLINE,
        )

        mode = execution_mode
        # Map control-plane mode to capability_contract mode.
        cc_mode = {"ONLINE": ONLINE, "DEGRADED": DEGRADED, "OFFLINE": OFFLINE}.get(
            execution_mode, ONLINE
        )

        discovery_q = capability_query or request
        try:
            discovery = discover_capabilities(
                discovery_q, mode=cc_mode, max_results=self.limits.max_capabilities
            )
            caps = discovery.get("capabilities", [])
        except Exception:
            caps = []

        # Cap + scrub every textual payload so secrets can never leak into the
        # pack the model sees.
        caps = caps[: self.limits.max_capabilities]
        artifacts = self._scrub_artifacts((artifacts or [])[: self.limits.max_artifacts])
        memory = self._scrub_artifacts((memory or [])[: self.limits.max_memory])

        env = {
            **_brain_health(),
            **_silverwing_state(),
            "execution_mode": mode,
            "discovery_matched": discovery.get("matched", len(caps)) if isinstance(discovery, dict) else len(caps),
        }

        pack = ContextPack(
            request=request,
            execution_mode=mode,
            available_capabilities=[self._cap_summary(c) for c in caps],
            relevant_artifacts=artifacts,
            memory=memory,
            environment=env,
            token_budget=self.limits.token_budget,
        )
        # Pack a token-accuracy note for observability.
        pack.environment["pack_size"] = {
            "capabilities": len(pack.available_capabilities),
            "artifacts": len(pack.relevant_artifacts),
            "memory": len(pack.memory),
        }
        return pack

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cap_summary(c: dict[str, Any]) -> dict[str, Any]:
        """Strip a contract entry down to the model-visible slice.

        Only: id, domain, risk, offline, cost_model, timeout, required_permissions.
        Never the schemas' secret-shaped fields (there are none, but we stay
        explicit about what the Brain is allowed to see).
        """
        return {
            "id": c.get("name"),
            "domain": c.get("domain"),
            "risk": c.get("risk"),
            "availability": c.get("availability"),
            "offline": c.get("offline", c.get("supports_offline", False)),
            "cost_model": c.get("cost_model"),
            "timeout": c.get("timeout"),
            "required_permissions": list(c.get("required_permissions", [])),
            "reason": c.get("reason") or c.get("availability_reason") or "",
        }

    def _scrub_artifacts(self, items: list[Any]) -> list[Any]:
        out: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                out.append(self._scrub_dict(item))
            else:
                s, _ = scrub_secrets(item)
                out.append(s)
        return out

    @staticmethod
    def _scrub_dict(d: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(v, str):
                s, _ = scrub_secrets(v)
                clean[k] = s
            elif isinstance(v, dict):
                clean[k] = ContextEngine._scrub_dict(v)
            elif isinstance(v, list):
                clean[k] = [ContextEngine._scrub_list_item(x) for x in v]
            else:
                clean[k] = v
        return clean

    @staticmethod
    def _scrub_list_item(v: Any) -> Any:
        if isinstance(v, str):
            s, _ = scrub_secrets(v)
            return s
        if isinstance(v, dict):
            return ContextEngine._scrub_dict(v)
        return v


# Re-export cost-kind alias used by callers that track context-build cost.
CONTEXT_BUILD_COST = CostKind  # noqa: F401


__all__ = ["ContextPack", "ContextLimits", "ContextEngine"]
