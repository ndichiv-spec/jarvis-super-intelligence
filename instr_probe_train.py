"""Stage-3B probe: instruction-tuning probe on the FROZEN r2000 baseline.

Loads the read-only r2000 checkpoint, supervised-finetunes on the synthetic
instruction dataset (F:/AI/data/instr_train.txt) in the EXACT formats used by
stage3a_evaluate.py, and saves a NEW checkpoint tree under:
    F:/AI/silverwing-10m-instr-probe/

The frozen baseline (F:/AI/baselines/... and silverwing-r2000/final) is NEVER
written. Resume-friendly: checkpoints every N steps include model + optimizer
so a run killed at a turn boundary can `cmd /c` resume from the latest ckpt.

Probe recipe (instruction-finetune regime, NOT the wiki-continuation recipe):
  LR 3e-5 (standard IT LR; 15x below the failed 2e-4, 1.5x the corrected 1e-5),
  cosine + 5% warmup, 500 steps, AdamW(b .9/.95, eps 1e-8, wd .01),
  grad_clip 1.0, grad_accum 4, batch 1, seq_len 256, seed 42, float32 CPU.
(We EXPECT common-val loss to rise -- IT shifts output from prose to Q/A format;
benchmarks are the target metric.)
"""
from __future__ import annotations
import argparse, json, math, os, time
from pathlib import Path
import torch
from torch.optim import AdamW
from torch.nn.utils import clip_grad_norm_
from safetensors.torch import load_file, save_file

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
import sys
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw  # noqa: E402

R2000_FINAL  = r"F:/AI/silverwing-r2000/final"
R2000_TOK    = r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json"
R2000_CFG    = Path(R2000_FINAL) / "config.json"
R2000_MODEL  = Path(R2000_FINAL) / "model.safetensors"
COMMON_VAL   = r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/val.txt"
INSTR_TRAIN  = r"F:/AI/data/instr_train.txt"
OUT          = Path(r"F:/AI/silverwing-10m-instr-probe")

torch.set_num_threads(4)
DEVICE = torch.device("cpu")
MAX_LEN = 256

def get_lr(step, base, warmup, total):
    if step < warmup:
        return base * (step + 1) / max(1, warmup)
    p = (step - warmup) / max(1, (total - warmup))
    p = min(max(p, 0.0), 1.0)
    return 0.5 * base * (1.0 + math.cos(math.pi * p))

def seed_everything(s):
    import random; random.seed(s); torch.manual_seed(s); torch.use_deterministic_algorithms(False)

def load_tokenizer():
    return sw.BPETokenizer.from_file(R2000_TOK)

def val_loss(model, tok):
    text = Path(COMMON_VAL).read_text(encoding="utf-8", errors="replace")
    ids = tok.encode(text)
    windows = 128
    n = min(len(ids), (MAX_LEN + 1) * windows)
    vloss=0.0; vc=0
    with torch.no_grad():
        for i in range(0, n - (MAX_LEN + 1), MAX_LEN + 1):
            batch = torch.tensor(ids[i:i + MAX_LEN + 1], dtype=torch.long)
            inp = batch[:-1].unsqueeze(0); labels = batch[1:].unsqueeze(0)
            o = model(inp, labels=labels)
            vloss += o["loss"].item(); vc += 1
    return vloss / max(vc, 1)

def make_chunks(text, tok):
    ids = tok.encode(text)
    if len(ids) < MAX_LEN + 2:
        raise SystemExit("instruction dataset too short (%d tokens)" % len(ids))
    # flat stream of overlapping-ish consecutive windows; wraps via data_ptr
    return ids

def safe_state_dict(model):
    """state_dict with tied embeddings de-aliased (embed_tokens == lm_head share storage)."""
    sd = {k: v for k, v in model.state_dict().items()}
    if "lm_head.weight" in sd and "embed_tokens.weight" in sd:
        sd["lm_head.weight"] = sd["lm_head.weight"].clone()  # break shared storage
    return {k: v.contiguous() for k, v in sd.items()}

