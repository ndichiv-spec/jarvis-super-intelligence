"""Learning-rate advisor + structured recommendation generation.

Analyzes the *historical* anomaly set and metric trends (never a single step)
and produces ``Recommendation`` objects that carry the fields the task
requires: action, reason, confidence, expected_effect, risk, and an explicit
authorization gate.

Advisory-only contract
----------------------
No recommendation ever mutates the optimizer/scheduler/checkpoints itself.
Any action that *could* lead to such a mutation carries
``authorization_required=True`` and is only "applied" after explicit human
approval via ``/api/training/advisor/approve``.
"""
from __future__ import annotations

import math
from typing import List

from .config import AdvisorConfig
from .schemas import (AnomalySeverity, Provenance, Recommendation,
                      RecommendationAction, RiskLevel, TrainingMetricsSnapshot)

_CONF_BY_SEVERITY = {
    AnomalySeverity.CRITICAL: 0.92,
    AnomalySeverity.HIGH: 0.82,
    AnomalySeverity.MEDIUM: 0.70,
    AnomalySeverity.LOW: 0.55,
    AnomalySeverity.INFO: 0.30,
}

_MUTATING = {
    RecommendationAction.INCREASE_LR, RecommendationAction.DECREASE_LR,
    RecommendationAction.USE_WARMUP, RecommendationAction.EXTEND_WARMUP,
    RecommendationAction.CHANGE_SCHEDULER, RecommendationAction.STOP_TRAINING,
    RecommendationAction.REDUCE_BATCH_SIZE, RecommendationAction.INCREASE_BATCH_SIZE,
    RecommendationAction.TIGHTEN_REGULARIZATION, RecommendationAction.RELAX_REGULARIZATION,
}


def _gen_id() -> str:
    import uuid
    return uuid.uuid4().hex[:10]


def _conf(severity: AnomalySeverity, n_ev: int) -> float:
    base = _CONF_BY_SEVERITY.get(severity, 0.5)
    # more supporting evidence -> higher confidence, capped
    return round(min(0.99, base + 0.05 * min(n_ev, 5)), 2)


