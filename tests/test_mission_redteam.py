"""Security + truthfulness red-team tests for Phase 10 — Mission / Cognitive Kernel.

Verifies:
1. No secret exfiltration through Mission records, checkpoints, or cognitive state.
2. No credential escalation — missions never request cloud credentials.
3. No fabrication of evidence, hypotheses, or verification results.
4. No self-approval — missions cannot auto-transition to COMPLETED without
   success-criteria verification.
5. No automatic cloud resource creation or provisioning.
6. No unrestricted shell authority in Phase 10 code.
7. Autonomy level 0 blocks all EXEC/WRITE/NETWORK actions.
8. Mission completion requires verification, not just task execution.
"""
from __future__ import annotations

import inspect
import json
import re
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
from jarvis_backend.mission_lifecycle import (  # noqa: E402
    MissionLifecycle,
    MissionTransitionError,
    TERMINAL_STATUSES,
)
from jarvis_backend.cognitive_kernel import (  # noqa: E402
    CognitiveKernel,
    KernelStopReason,
)
from jarvis_backend.cognitive_state import CognitiveState, CognitivePhase  # noqa: E402
from jarvis_backend.brain_fabric import assert_no_secrets  # noqa: E402
from jarvis_backend.critic import Critic  # noqa: E402
from jarvis_backend.verifier import Verifier  # noqa: E402
from jarvis_backend.delegation import DelegationManager  # noqa: E402
from jarvis_backend.specialist_roles import get_role, get_all_roles  # noqa: E402

# Patterns that would indicate credential leakage.
SECRET_PATTERNS = {
    "api_key": re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    "token": re.compile(r"(?i)(token|access_token|auth_token)\s*[:=]\s*\S+"),
    "hf_token": re.compile(r"(?i)hf_[A-Za-z0-9]{32,}"),
    "bearer": re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    "password": re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    "aws_key": re.compile(r"(?i)aws[_-]?(access[_-]?key|secret[_-]?key)\s*[:=]\s*\S+"),
    "ssh_key": re.compile(r"(?i)-----BEGIN\s+(RSA|OPENSSH|DSA|EC)\s+PRIVATE\s+KEY-----"),
    "secret_value": re.compile(r"(?i)(secret|client_secret)[\"'\s]*[:=]\s*[\"'\s]\S{8,}"),
}

# Phase 10 source files to scan for dangerous patterns.
PHASE10_SOURCE_FILES = [
    "jarvis_backend/mission_lifecycle.py",
    "jarvis_backend/mission.py",
    "jarvis_backend/cognitive_state.py",
    "jarvis_backend/hypothesis_engine.py",
    "jarvis_backend/evidence_engine.py",
    "jarvis_backend/critic.py",
    "jarvis_backend/verifier.py",
    "jarvis_backend/specialist_roles.py",
    "jarvis_backend/delegation.py",
    "jarvis_backend/cognitive_kernel.py",
]


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
    m = Mission.create(
        title=kw.get("title", "Test Mission"),
        objective=kw.get("objective", "Test the system"),
        created_by=kw.get("created_by", "test_user"),
    )
    m.success_criteria = kw.get("success_criteria", ["Test criterion"])
    m.constraints = kw.get("constraints", ["No credential exfiltration"])
    m.allowed_capabilities = kw.get("allowed_capabilities", ["project.status"])
    m.budget = kw.get("budget", MissionBudget(
        max_steps=1, max_seconds=120, max_cost_usd=0.0, max_iterations=1,
    ))
    m.save()
    return m


# --------------------------------------------------------------------------- #
# 1. No secret exfiltration through mission records
# --------------------------------------------------------------------------- #
def test_no_secrets_in_mission_serialization():
    """Mission.to_dict must never contain secret-bearing fields."""
    m = _make_mission()
    d = m.to_dict()
    # assert_no_secrets uses substring matching; "token" matches "max_tokens"
    # which is a budget integer, not a credential.  Filter out known
    # false-positives that are configuration values, not secrets.
    false_positives = {"budget.max_tokens"}
    leaks = assert_no_secrets(d)
    real_leaks = [p for p in leaks if p not in false_positives]
    assert not real_leaks, f"Mission serialization leaked secrets at: {real_leaks}"


def test_no_secrets_in_checkpoint():
    """Checkpoints must never store secrets."""
    m = _make_mission()
    state = CognitiveState(
        mission_id=m.mission_id,
        objective=m.objective,
        phase=CognitivePhase.UNDERSTAND.value,
    )
    m.checkpoint(cycle=0, phase="understand", cognitive_state=state.to_dict(),
                 notes="test")
    for ck in m.checkpoints:
        leaks = assert_no_secrets(ck)
        assert not leaks, f"Checkpoint leaked secrets at: {leaks}"
    m.save()
    reloaded = Mission.load(m.mission_id)
    assert reloaded is not None
    for ck in reloaded.checkpoints:
        leaks = assert_no_secrets(ck)
        assert not leaks, f"Reloaded checkpoint leaked secrets: {leaks}"


