"""Training Analysis Pipeline - 18 anomaly detectors over historical metrics.

Every detector runs over a *history* of ``TrainingMetricsSnapshot`` objects
(never a single step).  Detectors return ``Anomaly`` objects with explicit
evidence; when a metric is absent (``UNKNOWN``) the detector simply reports
"insufficient evidence" rather than fabricating a signal.
"""
from __future__ import annotations

import math
from typing import List, Optional

from .config import AdvisorConfig
from .schemas import (AdvisorStatus, Anomaly, AnomalySeverity, MetricValue,
                      Provenance, TrainingMetricsSnapshot)

# ---------------------------------------------------------------------------
# Robust statistics (pure Python, no numpy dependency)
# ---------------------------------------------------------------------------

def _series(snapshots: List[TrainingMetricsSnapshot], field: str) -> List[float]:
    out = []
    for s in snapshots:
        mv = getattr(s, field, None)
        if isinstance(mv, MetricValue) and mv.value is not None:
            out.append(mv.value)
    return out


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):  # sample std
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _mad(xs):
    med = _median(xs)
    return _median([abs(x - med) for x in xs])


def _slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def _robust_z(val, xs):
    """Robust z-score vs a history. Degenerate (zero-dispersion) history:
    any deviation from the constant median is flagged as a strong outlier."""
    med = _median(xs)
    m = _mad(xs)
    if m > 0:
        return (val - med) / (1.4826 * m)
    s = _std(xs)
    if s > 0:
        return (val - _mean(xs)) / s
    if val == med:
        return 0.0
    return 999.0 if val > med else -999.0


def _pct(a, b):
    return ((a - b) / b) if b else 0.0


def _obs_count(snapshots, field):
    return sum(1 for s in snapshots
               if isinstance(getattr(s, field, None), MetricValue)
               and getattr(s, field).value is not None)


def _latest(snapshots, field):
    for s in reversed(snapshots):
        mv = getattr(s, field, None)
        if isinstance(mv, MetricValue) and mv.value is not None:
            return mv
    return None


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------
# Each detector: (snapshots, config) -> List[Anomaly]

_EXPLODING = 1000.0
_VANISHING = 1e-6


def _a(detector, sev, title, desc, evidence=None, hint=None, metrics_evidence=None):
    return Anomaly(detector=detector, severity=sev, title=title, description=desc,
                   evidence=list(evidence or []), metrics_evidence=list(metrics_evidence or []),
                   recommendation_hint=hint)


def det_loss_divergence(snapshots, config):
    xs = _series(snapshots, "loss")
    if len(xs) < 2:
        return []
    if any((not math.isfinite(v)) for v in xs):
        return [_a("loss_divergence", AnomalySeverity.CRITICAL,
                   "Loss is non-finite",
                   "Training loss became NaN or Inf - an immediate stop and investigation is required.",
                   evidence=[f"loss last={xs[-1]}"], hint="stop_training")]
    if xs[-1] > xs[0] * 1.1:
        return [_a("loss_divergence", AnomalySeverity.HIGH,
                   "Loss is increasing",
                   f"Loss rose {xs[0]:.4f} -> {xs[-1]:.4f} ({(xs[-1]/max(xs[0],1e-9)-1)*100:.1f}%). "
                   "A rising training loss indicates divergence, usually from a learning rate that is too high.",
                   evidence=[f"loss first={xs[0]}", f"loss last={xs[-1]}"],
                   hint="decrease_lr",
                   metrics_evidence=[{"metric": "loss", "first": xs[0], "last": xs[-1]}])]
    return []


def det_loss_plateau(snapshots, config):
    xs = _series(snapshots, "loss")
    if len(xs) < config.analysis_threshold:
        return []
    window = xs[-config.analysis_threshold:]
    s = _slope(window)
    if abs(s) < 1e-6 and window[-1] > 1e-3:
        return [_a("loss_plateau", AnomalySeverity.MEDIUM,
                   "Loss plateau",
                   f"Loss slope over the last {len(window)} snapshots is ~0 ({s:.2e}) and loss={window[-1]:.4f}. "
                   "Flat training loss suggests LR may be too low or the model has plateaued.",
                   evidence=[f"slope={s:.2e}", f"loss={window[-1]}"],
                   hint="decrease_lr", metrics_evidence=[{"metric": "loss", "value": window[-1], "slope": s}])]
    return []


