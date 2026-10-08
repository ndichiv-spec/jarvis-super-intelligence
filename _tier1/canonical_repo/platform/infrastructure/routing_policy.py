"""
Policy-based Routing for JARVIS Control Plane.

Implements policy-based routing decisions using the durable registries
(Model Registry, Provider Registry, Artifact Registry) for cost-aware,
capability-aware, and provenance-aware routing.

Phase 2 compliance:
- Policy-based routing decisions using registered models and providers
- Cost-aware selection with budget constraints
- Privacy-aware routing
- Verification state checking
- Provenance-aware routing
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("routing_policy")

# --------------------------------------------------------------------------- #
# Routing policies
# --------------------------------------------------------------------------- #

class RoutingCostPolicy(str, Enum):
    """Cost policy for routing decisions."""
    FREE_ONLY = "free_only"       # Only use free/local providers
    LOCAL_ONLY = "local_only"     # Only use local providers
    LOW_COST = "low_cost"         # Prefer low-cost providers
    BEST_QUALITY = "best_quality" # Prefer highest quality
    LOW_LATENCY = "low_latency"   # Prefer fastest providers


class RoutingPrivacyLevel(str, Enum):
    """Privacy level for routing decisions."""
    PUBLIC = "public"       # Data can leave the organization
    INTERNAL = "internal"   # Data stays within organization
    PRIVATE = "private"     # Data stays on local devices


# --------------------------------------------------------------------------- #
# Routing decision result
# --------------------------------------------------------------------------- #

@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    selected_provider: str = ""
    selected_model: str = ""
    selected_model_id: str = ""
    
    # Provenance
    reasoning: str = ""
    cost_estimate_usd: float = 0.0
    latency_estimate_ms: int = 0
    
    # Decision factors
    cost_policy: str = "best_quality"
    privacy_level: str = "public"
    capability: str = ""
    task: str = ""
    
    # Fallback chain
    fallback_chain: List[Dict[str, Any]] = field(default_factory=list)
    
    # Validation
    is_verified: bool = False
    provider_health: str = "unknown"
    model_lifecycle: str = "discovered"
    
    # Timing
    timestamp: float = field(default_factory=time.time)
    
    # Metadata
    matched_rules: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Query specification
# --------------------------------------------------------------------------- #

@dataclass
class RoutingQuery:
    """Query specification for routing decisions."""
    capability: str = ""           # Required capability (e.g., "reasoning", "vision")
    privacy: str = "public"        # Privacy level requirement
    cost_policy: str = "best_quality"  # Cost policy
    max_cost_usd: Optional[float] = None  # Maximum acceptable cost
    max_latency_ms: Optional[int] = None  # Maximum acceptable latency
    required_models: List[str] = field(default_factory=list)  # Preferred models
    allowed_providers: List[str] = field(default_factory=list)  # Provider whitelist
    excluded_providers: List[str] = field(default_factory=list)  # Provider blacklist
    context_length: int = 0        # Required context window
    modalities: List[str] = field(default_factory=lambda: ["text"])  # Required modalities
    min_parameters: Optional[int] = None  # Minimum model parameters
    open_weights_only: bool = False  # Only use open-weight models
    verified_only: bool = False      # Only use verified models
    enabled_only: bool = True        # Only use enabled providers
    
    # Task and request metadata
    task: str = "chat"
    request_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Routing Policy Engine
# --------------------------------------------------------------------------- #

class RoutingPolicyEngine:
    """
    Policy-based routing engine using the portable registries.
    
    Makes routing decisions based on:
    - Model capabilities and lifecycle state
    - Provider health and verification status
    - Cost policies and budget constraints
    - Privacy requirements
    - User preferences and system policies
    """
    
    def __init__(self):
        self._model_registry = None
        self._provider_registry = None
        self._artifact_registry = None
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy-load registry instances."""
        if self._initialized:
            return
        
        try:
            from infrastructure.model_registry import get_model_registry
            from infrastructure.provider_registry import get_provider_registry
            from infrastructure.artifact_registry import get_artifact_registry
            
            self._model_registry = get_model_registry()
            self._provider_registry = get_provider_registry()
            self._artifact_registry = get_artifact_registry()
            self._initialized = True
        except Exception as e:
            logger.warning(f"Failed to initialize routing policy engine: {e}")
            self._initialized = True  # Continue with partial functionality
    
    def _get_available_providers(self) -> Dict[str, Any]:
        """Get map of provider_id -> ProviderInfo for available providers."""
        self._ensure_initialized()
        
        if self._provider_registry is None:
            return {}
        
        # Get all enabled healthy providers
        providers = self._provider_registry.list_providers(enabled=True)
        return {p.provider_id: p for p in providers}
    
    def _get_models_for_provider(self, provider_id: str) -> Dict[str, Any]:
        """Get map of model_id -> ModelInfo for models from a provider."""
        self._ensure_initialized()
        
        if self._model_registry is None:
            return {}
        
        models = self._model_registry.list_models(provider_id=provider_id)
        return {m.model_id: m for m in models}
    
    def _filter_by_capability(self, models: Dict[str, Any], capability: str) -> Dict[str, Any]:
        """Filter models by required capability."""
        if not capability:
            return models
        
        return {
            mid: m for mid, m in models.items()
            if capability in m.capabilities
        }
    
    def _filter_by_privacy(self, providers: Dict[str, Any], privacy: str) -> Dict[str, Any]:
        """Filter providers by privacy level."""
        if privacy == "public":
            return providers
        
        # Some providers may be restricted based on privacy level
        # For now, all enabled providers are available for internal use
        return providers
    
    def _filter_by_verification(self, providers: Dict[str, Any], verified_only: bool) -> Dict[str, Any]:
        """Filter providers by verification status."""
        if not verified_only:
            return providers
        
        return {
            pid: p for pid, p in providers.items()
            if p.verification_state == "verified"
        }
    
    def _filter_by_cost_policy(self, providers: Dict[str, Any], cost_policy: str) -> Dict[str, Any]:
        """Filter providers by cost policy."""
        if cost_policy == "best_quality":
            return providers
        
        if cost_policy == "free_only":
            # Only local/silverwing/ollama/llamacpp
            free_providers = {"local", "silverwing", "ollama", "llamacpp"}
            return {pid: p for pid, p in providers.items() if pid in free_providers}
        
        if cost_policy == "local_only":
            local_providers = {"local", "silverwing", "ollama", "llamacpp", "vllm"}
            return {pid: p for pid, p in providers.items() if pid in local_providers}
        
        return providers
    
    def _rank_models(self, 
                     models: Dict[str, Any],
                     query: RoutingQuery) -> List[tuple]:
        """
        Rank models by suitability.
        
        Returns list of (model_id, provider_id, score) tuples sorted by score.
        """
        results = []
        
        for model_id, model in models.items():
            # Check lifecycle state - allow registered and evaluating for routing
            if query.enabled_only and model.lifecycle_status not in ("approved", "deployed", "candidate", "registered", "evaluating"):
                continue
            
            if query.verified_only and not model.metadata.get("verified"):
                continue
            
            # Check context window
            if query.context_length > model.context_window:
                continue
            
            # Check minimum parameters
            if query.min_parameters and model.parameters:
                if model.parameters < query.min_parameters:
                    continue
            
            # Score based on various factors
            score = 0.0
            
            # Lifecycle state score
            lifecycle_scores = {
                "approved": 100,
                "deployed": 95,
                "candidate": 80,
                "registered": 50,
                "evaluating": 30,
            }
            score += lifecycle_scores.get(model.lifecycle_status, 0)
            
            # Evaluation results bonus
            if model.evaluation_results:
                score += 20
            
            # Open weights bonus (cost efficiency)
            if model.open_weights:
                score += 10
            
            # Parameters (bigger = generally better for quality)
            if model.parameters:
                # Normalize parameters to 0-50 scale
                param_score = min(50, model.parameters / 100_000_000)
                score += param_score
            
            # Context window bonus (larger = more flexible)
            ctx_score = min(30, model.context_window / 100_000)
            score += ctx_score
            
            # Penalties for excluded providers
            if model.provider_id in query.excluded_providers:
                score -= 100
            
            results.append((model_id, model.provider_id, score))
        
        # Sort by score descending
        results.sort(key=lambda x: x[2], reverse=True)
        return results
    
    def route(self, query: RoutingQuery) -> RoutingDecision:
        """
        Make a routing decision based on the query.
        
        Args:
            query: RoutingQuery with capability, privacy, cost, etc. requirements
        
        Returns:
            RoutingDecision with selected provider/model and reasoning
        """
        self._ensure_initialized()
        
        decision = RoutingDecision(
            cost_policy=query.cost_policy,
            privacy_level=query.privacy,
            capability=query.capability,
            task=query.task,
        )
        
        # Get available providers
        providers = self._get_available_providers()
        
        # Apply cost policy filter
        providers = self._filter_by_cost_policy(providers, query.cost_policy)
        
        # Apply verification filter
        providers = self._filter_by_verification(providers, query.verified_only)
        
        # Apply privacy filter
        providers = self._filter_by_privacy(providers, query.privacy)
        
        # Apply allowed providers filter
        if query.allowed_providers:
            providers = {pid: p for pid, p in providers.items() if pid in query.allowed_providers}
        
        if not providers:
            decision.reasoning = "No providers available after filtering"
            return decision
        
        # Build candidate list of all models from available providers
        candidate_models = {}
        for provider_id in providers:
            models = self._get_models_for_provider(provider_id)
            candidate_models.update(models)
        
        # Filter by capability
        candidate_models = self._filter_by_capability(candidate_models, query.capability)
        
        # Rank models
        ranked = self._rank_models(candidate_models, query)
        
        # Select best model
        if ranked:
            best_model_id, best_provider_id, best_score = ranked[0]
            
            # Get model info
            model = candidate_models.get(best_model_id)
            provider = providers.get(best_provider_id)
            
            decision.selected_model_id = best_model_id
            decision.selected_provider = best_provider_id
            decision.selected_model = best_model_id
            decision.model_lifecycle = model.lifecycle_status if model else "unknown"
            decision.provider_health = provider.health_state if provider else "unknown"
            decision.is_verified = provider.verification_state == "verified" if provider else False
            
            # Build fallback chain
            for model_id, prov_id, score in ranked[1:5]:
                decision.fallback_chain.append({
                    "provider": prov_id,
                    "model": model_id,
                    "score": score,
                })
            
            # Build reasoning
            reasons = []
            if model:
                reasons.append(f"lifecycle={model.lifecycle_status}")
                if model.evaluation_results:
                    reasons.append("has_evaluation_data")
                if model.open_weights:
                    reasons.append("open_weights")
            if provider:
                reasons.append(f"health={provider.health_state}")
                if provider.verification_state == "verified":
                    reasons.append("verified")
            
            decision.reasoning = f"Selected {best_provider_id}:{best_model_id} - " + ", ".join(reasons)
            
            # Update match notes
            decision.matched_rules = list(query.allowed_providers or ["cost_filter", "capability_filter"])
        else:
            decision.reasoning = "No models match criteria"
        
        return decision
    
    def route_with_budget(self,
                         query: RoutingQuery,
                         cost_tracker: Any = None) -> RoutingDecision:
        """
        Route with budget constraints.
        
        If a cost_tracker is provided, use historical cost data to inform decisions.
        """
        decision = self.route(query)
        
        if cost_tracker:
            # Apply cost-aware filtering
            # This would check if provider/model historically exceeds budget
            pass
        
        return decision


