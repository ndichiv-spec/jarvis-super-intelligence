# Training JARVIS's LLM on Kaggle (free GPU)

This is the GPU path for **Phase-train**: LoRA fine-tuning of JARVIS's LLM on the
project's own conversations, knowledge base and user memories. This sandbox is
CPU-only with no ML deps, so training itself is run on a Kaggle kernel with a free
GPU.

## Files

| File | Purpose |
|---|---|
| `scripts/prepare_training_data.py` | Export any corpus — **chat/knowledge/memory** (from the SQL store) **and `skills`** (mined from `.claude/skills/`) — to SFT JSONL. |
| `scripts/kaggle_train_jarvis_lora.py` | **Self-contained Kaggle kernel script** (installs deps, GPU check, trains LoRA, zips adapter). |
| `scripts/train_jarvis_lora.py` | Local-GPU equivalent of the same recipe (for a real GPU box). `--dry-run` validates a dataset with stdlib only. |
| `jarvis_data/sft_sample.jsonl` | Committed 12-example sample corpus (4 chat, 5 knowledge, 3 memory). |
| `jarvis_data/sft_skills.jsonl` | Mined skill corpus: **403 Q/A examples** across all 6 Claude skill packs (the real training signal). |

## Step 1 — Inspect / validate (works here, no ML deps)

```powershell
# Build the real skill corpus (403 Q/A examples mined from .claude/skills):
python scripts/prepare_training_data.py --source skills --out jarvis_data/sft_skills.jsonl

# Or the full combined corpus (skills + any chat/knowledge/memory in the store):
python scripts/prepare_training_data.py --out jarvis_data/sft_dataset.jsonl

# Validate the dataset + resolved LoRA config (stdlib only — no ML deps):
python scripts/train_jarvis_lora.py --dataset jarvis_data/sft_dataset.jsonl --dry-run
```

`--dry-run` parses the JSONL with stdlib `json`, buckets examples by source
(including `skills`), and prints the resolved LoRA config — no
`torch`/`transformers`/`peft` needed. The dry-run confirmed the full combined
corpus: **`total: 406, counts: chat=1, knowledge=1, memory=1, skills=403,
malformed=0`.**

## Step 2 — Run the training on Kaggle

1. **Create a kernel**: Kaggle → **Create** → **New Notebook** → *switch to a
   Script* (or New → Script), choose **Python**.
2. **Settings** (top-right gear):
   - **Accelerator → GPU** (T4 or P100).
   - **Internet → toggle ON** (required to pull the base model from the Hub).
3. **Paste** the contents of `scripts/kaggle_train_jarvis_lora.py` into the first
   code cell (or add it as a `.py` script kernel), then **Run all**.

Or, for real training, upload the skill corpus:
- Run `python scripts/prepare_training_data.py --source skills --out jarvis_data/sft_skills.jsonl`
  locally (it reads `.claude/skills` and needs no ML deps), then **add
  `jarvis_data/sft_skills.jsonl` as a Kaggle dataset**, mount it at
  `/kaggle/input/jarvis-sft/`, and the kernel will auto-detect it via
  `SFT_DATASET_PATH` / `/kaggle/input/jarvis-sft/sft_skills.jsonl`.
- You can also combine sources first (e.g. `--source all`) to fold in your real
  chat conversations, user memories, and knowledge base alongside the skills.
- Without a mounted corpus it falls back to a 5-example embedded smoke corpus.

## Step 3 — Download the adapter

After training, open the kernel's **Output** tab and download
`jarvis_lora_adapter.zip`. It contains:
- `adapter_config.json`, `adapter_model.bin` (the LoRA deltas, ~% of full model)
- `tokenizer/` (the tokenizer)

## Loading the adapter afterward

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained("gpt2")        # or the BASE_MODEL you used
tok = AutoTokenizer.from_pretrained("gpt2")
model = PeftModel.from_pretrained(base, "/path/to/jarvis_lora_adapter")
model.eval()
print(tok.decode(model.generate(
    **tok("JARVIS, who are you?", return_tensors="pt").input_ids, max_new_tokens=64)[0],
    skip_special_tokens=True))
```

## Tuning knobs (env vars in the kernel)

| Var | Default | Notes |
|---|---|---|
| `BASE_MODEL` | `gpt2` | Public + token-less. For quality use `meta-llama/Llama-3.2-1B` (public). |
| `BATCH_SIZE` | `2` | per-device; Kaggle T4 ~16 GB. |
| `EPOCHS` | `3` | set lower for a quick smoke test. |

With `gpt2` (124 M params) on a T4, the full sample corpus trains in ~2 minutes.

## Notes
- `torch 2.14.0+cpu` in *this* sandbox is the wrong build (no CUDA) and the
  declared `transformers>=5.0.0rc3` / `peft` / `trl` / `datasets` are **not
  installed here** — these are installed fresh inside the Kaggle kernel at Step 2.
- `meta-llama/Llama-3.2-1B` is **gate-free** on the Hub as of 2024; no HF token
  required. (Gated models need `HF_TOKEN` in Kaggle secret storage.)
