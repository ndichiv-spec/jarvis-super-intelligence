# Phase 9 — JARVIS Real Compute Fabric: Audit

Goal: make JARVIS auto-select and use **real** compute resources
(LOCAL · NVIDIA · KAGGLE · HUGGING FACE · future remote GPU) while keeping the
Brain completely isolated from provider credentials and execution authority.

This audit was performed **before any source change** (Phase 9 §1). It records
what already exists so Phase 9 never rebuilds it.

## 1. Roots

| Root | Role |
|------|------|
| `F:\AI` | Brain integration package (`jarvis_brain/`, `research_engine/`), provider **fabric** (`providers/`), backends (`brain_training/`, `brain_runtime/`), tests, docs. |
| `F:\AI\Jarvis-super-intelligence-` | Platform repo: FastAPI app (`jarvis_backend/`), orchestration infra (`infrastructure/`, `backend/control_plane/`), training pipelines. |

`tests/conftest.py` inserts **both** roots onto `sys.path`, so `providers.*`,
`infrastructure.*`, `jarvis_backend.*`, `research_engine.*`, `identity.*` all
resolve from tests.

## 2. Environment reality (this sandbox)

- Python 3.13 (CPython 313), Windows amd64, PowerShell-only shell.
- **No GPU**, **no `NVIDIA_API_KEY`/`JARVIS_NVIDIA_API_KEY`**, no Kaggle token,
  no `HF_TOKEN`, **no internet** to provider endpoints.
- `JARVIS_BRAIN_ENDPOINT` unset in plain env; set via `.env` only during pytest
  → `BRAIN_RUNTIME_UNAVAILABLE = True`.
- This is **correct, not a bug**. Real-provider tests here must report truthful
  `UNCONFIGURED`/`OFFLINE` and be environment-gated (`@pytest.mark.skipif`).

## 3. What already exists (REUSE — do NOT rebuild)

