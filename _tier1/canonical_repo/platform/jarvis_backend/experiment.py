"""Phase 11 — Experiment abstraction for the JARVIS Laboratory.

An *Experiment* is a controlled scientific/engineering investigation.  It is
**not** another JobRegistry — JobRegistry represents *execution* (a job that
runs on a compute resource); Experiment represents the *investigation*: the
question, the hypothesis, the variables, the design, the evaluation method,
and the conclusions drawn from comparing baseline and candidate results.

Persistence uses the existing ``get_store("experiments")`` pattern, mirroring
``Mission.save()`` / ``Mission.load()`` in ``mission.py``.

Security: the Brain never receives provider credentials, API keys, or secrets.
All experiment data is scrubbed via ``brain_fabric.assert_no_secrets()``
before it is exposed to anything Brain-facing.
"""
from __future__ import annotations

import time
import uuid as _uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _short_uuid() -> str:
    """Short UUID for experiment/campaign IDs (mirrors mission._short_uuid)."""
    return _uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Experiment lifecycle status
# ---------------------------------------------------------------------------
class ExperimentStatus(str, Enum):
    """Lifecycle states for a controlled experiment."""

    DESIGNED = "designed"            # Design complete, awaiting resource selection
    READY = "ready"                  # Resources allocated, awaiting authorization
    RUNNING = "running"             # Job submitted, execution in progress
    ANALYZING = "analyzing"          # Raw results collected, computing metrics
    VERIFYING = "verifying"          # Verifying metric schema, provenance, comparison
    COMPLETED = "completed"          # Verified baseline + candidate comparison with metrics
    FAILED = "failed"               # Execution or analysis error
    CANCELLED = "cancelled"         # Explicitly cancelled
    INCONCLUSIVE = "inconclusive"   # Results too ambiguous for a conclusion
    BLOCKED = "blocked"             # Required resource, dataset, or model unavailable


# Transition table: current → set of allowed next states
_EXPERIMENT_TRANSITIONS: dict[ExperimentStatus, frozenset[ExperimentStatus]] = {
    ExperimentStatus.DESIGNED: frozenset({
        ExperimentStatus.READY,
        ExperimentStatus.BLOCKED,
        ExperimentStatus.CANCELLED,
        ExperimentStatus.FAILED,
    }),
    ExperimentStatus.READY: frozenset({
        ExperimentStatus.RUNNING,
        ExperimentStatus.BLOCKED,
        ExperimentStatus.CANCELLED,
    }),
    ExperimentStatus.RUNNING: frozenset({
        ExperimentStatus.ANALYZING,
        ExperimentStatus.FAILED,
        ExperimentStatus.CANCELLED,
        ExperimentStatus.BLOCKED,
    }),
    ExperimentStatus.ANALYZING: frozenset({
        ExperimentStatus.VERIFYING,
        ExperimentStatus.FAILED,
        ExperimentStatus.INCONCLUSIVE,
    }),
    ExperimentStatus.VERIFYING: frozenset({
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.INCONCLUSIVE,
        ExperimentStatus.CANCELLED,
    }),
    # Terminal states
    ExperimentStatus.COMPLETED: frozenset(),
    ExperimentStatus.FAILED: frozenset(),
    ExperimentStatus.CANCELLED: frozenset(),
    ExperimentStatus.INCONCLUSIVE: frozenset(),
    ExperimentStatus.BLOCKED: frozenset({
        ExperimentStatus.READY,
        ExperimentStatus.DESIGNED,
        ExperimentStatus.CANCELLED,
    }),
}

_TERMINAL_STATUSES: frozenset[ExperimentStatus] = frozenset({
    ExperimentStatus.COMPLETED,
    ExperimentStatus.FAILED,
    ExperimentStatus.CANCELLED,
    ExperimentStatus.INCONCLUSIVE,
})


class ExperimentTransitionError(ValueError):
    """Raised on illegal experiment status transitions."""


def _is_terminal(status: ExperimentStatus) -> bool:
    return status in _TERMINAL_STATUSES


