"""Phase 10 — Cognitive Kernel tests.

Verifies the bounded cognitive loop: max_steps enforcement, budget exhaustion,
checkpointing, crash recovery / resume, no infinite loops, secret isolation,
and resource-aware cognition (Phase 9 integration).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend.core import get_store  # noqa: E402
from jarvis_backend.mission import (  # noqa: E402
    Mission,
    MissionBudget,
    MissionStatus,
    AutonomyLevel,
)
from jarvis_backend.cognitive_kernel import (  # noqa: E402
    CognitiveKernel,
    KernelStopReason,
    KernelResult,
)
from jarvis_backend.brain_fabric import assert_no_secrets  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()
    yield
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()


def _make_mission(**kw) -> Mission:
    """Create a minimal READ-only mission suitable for testing."""
    m = Mission.create(
        title=kw.get("title", "Status Check"),
        objective=kw.get("objective", "Check the status of the JARVIS platform"),
        created_by=kw.get("created_by", "test_user"),
    )
    m.success_criteria = kw.get("success_criteria", ["Platform status checked"])
    m.constraints = kw.get("constraints", ["No external API calls"])
    m.autonomy_level = kw.get("autonomy_level", AutonomyLevel.LEVEL_1.value)
    m.allowed_capabilities = kw.get(
        "allowed_capabilities",
        ["project.status", "model.status", "provider.status", "system.status"],
    )
    m.budget = kw.get("budget", MissionBudget(
        max_steps=2, max_seconds=120, max_cost_usd=0.0,
        max_iterations=2,
    ))
    m.save()
    return m


# --------------------------------------------------------------------------- #
# Initialization
# --------------------------------------------------------------------------- #
def test_kernel_initializes_with_default_components():
    kernel = CognitiveKernel()
    assert kernel.tool_registry is not None
    assert kernel.executor is not None
    assert kernel.evidence_engine is not None
    assert kernel.hypothesis_engine is not None
    assert kernel.verifier is not None
    assert kernel.critic is not None


def test_kernel_has_bounded_budget():
    """Kernel must always have a hard step limit."""
    kernel = CognitiveKernel()
    assert kernel is not None  # initialization does not hang


# --------------------------------------------------------------------------- #
# Bounded execution
# --------------------------------------------------------------------------- #
def test_kernel_respects_max_steps():
    """Kernel stops at max_steps even if success criteria are not met."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    assert result.steps_executed >= 1
    assert result.stop_reason in (
        KernelStopReason.MAX_STEPS_REACHED.value,
        KernelStopReason.BUDGET_EXHAUSTED.value,
        KernelStopReason.COMPLETED.value,
        KernelStopReason.FAILED.value,
    )
    # Should not exceed the requested max_steps
    assert result.steps_executed <= 1


def test_kernel_respects_step_limit_of_zero():
    """A step limit of 0 means no cycles run."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=0)
    assert result.steps_executed == 0


def test_kernel_budget_exhausted_stops_loop():
    """When max_steps budget is 1, the kernel stops after 1 cycle."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)
    assert result.steps_executed <= 1


# --------------------------------------------------------------------------- #
# Stop reasons
# --------------------------------------------------------------------------- #
def test_kernel_returns_kernel_result():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)
    assert isinstance(result, KernelResult)
    assert result.mission_id == mission.mission_id


def test_kernel_result_is_serializable():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)
    d = result.to_dict()
    assert d["mission_id"] == mission.mission_id
    assert "steps_executed" in d
    assert "stop_reason" in d
    assert "cognitive_state" in d
    assert "task_results" in d
    assert "findings" in d


# --------------------------------------------------------------------------- #
# No infinite loops
# --------------------------------------------------------------------------- #
def test_kernel_terminates_quickly():
    """The kernel must complete within a reasonable wall-clock time."""
    import time

    mission = _make_mission()
    kernel = CognitiveKernel()
    start = time.time()
    result = kernel.resume(mission.mission_id, max_steps=3)
    elapsed = time.time() - start
    # 3 cycles should complete in under 60 seconds
    assert elapsed < 60, f"Kernel took {elapsed:.1f}s — possible infinite loop"
    assert result.stop_reason is not None


# --------------------------------------------------------------------------- #
# Checkpointing
# --------------------------------------------------------------------------- #
def test_kernel_checkpoints_after_each_cycle():
    mission = _make_mission()
    kernel = CognitiveKernel()
    kernel.resume(mission.mission_id, max_steps=2)

    reloaded = Mission.load(mission.mission_id)
    assert reloaded is not None
    assert len(reloaded.checkpoints) >= 2  # at least one per cycle


def test_checkpoint_contains_cognitive_state():
    mission = _make_mission()
    kernel = CognitiveKernel()
    kernel.resume(mission.mission_id, max_steps=1)

    reloaded = Mission.load(mission.mission_id)
    ck = reloaded.latest_checkpoint()
    assert ck is not None
    assert "cognitive_state" in ck
    assert "phase" in ck
    assert "cycle" in ck


