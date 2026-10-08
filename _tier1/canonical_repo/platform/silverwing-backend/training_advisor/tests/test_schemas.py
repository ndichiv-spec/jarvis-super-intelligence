"""Schema + provenance-unit tests."""
import pytest
from pydantic import ValidationError

from training_advisor.schemas import (
    AdvisorResult, AdvisorStatus, Anomaly, AnomalySeverity,
    MetricValue, Provenance, Recommendation, RecommendationAction,
    RiskLevel, TrainingMetricsSnapshot, ProvenanceRecord,
)


def _obs(v):
    return MetricValue.observed(v, "test")


class TestMetricValue:
    def test_observed_float(self):
        m = MetricValue.observed(0.123, "training_loop")
        assert m.value == 0.123
        assert m.provenance == Provenance.OBSERVED
        assert m.source == "training_loop"

    def test_derived_text(self):
        m = MetricValue.derived("adamw", "derived")
        assert m.value is None
        assert m.text == "adamw"
        assert m.provenance == Provenance.DERIVED

    def test_unknown_defaults(self):
        m = MetricValue.unknown("stub", "no live data")
        assert m.value is None
        assert m.provenance == Provenance.UNKNOWN
        assert m.note is not None


class TestSnapshotDefaults:
    def test_all_metrics_unknown_by_default(self):
        snap = TrainingMetricsSnapshot(captured_at="t", run_id="r", model="m",
                                       model_name="M", architecture="transformer")
        assert snap.observed_keys() == []  # nothing observed -> empty
        assert snap.loss.provenance == Provenance.UNKNOWN

    def test_observed_keys_only_counts_observed(self):
        snap = TrainingMetricsSnapshot(captured_at="t", run_id="r", model="m",
                                       model_name="M", architecture="t")
        snap.loss = MetricValue.observed(1.0, "loop")
        snap.perplexity = MetricValue.derived(2.7, "loop")
        assert snap.observed_keys() == ["loss"]
        assert "perplexity" not in snap.observed_keys()


class TestRecommendation:
    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Recommendation(id="x", action="keep_lr", reason="r", confidence=1.5,
                           expected_effect="e", risk=RiskLevel.LOW)
        with pytest.raises(ValidationError):
            Recommendation(id="x", action="keep_lr", reason="r", confidence=-0.1,
                           expected_effect="e", risk=RiskLevel.LOW)

    def test_action_enum_members(self):
        names = {a.value for a in RecommendationAction}
        for required in ["keep_lr", "increase_lr", "decrease_lr", "use_warmup",
                         "extend_warmup", "change_scheduler", "stop_training",
                         "continue_training", "investigate_instability",
                         "collect_metrics", "checkpoint", "fix_dataset"]:
            assert required in names


class TestAdvisorResultValidation:
    def _valid(self):
        return {
            "analysis": "ok",
            "status": "warning",
            "recommendations": [
                {"id": "r1", "action": "keep_lr", "reason": "healthy",
                 "confidence": 0.8, "expected_effect": "no change", "risk": "low"},
            ],
            "anomalies": [],
            "metrics_summary": {},
            "provenance": {
                "created_at": "2024-01-01T00:00:00", "run_id": "r",
            },
        }

    def test_validates_clean(self):
        r = AdvisorResult.model_validate(self._valid())
        assert r.status == AdvisorStatus.WARNING
        assert r.recommendations[0].action == "keep_lr"
        assert r.recommendation_actions() == ["keep_lr"]

    def test_rejects_missing_required(self):
        d = self._valid()
        del d["recommendations"][0]["reason"]
        with pytest.raises(ValidationError):
            AdvisorResult.model_validate(d)

    def test_rejects_bad_status_enum(self):
        d = self._valid()
        d["status"] = "on_fire"
        with pytest.raises(ValidationError):
            AdvisorResult.model_validate(d)

    def test_rejects_bad_confidence(self):
        d = self._valid()
        d["recommendations"][0]["confidence"] = 5.0
        with pytest.raises(ValidationError):
            AdvisorResult.model_validate(d)

    def test_rejects_non_object_root(self):
        with pytest.raises((ValidationError, ValueError)):
            AdvisorResult.model_validate(["not", "an", "object"])

    def test_rejects_injection_extra_field_is_ignored(self):
        # Extra unknown fields are ignored by default (pydantic), but a
        # structurally-invalid recommendation must still be rejected.
        d = self._valid()
        d["recommendations"][0]["confidence"] = "not-a-number"
        with pytest.raises(ValidationError):
            AdvisorResult.model_validate(d)

    def test_json_round_trip(self):
        r = AdvisorResult.model_validate(self._valid())
        AdvisorResult.model_validate_json(r.model_dump_json())
