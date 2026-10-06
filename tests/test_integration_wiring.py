from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import monitoring_extended
from api.routers.ai import router as ai_router
from core.metrics import metrics


class _FakeAIResponse:
    def __init__(self) -> None:
        self.text = "ok"
        self.model = "local"
        self.confidence = 0.9
        self.sources = []
        self.tool_calls = []
        self.tool_results = []
        self.metadata = {"intents": [], "entities": {}}


class _FakeAIEngine:
    def chat(self, **kwargs):
        return _FakeAIResponse()

    def generate(self, prompt: str, max_tokens: int = 128):
        return _FakeAIResponse()

    def get_status(self):
        return {"tools_available": 3, "conversation_turns": 4}

    def train(self, input_text: str, output_text: str):
        return None


def test_monitoring_extended_mounts_at_single_monitoring_prefix():
    app = FastAPI()
    app.include_router(monitoring_extended.router, prefix="/api/v1/monitoring")
    client = TestClient(app)

    ok_response = client.get("/api/v1/monitoring/metrics")
    bad_response = client.get("/api/v1/monitoring/monitoring/metrics")

    assert ok_response.status_code == 200
    assert bad_response.status_code == 404


def test_ai_process_updates_metrics(monkeypatch):
    app = FastAPI()
    app.include_router(ai_router, prefix="/api/v1/ai")

    from api.middleware.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user"}
    monkeypatch.setattr("api.routers.ai.get_ai_engine", lambda: _FakeAIEngine(), raising=False)

    import ai_engine

    monkeypatch.setattr(ai_engine, "get_ai_engine", lambda: _FakeAIEngine())

    client = TestClient(app)
    response = client.post(
        "/api/v1/ai/process",
        json={"input": "hello", "use_rag": False, "learn": False, "model": "local"},
    )

    assert response.status_code == 200

    summary = metrics.get_metrics_summary()
    assert summary["counters"]["jarvis_ai_requests_total"] >= 1
    assert "jarvis_ai_processing_seconds" in summary["histograms"]
