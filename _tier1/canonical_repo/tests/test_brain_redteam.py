"""Phase 8 tests: Security red-team + no-fabrication audit (Phase 8 §31, §39).

These tests assert the architectural invariants that defend the control plane:

* secrets never reach the Brain (observed_results, model-view, context pack),
* the orchestrator never invokes shell / DB / provider SDKs directly — it only
  dispatches through :class:`ToolRegistry`,
* nonexistent capabilities are denied, never fabricated,
* a Brain cannot declare completion by fiat — completion is decided by real
  evidence against completion_conditions,
* when the Brain model is unreachable the adapter degrades honestly (ASK_USER),
  never inventing a plan.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from jarvis_brain.adapters import (
    DeterministicBrainAdapter, ModelBrainAdapter, build_brain_adapter,
)
from jarvis_brain.audit import EventType  # noqa: F401  (sanity import)
from jarvis_brain.budget import TaskBudget
from jarvis_brain.contract import (
    AutonomyLevel, BrainInput, BrainIntent, BrainOutput, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode, Plan, PlanDecision,
    PlanStep,
)
from jarvis_brain.orchestrator import BrainOrchestrator
from jarvis_brain.plan_validator import PlanValidator
from research_engine.capability_tools import build_capability_registry
from research_engine.models import ToolResult
from research_engine.tool_registry import ToolRegistry, ToolContext, scrub_secrets

pytestmark = pytest.mark.brain

SECRET = "sk-live-REDACTME-9f3a7c1e8b2d"
SECRET_ERR = "password=hunter2-SECRET-value"


@pytest.fixture
def brain_registry():
    return build_capability_registry()


@pytest.fixture
def brain_validator(brain_registry):
    return PlanValidator(brain_registry)


def _proposal(cap, args, cond):
    return BrainOutput(
        intent=BrainIntent(domain="general", task="t",
                           confidence=ConfidenceState.SUFFICIENT_INFORMATION),
        plan=Plan(summary="p", steps=[PlanStep(id="s1", capability=cap,
                                               summary="s", args=args)]),
        capability_requests=[CapabilityRequest(capability=cap, args=args,
                                               reason="x")],
        questions_for_user=[],
        completion_conditions=[CompletionCondition(type=cond, target="t",
                                                    expected=True)],
        confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
        summary="p",
    )


# ---------------------------------------------------------------------------
# Boundary: scrub_secrets redacts credential-shaped material
# ---------------------------------------------------------------------------
def test_scrub_secrets_redacts_api_key():
    out, red = scrub_secrets(f"api_key={SECRET} foo")
    assert SECRET not in out
    assert red is True
    assert "REDACTED" in out


def test_scrub_secrets_redacts_token_and_password():
    out, red = scrub_secrets(f"token={SECRET} password=hunter2")
    assert SECRET not in out
    assert "REDACTED" in out
    assert red is True


# ---------------------------------------------------------------------------
# Boundary: ToolRegistry scrubs before returning a ToolResult
# ---------------------------------------------------------------------------
def test_registry_scrubs_secret_from_tool_result():
    reg = ToolRegistry()

    class _LeakyTool:
        name = "leaky"
        required_permissions = ()
        risk = "read"

        async def invoke(self, args, ctx):
            return ToolResult(tool_id="t", name="leaky", success=True,
                              result=f"config dump: api_key={SECRET}",
                              error=f"token={SECRET_ERR}")

    reg._tools["leaky"] = _LeakyTool()
    ctx = ToolContext(user_id="alice", permissions=set(), principal={},
                      request_id="r1", budgets=None, research_dir=None)
    r = asyncio.run(reg.invoke("leaky", {}, ctx))
    assert SECRET not in r.result
    assert SECRET_ERR not in r.error
    assert r.redacted_secrets is True


# ---------------------------------------------------------------------------
# Boundary: orchestrator / adapter source never wires shell / DB / SDKs
# ---------------------------------------------------------------------------
def _source_for(module):
    return open(module.__file__, encoding="utf-8").read()


def test_orchestrator_has_no_shell_or_db_invocation():
    import jarvis_brain.orchestrator as _o
    src = _source_for(_o)
    for forbidden in ("import subprocess", "os.system", "os.popen", "os.exec",
                       "Popen(", "powershell", "cmd.exe", "os.remove",
                       "shutil.rmtree", "sqlite3.connect", "psycopg2"):
        assert forbidden not in src, f"orchestrator source contains {forbidden!r}"


def test_adapters_have_no_shell_or_db_invocation():
    import jarvis_brain.adapters as _a
    src = _source_for(_a)
    for forbidden in ("import subprocess", "os.system", "os.popen", "os.exec",
                       "Popen(", "powershell", "cmd.exe", "sqlite3.connect",
                       "psycopg2", "openai.OpenAI", "boto3"):
        assert forbidden not in src


# ---------------------------------------------------------------------------
# Red-team: secrets injected into a tool result never reach the Brain's
# observed_results feed (defense-in-depth scrub of the model-view feed).
# ---------------------------------------------------------------------------
def test_observed_results_sanitized_before_brain(brain_registry, brain_validator):
    captured: list[dict] = []

    class _SpyBrain:
        async def propose(self, brain_input, budget):
            # Record exactly what the Brain is given to reason over.
            captured.append({
                "observed_results": list(brain_input.task_state.get(
                    "observed_results", [])),
            })
            return _proposal("project.inspect", {}, "tests_passed")

    registry = brain_registry
    orig_invoke = registry.invoke

    async def spy_invoke(name, args, ctx):
        r = await orig_invoke(name, args, ctx)
        if name == "project.inspect" and r.success:
            # Simulate a buggy tool that leaked a secret into its result.
            r.result = f"raw dump api_key={SECRET} token={SECRET_ERR} matches"
            r.error = SECRET_ERR
        return r

    registry.invoke = spy_invoke

    # Force a replan so the Brain's propose runs with observed_results populated.
    budget = TaskBudget(max_replans=1, max_plan_iterations=4, max_retries=1,
                        max_cost=100.0, max_execution_time=60.0)
    orch = BrainOrchestrator(_SpyBrain(), registry, brain_validator, budget=budget)
    res = orch.run_sync("look up sky color")

    assert res.status in ("FAILED", "COMPLETED", "BUDGET_EXCEEDED")
    assert len(captured) >= 2  # initial propose + >=1 replan propose
    blob = json.dumps(captured)
    assert SECRET not in blob, "raw secret leaked into Brain observed_results"
    assert SECRET_ERR not in blob, "raw secret leaked into Brain observed_results"


# ---------------------------------------------------------------------------
# No-fabrication: a Brain cannot force COMPLETED; evidence gates completion.
# ---------------------------------------------------------------------------
def test_brain_cannot_fabricate_completion_on_failed_tool(brain_registry,
                                                          brain_validator):
    # Brain claims 'answer_generated' but the tool FAILS -> must NOT complete.
    class _FailingBrain:
        async def propose(self, brain_input, budget):
            return _proposal("project.inspect", {}, "answer_generated")

    async def bad_invoke(name, args, ctx):
        return ToolResult(tool_id="t", name=name, success=False,
                          error="TOOL_UNAVAILABLE")

    registry = brain_registry
    registry.invoke = bad_invoke
    budget = TaskBudget(max_replans=0, max_retries=1)
    orch = BrainOrchestrator(_FailingBrain(), registry, brain_validator,
                             budget=budget)
    res = orch.run_sync("look up sky color")
    # A failed tool must never yield COMPLETED, regardless of brain claims.
    assert res.status != "COMPLETED"
    assert res.status in ("FAILED", "BUDGET_EXCEEDED")


# ---------------------------------------------------------------------------
# No-fabrication: ModelBrainAdapter degrades honestly when unreachable
# ---------------------------------------------------------------------------
def test_model_adapter_degrades_when_brain_unreachable(monkeypatch):
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
    monkeypatch.setenv("JARVIS_BRAIN_BACKEND", "stub")

    class _FakeClient:
        def chat(self, messages, timeout=60, **_kwargs):
            class R:
                content = "[brain-stub] hello"
                usage = None
            return R()

    adapter = ModelBrainAdapter(_FakeClient())
    bi = BrainInput(
        request="greet me", context={}, available_capabilities=[],
        execution_mode=ExecutionMode.ONLINE.value, user_id="u",
        autonomy=AutonomyLevel.AUTONOMOUS.value, budget=TaskBudget(),
    )
    out = asyncio.run(adapter.propose(bi, TaskBudget()))
    # Honest: no fabricated plan, ASK_USER, offline label.
    assert out.capability_requests == []
    assert out.confidence_state == ConfidenceState.ASK_USER
    assert out.provenance.get("offline") is True


def test_brain_health_probe_normalizes_versioned_endpoint(monkeypatch):
    import json
    import urllib.request
    from jarvis_brain.adapters import _health_available

    requested = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"available": True, "stub": False}).encode()

    def _urlopen(url, timeout):
        requested.append((url, timeout))
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)

    assert _health_available("http://127.0.0.1:8011/v1")
    assert requested == [("http://127.0.0.1:8011/health", 3)]


def test_model_adapter_uses_runtime_model_provenance(monkeypatch):
    import json

    import jarvis_brain.adapters as adapters

    class _FakeClient:
        def chat(self, _messages, timeout=60, **_kwargs):
            class _Response:
                content = json.dumps({**BrainOutput().to_dict(), "model_ref": "gpt-4"})
                usage = None

            return _Response()

    monkeypatch.setattr(
        adapters,
        "_probe_brain",
        lambda: adapters.BrainAvailability(
            available=True,
            stub=False,
            backend="remote",
            model="nvidia/nemotron-3-ultra-550b-a55b",
            provider="nvidia",
        ),
    )
    adapter = ModelBrainAdapter(_FakeClient())

    output = asyncio.run(adapter.propose(BrainInput(request="hello"), None))

    assert output.model_ref == "nvidia/nemotron-3-ultra-550b-a55b"
    assert output.provenance["provider"] == "nvidia"


# ---------------------------------------------------------------------------
# Red-team: nonexistent capability is denied, not fabricated
# ---------------------------------------------------------------------------
def test_nonexistent_capability_denied_by_validator(brain_registry, brain_validator):
    bo = BrainOutput(
        intent=BrainIntent(domain="g", task="t",
                           confidence=ConfidenceState.SUFFICIENT_INFORMATION),
        plan=Plan(summary="p", steps=[PlanStep(id="s1",
                                               capability="nope.does.not.exist",
                                               summary="s", args={})]),
        capability_requests=[CapabilityRequest(capability="nope.does.not.exist",
                                               args={}, reason="x")],
        questions_for_user=[],
        completion_conditions=[CompletionCondition(type="answer_generated")],
        confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
    )
    res = brain_validator.validate(bo.to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED
    assert "nope.does.not.exist" not in res.authorized_capabilities


# ---------------------------------------------------------------------------
# No-fabrication: offline deterministic adapter never claims completion
# ---------------------------------------------------------------------------
def test_offline_adapter_never_declares_completion():
    saved = {k: os.environ.pop(k, None)
             for k in ("JARVIS_BRAIN_ENDPOINT", "JARVIS_BRAIN_BACKEND",
                       "JARVIS_BRAIN_MODEL")}
    try:
        adapter = build_brain_adapter()  # -> DeterministicBrainAdapter (unreachable)
        assert isinstance(adapter, DeterministicBrainAdapter)
        bi = BrainInput(
            request="research x", context={}, available_capabilities=[],
            execution_mode=ExecutionMode.OFFLINE.value, user_id="u",
            autonomy=AutonomyLevel.AUTONOMOUS.value, budget=TaskBudget(),
        )
        out = asyncio.run(adapter.propose(bi, TaskBudget()))
        # Never fabricates: insufficient evidence, offline provenance, and any
        # completion_condition is evidence-gated (never a self-declared "done").
        assert out.confidence_state == ConfidenceState.INSUFFICIENT_EVIDENCE
        assert out.provenance.get("offline") is True
        assert all(c.type == "evidence_sufficient" for c in out.completion_conditions)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
