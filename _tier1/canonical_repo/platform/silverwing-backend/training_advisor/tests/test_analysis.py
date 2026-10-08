"""Tests for the 18-detector analysis pipeline + status classification."""
import math

from training_advisor.analysis import (
    DETECTORS, run_all_detectors, classify_status, build_analysis_text,
)
from training_advisor.schemas import (
    AnomalySeverity, AdvisorStatus, MetricValue, TrainingMetricsSnapshot,
)


def _snap(i, **kw):
    fields = {}
    for k, v in kw.items():
        if isinstance(v, (dict, list)):
            fields[k] = v
        elif isinstance(v, (int, float)):
            fields[k] = MetricValue.observed(v, "test")
        else:
            fields[k] = MetricValue.observed(str(v), "test")
    return TrainingMetricsSnapshot(
        captured_at=f"2024-01-01T00:00:{i:02d}", run_id="r", model="m",
        model_name="M", architecture="transformer", **fields)


def _series(n, fn):
    return [_snap(i, **fn(i)) for i in range(n)]


class TestDetectorRegistry:
    def test_eighteen_detectors(self):
        # The task mandates exactly 18 anomaly detectors.
        assert len(DETECTORS) == 18
        names = {d.__name__ for d in DETECTORS}
        for required in [
            "det_loss_divergence", "det_loss_plateau", "det_validation_degradation",
            "det_overfitting", "det_undertraining", "det_learning_rate_problem",
            "det_gradient_instability", "det_exploding_gradients",
            "det_vanishing_gradients", "det_training_instability", "det_data_quality",
            "det_dataset_imbalance", "det_evaluation_anomaly",
            "det_checkpoint_regression", "det_throughput_regression",
            "det_resource_bottleneck", "det_suspicious_metric_change",
            "det_training_stalled",
        ]:
            assert required in names, required