### Provider fabric  (`F:\AI\providers/`)
| File | Symbols | Notes |
|------|---------|-------|
| `base.py` | `ProviderAdapter` (ABC, `chat` abstract), `ProviderRequest`, `ProviderResponse`, `Usage`, `Message`, `ToolCall`, `StreamChunk` | `chat(request: ProviderRequest) -> ProviderResponse`. `_guard_context` scans requests with `SecretManager.assert_no_secrets(..., force_scan_all=True)` and raises `providers.errors.SecretLeakError` if any known secret leaks into the outbound context. `health(force)` via TTL `HealthCache`. |
| `capabilities.py` | `Capability` (CHAT/RESPONSES/STREAMING/TOOL_CALLING/VISION/AUDIO/EMBEDDINGS/RERANKING/STRUCTURED_OUTPUT/REASONING/BATCH/FINE_TUNING/EVALUATION/WEB_SEARCH/FILE_SEARCH/COMPUTER_USE), `parse_capability/validate_capabilities/serialize`, `QUALITY_CAPABILITIES` | Provider capability enum (vendor model), **distinct** from the capability *tool* registry. |
| `health.py` | `HealthStatus` {UNCONFIGURED,UNKNOWN,AUTHENTICATION_FAILED,OFFLINE,UNAVAILABLE,DEGRADED,HEALTHY,ERROR,FORBIDDEN,RATE_LIMITED,TIMEOUT} with `ok`/`is_configured`/`is_authenticated`/`is_healthy`/`is_ready`/`is_inference_ready`; `ProviderHealth`; `HealthCache` (TTL default 30.0s, `get`/`set`/`invalidate`); `record_inference_result`/`get_inference_result` module state. | The truthful state vocabulary. `ProviderHealth.is_ready` = healthy + model_list_available + authenticated. |
| `models.py` | `ProviderModel`, `DeploymentKind` (HOSTED/SELF_HOSTED/LOCAL/ADAPTER/REMOTE_ENDPOINT), `CostClass` (FREE/LOW/MEDIUM/HIGH), `PrivacyClass` (PUBLIC/INTERNAL/PRIVATE/SENSITIVE/LOCAL_ONLY), `ModelRef.parse` | Immutable model registry entry; `ModelRef.parse` parses `provider:model`. |
| `routing.py` | `ProviderRouter`, `TaskProfile`, `TaskClassifier`, `RoutingCandidate`, `RoutingDecision` | **ModelRouter-equivalent** (Phase 5/6). `route_text(task) -> RoutingDecision{selected_provider, selected_model, fallback_chain, cost_estimate=None}`. Policy-driven (`JARVIS_PROVIDER_PRIORITY`), privacy-enforced, health-gated, honest `None` cost. |
| `registry.py` | `ProviderRegistry`, `get_registry()`/`reset_registry()` | `register(adapter, replace=True)`, `get(pid)`, `providers()`, `configured()`, `all_capabilities()`, `health_snapshot()`, `health_summary()`, `providers_matching(...)`. |
| `control_center.py` | `ProviderControlCenter`, `ProviderStatus`, `ProviderMeta` | `list_providers()`, `check_provider(pid, force)` (real probe + TTL cache), `refresh(providers)`, `report()`, `route_task(...)`. Honest 3-state map: IMPLEMENTED→CONFIGURED→AUTHENTICATED→HEALTHY→READY. `is_inference_ready` gate. Probes openai/nvidia/google/aws/hf. |
| `bootstrap.py` | `bootstrap_fabric(registry?, secrets?, *, register=True)` | Constructs `OpenAIAdapter/NvidiaAdapter/GoogleAdapter/AwsBedrockAdapter/HuggingFaceAdapter` from env via `SecretManager`, registers into shared registry. Unconfigured adapters are **still constructed** and honestly report `configured=False`. |
| `secrets.py` | `SecretManager` (env→.env→Fernet vault), `get_secret_manager()`/`reset_secret_manager()`. | env substring match on `KEY/TOKEN/SECRET`; `get/put/configured/redact/secrets()/assert_no_secrets/assert_no_secrets_in_requests/store/has_vault`. `JARVIS_VAULT_KEY`/`JARVIS_DOTENV_PATH`. |
| `telemetry.py` | `ProviderTelemetry`, `get_telemetry()` | `event(provider, model, kind, status, ...)`. |
| `errors.py` | `ProviderError`, `UnsupportedCapability`, `ProviderUnconfigured`, `ProviderUnavailable`, `ProviderAuthenticationError`, `ProviderTimeout`, `ProviderContractError`, `SecretLeakError`. | |
| `nvidia/`, `openai/`, `google/`, `aws/`, `huggingface/` | vendor adapters (`NvidiaAdapter`, `OpenAIAdapter`, …) + `config.py`/`health.py`/`capabilities.py`/`models.py`. | `providers.nvidia.config.NvidiaConfig.from_environ(secrets)` reads `NVIDIA_API_KEY`/`JARVIS_NVIDIA_API_KEY`. `nvidia_health_probe` (real `/v1/models` probe). `OpenAICompatibleClient` HTTP transport. |

