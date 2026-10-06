"""Provider tests: Local fallback + GeminiProvider with an injected fake client.

No real network/Gemini calls are made: the Gemini provider's SDK call is
replaced by a fake client so retries, timeouts, malformed-JSON rejection and
prompt-injection resistance are exercised deterministically.
"""
import asyncio
import dataclasses
import json

import pytest

from training_advisor import AdvisorResult, AdvisorStatus, GeminiProvider, LocalProvider
from training_advisor.schemas import MetricValue, RecommendationAction, TrainingMetricsSnapshot
from training_advisor.providers import _cache_key


# ---------------------------------------------------------------------------
# Fake Gemini SDK client
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, behavior):
        self._behavior = behavior
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        b = self._behavior
        if isinstance(b, BaseException):
            raise b
        if callable(b):
            return _FakeResp(b())
        return _FakeResp(b)


class _FakeClient:
    def __init__(self, behavior):
        self.models = _FakeModels(behavior)


_VALID_JSON = json.dumps({
    "analysis": "Gemini analysis text",
    "status": "warning",
    "recommendations": [
        {"id": "g1", "action": "keep_lr", "reason": "stable",
         "confidence": 0.85, "expected_effect": "no change", "risk": "low"},
    ],
    "anomalies": [],
    "metrics_summary": {"n_snapshots": 3},
    "provenance": {"created_at": "2024-01-01T00:00:00", "run_id": "r"},
    "created_at": "2024-01-01T00:00:00",
})


def _snaps(n=3):
    out = []
    for i in range(n):
        out.append(TrainingMetricsSnapshot(
            captured_at=f"t{i}", run_id="r", model="m", model_name="M",
            architecture="t", step=MetricValue.observed(i, "loop"),
            loss=MetricValue.observed(1.0 - i * 0.1, "loop")))
    return out


class TestLocalProvider:
    def test_available(self, cfg):
        assert LocalProvider(cfg).is_available() is True

    def test_empty_history_unknown(self, cfg):
        prov = LocalProvider(cfg)
        res = asyncio.run(prov.analyze([], [], cfg, {}))
        assert res.provider == "local"
        assert res.status == AdvisorStatus.UNKNOWN
        assert any(r.action == RecommendationAction.COLLECT_METRICS.value for r in res.recommendations)


class TestGeminiProvider:
    def test_uses_injected_client(self, cfg_key):
        prov = GeminiProvider(cfg_key, client=_FakeClient(_VALID_JSON))
        res = asyncio.run(prov.analyze(_snaps(), [], cfg_key, {}))
        assert res.provider == "gemini"
        assert res.status == AdvisorStatus.WARNING
        assert res.recommendations[0].action == "keep_lr"
        assert prov._client.models.calls == 1

    def test_malformed_json_raises(self, cfg_key):
        prov = GeminiProvider(cfg_key, client=_FakeClient("<<<not json>>>"))
        with pytest.raises(Exception):
            asyncio.run(prov.analyze(_snaps(), [], cfg_key, {}))

    def test_prompt_injection_invalid_shape_raises(self, cfg_key):
        bad = json.loads(_VALID_JSON)
        del bad["recommendations"][0]["reason"]
        prov = GeminiProvider(cfg_key, client=_FakeClient(json.dumps(bad)))
        with pytest.raises(Exception):
            asyncio.run(prov.analyze(_snaps(), [], cfg_key, {}))

    def test_fenced_json_is_tolerated(self, cfg_key):
        fenced = "```json\n" + _VALID_JSON + "\n```"
        prov = GeminiProvider(cfg_key, client=_FakeClient(fenced))
        res = asyncio.run(prov.analyze(_snaps(), [], cfg_key, {}))
        assert res.provider == "gemini"

    def test_timeout_retries_then_raises(self, cfg_key):
        fast = dataclasses.replace(cfg_key, max_retries=1, base_backoff_seconds=0.0,
                                   timeout_seconds=0.2)
        import time as _t

        def _sleep_forever():
            _t.sleep(5.0)
            return "x"  # unreachable

        prov = GeminiProvider(fast, client=_FakeClient(_sleep_forever))
        with pytest.raises(Exception):
            asyncio.run(prov.analyze(_snaps(), [], fast, {}))


class TestOrchestratorFallback:
    def test_gemini_failure_falls_back_to_local(self, ta_key, cfg_key):
        ta_key.primary = GeminiProvider(cfg_key, client=_FakeClient("<<<junk>>>"))
        res = asyncio.run(ta_key.analyze(force=True))
        assert res.provider == "local"
        assert res.status in {AdvisorStatus.UNKNOWN, AdvisorStatus.WARNING, AdvisorStatus.HEALTHY}

    def test_gemini_disabled_uses_local(self, ta):
        res = asyncio.run(ta.analyze(force=True))
        assert res.provider == "local"


def test_cache_key_is_stable():
    a = _snaps(3)
    assert _cache_key(a) == _cache_key(_snaps(3))
    assert _cache_key(a) != _cache_key(_snaps(4))