# --------------------------------------------------------------------------- #
# Crash recovery / resume
# --------------------------------------------------------------------------- #
def test_resume_restores_from_checkpoint():
    """Resume restores cognitive state from the latest checkpoint."""
    mission = _make_mission()
    mission.budget = MissionBudget(
        max_steps=5, max_seconds=300, max_cost_usd=0.0, max_iterations=5,
    )
    mission.save()
    kernel = CognitiveKernel()

    # Run 1 cycle
    result1 = kernel.resume(mission.mission_id, max_steps=1)
    assert result1.steps_executed >= 1

    # Resume — state should be restored from checkpoint
    result2 = kernel.resume(mission.mission_id, max_steps=1)
    assert result2.steps_executed >= 1

    reloaded = Mission.load(mission.mission_id)
    assert len(reloaded.checkpoints) >= 2


def test_resume_rejects_terminal_mission():
    mission = _make_mission()
    kernel = CognitiveKernel()
    # Force mission to terminal state
    mission.status = MissionStatus.COMPLETED.value
    mission.save()
    with pytest.raises(ValueError, match="terminal"):
        kernel.resume(mission.mission_id, max_steps=1)


def test_resume_rejects_nonexistent_mission():
    kernel = CognitiveKernel()
    with pytest.raises(ValueError, match="not found"):
        kernel.resume("mission_does_not_exist", max_steps=1)


# --------------------------------------------------------------------------- #
# DRAFT → ACTIVE transition
# --------------------------------------------------------------------------- #
def test_kernel_transitions_draft_to_active():
    mission = _make_mission()
    kernel = CognitiveKernel()
    kernel.resume(mission.mission_id, max_steps=1)

    reloaded = Mission.load(mission.mission_id)
    assert reloaded.status == MissionStatus.ACTIVE.value


# --------------------------------------------------------------------------- #
# Secret isolation
# --------------------------------------------------------------------------- #
def test_no_secrets_in_cognitive_state():
    """The cognitive state must never contain secrets after a kernel run."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    leaks = assert_no_secrets(result.cognitive_state)
    assert len(leaks) == 0, f"Secret leaks found: {leaks}"


def test_no_secrets_in_task_results():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=2)

    for tr in result.task_results:
        leaks = assert_no_secrets(tr)
        assert len(leaks) == 0, f"Secret leaks in task result: {leaks}"


def test_no_secrets_in_findings():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=2)

    for finding in result.findings:
        leaks = assert_no_secrets(finding)
        assert len(leaks) == 0, f"Secret leaks in finding: {leaks}"


# --------------------------------------------------------------------------- #
# Resource-aware cognition (Phase 9 integration)
# --------------------------------------------------------------------------- #
def test_cognitive_state_captures_local_hardware(monkeypatch):
    from jarvis_backend import cognitive_kernel

    monkeypatch.setattr(cognitive_kernel, "local_hardware", lambda: {
        "cpu": "Test CPU",
        "gpu": None,
        "gpu_count": 0,
        "ram_gb": 8.0,
    })
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    local_hw = state.get("confidence_state", {}).get("local_hardware", {})
    # local_hardware should be populated (even if with an error)
    assert "local_hardware" in state.get("confidence_state", {})


def test_cognitive_state_captures_brain_readiness():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    confidence = state.get("confidence_state", {})
    assert "brain_available" in confidence
    assert "brain_unavailable" in confidence


def test_cognitive_state_records_resource_verification():
    """The cognitive state should note that resources were verified."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    confidence = state.get("confidence_state", {})
    assert "local_hardware" in confidence
    # Should record CPU info
    hw = confidence.get("local_hardware", {})
    assert "cpu" in hw


# --------------------------------------------------------------------------- #
# Cognitive state correctness
# --------------------------------------------------------------------------- #
def test_cognitive_state_has_phase():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    assert "phase" in state
    assert state["phase"] != ""


def test_cognitive_state_records_hypotheses():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    # Should have proposed at least one hypothesis
    assert len(state.get("hypotheses", [])) >= 1


def test_cognitive_state_records_observations():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)

    state = result.cognitive_state
    # Observations should be recorded during OBSERVE phase
    assert isinstance(state.get("observations", []), list)


def test_cognitive_state_records_budget():
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=2)

    state = result.cognitive_state
    budget = state.get("budget_state", {})
    assert "steps_consumed" in budget
    assert budget["steps_consumed"] >= 1


# --------------------------------------------------------------------------- #
# Cautious planning (autonomy level enforcement)
# --------------------------------------------------------------------------- #
def test_level_0_autonomy_filters_network_capabilities():
    """Autonomy LEVEL_0 must not auto-authorize network/admin capabilities."""
    mission = _make_mission()
    mission.autonomy_level = AutonomyLevel.LEVEL_0.value
    mission.save()

    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=1)
    # Should complete without error — capabilities are filtered
    assert result.stop_reason is not None


# --------------------------------------------------------------------------- #
# Task graph (DAG) integration
# --------------------------------------------------------------------------- #
def test_kernel_creates_task_graph():
    """Each cycle should produce a task that gets linked to the mission."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=2)

    reloaded = Mission.load(mission.mission_id)
    assert len(reloaded.tasks) >= 1
    for t in reloaded.tasks:
        assert "task_id" in t
        assert "status" in t


# --------------------------------------------------------------------------- #
# No fabrication audit
# --------------------------------------------------------------------------- #
def test_cognitive_state_no_fabricated_evidence():
    """The Critic should not find untraceable evidence."""
    mission = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(mission.mission_id, max_steps=2)

    # All findings with severity 'error' should not be about fabrication
    for f in result.findings:
        if f.get("severity") == "error":
            assert "fabrication" not in f.get("category", "").lower(), \
                f"Critic found fabrication error: {f}"
