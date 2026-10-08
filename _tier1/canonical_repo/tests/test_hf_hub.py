"""Unit tests for the HF Hub registry module (offline; mocked network)."""
import pytest

from providers.huggingface import hub as h
from providers.health import HealthStatus


def test_capabilities_for_pipeline_known_and_unknown():
    assert "chat" in {c.value for c in h.capabilities_for_pipeline("text-generation")}
    assert h.capabilities_for_pipeline("totally-made-up") == frozenset()


def test_hf_auth_probe_maps_statuses(monkeypatch):
    cases = [
        (None, HealthStatus.HEALTHY),
        (h.HubAuthError("401"), HealthStatus.AUTHENTICATION_FAILED),
        (h.HubForbiddenError("403"), HealthStatus.FORBIDDEN),
        (h.HubRateLimitedError("429"), HealthStatus.RATE_LIMITED),
        (h.HubTimeoutError("timeout"), HealthStatus.TIMEOUT),
        (h.HubUnavailableError("down"), HealthStatus.UNAVAILABLE),
    ]
    for raise_me, expected in cases:
        def _fake(url, headers=None, timeout=15.0, _exc=raise_me):
            if _exc is not None:
                raise _exc
            return 200, {"type": "user", "name": "x"}

        monkeypatch.setattr(h, "_request_json", _fake)
        got = h.hf_auth_probe("tok")
        assert got.status is expected, f"{raise_me} -> {got.status} (want {expected})"


def test_hf_auth_probe_network_error_is_unavailable(monkeypatch):
    def _boom(url, headers=None, timeout=15.0):
        raise h.HubUnavailableError("name resolution failed")

    monkeypatch.setattr(h, "_request_json", _boom)
    assert h.hf_auth_probe("tok").status is HealthStatus.UNAVAILABLE


def test_discover_models_parses_rows(monkeypatch):
    rows = [
        {"id": "org/cool-model", "pipeline_tag": "text-generation",
         "downloads": 99, "likes": 3, "tags": ["x"]},
        {"id": "org/other", "pipeline_tag": "image-classification", "downloads": 1, "likes": 0},
    ]

    def _fake(url, headers=None, timeout=15.0):
        return 200, rows

    monkeypatch.setattr(h, "_request_json", _fake)
    infos = h.discover_models(token=None, limit=5)
    assert len(infos) == 2
    assert infos[0].model_id == "org/cool-model"
    assert "chat" in {c.value for c in infos[0].capabilities}
    assert h.capabilities_for_pipeline("text-generation")


def test_discover_models_clamps_limit(monkeypatch):
    rows = [{"id": f"o/m{i}"} for i in range(50)]

    def _fake(url, headers=None, timeout=15.0):
        assert "limit=10" in url
        return 200, rows

    monkeypatch.setattr(h, "_request_json", _fake)
    infos = h.discover_models(token=None, limit=10)
    assert len(infos) == 10  # clamped and sliced
    assert infos[0].sha == ""  # list API omits sha; honest empty


def test_whoami_token_returns_payload(monkeypatch):
    def _fake(url, headers=None, timeout=15.0):
        return 200, {"type": "user", "name": "Reyvic-254"}

    monkeypatch.setattr(h, "_request_json", _fake)
    status, payload = h.whoami_token("tok")
    assert status == 200
    assert payload["name"] == "Reyvic-254"