def _validate_experiment_transition(
    current: ExperimentStatus,
    target: ExperimentStatus,
    *,
    require_design: bool = False,
    require_baseline: bool = False,
    experiment: Optional[Any] = None,
) -> None:
    """Validate a state transition.

    Precondition checks:
    - Transition must be in the _EXPERIMENT_TRANSITIONS table.
    - If require_design, the experiment must have a non-empty design.
    - If require_baseline, the experiment must have a baseline result
      before transitioning to VERIFYING/COMPLETED.
    """
    allowed = _EXPERIMENT_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ExperimentTransitionError(
            f"Illegal experiment transition: {current.value} → {target.value}"
        )
    if require_design and experiment is not None:
        design = getattr(experiment, "design", None)
        if design is None or (isinstance(design, dict) and not design):
            raise ExperimentTransitionError(
                f"Cannot transition {current.value} → {target.value}: "
                "experiment has no design"
            )
    if require_baseline and experiment is not None:
        baseline = getattr(experiment, "baseline", None)
        if baseline is None or (isinstance(baseline, dict) and not baseline):
            raise ExperimentTransitionError(
                f"Cannot transition {current.value} → {target.value}: "
                "experiment has no baseline — improvement experiments require a baseline"
            )


def _is_experiment_terminal(status: ExperimentStatus) -> bool:
    return _is_terminal(status)


# ---------------------------------------------------------------------------
# Experiment Design
# ---------------------------------------------------------------------------
@dataclass
class ExperimentDesign:
    """Structured experiment design (the scientific method encoded).

    An experiment *must* have a design before it can proceed past DESIGNED.
    The design captures the question, hypothesis, variables, controls,
    datasets, models, parameters, expected outcomes, success/failure criteria,
    evaluation method, and compute requirements.
    """

    question: str = ""
    hypothesis: str = ""
    independent_variables: list[str] = field(default_factory=list)
    dependent_variables: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_outcomes: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    evaluation_method: str = ""
    compute_requirements: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "hypothesis": self.hypothesis,
            "independent_variables": list(self.independent_variables),
            "dependent_variables": list(self.dependent_variables),
            "controls": list(self.controls),
            "datasets": list(self.datasets),
            "models": list(self.models),
            "parameters": dict(self.parameters),
            "expected_outcomes": dict(self.expected_outcomes),
            "success_criteria": list(self.success_criteria),
            "failure_criteria": list(self.failure_criteria),
            "evaluation_method": self.evaluation_method,
            "compute_requirements": dict(self.compute_requirements),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentDesign":
        return cls(
            question=data.get("question", ""),
            hypothesis=data.get("hypothesis", ""),
            independent_variables=list(data.get("independent_variables", [])),
            dependent_variables=list(data.get("dependent_variables", [])),
            controls=list(data.get("controls", [])),
            datasets=list(data.get("datasets", [])),
            models=list(data.get("models", [])),
            parameters=dict(data.get("parameters", {})),
            expected_outcomes=dict(data.get("expected_outcomes", {})),
            success_criteria=list(data.get("success_criteria", [])),
            failure_criteria=list(data.get("failure_criteria", [])),
            evaluation_method=data.get("evaluation_method", ""),
            compute_requirements=dict(data.get("compute_requirements", {})),
        )


# ---------------------------------------------------------------------------
# Typed Metric
# ---------------------------------------------------------------------------
@dataclass
class Metric:
    """A typed, verifiable metric with full provenance.

    A metric is never fabricated — its value must come from an actual
    evaluation run (EvaluationSuite). The provenance list records which
    evaluation suite version, run, and artifact produced this value.
    """

    name: str          # e.g. "math_accuracy", "val_ppl"
    value: float       # measured value
    unit: str = ""     # e.g. "ratio", "perplexity", "tokens/sec"
    higher_is_better: bool = True
    sample_count: int = 0
    evaluation_version: str = ""  # suite_id:version
    provenance: list[str] = field(default_factory=list)  # run_ids, artifact_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "higher_is_better": self.higher_is_better,
            "sample_count": self.sample_count,
            "evaluation_version": self.evaluation_version,
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Metric":
        return cls(
            name=data["name"],
            value=float(data["value"]),
            unit=data.get("unit", ""),
            higher_is_better=data.get("higher_is_better", True),
            sample_count=int(data.get("sample_count", 0)),
            evaluation_version=data.get("evaluation_version", ""),
            provenance=list(data.get("provenance", [])),
        )


