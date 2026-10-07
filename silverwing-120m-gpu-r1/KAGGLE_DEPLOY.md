# Silverwing-120M-V1 — GPU R1 Clean Relaunch

## What This Is

A clean, self-contained training script that runs the **Silverwing-120M-V1** model training (500 steps) on Kaggle's GPU (P100). It fixes the root cause of the previous Kaggle kernel cancellation: the smoke test and training loop are now in the **same execution flow**, with `metrics.jsonl` initialized **before** the smoke test.

## Quick Deploy (3 Steps)

### 1. Create a new Kaggle Script Notebook

Go to https://www.kaggle.com/code → **New Notebook** → **Source** → "Create as Script" (not Notebook).

### 2. Configure the Kernel

| Setting | Value |
|---------|-------|
| **Accelerator** | GPU (P100) |
| **Internet** | ON |
| **Runtime type** | Python |

### 3. Attach Datasets

In the notebook's **Settings → Input** or via the **+ Add Input** button, attach:

1. `videlisndichi/silverwing-120m` — contains: `tokenizer.json`, `silverwing_120m_config.json`, `01_normalized.jsonl`, `r2000_eval.json`, `val.txt`, `stage3a_evaluate.py`
2. `videlisndichi/silverwing-120m-fixes` — contains: `val.txt`, `stage3a_evaluate.py` (backup)

### 4. Run

```
python silverwing_120m_gpu_r1.py
```

Or to resume from a checkpoint:
```
python silverwing_120m_gpu_r1.py --resume
```

## What The Script Does (Execution Flow)

```
hardware_preflight() → CUDA check (EXIT if no GPU)
  ↓
training_run_start event → metrics.jsonl
  ↓
verify tokenizer SHA256 → r2000 BPE 8192
  ↓
verify dataset → train.npy / val.npy (build from corpus if missing)
  ↓
GPU memory probe → VRAM usage (no batch scaling)
  ↓
GPU smoke test (9 checks: CUDA, Forward, Backward, AMP, Optimizer,
   Checkpoint, Resume, NaN, Inf) — ALL must PASS
  ↓
training_started event → metrics.jsonl
  ↓
TRAINING (500 steps, seq=256, grad_accum=4, LR=1.5e-4 cosine+25 warmup, BF16)
  ├── every 10 steps:   step, loss, lr, grad_norm, tok/s, tokens, VRAM, time
  ├── every 100 steps:  val_loss, perplexity, checkpoint save
  └── checkpoint every 100 steps + best + final
  ↓
Full evaluation vs r2000 + 10 fixed prompts + MATH/LOGIC/KNOWLEDGE/CODING benchmarks
  ↓
Generate all 12 report artifacts
```

## Training Configuration

| Parameter | Value |
|-----------|-------|
| Steps | 500 |
| Sequence length | 256 |
| Micro-batch | 1 |
| Gradient accumulation | 4 (effective batch = 4) |
| Learning rate | 1.5e-4 |
| LR schedule | Cosine decay + 25 warmup steps |
| Warmup steps | 25 |
| Weight decay | 0.01 |
| Grad clip | 1.0 |
| Seed | 42 |
| Precision | BF16 (preferred) / FP16 (fallback) |
| Init | From scratch (std=0.02, no r3000/r2000 weights) |

## Architecture (Unchanged)

- 12 layers, d_model=1024, 16 Q heads, 4 KV heads (GQA 4:1)
- head_dim=64, MLP=2176, SwiGLU activation
- RoPE (theta=10000), RMSNorm (eps=1e-5)
- Vocab=8192, ctx=2048, tied embeddings, no bias
- Param count: 120,087,552

## Required Artifacts (all generated automatically)

1. `silverwing_120m_gpu_r1_report.json`
2. `silverwing_120m_gpu_r1_report.md`
3. `metrics.jsonl` (streaming events: training_run_start, training_started, step_metrics every 10, validation every 100, training_complete)
4. `training_metrics.json`
5. `evaluation_report.json`
6. `comparison_report.json` (vs r2000 baseline)
7. `capability_history.json`
8. `run_manifest.json`
9. `dataset_manifest.json`
10. `sample_generations.txt`
11. `environment_report.txt`
12. `environment_report.json`

## Checkpoint Format

Each checkpoint directory contains:
- `model.safetensors` — de-aliased model weights (detached clone)
- `optimizer.pt` — optimizer + scheduler + step + tokens state (torch.save)
- `scaler.pt` — GradScaler state (FP16 only)
- `config.json` — model architecture config
- `tokenizer_manifest.json` — tokenizer metadata
- `metadata.json` — step, tokens, losses, all SHA256 hashes, param count

## Resuming

```bash
python silverwing_120m_gpu_r1.py --resume
# or from a specific checkpoint:
python silverwing_120m_gpu_r1.py --resume-from /kaggle/working/silverwing-120m-gpu-r1/checkpoints/step-300
```

Resume restores: model weights, optimizer state, scheduler state, global step, token count, GradScaler state.

## Key Design Decisions

- **P100 detection**: The script auto-installs `torch==2.4.1+cu121` if a P100 (sm_60) is detected, since Kaggle's default torch lacks P100 kernels.
- **metrics.jsonl BEFORE smoke**: Even if cancelled during smoke test, the `training_run_start` event proves the run began.
- **No CPU fallback**: The script hard-exits if CUDA is unavailable — this prevents wasting time on CPU.
- **Fresh LR schedule**: Cosine schedule is computed from scratch, never reusing any previous run's schedule.
- **r3000 forbidden**: The script will NEVER load the r3000-highLR checkpoint and starts from random init only.

## What To Check After The Run

1. `metrics.jsonl` should contain `training_started` event (proves training began)
2. 50 step_metrics events (every 10 steps × 50)
3. 5 validation events (every 100 steps)
4. Checkpoints at `step-100`, `step-200`, `step-300`, `step-400`, `step-500`, `best`, `final`
5. All 12 report artifacts present
6. `comparison_report.json` shows improvement over r2000 baseline
7. `nan_total` and `inf_total` should be 0
