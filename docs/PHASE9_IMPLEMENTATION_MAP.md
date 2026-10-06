# Phase 9 — JARVIS Real Compute Fabric (Implementation Map)

## Status: Phase 8 COMPLETE | `BRAIN_RUNTIME_UNAVAILABLE = True` (expected — no `JARVIS_BRAIN_ENDPOINT`)

Phase 9 does NOT require a running Brain runtime. JARVIS must select and use real
compute resources (LOCAL, NVIDIA, KAGGLE, HUGGING FACE, future remote GPU) while
keeping the Brain isolated from all credentials.

---

## Audit Summary

### Existing Foundation (ALL REUSED — NOT REBUILT)

| Layer | Location | Key Components |
|-------|----------|----------------|
| Resource abstraction | `F:\AI/jarvis_compute/` | `resource.py` — `ComputeResource` dataclass, state ladder, `from_cloud_resource`/`from_provider_status` |
| Compute selector | `F:\AI/jarvis_compute/selector.py` | `ComputeSelector` — deterministic ranking via `select()` → `Selection` |
| Compute contract | `F:\AI/jarvis_compute/contract.py` | `ComputeRequest`, `TrainingRequest`, `ComputeJobHandle`, truthful failure tokens |
| Cloud fabric | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/cloud_fabric.py` | `local_hardware()`, `select_compute()`, `cloud_resources()`, `execution_mode()`, per-resource probes |
| Brain fabric | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/brain_fabric.py` | `external_status()`, `_kaggle_probe()`, `_hf_probe()`, `integration_matrix()`, `assert_no_secrets()` |
| Remote host | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/remote_host.py` | `RemoteExecutionHost`, `Transport`, `discover()`, `verify_job()`, `meets_requirements()` |
| Capability contract | `F:\AI/research_engine/capability_contract.py` | 89 `_META` entries, `CapabilityContract`, `build_contracts()`, `discover_capabilities()` |
| Capability tools | `F:\AI/research_engine/capability_tools.py` | 88 registered Tool adapters, `build_capability_registry()`, `capability_inventory()` |
| Provider fabric | `F:\AI/providers/` | `ProviderControlCenter`, `bootstrap_fabric()`, `ProviderRouter` |
| NVIDIA adapter | `F:\AI/providers/nvidia/` | `NvidiaAdapter` (OpenAI-compatible), `nvidia_health_probe()` |
| HF adapters | `F:\AI/providers/huggingface/` | `HuggingFaceAdapter`, `hub_health()`, `publish()` via `brain_training/hf.py` |
| SecretManager | `F:\AI/providers/secrets.py` | `get_secret_manager()`, `assert_no_secrets()`, Fernet-encrypted vault |
| Job registry | `F:\AI/Jarvis-super-intelligence-/infrastructure/job_registry.py` | `JobRegistry`, `JobInfo`, lifecycle |
| Artifact registry | `F:\AI/Jarvis-super-intelligence-/infrastructure/artifact_registry.py` | `ArtifactRegistry`, provenance |
| Promotion gate | `F:\AI/Jarvis-super-intelligence-/infrastructure/promotion_gate.py` | Stage gating, `EvaluationCriteria`, `PromotionOutcome` |
| Control plane API | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/routers/control_plane.py` | FastAPI `/api/v2/control/*` endpoints |
| Chat service | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/chat_service.py` | `ChatService` with project-intelligence integration |
| Project intel | `F:\AI/Jarvis-super-intelligence-/jarvis_backend/project_intel.py` | `detect_project_intent()`, `select_capabilities()`, `build_evidence_pack()` |
| Training pipeline | `F:\AI/brain_training/pipeline.py` | `BrainPipeline` with 14 stages |
| Brain training | `F:\AI/brain_training/` | `hf.py` (HFConnection/publish), `kaggle.py` (KaggleProbe), `promote.py` (gate), `hardware.py` (gpu_probe) |

### Verified Baseline: 144 Tests PASS
All 5 Phase 9 test files pass (test_cloud_fabric, test_capability_contract, test_capability_fabric, test_brain_fabric, test_remote_host, test_integration_fabric).

---

## Gap Analysis

### Gap 1: Missing `compute.*` capability family in `_META`

Only `compute.select` exists in `_META` (89 entries total). The task requires 12 additional:
- `compute.discover`, `compute.verify`, `compute.inference`, `compute.training`,
`compute.evaluation`, `compute.embedding`, `compute.artifact_upload`,
`compute.artifact_download`, `compute.job_submit`, `compute.job_status`,
`compute.job_cancel`, `compute.resource_health`

These are **provider-agnostic compute capabilities** — thin facades that the Brain
sees, while provider-specific implementations (`nvidia.inference`, `kaggle.jobs`,
`huggingface.artifacts`) exist underneath.

### Gap 2: Missing `compute.*` Tool adapters

`capability_tools.py` has 88 registered tools but none in the `compute.*` family
(except `compute.select` via `ComputeSelectTool`). Each new capability needs a Tool
class that delegates to existing infrastructure WITHOUT exposing credentials.

### Gap 3: Missing control-plane compute endpoints

Control plane has `/cloud/compute/select` but no dedicated `/compute/*` routes for
the compute capability family (submit/verification/inference/training/etc).

### Gap 4: Missing chat-initiated compute routing

`project_intel.py` `_CAPABILITY_ROUTES` has no patterns for compute tasks.

### Gap 5: Missing security red-team tests

No tests verify the Brain→compute boundary (no credential exfiltration, no fake
availability claims, no unauthorized execution).

### Gap 6: Missing Phase 9 documentation

No `PHASE9_IMPLEMENTATION_MAP.md` (this file) or `PHASE9_RESULT.md`.

---

## Implementation Plan

### Step 1: Add 12 `compute.*` entries to `_META` (capability_contract.py)
Domain assignment:
- `ai_ml_development`: `compute.discover`, `compute.inference`, `compute.training`,
  `compute.evaluation`, `compute.embedding`, `compute.artifact_upload`,
  `compute.artifact_download`
- `infrastructure`: `compute.verify`, `compute.job_submit`, `compute.job_status`,
  `compute.job_cancel`, `compute.resource_health`

### Step 2: Implement 12 `compute.*` Tool adapters (capability_tools.py)
Each tool delegates to existing infrastructure, passes `assert_no_secrets()`:
- `compute.discover` → `cloud_fabric.cloud_resources()`
- `compute.select` → EXISTS (`ComputeSelectTool`)
- `compute.verify` → `compute.select` + resource verification via selected path
- `compute.inference` → `live_provider_status()` / NVIDIA adapter (read-only verification state; never exposes tokens)
- `compute.training` → `brain_training.pipeline` readiness
- `compute.evaluation` → `brain_fabric` evaluation pipeline status
- `compute.embedding` → local provider / NVIDIA inference path check
- `compute.artifact_upload` → `brain_training.hf` publish state
- `compute.artifact_download` → `brain_training.hf` repo_exists check
- `compute.job_submit` → `JobRegistry` create
- `compute.job_status` → `JobRegistry` list/status
- `compute.job_cancel` → `JobRegistry` cancel
- `compute.resource_health` → `live_provider_status()` per-resource

All tools are **read-only / status-reporting** — they report truthful availability
and verify readiness. Real execution (submitting training, running inference)
goes through the control plane with explicit authorization, NOT through the
capability fabric.

### Step 3: Register all 12 tools in `build_capability_registry()`
Maintain the `len(contracts) == len(registry.available())` invariant.

### Step 4: Add `/api/v2/control/compute/*` REST endpoints
- GET `/compute/discover`
- GET `/compute/select` (delegates to existing `compute.select`)
- POST `/compute/verify`
- POST `/compute/inference`
- POST `/compute/training`
- POST `/compute/evaluation`
- POST `/compute/embedding`
- POST `/compute/artifact/upload`
- POST `/compute/artifact/download`
- POST `/compute/job/submit`
- GET `/compute/job/{id}`
- POST `/compute/job/cancel`
- GET `/compute/resource/health`

All endpoints require authentication. Mutation endpoints require admin/approval.

### Step 5: Wire compute.* into project_intel.py routes
Add patterns for compute-related chat requests (e.g. "train a model", "run inference",
"upload artifact").

### Step 6: Write security red-team tests
- Secret exfiltration via compute capability results
- Credential leakage to Brain
- Capability over-claim (reporting success without verification)
- Unauthorized compute execution
- Truthful failure when no resources available

### Step 7: Write PHASE9_RESULT.md
Documenting all success criteria met.

### Step 8: Run full test suite
Confirm 144 + new tests all green.

---

## Credential Isolation Boundary

The Brain → Capability Fabric → Control Plane → Providers flow:
```
USER → BRAIN → STRUCTURED PLAN → PLAN VALIDATOR → COMPUTE SELECTOR
  → AUTHORIZATION (SecretManager resolves creds here, NOT in Brain)
  → EXECUTION → OBSERVATION → VERIFICATION → ARTIFACT REGISTRY
  → REASON / REPLAN → USER RESULT
```
The Brain only sees `compute.*` capability interfaces. Secrets are resolved by
`SecretManager` at execution time, never passed to the Brain.
