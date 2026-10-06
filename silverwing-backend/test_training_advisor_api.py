"""Integration tests for the Training Advisor HTTP endpoints + tool interface.

Run with:  python -m pytest test_training_advisor_api.py -q
(Uses the shared module-level db; SILVERWING_PERSIST=0 via backend/conftest.py.)
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _post_metrics(payload):
    resp = client.post("/api/training/metrics", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestTrainingMetricsAPI:
    def test_get_metrics_empty(self):
        resp = client.get("/api/training/metrics")
        assert resp.status_code == 200
        assert "snapshots" in resp.json()

    def test_post_metrics_provenance(self):
        body = {"run_id": "api-e2e", "step": 1, "loss": 0.5, "learning_rate": 1e-3,
                "tokens_processed": 100, "training_duration_seconds": 10.0}
        data = _post_metrics(body)
        assert data["status"] == "ok"
        obs = set(data["observed_keys"])
        assert {"step", "loss", "learning_rate", "tokens_processed",
                "training_duration_seconds"} <= obs


class TestTrainingAdvisorAPI:
    def test_status(self):
        resp = client.get("/api/training/advisor/status")
        assert resp.status_code == 200
        s = resp.json()
        assert s["status"] == "ok"
        assert "summary" in s

    def test_analyze_returns_validated_result(self):
        # seed a small real (OBSERVED) metric history so analysis is non-trivial
        for i in range(6):
            _post_metrics({"run_id": "api-e2e", "step": i * 10,
                           "loss": 1.0 - i * 0.05, "learning_rate": 1e-3,
                           "val_loss": 1.1 - i * 0.04})
        resp = client.post("/api/training/advisor/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["provider"] in {"local", "gemini"}
        result = data["result"]
        assert result["status"] in {"healthy", "warning", "critical", "unknown"}
        assert isinstance(result["recommendations"], list)
        assert result["provenance"]["provider"] in {"local", "gemini"}

    def test_recommendations(self):
        resp = client.get("/api/training/advisor/recommendations")
        assert resp.status_code == 200
        assert isinstance(resp.json()["recommendations"], list)

    def test_history(self):
        resp = client.get("/api/training/advisor/history")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["history"], list)
        assert len(data["history"]) >= 1

    def test_evidence(self):
        resp = client.get("/api/training/advisor/evidence")
        assert resp.status_code == 200
        ev = resp.json()["evidence"]
        assert isinstance(ev, list)
        assert any(e.get("source_type") == "training_advisor" for e in ev)

    def test_experiments(self):
        resp = client.get("/api/training/advisor/experiments")
        assert resp.status_code == 200
        ex = resp.json()["experiments"]
        assert isinstance(ex, list)
        assert any(e.get("type") == "experiment" for e in ex)

    def test_approve_round_trip(self):
        # ensure we have a recommendation to approve
        client.post("/api/training/advisor/analyze")
        recs = client.get("/api/training/advisor/recommendations").json()["recommendations"]
        assert len(recs) >= 1
        rid = recs[-1]["id"]
        resp = client.post("/api/training/advisor/approve", json={
            "recommendation_id": rid, "approver": "e2e-test",
        })
        assert resp.status_code == 200
        out = resp.json()
        assert out["status"] == "ok"
        assert out["result"]["approved"] is True

    def test_approve_unknown(self):
        resp = client.post("/api/training/advisor/approve", json={
            "recommendation_id": "does-not-exist", "approver": "x",
        })
        assert resp.status_code == 200
        assert resp.json()["result"]["approved"] is False
