"""Structured, validated schemas for the Training Advisor.

Everything that crosses the Gemini <-> Silverwing boundary is a Pydantic
model validated here.  Gemini output is treated as **untrusted**: the
``GeminiProvider`` parses the model's JSON response and re-validates it with
``AdvisorResult.model_validate``.  Anything that fails validation is rejected
and the orchestrator falls back to the deterministic ``LocalProvider`` (or
returns an ``UNKNOWN`` result), so malformed / prompt-injected Gemini output
can never corrupt Silverwing state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------
class Provenance(str, Enum):
    """Provenance labels for every ingested metric / piece of evidence.

    * OBSERVED  - directly measured by a real training loop / system probe.
    * DERIVED   - computed deterministically from an OBSERVED metric.
    * ESTIMATED - approximated with an explicit, documented basis.
    * UNKNOWN   - no live measurement is available for this field.
    """

    OBSERVED = "observed"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class MetricValue(BaseModel):
    """A single labelled metric sample.

    Numeric values go in ``value``; categorical/textual content (e.g.
    optimizer name, scheduler state) goes in ``text``.  ``provenance`` and
    ``source`` make the lineage of every number explicit.
    """

    value: Optional[float] = None
    text: Optional[str] = None
    provenance: Provenance = Provenance.UNKNOWN
    source: str = "unknown"
    note: Optional[str] = None

    @classmethod
    def observed(cls, value, source: str, note: Optional[str] = None):
        return cls(value=float(value) if isinstance(value, (int, float)) else None,
                   text=None if isinstance(value, (int, float)) else str(value),
                   provenance=Provenance.OBSERVED, source=source, note=note)

    @classmethod
    def derived(cls, value, source: str, note: Optional[str] = None):
        return cls(value=float(value) if isinstance(value, (int, float)) else None,
                   text=None if isinstance(value, (int, float)) else str(value),
                   provenance=Provenance.DERIVED, source=source, note=note)

    @classmethod
    def estimated(cls, value, source: str, note: Optional[str] = None):
        return cls(value=float(value) if isinstance(value, (int, float)) else None,
                   text=None if isinstance(value, (int, float)) else str(value),
                   provenance=Provenance.ESTIMATED, source=source, note=note)

    @classmethod
    def unknown(cls, source: str = "unknown", note: Optional[str] = None):
        return cls(value=None, text=None, provenance=Provenance.UNKNOWN,
                   source=source, note=note)


class TrainingMetricsSnapshot(BaseModel):
    """A point-in-time capture of Silverwing's training metrics."""

    captured_at: str
    run_id: str
    model: str
    model_name: str
    architecture: str
    status: str = "unknown"

    # Core training trajectory
    step: MetricValue = Field(default_factory=lambda: MetricValue.unknown())
    total_steps: MetricValue = Field(default_factory=MetricValue.unknown)
    epoch: MetricValue = Field(default_factory=MetricValue.unknown)
    loss: MetricValue = Field(default_factory=MetricValue.unknown)
    val_loss: MetricValue = Field(default_factory=MetricValue.unknown)
    perplexity: MetricValue = Field(default_factory=MetricValue.unknown)
    learning_rate: MetricValue = Field(default_factory=MetricValue.unknown)
    weight_decay: MetricValue = Field(default_factory=MetricValue.unknown)

    # Gradient statistics
    grad_norm: MetricValue = Field(default_factory=MetricValue.unknown)
    grad_mean: MetricValue = Field(default_factory=MetricValue.unknown)
    grad_std: MetricValue = Field(default_factory=MetricValue.unknown)
    max_grad_abs: MetricValue = Field(default_factory=MetricValue.unknown)
    clipping_applied: MetricValue = Field(default_factory=MetricValue.unknown)

    # Optimizer / scheduler / training config
    optimizer: MetricValue = Field(default_factory=MetricValue.unknown)
    optimizer_state: MetricValue = Field(default_factory=MetricValue.unknown)
    scheduler: MetricValue = Field(default_factory=MetricValue.unknown)
    scheduler_state: MetricValue = Field(default_factory=MetricValue.unknown)
    batch_size: MetricValue = Field(default_factory=MetricValue.unknown)
    sequence_length: MetricValue = Field(default_factory=MetricValue.unknown)

    # Tokens / throughput
    tokens_processed: MetricValue = Field(default_factory=MetricValue.unknown)
    tokens_per_second: MetricValue = Field(default_factory=MetricValue.unknown)
    train_throughput: MetricValue = Field(default_factory=MetricValue.unknown)

    # Checkpoints
    checkpoint_path: MetricValue = Field(default_factory=MetricValue.unknown)
    checkpoint_step: MetricValue = Field(default_factory=MetricValue.unknown)

    # Model scale
    parameter_count: MetricValue = Field(default_factory=MetricValue.unknown)

    # Dataset statistics (labelled per-statistic)
    dataset_stats: dict = Field(default_factory=dict)

    # Evaluation metrics (labelled per-metric)
    eval_metrics: dict = Field(default_factory=dict)

    def _metric(self, name: str) -> MetricValue:
        return getattr(self, name)

    # System resources
    cpu_util: MetricValue = Field(default_factory=MetricValue.unknown)
    ram_util: MetricValue = Field(default_factory=MetricValue.unknown)
    gpu_util: MetricValue = Field(default_factory=MetricValue.unknown)
    vram_used_mb: MetricValue = Field(default_factory=MetricValue.unknown)
    vram_total_mb: MetricValue = Field(default_factory=MetricValue.unknown)

    # Timing / logs
    training_duration_seconds: MetricValue = Field(default_factory=MetricValue.unknown)
    error_logs: list = Field(default_factory=list)
    warning_logs: list = Field(default_factory=list)

    def observed_keys(self) -> list:
        """Names of metrics whose provenance is OBSERVED (in this snapshot)."""
        keys = []
        for fname, f in type(self).model_fields.items():
            if fname in {"captured_at", "run_id", "model", "model_name", "architecture",
                         "status", "dataset_stats", "eval_metrics", "error_logs", "warning_logs"}:
                continue
            val = getattr(self, fname)
            if isinstance(val, MetricValue) and val.provenance == Provenance.OBSERVED:
                keys.append(fname)
        return keys

    def as_dict(self) -> dict:
        """Flatten to a plain dict of numeric/text values keyed by metric name."""
        out = {}
        for fname, f in type(self).model_fields.items():
            if fname in {"error_logs", "warning_logs", "dataset_stats", "eval_metrics"}:
                out[fname] = getattr(self, fname)
                continue
            if isinstance(getattr(self, fname), MetricValue):
                mv: MetricValue = getattr(self, fname)
                out[fname] = mv.value if mv.value is not None else mv.text
        out["dataset_stats"] = self.dataset_stats or {}
        out["eval_metrics"] = self.eval_metrics or {}
        return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class AnomalySeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Anomaly(BaseModel):
    detector: str
    severity: AnomalySeverity = AnomalySeverity.MEDIUM
    title: str
    description: str
    evidence: list = Field(default_factory=list)
    metrics_evidence: list = Field(default_factory=list)
    recommendation_hint: Optional[str] = None


