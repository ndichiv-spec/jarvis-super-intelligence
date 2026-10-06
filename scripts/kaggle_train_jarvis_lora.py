"""Kaggle Kernel — LoRA fine-tune JARVIS's LLM on a free GPU.

Drop this script into a **new Kaggle "Script" kernel** (New → Script → Python)
with the accelerator set to **GPU** (Settings → Accelerator → GPU) and **Internet
ON** (Settings → toggle "Internet").  Then run all cells top-to-bottom.

It is intentionally self-contained: it pip-installs the ML stack, picks a small
public base model (default `gpt2`, which needs NO Hugging Face token), trains a
LoRA adapter on JARVIS's own mined data (conversations, knowledge, memories and
the Claude skill packs), and zips the adapter to /kaggle/working so it appears
in the kernel's **Output** tab for download.

For better quality, switch BASE_MODEL to a public small Llama 3.2 release, e.g.
  meta-llama/Llama-3.2-1B
(gate-free on the Hub as of 2024).  GPT-2 target modules differ from Llama, so
TARGET_MODULES below auto-adapts based on the model id.
"""
from __future__ import annotations

# %% [markdown]
# ## 1. Install dependencies (idempotent — skipped if already present)

# %% [code]
import importlib
import subprocess
import sys


def _installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


_PIP = [
    ("transformers", "transformers"),
    ("accelerate", "accelerate"),
    ("peft", "peft"),
    ("datasets", "datasets"),
    ("bitsandbytes", "bitsandbytes"),
]
needs = [pkg for mod, pkg in _PIP if not _installed(mod)]
if needs:
    print("installing:", needs)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--no-cache-dir", *needs],
        check=False,
    )
else:
    print("all ML deps already present")


# %% [markdown]
# ## 2. GPU check

# %% [code]
import torch

assert torch.cuda.is_available(), (
    "No GPU detected. In the Kaggle kernel: Settings → Accelerator → GPU "
    "(T4/P100), then re-run."
)
print("GPU:", torch.cuda.get_device_name(0), "| VRAM:",
      round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1), "GB")


# %% [markdown]
# ## 3. Dataset — upload yours, or use the embedded fallback

# %% [code]
import json
import os
from pathlib import Path

# Prefer a corpus you uploaded (add a Kaggle dataset → /kaggle/input/jarvis-sft/),
# or set SFT_DATASET_PATH in the kernel settings. Accepts, in order of preference:
#   * sft_skills.jsonl  -> the 403 skill Q/A examples mined from .claude/skills
#   * sft_dataset.jsonl -> combined skills + chat/knowledge/memory
#   * sft_sample.jsonl  -> the 12-example committed sample
_CANDIDATES = [
    os.environ.get("SFT_DATASET_PATH", ""),
    str(Path("/kaggle/input/jarvis-sft") / "sft_skills.jsonl"),
    str(Path("/kaggle/input/jarvis-sft") / "sft_dataset.jsonl"),
    str(Path("/kaggle/input/jarvis-sft") / "sft_sample.jsonl"),
    "/kaggle/working/sft_sample.jsonl",
]
SFT_PATH = next((c for c in _CANDIDATES if c and Path(c).exists()), None)

if not SFT_PATH:
    # Embedded fallback corpus (always trains something on first run).
    _FALLBACK = [
        {"messages": [
            {"role": "user", "content": "Who is JARVIS?"},
            {"role": "assistant", "content":
                "JARVIS is a unified AI backend with auth, chat, persistent memory "
                "and observability, built for the Jarvis-super-intelligence project."}],
         "metadata": {"source": "knowledge", "key": "what_is_jarvis", "category": "overview"}},
        {"messages": [
            {"role": "user", "content": "What does the user prefer?"},
            {"role": "assistant", "content":
                "The user prefers concise, direct answers with no fluff."}],
         "metadata": {"source": "memory", "memory_id": "pref-001", "importance": 0.9}},
        {"messages": [
            {"role": "user", "content": "What is the JARVIS memory system?"},
            {"role": "assistant", "content":
                "JARVIS recalls user memories and knowledge into the system prompt "
                "via _system_with_context, ownership-safe and importance-scored."}],
         "metadata": {"source": "knowledge", "key": "memory", "category": "memory"}},
        {"messages": [
            {"role": "user", "content": "What is JARVIS?"},
            {"role": "assistant", "content":
                "JARVIS is the unified AI backend — FastAPI service with auth, chat, "
                "persistent memory (SQL Store) and structured-logging observability."}],
         "metadata": {"source": "knowledge", "key": "what_is_jarvis", "category": "overview"}},
        {"messages": [
            {"role": "user", "content": "What metrics does JARVIS expose?"},
            {"role": "assistant", "content":
                "JARVIS exposes requests_total, request_duration, errors_total and "
                "active_requests via /api/v1/metrics, plus memory_items and sessions."}],
         "metadata": {"source": "knowledge", "key": "metrics", "category": "observability"}},
    ]
    SFT_PATH = "/kaggle/working/_sft_fallback.jsonl"
    Path(SFT_PATH).write_text(
        "\n".join(json.dumps(e) for e in _FALLBACK), encoding="utf-8"
    )
    print("no dataset mounted — using embedded fallback corpus")

