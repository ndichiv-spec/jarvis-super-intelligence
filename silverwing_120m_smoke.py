"""Phase A — Silverwing-120M-v1 SMOKE PRETRAINING (120 steps).

Purpose (brief section 16 Phase A): confirm the 120M architecture trains on CPU:
loss decreases, no instability, checkpoint restores, generation works.

- Loads silverwing_120m_config.json (the validated 120M config, NOT the 12M r2000).
- Corpus: existing stage3a Wikipedia/Gutenberg train.txt (first 256k chars -> ~64k tokens;
  enough for a smoke; real runs will use the full controlled corpus built in stage 3B).
- LR 2e-4 peak (120M needs a LARGER lr than 12M's 1e-5), cosine + 10-step warmup, AdamW,
  grad_clip 1.0, grad_accum 1, batch 1, seq 256, seed 42, float32 CPU.
- Writes F:/AI/silverwing-120m/{checkpoints/step-N, final, metrics.jsonl, smoke.log}.
- Resume via --resume_from <step-N> (restores model + AdamW + global step + token count).
- Tied-embedding de-alias on save (safetensors rejects shared-storage tensors).
- 12M r2000 baseline is READ-ONLY: this trainer never touches silverwing-r2000/.
"""
from __future__ import annotations
import os, sys, json, math, time, argparse, hashlib
from pathlib import Path
import torch
from safetensors.torch import save_file, load_file

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw

