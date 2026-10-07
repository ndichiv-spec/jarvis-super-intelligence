# JARVIS Brain v1 — Training Operations

This document describes the **reproducible training/deployment pipeline** for
JARVIS Brain v1 (§25 workflow). It **reuses** the existing Kaggle SFT kernel and
corpus — it does **not** duplicate them.

## 1. Pipeline

`brain_training/pipeline.py` exposes `BrainPipeline.run()` (CLI:
`python -m brain_training pipeline`). It executes the §25 stage order and
reports each stage honestly:

```
prepare_dataset -> validate_dataset -> baseline -> export_kaggle -> run_pilot
  -> train -> checkpoint -> upload_hf -> evaluate -> promotion_gate
  -> deploy -> health_probe -> gateway_test
```

**Gating (spec S25/S18):** stages that require a CUDA GPU, Kaggle credentials,
or a valid HuggingFace token are reported `NOT RUN` / `NOT_CONNECTED` with the
actual reason — they are **never executed** on a CPU-only / unauthenticated box.
The chain proceeds through all stages regardless (reporting each honestly), and
auto-proceed `train -> validate -> publish -> evaluate` is allowed only when a
stage's prerequisites are met. **A model is never auto-promoted to production**
(manual gate, §18).

## 2. Stage detail

### 2.1 prepare_dataset (§6) — `DONE`
`brain_training/dataset.py:validate_corpus()` re-verifies the staged corpus on
the CPU-only box **without downloading weights or contacting HF**:

- recomputes SHA-256 of `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl`
- cross-checks passage count (292), source breakdown, and **split assignment**
  against `jarvis_brain_sft_dataset_manifest.json` (train 238 / val 22 / test 32)
- re-derives token counts via the Qwen tokenizer when importable, else a
  deterministic `len/3.8` char estimate (exact counts are produced on Kaggle)
- **leakage check (§7):** no r2000/silverwing benchmark *prompts* appear in the
  SFT data (full-question patterns, not bare keywords — bare concepts like
  "Red Planet" legitimately appear in encyclopedia prose and are excluded from
  the check)
- **secret scan (§27):** no leaked credentials in the corpus or dataset dir

**Honest finding (real):** passage count, sources, and splits **exactly match**
the manifest; leakage and secrets are clean. The byte-level SHA-256 does **not**
match the manifest (`81703f34…` actual vs `9cbcfb3c…` claimed): the locally-staged
`01_normalized.jsonl` is a re-staged copy whose bytes differ from the manifest
recorded by the prior Kaggle run. `content_ready=True` with an `integrity_note`;
the stale hash is surfaced, never faked. Fix: re-publish the canonical Kaggle
corpus or update the manifest hash.

### 2.2 validate_dataset (§27) — `DONE`
`secret_scan_artifact()` scans the dataset repo for leaked credentials
(`hf_…`, OpenAI `sk-…`, GitHub Pats, AWS, JWT, generic `..._TOKEN=…`). Scan
output is **masked** — raw secret values are never printed, logged, or written
to metadata. Report → `artifacts/scan/secret_scan.json`.

### 2.3 baseline (§16) — `NOT RUN` (no CUDA GPU)
`brain_training/baseline.py:run_baseline()` loads **the pinned base**
`Qwen/Qwen3-4B-Base` @ `1cfa9a7208912126459214e8b04321603b3df60c` and runs the
kernel's `run_r2000_eval(...)` over the math/logic/knowledge/coding scorers,
writing `artifacts/baseline/qwen3_4b_baseline.{json,md}`. On this dev box
(`cuda_available=False`, 8 GB RAM) it returns `NOT_RUN` with the device
status — a Qwen3-4B forward pass cannot be served. The runner is invoked only
when `hardware.gpu_probe().is_gpu` is true.

### 2.4 export_kaggle (§8) — `DONE`
The existing kernel + script + metadata are the Kaggle export (not duplicated).
`kaggle_kernel/jarvis_brain_qwen3_4b.ipynb` cell 1 prints the **actual**
accelerator (T4/P100/L4 — never assumed); cell 3 verifies the model revision
sha; cell 2 reads `JARVIS_HF_TOKEN` from Kaggle Secrets.

### 2.5 run_pilot (§S6 pilot) — `NOT RUN`
Smoke test: loads the base model + runs 1 inference step + writes a checkpoint
to confirm the train path works before the full run. GPU-gated.

### 2.6 train (§S6/Kaggle) — `NOT RUN`
Reuses **the existing kernel**
(`videlisndichi-jarvis-brain-qwen3-4b-sft-train/jarvis_brain_sft.py`) as a
subprocess only when GPU + Kaggle creds are present. The kernel's recipe
(verified, not rebuilt):

- base `Qwen/Qwen3-4B-Base`; QLoRA 4-bit nf4
  (`load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=fp16,
  bnb_4bit_use_double_quant=True`)
- LoRA `r=64, alpha=128, target_modules=[q,k,v,o]_proj, dropout=0.1, bias=none`,
  `task_type=CAUSAL_LM`