def det_validation_degradation(snapshots, config):
    xs = _series(snapshots, "val_loss")
    if len(xs) < 3:
        return []
    if xs[-1] > xs[0] * 1.05:
        return [_a("validation_degradation", AnomalySeverity.HIGH,
                   "Validation loss degrading",
                   f"Validation loss rose {xs[0]:.4f} -> {xs[-1]:.4f}. Generalization is getting worse.",
                   evidence=[f"val_loss first={xs[0]}", f"val_loss last={xs[-1]}"],
                   hint="decrease_lr", metrics_evidence=[{"metric": "val_loss", "first": xs[0], "last": xs[-1]}])]
    return []


def det_overfitting(snapshots, config):
    tl = _series(snapshots, "loss")
    vl = _series(snapshots, "val_loss")
    if len(tl) < config.analysis_threshold or len(vl) < config.analysis_threshold:
        return []
    ts, vs = _slope(tl[-config.analysis_threshold:]), _slope(vl[-config.analysis_threshold:])
    gap_first = vl[0] - tl[0]
    gap_last = vl[-1] - tl[-1]
    if ts < -1e-6 and vs > 1e-6 and gap_last > gap_first:
        return [_a("overfitting", AnomalySeverity.HIGH,
                   "Possible overfitting",
                   "Training loss declining while validation loss increases and the val-train gap is widening.",
                   evidence=[f"train_slope={ts:.2e}", f"val_slope={vs:.2e}",
                            f"gap {gap_first:.4f} -> {gap_last:.4f}"],
                   hint="tighten_regularization",
                   metrics_evidence=[{"metric":"loss","slope":ts},{"metric":"val_loss","slope":vs}])]
    return []


def det_undertraining(snapshots, config):
    tl = _series(snapshots, "loss")
    if len(tl) < config.analysis_threshold:
        return []
    s = _slope(tl[-config.analysis_threshold:])
    if s < 0 and abs(s) < 1e-3 and tl[-1] > 0.05:
        return [_a("undertraining", AnomalySeverity.LOW,
                   "Possible undertraining",
                   f"Loss still decreasing (slope={s:.2e}) and remains high ({tl[-1]:.4f}); "
                   "convergence has not been reached.",
                   evidence=[f"slope={s:.2e}", f"loss={tl[-1]}"],
                   hint="continue_training", metrics_evidence=[{"metric":"loss","value":tl[-1],"slope":s}])]
    return []


def det_learning_rate_problem(snapshots, config):
    lr = _series(snapshots, "learning_rate")
    loss = _series(snapshots, "loss")
    if not lr:
        return []
    # LR flat while loss plateaued
    if len(lr) >= config.analysis_threshold and max(lr) - min(lr) <= lr[-1] * 1e-6 + 1e-15:
        xs = _series(snapshots, "loss")
        if len(xs) >= config.analysis_threshold and abs(_slope(xs[-config.analysis_threshold:])) < 1e-6:
            return [_a("learning_rate_problem", AnomalySeverity.MEDIUM,
                       "LR not decaying on plateau",
                       "Learning rate is held flat while loss has plateaued; a decay schedule is warranted.",
                       evidence=[f"lr={lr[-1]}"], hint="change_scheduler",
                       metrics_evidence=[{"metric":"learning_rate","value":lr[-1]}])]
    # LR high co-occurring with divergence
    if loss and len(loss) >= 2 and loss[-1] > loss[0] * 1.1 and lr[-1] > 1e-3:
        return [_a("learning_rate_problem", AnomalySeverity.HIGH,
                   "LR too high for stability",
                   f"LR={lr[-1]} with diverging loss suggests the learning rate is too high.",
                   evidence=[f"lr={lr[-1]}", f"loss {loss[0]:.4f}->{loss[-1]:.4f}"],
                   hint="decrease_lr", metrics_evidence=[{"metric":"learning_rate","value":lr[-1]}])]
    return []


def det_gradient_instability(snapshots, config):
    g = _series(snapshots, "grad_norm")
    if len(g) < config.analysis_threshold:
        return []
    cv = _std(g) / (_mean(g) or 1e-9)
    if cv > 1.0:
        return [_a("gradient_instability", AnomalySeverity.HIGH,
                   "Gradient norm unstable",
                   f"grad_norm coefficient of variation={cv:.2f} (high variance across steps).",
                   evidence=[f"cv={cv:.2f}", f"mean={_mean(g):.4f}", f"std={_std(g):.4f}"],
                   hint="investigate_instability", metrics_evidence=[{"metric":"grad_norm","cv":cv}])]
    return []


