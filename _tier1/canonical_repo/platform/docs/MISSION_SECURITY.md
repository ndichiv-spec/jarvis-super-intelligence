# Phase 10 — Mission Security

## Overview

Phase 10 maintains strict security boundaries. The Cognitive Kernel, Cognitive State, and Mission abstractions never handle secrets — they only process structured reasoning artifacts derived from capability tool results.

## Security Boundaries

### What the Brain NEVER Receives

The Brain (and by extension, the Cognitive Kernel, Cognitive State, and Mission) must NEVER receive:

| Secret Type | Examples |
|-------------|----------|
| API keys | OpenAI, Anthropic, NVIDIA, HuggingFace API keys |
| OAuth tokens | Google, GitHub, Microsoft OAuth tokens |
| Provider credentials | AWS keys, GCP service account, Azure tokens |
| Database passwords | PostgreSQL, MySQL, MongoDB passwords |
| Filesystem credentials | Encrypted volume keys, NAS credentials |
| SSH keys | Private SSH keys, deployment keys |
| Cloud credentials | IAM roles, service principals |
| Raw secret configuration | `.env` files, config with secrets |
| Unrestricted shell authority | `shell=True`, `os.system`, unrestricted `subprocess` |

### Enforcement Mechanism

Secret scrubbing is enforced via `assert_no_secrets()` in `brain_fabric.py`:

```python
_SECRET_KEYS = (
    'api_key', 'apikey', 'token', 'secret',
    'password', 'passwd', 'credential',
    'authorization', 'bearer', 'private_key'
)
```

The function recursively walks cognitive state dictionaries and:
1. Detects any key matching substring patterns in `_SECRET_KEYS`
2. Raises `AssertionError` if a secret is found
3. Is called at every state mutation point:
   - `_perceive()` — before recording hardware/brain status
   - `_observe()` — before recording evidence from tool results
   - `_checkpoint()` — before persisting state
   - `resume()` — before restoring state

### Known False Positives

| Field | Why | Mitigation |
|-------|-----|------------|
| `max_tokens` | `token` is substring of `tokens` | Filtered in tests |
| `tokens_used` | `token` is substring | Filtered in tests |

These are model configuration fields, not secrets, and are handled in test assertions.

## Red-Team Test Coverage

26 security tests in `tests/test_mission_redteam.py`:

### Secret Isolation (5 tests)
- `test_no_secrets_in_mission_serialization` — No secrets in Mission.to_dict()
- `test_no_secrets_in_checkpoint` — No secrets in checkpoints
- `test_no_secrets_in_full_kernel_run` — No secrets after 2-cycle kernel run
- `test_no_secret_patterns_in_mission_json` — JSON output contains no secret patterns
- `test_mission_does_not_store_credentials` — Mission never stores credentials

### Credential Escalation Prevention (2 tests)
- `test_mission_does_not_request_cloud_credentials` — Missions don't request credentials
- `test_mission_constraints_can_block_credentials` — Constraints block credential flow

### No Fabrication (4 tests)
- `test_critic_flags_potential_fabrication` — VERIFIED evidence without provenance is flagged
- `test_critic_does_not_fabricate_positive_findings` — Critic doesn't fabricate
- `test_hypothesis_engine_rejects_unverified_confirmation` — CONFIRMED requires VERIFIED
- `test_no_cloud_provisioning_in_kernel` — No boto3/Azure/GCP SDK in kernel

### No Self-Approval (6 tests)
- `test_mission_cannot_skip_verifying_to_completed` — No DRAFT → COMPLETED
- `test_completion_requires_verification_not_tasks` — Tasks alone don't trigger COMPLETED
- `test_mission_stays_active_without_verification` — Stays ACTIVE without verification
- `test_level_0_blocks_exec_capabilities` — LEVEL_0 blocks EXEC/NETWORK
- `test_level_0_does_not_auto_approve` — LEVEL_0 doesn't auto-approve
- `test_level_0_role_requires_human_approval` — LEVEL_0 requires human approval

### Shell Authority Prevention (1 test)
- `test_no_shell_in_phase10_source` — No `shell=True`, `os.system`, `os.popen`

### Role Boundaries (3 tests)
- `test_critic_has_no_execution_authority` — Critic has no execute/run_tool/etc.
- `test_critic_only_has_critique_method` — Critic's public API is critique-only
- `test_all_specialist_roles_have_excluded_capabilities` — Every role is bounded
- `test_no_role_can_execute_admin_capabilities` — No auto-preferred admin capabilities

### Delegation Bounding (1 test)
- `test_delegation_depth_is_bounded` — DelegationManager enforces max depth

### Hardcoded Secrets (1 test)
- `test_no_hardcoded_secrets_in_phase10_source` — No hardcoded secrets in source

## Autonomy Level Enforcement

| Level | READ | EXEC | WRITE | NETWORK | CLOUD | Requires Approval |
|-------|------|------|-------|---------|-------|-------------------|
| LEVEL_0 (assisted) | ✅ | ❌ | ❌ | ❌ | ❌ | All EXEC+ |
| LEVEL_1 (supervised) | ✅ | ✅ (filtered) | ✅ (filtered) | ✅ (confirmation) | ❌ | NETWORK, CLOUD |
| LEVEL_2 (bounded) | ✅ | ✅ | ✅ | ✅ (high-risk) | ✅ (approval) | CLOUD |
| LEVEL_3 (self-improvement) | ✅ | ✅ | ✅ | ✅ | ✅ | Only via PromotionGate |

**The kernel cannot self-elevate.** Autonomy level is set at mission creation and can only be changed by an authorized human via the approval gate.

## Audit Trail

Every security-relevant action is recorded:

| Action | Audit Event |
|--------|-------------|
| Mission status change | `transition` event on timeline |
| Evidence registered | `evidence_registered` event |
| Tool result observed | `task_completed` event |
| Budget exhausted | `budget_exhausted` event |
| Hypothesis changed | `decision` event |
| Verification performed | `verify` event |

All events are persisted in `mission.metrics["event_timeline"]` and survive process restarts via checkpoint persistence.

## No-Fabrication Guarantee

The system guarantees truthfulness through three mechanisms:

1. **Evidence provenance**: Every evidence entry has an immutable `ProvenanceChain` recording who/what registered it and when.
2. **Verification states**: Evidence moves through GENERATED → EXECUTED → OBSERVED → VERIFIED. The Critic flags VERIFIED evidence without provenance.
3. **Critic oversight**: The analysis-only Critic runs at every cycle, checking for fabrication, evidence quality, and verification gaps.

## Cloud Provisioning Prevention

The kernel does NOT auto-provision cloud resources:
- No `boto3`, `azure`, or `gcp` imports in Phase 10 source
- No credential requests to providers
- Resources are discovered via Phase 9 `local_hardware()` — availability requires actual verification, never credentials alone
- `compute.job_submit` and `compute.training` require confirmation at LEVEL_0 and LEVEL_1

## Production Promotion Gate

Model promotion to production still requires the Phase 8 `PromotionGate`:
- Phase 9 verified: 58 compute tests pass, 0 failures
- `PromotionGate` must explicitly approve any model promotion
- The kernel cannot bypass the gate
