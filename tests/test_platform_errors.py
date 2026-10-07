"""Tests for the platform structured error contract (spec Part B).

Runs against a *minimal* FastAPI app wired with ``install_observability`` so
the tests are fast and isolated from the platform's provider fabric bootstrap
(which performs live provider checks).  The contract under test is the
``StarletteHTTPException`` handler: unknown routes no longer return
``{"detail":"Not Found"}`` and every error carries a request id.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis_backend.observability import install_observability

pytestmark = pytest.mark.brain


def _make_app() -> FastAPI:
    app = FastAPI()
    install_observability(app)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/auth-fail")
    async def auth_fail():
        raise HTTPException(status_code=401, detail="bad creds")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="nope")

    @app.get("/rate")
    async def rate():
        raise HTTPException(status_code=429, detail="slow down")

    return app


@pytest.fixture(scope="module")
def client():
    app = _make_app()
    # No `with` block -> lifespan/startup is not triggered (no fabric bootstrap).
    return TestClient(app)


class TestStructuredErrorContract:
    def test_404_is_not_detail_not_found(self, client):
        r = client.get("/does/not/exist")
        assert r.status_code == 404
        body = r.json()
        assert "detail" not in body  # the old generic shape is gone
        assert body["error"]["code"] == "ROUTE_NOT_FOUND"
        assert body["error"]["message"] == "The requested API route does not exist."
        assert body["error"]["path"] == "/does/not/exist"
        assert body["error"]["method"] == "GET"
        assert body["error"]["documentation"] == "/docs"

    def test_error_carries_request_id(self, client):
        r = client.get("/another/missing/route")
        body = r.json()
        rid = body["error"]["request_id"]
        assert rid  # non-empty correlation id
        assert r.headers.get("X-Request-ID") == rid

    def test_request_id_is_unique_per_request(self, client):
        r1 = client.get("/a")
        r2 = client.get("/b")
        assert r1.json()["error"]["request_id"] != r2.json()["error"]["request_id"]

    def test_request_id_propagated_when_client_supplies_it(self, client):
        r = client.get("/missing", headers={"X-Request-ID": "my-trace-123"})
        assert r.headers.get("X-Request-ID") == "my-trace-123"
        assert r.json()["error"]["request_id"] == "my-trace-123"

    def test_405_structured(self, client):
        r = client.put("/ok")
        assert r.status_code == 405
        assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"

    def test_401_structured(self, client):
        r = client.get("/auth-fail")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "AUTHENTICATION_ERROR"

    def test_403_structured(self, client):
        r = client.get("/forbidden")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "AUTHORIZATION_ERROR"

    def test_429_structured_and_retryable(self, client):
        r = client.get("/rate")
        assert r.status_code == 429
        err = r.json()["error"]
        assert err["code"] == "RATE_LIMITED"
        assert err["retryable"] is True

    def test_ok_response_also_has_request_id(self, client):
        r = client.get("/ok")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        assert r.json() == {"ok": True}