def det_exploding_gradients(snapshots, config):
    g = _series(snapshots, "grad_norm")
    if not g:
        return []
    mx = max(g)
    if mx > _EXPLODING or (len(g) >= 2 and g[-1] > g[0] * 2 and g[-1] > 10.0):
        return [_a("exploding_gradients", AnomalySeverity.CRITICAL,
                   "Exploding gradients",
                   f"grad_norm max={mx:.2f} exceeds the explosion threshold ({_EXPLODING}) or is growing sharply.",
                   evidence=[f"max_grad_norm={mx}"], hint="decrease_lr",
                   metrics_evidence=[{"metric":"grad_norm","max":mx}])]
    return []


def det_vanishing_gradients(snapshots, config):
    g = _series(snapshots, "grad_norm")
    if len(g) < config.analysis_threshold:
        return []
    if g[-1] < _VANISHING and _slope(g[-config.analysis_threshold:]) <= 0:
        return [_a("vanishing_gradients", AnomalySeverity.HIGH,
                   "Vanishing gradients",
                   f"grad_norm collapsed to {g[-1]:.2e} and is trending toward zero.",
                   evidence=[f"grad_norm last={g[-1]}"], hint="investigate_instability",
                   metrics_evidence=[{"metric":"grad_norm","value":g[-1]}])]
    return []


def det_training_instability(snapshots, config):
    xs = _series(snapshots, "loss")
    if len(xs) < config.analysis_threshold:
        return []
    # sign changes in delta
    deltas = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    changes = sum(1 for i in range(1, len(deltas)) if deltas[i] * deltas[i - 1] < 0)
    cv = _std(xs) / (_mean(xs) or 1e-9)
    if changes > len(deltas) * 0.4 or cv > 0.5:
        return [_a("training_instability", AnomalySeverity.MEDIUM,
                   "Loss oscillation / unstable",
                   f"Loss oscillates (sign changes={changes}/{len(deltas)}) and CV={cv:.2f}.",
                   evidence=[f"sign_changes={changes}", f"cv={cv:.2f}"],
                   hint="investigate_instability", metrics_evidence=[{"metric":"loss","cv":cv}])]
    return []


def det_data_quality(snapshots, config):
    xs = _series(snapshots, "loss")
    if len(xs) < 3:
        return []
    hist = xs[:-1]
    std = _std(hist) or (_mean(hist) * 0.1) or 1e-6
    for i in range(1, len(xs)):
        if abs(xs[i] - xs[i - 1]) > 3 * std:
            return [_a("data_quality", AnomalySeverity.LOW,
                       "Suspicious loss spike",
                       f"Loss jumped {xs[i-1]:.4f} -> {xs[i]:.4f} (>3stddev), suggesting a corrupt/bad batch.",
                       evidence=[f"step {i}: {xs[i-1]}->{xs[i]}"], hint="fix_dataset",
                       metrics_evidence=[{"metric":"loss","index":i,"from":xs[i-1],"to":xs[i]}])]
    return []


def det_dataset_imbalance(snapshots, config):
    em = snapshots[-1].eval_metrics if snapshots else {}
    if not em:
        return []
    nums = [v for v in em.values() if isinstance(v, (int, float))]
    if len(nums) >= 3:
        spread = (max(nums) - min(nums)) / (max(nums) or 1.0)
        if spread > 0.5:
            return [_a("dataset_imbalance", AnomalySeverity.LOW,
                       "Uneven evaluation metric spread",
                       "Per-class eval metrics vary widely; check label/dataset balance.",
                       evidence=[f"spread={spread:.2f}", f"min={min(nums):.3f}", f"max={max(nums):.3f}"],
                       hint="fix_dataset", metrics_evidence=[{"metric": "eval_metrics", "spread": spread}])]
    return []


def det_evaluation_anomaly(snapshots, config):
    vl = _series(snapshots, "val_loss")
    if len(vl) < 3:
        em = snapshots[-1].eval_metrics if snapshots else {}
        if not em:
            return []
        nums = [v for v in em.values() if isinstance(v, (int, float))]
        if len(nums) >= 3 and (max(nums) - min(nums)) / (max(nums) or 1.0) > 0.6:
            return [_a("evaluation_anomaly", AnomalySeverity.MEDIUM,
                       "Unstable evaluation metric",
                       "Evaluation metrics swing widely between snapshots.",
                       evidence=[f"range={min(nums):.3f}-{max(nums):.3f}"], hint="investigate_instability",
                       metrics_evidence=[{"metric":"eval_metrics","min":min(nums),"max":max(nums)}])]
        return []
    if abs(_robust_z(vl[-1], vl)) > 3:
        return [_a("evaluation_anomaly", AnomalySeverity.MEDIUM,
                   "Outlier validation loss",
                   f"Latest val_loss={vl[-1]:.4f} is a >3sigma outlier against history.",
                   evidence=[f"val_loss={vl[-1]}", f"z={_robust_z(vl[-1], vl):.2f}"],
                   hint="investigate_instability", metrics_evidence=[{"metric":"val_loss","value":vl[-1]}])]
    return []


