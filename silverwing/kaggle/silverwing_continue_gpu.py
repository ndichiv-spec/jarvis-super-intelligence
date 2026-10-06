#!/usr/bin/env python3
"""Phase 2 — Continue-pretrain silverwing-120m-base-v1 (canonical, device-agnostic).

Works on BOTH a local CPU box and a Kaggle GPU kernel. It avoids the two gotchas
in the legacy ``silverwing/kaggle/silverwing_train.py``:

* **Never retrains the tokenizer** — always loads the *served* tokenizer from the
  frozen checkpoint dir. A retrained tokenizer (even vocab=8192) would produce a
  different BPE merge table and silently misalign the 120M embedding table.
* **Never downscales to 12M** — always builds the architecture from the frozen
  ``config.json`` and never switches to a smaller config when on CPU.
* **Correct lineage** — reads ``tokens`` (not ``total_tokens``) from the frozen
  metadata so step/token accounting stays accurate.
* **GPU gate** — on the Kaggle path a CUDA device is required; if
  ``torch.cuda.is_available()`` is False it aborts with a clear message instead
  of silently training a 12M model.

This script NEVER writes to the frozen baseline (read-only ``--resume_from``);
all new checkpoints + metrics go to ``--output_dir``.

KAGGLE quick-start (free T4 kernel, ~3.5 h per 10M-token stage):
    1. Make dataset "silverwing-120m-base"  =  .sw_cache/silverwing-120m-base/r1/*
       (model.safetensors 514 MB, config.json, tokenizer.json, metadata.json)
    2. Make dataset "silverwing-corpus"      =  silverwing/data_pipeline/processed/{train,val}.txt
    3. Kaggle kernel: Python 3 / PyTorch (any) / Accelerator = GPU(T4) / Internet = ON,
       add BOTH datasets.
    4. Run:
       python silverwing/kaggle/silverwing_continue_gpu.py \
         --resume_from /kaggle/input/silverwing-120m-base \
         --data_dir  /kaggle/input/silverwing-corpus \
         --output_dir /kaggle/working/silverwing-continue \
         --steps 5000 --batch_size 1 --grad_accum 8 --lr 5e-5 \
         --warmup_steps 100 --save_steps 500 --eval_steps 250 --log_steps 25
    Outputs (checkpoints/metrics/summary) download from /kaggle/working/silverwing-continue.

LOCAL CPU (smoke / fallback — ~56 tok/s on this box => ~5 h / 1M tokens):
    python silverwing/kaggle/silverwing_continue_gpu.py \
        --resume_from F:\\AI\\.sw_cache\\silverwing-120m-base\\r1 \
        --data_dir  F:\\AI\\Jarvis-super-intelligence-\\silverwing\\data_pipeline\\processed \
        --output_dir F:\\AI\\Jarvis-super-intelligence-\\silverwing\\local_run\\exp_c_continue_120m \
        --steps 30 --seq_len 256 --batch_size 1 --grad_accum 4 --lr 5e-5 --warmup_steps 5 \
        --save_steps 30 --eval_steps 15 --log_steps 5
"""
from __future__ import annotations

import argparse, json, math, os, time, hashlib, sys
from pathlib import Path

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parent.parent.parent  # .../Jarvis-super-intelligence-
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from silverwing.training.train import SilverwingModel, ModelConfig, BPETokenizer  # noqa: E402

from safetensors.torch import load_file, save_file


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shard_ids(ids: np.ndarray, n: int, seq_len: int, rng: np.random.Generator) -> np.ndarray:
    """Pick ``n`` random contiguous seq_len-chunks from ``ids`` -> (n, seq_len) int64."""
    T = seq_len
    out = np.empty((n, T), dtype=np.int64)
    for i in range(n):
        j = int(rng.integers(0, max(1, len(ids) - T - 1)))
        out[i] = ids[j:j + T]
    return out