def save_ckpt(model, opt, step, data_ptr, tokens, train_loss, lr, path):
    path.mkdir(parents=True, exist_ok=True)
    sd = safe_state_dict(model)
    save_file(sd, str(path / "model.safetensors"))
    sha = sw.compute_hash(str(path / "model.safetensors"))
    torch.save({"opt": opt.state_dict(), "data_ptr": data_ptr, "step": step}, str(path / "optimizer.pt"))
    (path / "metadata.json").write_text(json.dumps({
        "step": step, "tag": "step-%d" % step, "train_loss": train_loss,
        "lr": lr, "total_tokens": tokens, "model_sha256": sha,
        "param_count": model.num_parameters(),
    }, indent=2), encoding="utf-8")
    if not (path/"config.json").exists():
        (path/"config.json").write_text(Path(R2000_CFG).read_text())
    print("[ckpt] saved step-%d sha=%s loss=%.4f" % (step, sha[:12], train_loss))
    return sha

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--save_every", type=int, default=100)
    ap.add_argument("--log_steps", type=int, default=20)
    ap.add_argument("--eval_every", type=int, default=50)
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--seq_len", type=int, default=MAX_LEN)
    ap.add_argument("--warmup_frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resume_from", default=None)
    args = ap.parse_args()

    seed_everything(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    warmup = max(1, int(args.steps * args.warmup_frac))

    # model + tokenizer (READ r2000; never write there)
    cfg = sw.ModelConfig(**json.loads(Path(R2000_CFG).read_text()))
    model = sw.SilverwingModel(cfg).to(DEVICE)
    sd = load_file(str(R2000_MODEL))
    model.load_state_dict(sd, strict=False)
    print("loaded r2000 init | params=%d sha=%s" % (model.num_parameters(), sw.compute_hash(R2000_MODEL)[:12]))
    tok = load_tokenizer()
    print("tokenizer vocab=%d" % tok.vocab_size)

    ids = make_chunks(Path(INSTR_TRAIN).read_text(encoding="utf-8"), tok)
    L = args.seq_len
    n_chunks_total = len(ids) - (L + 1)

    opt = AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95), eps=1e-8, weight_decay=0.01)

    start_step = 0; data_ptr = 0; global_tokens = 0
    if args.resume_from:
        ck = Path(args.resume_from)
        model.load_state_dict(load_file(str(ck / "model.safetensors")), strict=False)
        if (ck / "optimizer.pt").exists():
            st = torch.load(str(ck / "optimizer.pt"), map_location="cpu")
            opt.load_state_dict(st["opt"]); data_ptr = st.get("data_ptr", 0); start_step = st.get("step", 0)
        print("[resume] from %s step=%d data_ptr=%d" % (ck, start_step, data_ptr))

    metrics_f = open(OUT / "metrics.jsonl", "a", encoding="utf-8")
    t0 = time.time()
    nan_total = 0; inf_total = 0
    model.train()
    try:
        for step in range(start_step, args.steps):
            lr_now = get_lr(step, args.lr, warmup, args.steps)
            for g in opt.param_groups: g["lr"] = lr_now

            opt.zero_grad(set_to_none=True)
            run_loss = 0.0; run_tok = 0
            for _ in range(args.grad_accum):
                if data_ptr + L + 1 > n_chunks_total:
                    data_ptr = 0
                chunk = ids[data_ptr:data_ptr + L + 1]
                if len(chunk) < L + 1:        # tail guard
                    data_ptr = 0; chunk = ids[0:L + 1]
                input_ids = torch.tensor(chunk[:-1], dtype=torch.long).unsqueeze(0)
                labels = torch.tensor(chunk[1:], dtype=torch.long).unsqueeze(0)
                o = model(input_ids, labels=labels)
                loss = o["loss"]
                (loss / args.grad_accum).backward()
                run_loss += loss.item(); run_tok += L
                data_ptr += L + 1

            gnorm = clip_grad_norm_(model.parameters(), 1.0)
            gn = float(gnorm); nan = math.isnan(gn); inf = math.isinf(gn)
            if nan: nan_total += 1
            if inf: inf_total += 1
            opt.step()
            global_tokens += run_tok

            if (step + 1) % args.log_steps == 0:
                avg = run_loss / args.grad_accum
                rate = round(global_tokens / max(time.time() - t0, 1e-9), 1)
                row = {"step": step + 1, "steps": args.steps, "train_loss": round(avg,6),
                       "ppl": round(math.exp(min(avg, 20)),4), "lr": lr_now,
                       "grad_norm": round(gn,4), "grad_nan": nan, "grad_inf": inf,
                       "tok_per_s": rate, "elapsed_s": round(time.time() - t0, 1),
                       "tokens": global_tokens}
                metrics_f.write(json.dumps(row) + "\n"); metrics_f.flush()
                print("[instr-probe] step %d/%d loss=%.4f ppl=%.2f lr=%.2e gnorm=%.3f nan=%d inf=%d t/s=%s tok=%d" %
                      (step+1, args.steps, avg, row["ppl"], lr_now, gn, int(nan), int(inf), rate, global_tokens))
            if (step + 1) % args.eval_every == 0:
                v = val_loss(model, tok)
                print("[instr-probe] val_loss(step %d)=%.4f ppl=%.2f (expected to rise vs r2000 6.3445)" % (step+1, v, math.exp(min(v,20))))
            if (step + 1) % args.save_every == 0:
                save_ckpt(model, opt, step + 1, data_ptr, global_tokens,
                          run_loss / args.grad_accum, lr_now,
                          OUT / "checkpoints" / ("step-%d" % (step+1)))
    finally:
        metrics_f.close()

    avg = run_loss / args.grad_accum
    # final + best
    final = OUT / "final"
    final.mkdir(parents=True, exist_ok=True)
    save_file(safe_state_dict(model), str(final/"model.safetensors"))
    (final/"config.json").write_text(Path(R2000_CFG).read_text())
    sha = sw.compute_hash(str(final/"model.safetensors"))
    (final/"metadata.json").write_text(json.dumps({"step":args.steps,"tag":"final",
        "train_loss":avg,"lr":lr_now,"total_tokens":global_tokens,"model_sha256":sha,
        "param_count":model.num_parameters()}, indent=2), encoding="utf-8")
    print("[instr-probe] DONE. final sha=%s params=%d tokens_trained=%d" % (sha[:12], model.num_parameters(), global_tokens))
    print("[instr-probe] NOTE: common-val loss expected to rise (IT shifts prose->Q/A). "
          "Run stage3a_evaluate.py --ckpt %s/final --label r2000_instr --out eval/r2000_instr_eval.json" % OUT)

if __name__ == "__main__":
    main()
