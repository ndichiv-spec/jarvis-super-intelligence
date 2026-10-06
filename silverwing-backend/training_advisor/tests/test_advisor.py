"""Tests for the TrainingAdvisor orchestrator: cache/dedup, interval gating,
authorization gating, provenance recording (Evidence + Knowledge Graph), and
the unified tool-handler dispatch."""
import asyncio
import dataclasses

import pytest

import main as main_mod
from training_advisor import AdvisorConfig, TrainingAdvisor, AdvisorStatus
from training_advisor.schemas import RecommendationAction


def _diverging(inst, n=8):
    for i in range(n):
        inst.store.ingest({"run_id": "r", "step": i * 10, "loss": 2.0 + 0.3 * i,
                           "learning_rate": 1e-3, "tokens_processed": i * 100,
                           "training_duration_seconds": i * 10.0}, "r")


def _healthy(inst, n=10):
    for i in range(n):
        inst.store.ingest({"run_id": "r", "step": i * 10, "loss": 1.0 - 0.05 * i,
                           "val_loss": 1.1 - 0.04 * i}, "r")


class TestOrchestratorBasic:
    def test_empty_history_unknown(self, ta):
        res = asyncio.run(ta.analyze(force=True))
        assert res.provider == "local"
        assert res.status == AdvisorStatus.UNKNOWN
        assert any(r.action == RecommendationAction.COLLECT_METRICS.value for r in res.recommendations)

    def test_divergence_local_recommendation(self, ta):
        _diverging(ta)
        res = asyncio.run(ta.analyze(force=True))
        assert res.status == AdvisorStatus.WARNING
        actions = {r.action for r in res.recommendations}
        assert {"decrease_lr", "investigate_instability"} & actions

    def test_decrease_lr_is_authorization_gated(self, ta):
        _diverging(ta)
        res = asyncio.run(ta.analyze(force=True))
        dec = [r for r in res.recommendations if r.action == "decrease_lr"]
        assert dec
        assert dec[0].authorization_required is True

    def test_keep_lr_not_authorization_gated(self, ta):
        _healthy(ta)
        res = asyncio.run(ta.analyze(force=True))
        keep = [r for r in res.recommendations if r.action == "keep_lr"]
        assert keep
        assert keep[0].authorization_required is False


class TestCacheDedup:
    def test_same_metric_window_cached(self, ta):
        _healthy(ta, 6)
        r1 = asyncio.run(ta.analyze(force=False))
        r2 = asyncio.run(ta.analyze(force=False))
        assert r1 is r2  # identical window -> cached object

    def test_force_recomputes(self, ta):
        _healthy(ta, 6)
        r1 = asyncio.run(ta.analyze(force=False))
        r2 = asyncio.run(ta.analyze(force=True))
        assert r2 is not r1
        assert r2.cache_key == r1.cache_key


class TestIntervalGating:
    def test_interval_blocks_rerun(self, cfg):
        slow = dataclasses.replace(cfg, advisory_interval_seconds=99999.0)
        inst = TrainingAdvisor(slow)
        _healthy(inst, 6)
        r1 = asyncio.run(inst.analyze(force=False))
        r2 = asyncio.run(inst.analyze(force=False))
        assert r1 is r2


class TestProvenanceRecording:
    def test_analyze_records_evidence_and_entity(self, ta_db):
        for i in range(6):
            asyncio.run(ta_db.ingest({"run_id": "prov", "step": i, "loss": 0.5 + i * 0.01}, "prov"))
        before_ev = len(main_mod.db.evidence)
        before_kg = len(main_mod.db.knowledge)
        asyncio.run(ta_db.analyze(force=True))
        assert len(main_mod.db.evidence) > before_ev
        assert len(main_mod.db.knowledge) > before_kg
        newest = list(main_mod.db.evidence.values())[-1]
        assert newest.source_type == "training_advisor"
        # training_history holds the validated AdvisorResult
        assert len(main_mod.db.training_history) >= 1
        last = main_mod.db.training_history[-1]
        assert last.status.value in {"healthy", "warning", "critical", "unknown"}
        assert last.provider in {"local", "gemini"}

    def test_history_and_experiments(self, ta_db):
        asyncio.run(ta_db.analyze(force=True))
        hist = asyncio.run(ta_db.recorder.history(50))
        assert len(hist) >= 1
        assert "status" in hist[-1]
        assert isinstance(asyncio.run(ta_db.experiments(50)), list)
        assert isinstance(asyncio.run(ta_db.evidence(200)), list)

    def test_approve_mutating_recommendation(self, ta_db):
        _diverging(ta_db)
        asyncio.run(ta_db.analyze(force=True))
        latest = ta_db._last_result
        rec = next((r for r in latest.recommendations if r.authorization_required), None)
        assert rec is not None, "expected at least one authorization-gated recommendation"
        out = asyncio.run(ta_db.approve(rec.id, "tester", {"note": "manual override"}))
        assert out["approved"] is True
        assert rec.approved is True
        assert {"recommendation_id", "approver"} <= out.keys()

    def test_approve_unknown_id(self, ta_db):
        out = asyncio.run(ta_db.approve("no-such-id", "tester"))
        assert out["approved"] is False

    def test_approve_without_db_recorder(self, ta):
        asyncio.run(ta.analyze(force=True))
        out = asyncio.run(ta.approve("nope"))
        assert out["approved"] is False


class TestToolHandler:
    def test_status_dispatch(self, ta):
        out = asyncio.run(ta.tool_handler({"action": "status"}))
        assert out["status"] == "ok"
        assert "summary" in out

    def test_analyze_dispatch(self, ta):
        out = asyncio.run(ta.tool_handler({"action": "analyze"}))
        assert out["status"] == "ok"
        assert "provider" in out
        assert "result" in out

    def test_metrics_dispatch(self, ta):
        ta.store.ingest({"run_id": "r", "step": 1, "loss": 0.5}, "r")
        out = asyncio.run(ta.tool_handler({"action": "metrics"}))
        assert out["status"] == "ok"
        assert "snapshots" in out

    def test_recommendations_dispatch(self, ta):
        _diverging(ta)
        asyncio.run(ta.analyze(force=True))
        out = asyncio.run(ta.tool_handler({"action": "recommendations"}))
        assert out["status"] == "ok"
        assert isinstance(out["recommendations"], list)

    def test_unknown_action(self, ta):
        out = asyncio.run(ta.tool_handler({"action": "does-not-exist"}))
        assert out["status"] == "error"


# Shared db-backed fixture (uses the real module-level db + websocket manager).
@pytest.fixture
def ta_db(cfg):
    return TrainingAdvisor(cfg, db=main_mod.db, ws=main_mod.websocket_manager)
