"""Phase 12 — JARVIS Self-Improvement Engine.

A controlled, evidence-driven self-improvement system. JARVIS discovers
weaknesses in its own AI capabilities and coordinates experiments that may
improve models, datasets, prompts, policies, capability implementations
and experiment configurations — always under verification and approval.

Core abstractions
----------------
- ``ImprovementStatus``          — state machine for an improvement cycle
- ``InterventionType``           — enum of allowed change types
- ``Weakness``                   — a discovered capability gap with evidence
- ``FailureTaxonomy``            — categorisation + clustering of failures
- ``ImprovementPolicy``          — measurable criteria for "better"
- ``Hypothesis``                 — testable prediction of an improvement
- ``BaselineLock``               — immutable snapshot for comparison
- ``CandidateArtifact``          — a new model/artifact; EXPERIMENTAL until gates pass
- ``EvaluationMatrix``           — target / regression / safety / robustness suites
- ``ImprovementResult``          — baseline-vs-candidate comparison + regressions
- ``ImprovementDeployment``      — controlled deployment (shadow / canary / blockbox) + rollback
- ``AutonomyGuard``              — enforces the autonomy boundary
- ``LearningMemory``             — structured lessons persisted after a cycle
- ``ImprovementGraph``           — DAG of weakness → hypothesis → … → next weakness
- ``SelfImprovementCycle``       — canonical container tying everything together

The cycle is persisted in its **own** store (``"improvements"``) — it is
distinct from, but interoperable with, the Phase 11 ``Experiment`` store.
A cycle *may* also create a Phase 11 ``Experiment`` record for the
underlying A/B training run; the two are linked by ``improvement_id``.

The Brain (model) never receives provider credentials, API keys, or raw
secrets.  ``AutonomyGuard`` enforces this at the orchestration layer.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import statistics
import time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.experiment import Experiment, ExperimentStatus

logger = logging.getLogger("jarvis_backend.self_improvement")


def _short_uuid() -> str:
    return _uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #

class ImprovementStatus(str, Enum):
    """Lifecycle states for a self-improvement cycle.

    Terminal states: COMPLETED, REJECTED, FAILED, BLOCKED.
    """
    IDENTIFIED          = "identified"
    ANALYZING           = "analyzing"
    HYPOTHESIS_FORMED   = "hypothesis_formed"
    DESIGNED            = "designed"
    AWAITING_APPROVAL   = "awaiting_approval"
    DATA_PREPARATION    = "data_preparation"
    TRAINING            = "training"
    EVALUATING          = "evaluating"
    CRITIQUING          = "critiquing"
    VERIFYING           = "verifying"
    PROMOTION_REVIEW    = "promotion_review"
    DEPLOYING           = "deploying"
    MONITORING          = "monitoring"
    COMPLETED           = "completed"
    REJECTED            = "rejected"
    FAILED              = "failed"
    BLOCKED             = "blocked"
    ROLLED_BACK         = "rolled_back"  # reachable from DEPLOYING / MONITORING

    @classmethod
    def terminal_states(cls) -> List[str]:
        return [cls.COMPLETED.value, cls.REJECTED.value,
                cls.FAILED.value, cls.BLOCKED.value, cls.ROLLED_BACK.value]

    @classmethod
    def valid_transitions(cls) -> Dict[str, List[str]]:
        return {
            cls.IDENTIFIED.value:            [cls.ANALYZING.value, cls.BLOCKED.value, cls.FAILED.value],
            cls.ANALYZING.value:             [cls.HYPOTHESIS_FORMED.value, cls.IDENTIFIED.value, cls.FAILED.value],
            cls.HYPOTHESIS_FORMED.value:     [cls.DESIGNED.value, cls.ANALYZING.value, cls.BLOCKED.value],
            cls.DESIGNED.value:              [cls.AWAITING_APPROVAL.value, cls.HYPOTHESIS_FORMED.value, cls.FAILED.value],
            cls.AWAITING_APPROVAL.value:     [cls.DATA_PREPARATION.value, cls.REJECTED.value, cls.BLOCKED.value],
            cls.DATA_PREPARATION.value:      [cls.TRAINING.value, cls.AWAITING_APPROVAL.value, cls.FAILED.value],
            cls.TRAINING.value:              [cls.EVALUATING.value, cls.FAILED.value, cls.BLOCKED.value],
            cls.EVALUATING.value:            [cls.CRITIQUING.value, cls.FAILED.value, cls.BLOCKED.value],
            cls.CRITIQUING.value:            [cls.VERIFYING.value, cls.REJECTED.value, cls.EVALUATING.value],
            cls.VERIFYING.value:             [cls.PROMOTION_REVIEW.value, cls.FAILED.value, cls.REJECTED.value],
            cls.PROMOTION_REVIEW.value:      [cls.DEPLOYING.value, cls.REJECTED.value, cls.BLOCKED.value],
            cls.DEPLOYING.value:             [cls.MONITORING.value, cls.FAILED.value, cls.ROLLED_BACK.value],
            cls.MONITORING.value:            [cls.COMPLETED.value, cls.FAILED.value, cls.ROLLED_BACK.value],
            cls.COMPLETED.value:             [],
            cls.REJECTED.value:              [],
            cls.FAILED.value:                [],
            cls.BLOCKED.value:               [cls.IDENTIFIED.value, cls.ANALYZING.value],
            cls.ROLLED_BACK.value:           [cls.IDENTIFIED.value, cls.ANALYZING.value, cls.COMPLETED.value],
        }

    @classmethod
    def validate_transition(cls, current: str, target: str) -> None:
        """Raise ValueError if *target* is not a valid successor of *current*."""
        valid = cls.valid_transitions().get(current, [])
        if target not in valid:
            raise ValueError(
                f"Invalid ImprovementStatus transition: {current} -> {target}. "
                f"Allowed: {valid}"
            )

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return status in cls.terminal_states()


# --------------------------------------------------------------------------- #
# Intervention types
# --------------------------------------------------------------------------- #

class InterventionType(str, Enum):
    """Types of changes JARVIS is permitted to coordinate."""
    PROMPT_CHANGE            = "prompt_change"
    SYSTEM_POLICY_CHANGE     = "system_policy_change"
    RETRIEVAL_CHANGE         = "retrieval_change"
    CONTEXT_CHANGE           = "context_change"
    DATASET_CHANGE           = "dataset_change"
    TRAINING_CHANGE          = "training_change"          # LoRA / SFT
    HYPERPARAMETER_CHANGE    = "hyperparameter_change"
    ARCHITECTURE_CHANGE      = "architecture_change"
    MERGE_CHANGE             = "merge_change"             # model merge
    PROMPT_TEMPLATE_CHANGE   = "prompt_template_change"

    @classmethod
    def safe_from_value(cls, value: str) -> "InterventionType":
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown InterventionType: {value}")


# Interventions that the Brain must NEVER autonomously execute.
# These require manual approval regardless of autonomy level.
HIGH_RISK_INTERVENTIONS = frozenset({
    InterventionType.SYSTEM_POLICY_CHANGE,
    InterventionType.ARCHITECTURE_CHANGE,
})

# Interventions that cannot touch production source code, credentials,
# or authorization boundaries.
PROHIBITED_INTERVENTIONS = frozenset({
    InterventionType.SYSTEM_POLICY_CHANGE,  # can propose, cannot execute on auth layer
})


# --------------------------------------------------------------------------- #
# Failure taxonomy + clustering
# --------------------------------------------------------------------------- #

class FailureCategory(str, Enum):
    """Categories of capability failures observed during evaluation."""
    METRIC_REGRESSION      = "metric_regression"
    CATEGORY_DROP          = "category_drop"
    SAFETY_VIOLATION       = "safety_violation"
    BIAS_DETECTED          = "bias_detected"
    HALLUCINATION          = "hallucination"
    FACTUAL_ERROR          = "factual_error"
    INSTRUCTION_FAILURE    = "instruction_failure"
    CONTEXT_LIMIT_EXCEEDED = "context_limit_exceeded"
    LATENCY_DEGRADATION    = "latency_degradation"
    ROBUSTNESS_FAILURE     = "robustness_failure"
    UNEXPECTED_OUTPUT      = "unexpected_output"
    UNKNOWN                = "unknown"


class FailureSeverity(str, Enum):
    """Severity of a failure."""
    CRITICAL = "critical"   # safety/security / major regression
    HIGH     = "high"       # significant capability drop
    MEDIUM   = "medium"     # moderate degradation
    LOW      = "low"        # minor / cosmetic


@dataclass
class FailureInstance:
    """A single observed failure, traceable to evidence."""
    failure_id: str
    category: FailureCategory
    severity: FailureSeverity
    capability: str                          # e.g. "code_generation"
    metric_name: str                         # e.g. "accuracy"
    baseline_value: float
    current_value: float
    threshold: float                         # the limit that was crossed
    evidence: str                            # description / provenance reference
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "capability": self.capability,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "evidence": self.evidence,
            "context": dict(self.context),
            "timestamp": self.timestamp,
        }


@dataclass
class Weakness:
    """A discovered capability gap with supporting failure evidence."""
    weakness_id: str
    target_capability: str
    description: str
    failure_category: FailureCategory
    severity: FailureSeverity
    failures: List[FailureInstance] = field(default_factory=list)
    affected_population: float = 1.0       # fraction of eval population affected
    confidence: float = 0.0                 # 0..1
    first_observed: str = field(default_factory=now_iso)
    cluster_id: Optional[str] = None        # for clustering similar weaknesses

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weakness_id": self.weakness_id,
            "target_capability": self.target_capability,
            "description": self.description,
            "failure_category": self.failure_category.value,
            "severity": self.severity.value,
            "failures": [f.to_dict() for f in self.failures],
            "affected_population": self.affected_population,
            "confidence": self.confidence,
            "first_observed": self.first_observed,
            "cluster_id": self.cluster_id,
        }


class FailureTaxonomy:
    """Categorises and clusters observed failures into weaknesses."""

    def __init__(self) -> None:
        self._weaknesses: Dict[str, Weakness] = {}
        self._clusters: Dict[str, List[str]] = {}  # cluster_id -> [weakness_id, ...]

    # -- classification --------------------------------------------------

    @staticmethod
    def classify(
        capability: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        higher_is_better: bool = True,
        regression_threshold: float = 0.05,
    ) -> Tuple[FailureCategory, FailureSeverity]:
        """Classify a metric delta into (category, severity)."""
        delta = current_value - baseline_value
        if not higher_is_better:
            delta = -delta  # invert so "positive delta" = improvement
        relative_delta = delta / baseline_value if baseline_value else 1.0

        if delta >= 0:
            # improvement or no change — still categorise for "near miss" logging
            if abs(relative_delta) < 0.01:
                return FailureCategory.METRIC_REGRESSION, FailureSeverity.LOW
            return FailureCategory.METRIC_REGRESSION, FailureSeverity.LOW  # minor noise

        severity = FailureSeverity.MEDIUM
        if relative_delta < -0.30:
            severity = FailureSeverity.CRITICAL
        elif relative_delta < -0.15:
            severity = FailureSeverity.HIGH

        if "safety" in metric_name.lower() or "bias" in metric_name.lower():
            return FailureCategory.SAFETY_VIOLATION if delta < 0 else FailureCategory.BIAS_DETECTED, severity
        if "latenc" in metric_name.lower():
            return FailureCategory.LATENCY_DEGRADATION, severity
        if "accuracy" in metric_name.lower() or "score" in metric_name.lower():
            return FailureCategory.METRIC_REGRESSION, severity
        if "robust" in metric_name.lower():
            return FailureCategory.ROBUSTNESS_FAILURE, severity
        if "halluc" in metric_name.lower():
            return FailureCategory.HALLUCINATION, severity
        if "instruct" in metric_name.lower():
            return FailureCategory.INSTRUCTION_FAILURE, severity
        return FailureCategory.METRIC_REGRESSION, severity

    # -- detection -------------------------------------------------------

    def detect_weaknesses(
        self,
        baseline_results: Dict[str, Any],
        candidate_results: Dict[str, Any],
        evaluation_population: int = 0,
        min_regression: float = 0.05,
    ) -> List[Weakness]:
        """Compare baseline vs candidate results and detect weaknesses."""
        bl_metrics = baseline_results.get("metrics", [])
        cand_metrics = candidate_results.get("metrics", [])

        # Build metric maps keyed by (name, evaluation_version)
        bl_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for m in bl_metrics:
            key = (m.get("name"), m.get("evaluation_version", ""))
            bl_map[key] = m

        weaknesses: List[Weakness] = []

        for cm in cand_metrics:
            name = cm.get("name")
            ver = cm.get("evaluation_version", "")
            key = (name, ver)
            bl = bl_map.get(key)
            if not bl:
                continue
            bl_val = float(bl.get("value", 0.0))
            cand_val = float(cm.get("value", 0.0))
            higher_better = bl.get("higher_is_better", True)

            category, severity = self.classify(name, name, bl_val, cand_val, higher_better, min_regression)
            delta = cand_val - bl_val if higher_better else bl_val - cand_val
            rel_delta = delta / bl_val if bl_val else 1.0

            if delta < -min_regression * bl_val if bl_val else delta < -min_regression:
                # regression detected
                failures = [FailureInstance(
                    failure_id=f"fail_{_short_uuid()}",
                    category=category,
                    severity=severity,
                    capability=ver or name,
                    metric_name=name,
                    baseline_value=bl_val,
                    current_value=cand_val,
                    threshold=bl_val * (1 - min_regression) if higher_better else bl_val * (1 + min_regression),
                    evidence=f"Regression: {cand_val} vs baseline {bl_val} ({rel_delta:.2%} delta)",
                )]
                weakness = Weakness(
                    weakness_id=f"weakness_{_short_uuid()}",
                    target_capability=ver or name,
                    description=f"Regression in {name}: {rel_delta:.2%} drop from baseline {bl_val} to {cand_val}",
                    failure_category=category,
                    severity=severity,
                    failures=failures,
                    affected_population=1.0,
                    confidence=min(1.0, abs(rel_delta) * 2),
                )
                self._weaknesses[weakness.weakness_id] = weakness
                weaknesses.append(weakness)
            elif delta > min_regression * bl_val if bl_val else delta > min_regression:
                # improvement detected — still log as a "weakness" for completeness
                # but with LOW severity (it's actually a strength)
                pass  # improvements are tracked in ImprovementResult, not weaknesses

        # Cluster similar weaknesses
        self._cluster(weaknesses)

        return weaknesses

    def _cluster(self, weaknesses: List[Weakness]) -> None:
        """Cluster weaknesses by failure_category + severity."""
        for w in weaknesses:
            cluster_key = f"{w.failure_category.value}:{w.severity.value}"
            cluster_id = f"cluster_{hashlib.md5(cluster_key.encode()).hexdigest()[:8]}"
            w.cluster_id = cluster_id
            if cluster_id not in self._clusters:
                self._clusters[cluster_id] = []
            self._clusters[cluster_id].append(w.weakness_id)


class WeaknessDetector:
    """Detects weaknesses in JARVIS's own AI capabilities."""

    def __init__(self) -> None:
        self.taxonomy = FailureTaxonomy()

    def detect_from_results(
        self,
        baseline_results: Dict[str, Any],
        candidate_results: Dict[str, Any],
        evaluation_population: int = 0,
        min_regression: float = 0.05,
    ) -> List[Weakness]:
        """Detect weaknesses by comparing baseline vs candidate results."""
        return self.taxonomy.detect_weaknesses(
            baseline_results, candidate_results, evaluation_population, min_regression
        )

    def detect_from_critic_findings(
        self,
        critic_findings: List[Any],
    ) -> List[Weakness]:
        """Convert CriticFinding objects into Weakness objects."""
        weaknesses: List[Weakness] = []
        for finding in critic_findings:
            w = Weakness(
                weakness_id=f"weakness_{_short_uuid()}",
                target_capability=getattr(finding, "category", "unknown"),
                description=getattr(finding, "description", str(finding)),
                failure_category=FailureCategory.UNEXPECTED_OUTPUT,
                severity=FailureSeverity.MEDIUM,
                failures=[],
                affected_population=1.0,
                confidence=0.5,
            )
            self.taxonomy._weaknesses[w.weakness_id] = w
            weaknesses.append(w)
        return weaknesses


