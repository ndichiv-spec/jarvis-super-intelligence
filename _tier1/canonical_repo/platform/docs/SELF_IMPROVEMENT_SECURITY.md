# Self-Improvement Security Model

## Overview

The Self-Improvement Engine operates under strict security boundaries to ensure
JARVIS can never compromise its own safety, integrity, or the underlying
infrastructure.

## Core Principle

> JARVIS must NOT directly rewrite its own production source code, bypass
> security controls, modify credentials, alter authorization, or promote its
> own model without existing gates.

Self-improvement means **controlled improvement** of models, datasets, prompts,
policies, and capability implementations — always under verification and approval.

## Autonomy Boundary

### AutonomyGuard

The `AutonomyGuard` enforces the autonomy boundary at every step:

```python
guard = AutonomyGuard(autonomy_level=1)
allowed, reason = guard.check_intervention(InterventionType.T, target)
```

### Protected Paths

The following paths are **always** blocked from modification:

| Path | Reason |
|------|--------|
| `providers/` | Provider configuration directory |
| `jarvis_backend/core.py` | Core infrastructure |
| `infrastructure/artifact_registry.py` | Artifact registry — must be immutable |
| `infrastructure/job_registry.py` | Job registry — must be immutable |
| `infrastructure/provider_registry.py` | Provider registry |
| `infrastructure/promotion_gate.py` | Promotion gate — must be immutable |
| `infrastructure/audit_events.py` | Audit trail — must be immutable |
| `jarvis_backend/cloud_fabric.py` | Compute fabric |
| `.env` | Environment secrets |
| `jarvis_secret_key` | Secret key |

### Secret Field Detection

The following field names trigger automatic blocking:

```
api_key, apikey, token, secret, password, passwd, credential,
authorization, bearer, private_key
```

These are checked at multiple levels:
1. `AutonomyGuard.check_intervention()` — in the target string
2. `AutonomyGuard.check_artifact()` — in the candidate artifact's training_config
3. `assert_no_secrets()` — in all cycle payloads

## Prohibited Interventions

### SYSTEM_POLICY_CHANGE — Never Autonomous

`SYSTEM_POLICY_CHANGE` is in `PROHIBITED_INTERVENTIONS` and is **always blocked**
at every autonomy level. This prevents JARVIS from:

- Modifying authentication policies
- Changing authorization rules
- Altering security controls
- Modifying credential handling
- Bypassing audit logging

### High-Risk Interventions

In addition to prohibited interventions, `High-RISK_INTERVENTIONS` always
require manual approval:

```python
HIGH_RISK_INTERVENTIONS = frozenset({
    SYSTEM_POLICY_CHANGE,     # Always blocked (also in PROHIBITED)
    ARCHITECTURE_CHANGE,      # Model architecture changes
})
```

## Promotion Security

### Can-Promote Check

```python
guard.can_promote(artifact, promotion_approved=False)
```

An artifact can only be promoted if:
1. Its status is `APPROVED`, AND
2. Either:
   - `promotion_approved=True` (explicit manual approval), OR
   - `autonomy_level >= 3` (full autonomy) AND artifact is verified

### State Transition Integrity

Candidate artifacts follow a strict state machine:

```
EXPERIMENTAL → STAGING → LOCKED → EVALUATED → VERIFIED →
PROMOTION_REVIEW → APPROVED → DEPLOYED_SHADOW → DEPLOYED_CANARY → DEPLOYED
```

Direct status skipping is impossible — `CandidateStatus.validate_transition()`
raises `ValueError` for invalid transitions.

## Deployment Security

### Production Deployment

Production deployment requires:
1. `autonomy_level >= 3`, OR
2. Explicit manual approval

At `autonomy_level < 3`:
```python
with pytest.raises(PermissionError, match="Production deployment requires manual"):
    orch.deploy_candidate(cycle, mode=DeploymentMode.PRODUCTION.value)
```

### Rollback

All deployments have `rollback_on_failure=True` by default. The
`rollback_deployment()` method:

- Sets `rolled_back=True`
- Records `rollback_reason`
- Transitions candidate to `ROLLED_BACK` status
- Transitions cycle to `ROLLED_BACK` status

## No-Fabrication Guarantee

### EvidenceEngine

The `EvidenceEngine.assert_no_fabrication()` method checks that all metrics
are grounded in real evaluation data:

- WeaknessDetector only reports actual regressions
- BaselineLock hash verification prevents metric tampering
- Evaluation results include provenance tracking
- Candidate results include evaluation_version matching

### assert_no_secrets

The `assert_no_secrets()` function recursively scans all payloads for
secret-shaped fields:

```python
leaks = assert_no_secrets(cycle.to_dict())
# Returns list of paths like ["training_config.api_key"]
```

If any leaks are found, `verify_cycle()` marks the cycle as unverified.

## Audit Trail Integrity

### Persistence

All improvement cycles are persisted in the `improvements` store via
`get_store("improvements")`:

- Cycles: `data["cycles"]`
- Lessons: `data["lessons"]`
- Graph: `data["graph"]["nodes"]`, `data["graph"]["edges"]`

### Tamper Detection

- `BaselineLock` uses SHA256 hash of sorted JSON — tampering is detected
- Audit events are written via `AuditEventService`
- Baseline lock hash is immutable — tampering with metrics breaks verification

### No Erasure

The system prevents erasure of experiments or audit trails:

1. Cycles are persisted immediately on creation
2. BaselineLock hashes make tampering evident
3. `assert_no_fabrication()` checks evidence integrity
4. `verify_cycle()` checks all of the above

## Secret Isolation from Brain

The Brain never receives:
- API keys
- OAuth tokens
- Provider credentials
- Database passwords
- Filesystem credentials
- SSH keys
- Cloud credentials
- Raw secret configuration
- Unrestricted shell authority

All secret handling is delegated to `brain_fabric.assert_no_secrets()` and
the `AutonomyGuard` boundary checks.