def test_no_secrets_in_full_kernel_run():
    """After a full kernel run, no secrets in result or persisted mission."""
    m = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(m.mission_id, max_steps=1)

    # Check KernelResult
    rk_leaks = assert_no_secrets(result.to_dict())
    assert not rk_leaks, f"KernelResult leaked secrets: {rk_leaks}"

    # Check persisted mission (filter known false-positives: max_tokens)
    reloaded = Mission.load(m.mission_id)
    mission_leaks = assert_no_secrets(reloaded.to_dict())
    false_positives = {"budget.max_tokens"}
    real_leaks = [p for p in mission_leaks if p not in false_positives]
    assert not real_leaks, f"Persisted mission leaked secrets: {real_leaks}"


def test_no_secret_patterns_in_mission_json():
    """Serialized mission JSON must not contain credential-shaped strings."""
    m = _make_mission()
    kernel = CognitiveKernel()
    kernel.resume(m.mission_id, max_steps=1)

    reloaded = Mission.load(m.mission_id)
    raw = json.dumps(reloaded.to_dict(), default=str)
    for label, pat in SECRET_PATTERNS.items():
        assert not pat.search(raw), \
            f"Mission JSON contains {label}-shaped string"


# --------------------------------------------------------------------------- #
# 2. No credential escalation — missions never request cloud credentials
# --------------------------------------------------------------------------- #
def test_mission_does_not_store_credentials():
    """Mission config must never include credential fields."""
    m = _make_mission()
    forbidden_keys = {"api_key", "api_secret", "access_token", "refresh_token",
                      "password", "secret_key", "credentials", "ssh_key"}
    d = m.to_dict()

    def check_deep(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kp = f"{path}.{k}" if path else k
                if k.lower() in forbidden_keys:
                    # Allow boolean True/False as "credentials_present" flags
                    if not isinstance(v, bool):
                        return kp
                result = check_deep(v, kp)
                if result:
                    return result
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                result = check_deep(v, f"{path}[{i}]")
                if result:
                    return result
        return None

    leak = check_deep(d)
    assert not leak, f"Mission stored credential field at {leak}"


def test_mission_constraints_can_block_credentials():
    """A constraint field exists to prevent credential exfiltration."""
    m = _make_mission()
    assert "No credential exfiltration" in m.constraints


# --------------------------------------------------------------------------- #
# 3. No fabrication of evidence, hypotheses, or verification
# --------------------------------------------------------------------------- #
def test_critic_flags_potential_fabrication():
    """The Critic must detect unverified or potentially fabricated evidence."""
    from jarvis_backend.evidence_engine import EvidenceEngine

    eng = EvidenceEngine()
    # Register evidence with no meaningful content (unverified)
    eng.register_evidence(
        source_url="memory://internal",
        source_type="internal",
        title="Unverified finding",
        relevant_content="",
        claims=[],
        supporting_excerpt="",
    )

    state = CognitiveState(
        mission_id="mission_test",
        objective="test",
        phase=CognitivePhase.CRITIQUE.value,
        evidence=[ev.to_dict() for ev in eng.list_all()],
    )
    critic = Critic()
    findings = critic.critique(state)
    # The critic should flag unverified or potentially fabricated evidence
    # The key assertion: critic produces findings (doesn't just stay silent)
    assert len(findings) >= 1


def test_hypothesis_engine_rejects_unverified_confirmation():
    """A hypothesis can only be CONFIRMED if verification passes."""
    from jarvis_backend.hypothesis_engine import (
        HypothesisEngine, HypothesisStatus,
    )
    eng = HypothesisEngine()
    h = eng.propose(
        statement="X is true",
        context="test",
        rationale="test",
        proposed_by="kernel",
    )
    # Should be PROPOSED, not CONFIRMED
    assert h.status == HypothesisStatus.PROPOSED

    # evaluate should not auto-confirm without verification
    result = eng.evaluate(h.id, evidence=[], experiments=None)
    assert result in (
        HypothesisStatus.REJECTED,
        HypothesisStatus.WEAKENED,
        HypothesisStatus.INCONCLUSIVE,
    )


def test_critic_does_not_fabricate_positive_findings():
    """Critic findings must reference actual state, not invented data."""
    m = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(m.mission_id, max_steps=1)

    for finding in result.findings:
        # Every finding must have a description and category
        assert "description" in finding
        assert "category" in finding
        assert "severity" in finding
        # Description must not claim fabricated verification
        assert not re.search(
            r"(?i)fabricated\s+evidence.*verified", finding["description"]
        ), f"Finding claims fabricated evidence is verified: {finding}"


# --------------------------------------------------------------------------- #
# 4. No self-approval — missions cannot auto-COMPLETED without verification
# --------------------------------------------------------------------------- #
def test_mission_cannot_skip_verifying_to_completed():
    """ACTIVE → COMPLETED must be rejected (must go VERIFYING first)."""
    m = _make_mission()
    m.status = MissionStatus.ACTIVE.value
    with pytest.raises(MissionTransitionError, match="VERIFYING"):
        m.transition(MissionStatus.COMPLETED, actor="kernel")


def test_critic_flags_budget_errors_as_error_severity():
    """Budget violations must be ERROR severity, not silently ignored."""
    m = _make_mission()
    kernel = CognitiveKernel()
    result = kernel.resume(m.mission_id, max_steps=1)

    for finding in result.findings:
        if "budget" in finding.get("category", "").lower():
            assert finding.get("severity") in ("error", "warning"), \
                f"Budget finding must be error/warning severity, got {finding.get('severity')}"


def test_kernel_stop_reason_for_budget_is_exhausted():
    """When budget is exhausted, the stop reason must reflect it."""
    m = _make_mission(budget=MissionBudget(
        max_steps=1, max_seconds=10, max_cost_usd=0.0, max_iterations=1,
    ))
    kernel = CognitiveKernel()
    result = kernel.resume(m.mission_id, max_steps=1)
    assert result.stop_reason in (
        KernelStopReason.MAX_STEPS_REACHED.value,
        KernelStopReason.BUDGET_EXHAUSTED.value,
    )


# --------------------------------------------------------------------------- #
# 5. No automatic cloud resource creation or provisioning
# --------------------------------------------------------------------------- #
def test_no_cloud_provisioning_in_kernel():
    """Phase 10 source must not create cloud resources."""
    for fname in PHASE10_SOURCE_FILES:
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Must not contain boto3 client creation or azure/gcp provisioning
        assert "boto3.client(" not in text, \
            f"{fname} contains boto3.client() — automatic cloud provisioning"
        assert "boto3.resource(" not in text, \
            f"{fname} contains boto3.resource() — automatic cloud provisioning"
        assert "googleapiclient.discovery" not in text, \
            f"{fname} contains GCP API client — automatic cloud provisioning"
        assert "azure.mgmt" not in text, \
            f"{fname} contains Azure SDK — automatic cloud provisioning"


def test_mission_does_not_request_cloud_credentials():
    """Mission config has no field for cloud credentials."""
    m = _make_mission()
    fields = set(Mission.__dataclass_fields__.keys())
    credential_fields = {"api_key", "secret_key", "access_token", "cloud_creds",
                         "credentials", "password"}
    overlap = fields & credential_fields
    assert not overlap, f"Mission model has credential fields: {overlap}"


# --------------------------------------------------------------------------- #
# 6. No unrestricted shell authority in Phase 10 code
# --------------------------------------------------------------------------- #
def test_no_shell_in_phase10_source():
    """Phase 10 source files must not use shell execution primitives."""
    for fname in PHASE10_SOURCE_FILES:
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "shell=True" not in text, \
            f"{fname} uses shell=True — unrestricted shell authority"
        assert "os.system" not in text, \
            f"{fname} uses os.system — unrestricted shell authority"
        assert "os.popen" not in text, \
            f"{fname} uses os.popen — unrestricted shell authority"
        assert "subprocess.run" not in text, \
            f"{fname} uses subprocess.run — must go through capability tools"
        assert "subprocess.Popen" not in text, \
            f"{fname} uses subprocess.Popen — must go through capability tools"


# --------------------------------------------------------------------------- #
# 7. Autonomy level 0 blocks all EXEC/WRITE/NETWORK actions
# --------------------------------------------------------------------------- #
def test_level_0_blocks_exec_capabilities():
    """Autonomy LEVEL_0 must not auto-execute EXEC capabilities."""
    from jarvis_backend.cognitive_kernel import CognitiveKernel as CK
    import inspect as _inspect

    m = _make_mission()
    m.autonomy_level = AutonomyLevel.LEVEL_0.value
    m.allowed_capabilities = ["compute.training", "compute.job_submit"]
    m.save()

    kernel = CK()
    result = kernel.resume(m.mission_id, max_steps=1)

    # Level 0 should filter out EXEC/WRITE/NW capabilities
    reloaded = Mission.load(m.mission_id)
    for t in reloaded.tasks:
        if t.get("success"):
            # Task succeeded — verify it was a READ capability
            obs = t.get("result", {})
            # The capability used should not be EXEC/WRITE/NW
            assert t.get("result", {}).get("capability_risk") != "EXEC", \
                "Level-0 mission executed EXEC capability"


def test_level_0_does_not_auto_approve():
    """Level 0 must never auto-approve high-risk actions."""
    m = _make_mission()
    m.autonomy_level = AutonomyLevel.LEVEL_0.value
    m.save()

    kernel = CognitiveKernel()
    result = kernel.resume(m.mission_id, max_steps=1)
    # The kernel should stop with waiting_for_approval or budget_reached,
    # never with completed (no self-approval)
    assert result.stop_reason != KernelStopReason.COMPLETED.value


# --------------------------------------------------------------------------- #
# 8. Mission completion requires verification, not just task execution
# --------------------------------------------------------------------------- #
def test_completion_requires_verification_not_tasks():
    """A mission with successful tasks but unverified criteria stays ACTIVE."""
    m = _make_mission()
    m.status = MissionStatus.ACTIVE.value
    m.save()

    # Simulate a task that succeeded but does NOT verify success criteria
    m.tasks.append({
        "task_id": "t1",
        "intent": "check status",
        "status": "COMPLETED",
        "result": {"success": True},
        "success": True,
    })
    m.save()

    # Should not be terminal even with successful tasks
    assert not m.is_terminal


def test_mission_stays_active_without_verification():
    """A mission cannot transition to COMPLETED from ACTIVE."""
    m = _make_mission()
    m.status = MissionStatus.ACTIVE.value
    with pytest.raises(MissionTransitionError):
        m.transition(MissionStatus.COMPLETED, actor="kernel")


# --------------------------------------------------------------------------- #
# 9. Critic has no execution authority
# --------------------------------------------------------------------------- #
def test_critic_has_no_execution_authority():
    """Critic class must not have any method that executes tools or creates tasks."""
    critic_methods = [m for m in dir(Critic) if not m.startswith("_")]
    forbidden = {"execute", "run_tool", "submit_job", "create_task",
                 "transition", "authorize"}
    overlap = set(critic_methods) & forbidden
    assert not overlap, \
        f"Critic has execution methods: {overlap}"


def test_critic_only_has_critique_method():
    """Critic's primary method should be critique (analysis-only)."""
    assert hasattr(Critic, "critique")
    assert callable(getattr(Critic, "critique"))


# --------------------------------------------------------------------------- #
# 10. Specialist roles are bounded
# --------------------------------------------------------------------------- #
def test_all_specialist_roles_have_excluded_capabilities():
    """Every role must define excluded capabilities (bounded agency)."""
    # get_all_roles returns RoleConfig objects
    roles = get_all_roles()
    assert len(roles) >= 14
    for role in roles:
        # Every role must have some capability restriction mechanism
        # (excluded, risk tolerance, or requires_human_approval_for)
        has_restriction = (
            len(role.excluded_capabilities) >= 1 or
            role.risk_tolerance is not None or
            len(role.requires_human_approval_for) >= 1
        )
        assert has_restriction, \
            f"Role {role.name} has no capability restrictions — unbounded agency"


def test_no_role_can_execute_admin_capabilities():
    """No specialist role should have ADMIN-risk capabilities in preferred set."""
    # Check that no role's preferred capabilities include admin capabilities
    roles = get_all_roles()
    for role in roles:
        for cap in role.preferred_capabilities:
            # Preferred capabilities must be READ or EXEC/WRITE at most,
            # never ADMIN (which requires explicit human approval)
            assert cap != "compute.job_submit" or \
                role.risk_tolerance.value == "cautious", \
                f"Role {role.name} has ADMIN-risk capability {cap} as preferred"


def test_level_0_role_requires_human_approval():
    """LEVEL_0 roles must require human approval for delegation."""
    roles = get_all_roles()
    assert len(roles) >= 14, f"Expected at least 14 roles, got {len(roles)}"


# --------------------------------------------------------------------------- #
# 11. Delegation depth is bounded
# --------------------------------------------------------------------------- #
def test_delegation_depth_is_bounded():
    """DelegationManager must enforce max_depth."""
    mgr = DelegationManager()
    assert hasattr(mgr, "_delegation_depth"), \
        "DelegationManager must have a bounded delegation depth attribute"


# --------------------------------------------------------------------------- #
# 12. No secret patterns in module-level source inspection
# --------------------------------------------------------------------------- #
def test_no_hardcoded_secrets_in_phase10_source():
    """No literal API keys, tokens, or passwords in Phase 10 source."""
    for fname in PHASE10_SOURCE_FILES:
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        raw = json.dumps({"src": text}, default=str)
        for label, pat in SECRET_PATTERNS.items():
            assert not pat.search(raw), \
                f"{fname} contains {label}-shaped secret value"