### Compute fabric  (`F:\AI\Jarvis-super-intelligence-/jarvis_backend/`)
| File | Symbols | Notes |
|------|---------|-------|
| `cloud_fabric.py` (602 lines) | `local_hardware(refresh)`, `cloud_resources(refresh)`, `select_compute(requirements)`, `_nvidia_resource`, `_kaggle_resource`, `_huggingface_resource`, `_docker_resource`, `_remote_host_resource`, `_local_resource`, `_internet_reachable`, `_is_compute_gpu`. | **Local hardware profile** via read-only PowerShell (CPU cores/RAM/GPU/VRAM/SLAT/docker/network). **`cloud_resources()` = canonical resource list**: `local:control-node` + `cloud:nvidia` + `cloud:kaggle` + `cloud:huggingface` + `docker:execution` + `remote_execution_host`, each with a truthful `state_chain` (configured→authenticated→reachable→healthy→resource_verified→job_verified/inference_verified). **`select_compute(req)`**: deterministic hardware-aware router (`gpu_required`, `min_gpu_memory_gb`, `docker_required`, `persistent_runtime`, `network_required`, `max_cost_class`, `task`); never hardcodes "GPU→NVIDIA". |
| `remote_host.py` (473 lines) | `RemoteExecutionHost` (dataclass: `is_usable()`, `to_dict()`, `state_chain`, `status`, `health`, `cpu/memory_gb/gpu/gpu_memory_gb/storage_gb/docker`, `cost_class`, `capabilities`, `reason`, `transport`), `Transport`/`SshTransport`/`HttpsAgentTransport` (`available()`, `run(argv, timeout)`), `discover(verify=True)`, `verify_job()`, `meets_requirements(host, req)`, `remote_status()`. | "remote:\<id\>" abstraction. SSH/HTTPS transport with real `run`. `discover()` reads `JARVIS_REMOTE_HOST_URL`/`JARVIS_REMOTE_HOST_TRANSPORT`. |
| `brain_fabric.py` (1410 lines) | `assert_no_secrets(payload, _path="") -> list[str]` (the secret-leak gate for fabric output), `discover_brain()`, `discover_silverwing()`, `external_status()`, `docker_status()`, `pipeline_readiness()`, `nvidia_deployment_readiness()`, `fabric_overview()`, `integration_matrix()`, `brain_lifecycle()`, `silverwing_lifecycle()`, `contradictions()`, `development_status()`, `_kaggle_real_status()`, `_hf_real_status()`. | Brain/Silverwing lifecycle + contradiction detection. |
| `gateway.py` (1215 lines) | `ProviderGateway` + `_ensure_provider_fabric_import_path()`. | ProviderGateway location + sys.path bootstrap. |
| `execution_fabric.py` (1255) | `BrainAgent`, job execution runtime. | |

### Existing registries  (`F:\AI\Jarvis-super-intelligence-/infrastructure/`)
| File | Symbols | Notes |
|------|---------|-------|
| `job_registry.py` (709) | `JobType` (enum), `JobStatus` (QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED), `JobRecord` (SQLAlchemy), `JobInfo` (`from_record`), `JobRegistry` (`get_instance`, `create_job(job_info)`, `get(job_id)`, `update_status(...)`, `list_jobs(...)`, `cancel_job(job_id, reason)`, `archive_job`, `add_artifact(job_id, artifact_id, artifact_type)`, `set_resource_allocation`, `set_cost`, `get_job_cost`, `reset_instance`). | The **JobRegistry** compute jobs use (Phase 9 §8). |
| `artifact_registry.py` (577) | `ArtifactType` (enum), `ArtifactStatus`, `ArtifactRecord`, `ArtifactInfo` (`from_record`), `ArtifactRegistry` (`get_instance`, `register(artifact_info)`, `get`, `list_artifacts`, `update_status`, `record_access`, `link_to_model`, `get_artifacts_by_model`, `get_artifacts_by_training_run`, `get_parent_chain`, `compute_checksum`). | **ArtifactRegistry** (Phase 9 §7). |
| `model_registry.py` | `ModelRegistry` (`get_instance`, `list_models`). | **ModelRegistry**. |
| `promotion_gate.py` (531) | `PromotionOutcome` (enum), `EvaluationCriteria`, `PromotionDecision`, `PromotionGate` (`get_model_info`, `evaluate_for_promotion(model_id, criteria)`, `promote_model(...)`, `block_model`, `approve_model`, `deploy_model`, `get_promotion_history`, `list_blocked_models`), `get_promotion_gate()`, `get_*_criteria()`. | **PromotionGate** (Phase 9 §7). |

