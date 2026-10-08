#!/usr/bin/env python3
"""Phase 2 — Continue-pretraining silverwing-120m-base-v1 from the FROZEN checkpoint.

This script NEVER writes to the frozen baseline under ``.sw_cache`` /
``silverwing-models``; it only READS the frozen weights (strict load) and writes
new checkpoints to a fresh experiment directory
(``silverwing/local_run/exp_c_continue_120m/``).

It reuses the trainer's own classes (``silverwing.training.train``) so the
resumed checkpoint and architecture are guaranteed identical to what produced
``silverwing-120m-base-v1``.

Usage:
    python silverwing/phase2_continue_pretrain.py --steps 100 --seq_len 256
    python silverwing/phase2_continue_pretrain.py --steps 30 --eval_every 10
"""
from __future__ import annotations

import argparse, json, math, os, time, hashlib
from pathlib import Path

import numpy as np
import torch

ROOT = Path(r"F:\AI\Jarvis-super-intelligence-")
CACHE = ROOT / "silverwing" / "local_run" / "exp_c_continue_120m"
CORPUS = ROOT / "silverwing" / "data_pipeline" / "processed"
FROZEN = Path(r"F:\AI\.sw_cache\silverwing-120m-base/r1")

import sys as _sys
for _p in (str(ROOT), str(ROOT.parent)):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
from silverwing.training.train import SilverwingModel, ModelConfig, BPETokenizer  # noqa: E402

from safetensors.torch import load_file, save_file


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_corpus(tok, train_path: Path, val_path: Path, seq_len: int) -> tuple[np.ndarray, np.ndarray]:
    print(f"[DATA] encoding corpus train={train_path} val={val_path} ...")
    t0 = time.time()
    train_text = train_path.read_text("utf-8", "replace")
    val_text = val_path.read_text("utf-8", "replace")
    train_ids = np.asarray(tok.encode(train_text), dtype=np.int32)
    val_ids = np.asarray(tok.encode(val_text), dtype=np.int32)
    print(f"[DATA] train={len(train_ids)} tokens val={len(val_ids)} tokens "
          f"({round(time.time()-t0,1)}s)")
    return train_ids, val_ids


def sample_batch(ids: np.ndarray, batch: int, seq_len: int, device: str, rng: np.random.Generator):
    """Random contiguous sequences, wrapped with BOS(1) ... pad to seq_len."""
    T = seq_len
    out = torch.empty(batch, T, dtype=torch.long, device=device)
    for b in range(batch):
        i = int(rng.integers(0, max(1, len(ids) - T - 1)))
        seq = ids[i:i + T].copy()
        out[b] = torch.from_numpy(seq)
    return out


