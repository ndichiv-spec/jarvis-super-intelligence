"""
Model Promotion Gate Workflow for JARVIS Control Plane.

Provides governance workflows for model promotion through lifecycle states:
- evaluating -> candidate -> approved -> deployed
- With blocking for failed evaluations

Phase 2 compliance:
- Validation of evaluation criteria
- Provenance verification
- Cost/benchmark evaluation
- Audit trail of all promotion decisions
- Policy enforcement for promotions
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("promotion_gate")

# --------------------------------------------------------------------------- #
# Promotion decision outcome
# --------------------------------------------------------------------------- #

class PromotionOutcome(str, Enum):
    """Outcome of a promotion decision."""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVAL = "needs_more_evaluation"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------- #
# Promotion criteria
# --------------------------------------------------------------------------- #

@dataclass
class EvaluationCriteria:
    """Criteria for model promotion decisions."""
    min_accuracy: Optional[float] = None
    min_pass_rate: Optional[float] = None
    max_latency_ms: Optional[int] = None
    min_throughput_tps: Optional[float] = None
    min_context_window: int = 0
    required_capabilities: List[str] = field(default_factory=list)
    allowed_modalities: List[str] = field(default_factory=lambda: ["text"])
    min_parameters: Optional[int] = None
    open_weights_required: bool = False
    verification_required: bool = False
    cost_policy: str = "best_quality"
    
    # Provenance requirements
    parent_model_required: bool = False
    dataset_traceable: bool = False
    training_run_required: bool = False


@dataclass
class PromotionDecision:
    """Result of a promotion gate evaluation."""
    model_id: str
    decision: PromotionOutcome
    from_status: str
    to_status: str
    criteria: EvaluationCriteria
    evaluated_at: float = field(default_factory=time.time)
    evaluator: str = ""
    reason: str = ""
    scores: Dict[str, float] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    approvers: List[str] = field(default_factory=list)
    rejected_by: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "decision": self.decision.value,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "criteria": {f.name: f.default for f in field(self.__class__.dataclass_fields_['criteria'])} if hasattr(field(self.__class__, 'criteria'), '__dataclass_fields__') else {},
            "evaluated_at": self.evaluated_at,
            "evaluator": self.evaluator,
            "reason": self.reason,
            "scores": self.scores,
            "evidence": self.evidence,
            "approvers": self.approvers,
            "rejected_by": self.rejected_by,
        }


# --------------------------------------------------------------------------- #
# Promotion Gate Service
# --------------------------------------------------------------------------- #

class PromotionGate:
    """
    Model promotion gate with validation and approval workflows.
    
    Governs model lifecycle transitions:
    - registered -> evaluating: Start evaluation
    - evaluating -> candidate: Evaluation results assessed
    - candidate -> approved: Promotion approved
    - approved -> deployed: Ready for production use
    - approved -> blocked: Evaluation failed, needs review
    """
    
    def __init__(self):
        self._model_registry = None
        self._provider_registry = None
        self._cost_tracker = None
        self._initialized = False
        self._decisions: Dict[str, List[PromotionDecision]] = {}
    
    def _ensure_initialized(self) -> None:
        """Lazy-load registry instances."""
        if self._initialized:
            return
        
        try:
            from infrastructure.model_registry import get_model_registry, ModelInfo, ModelLifecycleState
            from infrastructure.provider_registry import get_provider_registry
            from infrastructure.usage_accounting import CostTracker
            from infrastructure.audit_events import get_audit_service, audit_model_promotion
            
            self._model_registry = get_model_registry()
            self._provider_registry = get_provider_registry()
            self._cost_tracker = CostTracker()
            self._audit = get_audit_service()
            self._initialized = True
        except Exception as e:
            logger.warning(f"Failed to initialize promotion gate: {e}")
    
    def get_model_info(self, model_id: str) -> Optional[Any]:
        """Get model info from registry."""
        if not self._model_registry:
            self._ensure_initialized()
        if self._model_registry:
            return self._model_registry.get(model_id)
        return None
    
    def evaluate_for_promotion(
        self,
        model_id: str,
        criteria: EvaluationCriteria,
        evaluator: str = "system",
    ) -> Tuple[PromotionOutcome, Dict[str, Any]]:
        """
        Evaluate a model against promotion criteria.
        
        Returns (outcome, evidence) tuple.
        """
        self._ensure_initialized()
        
        model = self.get_model_info(model_id)
        if not model:
            return PromotionOutcome.REJECTED, {"error": "Model not found"}
        
        scores: Dict[str, float] = {}
        evidence: Dict[str, Any] = {}
        passed: List[str] = []
        failed: List[str] = []
        
        # Accuracy check
        if criteria.min_accuracy is not None:
            accuracy = model.evaluation_results.get("accuracy", 0.0)
            scores["accuracy"] = accuracy
            if accuracy >= criteria.min_accuracy:
                passed.append(f"accuracy>= {criteria.min_accuracy}")
            else:
                failed.append(f"accuracy {accuracy} < {criteria.min_accuracy}")
        
        # Pass rate check
        if criteria.min_pass_rate is not None:
            pass_rate = model.evaluation_results.get("pass_rate", 0.0)
            scores["pass_rate"] = pass_rate
            if pass_rate >= criteria.min_pass_rate:
                passed.append(f"pass_rate>= {criteria.min_pass_rate}")
            else:
                failed.append(f"pass_rate {pass_rate} < {criteria.min_pass_rate}")
        
        # Latency check
        if criteria.max_latency_ms is not None:
            latency = model.evaluation_results.get("latency_ms", 0)
            scores["latency_ms"] = latency
            if latency <= criteria.max_latency_ms:
                passed.append(f"latency<={criteria.max_latency_ms}ms")
            else:
                failed.append(f"latency {latency}ms > {criteria.max_latency_ms}ms")
        
        # Context window check
        if criteria.min_context_window > 0:
            scores["context_window"] = float(model.context_window)
            if model.context_window >= criteria.min_context_window:
                passed.append(f"context_window>={criteria.min_context_window}")
            else:
                failed.append(f"context_window {model.context_window} < {criteria.min_context_window}")
        
        # Parameters check
        if criteria.min_parameters is not None and model.parameters:
            scores["parameters"] = float(model.parameters)
            if model.parameters >= criteria.min_parameters:
                passed.append(f"parameters>={criteria.min_parameters}")
            else:
                failed.append(f"parameters {model.parameters} < {criteria.min_parameters}")
        
        # Capabilities check
        if criteria.required_capabilities:
            missing_caps = [
                c for c in criteria.required_capabilities
                if c not in (model.capabilities or [])
            ]
            if not missing_caps:
                passed.append(f"has_capabilities {criteria.required_capabilities}")
            else:
                failed.append(f"missing_capabilities {missing_caps}")
        
        # Modalities check
        if criteria.allowed_modalities:
            model_modalities = set(model.modalities or ["text"])
            if model_modalities.issubset(set(criteria.allowed_modalities)):
                passed.append(f"modalities_ok {list(model_modalities)}")
            else:
                failed.append(f"modalities {list(model_modalities)} not in {criteria.allowed_modalities}")
        
        # Provenance check
        if criteria.parent_model_required and not model.parent_model_id:
            failed.append("parent_model_required")
        else:
            passed.append("has_parent_model")
        
        if criteria.dataset_traceable and not model.metadata.get("dataset_id"):
            failed.append("dataset_not_traceable")
        else:
            passed.append("dataset_traceable")
        
        # Store evidence
        evidence = {
            "scores": scores,
            "passed": passed,
            "failed": failed,
            "model_metadata": {
                "lifecycle_status": model.lifecycle_status,
                "capabilities": model.capabilities,
                "evaluation_results": model.evaluation_results,
            },
        }
        
        # Determine outcome
        if failed:
            outcome = PromotionOutcome.BLOCKED
            reason = f"Failed criteria: {', '.join(failed)}"
        elif not passed:
            outcome = PromotionOutcome.NEEDS_MORE_EVAL
            reason = "No criteria met, needs more evaluation data"
        else:
            outcome = PromotionOutcome.APPROVED
            reason = f"All criteria met: {', '.join(passed)}"
        
        return outcome, evidence
    
    def promote_model(
        self,
        model_id: str,
        current_status: str,
        target_status: str,
        criteria: Optional[EvaluationCriteria] = None,
        evaluator: str = "system",
        approvers: Optional[List[str]] = None,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Promote a model through the lifecycle.
        
        Returns (success, message) tuple.
        """
        self._ensure_initialized()
        
        valid_transitions = {
            "registered": ["evaluating", "blocked", "retired"],
            "evaluating": ["candidate", "blocked", "retired"],
            "candidate": ["approved", "blocked", "retired"],
            "approved": ["deployed", "deprecated", "retired"],
            "deployed": ["deprecated", "retired"],
            "deprecated": ["retired"],
            "blocked": ["retired"],
            "evaluating": ["approved"],  # Direct eval -> approved
        }
        
        if current_status not in valid_transitions:
            return False, f"Invalid current status: {current_status}"
        
        if target_status not in valid_transitions.get(current_status, []):
            return False, f"Invalid transition from {current_status} to {target_status}"
        
        # For candidate -> approved, evaluate criteria
        if current_status == "candidate" and target_status == "approved":
            if criteria:
                outcome, eval_evidence = self.evaluate_for_promotion(
                    model_id, criteria, evaluator
                )
                if outcome != PromotionOutcome.APPROVED:
                    return False, f"Promotion blocked: {eval_evidence.get('failed', [])}"
                
                evidence = eval_evidence
        
        # Update model lifecycle
        if not self._model_registry:
            return False, "Model registry not available"
        
        history_entry = {
            "at": time.time(),
            "status": target_status,
            "reason": reason,
            "evaluator": evaluator,
            "approvers": approvers or [],
        }
        
        success = self._model_registry.update_lifecycle(
            model_id,
            target_status,
            reason=reason,
            actor=evaluator,
        )
        
        if success:
            # Record the decision
            decision = PromotionDecision(
                model_id=model_id,
                decision=PromotionOutcome(target_status.lower()),
                from_status=current_status,
                to_status=target_status,
                criteria=criteria or EvaluationCriteria(),
                evaluator=evaluator,
                reason=reason,
                evidence=evidence or {},
                approvers=approvers or [],
            )
            
            if model_id not in self._decisions:
                self._decisions[model_id] = []
            self._decisions[model_id].append(decision)
            
            # Log audit event
            if self._audit:
                self._audit.record(
                    event_type="model.promotion",
                    category="model_registry",
                    severity="info",
                    action=f"promote_{current_status}_to_{target_status}",
                    result="success",
                    resource_type="model",
                    resource_id=model_id,
                    message=reason,
                    user_id=evaluator,
                    metadata={"approvers": approvers},
                )
        
        return success, success and "Promotion successful" or "Promotion failed"
    
    def block_model(
        self,
        model_id: str,
        reason: str,
        evaluator: str = "system",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Block a model that has failed evaluation or has issues."""
        self._ensure_initialized()
        
        model = self.get_model_info(model_id)
        if not model:
            return False
        
        success = self._model_registry.update_lifecycle(
            model_id,
            "blocked",
            reason=f"Blocked: {reason}",
            actor=evaluator,
        )
        
        if success:
            # Log audit event
            if self._audit:
                self._audit.record(
                    event_type="model.blocked",
                    category="model_registry",
                    severity="warning",
                    action="block_model",
                    result="success",
                    resource_type="model",
                    resource_id=model_id,
                    message=reason,
                    user_id=evaluator,
                    metadata={"evidence": evidence},
                )
        
        return success
    
    def approve_model(self, model_id: str, approver: str, reason: str = "") -> bool:
        """Manually approve a candidate model."""
        self._ensure_initialized()
        
        model = self.get_model_info(model_id)
        if not model:
            return False
        
        if model.lifecycle_status != "candidate":
            return False, "Model must be in 'candidate' status to approve"
        
        return self.promote_model(
            model_id,
            current_status="candidate",
            target_status="approved",
            evaluator=approver,
            reason=reason or "Manual approval",
        )[0]
    
    def deploy_model(self, model_id: str, deployer: str) -> bool:
        """Deploy an approved model to production."""
        self._ensure_initialized()
        
        model = self.get_model_info(model_id)
        if not model:
            return False
        
        if model.lifecycle_status != "approved":
            return False, "Model must be 'approved' to deploy"
        
        return self.promote_model(
            model_id,
            current_status="approved",
            target_status="deployed",
            evaluator=deployer,
            reason="Deployment to production",
        )[0]
    
    def get_promotion_history(self, model_id: str) -> List[Dict[str, Any]]:
        """Get promotion history for a model."""
        if model_id in self._decisions:
            return [d.to_dict() for d in self._decisions[model_id]]
        return []
    
    def list_blocked_models(self) -> List[str]:
        """List all blocked models."""
        self._ensure_initialized()
        
        if not self._model_registry:
            return []
        
        models = self._model_registry.list_models(lifecycle_status="blocked")
        return [m.model_id for m in models]


# --------------------------------------------------------------------------- #
# Global instance
# --------------------------------------------------------------------------- #

_promotion_gate: Optional[PromotionGate] = None


def get_promotion_gate() -> PromotionGate:
    """Get the global promotion gate instance."""
    global _promotion_gate
    if _promotion_gate is None:
        _promotion_gate = PromotionGate()
    return _promotion_gate


# --------------------------------------------------------------------------- #
# Pre-configured criteria profiles
# --------------------------------------------------------------------------- #

def get_default_criteria() -> EvaluationCriteria:
    """Get default evaluation criteria for general use."""
    return EvaluationCriteria(
        min_accuracy=0.7,
        min_pass_rate=0.8,
        max_latency_ms=5000,
        min_throughput_tps=1.0,
        required_capabilities=["chat", "completion"],
        open_weights_required=False,
    )


def get_reasoning_criteria() -> EvaluationCriteria:
    """Get criteria optimized for reasoning models."""
    return EvaluationCriteria(
        min_accuracy=0.85,
        min_pass_rate=0.9,
        max_latency_ms=10000,
        required_capabilities=["reasoning", "chat"],
        parent_model_required=True,
        dataset_traceable=True,
    )


def get_vision_criteria() -> EvaluationCriteria:
    """Get criteria for vision models."""
    return EvaluationCriteria(
        min_accuracy=0.7,
        min_context_window=16384,
        allowed_modalities=["text", "image"],
        required_capabilities=["vision", "chat"],
    )


def get_cost_efficient_criteria() -> EvaluationCriteria:
    """Get criteria for cost-efficient deployment."""
    return EvaluationCriteria(
        min_accuracy=0.65,
        open_weights_required=True,
        cost_policy="free_only",
    )


def get_high_quality_criteria() -> EvaluationCriteria:
    """Get criteria for high-quality/canonical models."""
    return EvaluationCriteria(
        min_accuracy=0.9,
        min_pass_rate=0.95,
        required_capabilities=["chat", "completion", "reasoning"],
        verification_required=True,
    )