# ---------------------------------------------------------------------------
# Advice
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationAction(str, Enum):
    KEEP_LR = "keep_lr"
    INCREASE_LR = "increase_lr"
    DECREASE_LR = "decrease_lr"
    USE_WARMUP = "use_warmup"
    EXTEND_WARMUP = "extend_warmup"
    CHANGE_SCHEDULER = "change_scheduler"
    STOP_TRAINING = "stop_training"
    CONTINUE_TRAINING = "continue_training"
    INVESTIGATE_INSTABILITY = "investigate_instability"
    COLLECT_METRICS = "collect_metrics"
    REDUCE_BATCH_SIZE = "reduce_batch_size"
    INCREASE_BATCH_SIZE = "increase_batch_size"
    CHECKPOINT = "checkpoint"
    INSPECT_GRADIENTS = "inspect_gradients"
    FIX_DATASET = "fix_dataset"
    RELAX_REGULARIZATION = "relax_regularization"
    TIGHTEN_REGULARIZATION = "tighten_regularization"


class Recommendation(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:10])
    action: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    expected_effect: str
    risk: RiskLevel = RiskLevel.LOW
    authorization_required: bool = True
    sub_action: Optional[str] = None
    target_metric: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    approved: bool = False


class AdvisorStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ProvenanceRecord(BaseModel):
    model: str = "local-rule"
    prompt_version: str = "1.0"
    provider: str = "local"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str = "silverwing-runtime"
    snapshot_count: int = 0
    observed_metric_count: int = 0
    confidence_basis: str = "statistical"
    notes: list = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result (validated structured output)
# ---------------------------------------------------------------------------
class AdvisorResult(BaseModel):
    """Validated, trusted structured output produced by an advisor run.

    This is the *only* type that crosses into Silverwing's evidence /
    provenance system.  It is always a validated Pydantic model.
    """

    analysis: str
    status: AdvisorStatus = AdvisorStatus.UNKNOWN
    recommendations: List[Recommendation] = Field(default_factory=list)
    anomalies: list = Field(default_factory=list)
    metrics_summary: dict = Field(default_factory=dict)
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    provider: str = "local"
    model: str = "local-rule"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    cache_key: Optional[str] = None
    raw_response: Optional[str] = None

    def recommendation_actions(self) -> list:
        out = []
        for r in self.recommendations:
            out.append(r.action if isinstance(r, Recommendation) else
                       (r.get("action") if isinstance(r, dict) else None))
        return out


# Backwards-friendly aliases
AnalysisResult = AdvisorResult
TrainingRecommendation = Recommendation
