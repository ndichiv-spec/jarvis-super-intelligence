"""LoRA fine-tune JARVIS's LLM on the project SFT dataset.

This is the training side of "train the project LLM."  It fine-tunes a causal
LLM with parameter-efficient LoRA adapters so the model internalises the
project's own conversations, knowledge base, and user memories.

Prerequisites
-------------
* A CUDA GPU (training a real LLM on CPU is extremely slow and only viable for
  toy models).
* The dataset produced by ``scripts/prepare_training_data.py``.
* The ML stack declared in ``requirements.txt``:
  ``transformers peft accelerate datasets bitsandbytes``.

Usage
-----
# 1) Inspect / validate the dataset + resolved config (works with NO ML deps):
    python scripts/train_jarvis_lora.py \
        --dataset jarvis_data/sft_dataset.jsonl --base-model gpt2 --dry-run

# 2) Full LoRA fine-tune on a GPU box:
    python scripts/train_jarvis_lora.py \
        --dataset jarvis_data/sft_dataset.jsonl \
        --base-model NousResearch/Llama-3.2-1B \
        --output-dir jarvis_data/lora-adapter \
        --per-device-train-batch-size 2 --gradient-accumulation-steps 8 \
        --num-train-epochs 3 --learning-rate 2e-4 --bf16

The base model is pulled from the Hugging Face Hub (or a local path).  The LoRA
adapter is written to ``--output-dir`` and can later be loaded for inference
without keeping the full model checkpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# Argument parsing (stdlib only so --dry-run works without ML deps)
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoRA fine-tune the JARVIS LLM.")
    p.add_argument("--dataset", required=True,
                   help="SFT JSONL produced by prepare_training_data.py")
    p.add_argument("--base-model", default="gpt2",
                   help="HF model id / local path (default: gpt2 smoke-test model)")
    p.add_argument("--output-dir", default="jarvis_data/lora-adapter",
                   help="Where to save the LoRA adapter")
    p.add_argument("--max-seq-len", type=int, default=512,
                   help="Tokenisation length / trainer sequence length")
    p.add_argument("--num-train-epochs", type=int, default=3)
    p.add_argument("--per-device-train-batch-size", type=int, default=2)
    p.add_argument("--gradient-accumulation-steps", type=int, default=8)
    p.add_argument("--learning-rate", type=float, default=2e-4)
    p.add_argument("--lr-scheduler-type", default="cosine",
                   choices=["cosine", "constant", "linear", "constant_with_warmup"])
    p.add_argument("--warmup-steps", type=int, default=3)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--target-modules", nargs="+",
                   default=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
                   help="LoRA target modules (Llama/Qwen/Gemma defaults)")
    p.add_argument("--fp16", action="store_true", help="Use fp16 (GPU only)")
    p.add_argument("--bf16", action="store_true", help="Use bf16 (GPU only)")
    p.add_argument("--load-in-4bit", action="store_true",
                   help="Quantise the base model to 4-bit via bitsandbytes (GPU only)")
    p.add_argument("--dataloader-num-workers", type=int, default=0)
    p.add_argument("--logging-steps", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry-run", action="store_true",
                   help="Validate the dataset + config and exit (no ML deps required)")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
# Dataset validation (stdlib only — always runnable)
# --------------------------------------------------------------------------- #
def _validate_dataset(path: str) -> dict:
    """Read the SFT JSONL with stdlib json and report counts + sanity checks."""
    p = Path(path)
    if not p.exists():
        sys.stderr.write(f"[train_jarvis_lora] dataset not found: {p}\n")
        sys.exit(2)
    counts = {"chat": 0, "knowledge": 0, "memory": 0, "skills": 0, "malformed": 0}
    n = 0
    sample = None
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
            except json.JSONDecodeError:
                counts["malformed"] += 1
                continue
            src = ex.get("metadata", {}).get("source", "chat")
            if src in counts:
                counts[src] += 1
            msgs = ex.get("messages") or []
            if not isinstance(msgs, list) or len(msgs) < 2:
                counts["malformed"] += 1
            n += 1
            if sample is None:
                sample = ex
    if n == 0:
        sys.stderr.write("[train_jarvis_lora] dataset is EMPTY — run "
                         "prepare_training_data.py first.\n")
        sys.exit(2)
    return {
        "total": n,
        "counts": counts,
        "sample_first_role": (sample.get("messages") or [{}])[0].get("role"),
    }


def _require_deps() -> None:
    missing = []
    for m in ("torch", "transformers", "peft", "accelerate", "datasets"):
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        sys.stderr.write(
            "[train_jarvis_lora] Missing ML dependencies: "
            + ", ".join(missing)
            + "\nInstall them with: pip install -r requirements.txt\n"
            "(bitsandbytes is CUDA-only and optional for 4-bit loading.)\n"
        )
        sys.exit(2)


def _format_conversation(messages) -> str:
    """Flatten an {messages:[...]} example into a plain-text training string.

    For chat examples this yields a real multi-turn conversation; for knowledge
    and memory single-turn Q/A examples it yields one instruction pair.  This
    simple scheme works for any tokenizer; using a model's native HF chat
    template is a straightforward future enhancement.
    """
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        tag = "USER" if role in ("user",) else "ASSISTANT"
        parts.append(f"{tag}: {content}")
    return "  ".join(parts) + "  "


def train(args: argparse.Namespace) -> None:
    _require_deps()
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    if not torch.cuda.is_available():
        sys.stderr.write(
            "[train_jarvis_lora] WARNING: no CUDA GPU detected. Training a "
            "real LLM on CPU is extremely slow; use a GPU machine.\n"
        )
    device_map = "auto"
    if args.bf16:
        torch_dtype = torch.bfloat16
    elif args.fp16:
        torch_dtype = torch.float16
    else:
        torch_dtype = torch.bfloat16

    if args.load_in_4bit and torch.cuda.is_available():
        from transformers import BitsAndBytesConfig

        bnb = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model, device_map=device_map,
            torch_dtype=torch_dtype, quantization_config=bnb,
            trust_remote_code=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model, device_map=device_map,
            torch_dtype=torch_dtype, trust_remote_code=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or "<pad>"

    # ---- dataset ----------------------------------------------------------- #
    raw = load_dataset("json", data_files=args.dataset, split="train")

    def _tokenize(example):
        text = _format_conversation(example["messages"])
        return tokenizer(text, truncation=True, max_length=args.max_seq_len,
                         padding="max_length")

    tokenized = raw.map(_tokenize, remove_columns=raw.column_names)

    # ---- LoRA -------------------------------------------------------------- #
    peft_config = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha,
        target_modules=args.target_modules,
        lora_dropout=args.lora_dropout, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)

    # ---- train ------------------------------------------------------------- #
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.num_train_epochs,
        learning_rate=args.learning_rate,
        lr_scheduler_type=args.lr_scheduler_type,
        warmup_steps=args.warmup_steps,
        weight_decay=args.weight_decay,
        logging_steps=args.logging_steps,
        seed=args.seed,
        fp16=args.fp16, bf16=args.bf16,
        dataloader_num_workers=args.dataloader_num_workers,
        optim="adamw_torch",
        remove_unused_columns=False,
    )
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    trainer = Trainer(
        model=model, args=training_args, train_dataset=tokenized,
        data_collator=data_collator, tokenizer=tokenizer,
    )
    trainer.train()
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"[train_jarvis_lora] LoRA adapter saved -> {args.output_dir}")


def main(argv=None) -> int:
    args = parse_args(argv)
    info = _validate_dataset(args.dataset)
    if args.dry_run:
        print("[train_jarvis_lora] DRY RUN — config + dataset validation only")
        print(json.dumps({
            "dataset": args.dataset,
            "base_model": args.base_model,
            "output_dir": args.output_dir,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "target_modules": args.target_modules,
            **info,
        }, indent=2))
        print("[train_jarvis_lora] dry-run OK — no ML deps required. "
              "Drop --dry-run on a CUDA box to start training.")
        return 0
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
