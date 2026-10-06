"""Phase 2.2 — observability tests.

Covers request-id correlation (header propagation + echo), metrics middleware
(request counting + the live /api/v1/metrics endpoint), and error tracking
(ChatError correlation + generic-Exception 500).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_backend.errors import ChatError, ErrorCategory


# --------------------------------------------------------------------------- #
# Shared app tests (use the project's TestClient)
# --------------------------------------------------------------------------- #
def test_request_id_generated_when_absent(client):
    resp = client.get("/api/ping")
    rid = resp.headers.get("X-Request-ID")
    assert rid, "X-Request-ID must be generated"
    # looks like a uuid4
    import uuid

    uuid.UUID(rid)


def test_request_id_propagated_from_header(client):
    resp = client.get("/api/ping", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


def test_request_id_echoed_on_404(client):
    resp = client.get("/api/does-not-exist", headers={"X-Request-ID": "rid-404"})
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-ID") == "rid-404"


def test_metrics_recorded_on_real_app(client):
    client.get("/api/ping")
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "requests_total" in data
    assert "GET|/api/ping|200" in data["requests_total"]
    assert data["requests_total"]["GET|/api/ping|200"] >= 1
    assert "request_duration_seconds" in data
    assert "errors_total" in data


def test_metrics_endpoint_reports_memory_items(client):
    from jarvis_backend.core import get_store, now_iso

    mem = get_store("memory").load()
    mem["m-1"] = {"id": "m-1", "content": "hello world", "layer": "short_term",
                  "importance": 0.5, "created_at": now_iso()}
    get_store("memory").save()
    resp = client.get("/api/v1/metrics")
    assert resp.json()["memory_items"] == 1


# --------------------------------------------------------------------------- #
# Isolated error-tracking app (does not mutate the shared project app)
# --------------------------------------------------------------------------- #
def _error_app() -> FastAPI:
    from jarvis_backend.observability import install_observability

    app = FastAPI()
    install_observability(app)

    @app.get("/boom")
    async def boom():
        raise ChatError(
            ErrorCategory.MODEL_ERROR, "provider exploded", retryable=True
        )

    @app.get("/crash")
    async def crash():
        raise RuntimeError("kaboom")

    return app


def _tc(app: FastAPI) -> TestClient:
    # raise_server_exceptions=False so the generic handler returns a 500 JSON
    # instead of the test client re-raising the exception.
    return TestClient(app, raise_server_exceptions=False)


def test_chat_error_handler_correlates_and_logs(caplog):
    caplog.set_level(logging.INFO)
    app = _error_app()
    resp = _tc(app).get("/boom", headers={"X-Request-ID": "corr-1"})

    assert resp.status_code == 502
    assert resp.headers["X-Request-ID"] == "corr-1"
    body = resp.json()["error"]
    assert body["category"] == "MODEL_ERROR"
    assert body["request_id"] == "corr-1"
    assert body["retryable"] is True
    assert body["status_code"] == 502

    # Structured error log carries the correlation id end-to-end.
    assert "corr-1" in caplog.text
    assert "MODEL_ERROR" in caplog.text


def test_unhandled_exception_returns_500_with_request_id():
    app = _error_app()
    resp = _tc(app).get("/crash", headers={"X-Request-ID": "corr-2"})

    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] == "corr-2"
    body = resp.json()["error"]
    assert body["category"] == "INTERNAL_ERROR"
    assert body["request_id"] == "corr-2"
    assert body["status_code"] == 500


# --------------------------------------------------------------------------- #
# record_error unit behaviour
# --------------------------------------------------------------------------- #
def test_record_error_classifies_generic_exception():
    from starlette.requests import Request

    from jarvis_backend.observability import record_error, request_id_var

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "raw_path": b"/api/chat",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    token = request_id_var.set("unit-rid")
    try:
        err = record_error(request, ValueError("something broke"))
    finally:
        request_id_var.reset(token)

    assert err.category == ErrorCategory.UNKNOWN_ERROR
    assert err.request_id == "unit-rid"
    assert err.status_code == 502


def test_record_error_preserves_chat_error_category():
    from starlette.requests import Request

    from jarvis_backend.observability import record_error, request_id_var

    request = Request(
        {"type": "http", "method": "GET", "path": "/x", "raw_path": b"/x",
         "headers": [], "query_string": b""}
    )
    token = request_id_var.set("unit-rid-2")
    try:
        err = record_error(
            request,
            ChatError(ErrorCategory.RATE_LIMITED, "slow down", request_id="pre-existing"),
        )
    finally:
        request_id_var.reset(token)

    # The correlation id wins so client + server logs line up.
    assert err.category == ErrorCategory.RATE_LIMITED
    assert err.request_id == "unit-rid-2"
