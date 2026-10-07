# JARVIS Brain v1 — Operations

## 1. Status command (§24)

`python -m brain_training status` prints the **actual observed state** of every
stage. It never fabricates "running"/"healthy". Each field below maps to a real
probe:

| Section            | Source                                | Honest value on this dev box         |
|--------------------|---------------------------------------|--------------------------------------|
| `env.device`       | `brain_training/hardware.py`          | `CPU (no CUDA)`; RAM 8.46 GB         |
| `base_model`       | `brain_runtime/model_registry`          | Qwen3-4B-Base @ pinned revision; not staged locally |
| `sft_dataset`      | `dataset.validate_corpus()`           | 292 passages, splits exact, leakage+secrets clean; sha256 re-staged (NOTE) |
| `kaggle`           | `kaggle.probe()`                      | `configured=false`, CLI installed, kernel artifacts present, GPU+internet enabled in metadata |
| `runs`             | `registry.RunRegistry`                | no runs recorded                     |
| `huggingface`      | `hf.probe()`                          | `NOT_CONNECTED` (token invalid 401)  |
| `upload`           | artifact inspection                    | NOT READY                            |
| `evaluation`       | artifact inspection                    | PENDING (baseline; GPU required)     |
| `promotion`        | `promote.gate("validated")`            | `experimental` / BLOCKED (5 blockers)|
| `inference`        | `deploy.probe_brain_endpoint()`        | `OFFLINE` (stub :8011 not running)   |
| `fallback`         | Phase-1 verification                   | JARVIS Gateway → Silverwing :8010 (tested) |
| `security`         | secret scan + gitignore                | clean; weights not committed         |
| `tests`            | pytest                                 | brain runtime + gateway PASS         |

## 2. Environment variables (no secrets printed)

`brain_training` resolves secrets **by reference only**:

- `JARVIS_HF_TOKEN` (preferred) or existing `HF_TOKEN` — used only to build a
  short-lived `huggingface_hub` client; dropped from locals after the probe.
- `KAGGLE_USERNAME` / `KAGGLE_KEY` — OS-env only; Kaggle injects these as kernel
  secrets at runtime (dev box does not hold them).
- `JARVIS_BRAIN_API_KEY` — held server-side by the gateway/brain runtime; never
  sent to the frontend.

When a token is declared in `.env` but **not loaded into the process
environment**, the status reports `token: <declared in .env <len=N>, not loaded>`
— length only, never the value (§4/S27).

## 3. Honest health semantics

The Brain runtime `/health` returns `available`/`stub`/`production_health`:

- `available=true, stub=false, production_health=true` → Brain is live and real.
- `available=false, stub=true` → stub Brain up (dev); gateway **must** fall back
  to Silverwing. `start_brain.py --stub` produces this; the stub is never
  advertised as production-healthy.
- unreachable → `OFFLINE`; gateway falls back to Silverwing `PROVIDER_UNAVAILABLE`.

## 4. Monitoring the Kaggle run

```bash
# after launching the kernel
watch -n 60 python -m brain_training status
```
As artifacts land in `artifacts/`, the status flips:
`runs.status`, `evaluation.status`, `promotion.current_stage`,
`inference.status`. Promote to `validated`/`promoted` only through the manual
gate once the evidence markers appear.

## 5. Artifact layout

```
brain_training/artifacts/
  status/status.json            # §24 snapshot
  pipeline/pipeline_report.json # §25 full report
  datasets/dataset_validation.json
  scan/secret_scan.json
  events/training_events.jsonl  # §14
  runs/training_runs.jsonl      # §15 (empty until a real run)
  checkpoints/                  # §12
  baseline/qwen3_4b_baseline.{json,md}
  training/                     # metrics from Kaggle SFT
  evaluation/jarvis_brain_comparison.{json,md}
  publish/                      # PublishIntent records (S9)
```

## 6. Re-verification commands

```bash
python -m brain_training status        # §24 — full actual state
python -m brain_training validate        # §6 — dataset re-verification
python -m brain_training probe-hf        # §3/4  — HF connection
python -m brain_training probe-kaggle    # §8   — Kaggle config
python -m brain_training hardware        # §8   — GPU/CUDA/RAM/disk
python -m brain_training gate validated  # §18  — promotion gate
python -m brain_training deploy          # §19-22 — deploy config + live health
python -m brain_training pipeline        # §25  — orchestrated stage report
python -m pytest tests/ -m "not integration" -q   # 143 passed; 1 pre-existing flake
```

## 7. Test posture (spec S30)

- `tests/test_jarvis_brain_training.py` — 23 locally-runnable tests (no torch at
  import; no network for the device/gate/promote/dataset tests).
- `tests/test_jarvis_brain_runtime.py` (16) + `tests/test_jarvis_brain_gateway.py` (16) —
  Phase-1 acceptance, all green.
- The single remaining failure,
  `tests/test_silverwing_evaluation.py::TestHarnessWithEcho::test_harness_full_evaluation_completes`
  (`assert 0.0 > 0`), is a **pre-existing** Silverwing-harness timing flake
  (pytest collects `tests/test_silverwing_runtime_real.py`, caches torch import,
  the EchoBackend eval runs in <5ms → rounds to `0.0`). It is **out of scope**:
  not caused by Brain code and must not be "fixed" by touching Silverwing source.
