# Silverwing Model Routing Policy

This document describes the routing algorithm used by `ModelRouter`
(`backend/model_provider.py`) and exposed via the `POST /api/models/route`
HTTP endpoint.

The router selects an optimal model for each request based on four primary
constraints — **capability**, **privacy**, **latency**, and **cost** — while
consulting the persistent `ModelRegistry` for model metadata and the
`ModelManager` for live provider availability.

---

## 1. Routing Decision Input

The `POST /api/models/route` endpoint accepts an optional JSON body:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task` | `str` | `""` | High-level task category (see §3) |
| `requested_capability` | `str` | `""` | Capability tag (e.g. `coding`, `reasoning`) |
| `requested_privacy` | `str` | `"public"` | Privacy level (see §4) |
| `requested_latency` | `str` | `"normal"` | Latency preference |
| `requested_cost` | `str` | `"best_quality"` | Cost policy (see §5) |

The `ModelRouter.select()` method accepts the same parameters directly:

```python
decision: RoutingDecision = router.select(
    capability="coding",
    privacy="public",
    latency="normal",
    cost="best_quality",
    task="coding",
)
```

---

## 2. RoutingDecision Output

Every routing decision produces a `RoutingDecision` Pydantic model with
full provenance:

| Field | Type | Description |
|-------|------|-------------|
| `task` | `str` | Resolved task label |
| `requested_capability` | `Optional[str]` | Capability that was requested |
| `requested_privacy` | `str` | Privacy level that was requested |
| `requested_latency` | `str` | Latency preference |
| `requested_cost` | `str` | Cost policy that was applied |
| `selected_model` | `str` | Chosen model (`provider:model_id`) |
| `provider` | `str` | Selected provider name |
| `reason` | `str` | Human-readable explanation |
| `fallback` | `Optional[str]` | Ultimate fallback model |
| `fallback_chain` | `List[str]` | Ordered list of fallback candidates |
| `latency_ms` | `float` | Measured latency (0 for pure routing) |
| `cost_estimate` | `float` | Estimated USD cost (0 for local) |
| `request_id` | `str` | UUID for tracing |
| `timestamp` | `float` | Epoch seconds |
| `success` | `bool` | Always `True` from `select()` |
| `error` | `Optional[str]` | Error message if routing failed |

---

## 3. Capability / Task → ModelClass Mapping

The `TASK_TO_CLASSES` dictionary maps high-level task labels to ordered
lists of `ModelClass` tags. The router filters the catalog to models that
have **at least one** of the required `ModelClass` tags.

| Task | ModelClass tags (in priority order) |
|------|--------------------------------------|
| `coding` | `CODE`, `LOCAL_OPEN_WEIGHT`, `LARGE_FRONTIER` |
| `deep_reasoning` | `REASONING`, `LARGE_FRONTIER` |
| `fast_response` | `SMALL_EDGE`, `FREE_TIER` |
| `multimodal` | `VISION`, `LOCAL_OPEN_WEIGHT`, `LARGE_FRONTIER` |
| `research` | `RESEARCH`, `LARGE_FRONTIER`, `REASONING` |
| `embedding` | `EMBEDDING`, `LOCAL_OPEN_WEIGHT` |
| `small_edge` | `SMALL_EDGE`, `LOCAL_OPEN_WEIGHT` |

When `task` is set, the router also queries `registry.by_capability(task)`
directly (matching against the `capabilities` list on each `ModelSpec`).

---

## 4. Privacy Filtering

Requests carry a privacy level that constrains which providers are eligible.
The `PrivacyPolicy` class maps each provider to a privacy classification:

| Provider | Classification |
|----------|----------------|
| `local` | private |
| `silverwing` | private |
| `ollama` | private |
| `llamacpp` | private |
| `vllm` | private |
| `openai-compatible` | private |
| `bedrock` | internal |
| `vertex` | internal |
| `openai` | public |
| `anthropic` | public |
| `google` | public |
| `groq` | public |
| `deepseek` | public |

The `PrivacyLevel` enum defines request levels:

| Level | String value | Allowed provider classifications |
|-------|-------------|----------------------------------|
| `PUBLIC` | `"public"` | public, internal, private, sensitive |
| `INTERNAL` | `"internal"` | internal, private, sensitive |
| `PRIVATE` | `"private"` | private, sensitive |
| `SENSITIVE` | `"sensitive"` | sensitive |

When `privacy` is `"public"` or `""`, no privacy filtering is applied.
For stricter levels, `PrivacyPolicy.is_allowed(provider, privacy_level)`
checks whether the provider's classification is permitted.

---

## 5. Cost Policy → Provider Preference

The `COST_POLICY_PROVIDERS` dictionary defines an ordered provider
preference for each cost policy. After capability and privacy filtering,
candidates are partitioned: providers in the preference list come first
(preserving catalog order), followed by all other eligible providers.

| CostPolicy | Provider preference order |
|------------|--------------------------|
| `free_only` | `local`, `silverwing`, `ollama`, `llamacpp` |
| `local_only` | `local`, `silverwing`, `ollama`, `llamacpp` |
| `low_cost` | `groq`, `deepseek`, `ollama`, `llamacpp`, `silverwing`, `local` |
| `best_quality` | `openai`, `anthropic`, `vertex`, `bedrock`, `google`, `groq`, `deepseek`, `silverwing`, `ollama`, `llamacpp`, `local` |
| `low_latency` | `groq`, `openai`, `silverwing`, `ollama`, `local` |
| `private_only` | `local`, `silverwing`, `ollama`, `llamacpp` |

---

## 6. Selection Algorithm (step by step)

1. **Determine available providers.**
   `ModelManager._providers` is iterated; `provider.is_available()`
   must return `True`. In the test environment (no API keys), only
   `local` and `silverwing` are available.

2. **Start with the full registry.**
   `registry.list()` returns all `ModelSpec` entries (53 in the static
   catalog).

3. **Filter by availability.**
   Keep specs whose `provider` is in the available providers list **or**
   whose `open_weights` flag is `True` (open-weight models can be
   self-hosted).

4. **Filter by model class.**
   If `model_classes` is explicitly provided, keep specs that have at
   least one matching class. If `capability` is set (but `model_classes`
   is not), look up `TASK_TO_CLASSES[capability]` and filter by those
   classes. If nothing matches, fall back to `registry.by_capability()`.

5. **Filter by task capability.**
   If `task` is non-empty, `registry.by_capability(task)` overrides the
   spec list entirely.

6. **Filter by privacy.**
   Non-public privacy levels remove providers that are not allowed.

7. **Filter by cost policy.**
   Partition specs into "preferred" (from `COST_POLICY_PROVIDERS`) and
   "others", then concatenate preferred + others.

8. **Sort candidates.**
   Primary key: `-benchmark_score` (higher is better).
   Secondary key: `pricing_input` ascending (cheaper first) — only when
   cost policy is `low_cost` or `free_only`; otherwise `0.0`.
   Tertiary key: `-latency_ms` (lower latency first).

9. **Select the first available model.**
   Walk the sorted list; the first spec whose provider's `is_available()`
   returns `True` is selected. Unavailable candidates are added to the
   `fallback_chain` (capped at 5 entries).

10. **Ultimate fallback.**
    If no available model is found, use
    `silverwing:silverwing-decoder-v2` (if Silverwing or Local is
    available), otherwise `local:local-rule`.

11. **Log observability event.**
    A `model.routing` event is recorded in the `EventLog` with the
    provider, model, request_id, and privacy provenance.

---

## 7. Fallback Chain

The `fallback_chain` field in `RoutingDecision` lists up to 5 model IDs
that were viable candidates but skipped because their provider was
unavailable. This provides full visibility into what the router would
have chosen if the primary model's provider were online.

The `fallback` field holds the ultimate safety-net model:
- `silverwing:silverwing-decoder-v2` (when Silverwing or Local is available)
- `local:local-rule` (when neither Silverwing nor Local is available)

When the selected model **is** the ultimate fallback, `fallback` is `None`.

---

## 8. Default Behavior

With all parameters at their defaults (`capability=""`, `privacy="public"`,
`latency="normal"`, `cost="best_quality"`, `task=""`):

- The router selects from all available + open-weight specs.
- In the test environment: `local:local-rule` is selected (it is always
  available) with `silverwing:silverwing-decoder-v2` as the fallback.
- When `task="coding"`: `silverwing:silverwing-decoder-v2` is selected.

---

## 9. Observability

Every `select()` call emits an `ObservabilityEvent` with:

- `event_type = "model.routing"`
- `request_id` (UUID)
- `provider` and `model` of the selected model
- `status = "ok"`
- `fallback` (the ultimate fallback, if applicable)
- `provenance` = the privacy level

The `route_and_chat()` method additionally emits:
- `model.request` (before execution)
- `model.started` (after completion)
- `model.completed` (with token counts and latency)
- `model.error` + `model.fallback` (on failure, with fallback to local)

Event logs are accessible via `router.events.get(event_types=..., request_id=...)`.

---

## 10. HTTP Endpoint

```
GET  /api/models/health  — returns per-provider health status
POST /api/models/route   — returns a RoutingDecision as JSON
```

Both endpoints are imported defensively: if `model_provider` fails to
import, they return an error dict without crashing the backend.
