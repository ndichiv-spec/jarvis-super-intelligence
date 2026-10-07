"""Capability router + policy engine for the JARVIS Provider Fabric (spec §10, §34-36).

The router answers the question "which provider/model should run this task?" from a
:class:`TaskProfile` (required capabilities, privacy, latency, cost). Rules:

* it **only** considers providers that declare every required capability;
* ordering is policy-driven and configurable — ``JARVIS_PROVIDER_PRIORITY`` (a
  comma-separated provider list) overrides scoring, so no vendor is baked in as
  universally superior (spec §35);
* privacy routing is enforced (spec §36) — ``LOCAL_ONLY`` work can never leave the
  machine through this router;
* cost is ``None`` whenever pricing is not declared (spec §34) — the router never
  fabricates a cost number.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .base import ProviderAdapter
from .capabilities import Capability, serialize
from .models import CostClass, PrivacyClass, ProviderModel
from .registry import ProviderRegistry, get_registry
from .telemetry import ProviderTelemetry, get_telemetry

COST_RANK = {
    CostClass.FREE: 4,
    CostClass.LOW: 3,
    CostClass.MEDIUM: 1,
    CostClass.HIGH: 0,
}
LATENCY_RANK = {"low": 3, "medium": 1, "high": 0}


@dataclass
class TaskProfile:
    """What a task needs. Capabilities are mandatory; the rest tune selection."""

    capabilities: frozenset[Capability] = frozenset({Capability.CHAT})
    privacy: PrivacyClass = PrivacyClass.PUBLIC
    latency: str = "medium"
    cost_budget: str = "any"  # any | low
    quality: str = "balanced"  # balanced | high
    description: str = ""

    def primary(self) -> Capability:
        if Capability.CHAT in self.capabilities:
            return Capability.CHAT
        for cap in self.capabilities:
            return cap
        return Capability.CHAT


class TaskClassifier:
    """Keyword classifier returning a :class:`TaskProfile` (a heuristic, not magic)."""

    _RULES: list[tuple[Capability, tuple[str, ...]]] = [
        (Capability.REASONING, (
            "reason", "think", "deep", "plan", "analy", "explain", "math",
            "logic", "prove", "complex",
        )),
        (Capability.TOOL_CALLING, (
            "tool", "function", "agent", "action", "n8n", "automation",
            "connector", "api call", "execute",
        )),
        (Capability.VISION, (
            "vision", "image", "photo", "picture", "ocr", "screenshot",
            "camera", "diagram", "chart", "visual",
        )),
        (Capability.AUDIO, (
            "audio", "speech", "voice", "transcribe", "listen", "song",
        )),
        (Capability.EMBEDDINGS, (
            "embed", "embedding", "vector", "semantic search",
        )),
        (Capability.RERANKING, (
            "rerank", "re-rank", "relevance scoring",
        )),
        (Capability.STRUCTURED_OUTPUT, (
            "json", "structured", "schema", "parse", "extract fields",
        )),
        (Capability.WEB_SEARCH, (
            "web search", "research", "browse", "internet", "search the web",
            "latest", "news", "citations",
        )),
        (Capability.FILE_SEARCH, (
            "file search", "documents", "search files", "knowledge base",
        )),
        (Capability.STREAMING, (
            "stream", "incremental",
        )),
    ]

    def classify(self, task: str) -> TaskProfile:
        lowered = (task or "").lower()
        caps: set[Capability] = {Capability.CHAT}
        for capability, keywords in self._RULES:
            if any(k in lowered for k in keywords):
                caps.add(capability)

        quality = "high" if any(k in lowered for k in ("sonnet", "opus", "reasoning", "hard")) else "balanced"
        latency = "low" if any(k in lowered for k in ("fast", "quick", "real-time")) else "medium"
        cost_budget = "low" if any(k in lowered for k in ("cheap", "bulk", "cost")) else "any"
        privacy = PrivacyClass.PUBLIC
        if any(k in lowered for k in ("private", "confidential")):
            privacy = PrivacyClass.PRIVATE
        if any(k in lowered for k in ("local only", "never leave", "offline")):
            privacy = PrivacyClass.LOCAL_ONLY
        return TaskProfile(
            capabilities=frozenset(caps),
            privacy=privacy,
            latency=latency,
            cost_budget=cost_budget,
            quality=quality,
            description=task,
        )


@dataclass
class RoutingCandidate:
    adapter: ProviderAdapter
    model: ProviderModel
    reason: str
    score: float = 0.0
    inference_verified: bool = False


@dataclass
class RoutingDecision:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    task_description: str = ""
    capabilities_required: list[str] = field(default_factory=list)
    privacy: str = PrivacyClass.PUBLIC.value
    policy: str = "best_quality"
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    reason: str = ""
    fallback_chain: list[dict] = field(default_factory=list)
    pricing_per_1k: Optional[list] = None  # [input, output] or None when unknown
    cost_estimate: Optional[float] = None  # None == unknown, never fabricated
    candidate_count: int = 0

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "task_description": self.task_description,
            "capabilities_required": self.capabilities_required,
            "privacy": self.privacy,
            "policy": self.policy,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "reason": self.reason,
            "fallback_chain": self.fallback_chain,
            "pricing_per_1k": self.pricing_per_1k,
            "cost_estimate": self.cost_estimate,
            "candidate_count": self.candidate_count,
        }


class PolicyEngine:
    """Scoring that implements a named policy (spec §34)."""

    @staticmethod
    def score(adapter: ProviderAdapter, model: ProviderModel, task: TaskProfile, policy: str) -> float:
        score = 0.0
        if policy == "best_quality":
            score += 3.0 if model.supports_capability(Capability.REASONING) else 0.0
            score += 1.5 if model.supports_capability(Capability.TOOL_CALLING) else 0.0
            score += 1.0 if model.supports_capability(Capability.STRUCTURED_OUTPUT) else 0.0
            score += float(len(model.capabilities)) * 0.05
            score += 0.1 if model.context_length >= 64000 else 0.0
        elif policy == "low_cost":
            score += COST_RANK.get(model.cost_class, 0) * 2.0
        elif policy == "fastest":
            score += LATENCY_RANK.get(model.latency_class, 0) * 2.0
        elif policy == "private_only":
            pass  # filtering already handled separately
        elif policy in ("silverwing_first", "local_first"):
            score += 10.0 if model.deployment.value == "local" else 0.0
        else:  # balanced
            score += 1.0 if model.supports_capability(Capability.REASONING) else 0.0
            score += 0.5 if model.supports_capability(Capability.TOOL_CALLING) else 0.0
            score += LATENCY_RANK.get(model.latency_class, 0) * 0.4
            score += COST_RANK.get(model.cost_class, 0) * 0.2
        # task-quality modifier applies across policies
        if task.quality == "high":
            score += 2.0 if model.supports_capability(Capability.REASONING) else 0.0
            score += 1.0 if model.supports_capability(Capability.TOOL_CALLING) else 0.0
        if task.latency == "low":
            score += 1.5 if LATENCY_RANK.get(model.latency_class, 0) >= 3 else 0.0
        if task.cost_budget == "low":
            score += 3.0 if COST_RANK.get(model.cost_class, 0) >= 3 else 0.0
        return score


class ProviderRouter:
    """Plan a task onto a provider/model with an honest fallback chain."""

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        *,
        priority: Optional[str] = None,
        policy: str = "best_quality",
        telemetry: Optional[ProviderTelemetry] = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.policy = policy
        self.priority = priority or os.environ.get("JARVIS_PROVIDER_PRIORITY") or ""
        self._priority_ids = [
            p.strip().lower() for p in self.priority.split(",") if p.strip()
        ]
        self.telemetry = telemetry or get_telemetry()

    # -- candidate building -------------------------------------------------
    def candidates(
        self, task: TaskProfile, *, skip: tuple[str, ...] = ()
    ) -> list[RoutingCandidate]:
        candidates: list[RoutingCandidate] = []
        for adapter in self.registry.providers():
            if adapter.provider_id in skip or not adapter.configured:
                continue
            if not all(adapter.supports(c) for c in task.capabilities):
                continue
            health = adapter.health(force=False)
            if not health.is_healthy or health.models_found <= 0:
                continue
            for model in adapter.models:
                if not all(model.supports_capability(c) for c in task.capabilities):
                    continue
                score = PolicyEngine.score(adapter, model, task, self.policy)
                reasons = [c.value for c in task.capabilities]
                reason = f"declares all required capabilities ({', '.join(reasons)})"
                candidates.append(
                    RoutingCandidate(
                        adapter=adapter,
                        model=model,
                        reason=reason,
                        score=score,
                        inference_verified=health.inference_verified,
                    )
                )
        return candidates

    def _ordered(self, candidates: list[RoutingCandidate]) -> list[RoutingCandidate]:
        if self._priority_ids:
            def index_of(cand: RoutingCandidate) -> int:
                try:
                    return self._priority_ids.index(cand.adapter.provider_id)
                except ValueError:
                    return len(self._priority_ids)
            candidates = sorted(
                candidates,
                key=lambda c: (index_of(c), -c.score, c.adapter.provider_id, c.model.model_id),
            )
        else:
            candidates = sorted(
                candidates,
                key=lambda c: (
                    0 if c.inference_verified else 1,
                    -c.score,
                    c.adapter.provider_id,
                    c.model.model_id,
                ),
            )
        return candidates

    # -- privacy guard ---------------------------------------------------------
    def _privacy_compliant(self, candidates: list[RoutingCandidate], privacy: PrivacyClass) -> list[RoutingCandidate]:
        if privacy is PrivacyClass.PUBLIC:
            return candidates
        return [
            c
            for c in candidates
            if _model_privacy_satisfies(c.model, privacy)
        ]

    # -- routing ---------------------------------------------------------------
    def route(self, task: TaskProfile, *, skip: tuple[str, ...] = (), policy: Optional[str] = None) -> RoutingDecision:
        effective_policy = policy or self.policy
        decision = RoutingDecision(
            task_description=task.description,
            capabilities_required=serialize(task.capabilities),
            privacy=task.privacy.value,
            policy=effective_policy,
        )
        candidates = self.candidates(task, skip=skip)
        candidates = self._privacy_compliant(candidates, task.privacy)
        ordered = self._ordered(candidates)
        decision.candidate_count = len(ordered)

        if not ordered:
            decision.reason = (
                "no configured provider declares all required capabilities "
                f"({', '.join(decision.capabilities_required)})"
            )
            self._record(decision)
            return decision

        primary = ordered[0]
        decision.selected_provider = primary.adapter.provider_id
        decision.selected_model = primary.model.qualified_id
        if primary.model.pricing_per_1k[0] is not None and primary.model.pricing_per_1k[1] is not None:
            decision.pricing_per_1k = list(primary.model.pricing_per_1k)
        # cost is None by design when unknown (spec §34)
        decision.reason = primary.reason + f" ({effective_policy} policy)"

        for cand in ordered[1:6]:
            decision.fallback_chain.append(
                {
                    "provider": cand.adapter.provider_id,
                    "model": cand.model.qualified_id,
                    "reason": cand.reason,
                }
            )
        self._record(decision)
        return decision

    def route_text(
        self,
        task_text: str,
        classifier: Optional[TaskClassifier] = None,
        **kwargs,
    ) -> RoutingDecision:
        profile = (classifier or TaskClassifier()).classify(task_text)
        return self.route(profile, **kwargs)

    def _record(self, decision: RoutingDecision) -> None:
        self.telemetry.event(
            provider=decision.selected_provider or "",
            model=decision.selected_model or "",
            request_id=decision.request_id,
            kind="routing",
            status="routed" if decision.selected_provider else "no_route",
            privacy_class=decision.privacy,
            cost_estimate=decision.cost_estimate,
        )


def _model_privacy_satisfies(model: ProviderModel, required: PrivacyClass) -> bool:
    order = [
        PrivacyClass.PUBLIC,
        PrivacyClass.INTERNAL,
        PrivacyClass.PRIVATE,
        PrivacyClass.SENSITIVE,
        PrivacyClass.LOCAL_ONLY,
    ]
    rank = {p: i for i, p in enumerate(order)}
    if required is PrivacyClass.LOCAL_ONLY:
        return model.privacy_class is PrivacyClass.LOCAL_ONLY
    return rank.get(model.privacy_class, 0) <= rank.get(required, 0)


_router_lock = threading.Lock()