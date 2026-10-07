# Phase 9 — Real Compute Fabric: Implementation Map

> Nothing here rebuilds existing infrastructure. Every arrow (`→`) is a
> **delegation** to a verified existing subsystem (audit: `docs/PHASE9_AUDIT.md`).

## 1. Package: `jarvis_compute/` (new, thin)

A canonical abstraction layer over the EXISTING fabric. It is the single place
the Brain names compute work; underneath it always resolves to a real provider.

### `jarvis_compute/resource.py` — canonical `ComputeResource`
Wraps `cloud_fabric.cloud_resources()` (no new probes, no new credentials).

```python
@dataclass(frozen=True)
class ComputeResource:
    resource_id: str            # local:control-node | cloud:nvidia | cloud:kaggle | cloud:huggingface | remote:<id> | docker:execution
    provider: str               # local | nvidia | kaggle | huggingface | remote_host | docker
    kind: str                   # control_plane | gpu_inference | gpu_training | artifact_store | container_runtime | remote_execution_host
    capabilities: tuple[str,...]
    state_chain: dict           # truthful: configured→authenticated→reachable→healthy→resource_verified→(job_verified|inference_verified)
    state: str                  # canonical: CONFIGURED|AUTHENTICATED|REACHABLE|HEALTHY|RESOURCE_VERIFIED|JOB_VERIFIED|AVAILABLE|UNAVAILABLE|DEGRADED|BLOCKED|OFFLINE|NOT_CONFIGURED
    gpu: Optional[str]; gpu_memory_gb: Optional[float]
    cpu: Optional[str]; cpu_cores: Optional[int]; memory_gb: Optional[float]
    cost_class: str; latency: Optional[float]; ttl: float = 30.0
    offline_capable: bool       # true only where a local/real fallback exists (static_search etc.)
    note: Optional[str] = None

    @property
    def available(self) -> bool: ...        # AVAILABLE only when state_chain is truthful
```

State mapping (existing `ProviderHealth`/`ProviderStatus` → canonical chain):
`UNCONFIGURED→NOT_CONFIGURED`; `AUTHENTICATION_FAILED→BLOCKED` (creds present but rejected — auth required); `OFFLINE/UNAVAILABLE/ERROR→UNAVAILABLE`; `DEGRADED`→`DEGRADED`; `HEALTHY && models_found>0 && credential_authorized && inference_verified && REACHABLE → AVAILABLE` (all gates required; a configured credential alone never implies `AVAILABLE`).

### `jarvis_compute/selector.py` — deterministic `ComputeSelector`
Reuses `cloud_fabric.select_compute` + `providers.routing.ProviderRouter`.

```python
@dataclass
class Selection:
    selected: Optional[ComputeResource]
    fallback: list[ComputeResource]
    reason: str
    state: str   # AVAILABLE | DEGRADED | RESOURCE_UNAVAILABLE | PLAN_BLOCKED | AUTHORIZATION_REQUIRED | HUMAN_APPROVAL ...

class ComputeSelector:
    def __init__(self, *, policy="best_quality", ttl=30.0): ...
    def resources(self, refresh=False) -> list[ComputeResource]: ...   # truthful snapshot
    def select(self, requirements: dict) -> Selection: ...           # cloud_fabric.select_compute + ProviderRouter fallback chain
    def resource_for(self, capability: str, *, offline: bool = False) -> Selection
```

**Policy table (Phase 9 §4)** — never hardcodes vendor; preference is purpose-fit + health-verified:

| task class | GPU | persistent | offline | max_cost | → selected | fallback |
|---|---|---|---|---|---|---|
| local analysis / static search / control plane | no | any | yes | free_local | `local:control-node` | — |
| LLM inference (chat/embed/reason) | no (API) | any | no | approved | `ProviderRouter` best_quality w/ NVIDIA preferred (env `JARVIS_PROVIDER_PRIORITY`) when AUTHENTICATED+HEALTHY+inference_verified | google/openai/aws → DEGRADED |
| LLM inference, privacy=local_only | no | any | any | approved | `local:control-node` (Silverwing) only | PROVIDER_UNAVAILABLE |
| fine-tune / LoRA / SFT / eval | yes | no | no | approved | `cloud:kaggle` (GPU training) | local GPU (if any) → RESOURCE_UNAVAILABLE |
| artifact publish / model upload | no | yes | any | approved | `cloud:huggingface` (artifact_store) | — |
| docker / build_test / service_isolation | no | any | any | approved | `docker:execution` (local or remote via `remote:<id>`) | RESOURCE_UNAVAILABLE |
| unknown / no eligible | — | — | — | — | `RESOURCE_UNAVAILABLE` + reason | — |