def recommend_for(anomaly, snapshots: List[TrainingMetricsSnapshot]) -> List[Recommendation]:
    """Map a single anomaly to one or more concrete recommendations."""
    hint = anomaly.recommendation_hint or RecommendationAction.CONTINUE_TRAINING
    recs: List[Recommendation] = []
    sev = anomaly.severity
    conf = _conf(sev, len(anomaly.evidence) + len(anomaly.metrics_evidence))

    action_map = {
        "stop_training": (RecommendationAction.STOP_TRAINING, RiskLevel.HIGH,
                          "Immediately halt training.",
                          "Prevents wasted compute and further divergence; capture the last good checkpoint."),
        "decrease_lr": (RecommendationAction.DECREASE_LR, RiskLevel.MEDIUM,
                        "Reduce the learning rate (e.g. x0.1-0.5).",
                        "Stabilises the descent and removes the divergence source; may slow convergence."),
        "increase_lr": (RecommendationAction.INCREASE_LR, RiskLevel.MEDIUM,
                        "Increase the learning rate (e.g. x2).",
                        "Accelerates progress out of a flat region; risks re-introducing instability."),
        "change_scheduler": (RecommendationAction.CHANGE_SCHEDULER, RiskLevel.MEDIUM,
                             "Switch to a decaying/warmup scheduler.",
                             "Aligns LR to the loss landscape for smoother convergence."),
        "use_warmup": (RecommendationAction.USE_WARMUP, RiskLevel.LOW,
                       "Introduce a linear warmup phase.", "Soft-starts optimization, avoiding early spikes."),
        "extend_warmup": (RecommendationAction.EXTEND_WARMUP, RiskLevel.LOW,
                          "Lengthen the current warmup phase.", "Gives optimizer momentum time to stabilise."),
        "tighten_regularization": (RecommendationAction.TIGHTEN_REGULARIZATION, RiskLevel.MEDIUM,
                                   "Increase weight decay / dropout.", "Reduces overfitting gap; may underfit if excessive."),
        "relax_regularization": (RecommendationAction.RELAX_REGULARIZATION, RiskLevel.LOW,
                                 "Reduce weight decay / dropout.", "Lets the model fit better if underfitting; risks overfitting."),
        "continue_training": (RecommendationAction.CONTINUE_TRAINING, RiskLevel.LOW,
                              "Keep training as-planned with current config.",
                              "Allows the existing schedule to complete its intended trajectory."),
        "investigate_instability": (RecommendationAction.INVESTIGATE_INSTABILITY, RiskLevel.LOW,
                                    "Investigate but do not change hyperparameters yet.",
                                    "Gathers diagnostics (gradient stats, LR, data) before acting."),
        "fix_dataset": (RecommendationAction.FIX_DATASET, RiskLevel.MEDIUM,
                        "Audit the data pipeline / class balance.",
                        "Removes spurious signal that corrupts the gradient signal."),
        "checkpoint": (RecommendationAction.CHECKPOINT, RiskLevel.LOW,
                       "Save a checkpoint now and verify the trajectory.",
                       "Preserves a known-good state before experimenting."),
        "inspect_gradients": (RecommendationAction.INSPECT_GRADIENTS, RiskLevel.LOW,
                              "Inspect gradient statistics in detail.",
                              "Diagnoses explosion/vanishing at the layer level."),
        "collect_metrics": (RecommendationAction.COLLECT_METRICS, RiskLevel.LOW,
                            "Instrument the training loop to emit metrics.",
                            "Enables statistical advising (currently UNKNOWN)."),
    }

    spec = action_map.get(hint)
    if spec is None:
        spec = action_map[RecommendationAction.CONTINUE_TRAINING]
    action, risk, effect, expected = spec
    recs.append(Recommendation(
        id=_gen_id(), action=action.value,
        reason=f"{anomaly.title}: {anomaly.description}",
        confidence=conf, expected_effect=expected, risk=risk,
        authorization_required=action in _MUTATING,
        sub_action=None, target_metric=anomaly.detector,
        parameters={"detector": anomaly.detector,
                    "severity": anomaly.severity.value,
                    "evidence": anomaly.evidence[:3]},
    ))
    # Companion: if instability, also suggest an LR guard
    if hint in ("investigate_instability", "decrease_lr") and sev in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL):
        recs.append(Recommendation(
            id=_gen_id(), action=RecommendationAction.USE_WARMUP.value,
            reason="Co-occurring instability alongside the above issue; a warmup reduces early shock.",
            confidence=min(0.9, conf), expected_effect="Smoother early optimisation dynamics.",
            risk=RiskLevel.LOW, authorization_required=True,
            target_metric="learning_rate"))
    return recs


def synthesize(snapshots: List[TrainingMetricsSnapshot], anomalies, config: AdvisorConfig):
    """Produce the final recommendation list from anomalies + trends."""
    recs: List[Recommendation] = []
    seen = set()
    for a in anomalies:
        for r in recommend_for(a, snapshots):
            key = r.action
            if key in seen:
                continue
            seen.add(key)
            recs.append(r)

    # No anomalies -> decide keep vs continue vs collect-metrics
    if not recs:
        obs = sum(len(s.observed_keys()) for s in snapshots)
        if obs == 0:
            recs.append(Recommendation(
                id=_gen_id(), action=RecommendationAction.COLLECT_METRICS.value,
                reason="No live training metrics are being produced. The model state is a static stub.",
                confidence=0.3, expected_effect="Enables statistical advising once a loop POSTs metrics.",
                risk=RiskLevel.LOW, authorization_required=False, target_metric="all"))
        elif len(snapshots) >= config.analysis_threshold:
            recs.append(Recommendation(
                id=_gen_id(), action=RecommendationAction.KEEP_LR.value,
                reason="No anomalies detected across the historical window; loss/stability look healthy.",
                confidence=0.8, expected_effect="Continue on the current schedule; no intervention required.",
                risk=RiskLevel.LOW, authorization_required=False, target_metric="loss"))
            if _still_converging(snapshots, config):
                recs.append(Recommendation(
                    id=_gen_id(), action=RecommendationAction.CONTINUE_TRAINING.value,
                    reason="Trajectory is healthy but loss is still descending; training budget remains.",
                    confidence=0.7, expected_effect="Allows convergence to complete.",
                    risk=RiskLevel.LOW, authorization_required=False, target_metric="loss"))

    return recs


def _still_converging(snapshots, config) -> bool:
    from .analysis import _series, _slope
    xs = _series(snapshots, "loss")
    if len(xs) < config.analysis_threshold:
        return False
    s = _slope(xs[-config.analysis_threshold:])
    return s < 0 and xs[-1] > 1e-3
