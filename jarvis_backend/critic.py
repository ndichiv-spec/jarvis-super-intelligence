"""Phase 10 — Critic Role.

The Critic is an **analysis-only** role with no execution authority.  It
inspects the cognitive state, evidence, hypotheses, and budget consumption
to surface inconsistencies, fabrication risks, budget overruns, and logical
flaws.  Its findings are returned to the Cognitive Kernel for action — the
Critic cannot modify state directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import now_iso
from research_engine.models import EvidenceStatus

from .cognitive_state import CriticFinding, CognitiveState
from .mission import _short_uuid

logger = logging.getLogger("jarvis_backend.critic")


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FindingCategory(str, Enum):
    EVIDENCE_QUALITY = "evidence_quality"
    FABRICATION = "fabrication"
    BUDGET = "budget"
    LOGIC = "logic"
    AUTHORIZATION = "authorization"
    VERIFICATION = "verification"
    CONFIDENCE = "confidence"
    EVIDENCE_CONFLICT = "evidence_conflict"
    HYPOTHESIS = "hypothesis"
    RESOURCE = "resource"
    EXPERIMENT = "experiment"


@dataclass
class CriticConfig:
    """Configuration thresholds for the Critic."""

    # Maximum allowed unverified evidence before flagging
    max_unverified_evidence: int = 5

    # Maximum allowed hypotheses without testing
    max_untested_hypotheses: int = 3

    # Confidence calibration threshold (if confidence > this but status
    # is unverified, flag it)
    confidence_calibration_threshold: float = 0.8

    # Evidence conflict threshold (same claims with contradictory verification)
    flag_evidence_conflicts: bool = True

    # Budget overrun threshold (fraction of budget)
    budget_warn_threshold: float = 0.8

    # Maximum cognitive steps
    max_steps: int = 50

    # Minimum sample size for experiment results to be trusted
    min_sample_size: int = 10

    # Maximum allowed relative regression before flagging
    max_relative_regression: float = -0.05

    # Maximum allowed duplicate dataset overlap between baseline and candidate
    max_dataset_overlap_fraction: float = 0.0


class Critic:
    """The Critic role — analysis only, no execution authority.

    The Critic examines the CognitiveState and returns findings.  It never
    modifies state directly; findings are surfaced to the Kernel which
    decides how to act on them.
    """

    def __init__(self, config: Optional[CriticConfig] = None) -> None:
        self.config = config or CriticConfig()

    def critique(self, state: CognitiveState) -> list[CriticFinding]:
        """Analyze the cognitive state and return a list of findings.

        The Critic has NO execution authority — it only reports.  All findings
        are recorded for the Kernel to act upon.
        """
        findings: list[CriticFinding] = []
        findings.extend(self._check_fabrication(state))
        findings.extend(self._check_evidence_quality(state))
        findings.extend(self._check_hypotheses(state))
        findings.extend(self._check_budget(state))
        findings.extend(self._check_confidence_calibration(state))
        findings.extend(self._check_evidence_conflicts(state))
        findings.extend(self._check_verification_gaps(state))
        return findings

    # -- Checks --
    def _check_fabrication(self, state: CognitiveState) -> list[CriticFinding]:
        """Detect potential fabrication: claims without supporting evidence."""
        findings: list[CriticFinding] = []
        bs = self.config

        # Check for known facts claiming confidence without evidence
        for fact in state.known_facts:
            if fact.get("confidence") is not None and fact.get("confidence") > bs.confidence_calibration_threshold:
                if not fact.get("verified", False):
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.WARNING.value,
                        category=FindingCategory.CONFIDENCE.value,
                        description=(
                            f"Known fact claims confidence={fact['confidence']} "
                            f"but is not verified: '{fact.get('statement', '')[:100]}'"
                        ),
                        recommendation="Require a deterministic verification check before trusting this confidence value",
                    ))

        # Check evidence that claims verification without provenance
        for ev in state.evidence:
            if ev.get("verification_status") == "VERIFIED":
                prov = ev.get("provenance", [])
                has_verified_link = any(
                    p.get("action") == "verified" for p in prov
                )
                if not has_verified_link:
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.ERROR.value,
                        category=FindingCategory.FABRICATION.value,
                        description=(
                            f"Evidence {ev.get('evidence_id', '?')} marked VERIFIED "
                            f"but has no verification provenance link — potential fabrication"
                        ),
                        recommendation="Remove VERIFIED status or add verification provenance",
                    ))
        return findings

    def _check_evidence_quality(self, state: CognitiveState) -> list[CriticFinding]:
        """Check for evidence quality issues."""
        findings: list[CriticFinding] = []

        # Count unverified evidence
        unverified = [e for e in state.evidence
                      if e.get("verification_status") == EvidenceStatus.UNVERIFIED.value]
        if len(unverified) > self.config.max_unverified_evidence:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.WARNING.value,
                category=FindingCategory.EVIDENCE_QUALITY.value,
                description=(
                    f"{len(unverified)} items of unverified evidence exceed "
                    f"threshold of {self.config.max_unverified_evidence}"
                ),
                recommendation="Verify or discard unverified evidence before drawing conclusions",
            ))

        # Check for empty evidence content
        empty_evidence = [e for e in state.evidence if not e.get("relevant_content")]
        if empty_evidence:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.WARNING.value,
                category=FindingCategory.EVIDENCE_QUALITY.value,
                description=(
                    f"{len(empty_evidence)} evidence item(s) have empty content"
                ),
                recommendation="Re-evaluate evidence sources that produced empty content",
            ))
        return findings

    def _check_hypotheses(self, state: CognitiveState) -> list[CriticFinding]:
        """Check hypothesis quality."""
        findings: list[CriticFinding] = []

        # Count untested hypotheses
        hyps = state.hypotheses
        untested = [h for h in hyps
                    if h.get("status") in ("PROPOSED",)
                    and not h.get("evidence_ids")]
        if len(untested) > self.config.max_untested_hypotheses:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.INFO.value,
                category=FindingCategory.HYPOTHESIS.value,
                description=(
                    f"{len(untested)} hypotheses have not been tested "
                    f"(threshold: {self.config.max_untested_hypotheses})"
                ),
                recommendation="Prioritize testing high-impact untested hypotheses",
            ))
        return findings

    def _check_budget(self, state: CognitiveState) -> list[CriticFinding]:
        """Check budget consumption."""
        findings: list[CriticFinding] = []
        bs = state.budget_state
        if not bs:
            return findings

        consumed = bs.get("steps_consumed", 0)
        remaining = bs.get("steps_remaining", 0)
        total = consumed + remaining
        if total > 0:
            ratio = consumed / total
            if ratio >= self.config.budget_warn_threshold:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.BUDGET.value,
                    description=(
                        f"Cognitive step budget {ratio:.0%} consumed "
                        f"({consumed}/{total} steps) — approaching limit"
                    ),
                    recommendation="Consider pausing to review progress or request a budget extension",
                ))
        if bs.get("exhausted"):
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.ERROR.value,
                category=FindingCategory.BUDGET.value,
                description="Cognitive step budget exhausted",
                recommendation="Mission must stop — budget hard limit reached",
            ))
        return findings

    def _check_confidence_calibration(self, state: CognitiveState) -> list[CriticFinding]:
        """Check that confidence values are calibrated."""
        findings: list[CriticFinding] = []
        threshold = self.config.confidence_calibration_threshold

        for h in state.hypotheses:
            conf = h.get("confidence")
            status = h.get("status", "PROPOSED")
            if conf is not None and conf >= threshold and status in ("PROPOSED", "TESTING"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.CONFIDENCE.value,
                    description=(
                        f"Hypothesis {h.get('id', '?')} has confidence={conf} "
                        f"but status is {status} — confidence not justified"
                    ),
                    recommendation="Only assign confidence after deterministic verification",
                ))
        return findings

    def _check_evidence_conflicts(self, state: CognitiveState) -> list[CriticFinding]:
        """Check for conflicting evidence."""
        findings: list[CriticFinding] = []
        if not self.config.flag_evidence_conflicts:
            return findings

        evidence = [e for e in state.evidence if e.get("claims")]
        for i, a in enumerate(evidence):
            for b in evidence[i + 1:]:
                if a.get("verification_status") == EvidenceStatus.CONTRADICTED.value or \
                   b.get("verification_status") == EvidenceStatus.CONTRADICTED.value:
                    # Check if claims conflict
                    for claim_a in a.get("claims", []):
                        for claim_b in b.get("claims", []):
                            if self._claims_conflict(claim_a, claim_b):
                                findings.append(CriticFinding(
                                    finding_id=f"find_{_short_uuid()}",
                                    at=now_iso(),
                                    severity=FindingSeverity.ERROR.value,
                                    category=FindingCategory.EVIDENCE_CONFLICT.value,
                                    description=(
                                        f"Conflicting evidence: '{claim_a[:80]}' vs "
                                        f"'{claim_b[:80]}'"
                                    ),
                                    recommendation="Investigate contradiction before proceeding",
                                ))
        return findings

    def _check_verification_gaps(self, state: CognitiveState) -> list[CriticFinding]:
        """Check for claims that lack verification."""
        findings: list[CriticFinding] = []
        for result in state.verification_results:
            if result.get("status") == "UNVERIFIED":
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.INFO.value,
                    category=FindingCategory.VERIFICATION.value,
                    description=(
                        f"Claim '{result.get('claim', '')[:80]}' remains unverified"
                    ),
                    recommendation="Attempt verification through deterministic methods",
                ))
        return findings

    @staticmethod
    def _claims_conflict(a: str, b: str) -> bool:
        """Simple conflict detection — reuse the models._contradicts heuristic."""
        try:
            from research_engine.models import _contradicts
            return _contradicts(a, b)
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Experiment critique (Phase 11)
    # ------------------------------------------------------------------ #
    def critique_experiment(self, experiment: Any) -> list[CriticFinding]:
        """Critique an experiment for scientific rigor and security.

        The Critic has NO execution authority — it only reports findings.
        An experiment is a dict (serialized) or an Experiment object.
        """
        findings: list[CriticFinding] = []
        bs = self.config

        exp = experiment.to_dict() if hasattr(experiment, "to_dict") else experiment

        # Check for missing baseline in improvement experiments
        findings.extend(self._check_experiment_missing_baseline(exp))

        # Check for dataset leakage (candidate trained on eval data)
        findings.extend(self._check_experiment_dataset_leakage(exp))

        # Check for invalid comparison (different suite versions)
        findings.extend(self._check_experiment_invalid_comparison(exp))

        # Check for small sample sizes
        findings.extend(self._check_experiment_small_sample(exp, bs))

        # Check for metric mismatch
        findings.extend(self._check_experiment_metric_mismatch(exp))

        # Check for evaluation contamination
        findings.extend(self._check_experiment_contamination(exp))

        # Check for uncontrolled variables
        findings.extend(self._check_experiment_uncontrolled_variables(exp))

        # Check for missing provenance
        findings.extend(self._check_experiment_missing_provenance(exp))

        # Check for unsupported conclusions
        findings.extend(self._check_experiment_unsupported_conclusion(exp))

        # Check for regression without acknowledgment
        findings.extend(self._check_experiment_regression(exp, bs))

        # Check for resource mismatch
        findings.extend(self._check_experiment_resource_mismatch(exp))

        # Check for incomplete verification
        findings.extend(self._check_experiment_incomplete_verification(exp))

        # Check for self-approval (experiment approving its own promotion)
        findings.extend(self._check_experiment_self_approval(exp))

        # Check for secret leakage in experiment data
        findings.extend(self._check_experiment_secret_leakage(exp))

        return findings

    def _check_experiment_missing_baseline(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for missing baseline in improvement experiments."""
        findings: list[CriticFinding] = []
        baseline = exp.get("baseline")
        hypothesis = exp.get("hypothesis", "")
        objective = exp.get("objective", "")

        # If the experiment is an improvement experiment (hypothesis mentions
        # improvement/comparison), require a baseline
        is_improvement = (
            "improve" in hypothesis.lower() or "improvement" in hypothesis.lower()
            or "better" in hypothesis.lower() or "compar" in objective.lower()
            or "improve" in objective.lower()
        )
        if is_improvement and not baseline:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.ERROR.value,
                category=FindingCategory.EXPERIMENT.value,
                description=(
                    f"Improvement experiment '{exp.get('name', '?')}' has no baseline — "
                    "never claim improvement without a baseline"
                ),
                recommendation="Establish a baseline before evaluating candidate improvements",
            ))
        return findings

    def _check_experiment_dataset_leakage(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for dataset leakage between training and evaluation."""
        findings: list[CriticFinding] = []
        datasets = exp.get("datasets", [])
        eval_datasets = [d for d in datasets if "eval" in str(d).lower()]
        train_datasets = [d for d in datasets if "train" in str(d).lower()]

        # Check if same dataset appears in both train and eval contexts
        for ed in eval_datasets:
            for td in train_datasets:
                if ed == td:
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.ERROR.value,
                        category=FindingCategory.EXPERIMENT.value,
                        description=(
                            f"Dataset leakage: {ed} appears in both training and "
                            "evaluation — candidate may have memorized eval data"
                        ),
                        recommendation="Ensure evaluation datasets are disjoint from training data",
                    ))
        return findings

    def _check_experiment_invalid_comparison(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for invalid comparisons (different evaluation suite versions)."""
        findings: list[CriticFinding] = []
        comparisons = exp.get("comparisons", [])
        versions = set()
        for comp in comparisons:
            if isinstance(comp, dict):
                ev = comp.get("evaluation_version")
                if ev:
                    versions.add(ev)

        if len(versions) > 1:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.ERROR.value,
                category=FindingCategory.EXPERIMENT.value,
                description=(
                    f"Invalid comparison: metrics computed with different evaluation "
                    f"versions: {versions}"
                ),
                recommendation="All comparisons must use the same evaluation version",
            ))

        baseline = exp.get("baseline")
        if baseline:
            baseline_metrics = baseline.get("metrics", []) if isinstance(baseline, dict) else []
            baseline_ev = set()
            for m in baseline_metrics:
                if isinstance(m, dict):
                    ev = m.get("evaluation_version")
                    if ev:
                        baseline_ev.add(ev)

            for cand in exp.get("candidates", []):
                cand_metrics = cand.get("metrics", []) if isinstance(cand, dict) else []
                cand_ev = set()
                for m in cand_metrics:
                    if isinstance(m, dict):
                        ev = m.get("evaluation_version")
                        if ev:
                            cand_ev.add(ev)

                if baseline_ev and cand_ev and baseline_ev != cand_ev:
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.ERROR.value,
                        category=FindingCategory.EXPERIMENT.value,
                        description=(
                            f"Invalid comparison: baseline uses evaluation versions "
                            f"{baseline_ev} but candidate uses {cand_ev}"
                        ),
                        recommendation="Baseline and candidate must be evaluated with the same suite version",
                    ))
        return findings

    def _check_experiment_small_sample(self, exp: dict[str, Any], config: CriticConfig) -> list[CriticFinding]:
        """Check for small sample sizes in experiment metrics."""
        findings: list[CriticFinding] = []
        all_metrics = []
        baseline = exp.get("baseline")
        if baseline and isinstance(baseline, dict):
            all_metrics.extend(baseline.get("metrics", []))
        for cand in exp.get("candidates", []):
            if isinstance(cand, dict):
                all_metrics.extend(cand.get("metrics", []))

        for m in all_metrics:
            if isinstance(m, dict):
                sample_count = m.get("sample_count", 0)
                if 0 < sample_count < config.min_sample_size:
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.WARNING.value,
                        category=FindingCategory.EXPERIMENT.value,
                        description=(
                            f"Small sample size for metric '{m.get('name', '?')}': "
                            f"{sample_count} samples (threshold: {config.min_sample_size})"
                        ),
                        recommendation="Increase sample size or mark results as preliminary",
                    ))
        return findings

    def _check_experiment_metric_mismatch(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for metric mismatch between baseline and candidate."""
        findings: list[CriticFinding] = []
        baseline = exp.get("baseline")
        if not baseline or not isinstance(baseline, dict):
            return findings

        baseline_metric_names = set()
        for m in baseline.get("metrics", []):
            if isinstance(m, dict):
                baseline_metric_names.add(m.get("name", ""))

        for cand in exp.get("candidates", []):
            if not isinstance(cand, dict):
                continue
            cand_metric_names = set()
            for m in cand.get("metrics", []):
                if isinstance(m, dict):
                    cand_metric_names.add(m.get("name", ""))

            if baseline_metric_names and cand_metric_names:
                if baseline_metric_names != cand_metric_names:
                    missing = baseline_metric_names - cand_metric_names
                    extra = cand_metric_names - baseline_metric_names
                    findings.append(CriticFinding(
                        finding_id=f"find_{_short_uuid()}",
                        at=now_iso(),
                        severity=FindingSeverity.WARNING.value,
                        category=FindingCategory.EXPERIMENT.value,
                        description=(
                            f"Metric mismatch: baseline has {sorted(baseline_metric_names)} "
                            f"but candidate has {sorted(cand_metric_names)} "
                            f"(missing: {sorted(missing)}, extra: {sorted(extra)})"
                        ),
                        recommendation="Ensure same evaluation dimensions are measured for baseline and candidate",
                    ))
        return findings

    def _check_experiment_contamination(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for contamination: datasets that overlap between conditions."""
        findings: list[CriticFinding] = []
        datasets = exp.get("datasets", [])
        # Check for identical dataset IDs appearing multiple times
        seen = set()
        for ds in datasets:
            ds_id = str(ds)
            if ds_id in seen:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description=f"Dataset {ds_id} appears multiple times in experiment",
                    recommendation="Verify this is intentional — possible data contamination",
                ))
            seen.add(ds_id)
        return findings

    def _check_experiment_uncontrolled_variables(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for uncontrolled variables in the experiment."""
        findings: list[CriticFinding] = []
        design = exp.get("design", {})
        if isinstance(design, dict):
            ivs = design.get("independent_variables", [])
            controls = design.get("controls", [])
            if ivs and not controls:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description=(
                        f"Experiment has independent variables {ivs} but no controls — "
                        "independent variables cannot be isolated"
                    ),
                    recommendation="Define control variables for each independent variable",
                ))
        elif isinstance(exp.get("variables"), list) and exp.get("variables"):
            if not exp.get("controls"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description=(
                        f"Experiment has variables {exp.get('variables')} but no controls"
                    ),
                    recommendation="Define control variables",
                ))
        return findings

    def _check_experiment_missing_provenance(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for missing provenance in experiment results."""
        findings: list[CriticFinding] = []
        provenance = exp.get("provenance", [])
        if not provenance:
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.ERROR.value,
                category=FindingCategory.EXPERIMENT.value,
                description="Experiment has no provenance records — results cannot be traced",
                recommendation="Add provenance for all models, datasets, and evaluation runs",
            ))

        # Check baseline provenance
        baseline = exp.get("baseline")
        if baseline and isinstance(baseline, dict):
            if not baseline.get("model"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description="Baseline lacks model provenance",
                    recommendation="Record the exact model and revision used for baseline",
                ))
            if not baseline.get("timestamp"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description="Baseline lacks timestamp",
                    recommendation="Record when the baseline was established",
                ))
        return findings

    def _check_experiment_unsupported_conclusion(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for conclusions not supported by evidence."""
        findings: list[CriticFinding] = []
        results = exp.get("results", {})
        status = exp.get("status", "")
        if status == "completed":
            # If completed, check that there are comparisons with actual values
            comparisons = exp.get("comparisons", [])
            if not comparisons:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description=(
                        "Experiment marked COMPLETED but has no comparisons — "
                        "conclusion not supported by evidence"
                    ),
                    recommendation="Only mark COMPLETED when actual comparison data exists",
                ))
            # Check for metrics with zero sample_count (fabricated/synthetic)
            all_metrics = []
            baseline = exp.get("baseline")
            if baseline and isinstance(baseline, dict):
                all_metrics.extend(baseline.get("metrics", []))
            for cand in exp.get("candidates", []):
                if isinstance(cand, dict):
                    all_metrics.extend(cand.get("metrics", []))

            for m in all_metrics:
                if isinstance(m, dict) and m.get("sample_count", 0) == 0:
                    if "value" in m and m["value"] != 0.0:
                        findings.append(CriticFinding(
                            finding_id=f"find_{_short_uuid()}",
                            at=now_iso(),
                            severity=FindingSeverity.ERROR.value,
                            category=FindingCategory.FABRICATION.value,
                            description=(
                                f"Metric '{m.get('name', '?')}' has non-zero value "
                                f"({m.get('value')}) but sample_count=0 — fabricated"
                            ),
                            recommendation="Metrics must have non-zero sample count for non-zero values",
                        ))
        return findings

    def _check_experiment_regression(self, exp: dict[str, Any], config: CriticConfig) -> list[CriticFinding]:
        """Check for regression beyond tolerance."""
        findings: list[CriticFinding] = []
        comparisons = exp.get("comparisons", [])
        for comp in comparisons:
            if not isinstance(comp, dict):
                continue
            rel_diff = comp.get("relative_difference", 0.0)
            metric_name = comp.get("metric_name", "?")
            higher_better = True  # We'd need to check the metric's higher_is_better
            # If metric has higher_is_better and relative_difference is very negative,
            # that's a regression
            if isinstance(rel_diff, (int, float)) and rel_diff < config.max_relative_regression:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.ERROR.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description=(
                        f"Regression detected on metric '{metric_name}': "
                        f"relative_difference={rel_diff:.4f} "
                        f"(threshold: {config.max_relative_regression})"
                    ),
                    recommendation="Acknowledge regression or investigate root cause",
                ))
        return findings

    def _check_experiment_resource_mismatch(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for resource mismatch between requirements and allocation."""
        findings: list[CriticFinding] = []
        reqs = exp.get("compute_requirements", {})
        if isinstance(reqs, dict):
            if reqs.get("gpu_required") and not reqs.get("selected_resource"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.ERROR.value,
                    category=FindingCategory.EXPERIMENT.value,
                    description="Experiment requires GPU but no GPU resource was selected",
                    recommendation="Select a GPU-capable resource or downgrade requirement",
                ))

            # Check if selected resource matches task type
            task_type = reqs.get("task_type", "")
            selected = reqs.get("selected_resource", "")
            if task_type == "training" and "kaggle" not in selected and "nvidia" not in selected and "local" in selected:
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.WARNING.value,
                    category=FindingCategory.RESOURCE.value,
                    description="Training task assigned to local control node without GPU",
                    recommendation="Consider Kaggle or NVIDIA resources for training workloads",
                ))
        return findings

    def _check_experiment_incomplete_verification(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for incomplete verification."""
        findings: list[CriticFinding] = []
        status = exp.get("status", "")
        results = exp.get("results", {})
        if status in ("completed", "verifying"):
            if not results.get("verification_passed"):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.ERROR.value,
                    category=FindingCategory.VERIFICATION.value,
                    description="Experiment marked for completion but verification was not passed",
                    recommendation="Run full verification before marking complete",
                ))
        return findings

    def _check_experiment_self_approval(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for self-approval — experiment bypassing PromotionGate."""
        findings: list[CriticFinding] = []
        provenance = exp.get("provenance", [])
        for prov in provenance:
            if isinstance(prov, str) and ("self_approved" in prov or "self_promote" in prov
                                         or "bypass_promotion" in prov):
                findings.append(CriticFinding(
                    finding_id=f"find_{_short_uuid()}",
                    at=now_iso(),
                    severity=FindingSeverity.ERROR.value,
                    category=FindingCategory.AUTHORIZATION.value,
                    description=f"Experiment attempted self-approval: {prov}",
                    recommendation="All model promotions must go through PromotionGate — never self-approve",
                ))

        # Check if a blocked experiment tries to transition to COMPLETED
        if exp.get("status") == "completed" and exp.get("blocked_reason"):
            findings.append(CriticFinding(
                finding_id=f"find_{_short_uuid()}",
                at=now_iso(),
                severity=FindingSeverity.ERROR.value,
                category=FindingCategory.AUTHORIZATION.value,
                description="Blocked experiment attempted COMPLETED status",
                recommendation="Blocked experiments cannot complete — resolve block reason first",
            ))
        return findings

    def _check_experiment_secret_leakage(self, exp: dict[str, Any]) -> list[CriticFinding]:
        """Check for secret leakage in experiment data."""
        findings: list[CriticFinding] = []
        try:
            from jarvis_backend.brain_fabric import assert_no_secrets, _SECRET_KEYS
        except ImportError:
            return findings

        def _scan(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = k.lower()
                    if any(s in kl for s in _SECRET_KEYS):
                        findings.append(CriticFinding(
                            finding_id=f"find_{_short_uuid()}",
                            at=now_iso(),
                            severity=FindingSeverity.ERROR.value,
                            category=FindingCategory.FABRICATION.value,
                            description=f"Secret-shaped key '{k}' found in experiment data at {path}",
                            recommendation="Scrub all secret-shaped keys from experiment data",
                        ))
                    _scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _scan(item, f"{path}[{i}]")
            elif isinstance(obj, str):
                for s in _SECRET_KEYS:
                    if s in obj.lower():
                        findings.append(CriticFinding(
                            finding_id=f"find_{_short_uuid()}",
                            at=now_iso(),
                            severity=FindingSeverity.ERROR.value,
                            category=FindingCategory.FABRICATION.value,
                            description=f"Secret-shaped string found in experiment data at {path}",
                            recommendation="Remove secret values from experiment data",
                        ))
                        break

        _scan(exp)
        return findings


__all__ = [
    "FindingSeverity",
    "FindingCategory",
    "CriticConfig",
    "Critic",
]
