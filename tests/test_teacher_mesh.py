"""Unit tests for the Teacher Mesh (offline; no provider calls)."""
import pytest

from providers.base import Capability, Message, ProviderRequest
from providers.health import HealthStatus, ProviderHealth
from providers.models import ProviderModel
from teacher_mesh.mesh import (
    TeacherCallError,
    TeacherMesh,
    TeacherUnavailable,
)


def _pm(model_id):
    return ProviderModel(
        provider="fake",
        model_id=model_id,
        name=model_id,
        deployment="hosted",
        context_length=0,
        capabilities={Capability.CHAT},
        pricing_per_1k=(None, None),
        cost_class="medium",
        privacy_class="public",
        latency_class="low",
        metadata={},
    )


class FakeAdapter:
    provider_id = "fake"
    display_name = "Fake"
    configured = True

    def __init__(self, tag, *, healthy=True, reply="42", fail=False):
        self.tag = tag
        self._healthy = healthy
        self._reply = reply
        self._fail = fail
        self.default_model = None
        self.models = [_pm(f"{tag}")]
        self.calls = 0

    def health(self, force=False):
        if self._healthy:
            return ProviderHealth(provider="fake", status=HealthStatus.HEALTHY, detail="ok")
        return ProviderHealth(provider="fake", status=HealthStatus.OFFLINE)

    def chat(self, request: ProviderRequest):
        self.calls += 1
        if self._fail:
            raise RuntimeError("backend 429 quota")
        return _FakeResp(self._reply)


class _FakeResp:
    def __init__(self, text):
        self.text = text


def _mesh(adapters):
    return TeacherMesh(adapters=adapters, include_local_jarvis=False, health_refresh_ms=0)


def test_select_requires_healthy_teacher():
    mesh = _mesh({"fake": FakeAdapter("a", healthy=False)})
    with pytest.raises(TeacherUnavailable):
        mesh.select()


def test_solve_from_healthy_teacher():
    mesh = _mesh({"fake": FakeAdapter("a", reply="def main(): pass")})
    mesh.refresh(force=True)
    res = mesh.solve({"question": "write a function"})
    assert res["solution"] == "def main(): pass"


def test_fallback_skips_failing_teacher():
    a = FakeAdapter("a", reply="first", fail=True)
    b = FakeAdapter("b", reply="second")
    mesh = _mesh({"fake": a, "other": b})
    mesh.refresh(force=True)
    res = mesh.solve({"question": "q"})
    assert res["solution"] == "second" or res["solution"] == "first"
    assert res["teacher_failures"], "a failure should be recorded"


def test_all_teachers_fail_raises_call_error():
    mesh = _mesh({"a": FakeAdapter("x", fail=True), "b": FakeAdapter("y", fail=True)})
    mesh.refresh(force=True)
    with pytest.raises(TeacherCallError):
        mesh.solve({"question": "q"})


def test_compare_solutions_converged_when_identical():
    a = FakeAdapter("a", reply="  42  ")
    b = FakeAdapter("b", reply="42")
    mesh = _mesh({"a": a, "b": b})
    mesh.refresh(force=True)

    def verifier(problem, solution):
        return {"outcome": "VERIFIED", "evidence": solution}

    res = mesh.compare_solutions(
        {"question": "q"}, "42", "fake/a", "42", "other/b", verifier=verifier
    )
    assert res["outcome"] == "CONVERGED"


def test_mesh_status_counts():
    mesh = _mesh({"a": FakeAdapter("a"), "b": FakeAdapter("b", healthy=False)})
    mesh.refresh(force=True)
    status = mesh.mesh_status()
    assert status["total"] == 2
    assert status["healthy"] == 1