# JARVIS Brain v1 — Deployment & Model Switching

> This document was previously named `JARVIS_BRAIN_DEPLOYSHIP.md`; renamed to
> `JARVIS_BRAIN_DEPLOYMENT.md` to match the spec artifact name (content unchanged).

## 1. Runtime contract (§3) — unchanged from Phase 1

| Property        | Value                                  |
|-----------------|----------------------------------------|
| host            | `127.0.0.1`                            |
| port            | `8011` (separate from Silverwing `:8010`) |
| protocol        | HTTP                                   |
| API style       | OpenAI-compatible                      |
| base path       | `/v1`                                  |
| health          | `/health`                              |
| models          | `/v1/models`                           |
| chat            | `/v1/chat/completions`                 |
| auth            | `Authorization: Bearer <JARVIS_BRAIN_API_KEY>` |

Auth rejects **missing / invalid / malformed** Authorization with `401
Unauthorized`; credentials are redacted in logs/telemetry/errors/audit/debug
(§5). The runtime is **model-provider agnostic**: `brain_runtime/backends/`
supports the real `TransformersBackend` (Qwen3-4B) and a `StubBackend` explicitly
labeled `stub` that reports `production_health=false`.

## 2. Model switching (§22)

`JARVIS_BRAIN_MODEL` selects the served model **without frontend or gateway
changes**:

```env
# Base model candidate
JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-v1
# SFT candidate (default)
JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1
```

The Brain runtime resolves both from `BrainCatalog` (`brain_runtime/model_registry.py` /
`BRAIN_LINEAGE.md`):

| JARVIS_BRAIN_MODEL       | Backend loads                          | training_method | status     |
|--------------------------|----------------------------------------|-----------------|------------|
| `jarvis-brain-qwen3-4b-v1` | Qwen3-4B-Base                          | `base`          | experimental |
| `jarvis-brain-qwen3-4b-sft-v1` | Qwen3-4B-Base + SFT LoRA adapter (remote HF) | `sft`           | training (not published) |

Model selection happens **inside** the Brain runtime; the gateway treats Brain
as a single upstream and is unaware of which variant is loaded — the frontend
is similarly agnostic.

## 3. Local model location (§7)

Qwen3-4B weights are **never** in the source tree. Resolution order:

1. `JARVIS_BRAIN_MODEL_CACHE` / `JARVIS_BRAIN_MODEL_REPO` (defaults to
   `F:/AI/.sw_cache` / `F:/AI/silverwing-models` per `_env.py`)
2. the Brain runtime's local model cache
3. HuggingFace Hub (remote, when `JARVIS_BRAIN_BACKEND=transformers` and a GPU
   backend is available)

Weights are git-ignored and excluded from commits. On this dev box
(8 GB RAM, no CUDA) the transformers backend loads **offline** and reports
`available=false, stub=true` — it never downloads shards (verified:
`test_real_transformers_offline_no_download`).

## 4. Deployment profiles (§19)

`brain_training/deploy.py:load_config()` defines three profiles:

| Profile      | Endpoint                              | Notes                                  |
|--------------|---------------------------------------|----------------------------------------|
| `dev`        | `http://127.0.0.1:8011/v1`            | local stub / local transformers backend |
| `local_stub` | `http://127.0.0.1:8011/v1`            | same as dev; for acceptance tests      |
| `remote`     | `https://<brain-inference-service>/v1` | HF Inference Endpoints / Kaggle GPU   |

`jarvis-brain-qwen3-4b-sft-v1` is promoted to `remote` only after it passes
the §18 promotion gate; the dev default stays on `:8011`.

## 5. Serving recipe (remote, GPU host)

```bash
# remote GPU host (Kaggle/GCP) — loads the validated SFT adapter from HF
export JARVIS_HF_TOKEN=<server-side only>
python -m brain_runtime --host 0.0.0.0 --port 8011 \
    --model jarvis-brain-qwen3-4b-sft-v1 \
    --backend transformers --device cuda
```
The runtime exposes `/health` with `available=true, stub=false,
production_health=true` once the adapter loads and a generation smoke test
passes. The Model Gateway then routes live traffic to the Brain; if Brain
health degrades, the gateway transparently falls back to Silverwing `:8010`
(verified by `tests/test_jarvis_brain_gateway.py`).

## 6. Model lifecycle transitions (§18)

```
experimental (SFT candidate, not published)  --requires-->  candidate
candidate  --requires baseline+SFT+comparison+scan+smoke-->  validated
validated  --MANUAL approval only-->  promoted  -> remote :8011
```
A transition never fires automatically on training completion (§18). Operators
gate via `python -m brain_training gate <stage>` / `promote.py`.