### Capability contract + Brain integration  (`F:\AI/research_engine/`, `F:\AI/jarvis_brain/`)
| File | Symbols | Notes |
|------|---------|-------|
| `research_engine/capability_tools.py` (1134 true lines) | 88 `Tool` classes incl. **`ComputeSelectTool`** (`compute.select`), `NvidiaInferenceTool` (`nvidia.inference`), `NvidiaModelsTool` (`nvidia.models`), `NvidiaDeploymentTool`, `KaggleStatusTool` (`kaggle.status`), `KaggleJobsTool` (`kaggle.jobs`), `HuggingFaceStatusTool`/`HuggingFaceArtifactsTool`, `RemoteComputeStatusTool`/`HealthTool`/`ResourcesTool`/`VerifyTool`, `DockerRemote*` (6), `CloudStatusTool`/`CloudResourcesTool`/`ExecutionModeTool`, `BrainStatusTool`/`BrainLifecycleTool`/`BrainArtifactsTool`, `Silverwing*`, `TrainingStatusTool`, `Development*`, `CapabilityDiscoverTool`/`CapabilityCatalogueTool`. | **The compute fabric already exposes compute tools** — but under **vendor-scoped / area-scoped names**, not the canonical `compute.*` namespace Phase 9 §3 requires. `build_capability_registry()` registers them; `ToolRegistry.invoke(name, args, ctx) -> ToolResult` is the single dispatch boundary. |
| `research_engine/capability_contract.py` (663) | `CapabilityContract` dataclass (id,name,domain,...,availability,authentication_required,required_permissions,risk_level,supports_streaming,supports_async,supports_offline,supports_background_jobs,service_dependencies,provider_dependencies,cost_model,timeout,retry_policy,audit_policy), `DomainPack`, `_META` table (per-capability metadata; `compute.select` is `domain=infrastructure, supports_offline=True, cost_model=local_compute, timeout=60`), `discover_capabilities`, `capability_catalogue`, `build_contracts`. | This is what the **Brain's available-capability pack** is built from. Missing `_META` entries for the canonical `compute.*` set → they are invisible to domain-filtered discovery. |
| `research_engine/tool_registry.py` (857) | `Tool` (ABC; `name/description/schema/risk/requires_confirmation` + abstract `invoke`), `ToolContext` (dataclass), `DefaultPermissionPolicy`, `Permission`/`PermissionPolicy`, `resolve_permissions`, `permission_granted`, `scrub_secrets(text)->(str,bool)`, `_SECRET_PATTERNS`. | Secret-scrubbing boundary; `invoke`/`authorize`/`describe` are the dispatch surface. |
| `research_engine/models.py` (371) | `RiskLevel` {READ,EXEC,WRITE,NETWORK,ADMIN}, `ToolResult` (fields + `to_model_view()`), `ToolCall`, `Evidence`, `SourceType`. | `ToolResult.to_model_view()` is the ONLY model-facing view. |
| `research_engine/verification.py` | `VerificationEngine`. | |
| `jarvis_brain/contract.py` … `orchestrator.py` | `BrainOrchestrator` (PLAN→EXECUTE→OBSERVE→VERIFY→REASON→REPLAN, single-terminal, approval-gate, conversation-linked, budget-enforced), `PlanValidator` (schema→capability existence→I/O compat→permission→risk→execution-mode→dependency→replan), `TaskBudget` (max_plan_iterations=3,max_retries=3,max_replans=2,max_execution_time=300,max_cost=1.0; token→USD `tokens/1000*rate`; strict `>` counters), `Protocol` state machine (`PLAN_VALIDATED→PLAN_AUTHORIZED→EXECUTION_STARTED`; `PLAN_AUTHORIZED` now correctly emitted on replan paths), `ContextEngine.build()` (bounded ≤12 capability discovery/artifacts/brain-state; `_scrub_artifacts`/`scrub_secrets`), adapters (`ModelBrainAdapter`, `DeterministicBrainAdapter`, `BrainAvailability`). | **Phase 8 — green, do NOT rebuild.** |

### Identity / auth  (`F:\AI/identity/`)
`rbac.py` (`PermissionEngine`, `identity/router.py`), `oidc.py`, `session.py`, `audit_log.py`, `linking.py`, `models.py`, `owner.py`. Reused for API routes + capability authorization.

## 4. Capability fabric today (the 88 tools, `build_capability_registry`)

`compute.*` canonical names are **ABSENT**. Present are:

- `compute.select` (delegates to `cloud_fabric.select_compute`)
- vendor-scoped: `nvidia.inference` / `nvidia.models` / `nvidia.deployment`, `kaggle.status` / `kaggle.jobs`, `huggingface.status` / `huggingface.artifacts`
- area-scoped: `remote.compute.{status,health,resources,verify}`, `cloud.{status,resources,execution_mode}`, `docker.*`, `docker.remote.*`
- read-only views: `provider.status`, `job.status`, `artifact.inspect`, `model.status`

`compute.select` already returns a real selected target + reason + fallback chain (or `RESOURCE_UNAVAILABLE`). The rest are **status/verification** views, not canonical **execution** contracts.

## 5. The genuine Phase 9 gap (no rebuild needed)

1. **Canonical `compute.*` contract namespace** (Phase 9 §3): `compute.discover/verify/inference/training/evaluation/embedding/artifact_upload/artifact_download/job_submit/job_status/job_cancel/resource_health` — as **thin capability tools** delegating to existing infra (`cloud_fabric`, `ProviderRouter`, `NvidiaAdapter.chat`, `brain_training/kaggle`, `JobRegistry`, `ArtifactRegistry`, `PromotionGate`, `ProviderControlCenter`). Registered in the existing `ToolRegistry` + `capability_contract._META`.
2. **Canonical `ComputeResource`** with the full truthful state chain (§2) — `cloud_fabric.cloud_resources()` already produces it; Phase 9 exposes it through the canonical contract.
3. **Deterministic `ComputeSelector`** (§4) — `cloud_fabric.select_compute()` already implements it; Phase 9 adds the canonical policy table + failure-state mapping + mode awareness and exposes it as `compute.select`.
4. **Brain ↔ control plane wiring** — the Phase 8 orchestrator already dispatches any registered tool via `ToolRegistry.invoke` and replans on failure. Adding `compute.*` tools + metadata to `capability_contract` makes them appear in the Brain's available-capability pack automatically and route through the existing `PLAN→EXECUTE→OBSERVE→VERIFY→REASON→REPLAN` loop + `TaskBudget`. No orchestrator rewrite needed; just (a) register canonical tools, (b) ensure compute failures map to `PROVIDER_UNAVAILABLE`/`RESOURCE_UNAVAILABLE` and reach the reassessment path, (c) keep `PLAN_AUTHORIZED` emitted before `EXECUTION_STARTED` (already fixed in Phase 8).
5. **Credential isolation** — already enforced by `ProviderAdapter._guard_context` + `ToolRegistry`/`ToolResult.to_model_view()` + `brain_fabric.assert_no_secrets`. Phase 9 proves it with red-team tests and never bypasses it.

## 6. Reuse checklist (what Phase 9 must NOT recreate)

| Do NOT rebuild | Reuse instead |
|----------------|---------------|
| ProviderGateway / ModelRouter / ModelRegistry | `providers.ProviderRouter` + `ProviderRegistry` + `ProviderControlCenter` + `models.py` |
| SecretManager / credential store | `providers.secrets.SecretManager` |
| JobRegistry / ArtifactRegistry / PromotionGate | `infrastructure.job_registry` / `artifact_registry` / `promotion_gate` |
| Provider health / TTL cache | `providers.health.HealthCache` / `ProviderControlCenter` |
| Kaggle / NVIDIA / HF adapters | `brain_training/kaggle.py`, `providers.nvidia.*`, `providers.huggingface.*` |
| remote:<id> host exec | `jarvis_backend.remote_host` |
| Local hardware detection | `jarvis_backend.cloud_fabric.local_hardware` |
| Capability tool dispatch + authorization + scrubbing | `research_engine.tool_registry.ToolRegistry` + `ToolResult.to_model_view()` + `scrub_secrets` |
| Capability catalogue / discovery | `research_engine.capability_contract` |
| Brain orchestration / plan validation / budget / protocol | `jarvis_brain/*` (Phase 8, green) |

## 7. Immediate next step

Write `docs/PHASE9_PLAN.md` (implementation map with concrete delegation), then implement the thin canonical `compute.*` layer in `jarvis_compute/` on top of the above, register it, and add the security/no-fabrication/truthfulness tests that are **green in this sandbox** (all providers report UNCONFIGURED/OFFLINE) plus env-gated live-provider E2E tests.