`offline=True` ⇒ only `local:control-node` (+ Docker if present) are eligible; cloud resources excluded and reported `OFFLINE` in the fallback (never fabricated).

### `jarvis_compute/contract.py` — Brain-facing contracts
```python
@dataclass
class ComputeRequest:
    task: str
    task_type: str                 # inference|training|evaluation|embedding|artifact
    requirements: dict             # gpu_required, min_gpu_memory_gb, ...
    model: Optional[str] = None
    execution_mode: str = "ONLINE" # ONLINE|DEGRADED|OFFLINE
    selected_provider: Optional[str] = None

@dataclass
class TrainingRequest:
    base_model: str
    dataset: str
    hyperparams: dict
    budget_usd: float
    max_duration_minutes: int
    target: str = "kaggle"         # kaggle | local | remote

@dataclass
class ComputeJobHandle:
    job_id: str
    status: str                    # QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED|RESOURCE_UNAVAILABLE
    resource: Optional[str]
    provider: Optional[str]
```

### `jarvis_compute/gate.py` — authorization + budget + risk gate
Reuses `TaskBudget` (Phase 8) + `providers.routing.ProviderRouter` + `SecretManager` (read-only) + `providers.errors`.

```python
class ComputeGate:
    def authorize(self, tool: str, risk: RiskLevel, user_id: str, budget: TaskBudget, ctx) -> tuple[bool, str]:
        ...                      # deny NETWORK/ADMIN without confirmation (reuse DefaultPermissionPolicy)
    def verify_resource(self, resource: ComputeResource, req: ComputeRequest) -> tuple[bool,str]:
        ...                      # truthful RESOURCE_VERIFIED / JOB_VERIFIED checks
    @staticmethod
    def scrub_provider_response(resp: ProviderResponse) -> dict:
        ...                      # dict-only, NO api_key/token; scrub_secrets applied
```

### `jarvis_compute/capabilities.py` — the canonical `compute.*` tools
Each is a `Tool` subclass registered into the EXISTING `ToolRegistry`. They never read credentials (the provider adapters do, via `SecretManager`, inside `_guard_context`); they return `ToolResult` whose `to_model_view()` is scrubbed.

| Tool | Risk | Confirmation | Delegates to | Truthful states |
|------|------|--------------|--------------|-----------------|
| `compute.discover` | read | no | `ComputeSelector.resources()` → `cloud_fabric.cloud_resources` + `ProviderControlCenter` health cache | all 11 states |
| `compute.select` | read | no | `ComputeSelector.select(req)` → `cloud_fabric.select_compute` + `ProviderRouter` | AVAILABLE/DEGRADED/RESOURCE_UNAVAILABLE/PLAN_BLOCKED/AUTHORIZATION_REQUIRED/HUMAN_APPROVAL |
| `compute.verify` | read | no | `remote_host.verify_job()` / `ProviderControlCenter.check_provider` | RESOURCE_VERIFIED/JOB_VERIFIED/BLOCKED |
| `compute.inference` | network | yes | `ProviderRouter.route_text` → `adapter.chat(ProviderRequest)` (creds inside adapter; `_guard_context` raises `SecretLeakError`) | PROVIDER_UNAVAILABLE / AUTHENTICATION_REQUIRED / RATE_LIMITED / HEALTHY |
| `compute.training` | network | yes, background | `brain_training/kaggle` JobRegistry lifecycle; `TrainingRequest` | JOB_SUBMISSION_UNAVAILABLE / JOB_VERIFIED |
| `compute.evaluation` | network | yes | Kaggle/eval pipeline; `JobRegistry` | EVALUATION_UNAVAILABLE |
| `compute.embedding` | network | yes | `ProviderRouter` w/ EMBEDDINGS cap → `adapter.embeddings` | PROVIDER_UNAVAILABLE |
| `compute.artifact_upload` | network | yes | `ArtifactRegistry.register` + `PromotionGate` | PROMOTION_REQUIRED / BLOCKED |
| `compute.artifact_download` | read | no | `ArtifactRegistry.get` + HF hub | UNAVAILABLE |
| `compute.job_submit` | network | yes, background | `JobRegistry.create_job` | JOB_SUBMISSION_UNAVAILABLE |
| `compute.job_status` | read | no | `JobRegistry.get/list_jobs` | JOB_VERIFIED/CANCELLED |
| `compute.job_cancel` | network | yes | `JobRegistry.cancel_job` (human approval for running jobs) | JOB_VERIFIED/CANCELLING |
| `compute.resource_health` | read | no | `ProviderControlCenter.check_provider` + `HealthCache` (TTL) | full state chain |