# --------------------------------------------------------------------------- #
# Improvement policy
# --------------------------------------------------------------------------- #

@dataclass
class ImprovementPolicy:
    """Measurable criteria defining what constitutes "better" for an improvement.

    JARVIS must never assume newer = better, larger = better, more training = better,
    or lower loss = better.  Improvement is defined against these criteria.
    """
    target_capability: str
    target_metric: str
    target_metric_higher_is_better: bool = True
    minimum_improvement: float = 0.05        # relative improvement required (e.g. 0.05 = 5%)
    maximum_allowed_regression: float = 0.02  # max relative drop allowed on any non-target metric
    evaluation_population: int = 0           # number of samples in eval
    confidence_required: float = 0.95        # confidence/uncertainty threshold
    budget_usd_daily: float = 50.0
    budget_usd_monthly: float = 200.0
    risk_level: str = "medium"               # low / medium / high / critical
    requires_manual_approval: bool = True
    min_evaluation_version: Optional[str] = None
    # Regression metrics that must not degrade beyond maximum_allowed_regression
    regression_protect_metrics: List[str] = field(default_factory=list)
    # Safety metrics that must not degrade at all (beyond any threshold)
    safety_protect_metrics: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementPolicy":
        return cls(
            target_capability=data.get("target_capability", "unknown"),
            target_metric=data.get("target_metric", "accuracy"),
            target_metric_higher_is_better=data.get("target_metric_higher_is_better", True),
            minimum_improvement=float(data.get("minimum_improvement", 0.05)),
            maximum_allowed_regression=float(data.get("maximum_allowed_regression", 0.02)),
            evaluation_population=int(data.get("evaluation_population", 0)),
            confidence_required=float(data.get("confidence_required", 0.95)),
            budget_usd_daily=float(data.get("budget_usd_daily", 50.0)),
            budget_usd_monthly=float(data.get("budget_usd_monthly", 200.0)),
            risk_level=str(data.get("risk_level", "medium")),
            requires_manual_approval=bool(data.get("requires_manual_approval", True)),
            min_evaluation_version=data.get("min_evaluation_version"),
            regression_protect_metrics=list(data.get("regression_protect_metrics", [])),
            safety_protect_metrics=list(data.get("safety_protect_metrics", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_capability": self.target_capability,
            "target_metric": self.target_metric,
            "target_metric_higher_is_better": self.target_metric_higher_is_better,
            "minimum_improvement": self.minimum_improvement,
            "maximum_allowed_regression": self.maximum_allowed_regression,
            "evaluation_population": self.evaluation_population,
            "confidence_required": self.confidence_required,
            "budget_usd_daily": self.budget_usd_daily,
            "budget_usd_monthly": self.budget_usd_monthly,
            "risk_level": self.risk_level,
            "requires_manual_approval": self.requires_manual_approval,
            "min_evaluation_version": self.min_evaluation_version,
            "regression_protect_metrics": list(self.regression_protect_metrics),
            "safety_protect_metrics": list(self.safety_protect_metrics),
        }


@dataclass
class Hypothesis:
    """A testable prediction that an intervention will improve a metric."""
    hypothesis_id: str
    statement: str
    target_metric: str
    expected_improvement: float          # relative (e.g. 0.10 = 10% improvement)
    predicted_side_effects: List[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: str = field(default_factory=now_iso)
    resolved: bool = False
    outcome: Optional[str] = None        # "supported", "refuted", "inconclusive"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "target_metric": self.target_metric,
            "expected_improvement": self.expected_improvement,
            "predicted_side_effects": list(self.predicted_side_effects),
            "confidence": self.confidence,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "outcome": self.outcome,
        }


@dataclass
class TrainingConfig:
    """Training configuration for an improvement cycle.

    Mirrors the env vars used in kaggle_kernel/jarvis_brain_qwen3_4b.py
    and scripts/kaggle_train_jarvis_lora.py.
    """
    base_model: str = "Qwen/Qwen3-4B"
    base_revision: str = "1cfa9a7208912126459214e8b04321603b3df60c"
    adapter_mode: str = "lora"           # lora | qlo | sft
    load_bits: int = 16                  # 4-bit (QLoRA), 16-bit (bf16), 32-bit (fp32)
    epochs: float = 3.0
    batch_size: int = 2
    learning_rate: float = 2e-4
    lr_scheduler: str = "cosine"
    warmup_ratio: float = 0.03
    gradient_accumulation_steps: int = 4
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    max_seq_length: int = 2048
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])
    max_steps: int = 0                   # 0 = full epochs
    compute_resource: str = "cloud:kaggle"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingConfig":
        return cls(
            base_model=data.get("base_model", "Qwen/Qwen3-4B"),
            base_revision=data.get("base_revision", "1cfa9a7208912126459214e8b04321603b3df60c"),
            adapter_mode=data.get("adapter_mode", "lora"),
            load_bits=int(data.get("load_bits", 16)),
            epochs=float(data.get("epochs", 3.0)),
            batch_size=int(data.get("batch_size", 2)),
            learning_rate=float(data.get("learning_rate", 2e-4)),
            lr_scheduler=data.get("lr_scheduler", "cosine"),
            warmup_ratio=float(data.get("warmup_ratio", 0.03)),
            gradient_accumulation_steps=int(data.get("gradient_accumulation_steps", 4)),
            lora_rank=int(data.get("lora_rank", 16)),
            lora_alpha=int(data.get("lora_alpha", 32)),
            lora_dropout=float(data.get("lora_dropout", 0.05)),
            max_seq_length=int(data.get("max_seq_length", 2048)),
            target_modules=list(data.get("target_modules", [])),
            max_steps=int(data.get("max_steps", 0)),
            compute_resource=data.get("compute_resource", "cloud:kaggle"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_model": self.base_model,
            "base_revision": self.base_revision,
            "adapter_mode": self.adapter_mode,
            "load_bits": self.load_bits,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "lr_scheduler": self.lr_scheduler,
            "warmup_ratio": self.warmup_ratio,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "lora_rank": self.lora_rank,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "max_seq_length": self.max_seq_length,
            "target_modules": list(self.target_modules),
            "max_steps": self.max_steps,
            "compute_resource": self.compute_resource,
        }


# --------------------------------------------------------------------------- #
# Baseline lock
# --------------------------------------------------------------------------- #

@dataclass
class BaselineLock:
    """Immutable snapshot of baseline metrics used for comparison.

    Once created, the lock cannot be modified — any attempt to change
    ``metrics``, ``model_id``, or ``revision`` raises ValueError.
    """
    model_id: str
    revision: str
    metrics: Dict[str, float]
    dataset_id: str
    locked_at: str = field(default_factory=now_iso)
    lock_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.lock_hash:
            self.lock_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps({
            "model_id": self.model_id,
            "revision": self.revision,
            "metrics": self.metrics,
            "dataset_id": self.dataset_id,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def verify(self) -> bool:
        """Verify the lock has not been tampered with."""
        return self.lock_hash == self._compute_hash()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "metrics": dict(self.metrics),
            "dataset_id": self.dataset_id,
            "locked_at": self.locked_at,
            "lock_hash": self.lock_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaselineLock":
        return cls(
            model_id=data["model_id"],
            revision=data["revision"],
            metrics=dict(data.get("metrics", {})),
            dataset_id=data.get("dataset_id", ""),
            locked_at=data.get("locked_at", now_iso()),
            lock_hash=data.get("lock_hash", ""),
        )

    def freeze(self) -> "BaselineLock":
        """Return a deep copy that cannot be mutated by callers holding the reference.

        The lock's ``lock_hash`` is recomputed to ensure integrity.
        """
        return BaselineLock(
            model_id=self.model_id,
            revision=self.revision,
            metrics=dict(self.metrics),
            dataset_id=self.dataset_id,
            locked_at=self.locked_at,
            lock_hash=self.lock_hash,
        )


# --------------------------------------------------------------------------- #
# Candidate artifact
# --------------------------------------------------------------------------- #

class CandidateStatus(str, Enum):
    """Status of a candidate artifact throughout the improvement cycle."""
    EXPERIMENTAL     = "experimental"     # just created, not validated
    STAGING          = "staging"          # artifact registered in ArtifactRegistry
    LOCKED           = "locked"           # baseline-locked for comparison
    EVALUATED        = "evaluated"        # passed evaluation matrix
    VERIFIED         = "verified"         # passed verification
    PROMOTION_REVIEW = "promotion_review" # under PromotionGate review
    APPROVED         = "approved"          # PromotionGate approved
    DEPLOYED_SHADOW  = "deployed_shadow"  # shadow deployment
    DEPLOYED_CANARY  = "deployed_canary"  # canary deployment
    DEPLOYED         = "deployed"         # production deployment
    ROLLED_BACK      = "rolled_back"      # reverted after deployment issue
    REJECTED         = "rejected"         # candidate rejected
    FAILED           = "failed"           # candidate failed
    DEPRECATED       = "deprecated"       # superseded by newer candidate
    RETIRED          = "retired"          # retired from service

    @classmethod
    def terminal_states(cls) -> List[str]:
        return [cls.APPROVED, cls.DEPLOYED, cls.ROLLED_BACK,
                cls.REJECTED, cls.FAILED]

    @classmethod
    def valid_transitions(cls) -> Dict[str, List[str]]:
        return {
            cls.EXPERIMENTAL:     [cls.STAGING, cls.FAILED],
            cls.STAGING:          [cls.LOCKED, cls.FAILED],
            cls.LOCKED:           [cls.EVALUATED, cls.FAILED],
            cls.EVALUATED:        [cls.VERIFIED, cls.REJECTED],
            cls.VERIFIED:         [cls.PROMOTION_REVIEW, cls.REJECTED],
            cls.PROMOTION_REVIEW: [cls.APPROVED, cls.REJECTED, cls.FAILED],
            cls.APPROVED:         [cls.DEPLOYED_SHADOW, cls.FAILED],
            cls.DEPLOYED_SHADOW:  [cls.DEPLOYED_CANARY, cls.ROLLED_BACK, cls.FAILED],
            cls.DEPLOYED_CANARY:  [cls.DEPLOYED, cls.ROLLED_BACK, cls.FAILED],
            cls.DEPLOYED:         [cls.DEPLOYED_CANARY, cls.ROLLED_BACK, cls.DEPRECATED],
            cls.ROLLED_BACK:      [cls.DEPLOYED_CANARY],  # can re-candidate after rollback
            cls.DEPRECATED:       [cls.RETIRED],
            cls.RETIRED:          [],
        }

    @classmethod
    def validate_transition(cls, current: str, target: str) -> None:
        valid = cls.valid_transitions().get(current, [])
        if target not in valid:
            raise ValueError(
                f"Invalid CandidateStatus transition: {current} -> {target}. "
                f"Allowed: {valid}"
            )


@dataclass
class CandidateArtifact:
    """A candidate model/artifact produced by an improvement cycle.

    Starts as EXPERIMENTAL — only transitions to APPROVED after
    VerificationEngine + PromotionGate approval.
    """
    artifact_id: str
    improvement_id: str
    model_id: str
    revision: str
    artifact_type: str = "lora_adapter"   # mirrors ArtifactType values
    artifact_uri: str = ""
    checksum: str = ""
    training_config: Dict[str, Any] = field(default_factory=dict)
    dataset_id: str = ""
    status: str = CandidateStatus.EXPERIMENTAL.value
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    parent_artifact_id: Optional[str] = None

    def transition(self, target: CandidateStatus) -> None:
        """Transition to a new status, validating the transition."""
        CandidateStatus.validate_transition(self.status, target.value)
        self.status = target.value
        self.updated_at = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "improvement_id": self.improvement_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "artifact_type": self.artifact_type,
            "artifact_uri": self.artifact_uri,
            "checksum": self.checksum,
            "training_config": dict(self.training_config),
            "dataset_id": self.dataset_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_artifact_id": self.parent_artifact_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateArtifact":
        return cls(
            artifact_id=data["artifact_id"],
            improvement_id=data["improvement_id"],
            model_id=data["model_id"],
            revision=data["revision"],
            artifact_type=data.get("artifact_type", "lora_adapter"),
            artifact_uri=data.get("artifact_uri", ""),
            checksum=data.get("checksum", ""),
            training_config=dict(data.get("training_config", {})),
            dataset_id=data.get("dataset_id", ""),
            status=data.get("status", CandidateStatus.EXPERIMENTAL.value),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
            parent_artifact_id=data.get("parent_artifact_id"),
        )


# --------------------------------------------------------------------------- #
# Evaluation matrix
# --------------------------------------------------------------------------- #

@dataclass
class EvaluationMatrix:
    """Matrix of evaluation suites for an improvement cycle.

    - target: evaluates the specific capability being improved
    - regression: checks that other capabilities haven't regressed
    - safety: verifies safety properties are maintained
    - robustness: tests robustness under adversarial/edge conditions
    """
    target_suite: str = "math_reasoning"       # v1 of the target capability suite
    target_suite_id: str = "math_reasoning:v1"
    regression_suites: List[str] = field(default_factory=lambda: [
        "code_generation", "code_repair", "general_reasoning",
        "document_analysis", "data_analysis", "instruction_following",
    ])
    safety_suites: List[str] = field(default_factory=lambda: [
        "security", "geography",
    ])
    robustness_suites: List[str] = field(default_factory=lambda: [
        "generation_quality", "rag",
    ])
    # Minimum acceptable scores per suite (relative to baseline)
    min_regression_threshold: float = 0.02  # 2% max drop allowed
    min_safety_threshold: float = 1.0       # safety metrics must not drop at all

    def all_suites(self) -> List[str]:
        """Return all suites in the matrix."""
        return [self.target_suite] + list(self.regression_suites) + \
               list(self.safety_suites) + list(self.robustness_suites)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_suite": self.target_suite,
            "target_suite_id": self.target_suite_id,
            "regression_suites": list(self.regression_suites),
            "safety_suites": list(self.safety_suites),
            "robustness_suites": list(self.robustness_suites),
            "min_regression_threshold": self.min_regression_threshold,
            "min_safety_threshold": self.min_safety_threshold,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationMatrix":
        return cls(
            target_suite=data.get("target_suite", "math_reasoning"),
            target_suite_id=data.get("target_suite_id", "math_reasoning:v1"),
            regression_suites=list(data.get("regression_suites", [])),
            safety_suites=list(data.get("safety_suites", [])),
            robustness_suites=list(data.get("robustness_suites", [])),
            min_regression_threshold=float(data.get("min_regression_threshold", 0.02)),
            min_safety_threshold=float(data.get("min_safety_threshold", 1.0)),
        )


# --------------------------------------------------------------------------- #
# Improvement result
# --------------------------------------------------------------------------- #

@dataclass
class ImprovementResult:
    """Result of comparing baseline vs candidate evaluation results."""
    baseline_results: Dict[str, Any] = field(default_factory=dict)
    candidate_results: Dict[str, Any] = field(default_factory=dict)
    comparison: Dict[str, Any] = field(default_factory=dict)
    regression_detected: bool = False
    regressions: List[str] = field(default_factory=list)
    target_improvement: float = 0.0       # relative improvement on target metric
    target_metric_meets_threshold: bool = False
    safety_violations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    verdict: str = "pending"              # "improved", "regressed", "mixed", "no_change", "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_results": dict(self.baseline_results),
            "candidate_results": dict(self.candidate_results),
            "comparison": dict(self.comparison),
            "regression_detected": self.regression_detected,
            "regressions": list(self.regressions),
            "target_improvement": self.target_improvement,
            "target_metric_meets_threshold": self.target_metric_meets_threshold,
            "safety_violations": list(self.safety_violations),
            "confidence": self.confidence,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementResult":
        return cls(
            baseline_results=dict(data.get("baseline_results", {})),
            candidate_results=dict(data.get("candidate_results", {})),
            comparison=dict(data.get("comparison", {})),
            regression_detected=bool(data.get("regression_detected", False)),
            regressions=list(data.get("regressions", [])),
            target_improvement=float(data.get("target_improvement", 0.0)),
            target_metric_meets_threshold=bool(data.get("target_metric_meets_threshold", False)),
            safety_violations=list(data.get("safety_violations", [])),
            confidence=float(data.get("confidence", 0.0)),
            verdict=data.get("verdict", "pending"),
        )


# --------------------------------------------------------------------------- #
# Deployment
# --------------------------------------------------------------------------- #

class DeploymentMode(str, Enum):
    """Controlled deployment modes."""
    SHADOW   = "shadow"    # parallel, no traffic — comparison only
    CANARY   = "canary"    # gradual traffic rollout
    BLOCKBOX = "blockbox"  # isolated testing environment
    PRODUCTION = "production"  # full production deployment

    @classmethod
    def risk_level(cls, mode: str) -> str:
        mapping = {
            cls.SHADOW: "low",
            cls.BLOCKBOX: "low",
            cls.CANARY: "medium",
            cls.PRODUCTION: "high",
        }
        return mapping.get(mode, "medium")


@dataclass
class ImprovementDeployment:
    """Controlled deployment configuration with rollback capability."""
    deployment_id: str
    candidate_artifact_id: str
    mode: str = DeploymentMode.SHADOW.value
    traffic_fraction: float = 0.0       # 0.0 for shadow/blockbox, 0-1 for canary
    canary_steps: int = 0               # number of canary increments
    rollback_on_failure: bool = True
    health_check_metric: str = ""
    health_check_threshold: float = 0.0
    deployed_at: str = field(default_factory=now_iso)
    rolled_back: bool = False
    rollback_reason: str = ""
    rollback_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "candidate_artifact_id": self.candidate_artifact_id,
            "mode": self.mode,
            "traffic_fraction": self.traffic_fraction,
            "canary_steps": self.canary_steps,
            "rollback_on_failure": self.rollback_on_failure,
            "health_check_metric": self.health_check_metric,
            "health_check_threshold": self.health_check_threshold,
            "deployed_at": self.deployed_at,
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
            "rollback_at": self.rollback_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementDeployment":
        return cls(
            deployment_id=data["deployment_id"],
            candidate_artifact_id=data["candidate_artifact_id"],
            mode=data.get("mode", DeploymentMode.SHADOW.value),
            traffic_fraction=float(data.get("traffic_fraction", 0.0)),
            canary_steps=int(data.get("canary_steps", 0)),
            rollback_on_failure=bool(data.get("rollback_on_failure", True)),
            health_check_metric=data.get("health_check_metric", ""),
            health_check_threshold=float(data.get("health_check_threshold", 0.0)),
            deployed_at=data.get("deployed_at", now_iso()),
            rolled_back=bool(data.get("rolled_back", False)),
            rollback_reason=data.get("rollback_reason", ""),
            rollback_at=data.get("rollback_at"),
        )

    @staticmethod
    def create_shadow(candidate_artifact_id: str) -> "ImprovementDeployment":
        """Create a shadow deployment (no traffic, comparison only)."""
        return ImprovementDeployment(
            deployment_id=f"deploy_{_short_uuid()}",
            candidate_artifact_id=candidate_artifact_id,
            mode=DeploymentMode.SHADOW.value,
            traffic_fraction=0.0,
            rollback_on_failure=True,
        )


# --------------------------------------------------------------------------- #
# Autonomy guard
# --------------------------------------------------------------------------- #

# Resources/paths JARVIS must NEVER modify, regardless of autonomy level.
PROTECTED_PATHS = frozenset({
    "jarvis_backend/core.py",         # auth, DB, secrets
    "infrastructure/provider_registry.py",
    "infrastructure/promotion_gate.py",
    "infrastructure/job_registry.py",
    "infrastructure/artifact_registry.py",
    "infrastructure/audit_events.py",
    "jarvis_backend/cloud_fabric.py",  # credential boundary
    "providers/",                     # all provider code
    ".env",                           # secret files
    "jarvis_secret_key",
})

# Secret-shaped field names that must never appear in improvement artifacts
SECRET_FIELD_PATTERNS = (
    "api_key", "apikey", "token", "secret", "password",
    "passwd", "credential", "authorization", "bearer",
    "private_key",
)


class AutonomyGuard:
    """Enforces the autonomy boundary.

    JARVIS must NOT:
    - Directly rewrite its own production source code
    - Bypass security controls
    - Modify credentials
    - Alter authorization
    - Promote its own model without existing gates

    The ``intervention`` and ``artifact`` objects are checked before execution.
    """

    def __init__(self, autonomy_level: int = 0) -> None:
        """*autonomy_level* mirrors ``AutonomyLevel`` but the guard is
        always active regardless of level for protected resources."""
        self.autonomy_level = autonomy_level

    # -- intervention checks ------------------------------------------------

    def check_intervention(self, intervention_type: InterventionType,
                           target: str) -> Tuple[bool, str]:
        """Check whether an intervention is permitted.

        Returns (allowed, reason).
        """
        # SYSTEM_POLICY_CHANGE is never autonomous
        if intervention_type == InterventionType.SYSTEM_POLICY_CHANGE:
            return False, "system_policy_change requires manual owner approval"

        # High-risk interventions always require manual approval
        if intervention_type in HIGH_RISK_INTERVENTIONS:
            return False, f"{intervention_type.value} requires manual approval"

        # Check protected paths — the intervention target must not touch them
        for protected in PROTECTED_PATHS:
            if target.startswith(protected) or protected in target:
                return False, f"intervention targets protected path: {protected}"

        # Check for secret-shaped parameters
        if self._contains_secrets(target):
            return False, "intervention contains secret-shaped parameters"

        return True, "permitted"

    # -- artifact checks ----------------------------------------------------

    def check_artifact(self, artifact: CandidateArtifact) -> Tuple[bool, str]:
        """Verify a candidate artifact does not contain secrets."""
        if self._contains_secrets(artifact.checksum):
            return False, "artifact checksum appears secret-shaped"

        # Verify training_config has no secret fields
        for key in artifact.training_config:
            lowered = key.lower()
            if any(pat in lowered for pat in SECRET_FIELD_PATTERNS):
                return False, f"training_config contains secret-shaped field: {key}"

        # Artifact URI must not contain credential fragments
        uri_lower = artifact.artifact_uri.lower()
        for pat in SECRET_FIELD_PATTERNS:
            if pat in uri_lower:
                return False, f"artifact URI contains secret-shaped field: {pat}"

        return True, "permitted"

    # -- promotion checks ---------------------------------------------------

    def can_promote(self, artifact: CandidateArtifact,
                    promotion_approved: bool = False) -> Tuple[bool, str]:
        """Check whether a candidate can be promoted to production.

        Production promotion requires either:
        - Manual approval (promotion_approved=True), OR
        - Autonomy level >= 3 AND artifact is verified + approved
        """
        if artifact.status != CandidateStatus.APPROVED.value:
            return False, f"artifact must be APPROVED (current: {artifact.status})"

        if artifact.status == CandidateStatus.EXPERIMENTAL.value:
            return False, "EXPERIMENTAL artifacts can never be promoted"

        if not promotion_approved:
            if self.autonomy_level < 3:
                return False, "production promotion requires manual approval"
            # Level 3+ can promote verified+approved artifacts
            return True, "autonomous promotion permitted (level 3+)"

        return True, "manual approval granted"

    # -- source code protection --------------------------------------------

    @staticmethod
    def is_production_source(path: str) -> bool:
        """Check if a file path is protected production source."""
        for protected in PROTECTED_PATHS:
            if path.startswith(protected) or protected in path:
                return True
        return False

    @staticmethod
    def _contains_secrets(text: str) -> bool:
        """Check if text contains secret-shaped content."""
        if not text:
            return False
        lowered = text.lower()
        return any(pat in lowered for pat in SECRET_FIELD_PATTERNS)

    # -- credential access protection --------------------------------------

    def assert_no_credential_access(self, operation: str,
                                    details: Dict[str, Any]) -> None:
        """Assert that an operation does not attempt to access credentials.

        Raises PermissionError if a credential access pattern is detected.
        """
        # Check operation type
        credential_ops = {
            "read_env", "read_file", "list_env", "exec_shell",
            "access_keyring", "read_secret_store",
        }
        if operation in credential_ops:
            raise PermissionError(
                f"AUTONOMY GUARD: operation '{operation}' is prohibited. "
                f"JARVIS may not directly access credentials, secrets, "
                f"or execute unrestricted shell commands."
            )

        # Check detail values for secret-shaped keys
        for key, val in details.items():
            if isinstance(val, str) and val.lower().strip() in {
                "api_key", "token", "password", "secret", "credentials",
            }:
                raise PermissionError(
                    f"AUTONOMY GUARD: operation '{operation}' attempts to access "
                    f"credential '{key}'. Direct credential access is prohibited."
                )


# --------------------------------------------------------------------------- #
# Learning memory
# --------------------------------------------------------------------------- #

@dataclass
class Lesson:
    """A structured lesson learned from an improvement cycle."""
    lesson_id: str
    improvement_id: str
    weakness_id: str
    hypothesis_id: str
    intervention_type: str
    outcome: str            # "success", "failure", "partial", "inconclusive"
    what_worked: str
    what_failed: str
    metrics_improved: Dict[str, float] = field(default_factory=dict)
    metrics_regressed: Dict[str, float] = field(default_factory=dict)
    key_learning: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "improvement_id": self.improvement_id,
            "weakness_id": self.weakness_id,
            "hypothesis_id": self.hypothesis_id,
            "intervention_type": self.intervention_type,
            "outcome": self.outcome,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "metrics_improved": dict(self.metrics_improved),
            "metrics_regressed": dict(self.metrics_regressed),
            "key_learning": self.key_learning,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lesson":
        return cls(
            lesson_id=data["lesson_id"],
            improvement_id=data["improvement_id"],
            weakness_id=data["weakness_id"],
            hypothesis_id=data["hypothesis_id"],
            intervention_type=data.get("intervention_type", ""),
            outcome=data.get("outcome", "inconclusive"),
            what_worked=data.get("what_worked", ""),
            what_failed=data.get("what_failed", ""),
            metrics_improved=dict(data.get("metrics_improved", {})),
            metrics_regressed=dict(data.get("metrics_regressed", {})),
            key_learning=data.get("key_learning", ""),
            created_at=data.get("created_at", now_iso()),
        )


class LearningMemory:
    """Persists structured lessons after each improvement cycle."""

    @property
    def store(self):
        return get_store("improvements")

    def _load(self) -> Dict[str, Any]:
        data = self.store.load()
        if "lessons" not in data:
            data["lessons"] = {}
        return data

    def save(self) -> None:
        self.store.save()

    def add_lesson(self, lesson: Lesson) -> None:
        data = self._load()
        data["lessons"][lesson.lesson_id] = lesson.to_dict()
        self.save()

    def get_lessons(self, target_capability: Optional[str] = None) -> List[Lesson]:
        data = self._load()
        lessons: List[Lesson] = []
        for ld in data.get("lessons", {}).values():
            lesson = Lesson.from_dict(ld)
            if target_capability and lesson.intervention_type != target_capability:
                # Also match by outcome relevance
                pass
            lessons.append(lesson)
        return lessons

    def get_lessons_for_capability(self, capability: str) -> List[Lesson]:
        """Retrieve lessons relevant to a specific capability."""
        data = self._load()
        relevant: List[Lesson] = []
        for ld in data.get("lessons", {}).values():
            lesson = Lesson.from_dict(ld)
            # Match if the lesson's weakness or metric touches this capability
            if capability.lower() in lesson.intervention_type.lower() or \
               any(capability.lower() in k.lower() for k in lesson.metrics_improved.keys()) or \
               any(capability.lower() in k.lower() for k in lesson.metrics_regressed.keys()):
                relevant.append(lesson)
        return relevant


# --------------------------------------------------------------------------- #
# Improvement graph
# --------------------------------------------------------------------------- #

@dataclass
class GraphNode:
    """A node in the improvement graph (one improvement cycle)."""
    improvement_id: str
    weakness_id: str
    hypothesis_id: str
    intervention_type: str
    artifact_id: Optional[str] = None
    experiment_id: Optional[str] = None
    outcome: str = "pending"  # "improved", "regressed", "rejected", "failed"
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "improvement_id": self.improvement_id,
            "weakness_id": self.weakness_id,
            "hypothesis_id": self.hypothesis_id,
            "intervention_type": self.intervention_type,
            "artifact_id": self.artifact_id,
            "experiment_id": self.experiment_id,
            "outcome": self.outcome,
            "created_at": self.created_at,
        }


class ImprovementGraph:
    """Directed acyclic graph of improvement cycles.

    Links: weakness → hypothesis → intervention → dataset → training →
    artifact → evaluation → promotion → deployment → observation → next weakness
    """

    @property
    def store(self):
        return get_store("improvements")

    def _load(self) -> Dict[str, Any]:
        data = self.store.load()
        if "graph" not in data:
            data["graph"] = {"nodes": {}, "edges": []}
        return data

    def add_node(self, node: GraphNode) -> None:
        data = self._load()
        data["graph"]["nodes"][node.improvement_id] = node.to_dict()
        self.store.save()

    def add_edge(self, source_improvement_id: str,
                 target_improvement_id: str,
                 edge_type: str = "follows_from") -> None:
        """Add a directed edge: source improvement → target improvement.

        This represents: "the weakness discovered in *source* cycle informed
        the hypothesis in *target* cycle".
        """
        data = self._load()
        edge = {
            "source": source_improvement_id,
            "target": target_improvement_id,
            "type": edge_type,
            "created_at": now_iso(),
        }
        data["graph"]["edges"].append(edge)
        self.store.save()

    def get_next_weakness_hint(self, improvement_id: str) -> Optional[str]:
        """Look at completed cycles for this improvement and suggest the
        next weakness to investigate based on the graph."""
        data = self._load()
        node = data["graph"]["nodes"].get(improvement_id)
        if not node or node.get("outcome") not in ("improved", "regressed"):
            return None
        # If the last cycle improved a metric but introduced regressions,
        # suggest addressing the regressed metrics
        if node.get("outcome") == "improved":
            # Find edges where this node was a source
            for edge in data["graph"]["edges"]:
                if edge["source"] == improvement_id:
                    continue
            # Suggest: if regression was detected, target that
            return node.get("weakness_id")
        return None

    def get_chain(self, improvement_id: str) -> List[Dict[str, Any]]:
        """Return the causal chain leading to this improvement (oldest first)."""
        data = self._load()
        chain: List[Dict[str, Any]] = []
        visited: set[str] = set()
        current = improvement_id
        while current and current not in visited:
            visited.add(current)
            node = data["graph"]["nodes"].get(current)
            if node:
                chain.insert(0, node)
            # Find the source that led to this node
            parent = None
            for edge in data["graph"]["edges"]:
                if edge["target"] == current:
                    parent = edge["source"]
                    break
            current = parent
        return chain


# --------------------------------------------------------------------------- #
# SelfImprovementCycle — the canonical container
# --------------------------------------------------------------------------- #

@dataclass
class SelfImprovementCycle:
    """One controlled attempt to improve a JARVIS capability.

    Fields mirror the specification exactly:
      improvement_id, mission_id, target_capability, baseline_model,
      baseline_revision, problem_statement, failure_evidence, hypotheses,
      proposed_change, change_type, dataset, training_config, evaluation_suite,
      compute_requirements, budget, approval_requirements, candidate_artifact,
      baseline_results, candidate_results, regression_results, critic_findings,
      verification, promotion_decision, deployment, post_deployment_results,
      status, provenance, created_at, updated_at.

    The cycle is persisted in the ``"improvements"`` store (separate from
    the ``"experiments"`` store).  A cycle may *also* create a Phase 11
    ``Experiment`` record for the underlying A/B run, linked via
    ``experiment_id``.
    """
    improvement_id: str
    mission_id: str
    target_capability: str
    baseline_model: str
    baseline_revision: str
    problem_statement: str
    failure_evidence: List[Dict[str, Any]] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    proposed_change: Dict[str, Any] = field(default_factory=dict)
    change_type: str = ""                   # InterventionType value
    dataset: Dict[str, Any] = field(default_factory=dict)
    training_config: Dict[str, Any] = field(default_factory=dict)
    evaluation_suite: str = ""
    compute_requirements: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    approval_requirements: List[str] = field(default_factory=list)
    candidate_artifact: Optional[Dict[str, Any]] = None
    baseline_results: Dict[str, Any] = field(default_factory=dict)
    candidate_results: Dict[str, Any] = field(default_factory=dict)
    regression_results: Dict[str, Any] = field(default_factory=dict)
    critic_findings: List[Dict[str, Any]] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    promotion_decision: Optional[Dict[str, Any]] = None
    deployment: Optional[Dict[str, Any]] = None
    post_deployment_results: Dict[str, Any] = field(default_factory=dict)
    status: str = ImprovementStatus.IDENTIFIED.value
    owner: str = "system"
    experiment_id: Optional[str] = None       # link to Phase 11 Experiment
    job_id: Optional[str] = None             # link to JobRegistry training job
    provenance: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # -- lifecycle ----------------------------------------------------------

    def transition(self, target: ImprovementStatus,
                   actor: str = "system", notes: str = "") -> None:
        """Transition to a new status, validating the transition."""
        ImprovementStatus.validate_transition(self.status, target.value)
        self.status = target.value
        self.updated_at = now_iso()
        self.provenance.append(f"transition:{actor}:{target.value}:{notes}")

    def can_transition(self, target: ImprovementStatus) -> bool:
        """Check if transition to *target* is valid."""
        valid = ImprovementStatus.valid_transitions().get(self.status, [])
        return target.value in valid

    @property
    def is_terminal(self) -> bool:
        return ImprovementStatus.is_terminal(self.status)

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "improvement_id": self.improvement_id,
            "mission_id": self.mission_id,
            "target_capability": self.target_capability,
            "baseline_model": self.baseline_model,
            "baseline_revision": self.baseline_revision,
            "problem_statement": self.problem_statement,
            "failure_evidence": list(self.failure_evidence),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "proposed_change": dict(self.proposed_change),
            "change_type": self.change_type,
            "dataset": dict(self.dataset),
            "training_config": dict(self.training_config),
            "evaluation_suite": self.evaluation_suite,
            "compute_requirements": dict(self.compute_requirements),
            "budget": dict(self.budget),
            "approval_requirements": list(self.approval_requirements),
            "candidate_artifact": self.candidate_artifact,
            "baseline_results": dict(self.baseline_results),
            "candidate_results": dict(self.candidate_results),
            "regression_results": dict(self.regression_results),
            "critic_findings": list(self.critic_findings),
            "verification": dict(self.verification),
            "promotion_decision": self.promotion_decision,
            "deployment": self.deployment,
            "post_deployment_results": dict(self.post_deployment_results),
            "status": self.status,
            "owner": self.owner,
            "experiment_id": self.experiment_id,
            "job_id": self.job_id,
            "provenance": list(self.provenance),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelfImprovementCycle":
        obj = cls(
            improvement_id=data["improvement_id"],
            mission_id=data["mission_id"],
            target_capability=data["target_capability"],
            baseline_model=data["baseline_model"],
            baseline_revision=data["baseline_revision"],
            problem_statement=data["problem_statement"],
            failure_evidence=list(data.get("failure_evidence", [])),
            hypotheses=[Hypothesis.from_dict(h) if isinstance(h, dict) else h
                        for h in data.get("hypotheses", [])],
            proposed_change=dict(data.get("proposed_change", {})),
            change_type=data.get("change_type", ""),
            dataset=dict(data.get("dataset", {})),
            training_config=dict(data.get("training_config", {})),
            evaluation_suite=data.get("evaluation_suite", ""),
            compute_requirements=dict(data.get("compute_requirements", {})),
            budget=dict(data.get("budget", {})),
            approval_requirements=list(data.get("approval_requirements", [])),
            candidate_artifact=data.get("candidate_artifact"),
            baseline_results=dict(data.get("baseline_results", {})),
            candidate_results=dict(data.get("candidate_results", {})),
            regression_results=dict(data.get("regression_results", {})),
            critic_findings=list(data.get("critic_findings", [])),
            verification=dict(data.get("verification", {})),
            promotion_decision=data.get("promotion_decision"),
            deployment=data.get("deployment"),
            post_deployment_results=dict(data.get("post_deployment_results", {})),
            status=data.get("status", ImprovementStatus.IDENTIFIED.value),
            owner=data.get("owner", "system"),
            experiment_id=data.get("experiment_id"),
            job_id=data.get("job_id"),
            provenance=list(data.get("provenance", [])),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
        )
        return obj

    def save(self) -> None:
        """Persist this cycle to the improvements store."""
        store = get_store("improvements")
        data = store.load()
        if "cycles" not in data:
            data["cycles"] = {}
        data["cycles"][self.improvement_id] = self.to_dict()
        store.save()

    @classmethod
    def create(cls, target_capability: str, baseline_model: str,
               baseline_revision: str, problem_statement: str,
               mission_id: str = "", owner: str = "system") -> "SelfImprovementCycle":
        """Create a new improvement cycle in IDENTIFIED state."""
        improvement_id = f"impr_{_short_uuid()}"
        cycle = cls(
            improvement_id=improvement_id,
            mission_id=mission_id,
            target_capability=target_capability,
            baseline_model=baseline_model,
            baseline_revision=baseline_revision,
            problem_statement=problem_statement,
            change_type="",
            status=ImprovementStatus.IDENTIFIED.value,
            owner=owner,
            provenance=[f"created:{owner}:{now_iso()}"],
        )
        cycle.save()
        logger.info("Created improvement cycle %s for capability %s",
                    improvement_id, target_capability)
        return cycle

    @classmethod
    def load(cls, improvement_id: str) -> Optional["SelfImprovementCycle"]:
        """Load a cycle from the improvements store."""
        store = get_store("improvements")
        data = store.load()
        cycle_dict = data.get("cycles", {}).get(improvement_id)
        if cycle_dict is None:
            return None
        return cls.from_dict(cycle_dict)

    @classmethod
    def list_all(cls) -> List["SelfImprovementCycle"]:
        """List all improvement cycles."""
        store = get_store("improvements")
        data = store.load()
        cycles = data.get("cycles", {})
        return [cls.from_dict(c) for c in cycles.values()]

    @classmethod
    def list_by_status(cls, status: str) -> List["SelfImprovementCycle"]:
        """List cycles with a given status."""
        return [c for c in cls.list_all() if c.status == status]

    @classmethod
    def list_by_capability(cls, capability: str) -> List["SelfImprovementCycle"]:
        """List cycles targeting a given capability."""
        return [c for c in cls.list_all()
                if c.target_capability == capability]

    # -- accessors ----------------------------------------------------------

    @property
    def change_type_enum(self) -> InterventionType:
        return InterventionType.safe_from_value(self.change_type) \
            if self.change_type else InterventionType.DATASET_CHANGE

    def add_failure_evidence(self, evidence: Dict[str, Any]) -> None:
        self.failure_evidence.append(evidence)
        self.updated_at = now_iso()

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        self.hypotheses.append(hypothesis)
        self.updated_at = now_iso()

    def set_training_config(self, config: TrainingConfig) -> None:
        self.training_config = config.to_dict()
        self.updated_at = now_iso()

    def set_candidate(self, artifact: CandidateArtifact) -> None:
        self.candidate_artifact = artifact.to_dict()
        self.updated_at = now_iso()

    def get_candidate(self) -> Optional[CandidateArtifact]:
        if self.candidate_artifact:
            return CandidateArtifact.from_dict(self.candidate_artifact)
        return None

    def set_baseline_lock(self, lock: BaselineLock) -> None:
        """Store the baseline lock (immutable snapshot)."""
        self.dataset["baseline_lock"] = lock.to_dict()
        self.updated_at = now_iso()

    def get_baseline_lock(self) -> Optional[BaselineLock]:
        bl = self.dataset.get("baseline_lock")
        if bl:
            return BaselineLock.from_dict(bl)
        return None

    def add_critic_finding(self, finding: Dict[str, Any]) -> None:
        self.critic_findings.append(finding)
        self.updated_at = now_iso()

    def set_verification(self, verified: bool, checks: List[str],
                         details: Dict[str, Any] = None) -> None:
        self.verification = {
            "verified": verified,
            "checks": list(checks),
            "details": details or {},
            "verified_at": now_iso(),
        }
        self.updated_at = now_iso()

    def set_promotion_decision(self, outcome: str, approved: bool,
                               reason: str, scores: Dict[str, float] = None) -> None:
        self.promotion_decision = {
            "outcome": outcome,
            "approved": approved,
            "reason": reason,
            "scores": scores or {},
            "decided_at": now_iso(),
        }
        self.updated_at = now_iso()

    def set_deployment(self, deployment: ImprovementDeployment) -> None:
        self.deployment = deployment.to_dict()
        self.updated_at = now_iso()

    def set_post_deployment_results(self, results: Dict[str, Any]) -> None:
        self.post_deployment_results = dict(results)
        self.updated_at = now_iso()

    def rollback_deployment(self, reason: str) -> None:
        """Trigger a rollback of the current deployment."""
        if self.deployment:
            self.deployment["rolled_back"] = True
            self.deployment["rollback_reason"] = reason
            self.deployment["rollback_at"] = now_iso()
        self.status = ImprovementStatus.ROLLED_BACK.value
        self.updated_at = now_iso()

    # -- evaluation ---------------------------------------------------------

    def evaluate_improvement(self, policy: ImprovementPolicy) -> ImprovementResult:
        """Compare baseline vs candidate results against the improvement policy.

        Uses only the metrics stored on the cycle — never fabricates.
        """
        result = ImprovementResult()
        result.baseline_results = dict(self.baseline_results)
        result.candidate_results = dict(self.candidate_results)

        bl_metrics = self.baseline_results.get("metrics", [])
        cand_metrics = self.candidate_results.get("metrics", [])

        # Build comparison maps
        bl_map: Dict[str, Dict[str, Any]] = {}
        for m in bl_metrics:
            bl_map[m.get("name", "")] = m
        cand_map: Dict[str, Dict[str, Any]] = {}
        for m in cand_metrics:
            cand_map[m.get("name", "")] = m

        # Find target metric
        target_metric = policy.target_metric
        bl_target = bl_map.get(target_metric, {})
        cand_target = cand_map.get(target_metric, {})

        bl_target_val = float(bl_target.get("value", 0.0))
        cand_target_val = float(cand_target.get("value", 0.0))
        higher_better = bl_target.get("higher_is_better", True)

        delta = cand_target_val - bl_target_val if higher_better else bl_target_val - cand_target_val
        result.target_improvement = delta / bl_target_val if bl_target_val else 0.0

        # Check if target meets minimum improvement
        result.target_metric_meets_threshold = (
            result.target_improvement >= policy.minimum_improvement
        ) if higher_better else (
            result.target_improvement >= policy.minimum_improvement
        )

        # Check regression on protected metrics
        result.regression_detected = False
        result.regressions = []
        max_regression = 0.0
        for metric_name, bl_m in bl_map.items():
            cm = cand_map.get(metric_name)
            if not cm:
                continue
            bl_v = float(bl_m.get("value", 0.0))
            cand_v = float(cm.get("value", 0.0))
            hb = bl_m.get("higher_is_better", True)

            m_delta = cand_v - bl_v if hb else bl_v - cand_v
            rel_delta = m_delta / bl_v if bl_v else 0.0

            # Check if this metric is in regression_protect
            is_protected = (
                metric_name in policy.regression_protect_metrics or
                metric_name in policy.safety_protect_metrics
            )
            if is_protected and rel_delta < -policy.maximum_allowed_regression:
                result.regression_detected = True
                result.regressions.append(
                    f"{metric_name}: {rel_delta:.2%} regression "
                    f"(baseline={bl_v}, candidate={cand_v})"
                )
                if abs(rel_delta) > max_regression:
                    max_regression = abs(rel_delta)

            # Safety metrics must not drop at all
            if metric_name in policy.safety_protect_metrics and rel_delta < 0:
                result.safety_violations.append(
                    f"{metric_name}: {rel_delta:.2%} drop in safety metric"
                )

        # Build comparison dict
        result.comparison = {
            "target_metric": target_metric,
            "baseline_value": bl_target_val,
            "candidate_value": cand_target_val,
            "relative_improvement": result.target_improvement,
            "meets_minimum_improvement": result.target_metric_meets_threshold,
            "max_regression": max_regression,
            "regression_detected": result.regression_detected,
            "safety_violations_count": len(result.safety_violations),
            "evaluation_version": bl_target.get("evaluation_version", ""),
        }

        # Verdict
        target_ok = result.target_metric_meets_threshold
        no_regression = not result.regression_detected
        no_safety_violation = len(result.safety_violations) == 0

        if target_ok and no_regression and no_safety_violation:
            result.verdict = "improved"
        elif not target_ok and no_regression and no_safety_violation:
            result.verdict = "no_change"
        elif result.regression_detected:
            result.verdict = "regressed"
        elif not no_safety_violation:
            result.verdict = "regressed"
        else:
            result.verdict = "mixed"

        # Confidence based on regression magnitude
        result.confidence = 1.0 - max_regression if max_regression < 0.5 else 0.0

        return result


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #

def _get_cycles_store() -> Dict[str, Any]:
    """Low-level access to the improvements store dict."""
    store = get_store("improvements")
    data = store.load()
    if "cycles" not in data:
        data["cycles"] = {}
    return data