def det_checkpoint_regression(snapshots, config):
    ck = [(s.checkpoint_step.value, s.loss.value) for s in snapshots
          if s.checkpoint_step.value is not None and s.loss.value is not None]
    if len(ck) < 2:
        return []
    worst = 0.0
    for i in range(1, len(ck)):
        if ck[i][1] > ck[0][1] * 1.02:
            worst = max(worst, ck[i][1])
    if worst:
        return [_a("checkpoint_regression", AnomalySeverity.MEDIUM,
                   "Checkpoint regression",
                   f"A later checkpoint ({ck[-1][0]}) has higher loss than an earlier one "
                   f"({ck[0][0]}), indicating a regression in the saved trajectory.",
                   evidence=[f"ckpt {ck[0][0]} loss={ck[0][1]:.4f}", f"ckpt {ck[-1][0]} loss={ck[-1][1]:.4f}"],
                   hint="checkpoint", metrics_evidence=[{"metric":"loss","checkpoints":len(ck)}])]
    return []


def det_throughput_regression(snapshots, config):
    xs = _series(snapshots, "tokens_per_second")
    if len(xs) < config.analysis_threshold:
        return []
    s = _slope(xs[-config.analysis_threshold:])
    if s < 0 and abs(s) / (_mean(xs) or 1.0) > 0.05:
        return [_a("throughput_regression", AnomalySeverity.LOW,
                   "Throughput declining",
                   f"tokens_per_second slope={s:.2f}/step is negative.",
                   evidence=[f"slope={s:.2f}", f"tps last={xs[-1]}"],
                   hint="investigate_instability", metrics_evidence=[{"metric":"tokens_per_second","slope":s}])]
    return []


def det_resource_bottleneck(snapshots, config):
    last = snapshots[-1] if snapshots else None
    if not last:
        return []
    out = []
    gpu = last.gpu_util
    vram = last.vram_used_mb
    vram_tot = last.vram_total_mb
    tps = last.tokens_per_second
    if gpu.value is not None and gpu.value >= 0.9:
        out.append(_a("resource_bottleneck", AnomalySeverity.LOW,
                      "GPU saturated",
                      f"GPU utilization={gpu.value:.0%} is at capacity while throughput tps={tps.value or 'n/a'}.",
                      evidence=[f"gpu_util={gpu.value}"], hint="investigate_instability",
                      metrics_evidence=[{"metric":"gpu_util","value":gpu.value}]))
    if (vram.value is not None and vram_tot.value is not None
            and vram_tot.value > 0 and vram.value / vram_tot.value >= 0.95):
        out.append(_a("resource_bottleneck", AnomalySeverity.MEDIUM,
                      "VRAM near capacity",
                      f"VRAM used={vram.value}MB / total={vram_tot.value}MB "
                      f"({vram.value/vram_tot.value:.0%}); risk of OOM.",
                      evidence=[f"vram={vram.value}/{vram_tot.value}"], hint="checkpoint",
                      metrics_evidence=[{"metric":"vram_used_mb","value":vram.value,"pct":vram.value/vram_tot.value}]))
    return out


def det_suspicious_metric_change(snapshots, config):
    out = []
    if len(snapshots) < 3:
        return out
    metric_fields = ["loss", "val_loss", "learning_rate", "grad_norm", "tokens_per_second"]
    for f in metric_fields:
        xs = _series(snapshots, f)
        if len(xs) >= 3:
            z = _robust_z(xs[-1], xs[:-1])
            if abs(z) > 3:
                out.append(_a("suspicious_metric_change", AnomalySeverity.MEDIUM,
                              f"Suspicious {f} change",
                              f"{f}={xs[-1]} is a {z:.1f}sigma outlier vs recent history.",
                              evidence=[f"{f}={xs[-1]}", f"z={z:.1f}"],
                              hint="investigate_instability",
                              metrics_evidence=[{"metric": f, "value": xs[-1], "z": z}]))
    return out