- `TrainingArguments(per_device_train_batch_size=1, grad_accum=8, 1 epoch,
  lr=2e-4, fp16, logging_steps=10, save_steps=200, save_total_limit=2)`
- saves adapter LoRA to `/kaggle/working/jarvis-brain-qwen3-4b-sft-v1`
- r2000 eval scorers inline; NaN/Inf abort; writes `run_manifest.json` with
  `weights_on_kaggle_only=True`

### 2.7 checkpoint (§12)
`brain_training/registry.py:CheckpointMeta` + `write_checkpoint_manifest()`.
Each checkpoint preserves: adapter + optimizer + scheduler + scaler + step +
epoch + random state + training config + dataset revision + tokenizer sha256 +
model/base revision. Naming: `jarvis-brain-qwen3-4b-sft-v1-step-NNNNNN.json`.
On the dev box no checkpoints exist (`checkpoint_count: 0`).

### 2.8 upload_hf (§S9) — `NOT CONNECTED`
Publish contract (implemented in `brain_training/hf.py`, invoked only on a GPU
host with a valid token):
```
Kaggle checkpoint -> validation -> artifact manifest -> HF upload
-> commit/revision -> registry update
```
Published per model: weights, tokenizer, config, training configuration,
evaluation metrics, `dataset_manifest.json`, model card. **Adapters are never
presented as a merged model** unless a real merge+verify is performed
(`PublishIntent.merged=False` by default; base model + adapter type + training
method + dataset revision are always recorded on the card).

On this box `hf_probe()` returns **NOT_CONNECTED**: the process environment has
no token; `.env` declares an `HF_TOKEN` (`<len=201>`, `hf_` prefix) which a prior
`whoami` probe confirmed is **invalid (401)**. No upload is attempted — partial
uploads are rejected by gate.

### 2.9 evaluate (§17) — `NOT RUN`
`Qwen3-4B-Base` vs `jarvis-brain-qwen3-4b-sft-v1` over the **same r2000**
prompt set (math/logic/knowledge/coding/instruction) + length/quality scoring.
Writes `artifacts/evaluation/jarvis_brain_comparison.{json,md}`. GPU-gated;
no baseline yet on the dev box.

### 2.10 promotion_gate (§18) — `BLOCKED`
`brain_training/promote.py`. Evidence-driven, **never automatic**.
Stages: `experimental -> candidate -> validated -> promoted`. Required evidence
(§18):
- baseline metrics present
- SFT metrics present
- base-vs-SFT comparison present
- security scan clean
- adapter reload + generation smoke verified

On the dev box all evidence is absent → current stage `experimental`, target
`validated` → **BLOCKED** (5 explicit blockers). `promoted` additionally requires
manual approval and is always denied by the gate.

### 2.11 deploy + health_probe (§19-22)
`brain_training/deploy.py` loads the deploy config
(`JARVIS_BRAIN_ENDPOINT`/`JARVIS_BRAIN_MODEL`/`JARVIS_BRAIN_API_KEY`), resolves
the model via `BrainCatalog`, and performs a **live unauthenticated GET
/health**. Current reality: the Brain stub on `:8011` is **not running** →
`reachable=False` → status `OFFLINE` (honest, never faked). When the stub is up,
`/health` returns `available=false, stub=true` and the gateway falls back to
Silverwing `:8010` (verified by `tests/test_jarvis_brain_gateway.py`, 16 tests).

### 2.12 gateway_test — `DONE`
Re-runs `tests/test_jarvis_brain_gateway.py` (16 tests): Brain-first routing,
`GatewayError`→`PROVIDER_UNAVAILABLE` fallback, auth gating (missing/invalid/
malformed key), and stub-vs-production health honest-reporting.

## 3. Monitoring (§14/20)

- `artifacts/events/training_events.jsonl` — append-only lifecycle events
  (`dataset.validated`, `dataset.security_scanned`, `brain.health_probed`,
  `training.status_report`, …). Detail strings are **redacted** of secret var
  names.
- `artifacts/runs/training_runs.jsonl` — run registry (empty on dev box;
  initialized at startup). Each record: real observed `latest_train_loss /
  latest_val_loss / latest_lr / latest_step / latest_tokens` — never fabricated.
- `artifacts/pipeline/pipeline_report.json` — full §25 stage report.
- `artifacts/status/status.json` — §24 actual-state snapshot.

To follow progress live on a Kaggle run: `python -m brain_training status`
prints `runs` + `evaluation` as artifacts land.

## 4. Kaggle invocation (for operators)

```bash
# one-time (local dev shell): authenticate the kaggle CLI
kaggle config   # uses KAGGLE_USERNAME / KAGGLE_KEY (kernel UI injects these in-kernel)
# launch the existing kernel (GPU + internet enabled)
kaggle kernels push -k videlisndichi/jarvis-brain-v1-qwen3-4b-lora-qlora-sft
# poll:
python -m brain_training status
```
