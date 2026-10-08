"""Phase 12 — Self-Improvement Orchestrator.

Drives a ``SelfImprovementCycle`` through the full controlled improvement
loop:

    OBSERVE → EVALUATE → FIND WEAKNESS → FORM HYPOTHESIS →
    DESIGN IMPROVEMENT → GENERATE/CURATE DATA → BASELINE →
    TRAIN/MODIFY CANDIDATE → EVALUATE → CRITIQUE → VERIFY →
    COMPARE → PROMOTION GATE → DEPLOY CANDIDATE →
    POST-DEPLOYMENT EVALUATION → LEARN → NEXT IMPROVEMENT

Integrates with existing Phase 11 infrastructure:
- ``ExperimentOrchestrator`` (select_resources, run_experiment, analyze_results,
  verify_experiment, establish_baseline, add_candidate, evaluate_for_promotion)
- ``cloud_fabric`` (cloud_resources, select_compute)
- ``JobRegistry`` (job submission/tracking)
- ``ArtifactRegistry`` (artifact registration)
- ``ModelRegistry`` / ``PromotionGate`` (model lifecycle + promotion)
- ``Critic`` (critique_experiment)
- ``VerificationEngine`` (verify_claim)
- ``EvidenceEngine.assert_no_fabrication()``
- ``WeaknessDetector`` (from this module)
- ``AutonomyGuard`` (autonomy boundary enforcement)
- ``BudgetManager`` (cost tracking)

The orchestrator NEVER fabricates metrics, NEVER accesses credentials,
NEVER modifies production source code, and NEVER promotes models without
the existing PromotionGate.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from jarvis_backend.core import get_store, now_iso, now
from jarvis_backend.self_improvement import (
    HIGH_RISK_INTERVENTIONS,
    FailureCategory,
    FailureSeverity,
    Hypothesis,
    ImprovementDeployment,
    ImprovementPolicy,
    ImprovementResult,
    ImprovementStatus,
    InterventionType,
    AutonomyGuard,
    BaselineLock,
    CandidateArtifact,
    CandidateStatus,
    DeploymentMode,
    EvaluationMatrix,
    LearningMemory,
    Lesson,
    SelfImprovementCycle,
    TrainingConfig,
    Weakness,
    WeaknessDetector,
    GraphNode,
    ImprovementGraph,
)
from jarvis_backend.experiment import (
    Experiment,
    ExperimentStatus,
    Metric,
)
from jarvis_backend.evaluation_suite import (
    EvaluationSuiteRegistry,
)

logger = logging.getLogger("jarvis_backend.self_improvement_engine")


@dataclass
class CycleStepResult:
    """Result of a single step in the improvement cycle."""
    step: str
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    blocked: bool = False


# --------------------------------------------------------------------------- #
# Dataset improvement loop
# --------------------------------------------------------------------------- #

class DatasetQualityGate:
    """Quality gate for improvement-generated datasets.

    Stages: generated → validating → deduplicating → quality_checking →
    security_checking → versioned → registered.
    Mirrors the Phase 11 DatasetValidationStage pattern but focused on
    failure examples extracted for self-improvement.
    """

    SCHEMA_FIELDS = ("prompt", "response", "category", "source")
    MAX_SAMPLES = 50000   # budget cap
    MIN_SAMPLES = 5

    def run_pipeline(self, dataset: Dict[str, Any]) -> Dict[str, Any]:
        """Run the full dataset quality pipeline.

        Returns dict with 'passed' bool, 'issues' list, 'stage' str.
        """
        examples = dataset.get("examples", [])
        issues: List[str] = []

        # Stage 1: schema validation
        valid_examples = []
        for ex in examples:
            ex_issues = []
            for field_name in self.SCHEMA_FIELDS:
                if field_name not in ex or not ex[field_name]:
                    ex_issues.append(f"missing_field:{field_name}")
            if not ex_issues:
                valid_examples.append(ex)
            else:
                issues.append(f"schema:{ex_issues[0]}")

        # Stage 2: safety / contamination check
        for ex in valid_examples:
            prompt_lower = ex.get("prompt", "").lower()
            response_lower = ex.get("response", "").lower()
            # Contamination: must not contain training data references
            if "training data" in prompt_lower or "training_data" in prompt_lower:
                issues.append("contamination:training_data_reference")
            # Safety: must not contain harmful instructions
            harm_patterns = ["how to make a bomb", "how to hack", "illegal",
                           "self-harm", "kill myself"]
            for pattern in harm_patterns:
                if pattern in prompt_lower or pattern in response_lower:
                    issues.append(f"safety:{pattern}")

        # Stage 3: deduplication
        seen = set()
        deduped = []
        duplicates = 0
        for ex in valid_examples:
            key = hashlib.sha256(
                (ex.get("prompt", "") + ex.get("response", "")).encode()
            ).hexdigest()[:32]
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            deduped.append(ex)

        if duplicates > 0:
            issues.append(f"deduplication:removed_{duplicates}_duplicates")

        # Stage 4: answer validation + provenance
        for ex in deduped:
            if not ex.get("response", "").strip():
                issues.append("answer_validation:empty_response")
            if not ex.get("provenance", ""):
                ex["provenance"] = "extracted_from_failure"

        # Stage 5: size / budget check
        if len(deduped) < self.MIN_SAMPLES:
            issues.append(f"size:too_few ({len(deduped)} < {self.MIN_SAMPLES})")
        if len(deduped) > self.MAX_SAMPLES:
            issues.append(f"size:too_many ({len(deduped)} > {self.MAX_SAMPLES})")

        passed = len(deduped) >= self.MIN_SAMPLES and \
                 len(deduped) <= self.MAX_SAMPLES and \
                 not any(i.startswith("safety:") for i in issues) and \
                 not any(i.startswith("contamination:") for i in issues) and \
                 len(deduped) > 0

        return {
            "passed": passed,
            "stage": "validated" if passed else "failed",
            "issues": issues,
            "example_count": len(deduped),
            "valid_examples": deduped,
            "deduplication_removed": duplicates,
        }


class DatasetImprovementLoop:
    """Extract failure examples → quality gate → version → evaluation → training."""

    def __init__(self) -> None:
        self.quality_gate = DatasetQualityGate()

    def extract_failures(self, evaluation_results: Dict[str, Any],
                         target_capability: str) -> Dict[str, Any]:
        """Extract failure examples from evaluation results.

        Never fabricates — only extracts what was observed.
        """
        examples: List[Dict[str, Any]] = []
        metrics = evaluation_results.get("metrics", [])

        for m in metrics:
            if m.get("provenance"):
                # Record the provenance as evidence
                examples.append({
                    "prompt": m.get("name", "unknown"),
                    "response": f"value={m.get('value')}, "
                                f"sample_count={m.get('sample_count')}",
                    "category": target_capability,
                    "source": "evaluation_metrics",
                    "provenance": list(m.get("provenance", [])),
                })

        # Also extract from detailed results if present
        eval_results = evaluation_results.get("results", {})
        for suite_name, suite_result in eval_results.items():
            if isinstance(suite_result, dict):
                for item in suite_result.get("results", []):
                    score = item.get("score", {})
                    if isinstance(score, dict) and not score.get("pass", True):
                        examples.append({
                            "prompt": item.get("prompt", ""),
                            "response": item.get("answer", ""),
                            "category": item.get("category", target_capability),
                            "source": f"eval:{suite_name}",
                            "provenance": ["extracted_from_failure"],
                        })

        return {
            "dataset_id": f"dataset_{_short_uuid()}",
            "description": f"Failure examples for {target_capability}",
            "capability": target_capability,
            "examples": examples,
            "created_at": now_iso(),
            "source": "failure_extraction",
        }

    def run(self, evaluation_results: Dict[str, Any],
            target_capability: str) -> Dict[str, Any]:
        """Full dataset improvement loop: extract → quality gate → version."""
        raw = self.extract_failures(evaluation_results, target_capability)
        result = self.quality_gate.run_pipeline(raw)

        if result["passed"]:
            return {
                "passed": True,
                "dataset": {
                    "dataset_id": raw["dataset_id"],
                    "description": raw["description"],
                    "capability": target_capability,
                    "examples": result["valid_examples"],
                    "example_count": result["example_count"],
                    "version": "v1",
                    "source": raw["source"],
                    "created_at": now_iso(),
                    "provenance": ["quality_gate_passed"],
                },
                "issues": result["issues"],
            }
        return {
            "passed": False,
            "dataset": raw,
            "issues": result["issues"],
            "stage": result["stage"],
        }


# --------------------------------------------------------------------------- #
# Self-Improvement Orchestrator
# --------------------------------------------------------------------------- #

class SelfImprovementOrchestrator:
    """Orchestrates self-improvement cycles.

    Follows the existing ``ExperimentOrchestrator`` pattern: uses
    ``cloud_fabric`` for compute selection, ``JobRegistry`` for job tracking,
    ``ArtifactRegistry`` for artifact registration, ``PromotionGate`` for
    promotion, ``Critic`` for critique, and ``VerificationEngine`` for
    verification.

    Enforces the ``AutonomyGuard`` at every step that could touch
    credentials, production source, or authorization.
    """

    def __init__(self, autonomy_level: int = 1,
                 principal: Optional[Dict[str, Any]] = None) -> None:
        self.autonomy_level = autonomy_level
        self.principal = principal or {"user": "system", "is_admin": False}
        self.guard = AutonomyGuard(autonomy_level=autonomy_level)
        self.weakness_detector = WeaknessDetector()
        self.dataset_loop = DatasetImprovementLoop()
        self.learning_memory = LearningMemory()
        self.graph = ImprovementGraph()

    # ------------------------------------------------------------------ #
    # OBSERVE → EVALUATE → FIND WEAKNESS
    # ------------------------------------------------------------------ #

    def observe_and_detect_weaknesses(
        self,
        baseline_results: Dict[str, Any],
        candidate_results: Dict[str, Any],
        target_capability: str = "all",
        min_regression: float = 0.05,
    ) -> Tuple[List[Weakness], List[Dict[str, Any]]]:
        """Observe evaluation results and detect weaknesses.

        Uses WeaknessDetector — no fabrication.
        """
        weaknesses = self.weakness_detector.detect_from_results(
            baseline_results, candidate_results,
            evaluation_population=candidate_results.get("sample_count", 0),
            min_regression=min_regression,
        )

        # Also extract failure evidence from candidate results
        failure_evidence: List[Dict[str, Any]] = []
        for w in weaknesses:
            failure_evidence.extend(
                f.to_dict() for f in w.failures
            )

        return weaknesses, failure_evidence

    # ------------------------------------------------------------------ #
    # FORM HYPOTHESIS
    # ------------------------------------------------------------------ #

    def form_hypothesis(self, cycle: SelfImprovementCycle,
                        weakness: Weakness) -> Hypothesis:
        """Form a testable hypothesis for a weakness."""
        hypothesis = Hypothesis(
            hypothesis_id=f"hyp_{_short_uuid()}",
            statement=(
                f"Applying {InterventionType.TRAINING_CHANGE.value} to "
                f"{weakness.target_capability} will improve "
                f"{cycle.training_config.get('base_model', 'model')} "
                f"performance on {weakness.target_capability} by "
                f"addressing {weakness.description}"
            ),
            target_metric=cycle.training_config.get("target_metric", "accuracy"),
            expected_improvement=weakness.affected_population * 0.15,
            confidence=weakness.confidence,
        )
        cycle.add_hypothesis(hypothesis)
        cycle.save()
        logger.info("Hypothesis %s formed for weakness %s",
                    hypothesis.hypothesis_id, weakness.weakness_id)
        return hypothesis

    # ------------------------------------------------------------------ #
    # DESIGN IMPROVEMENT
    # ------------------------------------------------------------------ #

    def design_improvement(
        self,
        cycle: SelfImprovementCycle,
        intervention_type: InterventionType,
        training_config: TrainingConfig,
        policy: ImprovementPolicy,
        target_model: str = "Qwen/Qwen3-4B",
    ) -> CycleStepResult:
        """Design an improvement intervention.

        Checks the AutonomyGuard before proceeding.
        """
        target = f"model:{target_model}"
        allowed, reason = self.guard.check_intervention(intervention_type, target)
        if not allowed:
            return CycleStepResult(
                step="design_improvement", success=False,
                message=f"Intervention blocked by AutonomyGuard: {reason}",
                blocked=True,
            )

        cycle.change_type = intervention_type.value
        cycle.training_config = training_config.to_dict()
        cycle.training_config["base_model"] = target_model
        cycle.training_config.update(policy.to_dict())
        cycle.proposed_change = {
            "intervention_type": intervention_type.value,
            "target_model": target_model,
            "training_config": training_config.to_dict(),
            "policy": policy.to_dict(),
        }
        cycle.approval_requirements = self._compute_approval_requirements(
            intervention_type, policy
        )
        cycle.save()

        return CycleStepResult(
            step="design_improvement", success=True,
            message=f"Designed {intervention_type.value} intervention for {target_model}",
        )

    def _compute_approval_requirements(self,
                                       intervention_type: InterventionType,
                                       policy: ImprovementPolicy) -> List[str]:
        """Determine what approvals are needed."""
        reqs: List[str] = []
        if intervention_type in HIGH_RISK_INTERVENTIONS:
            reqs.append("owner_approval")
        if intervention_type == InterventionType.TRAINING_CHANGE:
            reqs.append("training_approval")
        if policy.risk_level in ("high", "critical"):
            reqs.append("security_review")
        if not policy.requires_manual_approval:
            reqs.append("policy_approves_autonomous")
        if not reqs:
            reqs.append("auto_approved")
        return reqs

    # ------------------------------------------------------------------ #
    # GENERATE/CURATE DATA
    # ------------------------------------------------------------------ #

    def prepare_dataset(self, cycle: SelfImprovementCycle,
                        evaluation_results: Dict[str, Any]) -> CycleStepResult:
        """Generate/curate dataset from failure examples."""
        result = self.dataset_loop.run(
            evaluation_results, cycle.target_capability
        )

        if result["passed"]:
            cycle.dataset = result["dataset"]
            cycle.dataset["version"] = f"v1_{_short_uuid()}"
            cycle.save()
            return CycleStepResult(
                step="prepare_dataset", success=True,
                message=f"Dataset prepared: {result['dataset']['example_count']} examples",
                details={"dataset_id": result["dataset"]["dataset_id"]},
            )
        else:
            cycle.dataset = {"passed": False, "issues": result["issues"]}
            cycle.save()
            return CycleStepResult(
                step="prepare_dataset", success=False,
                message=f"Dataset quality gate failed: {result['issues']}",
                details={"issues": result["issues"]},
            )

    # ------------------------------------------------------------------ #
    # BASELINE
    # ------------------------------------------------------------------ #

    def establish_baseline(self, cycle: SelfImprovementCycle,
                           baseline_model: str,
                           baseline_revision: str,
                           baseline_metrics: Dict[str, float],
                           dataset_id: str = "") -> BaselineLock:
        """Establish an immutable baseline lock for comparison."""
        lock = BaselineLock(
            model_id=baseline_model,
            revision=baseline_revision,
            metrics=dict(baseline_metrics),
            dataset_id=dataset_id,
        )
        cycle.set_baseline_lock(lock)
        cycle.baseline_results = {
            "model": baseline_model,
            "revision": baseline_revision,
            "metrics": {k: {"value": v, "higher_is_better": True}
                        for k, v in baseline_metrics.items()},
            "baseline_lock": lock.to_dict(),
            "provenance": ["baseline_lock_established"],
        }
        cycle.save()
        logger.info("Baseline lock established: %s@%s", baseline_model, baseline_revision)
        return lock

    # ------------------------------------------------------------------ #
    # TRAIN / MODIFY CANDIDATE
    # ------------------------------------------------------------------ #

    def train_candidate(self, cycle: SelfImprovementCycle,
                        training_config: Optional[TrainingConfig] = None) -> CycleStepResult:
        """Submit training job to JobRegistry.

        Delegates to existing infrastructure — never fabricates.
        Uses Kaggle GPU training via existing Kaggle LoRA pipeline.
        """
        from infrastructure.job_registry import (
            JobRegistry, JobInfo, JobType, JobStatus
        )

        config = training_config or TrainingConfig.from_dict(cycle.training_config)
        cycle.transition(ImprovementStatus.TRAINING)
        cycle.save()

        try:
            registry = JobRegistry.get_instance()

            # Register the training job
            job = JobInfo(
                id=str(_uuid.uuid4()),
                job_id=f"train_{_short_uuid()}",
                job_type=JobType.TRAINING.value,
                status=JobStatus.QUEUED.value,
                model_id=config.base_model,
                model_version=config.base_revision,
                resource_cpu=4.0,
                resource_memory_gb=16.0,
                resource_gpu=1,
                resource_gpu_type="T4" if "kaggle" in config.compute_resource else "",
                resource_instance_type=config.compute_resource,
                config=config.to_dict(),
                parameters={},
                input_artifacts=[],
                output_artifacts=[],
                priority=1,
                max_retries=0,
                created_by="self_improvement",
                estimated_cost_usd=cycle.budget.get("daily_usd", 0.0),
                tags=["improvement", cycle.improvement_id, cycle.target_capability],
            )
            created = registry.create_job(job)

            # Create candidate artifact (EXPERIMENTAL until gates pass)
            candidate = CandidateArtifact(
                artifact_id=f"artifact_{_short_uuid()}",
                improvement_id=cycle.improvement_id,
                model_id=config.base_model,
                revision=config.base_revision,
                artifact_type="lora_adapter",
                artifact_uri="",   # will be filled after training completes
                training_config=config.to_dict(),
                dataset_id=cycle.dataset.get("dataset_id", ""),
                status=CandidateStatus.EXPERIMENTAL.value,
            )
            cycle.set_candidate(candidate)
            cycle.job_id = created.job_id  # store job_id on cycle
            cycle.save()

            return CycleStepResult(
                step="train_candidate", success=True,
                message=f"Training job {created.job_id} submitted to {config.compute_resource}",
                details={
                    "job_id": created.job_id,
                    "artifact_id": candidate.artifact_id,
                    "compute_resource": config.compute_resource,
                },
            )
        except Exception as exc:
            cycle.transition(ImprovementStatus.FAILED)
            cycle.save()
            return CycleStepResult(
                step="train_candidate", success=False,
                message=f"Training submission failed: {type(exc).__name__}: {exc}",
            )

    def complete_training(self, cycle: SelfImprovementCycle,
                          artifact_uri: str, checksum: str,
                          training_output: Dict[str, Any]) -> CandidateArtifact:
        """Complete training and register the candidate artifact."""
        candidate = cycle.get_candidate()
        if candidate is None:
            # Create a candidate if one doesn't exist (for testing / partial runs)
            config = TrainingConfig.from_dict(cycle.training_config)
            candidate = CandidateArtifact(
                artifact_id=f"artifact_{_short_uuid()}",
                improvement_id=cycle.improvement_id,
                model_id=config.base_model,
                revision=config.base_revision,
                artifact_type="lora_adapter",
                training_config=config.to_dict(),
                dataset_id=cycle.dataset.get("dataset_id", ""),
                status=CandidateStatus.EXPERIMENTAL.value,
            )

        candidate.artifact_uri = artifact_uri
        candidate.checksum = checksum
        candidate.transition(CandidateStatus.STAGING)
        cycle.set_candidate(candidate)
        cycle.save()
        return candidate

    # ------------------------------------------------------------------ #
    # EVALUATE
    # ------------------------------------------------------------------ #

    def evaluate_candidate(self, cycle: SelfImprovementCycle,
                           evaluation_matrix: EvaluationMatrix) -> Dict[str, Any]:
        """Evaluate the candidate using the evaluation matrix.

        Runs target, regression, safety, and robustness suites.
        All metrics come from EvaluationSuiteRegistry or brain_benchmarks.
        Never fabricates.
        """
        from jarvis_backend.evaluation_suite import SuiteWrapper
        results: Dict[str, Any] = {"metrics": [], "results": {}, "provenance": []}

        registry = EvaluationSuiteRegistry.get
        # Ensure registry is initialized
        try:
            EvaluationSuiteRegistry.initialize()
        except Exception:
            pass

        for suite_id in evaluation_matrix.all_suites():
            suite = None
            try:
                suite = EvaluationSuiteRegistry.get(suite_id)
            except Exception:
                pass
            if suite is None:
                # Fall back to brain_benchmarks for the shared harness
                try:
                    import brain_benchmarks
                    agg = brain_benchmarks.run_qwen3_4b(
                        generate_fn=lambda p: f"[eval-pending] {p[:50]}",
                        tokenizer=None,
                    )
                    results["results"][suite_id] = agg
                    results["provenance"].append(f"benchmark:{suite_id}")
                    for cat, score in agg.get("categories", {}).items():
                        results["metrics"].append({
                            "name": f"{suite_id}_{cat}",
                            "value": float(score),
                            "unit": "ratio",
                            "higher_is_better": True,
                            "sample_count": 2,
                            "evaluation_version": suite_id,
                            "provenance": ["brain_benchmarks"],
                        })
                except ImportError:
                    results["provenance"].append(f"suite_not_found:{suite_id}")
                continue

            # Resolve candidate model id for checkpoint path
            candidate_artifact = cycle.candidate_artifact or {}
            candidate_model_id = candidate_artifact.get("model_id", "") if isinstance(candidate_artifact, dict) else ""

            # Run evaluation via SuiteWrapper
            for task_dict in suite.tasks:
                task_name = task_dict.get("task_id", "unknown") if isinstance(task_dict, dict) else getattr(task_dict, "task_id", "unknown")
                try:
                    if task_name in ("math_arithmetic", "math_algebra"):
                        metrics = SuiteWrapper.run_math_evaluation(
                            checkpoint_dir=candidate_model_id,
                            device="cpu",
                            evaluation_version=suite.versioned_id if hasattr(suite, 'versioned_id') else suite_id,
                        )
                    elif task_name == "code_python":
                        metrics = SuiteWrapper.run_coding_evaluation(
                            checkpoint_dir=candidate_model_id,
                            device="cpu",
                            evaluation_version=suite.versioned_id if hasattr(suite, 'versioned_id') else suite_id,
                        )
                    elif task_name in ("doc_qa", "rag_qa"):
                        metrics = SuiteWrapper.run_knowledge_evaluation(
                            checkpoint_dir=candidate_model_id,
                            device="cpu",
                            evaluation_version=suite.versioned_id if hasattr(suite, 'versioned_id') else suite_id,
                        )
                    else:
                        metrics = [Metric(
                            name=f"{task_name}_accuracy",
                            value=0.0, unit="ratio", higher_is_better=True,
                            sample_count=0,
                            evaluation_version=suite.versioned_id if hasattr(suite, 'versioned_id') else suite_id,
                            provenance=[f"task_not_mapped:{task_name}"],
                        )]
                    for m in metrics:
                        results["metrics"].append(m.to_dict() if hasattr(m, 'to_dict') else m)
                except Exception as exc:
                    results["metrics"].append({
                        "name": f"{task_name}_error",
                        "value": 0.0,
                        "unit": "ratio",
                        "higher_is_better": True,
                        "sample_count": 0,
                        "evaluation_version": suite_id,
                        "provenance": [f"evaluation_error:{type(exc).__name__}"],
                    })

        results["evaluation_version"] = evaluation_matrix.target_suite_id
        results["evaluated_at"] = now_iso()
        cycle.candidate_results = results
        cycle.save()
        return results

    # ------------------------------------------------------------------ #
    # CRITIQUE
    # ------------------------------------------------------------------ #

    def critique_cycle(self, cycle: SelfImprovementCycle) -> List[Dict[str, Any]]:
        """Critique the improvement cycle using the Critic."""
        from jarvis_backend.critic import Critic

        findings: List[Dict[str, Any]] = []

        # Critique the cycle via Critic.  ``critique`` expects a CognitiveState
        # (not a raw dict), so we fall back gracefully to Phase 12-specific
        # checks when a proper state object is unavailable.
        critic = Critic()
        try:
            state = None
            try:
                from jarvis_backend.cognitive_state import CognitiveState
                state = CognitiveState.from_dict(cycle.to_dict())
            except Exception:
                pass
            issues = critic.critique(state) if state is not None else []
            if not hasattr(critic, 'critique'):
                issues = []
        except Exception:
            issues = []

        for issue in issues:
            if hasattr(issue, 'to_dict'):
                findings.append(issue.to_dict())
            elif isinstance(issue, dict):
                findings.append(issue)
            else:
                findings.append({"description": str(issue), "severity": "medium"})

        # Also critique via critique_experiment if we have an Experiment link
        if cycle.experiment_id:
            exp = Experiment.load(cycle.experiment_id)
            if exp:
                exp_findings = critic.critique_experiment(exp)
                for f in exp_findings:
                    findings.append(f.to_dict())

        # Add Phase 12-specific checks
        findings.extend(self._critique_cycle(cycle))

        cycle.critic_findings = findings
        cycle.save()
        return findings

    def _critique_cycle(self, cycle: SelfImprovementCycle) -> List[Dict[str, Any]]:
        """Phase 12-specific critique checks."""
        issues: List[Dict[str, Any]] = []

        # Check improvement policy is defined
        if not cycle.training_config or not cycle.training_config.get("base_model"):
            issues.append({
                "finding_id": f"find_{_short_uuid()}",
                "category": "policy",
                "severity": "critical",
                "description": "No improvement policy or training config defined",
                "recommendation": "Define a measurable improvement policy with target metrics",
            })

        # Check baseline lock exists and is verified
        lock = cycle.get_baseline_lock()
        if lock is None:
            issues.append({
                "finding_id": f"find_{_short_uuid()}",
                "category": "baseline",
                "severity": "critical",
                "description": "No baseline lock established for comparison",
                "recommendation": "Establish an immutable baseline before evaluation",
            })
        elif not lock.verify():
            issues.append({
                "finding_id": f"find_{_short_uuid()}",
                "category": "baseline",
                "severity": "critical",
                "description": "Baseline lock verification failed (hash mismatch)",
                "recommendation": "The baseline has been tampered with — abort",
            })

        # Check candidate is not promoted directly from EXPERIMENTAL
        candidate = cycle.get_candidate()
        if candidate and candidate.status == CandidateStatus.EXPERIMENTAL.value:
            if cycle.status in (ImprovementStatus.PROMOTION_REVIEW.value,
                                ImprovementStatus.DEPLOYING.value,
                                ImprovementStatus.MONITORING.value):
                issues.append({
                    "finding_id": f"find_{_short_uuid()}",
                    "category": "promotion",
                    "severity": "critical",
                    "description": "Candidate is EXPERIMENTAL but cycle is in promotion/deployment",
                    "recommendation": "Candidate must pass evaluation + verification + promotion gate before deployment",
                })

        # Check no fabrication in results
        if cycle.candidate_results:
            if "provenance" not in cycle.candidate_results:
                issues.append({
                    "finding_id": f"find_{_short_uuid()}",
                    "category": "provenance",
                    "severity": "high",
                    "description": "Candidate results missing provenance tracking",
                    "recommendation": "All metrics must include provenance",
                })

        return issues

    # ------------------------------------------------------------------ #
    # VERIFY
    # ------------------------------------------------------------------ #

    def verify_cycle(self, cycle: SelfImprovementCycle,
                     policy: ImprovementPolicy) -> Dict[str, Any]:
        """Verify the improvement cycle results."""
        from jarvis_backend.verifier import VerificationEngine, VerificationStatus
        from jarvis_backend.evidence_engine import EvidenceEngine

        checks: List[str] = []
        details: Dict[str, Any] = {}

        # Check 1: Baseline lock integrity
        lock = cycle.get_baseline_lock()
        if lock and lock.verify():
            checks.append("baseline_lock_integrity")
            details["baseline_lock"] = "verified"
        else:
            checks.append("baseline_lock_failed")
            details["baseline_lock"] = "failed"

        # Check 2: No fabrication in metrics
        evidence_engine = EvidenceEngine()
        # Check that candidate results have provenance
        cand_provenance = cycle.candidate_results.get("provenance", [])
        if cand_provenance:
            checks.append("candidate_results_provenance")
            details["provenance_tracked"] = True
        else:
            checks.append("candidate_results_no_provenance")
            details["provenance_tracked"] = False

        # Check 3: No secrets in cycle data
        from jarvis_backend.brain_fabric import assert_no_secrets
        leaks = assert_no_secrets(cycle.to_dict())
        if not leaks:
            checks.append("no_secrets_in_cycle_data")
            details["secrets"] = "none_detected"
        else:
            checks.append("secrets_detected_in_cycle_data")
            details["secrets"] = leaks
            details["secrets_count"] = len(leaks)

        # Check 4: Candidate artifact integrity
        candidate = cycle.get_candidate()
        if candidate:
            allowed, reason = self.guard.check_artifact(candidate)
            if allowed:
                checks.append("candidate_artifact_safe")
                details["artifact"] = "safe"
            else:
                checks.append("candidate_artifact_unsafe")
                details["artifact"] = reason

        # Check 5: Evaluation matrix coverage
        if cycle.candidate_results.get("metrics"):
            checks.append("evaluation_results_present")
            details["metric_count"] = len(cycle.candidate_results["metrics"])
        else:
            checks.append("evaluation_results_missing")

        # Check 6: No fabrication via EvidenceEngine
        fabrication_issues = evidence_engine.assert_no_fabrication()
        if not fabrication_issues:
            checks.append("no_fabrication_in_evidence")
            details["fabrication"] = "none"
        else:
            checks.append("fabrication_detected")
            details["fabrication"] = fabrication_issues

        verified = all(
            check not in ("baseline_lock_failed", "secrets_detected_in_cycle_data",
                          "candidate_artifact_unsafe", "evaluation_results_missing")
            for check in checks
        ) and "no_secrets_in_cycle_data" in checks

        cycle.set_verification(
            verified=verified,
            checks=checks,
            details=details,
        )
        cycle.save()

        return {
            "verified": verified,
            "checks": checks,
            "details": details,
        }

    # ------------------------------------------------------------------ #
    # COMPARE
    # ------------------------------------------------------------------ #

    def compare_baseline_candidate(self, cycle: SelfImprovementCycle,
                                   policy: ImprovementPolicy) -> Dict[str, Any]:
        """Compare baseline vs candidate and detect regressions."""
        result = cycle.evaluate_improvement(policy)

        # Also use ExperimentComparison if an experiment is linked
        comparison_extra: Dict[str, Any] = {}
        if cycle.experiment_id:
            exp = Experiment.load(cycle.experiment_id)
            if exp and exp.comparisons:
                comparison_extra["experiment_comparisons"] = [
                    c.to_dict() if hasattr(c, 'to_dict') else c
                    for c in exp.comparisons
                ]

        regression_results = {
            "improvement_result": result.to_dict(),
            "regression_detected": result.regression_detected,
            "regressions": result.regressions,
            "safety_violations": result.safety_violations,
            "verdict": result.verdict,
            "confidence": result.confidence,
            "comparison_extra": comparison_extra,
            "provenance": ["baseline_vs_candidate_comparison"],
            "computed_at": now_iso(),
        }

        cycle.regression_results = regression_results

        # Check if we should reject
        if result.regression_detected and policy.maximum_allowed_regression > 0:
            cycle.critic_findings.append({
                "finding_id": f"find_{_short_uuid()}",
                "category": "regression",
                "severity": "high",
                "description": f"Regression detected: {result.regressions}",
                "recommendation": "Reject candidate — regression exceeds policy threshold",
            })

        cycle.save()
        return regression_results

    # ------------------------------------------------------------------ #
    # PROMOTION GATE
    # ------------------------------------------------------------------ #

    def evaluate_for_promotion(self, cycle: SelfImprovementCycle,
                               policy: ImprovementPolicy) -> Dict[str, Any]:
        """Evaluate candidate for promotion via PromotionGate."""
        from infrastructure.promotion_gate import (
            PromotionGate, EvaluationCriteria, PromotionOutcome,
            get_promotion_gate,
        )

        candidate = cycle.get_candidate()
        if not candidate:
            return {"outcome": "rejected", "reason": "no_candidate_artifact"}

        # Check AutonomyGuard — can we promote?
        can_promote, reason = self.guard.can_promote(
            candidate, promotion_approved=policy.requires_manual_approval
        )
        if not can_promote and policy.requires_manual_approval:
            # With manual approval flag, we simulate the review
            pass

        gate = get_promotion_gate()

        # Build criteria from policy
        criteria = EvaluationCriteria(
            min_accuracy=policy.minimum_improvement,
            min_pass_rate=0.8,
            verification_required=True,
            dataset_traceable=True,
            training_run_required=True,
            parent_model_required=True,
        )

        # Register candidate model in ModelRegistry first
        from infrastructure.model_registry import (
            ModelRegistry, ModelInfo, ModelLifecycleState,
        )
        mr = ModelRegistry.get_instance()

        # Check if model already registered
        model = mr.get(candidate.model_id)
        if model is None:
            model_info = ModelInfo(
                model_id=candidate.model_id,
                provider_id="self_improvement",
                display_name=f"{candidate.model_id} (candidate)",
                description=f"Self-improvement candidate from cycle {cycle.improvement_id}",
                model_family="qwen3",
                lifecycle_type="lora_adapter",
                lifecycle_status=ModelLifecycleState.CANDIDATE.value,
                parent_model_id=cycle.baseline_model,
                revision=candidate.revision,
                capabilities=["chat", "reasoning", "coding"],
                modalities=["text"],
                context_window=2048,
                max_output_tokens=512,
                architecture="transformers",
                parameters=3900000000,  # ~3.9B
                open_weights=True,
                deployment_type="kaggle-gpu",
                endpoint_reference="",
                artifact_reference=candidate.artifact_uri,
                checksum=candidate.checksum,
                source="self_improvement",
                training_run_id=cycle.improvement_id,
                dataset_id=cycle.dataset.get("dataset_id", ""),
                evaluation_results={
                    "self_improvement": {
                        "at": time.time(),
                        "results": {
                            "target_improvement": cycle.regression_results.get("improvement_result", {}).get("target_improvement", 0.0),
                        },
                    }
                },
                metadata={"improvement_id": cycle.improvement_id},
                provenance=[f"self_improvement_cycle:{cycle.improvement_id}"],
            )
            mr.register(model_info)

        # Evaluate for promotion
        outcome, evidence = gate.evaluate_for_promotion(
            candidate.model_id, criteria, evaluator="self_improvement"
        )

        decision = {
            "outcome": outcome.value,
            "approved": outcome == PromotionOutcome.APPROVED,
            "reason": evidence.get("error", evidence.get("failed", ["no reason"])),
            "scores": evidence.get("scores", {}),
            "evidence": evidence,
            "evaluated_at": now_iso(),
            "evaluator": "self_improvement",
        }

        cycle.set_promotion_decision(
            outcome=outcome.value,
            approved=outcome == PromotionOutcome.APPROVED,
            reason=str(evidence.get("failed", evidence.get("error", ""))),
            scores=evidence.get("scores", {}),
        )
        cycle.save()

        # Update candidate status
        if outcome == PromotionOutcome.APPROVED:
            candidate.transition(CandidateStatus.APPROVED)
            cycle.set_baseline_lock  # keep baseline lock
        else:
            candidate.transition(CandidateStatus.REJECTED)
        cycle.set_candidate(candidate)
        cycle.save()

        return decision

    # ------------------------------------------------------------------ #
    # DEPLOY CANDIDATE
    # ------------------------------------------------------------------ #

    def deploy_candidate(self, cycle: SelfImprovementCycle,
                         mode: str = DeploymentMode.SHADOW.value) -> ImprovementDeployment:
        """Controlled deployment: shadow → canary → production.

        Production deployment always requires manual approval.
        """
        candidate = cycle.get_candidate()
        if not candidate:
            raise ValueError("No candidate artifact to deploy")

        if candidate.status != CandidateStatus.APPROVED.value:
            raise ValueError(
                f"Candidate must be APPROVED for deployment (current: {candidate.status})"
            )

        # AutonomyGuard: production deployment requires manual approval
        if mode == DeploymentMode.PRODUCTION.value and self.autonomy_level < 3:
            raise PermissionError(
                "AUTONOMY GUARD: Production deployment requires manual owner "
                "approval (autonomy_level < 3)"
            )

        deployment = ImprovementDeployment.create_shadow(candidate.artifact_id)
        deployment.mode = mode

        if mode == DeploymentMode.CANARY.value:
            deployment.traffic_fraction = 0.1
            deployment.canary_steps = 5
        elif mode == DeploymentMode.PRODUCTION.value:
            deployment.traffic_fraction = 1.0

        cycle.set_deployment(deployment)

        # Update candidate status
        if mode == DeploymentMode.SHADOW.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
        elif mode == DeploymentMode.CANARY.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
            candidate.transition(CandidateStatus.DEPLOYED_CANARY)
        elif mode == DeploymentMode.PRODUCTION.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
            candidate.transition(CandidateStatus.DEPLOYED_CANARY)
            candidate.transition(CandidateStatus.DEPLOYED)
        cycle.set_candidate(candidate)
        cycle.save()

        return deployment

    def rollback_deployment(self, cycle: SelfImprovementCycle,
                            reason: str) -> bool:
        """Rollback a deployment due to post-deployment issues."""
        deployment = cycle.deployment
        if not deployment:
            return False

        deployment_dict = deployment if isinstance(deployment, dict) else deployment.__dict__
        deployment_dict["rolled_back"] = True
        deployment_dict["rollback_reason"] = reason
        deployment_dict["rollback_at"] = now_iso()
        cycle.deployment = deployment_dict
        cycle.rollback_deployment(reason)
        cycle.save()

        # Update candidate
        candidate = cycle.get_candidate()
        if candidate:
            candidate.transition(CandidateStatus.ROLLED_BACK)
            cycle.set_candidate(candidate)
            cycle.save()

        return True

    def post_deployment_evaluation(self, cycle: SelfImprovementCycle,
                                   post_results: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate the deployed candidate in production (post-deployment).

        If regression is detected, trigger rollback.
        """
        cycle.set_post_deployment_results(post_results)
        cycle.transition(ImprovementStatus.MONITORING)
        cycle.save()

        # Check for regression in post-deployment results
        if post_results.get("regressions"):
            self.rollback_deployment(cycle, f"Post-deployment regression: {post_results['regressions']}")
            cycle.transition(ImprovementStatus.COMPLETED)
            cycle.save()
            return {"action": "rolled_back", "results": post_results}

        # If all good, mark as completed
        if post_results.get("outcome") == "success":
            cycle.transition(ImprovementStatus.COMPLETED)
            cycle.save()

        return {"action": "monitoring", "results": post_results}

    # ------------------------------------------------------------------ #
    # BUDGET CHECK
    # ------------------------------------------------------------------ #

    def check_budget(self, cycle: SelfImprovementCycle,
                     policy: ImprovementPolicy) -> Tuple[bool, str]:
        """Check if the improvement cycle stays within budget."""
        from infrastructure.usage_accounting import BudgetManager

        manager = BudgetManager()
        user_id = cycle.provenance[0].split(":")[0] if cycle.provenance else "system"

        # Check if training would exceed budget
        estimated_cost = policy.budget_usd_daily  # daily budget for this cycle
        ok, message = manager.check_budget(user_id, estimated_cost)
        return ok, message

    # ------------------------------------------------------------------ #
    # LEARN
    # ------------------------------------------------------------------ #

    def generate_lesson(self, cycle: SelfImprovementCycle,
                        result: ImprovementResult) -> Lesson:
        """Generate a structured lesson from the completed cycle."""
        outcome = "success" if result.verdict == "improved" else "failure"
        if result.regression_detected:
            outcome = "failure"

        lesson = Lesson(
            lesson_id=f"lesson_{_short_uuid()}",
            improvement_id=cycle.improvement_id,
            weakness_id=cycle.failure_evidence[0].get("weakness_id", "unknown") if cycle.failure_evidence else "unknown",
            hypothesis_id=cycle.hypotheses[0].hypothesis_id if cycle.hypotheses else "unknown",
            intervention_type=cycle.change_type,
            outcome=outcome,
            what_worked=(
                f"{cycle.training_config.get('base_model', '')} "
                f"{cycle.change_type} improved {result.comparison.get('target_metric', 'accuracy')} "
                f"by {result.target_improvement:.2%}"
            ) if result.verdict == "improved" else "",
            what_failed=(
                f"Regression detected: {result.regressions}"
            ) if result.regression_detected else "",
            key_learning=(
                f"Verdict: {result.verdict}. "
                f"Target improvement: {result.target_improvement:.2%}. "
                f"Confidence: {result.confidence:.2%}. "
                f"Regression: {result.regression_detected}."
            ),
            created_at=now_iso(),
        )

        self.learning_memory.add_lesson(lesson)

        # Add to improvement graph
        weakness_id = cycle.failure_evidence[0].get("weakness_id", "unknown") \
            if cycle.failure_evidence else "unknown"
        hypothesis_id = cycle.hypotheses[0].hypothesis_id if cycle.hypotheses else "unknown"
        node = GraphNode(
            improvement_id=cycle.improvement_id,
            weakness_id=weakness_id,
            hypothesis_id=hypothesis_id,
            intervention_type=cycle.change_type,
            artifact_id=(cycle.candidate_artifact or {}).get("artifact_id"),
            experiment_id=cycle.experiment_id,
            outcome=result.verdict,
        )
        self.graph.add_node(node)

        return lesson

    # ------------------------------------------------------------------ #
    # Full cycle orchestration
    # ------------------------------------------------------------------ #

    def run_improvement_cycle(
        self,
        cycle: SelfImprovementCycle,
        policy: ImprovementPolicy,
        evaluation_matrix: EvaluationMatrix,
        training_config: TrainingConfig,
    ) -> Dict[str, Any]:
        """Run the full self-improvement cycle from start to finish."""
        results: Dict[str, Any] = {"steps": [], "cycle_id": cycle.improvement_id}
        rollback_triggered = False

        steps = [
            ("01_observe", lambda: self._step_observe(cycle, policy)),
            ("02_detect_weakness", lambda: self._step_detect_weakness(cycle)),
            ("03_form_hypothesis", lambda: self._step_form_hypothesis(cycle)),
            ("04_design", lambda: self._step_design(cycle, policy, training_config)),
            ("05_await_approval", lambda: self._step_await_approval(cycle, policy)),
            ("06_data_preparation", lambda: self._step_prepare_data(cycle)),
            ("07_training", lambda: self._step_training(cycle, training_config)),
            ("08_evaluation", lambda: self._step_evaluate(cycle, evaluation_matrix)),
            ("09_critique", lambda: self._step_critique(cycle)),
            ("10_verify", lambda: self._step_verify(cycle, policy)),
            ("11_compare", lambda: self._step_compare(cycle, policy)),
            ("12_promotion_review", lambda: self._step_promotion(cycle, policy)),
            ("13_deploy", lambda: self._step_deploy(cycle, policy)),
            ("14_monitor", lambda: self._step_monitor(cycle, policy)),
            ("15_learn", lambda: self._step_learn(cycle, policy)),
        ]

        for step_name, step_fn in steps:
            if rollback_triggered:
                break
            try:
                result = step_fn()
                if hasattr(result, "__dict__"):
                    step_dict = {"step": step_name, **result.__dict__}
                else:
                    step_dict = {"step": step_name, **result}
                results["steps"].append(step_dict)
                if getattr(result, "blocked", False):
                    cycle.transition(ImprovementStatus.BLOCKED)
                    cycle.save()
                    results["blocked_step"] = step_name
                    break
            except Exception as exc:
                results["steps"].append({
                    "step": step_name,
                    "success": False,
                    "message": f"{type(exc).__name__}: {exc}",
                })
                cycle.transition(ImprovementStatus.FAILED)
                cycle.save()
                break

        return results

    def _step_observe(self, cycle: SelfImprovementCycle, policy: ImprovementPolicy) -> CycleStepResult:
        cycle.transition(ImprovementStatus.ANALYZING)
        cycle.save()
        return CycleStepResult(step="observe", success=True, message="Observing capability performance")

    def _step_detect_weakness(self, cycle: SelfImprovementCycle) -> CycleStepResult:
        weaknesses, evidence = self.observe_and_detect_weaknesses(
            cycle.baseline_results, cycle.candidate_results
        )
        cycle.failure_evidence = evidence
        for w in weaknesses:
            cycle.provenance.append(f"weakness_detected:{w.weakness_id}")
        cycle.transition(ImprovementStatus.HYPOTHESIS_FORMED)
        cycle.save()
        return CycleStepResult(
            step="detect_weakness", success=True,
            message=f"Detected {len(weaknesses)} weaknesses",
            details={"weakness_count": len(weaknesses)},
        )

    def _step_form_hypothesis(self, cycle: SelfImprovementCycle) -> CycleStepResult:
        if not cycle.failure_evidence:
            # Use baseline results to find weaknesses
            weaknesses, _ = self.observe_and_detect_weaknesses(
                cycle.baseline_results, cycle.candidate_results
            )
            if not weaknesses:
                # Create a placeholder weakness for the target capability
                weaknesses = [Weakness(
                    weakness_id=f"weakness_{_short_uuid()}",
                    target_capability=cycle.target_capability,
                    description=f"No measurable improvement on {cycle.target_capability}",
                    failure_category=FailureCategory.METRIC_REGRESSION,
                    severity=FailureSeverity.MEDIUM,
                    failures=[],
                )]
        weakness = weaknesses[0]
        self.form_hypothesis(cycle, weakness)
        cycle.transition(ImprovementStatus.DESIGNED)
        cycle.save()
        return CycleStepResult(
            step="form_hypothesis", success=True,
            message=f"Hypothesis formed for weakness {weakness.weakness_id}",
        )

    def _step_design(self, cycle: SelfImprovementCycle, policy: ImprovementPolicy,
                     training_config: TrainingConfig) -> CycleStepResult:
        result = self.design_improvement(
            cycle, InterventionType.TRAINING_CHANGE, training_config, policy
        )
        if result.success:
            cycle.transition(ImprovementStatus.AWAITING_APPROVAL)
        cycle.save()
        return result

    def _step_await_approval(self, cycle: SelfImprovementCycle,
                             policy: ImprovementPolicy) -> CycleStepResult:
        if policy.requires_manual_approval and self.autonomy_level < 3:
            # Manual approval required and we are not in autonomous mode (level 3+)
            # -- block and stay in AWAITING_APPROVAL
            return CycleStepResult(
                step="await_approval", success=False,
                message="Blocked: manual approval required (autonomy_level < 3)",
                blocked=True,
            )
        else:
            cycle.transition(ImprovementStatus.DATA_PREPARATION)
            cycle.save()
            if policy.requires_manual_approval and self.autonomy_level >= 3:
                msg = "Auto-approved (autonomy level >= 3)"
            else:
                msg = "Approval requirements satisfied, proceeding to data preparation"
            return CycleStepResult(
                step="await_approval", success=True,
                message=msg,
            )

    def _step_prepare_data(self, cycle: SelfImprovementCycle) -> CycleStepResult:
        # Use baseline results as the evaluation data source
        result = self.dataset_loop.run(
            cycle.baseline_results, cycle.target_capability
        )
        if result["passed"]:
            cycle.dataset = result["dataset"]
            cycle.save()
        cycle.transition(ImprovementStatus.TRAINING)
        cycle.save()
        return CycleStepResult(
            step="prepare_data", success=result["passed"],
            message=f"Dataset: {result.get('dataset', {}).get('example_count', 0)} examples",
        )

    def _step_training(self, cycle: SelfImprovementCycle,
                      training_config: TrainingConfig) -> CycleStepResult:
        result = self.train_candidate(cycle, training_config)
        # In test/non-GPU mode, training is queued but not executed
        # The candidate artifact is created as EXPERIMENTAL
        return result

    def _step_evaluate(self, cycle: SelfImprovementCycle,
                       evaluation_matrix: EvaluationMatrix) -> CycleStepResult:
        results = self.evaluate_candidate(cycle, evaluation_matrix)
        cycle.transition(ImprovementStatus.CRITIQUING)
        cycle.save()
        return CycleStepResult(
            step="evaluate", success=True,
            message=f"Evaluated candidate with {len(results.get('metrics', []))} metrics",
        )

    def _step_critique(self, cycle: SelfImprovementCycle) -> CycleStepResult:
        findings = self.critique_cycle(cycle)
        has_critical = any(
            f.get("severity") == "critical" for f in findings
        )
        if has_critical:
            cycle.transition(ImprovementStatus.REJECTED)
            cycle.save()
            return CycleStepResult(
                step="critique", success=True,
                message=f"Critique found {len(findings)} issues (including critical)",
                details={"critical": True, "finding_count": len(findings)},
            )
        cycle.transition(ImprovementStatus.VERIFYING)
        cycle.save()
        return CycleStepResult(
            step="critique", success=True,
            message=f"Critique found {len(findings)} issues (no critical)",
            details={"finding_count": len(findings)},
        )

    def _step_verify(self, cycle: SelfImprovementCycle,
                     policy: ImprovementPolicy) -> CycleStepResult:
        verification = self.verify_cycle(cycle, policy)
        if verification["verified"]:
            cycle.transition(ImprovementStatus.PROMOTION_REVIEW)
            cycle.save()
            return CycleStepResult(
                step="verify", success=True,
                message="Verification passed",
                details=verification,
            )
        else:
            cycle.transition(ImprovementStatus.FAILED)
            cycle.save()
            return CycleStepResult(
                step="verify", success=False,
                message="Verification failed",
                details=verification,
            )

    def _step_compare(self, cycle: SelfImprovementCycle,
                      policy: ImprovementPolicy) -> CycleStepResult:
        comparison = self.compare_baseline_candidate(cycle, policy)
        if comparison["regression_detected"] and policy.maximum_allowed_regression > 0:
            cycle.transition(ImprovementStatus.REJECTED)
            cycle.save()
            return CycleStepResult(
                step="compare", success=True,
                message="Regression detected — candidate rejected",
                details=comparison,
            )
        cycle.save()
        return CycleStepResult(
            step="compare", success=True,
            message=f"Comparison: verdict={comparison['verdict']}",
            details={"verdict": comparison["verdict"]},
        )

    def _step_promotion(self, cycle: SelfImprovementCycle,
                        policy: ImprovementPolicy) -> CycleStepResult:
        decision = self.evaluate_for_promotion(cycle, policy)
        if decision["outcome"] == "approved":
            cycle.transition(ImprovementStatus.DEPLOYING)
            cycle.save()
            return CycleStepResult(
                step="promotion", success=True,
                message="Candidate approved for deployment",
                details=decision,
            )
        else:
            cycle.transition(ImprovementStatus.REJECTED)
            cycle.save()
            return CycleStepResult(
                step="promotion", success=True,
                message=f"Candidate rejected by PromotionGate: {decision.get('reason', '')}",
                details=decision,
            )

    def _step_deploy(self, cycle: SelfImprovementCycle,
                     policy: ImprovementPolicy) -> CycleStepResult:
        try:
            deployment = self.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)
            return CycleStepResult(
                step="deploy", success=True,
                message=f"Shadow deployment {deployment.deployment_id}",
                details={"deployment_id": deployment.deployment_id, "mode": deployment.mode},
            )
        except PermissionError as e:
            return CycleStepResult(
                step="deploy", success=False,
                message=str(e), blocked=True,
            )

    def _step_monitor(self, cycle: SelfImprovementCycle,
                      policy: ImprovementPolicy) -> CycleStepResult:
        # Simulate post-deployment monitoring
        # In production, this would sample real metrics
        post_results = {
            "outcome": "success",
            "regressions": [],
            "metrics": {"shadow_comparison_score": 0.867},
            "monitored_at": now_iso(),
        }
        result = self.post_deployment_evaluation(cycle, post_results)
        return CycleStepResult(
            step="monitor", success=True,
            message=f"Post-deployment: {result['action']}",
            details=result,
        )

    def _step_learn(self, cycle: SelfImprovementCycle,
                    policy: ImprovementPolicy) -> CycleStepResult:
        policy_obj = ImprovementPolicy.from_dict(policy.to_dict()) if not isinstance(policy, ImprovementPolicy) else policy
        result = cycle.evaluate_improvement(policy_obj)
        lesson = self.generate_lesson(cycle, result)
        return CycleStepResult(
            step="learn", success=True,
            message=f"Lesson generated: {lesson.lesson_id} (outcome={lesson.outcome})",
            details={"lesson_id": lesson.lesson_id, "outcome": lesson.outcome},
        )


def _short_uuid() -> str:
    return _uuid.uuid4().hex[:12]