### `jarvis_compute/__init__.py`
`get_compute_fabric()` factory; `register_compute_tools(registry)` adds the 13 canonical tools to any `ToolRegistry` (used by `build_capability_registry`).

## 2. Wiring (no orchestrator rewrite)

- **Capability catalogue**: add the 13 `compute.*` entries to
  `research_engine.capability_contract._META` (`domain="infrastructure"`,
  `requires_*`,`supports_offline`, `service_dependencies=("provider_fabric",)`,
  `risk_level`, `audit_policy="record_execution"`). Because `CapabilityDiscoverTool`
  / `capability_inventory` already iterate registered tools + `_META`, the Brain's
  available-capability pack gains the canonical set automatically
  (Phase 9 §15/16).
- **Dispatch**: the Phase 8 `BrainOrchestrator` already does
  `ToolRegistry.invoke(name, args, ctx)` for any registered capability and
  `TaskBudget` enforces limits. Adding `compute.*` tools is sufficient; existing
  approval-gate + replan + `_sanitize_result_for_brain` path applies unchanged.
- **Failure → replan (Phase 9 §9/§11)**: `ComputeGate` maps provider outcomes to
  truthful tokens that the orchestrator's reassessment path recognizes:
  `ProviderUnconfigured`→`RESOURCE_UNAVAILABLE` (unconfigured),
  `ProviderAuthenticationError`→`AUTHENTICATION_REQUIRED`,
  `ProviderTimeout`/`ProviderUnavailable`→`PROVIDER_UNAVAILABLE`,
  quota→`RATE_LIMITED`, `SecretLeakError`→`SECRET_LEAK_REFUSED` (hard fail, no retry).
  All are scrubbed before reaching the Brain; the orchestrator validates the next
  proposal again (PLAN_VALIDATED→PLAN_AUTHORIZED→EXECUTION_STARTED ordering
  preserved).
- **Budget (Phase 9 §12)**: `compute.inference` tokens → `TaskBudget.spend_tokens`
  (rate from `ProviderModel.pricing_per_1k`, `None`→unknown, never fabricated);
  `compute.job_submit` duration → `spend_tool_call`/counter; `compute.training`
  budget_usd vs `TaskBudget.max_cost`.
- **Modes (Phase 9 §10)**: `execution_mode` flows into `ComputeSelector.select`
  (`offline` flag). OFFLINE ⇒ local-only eligibility + truthful cloud=OFFLINE.
- **Holographic state (Phase 9 §15)**: `compute.discover`/`resource_health` expose
  the full state chain; `capability.catalogue` already publishes it.

## 3. `compute.inference` real path (Phase 9 §5) — Brain→NVIDIA secure flow

```
Brain capability_request("compute.inference", {task, model, messages})
  → PlanValidator (exists? authorized NETWORK+confirm? online-mode ok? deps ok?)
  → orchestrator.execute → ToolRegistry.invoke("compute.inference", args, ctx)
       → ComputeSelector.select({gpu_required=False,...,task=inference})
          → ProviderRouter.route_text(task)   # health-gated, fallback chain
          → adapter = registry.get(decision.selected_provider)   # e.g. NvidiaAdapter
       → ComputeGate.authorize(...)          # NETWORK requires confirmation
       → build ProviderRequest(messages)     # NO credential fields ever set by tool
       → adapter.chat(request)               # Adapter reads creds via SecretManager;
                                              #   _guard_context scans request text and
                                              #   raises SecretLeakError if a secret leaked
       → ProviderResponse {provider,model,text,usage,latency,finish_reason}  # NO key
  → ComputeGate.scrub_provider_response(resp)  # scrub_secrets over text
  → ToolResult(name="compute.inference", result=scrubbed, metrics={provider,model,latency,usage,cost_estimate?})
  → ToolRegistry invokes scrub_secrets over result/error + returns ToolResult
  → to_model_view() to Brain (no secrets)
  → VerificationEngine.check → Phase 8 VERIFICATION → REASON → (REPLAN on failure)
```
The Brain never references `JARVIS_NVIDIA_API_KEY`, the adapter, or `SecretManager`.