@torch.no_grad()
def eval_val_loss(model, val_ids: np.ndarray, tok, seq_len: int, n: int = 16) -> float:
    if len(val_ids) < seq_len + 1:
        return float("nan")
    rng = np.random.default_rng(0)
    batches = shard_ids(val_ids, n, seq_len, rng).astype(np.int32)
    losses = []
    for b in batches:
        x = torch.from_numpy(b).long().unsqueeze(0)
        with torch.no_grad():
            out = model(x, labels=x)
        losses.append(float(out["loss"]))
    return float(np.mean(losses))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume_from", type=str, required=True,
                    help="dir with model.safetensors+config.json+tokenizer.json+metadata.json")
    ap.add_argument("--data_dir", type=str, default=None,
                    help="dir containing train.txt + val.txt (the reproducible corpus)")
    ap.add_argument("--output_dir", type=str, required=True)
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--seq_len", type=int, default=256)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--warmup_steps", type=int, default=10)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--grad_clip", type=float, default=1.0)
    ap.add_argument("--log_steps", type=int, default=5)
    ap.add_argument("--eval_steps", type=int, default=25)
    ap.add_argument("--save_steps", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", type=str, default="auto", choices=["auto", "cuda", "cpu"])
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)

    # ---- device / GPU gate ------------------------------------------------ #
    if args.device == "cuda" or (args.device == "auto" and not torch.cuda.is_available()):
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            print("[FATAL] CUDA not available. On Kaggle: enable an Accelerator=GPU(T4) kernel "
                  "and DON'T run unaccelerated (the legacy trainer would silently drop to 12M).")
            return 2
    else:
        device = torch.device("cpu")
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        print("[WARN] CPU path — continuing LOCAL only. A Kaggle GPU(T4) kernel is ~10-20x faster.")

    frozen = Path(args.resume_from)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ckpt_dir = out / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    print(f"[OUTPUT] {out}")

    # ---- config + model (strict, from frozen) --------------------------- #
    cfg = ModelConfig(**json.loads((frozen / "config.json").read_text()))
    model = SilverwingModel(cfg).to(device)
    base_meta = json.loads((frozen / "metadata.json").read_text()) \
        if (frozen / "metadata.json").exists() else {}
    base_step   = int(base_meta.get("step", 0))
    base_tokens = int(base_meta.get("tokens", base_meta.get("total_tokens", 0)))
    sd = load_file(str(frozen / "model.safetensors"))
    missing, unexpected = model.load_state_dict(sd, strict=True)
    print(f"[LOAD] params={sum(p.numel() for p in model.parameters())} "
          f"step={base_step} tokens={base_tokens:,} "
          f"strict_load missing={len(missing)} unexpected={len(unexpected)}")
    assert not missing and not unexpected, "checkpoint <-> SilverwingModel key mismatch!"

    # ---- SERVED tokenizer (NEVER retrain) --------------------------------- #
    tok = BPETokenizer.from_file(str(frozen / "tokenizer.json"))
    print(f"[TOKENIZER] loaded frozen tokenizer vocab={tok.vocab_size} "
          f"sha256={file_sha256(frozen/'tokenizer.json')}")

    # ---- corpus (cache encoded ids) -------------------------------------- #
    cache_train = out / "corpus_train.npy"
    cache_val = out / "corpus_val.npy"
    if cache_train.exists() and cache_val.exists():
        print("[DATA] loading cached token-id arrays ...")
        train_ids = np.load(cache_train)
        val_ids = np.load(cache_val)
    else:
        if not args.data_dir:
            print("[FATAL] --data_dir required on first run (no cached corpus).")
            return 2
        data = Path(args.data_dir)
        t0 = time.time()
        train_text = (data / "train.txt").read_text("utf-8", "replace")
        val_text = (data / "val.txt").read_text("utf-8", "replace")
        train_ids = np.asarray(tok.encode(train_text), dtype=np.int32)
        val_ids = np.asarray(tok.encode(val_text), dtype=np.int32)
        np.save(cache_train, train_ids)
        np.save(cache_val, val_ids)
        print(f"[DATA] train={len(train_ids)} val={len(val_ids)} tokens ({round(time.time()-t0,1)}s)")

    dataset_hash = file_sha256(Path(args.data_dir) / "train.txt") if args.data_dir else base_meta.get("dataset_hash")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95),
                            weight_decay=args.weight_decay, eps=1e-8)
    tokens_per_step = args.batch_size * args.seq_len * args.grad_accum

    metrics_path = out / "metrics.jsonl"
    lineage = {
        "base_model": "silverwing-120m-base-v1 r1",
        "base_model_sha256": file_sha256(frozen / "model.safetensors"),
        "base_config_sha256": file_sha256(frozen / "config.json"),
        "base_tokenizer_sha256": file_sha256(frozen / "tokenizer.json"),
        "base_step": base_step, "base_tokens": base_tokens,
        "base_train_loss": base_meta.get("train_loss"),
        "base_val_loss": base_meta.get("val_loss"),
        "dataset_train_sha256": dataset_hash,
    }
    print(f"[TRAIN] step {base_step} -> {base_step + args.steps} "
          f"(|{tokens_per_step} tok/optim-step, ~{round(args.steps*tokens_per_step/1e6,2)}M new tokens)")

    model.train()
    t0 = time.time(); running = 0.0; count = 0; gstep = base_step
    for s in range(1, args.steps + 1):
        opt.zero_grad(set_to_none=True)
        if gstep - base_step < args.warmup_steps:
            lr_scale = (gstep - base_step + 1) / max(1, args.warmup_steps)
        else:
            prog = (gstep - base_step - args.warmup_steps) / max(1, args.steps - args.warmup_steps)
            lr_scale = 0.5 * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = args.lr * lr_scale
        for _ in range(args.grad_accum):
            x = shard_ids(train_ids, args.batch_size, args.seq_len, rng).astype(np.int32)
            x = torch.from_numpy(x).long().to(device)
            mout = model(x, labels=x)
            loss = mout["loss"] / args.grad_accum
            loss.backward()
            running += float(loss.detach()) * args.grad_accum
            count += 1
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        opt.step()
        gstep += 1
        if s % args.log_steps == 0:
            elapsed = time.time() - t0
            trained = gstep - base_step
            print(f"[step {gstep}] loss={running/count:.4f} lr={opt.param_groups[0]['lr']:.2e} "
                  f"tok={base_tokens + trained*tokens_per_step:,} "
                  f"tok/s~{round(trained*tokens_per_step/elapsed)} elapsed={round(elapsed)}s")
        if s % args.eval_steps == 0:
            vl = eval_val_loss(model, val_ids, tok, args.seq_len, n=16)
            print(f"[eval] val_loss@step{gstep}={vl:.4f} (frozen val_loss={base_meta.get('val_loss')})")
            with open(metrics_path, "a") as f:
                f.write(json.dumps({"step": gstep, "val_loss": round(vl, 6)}) + "\n")
        if s % args.save_steps == 0:
            d = ckpt_dir / f"step-{gstep}"
            d.mkdir(exist_ok=True)
            sd = {k: v.contiguous().cpu() for k, v in model.state_dict().items()}
            _ptrs = {}
            for _k, _v in list(sd.items()):
                _p = _v.data_ptr()
                if _p in _ptrs:
                    sd[_k] = _v.clone()
                else:
                    _ptrs[_p] = _k
            save_file(sd, str(d / "model.safetensors"))
            (d / "tokenizer.json").write_bytes((frozen / "tokenizer.json").read_bytes())
            meta = dict(lineage)
            meta.update({"step": gstep, "new_tokens_trained": (gstep - base_step)*tokens_per_step,
                          "total_tokens": base_tokens + (gstep - base_step)*tokens_per_step,
                          "lr_peak": args.lr, "device": str(device), "torch": torch.__version__,
                          "config": {"n_layers": cfg.n_layers, "n_heads": cfg.n_heads,
                                     "n_kv_heads": cfg.n_kv_heads, "d_model": cfg.d_model,
                                     "hidden_size": cfg.hidden_size, "vocab_size": cfg.vocab_size,
                                     "max_position_embeddings": cfg.max_position_embeddings}})
            (d / "metadata.json").write_text(json.dumps(meta, indent=2))
            print(f"[ckpt] saved {d}")

    elapsed = time.time() - t0
    trained_tokens = (gstep - base_step) * tokens_per_step
    summary = dict(lineage)
    summary.update({
        "experiment": "exp_c_continue_120m", "step_start": base_step, "step_end": gstep,
        "steps_trained": args.steps, "tokens_trained": trained_tokens,
        "elapsed_s": round(elapsed, 2), "tok_s": round(trained_tokens / elapsed),
        "lr_peak": args.lr, "seq_len": args.seq_len, "batch": args.batch_size,
        "grad_accum": args.grad_accum,
    })
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2))
    print("[DONE] " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
