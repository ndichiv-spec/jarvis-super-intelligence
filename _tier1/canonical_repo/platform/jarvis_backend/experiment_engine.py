"""Phase 11 — Experiment Engine for the JARVIS Laboratory.

The ExperimentOrchestrator drives experiments through the laboratory loop:

    QUESTION → MISSION → HYPOTHESES → EXPERIMENT DESIGN →
    RESOURCE SELECTION → DATA/INPUT → EXECUTION → OBSERVATION →
    ANALYSIS → CRITIQUE → VERIFICATION → COMPARISON → CONCLUSION →
    ARTIFACT → LESSON → NEXT EXPERIMENT

Integrates with:
- cloud_fabric.select_compute() for real compute resource selection
- JobRegistry for job submission/tracking
- ArtifactRegistry for artifact registration
- PromotionGate for model promotion evaluation
- HypothesisEngine for hypothesis outcome recording
- brain_fabric.assert_no_secrets() for secret scrubbing

The Brain never receives provider credentials, API keys, or secrets.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.experiment import (
    Experiment,
    ExperimentComparison,
    ExperimentDesign,
    ExperimentLifecycle,
    ExperimentStatus,
    ExperimentTransitionError,
    Metric,
    ReproducibilityManifest,
    _short_uuid,
)
from jarvis_backend.evaluation_suite import (
    EvaluationSuite,
    EvaluationSuiteRegistry,
    SuiteWrapper,
    EvaluationTask,
)
from jarvis_backend.dataset import Dataset, DatasetRegistry, DatasetValidator

logger = logging.getLogger("jarvis_backend.experiment_engine")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class ExperimentRunResult:
    """Result of attempting to run an experiment."""
    success: bool
    experiment_id: str
    status: str
    message: str = ""
    job_ids: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    resources_selected: Optional[str] = None


@dataclass
class ResourceSelectionResult:
    """Result of compute resource selection for an experiment."""
    selected: bool
    resource_id: str
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    available_resources: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compute Bounds (wraps cloud_fabric)
# ---------------------------------------------------------------------------
@dataclass
class ComputeBounds:
    """Performance bounds and resource requirements for an experiment.

    Wraps cloud_fabric.local_hardware() + select_compute().
    """
    gpu_required: bool = False
    min_gpu_memory_gb: float = 0.0
    min_cpu_cores: int = 1
    min_ram_gb: float = 1.0
    task_type: str = "evaluation"
    max_cost_class: str = "free_local"
    network_required: bool = False
    docker_required: bool = False
    offline_ok: bool = True

    @classmethod
    def from_requirements(cls, reqs: dict[str, Any]) -> "ComputeBounds":
        return cls(
            gpu_required=bool(reqs.get("gpu_required", False)),
            min_gpu_memory_gb=float(reqs.get("min_gpu_memory_gb", 0.0)),
            min_cpu_cores=int(reqs.get("min_cpu_cores", 1)),
            min_ram_gb=float(reqs.get("min_ram_gb", 1.0)),
            task_type=str(reqs.get("task_type", "evaluation")),
            max_cost_class=str(reqs.get("max_cost_class", "free_local")),
            network_required=bool(reqs.get("network_required", False)),
            docker_required=bool(reqs.get("docker_required", False)),
            offline_ok=bool(reqs.get("offline_ok", True)),
        )

    def to_requirements_dict(self) -> dict[str, Any]:
        return {
            "gpu_required": self.gpu_required,
            "min_gpu_memory_gb": self.min_gpu_memory_gb,
            "min_cpu_cores": self.min_cpu_cores,
            "min_ram_gb": self.min_ram_gb,
            "task_type": self.task_type,
            "max_cost_class": self.max_cost_class,
            "network_required": self.network_required,
            "docker_required": self.docker_required,
            "offline_ok": self.offline_ok,
        }


# ---------------------------------------------------------------------------
# Experiment Orchestrator
# ---------------------------------------------------------------------------
class ExperimentOrchestrator:
    """Orchestrates experiments through the laboratory pipeline."""

    def __init__(self) -> None:
        self.lifecycle = ExperimentLifecycle()

    # ------------------------------------------------------------------ #
    # Design
    # ------------------------------------------------------------------ #
    def design_experiment(
        self,
        mission_id: str,
        name: str,
        design: ExperimentDesign,
        owner: str = "system",
    ) -> Experiment:
        """Create a new experiment from a design in DESIGNED state."""
        exp = Experiment.create(
            mission_id=mission_id,
            name=name,
            objective=design.question,
            owner=owner,
            design=design,
        )
        # Verify no secrets in design
        from jarvis_backend.brain_fabric import assert_no_secrets
        leaks = assert_no_secrets(design.to_dict())
        if leaks:
            logger.error("Secrets detected in experiment design: %s", leaks)
            exp.blocked_reason = f"secrets_detected: {leaks}"
            exp.status = ExperimentStatus.BLOCKED.value
            exp.save()
            raise ValueError(f"Secrets detected in experiment design: {leaks}")

        logger.info("Experiment %s designed for mission %s", exp.experiment_id, mission_id)
        return exp

    # ------------------------------------------------------------------ #
    # Resource selection
    # ------------------------------------------------------------------ #
    def select_resources(self, exp_id: str) -> ResourceSelectionResult:
        """Select compute resources using cloud_fabric — never fabricates."""
        exp = Experiment.load(exp_id)
        if exp is None:
            return ResourceSelectionResult(
                selected=False, resource_id="", reason="experiment_not_found",
            )
        try:
            from jarvis_backend.cloud_fabric import select_compute, cloud_resources
            cf = cloud_resources()
            by_id = cf.get("by_id", {})
            bounds = ComputeBounds.from_requirements(exp.compute_requirements)
            reqs = bounds.to_requirements_dict()

            sel_result = select_compute(reqs)
            resource_id = sel_result.get("selected", "") if sel_result else None

            if resource_id:
                return ResourceSelectionResult(
                    selected=True,
                    resource_id=resource_id,
                    reason="resource_selected",
                    details=sel_result or {},
                    available_resources=[dict(r) for r in cf.get("resources", [])],
                )
            else:
                available = []
                for rid, rinfo in by_id.items():
                    available.append({
                        "resource_id": rid,
                        "status": rinfo.get("status", "UNKNOWN"),
                        "type": rinfo.get("type", ""),
                    })
                return ResourceSelectionResult(
                    selected=False, resource_id="",
                    reason=sel_result.get("infeasible_reason") or "no_resources_available",
                    available_resources=available,
                )
        except Exception as exc:
            logger.debug("Resource selection failed: %s", exc)
            return ResourceSelectionResult(
                selected=False, resource_id="",
                reason=f"{type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------ #
    # Prepare
    # ------------------------------------------------------------------ #
    def prepare_experiment(self, exp_id: str) -> Experiment:
        """Prepare an experiment: select resources, validate prerequisites."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        if exp.status != ExperimentStatus.DESIGNED.value:
            if exp.status != ExperimentStatus.BLOCKED.value:
                raise ExperimentTransitionError(
                    f"Cannot prepare experiment in status {exp.status}"
                )

        selection = self.select_resources(exp_id)
        if not selection.selected:
            exp.transition(ExperimentStatus.BLOCKED, actor="orchestrator",
                           notes=selection.reason)
            exp.blocked_reason = selection.reason
            exp.provenance.append(f"resource_selection_blocked:{selection.reason}")
            exp.save()
            return exp

        bounds = ComputeBounds.from_requirements(exp.compute_requirements)
        if not self._validate_resource(selection.resource_id, bounds, exp):
            exp.transition(ExperimentStatus.BLOCKED, actor="orchestrator",
                           notes="resource_does_not_meet_requirements")
            exp.blocked_reason = "resource_does_not_meet_requirements"
            exp.save()
            return exp

        exp.compute_requirements = dict(exp.compute_requirements)
        exp.compute_requirements["selected_resource"] = selection.resource_id
        exp.provenance.append(f"resource_selected:{selection.resource_id}")
        exp.save()

        exp.transition(ExperimentStatus.READY, actor="orchestrator",
                      notes=f"Resources selected: {selection.resource_id}")
        return exp

    def _validate_resource(self, resource_id: str, bounds: ComputeBounds, exp: Experiment) -> bool:
        """Validate that a resource meets the experiment's compute requirements."""
        try:
            from jarvis_backend.cloud_fabric import cloud_resources
            cf = cloud_resources()
            by_id = cf.get("by_id", {})
            rinfo = by_id.get(resource_id, {})
            if not rinfo:
                if resource_id == "local:control-node":
                    return not bounds.gpu_required
                return False
            status = rinfo.get("status", "UNKNOWN")
            if status not in ("AVAILABLE", "READY", "HEALTHY"):
                if status == "DEGRADED" and not bounds.gpu_required:
                    return True
                return False
            if bounds.gpu_required:
                rtype = rinfo.get("type", "")
                if rtype not in ("gpu_inference", "gpu_training"):
                    return False
            return True
        except Exception as exc:
            logger.debug("Resource validation failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #
    def run_experiment(self, exp_id: str) -> ExperimentRunResult:
        """Run an experiment: submit job, execute, collect observations."""
        exp = Experiment.load(exp_id)
        if exp is None:
            return ExperimentRunResult(
                success=False, experiment_id=exp_id,
                status=ExperimentStatus.BLOCKED.value,
                message="experiment_not_found",
            )

        if exp.status == ExperimentStatus.READY.value:
            exp.transition(ExperimentStatus.RUNNING, actor="orchestrator", notes="Job submitted")
        elif exp.status == ExperimentStatus.DESIGNED.value:
            exp = self.prepare_experiment(exp_id)
            if exp.status == ExperimentStatus.BLOCKED.value:
                return ExperimentRunResult(
                    success=False, experiment_id=exp_id, status=exp.status,
                    message=exp.blocked_reason or "blocked",
                    blocked_reason=exp.blocked_reason,
                )
            exp.transition(ExperimentStatus.RUNNING, actor="orchestrator",
                          notes="Job submitted after auto-prepare")
        else:
            raise ExperimentTransitionError(
                f"Cannot run experiment in status {exp.status}"
            )

        exp.save()

        # Submit job to JobRegistry
        job_result = self._submit_evaluation_job(exp)
        if job_result["success"]:
            exp.job_ids.append(job_result["job_id"])
            exp.save()
        else:
            exp.transition(ExperimentStatus.FAILED, actor="orchestrator",
                          notes=f"Job submission failed: {job_result.get('error', 'unknown')}")
            exp.save()
            return ExperimentRunResult(
                success=False, experiment_id=exp_id, status=exp.status,
                message=job_result.get("error", "job_submission_failed"),
                job_ids=exp.job_ids,
            )

        # Run the evaluation (analysis phase)
        exp = self.analyze_results(exp_id)

        return ExperimentRunResult(
            success=True,
            experiment_id=exp_id,
            status=exp.status,
            message="experiment analysis complete",
            job_ids=exp.job_ids,
            metrics=[m for c in exp.candidates for m in c.get("metrics", [])],
            resources_selected=exp.compute_requirements.get("selected_resource"),
        )

    def _submit_evaluation_job(self, exp: Experiment) -> dict[str, Any]:
        """Submit an evaluation job to JobRegistry. Never fabricates."""
        try:
            from infrastructure.job_registry import JobRegistry, JobInfo, JobType, JobStatus
            from jarvis_backend.cloud_fabric import cloud_resources

            registry = JobRegistry.get_instance()
            resource = exp.compute_requirements.get("selected_resource", "local:control-node")
            cf = cloud_resources()
            by_id = cf.get("by_id", {})
            rinfo = by_id.get(resource, {})

            job = JobInfo(
                id=str(_uuid.uuid4()),
                job_id=f"job_{_short_uuid()}",
                job_type=JobType.EVALUATION.value,
                status=JobStatus.QUEUED.value,
                model_id=exp.models[0] if exp.models else "",
                model_version="",
                resource_cpu=float(rinfo.get("cpu_cores", 1)),
                resource_memory_gb=float(rinfo.get("memory_gb", 2.0) or 2.0),
                resource_gpu=int(rinfo.get("gpu_count", 0) or 0),
                resource_gpu_type=str(rinfo.get("gpu_type", "")),
                resource_instance_type=str(rinfo.get("instance_type", "")),
                config=exp.configurations,
                parameters=exp.compute_requirements,
                input_artifacts=exp.artifacts,
                output_artifacts=[],
                priority=0,
                max_retries=0,
                created_by=exp.owner,
                estimated_cost_usd=0.0,
                tags=["experiment", exp.experiment_id, exp.mission_id],
            )
            created = registry.create_job(job)
            return {"success": True, "job_id": created.job_id}
        except Exception as exc:
            logger.debug("Job submission failed: %s", exc)
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------ #
    # Analyze
    # ------------------------------------------------------------------ #
    def analyze_results(self, exp_id: str) -> Experiment:
        """Analyze experiment results: compute metrics via EvaluationSuite."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        if exp.status == ExperimentStatus.RUNNING.value:
            exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator",
                          notes="Computing metrics")
        elif exp.status != ExperimentStatus.ANALYZING.value:
            raise ExperimentTransitionError(
                f"Cannot analyze experiment in status {exp.status}"
            )

        metrics = self._compute_metrics(exp)
        exp.results["metrics"] = [m.to_dict() for m in metrics]
        exp.save()
        return exp

    def _compute_metrics(self, exp: Experiment) -> list[Metric]:
        """Compute metrics using EvaluationSuite — never fabricates."""
        suite = EvaluationSuiteRegistry.get(exp.evaluation_suite)
        if suite is None:
            suite = EvaluationSuite.load(exp.evaluation_suite)
        if suite is None:
            logger.warning("Evaluation suite %s not found", exp.evaluation_suite)
            return [Metric(
                name="no_suite", value=0.0, unit="ratio",
                higher_is_better=True, sample_count=0,
                evaluation_version=exp.evaluation_suite or "unknown",
                provenance=["suite_not_found"],
            )]

        all_metrics: list[Metric] = []
        for task_dict in suite.tasks:
            task = EvaluationTask.from_dict(task_dict) if isinstance(task_dict, dict) else task_dict
            task_metrics = self._run_task(task, suite, exp)
            all_metrics.extend(task_metrics)
        return all_metrics

    def _run_task(self, task: Any, suite: EvaluationSuite, exp: Experiment) -> list[Metric]:
        """Run a single evaluation task, returning typed Metrics."""
        task_id = task.task_id if hasattr(task, "task_id") else task.get("task_id", "")
        checkpoint = exp.models[0] if exp.models else ""

        if task_id in ("math_arithmetic", "math_algebra"):
            return SuiteWrapper.run_math_evaluation(
                checkpoint_dir=checkpoint, device="cpu",
                evaluation_version=suite.versioned_id,
            )
        elif task_id == "code_python":
            return SuiteWrapper.run_coding_evaluation(
                checkpoint_dir=checkpoint, device="cpu",
                evaluation_version=suite.versioned_id,
            )
        elif task_id == "doc_qa" or task_id == "rag_qa":
            return SuiteWrapper.run_knowledge_evaluation(
                checkpoint_dir=checkpoint, device="cpu",
                evaluation_version=suite.versioned_id,
            )
        elif task_id == "perplexity_eval":
            val_file = exp.configurations.get("val_file", "")
            if checkpoint and val_file:
                return SuiteWrapper.run_full_checkpoint_evaluation(
                    checkpoint_dir=checkpoint, val_file=val_file,
                    work_dir="jarvis_data/experiments",
                    tag=exp.name,
                    evaluation_version=suite.versioned_id,
                )
            return [Metric(
                name="val_ppl", value=0.0, unit="perplexity",
                higher_is_better=False, sample_count=0,
                evaluation_version=suite.versioned_id,
                provenance=["checkpoint_or_val_file_not_provided"],
            )]
        else:
            return [Metric(
                name=f"{task_id}_accuracy", value=0.0, unit="ratio",
                higher_is_better=True, sample_count=0,
                evaluation_version=suite.versioned_id,
                provenance=[f"task_not_mapped:{task_id}"],
            )]

    # ------------------------------------------------------------------ #
    # Verify
    # ------------------------------------------------------------------ #
    def verify_experiment(self, exp_id: str) -> Experiment:
        """Verify an experiment's results: metric schema, provenance, comparison."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        if exp.status == ExperimentStatus.ANALYZING.value:
            try:
                exp.transition(ExperimentStatus.VERIFYING, actor="orchestrator",
                              notes="Verifying experiment results")
            except ExperimentTransitionError:
                # e.g. missing baseline required for VERIFYING — collect issue
                # and transition to FAILED below instead of crashing.
                issues = []
                if not exp.baseline:
                    issues.append("missing_baseline: experiment has no baseline")
                exp.results["verification_issues"] = issues
                exp.save()
                exp.transition(ExperimentStatus.FAILED, actor="orchestrator",
                              notes=f"Verification failed: {'; '.join(issues) if issues else 'transition failed'}")
                return exp
        elif exp.status != ExperimentStatus.VERIFYING.value:
            raise ExperimentTransitionError(
                f"Cannot verify experiment in status {exp.status}"
            )

        issues: list[str] = []

        # Check metric schema
        all_metrics = []
        if exp.baseline:
            all_metrics.extend(exp.baseline.get("metrics", []))
        for cand in exp.candidates:
            all_metrics.extend(cand.get("metrics", []))

        for m in all_metrics:
            if not isinstance(m, dict):
                issues.append(f"metric_not_dict: {m}")
                continue
            for field_name in ("name", "value", "unit", "provenance"):
                if field_name not in m:
                    issues.append(f"metric_missing_{field_name}")

        # Check baseline exists for improvement experiments
        if not exp.baseline:
            issues.append("missing_baseline: experiment has no baseline")

        # Check comparison integrity
        for comp in exp.comparisons:
            if not isinstance(comp, dict):
                issues.append("comparison_not_dict")
                continue
            for field_name in ("baseline_value", "candidate_value", "absolute_difference",
                               "relative_difference", "evaluation_version"):
                if field_name not in comp:
                    issues.append(f"comparison_missing_{field_name}")

        # Check provenance
        if not exp.provenance:
            issues.append("missing_provenance: no provenance records")

        if issues:
            exp.results["verification_issues"] = issues
            exp.save()
            if any("missing_baseline" in i for i in issues):
                exp.transition(ExperimentStatus.FAILED, actor="orchestrator",
                              notes=f"Verification failed: {'; '.join(issues)}")
            else:
                exp.transition(ExperimentStatus.INCONCLUSIVE, actor="orchestrator",
                              notes=f"Verification inconclusive: {'; '.join(issues)}")
        else:
            exp.results["verification_passed"] = True
            exp.results["verification_at"] = now_iso()
            exp.save()
            exp.transition(ExperimentStatus.COMPLETED, actor="orchestrator",
                          notes="All verification checks passed")
        return exp

    # ------------------------------------------------------------------ #
    # Complete
    # ------------------------------------------------------------------ #
    def complete_experiment(self, exp_id: str) -> Experiment:
        """Finalize a verified experiment. Generates reproducibility manifest."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        if exp.status != ExperimentStatus.VERIFYING.value:
            if exp.status == ExperimentStatus.COMPLETED.value:
                # Already completed — ensure manifest is built if missing
                if exp.reproducibility_metadata is None:
                    manifest = self._build_reproducibility_manifest(exp)
                    exp.reproducibility_metadata = manifest
                    exp.save()
                    self._record_hypothesis_outcome(exp)
                return exp
            raise ExperimentTransitionError(
                f"Cannot complete experiment in status {exp.status} — must be VERIFYING"
            )

        manifest = self._build_reproducibility_manifest(exp)
        exp.reproducibility_metadata = manifest
        exp.save()

        exp.transition(ExperimentStatus.COMPLETED, actor="orchestrator",
                      notes=f"Experiment completed with reproducibility manifest {manifest.manifest_id}")

        self._record_hypothesis_outcome(exp)
        return exp

    def _build_reproducibility_manifest(self, exp: Experiment) -> ReproducibilityManifest:
        """Build a reproducibility manifest from experiment data."""
        code_revision = ""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=os.getcwd()
            )
            if result.returncode == 0:
                code_revision = result.stdout.strip()
        except Exception:
            code_revision = "unknown"

        sw_versions = {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        try:
            import torch
            sw_versions["torch"] = torch.__version__
        except ImportError:
            sw_versions["torch"] = "not_installed"
        try:
            import safetensors
            sw_versions["safetensors"] = safetensors.__version__
        except ImportError:
            sw_versions["safetensors"] = "not_installed"

        dataset_versions = []
        for ds_id in exp.datasets:
            ds = Dataset.load(ds_id)
            if ds is not None:
                dataset_versions.append({
                    "dataset_id": ds.dataset_id,
                    "version": ds.version,
                    "hash": ds.hash,
                })

        model_versions = [{"model": m, "revision": ""} for m in exp.models]

        metrics = []
        if exp.baseline:
            metrics.extend(exp.baseline.get("metrics", []))
        for cand in exp.candidates:
            metrics.extend(cand.get("metrics", []))

        return ReproducibilityManifest(
            code_revision=code_revision,
            dataset_versions=dataset_versions,
            model_versions=model_versions,
            configuration=exp.configurations,
            hyperparameters=exp.compute_requirements,
            evaluation_suite=exp.evaluation_suite,
            compute_resource=exp.compute_requirements.get("selected_resource", "unknown"),
            environment={
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "torch_available": sw_versions.get("torch", "unknown"),
            },
            random_seed=exp.configurations.get("seed"),
            software_versions=sw_versions,
            artifacts=exp.artifacts,
            metrics=metrics,
        )

    def _record_hypothesis_outcome(self, exp: Experiment) -> None:
        """Record the experiment outcome in the HypothesisEngine."""
        try:
            from jarvis_backend.hypothesis_engine import HypothesisEngine
            engine = HypothesisEngine()
            for h in engine.list_all():
                if h.statement == exp.hypothesis or h.id in exp.provenance:
                    evidence = []
                    if exp.baseline and exp.candidates:
                        for comp_dict in exp.comparisons:
                            evidence.append({
                                "type": "experiment_comparison",
                                "experiment_id": exp.experiment_id,
                                "metric": comp_dict.get("metric_name", ""),
                                "baseline_value": comp_dict.get("baseline_value", 0),
                                "candidate_value": comp_dict.get("candidate_value", 0),
                                "absolute_difference": comp_dict.get("absolute_difference", 0),
                                "relative_difference": comp_dict.get("relative_difference", 0),
                                "evaluation_version": comp_dict.get("evaluation_version", ""),
                            })
                    if evidence:
                        engine.evaluate(h.id, evidence=evidence, experiments=[exp])
                    break
        except Exception as exc:
            logger.debug("Hypothesis recording failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Baseline/Candidate management
    # ------------------------------------------------------------------ #
    def establish_baseline(
        self, exp_id: str, model: str, revision: str,
        metrics: list[Metric], compute: str,
    ) -> Experiment:
        """Establish the baseline for an experiment. Mandatory before VERIFYING."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        from jarvis_backend.brain_fabric import assert_no_secrets
        for m in metrics:
            assert_no_secrets(m.to_dict())

        exp.set_baseline(model=model, revision=revision, metrics=metrics, compute=compute)
        exp.save()
        return exp

    def add_candidate(
        self, exp_id: str, model: str, revision: str,
        metrics: list[Metric], compute: str,
    ) -> int:
        """Add a candidate and compute comparisons vs baseline."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        from jarvis_backend.brain_fabric import assert_no_secrets
        for m in metrics:
            assert_no_secrets(m.to_dict())

        idx = exp.add_candidate(model=model, revision=revision, metrics=metrics, compute=compute)
        exp.save()
        return idx

    # ------------------------------------------------------------------ #
    # Promotion gate integration
    # ------------------------------------------------------------------ #
    def evaluate_for_promotion(self, exp_id: str) -> dict[str, Any]:
        """Feed experiment results into the PromotionGate.

        Uses the experiment's actual comparison data to determine if the
        candidate model meets promotion criteria. Never fabricates.
        """
        exp = Experiment.load(exp_id)
        if exp is None:
            return {"approved": False, "reason": "experiment_not_found"}

        if not exp.comparisons:
            return {"approved": False, "reason": "no_comparisons_available"}

        if not exp.candidates:
            return {"approved": False, "reason": "no_candidate_model"}

        candidate = exp.candidates[0]
        model_id = candidate.get("model", "")

        # Derive criteria from the experiment's success criteria.
        # The candidate is approved if ALL comparisons show improvement
        # (no regressions) per the experiment's success/failure criteria.
        try:
            from infrastructure.promotion_gate import (
                get_promotion_gate,
                EvaluationCriteria,
                PromotionOutcome,
            )
            gate = get_promotion_gate()

            # Build metrics dict from candidate
            metrics_dict = {}
            for m in candidate.get("metrics", []):
                if isinstance(m, dict):
                    metrics_dict[m.get("name", "")] = m.get("value", 0.0)

            criteria = EvaluationCriteria(
                min_accuracy=0.0,
                cost_policy="best_quality",
            )

            decision = gate.evaluate_for_promotion(
                model_id=model_id,
                criteria=criteria,
                evaluator="experiment_orchestrator",
            )
            outcome, evidence = decision

            # Fall back to comparison-based decision if model not in registry
            if outcome == PromotionOutcome.REJECTED and "Model not found" in str(evidence.get("error", "")):
                # Model not registered — use comparison data directly
                has_regression = False
                for comp in exp.comparisons:
                    if isinstance(comp, dict):
                        rel_diff = comp.get("relative_difference", 0.0)
                    else:
                        rel_diff = comp.relative_difference
                    # Check if relative difference indicates regression
                    metric = comp if isinstance(comp, ExperimentComparison) else None
                    if metric and not metric.higher_is_better:
                        # For metrics where lower is better, a negative diff is bad
                        if rel_diff < 0:
                            has_regression = True
                    elif isinstance(comp, dict):
                        # For accuracy-like metrics, negative diff is regression
                        if rel_diff < 0:
                            has_regression = True

                approved = not has_regression and len(exp.comparisons) > 0
                return {
                    "approved": approved,
                    "outcome": "approved" if approved else "blocked",
                    "reason": "model_not_registered_comparison_based" if not approved else "no_regression",
                    "model_id": model_id,
                }

            approved = outcome == PromotionOutcome.APPROVED
            return {
                "approved": approved,
                "outcome": outcome.value,
                "reason": evidence.get("reason", ""),
                "model_id": model_id,
            }
        except Exception as exc:
            logger.debug("Promotion evaluation failed: %s", exc)
            return {"approved": False, "reason": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------ #
    # Blocked reporting
    # ------------------------------------------------------------------ #
    def report_blocked(self, exp_id: str, resource_id: str, reason: str) -> Experiment:
        """Truthfully report that an experiment is blocked by a resource."""
        exp = Experiment.load(exp_id)
        if exp is None:
            raise KeyError(f"Experiment not found: {exp_id}")

        exp.blocked_reason = f"{resource_id}: {reason}"
        exp.provenance.append(f"blocked:{resource_id}:{reason}")
        exp.transition(ExperimentStatus.BLOCKED, actor="orchestrator",
                      notes=f"Blocked: {resource_id} — {reason}")
        exp.save()
        return exp


__all__ = [
    "ExperimentRunResult",
    "ResourceSelectionResult",
    "ComputeBounds",
    "ExperimentOrchestrator",
]
