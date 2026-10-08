# Silverwing Capability Registry

This document describes the `ModelSpec` data model, the `ModelClass`
taxonomy, and the `_infer_model_classes` mapping that bridges the static
model catalog (`backend/model_catalog.py`) to the rich capability tags
used by the `ModelRouter`.

The canonical, machine-readable source of truth is `backend/model_provider.py`
(class `ModelSpec`) and `backend/model_catalog.py` (class `ModelInfo`).

---

## 1. ModelSpec Fields

`ModelSpec` (Pydantic `BaseModel`, defined in `model_provider.py`)
is the mutable registry entry that extends the static `ModelInfo`
from the catalog with runtime health and cost-tracking fields.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | *(required)* | Canonical key, e.g. `"openai:gpt-5.6-sol"` |
| `provider` | `str` | *(required)* | Provider name (see §3) |
| `deployment` | `str` | `""` | Deployment label (e.g. `"openai"`, `"ollama"`) |
| `model_id` | `str` | *(required)* | Provider-native model identifier |
| `name` | `str` | `""` | Human-readable name |
| `description` | `str` | `""` | Short description |
| `context_length` | `int` | `0` | Context window size in tokens |
| `max_output_tokens` | `int` | `0` | Maximum output tokens |
| `modality` | `List[str]` | `[]` | Modalities supported (text, image, audio, etc.) |
| `capabilities` | `List[str]` | `[]` | Capability tags (see §2) |
| `model_classes` | `List[str]` | `[]` | `ModelClass` taxonomy tags (see §4) |
| `pricing_input` | `Optional[float]` | `None` | USD per 1M input tokens |
| `pricing_output` | `Optional[float]` | `None` | USD per 1M output tokens |
| `free_tier` | `bool` | `False` | Has a free or generous free tier |
| `open_weights` | `bool` | `False` | Can be self-hosted (HF / llama.cpp / Ollama) |
| `license` | `str` | `""` | License type |
| `commercial_use` | `str` | `""` | Commercial use permissions |
| `local_availability` | `str` | `""` | Self-hosting availability notes |
| `api_availability` | `str` | `""` | API availability notes |
| `supported_engines` | `List[str]` | `[]` | Compatible serving engines |
| `hardware_requirements` | `str` | `""` | Minimum hardware notes |
| `latency_ms` | `Optional[float]` | `None` | Measured inference latency |
| `benchmark_score` | `Optional[float]` | `None` | Normalized benchmark score |
| `status` | `HealthStatus` | `UNKNOWN` | Current health status (see §5) |
| `privacy` | `str` | `"public"` | Default privacy level |
| `last_check` | `float` | `0.0` | Epoch seconds of last health check |
| `health_history` | `List[Dict]` | `[]` | Rolling log of health transitions |

---

## 2. Capability Tags

Capability tags are free-form strings on `ModelSpec.capabilities` that
describe what a model can do. They are sourced from the static catalog's
`ModelInfo.capabilities` field and include:

| Tag | Description |
|-----|-------------|
| `reasoning` | Complex reasoning, chain-of-thought |
| `coding` | Code generation and understanding |
| `vision` | Image understanding / multi-modal |
| `tool-use` | Function calling / tool use |
| `multilingual` | Multiple language support |
| `audio` | Speech-to-text / text-to-speech |
| `embeddings` | Text embedding generation |
| `image-gen` | Image generation |
| `memory-retrieval` | Memory-augmented retrieval (Silverwing-specific) |

These tags are used by `ModelRegistry.by_capability()` and by the
`task`-based filtering in `ModelRouter.select()`.

---

## 3. Provider Registry

The `ModelRegistry` builds its entries from two sources:

1. **Static catalog** (`MODEL_CATALOG` in `model_catalog.py`) — 53 entries
   covering 12 providers, loaded at startup.
2. **Persistent JSON store** (`model_registry.json`) — runtime health
   and latency updates that survive restarts. If the file exists and
   is valid, it overrides the static catalog; otherwise the registry
   is built from the catalog.

The `ModelManager` (`model_provider.py`) registers 12 provider classes.
Each provider maps to a canonical name in `_PROVIDER_ALIASES`:

