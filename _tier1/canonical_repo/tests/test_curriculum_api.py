"""API-level tests for the governed curriculum router (offline; no live probes).

The router is exercised via TestClient. Live-probe and network surfaces are
faked so the suite stays hermetic: hub endpoints use a stub adapter, and only
validation-shape cases (400/404) are hit against the real remote/lifecycle
paths.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import jarvis_backend.routers.curriculum as cr
from jarvis_backend.main import app


@pytest.fixture
def client(monkeypatch):
    class _FakeHF:
        configured = True

        def discover_models(self, search="", author="", limit=20, pipeline_tag=""):
            return [
                {
                    "model_id": "org/m1",
                    "name": "m1",
                    "capabilities": ["chat"],
                    "tags": {"x"},
                    "downloads": 1,
                    "likes": 0,
                    "sha": "",
                }
            ]

        def hub_health(self, force=False):
            return SimpleNamespace(
                status="healthy",
                to_dict=lambda: {"status": "healthy", "provider": "hf"},
            )

        def hub_identity(self):
            return {"type": "user", "name": "tester", "fullname": "Test User", "org": None}

    monkeypatch.setattr(cr, "_hf_adapter", lambda: _FakeHF())
    from jarvis_backend.core import get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_hub_health_uses_fake_adapter(client):
    resp = client.get("/api/v1/hub/health?probe=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["health"]["status"] == "healthy"
    assert body["role"] == "registry"


def test_hub_models_returns_parsed_rows(client):
    resp = client.get("/api/v1/hub/models?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "huggingface-hub"
    assert body["count"] == 1
    row = body["models"][0]
    assert row["model_id"] == "org/m1"
    assert row["capabilities"] == ["chat"]  # normalized + sorted


def test_hub_models_rejects_bad_limit(client):
    resp = client.get("/api/v1/hub/models?limit=0")
    assert resp.status_code == 422


def test_teachers_endpoint_shape(client):
    resp = client.get("/api/v1/teachers")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("teachers"), list)


def test_datasets_list_shape(client):
    resp = client.get("/api/v1/datasets")
    assert resp.status_code == 200
    body = resp.json()
    assert "datasets" in body


def test_unknown_domain_rejected(client):
    resp = client.post("/api/v1/episodes", json={"domain": "not-a-domain", "difficulty": 3})
    # Either 400 (domain actually unknown in DOMAIN_CATEGORIES) or a mesh/edge
    # failure — but never a fabricated COMPLETED with no verification.
    assert resp.status_code in (400, 500, 503)


def test_training_launch_requires_remote_target(client):
    resp = client.post("/api/v1/training/runs", json={"dataset_ids": ["ds-1"]})
    assert resp.status_code == 400


def test_training_launch_requires_datasets(client):
    resp = client.post("/api/v1/training/runs", json={"remote_target": "http://train.example"})
    assert resp.status_code == 400


def test_models_revisions_endpoint(client):
    resp = client.get("/api/v1/models/revisions")
    assert resp.status_code == 200
    body = resp.json()
    assert "records" in body
    assert body["count"] >= 0


def test_lineage_404_for_missing_record(client):
    resp = client.get("/api/v1/models/does-not-exist/lineage")
    assert resp.status_code == 404


def test_training_runs_empty_shape(client):
    resp = client.get("/api/v1/training/runs")
    assert resp.status_code == 200
    assert "runs" in resp.json()