# ---------------------------------------------------------------------------
# Experiment Comparison (baseline vs candidate)
# ---------------------------------------------------------------------------
@dataclass
class ExperimentComparison:
    """A truthful comparison of baseline vs candidate metrics.

    Both baseline_value and candidate_value are measured values. The
    differences are computed, never fabricated.
    """

    metric_name: str
    baseline_value: float
    candidate_value: float
    absolute_difference: float
    relative_difference: float
    sample_count: int
    evaluation_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "candidate_value": self.candidate_value,
            "absolute_difference": self.absolute_difference,
            "relative_difference": self.relative_difference,
            "sample_count": self.sample_count,
            "evaluation_version": self.evaluation_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentComparison":
        return cls(
            metric_name=data["metric_name"],
            baseline_value=float(data["baseline_value"]),
            candidate_value=float(data["candidate_value"]),
            absolute_difference=float(data["absolute_difference"]),
            relative_difference=float(data["relative_difference"]),
            sample_count=int(data.get("sample_count", 0)),
            evaluation_version=data.get("evaluation_version", ""),
        )

    @staticmethod
    def from_metrics(baseline: Metric, candidate: Metric) -> Optional["ExperimentComparison"]:
        """Compute a comparison from two typed Metrics.

        Returns None if the metrics cannot be compared (different names,
        different evaluation versions, or zero sample).
        """
        if baseline.name != candidate.name:
            return None
        if baseline.evaluation_version != candidate.evaluation_version:
            return None
        if baseline.sample_count == 0 or candidate.sample_count == 0:
            return None
        abs_diff = candidate.value - baseline.value
        if baseline.value != 0:
            rel_diff = (candidate.value - baseline.value) / abs(baseline.value)
        else:
            rel_diff = float("inf") if candidate.value != 0 else 0.0
        return ExperimentComparison(
            metric_name=baseline.name,
            baseline_value=baseline.value,
            candidate_value=candidate.value,
            absolute_difference=abs_diff,
            relative_difference=rel_diff,
            sample_count=baseline.sample_count + candidate.sample_count,
            evaluation_version=baseline.evaluation_version,
        )


