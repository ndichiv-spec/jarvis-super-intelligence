"""Tests for metric ingestion and provenance labelling."""
import dataclasses
import math
from datetime import datetime

import pytest

from training_advisor.metrics import MetricsStore
from training_advisor.schemas import Provenance


def _store(cfg):
    return MetricsStore(cfg)


class TestIngestProvenance:
    def test_observed_metrics_are_observed(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "step": 10, "loss": 0.5,
                             "learning_rate": 1e-3, "tokens_processed": 100,
                             "training_duration_seconds": 10.0}, "r1")
        obs = set(snap.observed_keys())
        assert {"step", "loss", "learning_rate", "tokens_processed",
                "training_duration_seconds"} <= obs
        assert snap.loss.provenance == Provenance.OBSERVED
        assert snap.step.provenance == Provenance.OBSERVED

    def test_perplexity_derived_from_loss(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "loss": 2.0})
        assert snap.perplexity.value == pytest.approx(math.exp(2.0))
        assert snap.perplexity.provenance == Provenance.DERIVED
        assert "perplexity" not in snap.observed_keys()

    def test_loss_derived_from_perplexity(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "perplexity": 7.389})
        assert snap.loss.value == pytest.approx(math.log(7.389), rel=1e-3)
        assert snap.loss.provenance == Provenance.DERIVED

    def test_throughput_derived(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "tokens_processed": 1000,
                             "training_duration_seconds": 5.0})
        assert snap.tokens_per_second.value == 200.0
        assert snap.tokens_per_second.provenance == Provenance.DERIVED
        assert snap.train_throughput.value == 200.0

    def test_missing_metrics_are_unknown(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "loss": 0.5})
        assert snap.grad_norm.provenance == Provenance.UNKNOWN
        assert snap.grad_norm.value is None
        assert snap.grad_norm.note is not None

    def test_no_invention_of_metrics(self, cfg):
        store = _store(cfg)
        snap = store.ingest({"run_id": "r1", "loss": 0.5})
        assert snap.val_loss.value is None
        assert snap.learning_rate.value is None

    def test_max_history_cap(self, cfg):
        small = dataclasses.replace(cfg, max_history=3)
        store = _store(small)
        for i in range(10):
            store.ingest({"run_id": "r", "step": i, "loss": float(i)})
        assert len(store.snapshots) == 3
        assert store.snapshots[-1].step.value == 9


class TestRuntimeSnapshot:
    def test_stub_metrics_unknown(self, cfg):
        store = _store(cfg)

        class _FakeDb:
            start_time = datetime.utcnow()
            events = []

        store.set_runtime(_FakeDb())
        snap = store.runtime_snapshot()
        assert snap.training_duration_seconds.provenance == Provenance.OBSERVED
        assert snap.loss.provenance == Provenance.UNKNOWN
        assert snap.grad_norm.provenance == Provenance.UNKNOWN
        assert snap.model_name == "Silverwing-Decoder-V2"