class TestDetectors:
    def test_loss_divergence_fires(self, cfg):
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 2.4 - 0.05 * i + (i > 4) * 0.6 * (i - 4)})
        # losses climb after step 5
        anoms = run_all_detectors(snaps, cfg)
        dets = {a.detector for a in anoms}
        assert "loss_divergence" in dets

    def test_loss_plateau_fires(self, cfg):
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 0.5 + 1e-9 * i,
                                      "learning_rate": 1e-4})
        # flat loss, flat LR -> plateau + lr not decaying on plateau
        anoms = run_all_detectors(snaps, cfg)
        dets = {a.detector for a in anoms}
        assert "loss_plateau" in dets

    def test_validation_degradation_fires(self, cfg):
        snaps = _series(5, lambda i: {"step": i * 10, "loss": 0.1 * i,
                                      "val_loss": 0.5 + 0.3 * i})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "validation_degradation" for a in anoms)

    def test_overfitting_fires(self, cfg):
        # train loss falling, val loss rising, gap widening
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 2.0 - 0.2 * i,
                                      "val_loss": 1.0 + 0.15 * i})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "overfitting" for a in anoms)

    def test_gradient_instability_fires(self, cfg):
        # grad_norm with high CV
        snaps = [_snap(i, step=i * 10, grad_norm=50.0 if i == 7 else 0.1) for i in range(8)]
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "gradient_instability" for a in anoms)

    def test_exploding_gradients_fires(self, cfg):
        snaps = _series(4, lambda i: {"step": i * 10, "grad_norm": [1.0, 5.0, 50.0, 2000.0][i]})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "exploding_gradients" for a in anoms)

    def test_vanishing_gradients_fires(self, cfg):
        snaps = [_snap(i, step=i * 10,
                       grad_norm=1e-9 * (0.5 ** i)) for i in range(8)]
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "vanishing_gradients" for a in anoms)

    def test_training_plateau_undertraining(self, cfg):
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 0.5 - 1e-4 * i})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "undertraining" for a in anoms)

    def test_resource_bottleneck_fires(self, cfg):
        snaps = [_snap(0, step=1, gpu_util=0.95, vram_used_mb=24_000,
                       vram_total_mb=25_600, tokens_per_second=50)]
        snaps = _series(1, lambda i: {"step": i, "gpu_util": 1.0,
                                      "vram_used_mb": 24000, "vram_total_mb": 25600,
                                      "tokens_per_second": 50})
        anoms = run_all_detectors(snaps, cfg)
        dets = {a.detector for a in anoms}
        assert "resource_bottleneck" in dets

    def test_training_stalled_insufficient_history(self, cfg):
        snaps = _series(1, lambda i: {"step": i, "loss": 0.5})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "training_stalled" for a in anoms)

    def test_stalled_step_not_advancing(self, cfg):
        snaps = _series(6, lambda i: {"step": 10, "loss": 0.5 - 0.01 * i})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "training_stalled" for a in anoms)

    def test_suspicious_metric_change_fires(self, cfg):
        snaps = _series(5, lambda i: {"step": i * 10, "loss": 0.5,
                                      "learning_rate": 1e-3, "grad_norm": 1.0,
                                      "tokens_per_second": 100.0})
        snaps.append(_snap(5, step=60, loss=5.0, learning_rate=1e-3,
                           grad_norm=1.0, tokens_per_second=100.0))
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "suspicious_metric_change" for a in anoms)

    def test_data_quality_fires(self, cfg):
        snaps = _series(5, lambda i: {"step": i * 10, "loss": 0.5})
        snaps.append(_snap(5, step=60, loss=5.0))
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "data_quality" for a in anoms)

    def test_dataset_imbalance_fires(self, cfg):
        snaps = [_snap(0, step=1, eval_metrics={"acc_a": 0.9, "acc_b": 0.1, "acc_c": 0.2})]
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "dataset_imbalance" for a in anoms)

    def test_evaluation_anomaly_fires(self, cfg):
        # val_loss normal then a 3-sigma outlier
        base = [0.5, 0.48, 0.5, 0.51, 0.49, 0.5, 0.48, 0.51]
        snaps = _series(8, lambda i: {"step": i * 10, "val_loss": base[i]})
        snaps.append(_snap(8, step=80, val_loss=5.0))
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "evaluation_anomaly" for a in anoms)

    def test_checkpoint_regression_fires(self, cfg):
        snaps = []
        for i in range(6):
            snaps.append(TrainingMetricsSnapshot(
                captured_at=f"t{i}", run_id="r", model="m", model_name="M",
                architecture="t", loss=MetricValue.observed(0.5 - 0.01 * i, "loop"),
                checkpoint_step=MetricValue.observed(i * 100, "loop")))
        # last checkpoint regresses loss
        snaps.append(TrainingMetricsSnapshot(
            captured_at="t6", run_id="r", model="m", model_name="M",
            architecture="t", loss=MetricValue.observed(0.7, "loop"),
            checkpoint_step=MetricValue.observed(600, "loop")))
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "checkpoint_regression" for a in anoms)

    def test_throughput_regression_fires(self, cfg):
        snaps = _series(8, lambda i: {"step": i * 10,
                                      "tokens_per_second": 100.0 - 10.0 * i})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "throughput_regression" for a in anoms)

    def test_learning_rate_problem_fires(self, cfg):
        # flat LR while loss plateaued
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 0.5, "learning_rate": 1e-4})
        anoms = run_all_detectors(snaps, cfg)
        assert any(a.detector == "learning_rate_problem" for a in anoms)

    def test_healthy_no_anomalies(self, cfg):
        snaps = _series(10, lambda i: {"step": i * 10, "loss": 1.0 - 0.05 * i,
                                       "val_loss": 0.9 - 0.04 * i,
                                       "learning_rate": 1e-3})
        anoms = run_all_detectors(snaps, cfg)
        assert anoms == []


class TestStatusClassification:
    def test_empty_history_unknown(self, cfg):
        snaps = []
        status = classify_status(snaps, [])
        assert status == AdvisorStatus.UNKNOWN

    def test_no_observed_metrics_unknown(self, cfg):
        # all-UNKNOWN stub snapshot
        snap = TrainingMetricsSnapshot(captured_at="t", run_id="r", model="m",
                                       model_name="M", architecture="transformer")
        status = classify_status([snap], [])
        assert status == AdvisorStatus.UNKNOWN

    def test_critical_severity(self, cfg):
        snaps = _series(4, lambda i: {"step": i * 10,
                                      "loss": [2.4, 2.1, 2.1, 3.1][i],
                                      "grad_norm": 5000.0})
        anoms = run_all_detectors(snaps, cfg)
        status = classify_status(snaps, anoms)
        assert status == AdvisorStatus.CRITICAL

    def test_healthy(self, cfg):
        snaps = _series(10, lambda i: {"step": i * 10, "loss": 1.0 - 0.05 * i})
        anoms = run_all_detectors(snaps, cfg)
        status = classify_status(snaps, anoms)
        assert status == AdvisorStatus.HEALTHY

    def test_analysis_text_summarises(self, cfg):
        snaps = _series(8, lambda i: {"step": i * 10, "loss": 2.0 + 0.2 * i})
        anoms = run_all_detectors(snaps, cfg)
        text = build_analysis_text(snaps, anoms)
        assert "Analyzed" in text
        assert "snapshot" in text