@torch.no_grad()
def eval_val_loss(model, val_ids: np.ndarray, tok, seq_len: int, n: int = 64, grad_accum_units: int = 256) -> float:
    if len(val_ids) < seq_len + 1:
        return float("nan")
    losses = []
    T = min(seq_len, 256)
    for _ in range(n):
        i = int(np.random.randint(0, max(1, len(val_ids) - T - 1)))
        ids = torch.from_numpy(val_ids[i:i + T]).long().unsqueeze(0)
        with torch.no_grad():
            out = model(ids, labels=ids)
        losses.append(float(out["loss"]))
    return float(np.mean(losses))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--seq_len", type=int, default=256)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--warmup_steps", type=int, default=10)
    ap.add_argument("--log_every", type=int, default=5)
    ap.add_argument("--eval_every", type=int, default=25)
    ap.add_argument("--save_every", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = "cpu"
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    print("[CONFIG] loading frozen 120M config + checkpoint (strict, read-only) ...")
    cfg = ModelConfig(**json.loads((FROZEN / "config.json").read_text()))
    model = SilverwingModel(cfg).to(device)
    sd = load_file(str(FROZEN / "model.safetensors"))
    missing, unexpected = model.load_state_dict(sd, strict=True)
    base_params = sum(p.numel() for p in model.parameters())
    print(f"[CONFIG] params={base_params} (expected 120087552) "
          f"loaded_tensors={len(sd)} missing={len(missing)} unexpected={len(unexpected)}")
    assert base_params == 120087552, "architecture mismatch!"
    assert len(missing) == 0 and len(unexpected) == 0, "checkpoint key mismatch!"

    print("[TOKENIZER] loading served tokenizer (must match training) ...")
    tok = BPETokenizer.from_file(str(FROZEN / "tokenizer.json"))
    print(f"[TOKENIZER] vocab={tok.vocab_size} sha256={file_sha256(FROZEN/'tokenizer.json')}")

    train_ids, val_ids = load_corpus(tok, CORPUS / "train.txt", CORPUS / "val.txt", args.seq_len)
    # (the ternary above is intentionally kept simple)

    base_step = 400          # frozen checkpoint reached step 400
    base_tokens = 409600     # ... over 409,600 tokens
    start_step = base_step
    total_tokens = base_tokens
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr,
                            betas=(0.9, 0.95), weight_decay=args.weight_decay, eps=1e-8)

    metrics_path = CACHE / "metrics.jsonl"
    ckpt_dir = CACHE / "checkpoints"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text("", encoding="utf-8")  # truncate

    tokens_per_step = args.batch_size * args.seq_len * args.grad_accum
    print(f"[TRAIN] resuming step {start_step}, targeting step {start_step + args.steps} "
          f"(|{tokens_per_step} tokens/optim-step, ~{round(args.steps*tokens_per_step/1e6,2)}M new tokens)")

    model.train()
    t0 = time.time()
    running = 0.0
    count = 0
    global_step = start_step
    for s in range(1, args.steps + 1):
        opt.zero_grad(set_to_none=True)
        # cosine schedule over the NEW run (warmup first)
        if global_step - start_step < args.warmup_steps:
            lr_scale = (global_step - start_step + 1) / max(1, args.warmup_steps)
        else:
            prog = (global_step - start_step - args.warmup_steps) / max(1, args.steps - args.warmup_steps)
            lr_scale = 0.5 * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = args.lr * lr_scale
        for _ in range(args.grad_accum):
            x = sample_batch(train_ids, args.batch_size, args.seq_len, device, rng)
            out = model(x, labels=x)
            loss = out["loss"] / args.grad_accum
            loss.backward()
            running += float(loss) * args.grad_accum
            count += 1
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        global_step += 1
        total_tokens += tokens_per_step
        if s % args.log_every == 0:
            elapsed = time.time() - t0
            tok_s = total_tokens / elapsed
            avg_loss = running / count
            print(f"[step {global_step}] loss={avg_loss:.4f} lr={opt.param_groups[0]['lr']:.2e} "
                  f"tok={total_tokens:,} tok/s~{round(tok_s)} elapsed={round(elapsed)}s")
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "step": global_step, "train_loss": round(avg_loss, 6),
                    "lr": opt.param_groups[0]["lr"],
                    "tokens": total_tokens, "elapsed_s": round(elapsed, 2),
                    "tok_s": round(tok_s),
                }) + "\n")
            running, count = 0.0, 0
        if s % args.eval_every == 0:
            vl = eval_val_loss(model, val_ids, tok, args.seq_len, n=64)
            print(f"[eval] val_loss@step{global_step}={vl:.4f} (baseline frozen val_loss=5.4373)")
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"step": global_step, "val_loss": round(vl, 6)}) + "\n")

        if s % args.save_every == 0:
            step_dir = ckpt_dir / f"step-{global_step}"
            step_dir.mkdir(parents=True, exist_ok=True)
            sd = {k: v.contiguous() for k, v in model.state_dict().items()}
            # dedupe tied weights (lm_head.weight == embed_tokens.weight) so safetensors can save
            _ptrs = {}
            for _k, _v in list(sd.items()):
                _p = _v.data_ptr()
                if _p in _ptrs:
                    sd[_k] = _v.clone()
                else:
                    _ptrs[_p] = _k
            save_file(sd, str(step_dir / "model.safetensors"))
            meta = {
                "step": global_step,
                "base_checkpoint": "silverwing-120m-base-v1 r1 (da860489…) step-400",
                "base_model_sha256": file_sha256(FROZEN / "model.safetensors"),
                "base_config_sha256": file_sha256(FROZEN / "config.json"),
                "tokenizer_sha256": file_sha256(FROZEN / "tokenizer.json"),
                "dataset_train_sha256": file_sha256(CORPUS / "train.txt"),
                "dataset_val_sha256": file_sha256(CORPUS / "val.txt"),
                "tokens_trained_since_resume": total_tokens - base_tokens,
                "lr": opt.param_groups[0]["lr"],
                "config": {"n_layers": cfg.n_layers, "n_heads": cfg.n_heads,
                           "n_kv_heads": cfg.n_kv_heads, "d_model": cfg.d_model,
                           "hidden_size": cfg.hidden_size, "vocab_size": cfg.vocab_size,
                           "max_position_embeddings": cfg.max_position_embeddings,
                           "tie_word_embeddings": cfg.tie_word_embeddings},
                "device": device,
                "torch_version": torch.__version__,
                "seed": args.seed,
            }
            (step_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(f"[ckpt] saved {step_dir}")

    summary = {
        "experiment": "exp_c_continue_120m",
        "from_checkpoint": "silverwing-120m-base-v1 r1 (da860489943c6bfe2e826a0a9325e75e381b4ef0a48270f4c4c6a6a4ef12abb4) step-400",
        "steps_trained": args.steps,
        "step_start": start_step, "step_end": global_step,
        "tokens_since_resume": total_tokens - base_tokens,
        "final_train_loss": round(running / max(1, count), 6) if count else None,
        "elapsed_s": round(time.time() - t0, 2),
        "tok_s": round((total_tokens - base_tokens) / (time.time() - t0)),
        "lr_peak": args.lr,
        "seq_len": args.seq_len, "batch": args.batch_size, "grad_accum": args.grad_accum,
        "metrics_path": str(metrics_path),
        "checkpoints_dir": str(ckpt_dir),
    }
    (CACHE / "training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[DONE] " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