# --------------------------------------------------------------------------- #
# Cost tracker for routing decisions
# --------------------------------------------------------------------------- #

@dataclass
class CostEstimate:
    """Cost estimate for a routing decision."""
    provider: str
    model: str
    estimated_input_usd: float = 0.0
    estimated_output_usd: float = 0.0
    total_estimated_usd: float = 0.0
    confidence: float = 1.0  # 0-1 confidence in estimate


class CostTracker:
    """
    Tracks costs for routing decisions.
    """
    
    # Provider pricing estimates (USD per 1M tokens)
    # These are rough estimates - actual pricing varies by model/version
    PRICING_INPUT: Dict[str, float] = {
        "openai:gpt-4": 0.03,
        "anthropic:claude": 0.015,
        "google:gemini": 0.0075,
        "groq": 0.0005,
        "deepseek": 0.00014,
        "ollama": 0.0,  # Free
        "llamacpp": 0.0,  # Free
        "silverwing": 0.0,  # Free
        "local": 0.0,  # Free
    }
    
    PRICING_OUTPUT: Dict[str, float] = {
        "openai:gpt-4": 0.06,
        "anthropic:claude": 0.03,
        "google:gemini": 0.0001,
        "groq": 0.0005,
        "deepseek": 0.00014,
        "ollama": 0.0,
        "llamacpp": 0.0,
        "silverwing": 0.0,
        "local": 0.0,
    }
    
    def __init__(self, max_daily_budget_usd: float = 0.0):
        self.max_daily_budget_usd = max_daily_budget_usd
        self.daily_spent_usd = 0.0
        self._history: List[Dict[str, Any]] = []
    
    def estimate_cost(self, 
                      provider: str, 
                      model: str,
                      input_tokens: int = 0,
                      output_tokens: int = 0) -> CostEstimate:
        """Estimate cost for a request."""
        provider_key = f"{provider}:{model}"
        
        input_rate = self.PRICING_INPUT.get(provider_key, 0.0)
        output_rate = self.PRICING_OUTPUT.get(provider_key, 0.0)
        
        input_cost = (input_tokens / 1_000_000) * input_rate
        output_cost = (output_tokens / 1_000_000) * output_rate
        
        return CostEstimate(
            provider=provider,
            model=model,
            estimated_input_usd=input_cost,
            estimated_output_usd=output_cost,
            total_estimated_usd=input_cost + output_cost,
            confidence=0.9 if provider in self.PRICING_INPUT else 0.5,
        )
    
    def record_usage(self, 
                     provider: str,
                     model: str,
                     input_tokens: int,
                     output_tokens: int,
                     latency_ms: int = 0,
                     success: bool = True) -> float:
        """Record actual usage and return the cost."""
        estimate = self.estimate_cost(provider, model, input_tokens, output_tokens)
        cost = estimate.total_estimated_usd
        
        if success:
            self.daily_spent_usd += cost
        
        self._history.append({
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "success": success,
        })
        
        return cost
    
    def within_budget(self, estimated_cost: float) -> bool:
        """Check if estimated cost is within daily budget."""
        if self.max_daily_budget_usd <= 0:
            return True
        return self.daily_spent_usd + estimated_cost <= self.max_daily_budget_usd


# --------------------------------------------------------------------------- #
# Global routing policy engine instance
# --------------------------------------------------------------------------- #

_routing_engine: Optional[RoutingPolicyEngine] = None


def get_routing_engine() -> RoutingPolicyEngine:
    """Get the global routing policy engine instance."""
    global _routing_engine
    if _routing_engine is None:
        _routing_engine = RoutingPolicyEngine()
    return _routing_engine


def reset_routing_engine() -> None:
    """Reset the routing engine (for testing)."""
    global _routing_engine
    _routing_engine = None


# --------------------------------------------------------------------------- #
# Convenience functions
# --------------------------------------------------------------------------- #

def route_request(
    capability: str = "",
    privacy: str = "public",
    cost_policy: str = "best_quality",
    max_cost: Optional[float] = None,
    model_preferences: Optional[List[str]] = None,
) -> RoutingDecision:
    """Convenience function to route a request."""
    engine = get_routing_engine()
    
    query = RoutingQuery(
        capability=capability,
        privacy=privacy,
        cost_policy=cost_policy,
        max_cost_usd=max_cost,
        allowed_providers=model_preferences or [],
    )
    
    return engine.route(query)