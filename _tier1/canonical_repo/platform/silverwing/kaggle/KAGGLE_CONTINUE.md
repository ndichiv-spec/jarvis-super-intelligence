# Kaggle GPU continuation — silverwing-120m-base-v1

Use this **only** to continue-pretrain on a Kaggle **GPU** kernel. CPU here is ~56 tok/s
(≈5 h per 1M tokens); a free T4 is ~10–20× faster, so a 10M-token stage finishes in ~3.5 h.

The script is `silverwing/kaggle/silverwing_continue_gpu.py`. It is the **canonical**
Phase-2 trainer: it loads the frozen checkpoint + served tokenizer with `strict=True`,
never retrains the tokenizer, never downscales to 12M, and aborts cleanly if no GPU.

## 1. Create the two Kaggle datasets

### Dataset A — `silverwing-120m-base` (the frozen checkpoint)
Package the entire frozen checkpoint directory (read from local):
```
F:\AI\.sw_cache\silverwing-120m-base\r1\
  model.safetensors      (513,915,792 bytes  — sha256 da860489…)
  config.json            (337 bytes         — sha256 df1f7562…)
  tokenizer.json         (568,422 bytes      — sha256 5b09bfb6…)
  metadata.json          (605 bytes)
  .sw_cache_entry.json   (212 bytes)
```
Kaggle slug becomes `silverwing-120m-base` → mounted at `/kaggle/input/silverwing-120m-base`.

### Dataset B — `silverwing-corpus` (the improved training corpus)
```
F:\AI\Jarvis-super-intelligence-\silverwing\data_pipeline\processed\
  train.txt   (37,563,082 bytes — sha256 3b6c1a30…)  ~12.67M tokens, CC-BY-SA 3.0 + PD
  val.txt     (867,033 bytes    — sha256 561edaf2…)  ~251K tokens
```
Kaggle slug becomes `silverwing-corpus` → mounted at `/kaggle/input/silverwing-corpus`.

> The baseline's own dataset hash in the manifest is `5b389a08…` (409,600 tokens); the
> new corpus above (13.6 M tokens) supersedes it for continued pretraining. Its hash is
> recorded into every new checkpoint's `metadata.json.dataset_train_sha256` for lineage.

## 2. Create / configure the Kaggle kernel
- **SDK:** Python 3. **Accelerator:** GPU (T4) — *must* be set; the script will fatal if no CUDA.
- **Internet:** ON.
- **Add datasets:** `silverwing-120m-base` + `silverwing-corpus`.
- Attach this repo (or paste the script into a cell) so `silverwing/` is importable.

## 3. Run (Phase-4 staged schedule)
Stage 1 — 10M tokens (~3.5 h on T4):
```bash
python silverwing/kaggle/silverwing_continue_gpu.py \
  --resume_from /kaggle/input/silverwing-120m-base \
  --data_dir  /kaggle/input/silverwing-corpus \
  --output_dir /kaggle/working/silverwing-continue \
  --steps 5000 --batch_size 1 --grad_accum 8 --lr 5e-5 --warmup_steps 100 \
  --save_steps 500 --eval_steps 250 --log_steps 25
```
(5000 steps × 2048 tok = 10.24 M tokens.)

Stage 2 — 25M, Stage 3 — 50M, Stage 4 — 100M: multiply `--steps` (12500 / 25000 / 50000),
and `--resume_from` the **last checkpoint** of the previous stage
(`/kaggle/working/silverwing-continue/checkpoints/step-<N>`). After each stage re-evaluate
the Phase-6 fixed prompts (see `silverwing/phase1_freeze.py`'s 7 prompts).

## 4. Download outputs
From the kernel's **Output** tab: `silverwing-continue/checkpoints/`, `metrics.jsonl`,
`training_summary.json`, `corpus_{train,val}.npy`. Copy these back to
`silverwing/local_run/exp_c_continue_120m/` (or a Kaggle-staged folder) so the local
JARVIS runtime can serve the continued model once you copy `model.safetensors` into a
new `.sw_cache` revision.

## Pitfalls avoided by this script (do NOT use the legacy trainer for the 120M)
1. **Tokenizer drift:** `silverwing_train.py` retrains a BPE if `work_dir/tokenizer/` is
   empty. A retrained 8192-vocab BPE has a *different merge table*, misaligning the frozen
   embeddings. This script always loads the served `5b09bfb6` tokenizer.
2. **Silent 12M downscale:** `silverwing_train.py` switches to 12M on CPU (P100-fallback
   or no-accelerator). This script aborts with a clear message if CUDA is missing.
3. **Token-accounting gap:** the legacy loader reads `meta["total_tokens"]`, but the frozen
   metadata uses `"tokens"`. This script reads the correct key.