| Canonical name | Aliases |
|----------------|---------|
| `openai` | `openai-compatible` |
| `anthropic` | `claude` |
| `google` | `gemini` |
| `groq` | `groqcloud` |
| `deepseek` | `deepseekai` |
| `ollama` | — |
| `llamacpp` | `llama_cpp`, `llamacpp_server` |
| `bedrock` | `aws_bedrock` |
| `vertex` | `vertexai`, `vertex_ai` |
| `local` | — |
| `silverwing` | — |
| `vllm` | — |

### Provider Availability in Test Environment

| Provider | Available? | Reason |
|----------|-----------|--------|
| `local` | Yes | No credentials needed (deterministic echo) |
| `silverwing` | Yes | Always available; echoes or uses local server |
| `openai` | No | `OPENAI_API_KEY` not set |
| `anthropic` | No | `ANTHROPIC_API_KEY` not set |
| `google` | No | `GEMINI_API_KEY` not set |
| `groq` | No | `GROQ_API_KEY` not set; `groq` SDK not installed |
| `deepseek` | No | `DEEPSEEK_API_KEY` not set |
| `bedrock` | No | No AWS credentials |
| `vertex` | No | `google-cloud-aiplatform` not installed; no creds |
| `ollama` | No | `OLLAMA_HOST` not set |
| `llamacpp` | No | `LLAMACPP_API_BASE` not set |
| `vllm` | No | `VLLM_API_BASE` not set |

---

## 4. ModelClass Taxonomy

`ModelClass` (Pydantic `str` enum, defined in `model_provider.py`)
provides a richer classification than raw capability tags. These tags
are used by `TASK_TO_CLASSES` in the router and by
`_infer_model_classes()`.

| Enum member | Value | Description |
|-------------|-------|-------------|
| `LOCAL_OPEN_WEIGHT` | `"LOCAL_OPEN_WEIGHT"` | Open-weight models runnable locally |
| `LOCAL_PROPRIETARY` | `"LOCAL_PROPRIETARY"` | Proprietary models served locally |
| `CLOUD_API` | `"CLOUD_API"` | Cloud-hosted paid API |
| `FREE_TIER` | `"FREE_TIER"` | Has a free usage tier |
| `PAID_API` | `"PAID_API"` | Paid API, no free tier |
| `SPECIALIZED` | `"SPECIALIZED"` | Domain-specialized (e.g. coder models) |
| `EMBEDDING` | `"EMBEDDING"` | Embedding models |
| `VISION` | `"VISION"` | Vision / multimodal models |
| `AUDIO` | `"AUDIO"` | Audio models |
| `CODE` | `"CODE"` | Code-generation models |
| `REASONING` | `"REASONING"` | Reasoning-focused models |
| `RESEARCH` | `"RESEARCH"` | Research-grade models |
| `SMALL_EDGE` | `"SMALL_EDGE"` | Small, edge-deployable models |
| `LARGE_FRONTIER` | `"LARGE_FRONTIER"` | Large frontier-scale models |

---

## 5. `_infer_model_classes` Mapping

`_infer_model_classes(info: ModelInfo) -> List[str]` infers the
appropriate `ModelClass` tags from a `ModelInfo`'s capabilities,
metadata, and serving endpoints. This bridges the static catalog (which
uses simple capability tags) to the broader taxonomy.

### Inference rules (applied in order):

1. **Open weights check:**
   - If `info.open_weights` is `True`:
     - If any serving endpoint is `"ollama"`, `"llamacpp"`, or `"vllm"`
       → add `LOCAL_OPEN_WEIGHT`
     - Else if no serving endpoint is `"openai"`, `"anthropic"`, `"google"`,
       `"groq"`, `"bedrock"`, or `"vertex"`
       → add `LOCAL_OPEN_WEIGHT` (self-hosted only)
     - Otherwise → add `CLOUD_API`
   - Else → add `CLOUD_API`

2. **Capability-based classes:**

   | Capability tag | ModelClass added |
   |----------------|-----------------|
   | `reasoning` | `REASONING` |
   | `coding` | `CODE` |
   | `vision` or `multimodal` | `VISION` |
   | `audio` | `AUDIO` |
   | `embeddings` | `EMBEDDING` |

