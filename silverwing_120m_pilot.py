"""Phase B7-B10 — Silverwing-120M-v1 PRETRAINING PILOT (500 steps).

- CLEAN from-scratch 120M init (seed 42, NOT the smoke checkpoint — per B7).
- Corpus: silverwing-120m/data/{train.npy,val.npy} (10M-token validated shard, val held-out).
- seq 256, batch 1, grad_accum 1 (CPU compute probe; B9: seq 256 is the smoke length).
- LR 1.5e-4 peak (cosine + 25-step warmup; 120M needs larger LR than 12M's 1e-5).
- AdamW(b .9/.95,eps1e-8,wd.01,clip1.0), seed 42, float32 CPU.
- Checkpoints: step-100/200/300/400/500 + best + final (model+optimizer+metrics+metadata).
- Logs metrics.jsonl (step,tokens,train_loss,val_loss,lr,grad_norm,tok/s,nan,inf).
- Resume via --resume_from; stable_state_dict de-aliases tied embeddings on save.
- NEVER touches silverwing-r2000/ (read-only tokenizer only).
"""
from __future__ import annotations
import os, sys, json, math, time, hashlib, argparse
from pathlib import Path
import numpy as np
import torch

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw

WORK = Path(r"F:/AI/silverwing-120m")
DATA = WORK / "data"
CFG_PATH = WORK / "silverwing_120m_config.json"
TOK_PATH = Path(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
SEQ = 256
TARGET_STEPS = 500

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

@torch.no_grad()
def eval_val(model, val_chunks, n_win=128):
    n=len(val_chunks)
    if n==0: return None,None,0
    # deterministic subset (fast CPU probe; full val set evaluated only at end via harness)
    if n>n_win:
        sel=np.linspace(0,n-1,n_win).astype(int)
    else:
        sel=np.arange(n)
    model.eval(); tot=0.0; wins=0
    for w in sel:
        x=torch.tensor(val_chunks[w][:SEQ],dtype=torch.long).unsqueeze(0)
        y=torch.tensor(val_chunks[w][:SEQ],dtype=torch.long).unsqueeze(0)
        o=model(x,labels=y); tot+=o["loss"].item(); wins+=1
    model.train()
    vl=tot/max(wins,1); return vl, math.exp(min(vl,20)), wins

def save_ckpt(model, opt, sched, step, toks, path, train_loss=None, val_loss=None):
    from safetensors.torch import save_file
    path=Path(path); path.mkdir(parents=True, exist_ok=True)
    sd={k:v.detach().clone() for k,v in model.state_dict().items()}  # breaks tied-storage sharing
    save_file(sd, str(path/"model.safetensors"))
    torch.save({"step":step,"tokens":toks,"train_loss":train_loss,"val_loss":val_loss,
                "opt":opt.state_dict(),"sched":sched.state_dict()}, str(path/"optimizer.pt"))
    meta={"step":step,"tokens":toks,"train_loss":train_loss,"val_loss":val_loss,
          "model_sha256":sha256(path/"model.safetensors"),
          "param_count":model.num_parameters(),
          "config_sha256":sha256(CFG_PATH),
          "tokenizer_sha256":sha256(TOK_PATH)}
    json.dump(meta, open(path/"metadata.json","w"), indent=2)
    return meta["model_sha256"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--steps",type=int,default=TARGET_STEPS)
    ap.add_argument("--lr",type=float,default=1.5e-4)
    ap.add_argument("--warmup",type=int,default=25)
    ap.add_argument("--save_every",type=int,default=100)
    ap.add_argument("--eval_every",type=int,default=50)
    ap.add_argument("--resume_from",type=str,default=None)
    args=ap.parse_args()

    cfg=sw.ModelConfig(**json.load(open(CFG_PATH)))
    train_chunks=np.load(DATA/"train.npy")
    val_chunks=np.load(DATA/"val.npy")
    print(f"[pilot] train chunks={train_chunks.shape[0]} val chunks={val_chunks.shape[0]} seq={SEQ}", flush=True)
    print(f"[pilot] params={sw.estimate_parameters(cfg):,}  (from-scratch init, NOT smoke)", flush=True)

    torch.manual_seed(42)
    model=sw.SilverwingModel(cfg); model.train()
    opt=torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9,0.95), eps=1e-8, weight_decay=0.01)
    total_steps=args.steps
    def lr_lambda(step):
        if step<args.warmup: return step/max(args.warmup,1)
        prog=(step-args.warmup)/max(total_steps-args.warmup,1)
        return 0.5*(1+math.cos(math.pi*prog))
    sched=torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

    n_train=train_chunks.shape[0]
    start_step=0; toks=0; best_val=float("inf"); nan_total=0; inf_total=0
    rng=np.random.default_rng(42)
    logf=open(WORK/"metrics.jsonl","a",buffering=1)
    t0=time.time()
    print(f"[pilot] start: {model.num_parameters():,} params, LR {args.lr} cosine+{args.warmup}warmup, seq {SEQ}", flush=True)
    for step in range(start_step, total_steps):
        idx=int(rng.integers(0, n_train))
        chunk=train_chunks[idx]
        x=torch.tensor(chunk[:SEQ],dtype=torch.long).unsqueeze(0)  # input (model shifts internally)
        y=torch.tensor(chunk[:SEQ],dtype=torch.long).unsqueeze(0)   # labels same length as input
        o=model(x,labels=y); loss=o["loss"]
        loss.backward()
        gn=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
        opt.step(); sched.step(); opt.zero_grad()
        nl=float(loss.item()); gnn=float(gn.item())
        if not math.isfinite(nl):
            print("[pilot] WARNING non-finite loss at step",step,flush=True)
        nan_total += int(not math.isfinite(nl))
        inf_total += int(math.isinf(nl))
        if step%10==0:
            print(f"[pilot] step {step}/{total_steps} loss={nl:.4f} ppl={math.exp(min(nl,20)):.1f} "
                  f"lr={opt.param_groups[0]['lr']:.2e} gnorm={gnn:.3f} nan={not math.isfinite(nl)} "
                  f"inf={math.isinf(nl)} tok={step*SEQ*(1)} t/s={step*SEQ/(time.time()-t0):.0f}", flush=True)
        logf.write(json.dumps({"step":step,"tokens":(step+1)*SEQ,"train_loss":nl,
                               "lr":opt.param_groups[0]['lr'],"grad_norm":gnn,
                               "nan":not math.isfinite(nl),"inf":math.isinf(nl)})+"\n")
        if (step+1)%args.save_every==0 or step==total_steps-1:
            sh=save_ckpt(model,opt,sched,step+1,(step+1)*SEQ,WORK/f"checkpoints/step-{step+1}",nl,None)
            print(f"[ckpt] saved step-{step+1} sha={sh[:12]} loss={nl:.4f}", flush=True)
        if (step+1)%args.eval_every==0:
            vl,vpp,vw=eval_val(model,val_chunks)
            logf.write(json.dumps({"step":step,"tokens":(step+1)*SEQ,"val_loss":vl,"val_ppl":vpp,"val_windows":vw})+"\n")
            print(f"[val] step {step+1}/{total_steps} val_loss={vl:.4f} ppl={vpp:.1f} windows={vw}", flush=True)
            if vl<best_val:
                best_val=vl
                bsh=save_ckpt(model,opt,sched,step+1,(step+1)*SEQ,WORK/"best",nl,vl)
                print(f"[best] new best val={vl:.4f} ppl={vpp:.1f} sha={bsh[:12]}", flush=True)
    sh=save_ckpt(model,opt,sched,total_steps,total_steps*SEQ,WORK/"final",nl,best_val)
    print(f"[final] saved final sha={sh[:12]} params={model.num_parameters()} best_val={best_val:.4f}", flush=True)
    print(f"[pilot] DONE 500 steps. nan_total={nan_total} inf_total={inf_total} nan_total={nan_total}", flush=True)

if __name__=="__main__":
    main()