# Validate it loads.
_rows = [json.loads(l) for l in Path(SFT_PATH).open(encoding="utf-8") if l.strip()]
assert _rows, f"dataset {SFT_PATH} is empty"
assert all(isinstance(r.get("metadata"), dict) and r["messages"] for r in _rows), \
    "each example must have {messages:[...], metadata:{...}}"
print(f"dataset OK: {SFT_PATH} — {len(_rows)} examples")


# %% [markdown]
# ## 4. Model + tokenizer + LoRA config

# %% [code]
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HOME", "/kaggle/working/hf_cache")
BASE_MODEL = os.environ.get("BASE_MODEL", "gpt2")  # public, token-less, tiny/fasts

from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model  # noqa: E402
from datasets import load_dataset  # noqa: E402

_model_lower = BASE_MODEL.lower()
if any(t in _model_lower for t in ("llama", "gemma", "qwen", "mistral", "mixtral")):
    TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"]
else:
    TARGET_MODULES = ["c_attn", "c_proj", "c_fc"]  # GPT-2 family

print("base_model:", BASE_MODEL, "| target_modules:", TARGET_MODULES)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token or "<pad>"

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    device_map="auto",
    torch_dtype=(torch.bfloat16 if torch.cuda.is_available() else torch.float32),
    trust_remote_code=True,
)


# %% [markdown]
# ## 5. Tokenise + train with LoRA

# %% [code]
MAX_LEN = 256
raw = load_dataset("json", data_files=SFT_PATH, split="train")


def _format(example):
    parts = []
    for m in example["messages"]:
        tag = "USER" if m.get("role") == "user" else "ASSISTANT"
        parts.append(f"{tag}: {(m.get('content') or '').strip()}")
    return {"text": "  ".join(parts) + "  "}


raw = raw.map(_format, remove_columns=raw.column_names)


def _tok(example):
    return tokenizer(example["text"], truncation=True, max_length=MAX_LEN,
                     padding="max_length")


tokenized = raw.map(_tok, remove_columns=raw.column_names)

peft_config = LoraConfig(
    r=16, lora_alpha=32, target_modules=TARGET_MODULES,
    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
)
model = get_peft_model(model, peft_config)

args = TrainingArguments(
    output_dir="/kaggle/working/jarvis_lora",
    per_device_train_batch_size=int(os.environ.get("BATCH_SIZE", 2)),
    gradient_accumulation_steps=8,
    num_train_epochs=int(os.environ.get("EPOCHS", 3)),
    learning_rate=2e-4,
    fp16=False, bf16=True,
    logging_steps=1, seed=42,
    optim="adamw_torch", remove_unused_columns=False,
)

trainer = Trainer(
    model=model, args=args, train_dataset=tokenized,
    data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    tokenizer=tokenizer,
)
trainer.train()


# %% [markdown]
# ## 6. Save + zip the LoRA adapter (appears in Output tab)

# %% [code]
import shutil

OUT = Path("/kaggle/working/jarvis_lora")
OUT.mkdir(parents=True, exist_ok=True)
trainer.save_model(str(OUT))  # adapter_model.bin / adapter_config.json
tokenizer.save_pretrained(str(OUT))

zip_path = "/kaggle/working/jarvis_lora_adapter.zip"
shutil.make_archive(zip_path.replace(".zip", ""), "zip")
print(f"LoRA adapter saved and zipped -> {zip_path}")
print("Download it from the kernel's Output tab, then load with:")
print("  from peft import PeftModel")
print("  model = PeftModel.from_pretrained(base_model, OUT_DIR)")