# ---------------------------------------------------------------------------
# Reproducibility Manifest
# ---------------------------------------------------------------------------
@dataclass
class ReproducibilityManifest:
    """Full reproducibility metadata for an experiment.

    Captures everything needed to reproduce an experiment result: code
    revision, dataset versions, model versions, configuration,
    hyperparameters, evaluation suite, compute resource, environment,
    random seed, software versions, artifacts, and metrics.
    """

    code_revision: str = ""
    dataset_versions: list[dict[str, Any]] = field(default_factory=list)
    model_versions: list[dict[str, Any]] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    evaluation_suite: str = ""
    compute_resource: str = ""
    environment: dict[str, Any] = field(default_factory=dict)
    random_seed: Optional[int] = None
    software_versions: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=now_iso)
    manifest_id: str = field(default_factory=lambda: f"manifest_{_short_uuid()}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "code_revision": self.code_revision,
            "dataset_versions": list(self.dataset_versions),
            "model_versions": list(self.model_versions),
            "configuration": dict(self.configuration),
            "hyperparameters": dict(self.hyperparameters),
            "evaluation_suite": self.evaluation_suite,
            "compute_resource": self.compute_resource,
            "environment": dict(self.environment),
            "random_seed": self.random_seed,
            "software_versions": dict(self.software_versions),
            "artifacts": list(self.artifacts),
            "metrics": list(self.metrics),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReproducibilityManifest":
        return cls(
            manifest_id=data.get("manifest_id", f"manifest_{_short_uuid()}"),
            code_revision=data.get("code_revision", ""),
            dataset_versions=list(data.get("dataset_versions", [])),
            model_versions=list(data.get("model_versions", [])),
            configuration=dict(data.get("configuration", {})),
            hyperparameters=dict(data.get("hyperparameters", {})),
            evaluation_suite=data.get("evaluation_suite", ""),
            compute_resource=data.get("compute_resource", ""),
            environment=dict(data.get("environment", {})),
            random_seed=data.get("random_seed"),
            software_versions=dict(data.get("software_versions", {})),
            artifacts=list(data.get("artifacts", [])),
            metrics=list(data.get("metrics", [])),
            generated_at=data.get("generated_at", now_iso()),
        )


# ---------------------------------------------------------------------------
# Experiment Event Timeline
# ---------------------------------------------------------------------------
@dataclass
class ExperimentEvent:
    """One entry on the experiment's event timeline."""

    event_id: str
    experiment_id: str
    at: str
    kind: str          # e.g. "transition", "baseline", "candidate", "evaluation", "verification"
    status_from: Optional[str]
    status_to: Optional[str]
    detail: str
    actor: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "experiment_id": self.experiment_id,
            "at": self.at,
            "kind": self.kind,
            "from": self.status_from,
            "to": self.status_to,
            "detail": self.detail,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentEvent":
        return cls(
            event_id=data["event_id"],
            experiment_id=data["experiment_id"],
            at=data["at"],
            kind=data["kind"],
            status_from=data.get("from"),
            status_to=data.get("to"),
            detail=data.get("detail", ""),
            actor=data.get("actor", "system"),
        )


# ---------------------------------------------------------------------------
# Experiment Budget
# ---------------------------------------------------------------------------
@dataclass
class ExperimentBudget:
    """Hard limits for an experiment — enforced by ExperimentOrchestrator."""

    max_cost_usd: float = 5.0
    max_seconds: int = 1_800
    max_jobs: int = 1
    max_steps: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_seconds": self.max_seconds,
            "max_jobs": self.max_jobs,
            "max_steps": self.max_steps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentBudget":
        return cls(
            max_cost_usd=data.get("max_cost_usd", 5.0),
            max_seconds=data.get("max_seconds", 1_800),
            max_jobs=data.get("max_jobs", 1),
            max_steps=data.get("max_steps", 100),
        )


# ---------------------------------------------------------------------------
# Experiment — the durable investigation
# ---------------------------------------------------------------------------
@dataclass
class Experiment:
    """A controlled scientific/engineering investigation.

    Experiment ≠ JobRegistry.  JobRegistry tracks *execution* of jobs on
    compute resources.  Experiment tracks the *investigation*: the design,
    the hypothesis, the baseline, the candidate, the metrics, the comparison,
    and the conclusion.

    Persistence: ``get_store("experiments")`` via ``save()``/``load()``.
    """

    experiment_id: str
    mission_id: str
    name: str
    objective: str = ""
    hypothesis: str = ""

    # Design
    design: dict[str, Any] = field(default_factory=dict)  # serialized ExperimentDesign

    # Variables / controls
    variables: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)

    # Inputs
    inputs: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    configurations: dict[str, Any] = field(default_factory=dict)
    compute_requirements: dict[str, Any] = field(default_factory=dict)

    # Evaluation
    evaluation_suite: str = ""  # suite_id:version

    # Results
    baseline: Optional[dict[str, Any]] = None  # {"model": ..., "revision": ..., "metrics": [Metric.to_dict], "compute": ..., "timestamp": ...}
    candidates: list[dict[str, Any]] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)  # list of ExperimentComparison.to_dict
    results: dict[str, Any] = field(default_factory=dict)

    # Provenance
    artifacts: list[str] = field(default_factory=list)  # artifact_ids
    job_ids: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    reproducibility_metadata: Optional[dict[str, Any]] = None

    # Lifecycle
    status: str = ExperimentStatus.DESIGNED.value
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    owner: str = "system"
    budget: dict[str, Any] = field(default_factory=lambda: ExperimentBudget().to_dict())
    event_timeline: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=now_iso)
    blocked_reason: Optional[str] = None

    # -- Lifecycle --
    def transition(
        self,
        target: ExperimentStatus,
        actor: str = "system",
        notes: str = "",
    ) -> None:
        """Validate and apply a state transition.

        Raises ``ExperimentTransitionError`` if the transition is illegal
        or preconditions are not met.
        """
        current = ExperimentStatus(self.status)
        _validate_experiment_transition(
            current, target,
            require_design=(target in (ExperimentStatus.READY, ExperimentStatus.RUNNING)),
            require_baseline=(target == ExperimentStatus.VERIFYING),
            experiment=self,
        )

        prev = self.status
        self.status = target.value
        self.updated_at = now_iso()
        if target == ExperimentStatus.RUNNING and self.started_at is None:
            self.started_at = now_iso()
        if target in (ExperimentStatus.COMPLETED, ExperimentStatus.FAILED,
                       ExperimentStatus.CANCELLED, ExperimentStatus.INCONCLUSIVE,
                       ExperimentStatus.BLOCKED):
            self.completed_at = now_iso()

        self._record_event(
            kind="transition",
            detail=notes or f"experiment transitioned {prev} → {target.value}",
            actor=actor,
            status_from=prev,
            status_to=target.value,
        )

    @property
    def is_terminal(self) -> bool:
        return _is_experiment_terminal(ExperimentStatus(self.status))

    @property
    def status_enum(self) -> ExperimentStatus:
        try:
            return ExperimentStatus(self.status)
        except ValueError:
            return ExperimentStatus.DESIGNED

    # -- Event timeline --
    def _record_event(
        self,
        kind: str,
        detail: str,
        actor: str = "system",
        status_from: Optional[str] = None,
        status_to: Optional[str] = None,
    ) -> None:
        ev = ExperimentEvent(
            event_id=f"ev_{_short_uuid()}",
            experiment_id=self.experiment_id,
            at=now_iso(),
            kind=kind,
            status_from=status_from,
            status_to=status_to,
            detail=detail,
            actor=actor,
        )
        self.event_timeline.append(ev.to_dict())
        self.updated_at = now_iso()

    def event_timeline_list(self) -> list[dict[str, Any]]:
        return list(self.event_timeline)

    # -- Baseline / Candidates --
    def set_baseline(
        self,
        model: str,
        revision: str,
        metrics: list[Metric],
        compute: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Establish the baseline for this experiment.

        A baseline must exist before VERIFYING/COMPLETED.  This records
        full provenance: model, revision, metrics, compute, timestamp.
        """
        self.baseline = {
            "model": model,
            "revision": revision,
            "metrics": [m.to_dict() for m in metrics],
            "compute": compute,
            "timestamp": timestamp or now_iso(),
            "type": "baseline",
        }
        self.provenance.append(f"baseline:{model}:{revision}")
        self.results.setdefault("baseline", {})
        self.results["baseline"] = {
            "model": model,
            "revision": revision,
            "metrics": [m.to_dict() for m in metrics],
            "compute": compute,
            "timestamp": timestamp or now_iso(),
        }
        self._record_event(
            kind="baseline",
            detail=f"Baseline established: model={model} revision={revision}",
        )

    def add_candidate(
        self,
        model: str,
        revision: str,
        metrics: list[Metric],
        compute: str,
        timestamp: Optional[str] = None,
    ) -> int:
        """Add a candidate result and compute comparison vs baseline.

        Returns the index of the candidate in self.candidates.
        """
        candidate_dict = {
            "model": model,
            "revision": revision,
            "metrics": [m.to_dict() for m in metrics],
            "compute": compute,
            "timestamp": timestamp or now_iso(),
            "type": "candidate",
            "index": len(self.candidates),
        }
        self.candidates.append(candidate_dict)
        self.provenance.append(f"candidate:{model}:{revision}:{len(self.candidates) - 1}")

        # Compute comparisons against baseline
        if self.baseline is not None:
            self._compute_comparisons()

        self._record_event(
            kind="candidate",
            detail=f"Candidate added: model={model} revision={revision}",
        )
        return len(self.candidates) - 1

    def _compute_comparisons(self) -> None:
        """Compute all baseline-vs-candidate comparisons from typed metrics."""
        if not self.baseline:
            return
        baseline_metrics = [
            Metric.from_dict(m) for m in self.baseline.get("metrics", [])
        ]
        self.comparisons = []
        for cand in self.candidates:
            candidate_metrics = [
                Metric.from_dict(m) for m in cand.get("metrics", [])
            ]
            for bm in baseline_metrics:
                for cm in candidate_metrics:
                    comp = ExperimentComparison.from_metrics(bm, cm)
                    if comp is not None:
                        self.comparisons.append(comp.to_dict())

    def compute_comparison(
        self, baseline_metrics: list[Metric], candidate_metrics: list[Metric]
    ) -> list[ExperimentComparison]:
        """Compute comparisons from provided metric lists.

        Neither list may be empty. Both metric lists must have matching
        metric names and evaluation versions for a comparison to be produced.
        Returns an empty list if no comparable metrics exist.
        """
        results: list[ExperimentComparison] = []
        if not baseline_metrics or not candidate_metrics:
            return results
        for bm in baseline_metrics:
            for cm in candidate_metrics:
                comp = ExperimentComparison.from_metrics(bm, cm)
                if comp is not None:
                    results.append(comp)
        return results

    # -- Serialization --
    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "mission_id": self.mission_id,
            "name": self.name,
            "objective": self.objective,
            "hypothesis": self.hypothesis,
            "design": dict(self.design) if self.design else {},
            "variables": list(self.variables),
            "controls": list(self.controls),
            "inputs": list(self.inputs),
            "datasets": list(self.datasets),
            "models": list(self.models),
            "configurations": dict(self.configurations),
            "compute_requirements": dict(self.compute_requirements),
            "evaluation_suite": self.evaluation_suite,
            "baseline": self.baseline,
            "candidates": list(self.candidates),
            "comparisons": list(self.comparisons),
            "results": dict(self.results),
            "artifacts": list(self.artifacts),
            "job_ids": list(self.job_ids),
            "provenance": list(self.provenance),
            "reproducibility_metadata": (
                self.reproducibility_metadata.to_dict()
                if isinstance(self.reproducibility_metadata, ReproducibilityManifest)
                else self.reproducibility_metadata
            ),
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "owner": self.owner,
            "budget": dict(self.budget),
            "event_timeline": list(self.event_timeline),
            "updated_at": self.updated_at,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experiment":
        repro_val = data.get("reproducibility_metadata")
        if isinstance(repro_val, dict):
            repro = ReproducibilityManifest.from_dict(repro_val)
        elif isinstance(repro_val, ReproducibilityManifest):
            repro = repro_val
        else:
            repro = None
        return cls(
            experiment_id=data["experiment_id"],
            mission_id=data["mission_id"],
            name=data["name"],
            objective=data.get("objective", ""),
            hypothesis=data.get("hypothesis", ""),
            design=dict(data.get("design", {})),
            variables=list(data.get("variables", [])),
            controls=list(data.get("controls", [])),
            inputs=list(data.get("inputs", [])),
            datasets=list(data.get("datasets", [])),
            models=list(data.get("models", [])),
            configurations=dict(data.get("configurations", {})),
            compute_requirements=dict(data.get("compute_requirements", {})),
            evaluation_suite=data.get("evaluation_suite", ""),
            baseline=data.get("baseline"),
            candidates=list(data.get("candidates", [])),
            comparisons=list(data.get("comparisons", [])),
            results=dict(data.get("results", {})),
            artifacts=list(data.get("artifacts", [])),
            job_ids=list(data.get("job_ids", [])),
            provenance=list(data.get("provenance", [])),
            reproducibility_metadata=repro,
            status=data.get("status", ExperimentStatus.DESIGNED.value),
            created_at=data.get("created_at", now_iso()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            owner=data.get("owner", "system"),
            budget=dict(data.get("budget", ExperimentBudget().to_dict())),
            event_timeline=list(data.get("event_timeline", [])),
            updated_at=data.get("updated_at", now_iso()),
            blocked_reason=data.get("blocked_reason"),
        )

    # -- Persistence --
    def save(self) -> None:
        """Persist this experiment to the experiment store."""
        store = get_store("experiments")
        experiments = store.load()
        experiments[self.experiment_id] = self.to_dict()
        store.save()

    @staticmethod
    def load(experiment_id: str) -> Optional["Experiment"]:
        """Load an experiment from the persistent store, or None."""
        store = get_store("experiments")
        experiments = store.load()
        raw = experiments.get(experiment_id)
        if raw is None:
            return None
        return Experiment.from_dict(raw)

    @staticmethod
    def list_all() -> list["Experiment"]:
        """Return all saved experiments."""
        store = get_store("experiments")
        experiments = store.load()
        return [Experiment.from_dict(raw) for raw in experiments.values()]

    @staticmethod
    def list_by_mission(mission_id: str) -> list["Experiment"]:
        """Return all experiments linked to a given mission."""
        store = get_store("experiments")
        experiments = store.load()
        return [
            Experiment.from_dict(raw)
            for raw in experiments.values()
            if raw.get("mission_id") == mission_id
        ]

    @staticmethod
    def create(
        mission_id: str,
        name: str,
        objective: str = "",
        owner: str = "system",
        design: Optional[ExperimentDesign] = None,
    ) -> "Experiment":
        """Create a new Experiment in DESIGNED state.

        If ``design`` is provided, its ``to_dict()`` is stored serialized.
        The experiment must have a design before transitioning to READY/RUNNING.
        """
        exp_id = f"exp_{_short_uuid()}"
        exp = Experiment(
            experiment_id=exp_id,
            mission_id=mission_id,
            name=name,
            objective=objective,
            owner=owner,
            status=ExperimentStatus.DESIGNED.value,
        )
        if design is not None:
            exp.design = design.to_dict()
            exp.hypothesis = design.hypothesis
            exp.variables = design.independent_variables
            exp.controls = design.controls
            exp.datasets = design.datasets
            exp.models = design.models
            exp.compute_requirements = design.compute_requirements
            exp.evaluation_suite = design.evaluation_method or ""
        exp.save()
        return exp


# ---------------------------------------------------------------------------
# Experiment Lifecycle (state machine)
# ---------------------------------------------------------------------------
class ExperimentLifecycle:
    """Deterministic state machine for experiment lifecycle transitions.

    Uses the same pattern as MissionLifecycle but for experiments.
    """

    def __init__(self) -> None:
        self._transitions = _EXPERIMENT_TRANSITIONS

    @property
    def valid_transitions(self) -> dict[str, list[str]]:
        """Return transition table as value→list-of-values."""
        return {
            k.value: [t.value for t in v]
            for k, v in self._transitions.items()
        }

    def can_transition(self, current: ExperimentStatus, target: ExperimentStatus) -> bool:
        """Check if a transition is allowed."""
        return target in self._transitions.get(current, frozenset())

    def can_transition_str(self, current: str, target: str) -> bool:
        """String-based transition check (for API use)."""
        try:
            return self.can_transition(ExperimentStatus(current), ExperimentStatus(target))
        except ValueError:
            return False

    def is_terminal(self, status: ExperimentStatus) -> bool:
        return _is_experiment_terminal(status)

    def validate_transition(
        self,
        current: ExperimentStatus,
        target: ExperimentStatus,
        experiment: Optional[Experiment] = None,
    ) -> None:
        """Validate a transition, raising ExperimentTransitionError if invalid."""
        _validate_experiment_transition(
            current, target,
            require_design=(target in (ExperimentStatus.READY, ExperimentStatus.RUNNING)),
            require_baseline=(target == ExperimentStatus.VERIFYING),
            experiment=experiment,
        )

    def terminal_states(self) -> list[str]:
        return [s.value for s in _TERMINAL_STATUSES]


__all__ = [
    "ExperimentStatus",
    "ExperimentTransitionError",
    "ExperimentDesign",
    "Metric",
    "ExperimentComparison",
    "ReproducibilityManifest",
    "ExperimentEvent",
    "ExperimentBudget",
    "Experiment",
    "ExperimentLifecycle",
    # Re-export for convenience
    "_short_uuid",
]