def det_training_stalled(snapshots, config):
    # step or tokens flat over a window while captured_at advances
    steps = [s.step.value for s in snapshots if s.step.value is not None]
    toks = [s.tokens_processed.value for s in snapshots if s.tokens_processed.value is not None]
    times = [s.captured_at for s in snapshots]
    if len(snapshots) >= config.analysis_threshold:
        if len(steps) >= 2 and steps[-1] == steps[0]:
            return [_a("training_stalled", AnomalySeverity.HIGH,
                       "Step not advancing",
                       "global step has not advanced over the last "
                       f"{len(snapshots)} snapshots.",
                       evidence=[f"step {steps[0]} -> {steps[-1]}"], hint="investigate_instability",
                       metrics_evidence=[{"metric":"step","first":steps[0],"last":steps[-1]}])]
        if len(toks) >= 2 and toks[-1] == toks[0] and times[-1] != times[0]:
            return [_a("training_stalled", AnomalySeverity.MEDIUM,
                       "Tokens not advancing",
                       "tokens_processed is flat across snapshots despite time passing.",
                       evidence=[f"tokens {toks[0]} -> {toks[-1]}"], hint="investigate_instability",
                       metrics_evidence=[{"metric":"tokens_processed","first":toks[0],"last":toks[-1]}])]
    # single snapshot that never advances can't be proven stalled; report unknown-data
    if len(snapshots) < config.analysis_threshold:
        return [_a("training_stalled", AnomalySeverity.INFO,
                   "Insufficient history",
                   f"Only {len(snapshots)} snapshot(s) observed; need >="
                   f"{config.analysis_threshold} to evaluate stalling trends.",
                   evidence=[], hint="collect_metrics")]
    return []


DETECTORS = [
    det_loss_divergence, det_loss_plateau, det_validation_degradation,
    det_overfitting, det_undertraining, det_learning_rate_problem,
    det_gradient_instability, det_exploding_gradients, det_vanishing_gradients,
    det_training_instability, det_data_quality, det_dataset_imbalance,
    det_evaluation_anomaly, det_checkpoint_regression, det_throughput_regression,
    det_resource_bottleneck, det_suspicious_metric_change, det_training_stalled,
]

_DETECTOR_TITLES = {
    "loss_divergence", "loss_plateau", "validation_degradation", "overfitting",
    "undertraining", "learning_rate_problem", "gradient_instability",
    "exploding_gradients", "vanishing_gradients", "training_instability",
    "data_quality", "dataset_imbalance", "evaluation_anomaly",
    "checkpoint_regression", "throughput_regression", "resource_bottleneck",
    "suspicious_metric_change", "training_stalled",
}

_DETECTOR_TITLE_MAP = {name: name.replace("_", " ").title() for name in _DETECTOR_TITLES}


def run_all_detectors(snapshots, config):
    anomalies: List[Anomaly] = []
    for d in DETECTORS:
        try:
            anomalies.extend(d(snapshots, config))
        except Exception as e:  # a detector must never crash the pipeline
            anomalies.append(_a(d.__name__, AnomalySeverity.INFO,
                                f"{d.__name__} error",
                                f"Detector raised: {e}", hint="collect_metrics"))
    return anomalies


def classify_status(snapshots, anomalies):
    """Map anomalies -> AdvisorStatus without fabricating signals."""
    if not snapshots:
        return AdvisorStatus.UNKNOWN
    obs = sum(len(s.observed_keys()) for s in snapshots)
    if obs == 0:
        return AdvisorStatus.UNKNOWN
    crit = [a for a in anomalies if a.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)]
    med = [a for a in anomalies if a.severity in (AnomalySeverity.LOW, AnomalySeverity.MEDIUM)]
    if any(a.severity == AnomalySeverity.CRITICAL for a in anomalies):
        return AdvisorStatus.CRITICAL
    if crit or med:
        return AdvisorStatus.WARNING
    return AdvisorStatus.HEALTHY


def build_analysis_text(snapshots, anomalies):
    obs = sum(len(s.observed_keys()) for s in snapshots)
    if not snapshots or obs == 0:
        return (f"Analyzed {len(snapshots)} snapshot(s) with {obs} OBSERVED metric(s). "
                "No live training metrics are currently instrumented (the Silverwing model "
                "state is a static stub). POST real training metrics to "
                "/api/training/metrics or /api/tools/invoke (tool='training_advisor') to "
                "enable statistical advising.")
    sev_counts = {}
    for a in anomalies:
        sev_counts[a.severity.value] = sev_counts.get(a.severity.value, 0) + 1
    sev_str = ", ".join(f"{k}:{v}" for k, v in sev_counts.items()) or "none"
    names = "; ".join(a.title for a in anomalies[:5]) or "none"
    return (f"Analyzed {len(snapshots)} snapshot(s), {obs} OBSERVED metric(s). "
            f"Detectors flagged {len(anomalies)} anomaly/anomalies [{sev_str}]: {names}.")