3. **Free tier:** If `info.free_tier` is `True` → add `FREE_TIER`

4. **Size heuristics (based on `context_length`):**
   - `>= 1_000_000` tokens → add `LARGE_FRONTIER`
   - `< 32_000` tokens → add `SMALL_EDGE`

5. **Specialized:** If the family name contains `"coder"` or `"code"`
   → add `SPECIALIZED`

### Example mappings:

| Model | Open weights? | Context | Capabilities | Inferred classes |
|-------|--------------|---------|-------------|-----------------|
| `openai:gpt-5.6-sol` | No | 2 000 000 | reasoning, coding, vision, tool-use, multilingual | `CLOUD_API`, `REASONING`, `CODE`, `VISION`, `LARGE_FRONTIER` |
| `anthropic:claude-opus-5` | No | 1 000 000 | reasoning, coding, vision, tool-use, multilingual | `CLOUD_API`, `REASONING`, `CODE`, `VISION`, `LARGE_FRONTIER` |
| `google:gemini-2.5-pro` | No | 1 000 000 | reasoning, coding, vision, tool-use, multilingual | `CLOUD_API`, `REASONING`, `CODE`, `VISION`, `LARGE_FRONTIER` |
| `deepseek:deepseek-v4-pro` | No | 64 000 | reasoning, coding, tool-use | `CLOUD_API`, `REASONING`, `CODE` |
| `groq:llama-3.3-70b-versatile` | Yes | 131 072 | coding, multilingual, tool-use | `LOCAL_OPEN_WEIGHT`, `CODE` |
| `silverwing:silverwing-decoder-v2` | Yes | 32 768 | reasoning, coding, tool-use, memory-retrieval | `LOCAL_OPEN_WEIGHT`, `REASONING`, `CODE` |
| `silverwing:silverwing-embed-v1` | Yes | 8 192 | embeddings, memory-retrieval | `LOCAL_OPEN_WEIGHT`, `EMBEDDING` |
| `local:local-rule` | No | 0 | reasoning, tool-use, memory-retrieval | `CLOUD_API` |

---

## 6. Registry Persistence

`ModelRegistry.save()` writes the current state to a JSON file
(default: `model_registry.json`, configurable via
`SILVERWING_REGISTRY_PATH`). The file contains:

```json
{
  "models": [ { ...ModelSpec.model_dump()... }, ... ],
  "updated_at": 1234567890.0
}
```

`update_health()` records a health transition:

```python
spec.status = new_status
spec.last_check = time.time()
spec.health_history.append({
    "timestamp": time.time(),
    "from": old_status.value,
    "to": new_status.value,
})
```

Health history is capped at 50 entries per model.

---

## 7. HealthStatus Enum

| Value | Meaning |
|-------|---------|
| `AVAILABLE` | Provider/model is online and ready |
| `DEGRADED` | Available but with degraded performance |
| `RATE_LIMITED` | Rate-limited; requests may fail |
| `OFFLINE` | Provider/model is not reachable |
| `AUTH_ERROR` | Credentials missing or invalid |
| `DEPRECATED` | Model is deprecated; use alternatives |
| `UNKNOWN` | Health not yet checked |

When the registry is built from the static catalog, `local` models are
marked `AVAILABLE`; all others start as `UNKNOWN`.

---

## 8. Catalog Summary

The static `MODEL_CATALOG` contains **53** model entries across **12**
providers and **25** families, including:

- **OpenAI GPT-5.x** (3 models) + GPT-OSS open weights (2 models)
- **Anthropic Claude 5** (6 models) + Claude 3.5 (1 model)
- **Google Gemini** (5 models) + Gemma (1 model)
- **Llama 4** (7 models via Bedrock, Ollama, Vertex, Groq)
- **Qwen 3.x** (7 models via multiple providers)
- **DeepSeek** (4 models)
- **Amazon Nova** (2 models via Bedrock)
- **Silverwing** (2 models: decoder + embed)
- **Local** (1 deterministic fallback model)

20 of the 53 entries are open-weight and can be self-hosted.