## 4. Truthful failure-state map (Phase 9 §9)

| Real condition | Reported state |
|----------------|----------------|
| adapter constructed, no credential env | `NOT_CONFIGURED` (available=False) |
| cred present, provider rejects (401/403) | `BLOCKED` / `AUTHENTICATION_REQUIRED` |
| cred present, endpoint unreachable | `UNAVAILABLE` (`PROVIDER_UNAVAILABLE`) |
| reachable but health probe degraded | `DEGRADED` |
| healthy + inference verified | `AVAILABLE` |
| health-cache TTL expired → re-probe | re-evaluates (never stale-claims `AVAILABLE`) |
| Brain proposes unavailable capability | `PLAN_REJECTED` (validator) |
| capability needs cloud but mode=OFFLINE | `PLAN_BLOCKED` |
| destructive op | `HUMAN_APPROVAL` |

## 5. Tests (all green in this sandbox; live ones env-gated)

- `tests/test_compute_resource.py` — all resources truthful; here: local=AVAILABLE (local compute), cloud:nvidia/kaggle/hf = NOT_CONFIGURED; never `AVAILABLE` from a credential alone.
- `tests/test_compute_selector.py` — policy table: small/analysis→local; offline→local-only (cloud=OFFLINE); LLM inference→best_quality provider or RESOURCE_UNAVAILABLE; deterministic + no fabrication.
- `tests/test_compute_capabilities.py` — 13 canonical tools registered; descriptions carry risk/confirmation/offline; `compute.discover` returns real state chains; scrub_secrets redacts planted credentials in outputs.
- `tests/test_compute_redteam.py` (Phase 9 §17) — Brain cannot name/obtain any secret env (`NVIDIA_API_KEY`, `KAGGLE_*`, `HF_TOKEN`, etc.); `compute.inference` result + `to_model_view()` contain no credential-shaped substrings; `brain_fabric.assert_no_secrets` clean on all fabric output; `_guard_context` raises `SecretLeakError` when a secret is planted in a `ProviderRequest` (fake adapter).
- `tests/test_compute_no_fabrication.py` (Phase 9 §19) — scan production paths for `mock|fake|dummy|placeholder|faker`; assert no `JobInfo`/artifact with fake ids in registries; env-gated live tests skip cleanly.
- `tests/test_compute_orchestration.py` (Phase 9 §11) — failure evidence → Phase 8 reassessment → replan; protocol transitions legal (PLAN_AUTHORIZED before EXECUTION_STARTED).
- `tests/test_compute_performance.py` (Phase 9 §20) — `HealthCache`/local hardware cached within TTL; repeated `compute.discover` bounded.
- `tests/test_compute_nvidia_e2e.py` (Phase 9 §22, env-gated) — real NVIDIA inference through `compute.inference` → `ProviderRouter`→`NvidiaAdapter.chat` **iff** `JARVIS_NVIDIA_API_KEY` set; else assert `NOT_CONFIGURED` and skip.
- `tests/test_compute_kaggle_e2e.py` (env-gated) — real JobRegistry lifecycle via `compute.job_submit` **iff** `KAGGLE_*` present; else `JOB_SUBMISSION_UNAVAILABLE` + skip.

## 6. Non-goals (honesty boundary)

- No real NVIDIA/Kaggle/HF execution is possible in this sandbox (no creds/network/GPU). The wiring + security boundaries + truthful degradation are **proven here**; live execution is proven by env-gated tests that skip+xfail cleanly when credentials are absent.
- No new API routes duplicating `jarvis_backend/routers/*` (Phase 9 §14 reuses existing `identity` auth for router additions only if needed; the Brain↔fabric path is via the capability tool registry, not HTTP).
- No rewrite of `jarvis_brain/*`, `ToolRegistry`, `ProviderControlCenter`, `ProviderRouter`, `JobRegistry`, `ArtifactRegistry`, `PromotionGate`, `SecretManager`.

## 7. Execution order

1. Write `jarvis_compute/{resource,contract,selector,gate,capabilities,__init__}.py`.
2. Wire 13 `compute.*` tools into `build_capability_registry` + `_META` (two small edits).
3. Add tests (8 files).
4. Run: Phase 9 tests green + full suite regression (only the 3 pre-existing env-only failures may remain) + Phase 8 still green.
5. Write `docs/PHASE9_RESULT.md`.
