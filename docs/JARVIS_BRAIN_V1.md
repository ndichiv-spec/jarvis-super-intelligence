# JARVIS Brain v1 — Overview

Single source of truth for the **JARVIS Brain v1** model runtime + training/deployment
lifecycle. This document ties together Phase 1 (runtime) and Phase 2 (training ops).

> **Spec anchor**: section 1 — dedicated Brain endpoint; section S30 — no
> fabrication. Every status below is the *actual observed* state on this dev box,
> re-verifiable via `python -m brain_training status`.

## 1. Endpoints

| Service      | URL                        | Runtime            |
|--------------|----------------------------|--------------------|
| JARVIS Brain | `http://127.0.0.1:8011/v1` | Qwen3-4B Base / SFT |
| Silverwing   | `http://127.0.0.1:8010`    | silverwing-120M    |

Silverwing is **untouched** by this phase. The Brain is a **separate runtime**
(§1). The Model Gateway (`/jarvis_backend/gateway.py`) is the only abstraction
boundary; the frontend is model-agnostic and never chooses a backend.

## 2. Model line

Lineage lives in `brain_runtime/BRAIN_LINEAGE.md` and
`brain_runtime/model_registry.py` (`BrainCatalog`). **Qwen3-4B weights are NEVER
in the source tree** (§7):

| Variant | Model ID                | Base                  | Params        | Training method | Status        |
|---------|-------------------------|-----------------------|---------------|-----------------|---------------|
| Base    | `jarvis-brain-qwen3-4b-v1` | `Qwen/Qwen3-4B-Base` | 4,004,667,392 | base            | experimental  |
| SFT     | `jarvis-brain-qwen3-4b-sft-v1` | `Qwen/Qwen3-4B-Base` | 4,004,667,392 | sft (LoRA/QLoRA) | training (not published) |

Switching `JARVIS_BRAIN_MODEL` between the two changes the served model **without
frontend changes** (model switching, §22). The SFT is a **true adapter** — it is
**never** reported as a merged model unless an actual merge+verify is performed
(§9).

## 3. Environment

```env
JARVIS_BRAIN_ENDPOINT=http://127.0.0.1:8011/v1
JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1      # or ...-qwen3-4b-v1 (base)
JARVIS_BRAIN_BACKEND=transformers
JARVIS_HF_TOKEN=<server-side only>                   # preferred HF token var
JARVIS_ADMIN_EMAIL=ndichiv@gmail.com
```

Secrets are sourced from `.env` / the OS by the launcher (`_env.py`
`os.environ.setdefault`); they are never hardcoded, never printed, and never sent
to the frontend (§4/§5). The `JARVIS_BRAIN_API_KEY` authenticates Brain requests
(`Authorization: Bearer <key>`); the gateway holds it server-side only.

## 4. This phase — Training orchestration (Phase 2)

`brain_training/` is a thin orchestration layer that **reuses** the existing
assets (no duplicate pipeline):

- SFT kernel: `videlisndichi-jarvis-brain-qwen3-4b-sft-train/jarvis_brain_sft.py`
- SFT corpus:  `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl` (292 passages)
- Kernel notebook: `kaggle_kernel/jarvis_brain_qwen3_4b.ipynb`
- Stage-3A artifact template (mirror for §25 reports): `silverwing-stage3a/`

### 4.1 CLI

```
python -m brain_training status        # §24 — actual-state view
python -m brain_training validate        # §6 — dataset validation
python -m brain_training probe-hf        # §3/4 — HF connection
python -m brain_training probe-kaggle    # §8 — Kaggle configuration
python -m brain_training hardware        # §8 — GPU/CUDA/RAM/disk
python -m brain_training gate validated  # §18 — promotion gate
python -m brain_training deploy          # §19-22 — deploy config + live Brain health
python -m brain_training pipeline        # §25 — run the orchestrated workflow
python -m brain_training baseline        # §16 — Qwen3-4B baseline (GPU-gated)
```

### 4.2 Artifacts (all under `brain_training/artifacts/`)

```
artifacts/
  datasets/dataset_validation.json     # §6  corpus re-verification (sha256, splits, leakage, secrets)
  scan/secret_scan.json                # §27 secret scan over dataset
  events/training_events.jsonl         # §14 append-only event log
  runs/training_runs.jsonl             # §15 run registry (empty until a real run)
  checkpoints/                         # §12 checkpoint manifests
  baseline/qwen3_4b_baseline.json      # §16 baseline (NOT_RUN on CPU)
  training/                            # metrics from Kaggle SFT run (pending)
  evaluation/jarvis_brain_comparison.json  # §17 base-vs-SFT (pending)
  status/status.json                   # §24 actual-state snapshot
  pipeline/pipeline_report.json        # §25 full stage report
```

All artifacts are regenerated from observed state; none are fabricated.

## 5. Honesty posture (spec S30)

On this dev box (8 GB RAM, `torch 2.14.0+cpu`, no CUDA, invalid HF token, unauthenticated Kaggle),
the lifecycle is **honestly reported**:

| Stage            | Verdict        | Reason                                         |
|------------------|----------------|------------------------------------------------|
| Dataset prep     | READY          | 292 passages, exact splits, leakage+secrets clean |
| Dataset sha      | NOTE           | re-staged copy bytes differ from manifest hash |
| Baseline (SFT)   | NOT RUN        | no CUDA GPU                                    |
| Kaggle export    | DONE           | kernel + script + metadata present           |
| Pilot            | NOT RUN        | no CUDA GPU                                    |
| Train            | NOT RUN        | no GPU / Kaggle unconfigured                   |
| Upload HF        | NOT CONNECTED  | HF token invalid (401)                         |
| Evaluate         | NOT RUN        | no GPU                                         |
| Promotion        | BLOCKED        | experimental; no evidence                      |
| Deploy /health   | OFFLINE        | stub not running (live probe, not faked)       |

The full stage-by-stage measurements live in §25: `docs/JARVIS_BRAIN_TRAINING_REPORT.md`.