WORK = Path(r"F:/AI/silverwing-120m")
CFG_PATH = WORK / "silverwing_120m_config.json"
R2000_TOK = Path(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")   # reuse tokenizer (compatible)
CORPUS = Path(r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/train.txt")  # normal read
VAL = Path(r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/val.txt")

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

@torch.no_grad()
def val_loss(model, ids, bs=128):
    """Fixed-window (128-token) validation loss on the common val, same scheme as r2000 eval."""
    model.eval()
    tot=0.0; wins=0; ntok=0
    step=128
    for i in range(0, max(0,len(ids)-step), step):
        w = ids[i:i+step+1]
        if len(w) < step+1: break
        x = torch.tensor(w[:-1], dtype=torch.long).unsqueeze(0)
        y = torch.tensor(w[1:], dtype=torch.long).unsqueeze(0)
        o = model(x, labels=y)
        tot += o["loss"].item(); wins += 1; ntok += step
    model.train()
    vl = tot/max(wins,1)
    return vl, math.exp(min(vl,20)), wins, ntok

def safe_state_dict(model):
    """Clone tied lm_head so safetensors-save_file accepts it (no shared storage)."""
    from safetensors.torch import save_file
    sd = {k: v.detach().clone() for k,v in model.state_dict().items()}
    # if embeddings are tied, lm_head.weight IS embed_tokens.weight (same storage).
    # clone already broke storage sharing above. ensure distinct:
    return sd

def save_ckpt(model, opt, step, toks, path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    from safetensors.torch import save_file
    sd = safe_state_dict(model)
    save_file(sd, str(path/"model.safetensors"))
    torch.save({"step":step,"tokens":toks,"opt":opt.state_dict()}, str(path/"optimizer.pt"))
    meta = {"step":step,"tokens":toks,"model_sha256":sha256(path/"model.safetensors"),
            "train_loss":None}
    json.dump(meta, open(path/"metadata.json","w"), indent=2)
    return sha256(path/"model.safetensors")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--grad_accum", type=int, default=1)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--save_every", type=int, default=40)
    ap.add_argument("--eval_every", type=int, default=40)
    ap.add_argument("--resume_from", type=str, default=None)
    args = ap.parse_args()

    (WORK/"checkpoints").mkdir(parents=True, exist_ok=True)
    cfg = sw.ModelConfig(**json.load(open(CFG_PATH)))
    torch.manual_seed(42)
    model = sw.SilverwingModel(cfg)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01, eps=1e-8, betas=(0.9,0.95))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (s+1)/max(args.warmup,1) if s<args.warmup
                                               else 0.5*(1+math.cos(math.pi*(s-args.warmup)/(max(args.steps,args.warmup+1)-args.warmup))))
    tok = sw.BPETokenizer.from_file(str(R2000_TOK))

    # corpus: first 256k chars -> tokenize once
    print("[DATA] loading corpus (first 256k chars) ...", flush=True)
    raw = open(CORPUS, encoding="utf-8", errors="replace").read(262144)
    ids = tok.encode(raw)
    print(f"[DATA] {len(raw):,} chars -> {len(ids):,} tokens", flush=True)
    ids = torch.tensor(ids, dtype=torch.long)
    val_ids = tok.encode(open(VAL, encoding="utf-8", errors="replace").read(65536))

    start_step = 0; toks_done = 0
    if args.resume_from:
        rp = Path(args.resume_from)
        model.load_state_dict(load_file(str(rp/"model.safetensors")), strict=False)
        ck = torch.load(rp/"optimizer.pt", map_location="cpu", weights_only=False)
        opt.load_state_dict(ck["opt"]); start_step = ck["step"]; toks_done = ck["tokens"]
        print(f"[RESUME] from {rp} step={start_step} tokens={toks_done}", flush=True)

    logf = open(WORK/"metrics.jsonl","a",buffering=1)
    L = args.steps
    for step in range(start_step, L):
        i = (step * args.seq) % (len(ids) - args.seq - 1)
        x = ids[i:i+args.seq].unsqueeze(0)
        y = ids[i+1:i+args.seq+1].unsqueeze(0)
        o = model(x, labels=y)
        loss = o["loss"]; (loss/args.grad_accum).backward()
        gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step(); opt.zero_grad()
        if step % 5 == 0:
            print(f"[120M-smoke] step {step}/{L} loss={loss.item():.4f} ppl={math.exp(min(loss.item(),20)):.1f} "
                  f"lr={opt.param_groups[0]['lr']:.2e} gnorm={gn.item():.3f} nan={bool(torch.isnan(loss).any())} "
                  f"inf={bool(torch.isinf(loss).any())} tok={step*args.seq*(args.batch)}", flush=True)
        logf.write(json.dumps({"step":step,"train_loss":loss.item(),"lr":opt.param_groups[0]['lr'],
                               "grad_norm":gn.item(),"nan":bool(torch.isnan(loss).any()),
                               "inf":bool(torch.isinf(loss).any())})+ "\n")
        if (step+1) % args.save_every == 0 or step == L-1:
            sh = save_ckpt(model, opt, step+1, (step+1)*args.seq, WORK/f"checkpoints/step-{step+1}")
            print(f"[ckpt] saved step-{step+1} sha={sh[:12]} loss={loss.item():.4f}", flush=True)
        if (step+1) % args.eval_every == 0:
            vl,vpp,vw,vt = val_loss(model, val_ids)
            print(f"[val] step {step+1}/{L} val_loss={vl:.4f} ppl={vpp:.1f} windows={vw} tokens={vt}", flush=True)
    # final
    sh = save_ckpt(model, opt, L, L*args.seq, WORK/"final")
    print(f"[final] saved final sha={sh[:12]} params={model.num_parameters()}", flush=True)

    # generation sanity (Phase A: generation works) -- reuse in-mem trained weights
    model.eval()
    PROMPTS = ["The story began", "Science is", "What is 17 × 24?", "Explain gravity."]
    print("[gen] sample generation (120M, fresh from smoke):", flush=True)
    with open(WORK / "sample_generations.txt", "w", encoding="utf-8") as f:
        f.write("Silverwing-120M-v1 sample generations (Phase A smoke, 50 steps, LR 2e-4, seq 256)\n"
                + "=" * 70 + "\n")
        for p in PROMPTS:
            with torch.no_grad():
                ids = torch.tensor([tok.encode(p)], dtype=torch.long)
                g = model.generate(ids, max_new_tokens=48, temperature=0.8, top_p=0.9)
                text = tok.decode(g[0].tolist())
                f.write(f"\nPROMPT: {p}\nGEN: {text}\n" + "-" * 70 + "\n")
            print(f"  GEN {p!r}: {text[:80].encode('utf-8', 'replace').decode('utf-8')!r}", flush=True)
    print("[smoke] DONE.", flush=True)

if __name__ == "__main__":
    main()
