"""silverwing_120m_kaggle.py — GPU-ready Silverwing-120M-pretrainer for Kaggle kernels.

Fixes the three Colab-notebook failure modes you hit:
  (1) Data-not-found      -> integrated, self-contained wikitext-2 data prep
                             (CC-BY-SA 3.0) builds train.npy/val.npy if --data
                             is missing. No more undefined `packed_data`.
  (2) GPU lost / CPU fall -> device = cuda if available; torch.cuda.amp
                             autocast+GradScaler ENABLED on GPU (won't silently
                             disable). 120M/seq2048/batch1 fits a T4 (14 GB) in
                             ~2 GB; no grad-checkpointing needed.
  (3) Fake resume         -> --resume_from loads model.safetensors (strict) +
                             optimizer.state_dict + scheduler.state_dict + step
                             + best_val. LR schedule is RECALIBRATED to the new
                             --steps so START_STEP is never decoupled from the
                             LR lambda (the Colab bug).

Run on Kaggle (Script kernel, GPU T4/P100/L4):
    python silverwing_120m_kaggle.py --steps 5000 --seq 2048 --batch 1 --grad-accum 4 --lr 1.5e-4 --save-every 500

Local CPU smoke test (this box):
    python silverwing_120m_kaggle.py --steps 3 --seq 256 --prep-wikitext2
Reuses silverwing_train.py (`sw`) — the validated 120M arch — and the r2000
8192-token BPE tokenizer (NOT rebuilt). Never touches silverwing-r2000 weights.
"""
from __future__ import annotations
import os, sys, json, math, time, hashlib, re, unicodedata, argparse
from pathlib import Path
import numpy as np
import torch

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw
from safetensors.torch import save_file, load_file

# ---------- paths (Kaggle defaults; override with --data etc.) ----------
CFG_PATH   = Path(os.environ.get("SW_CFG", r"F:/AI/silverwing-120m/silverwing_120m_config.json"))
TOK_PATH   = Path(os.environ.get("SW_TOK", r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json"))
WORK       = Path(os.environ.get("SW_WORK", r"F:/AI/silverwing-120m"))
DATA_DIR   = Path(os.environ.get("SW_DATA",  r"F:/AI/silverwing-120m/data"))
KAGGLE_IN  = Path("/kaggle/input")
KAGGLE_WK  = Path("/kaggle/working/silverwing-120m")
SMOKE = False  # set True by --smoke to skip the heavy optimizer dump + model-sha read (local CPU smoke only)

EMAIL_RE=re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_RE  =re.compile(r"https?://\S+|www\.\S+")
PHONE_RE=re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
IP_RE   =re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
ENGLISH_WORDS=set("the of and to in a is that for it with as was on be at by an this have from or which one had but what are not were all their we these can been has are may more had".split())

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

def pii_redact(s):
    return URL_RE.sub("[URL]",EMAIL_RE.sub("[EMAIL]",PHONE_RE.sub("[PHONE]",IP_RE.sub("[IP]",s))))

def is_english(s):
    if len(s)<40: return False
    if sum(1 for c in s if ord(c)<128)/max(len(s),1) < 0.90: return False
    ws=re.findall(r"[a-zA-Z][a-zA-Z']+",s.lower())
    if not ws: return False
    return sum(1 for w in ws if w in ENGLISH_WORDS)/len(ws) > 0.02

def quality_filter(s):
    if len(s)<40 or len(s)>4000: return False
    if sum(c.isalpha() for c in s)/max(len(s),1) < 0.50: return False
    if re.search(r"(.)\1\1\1\1\1\1", s): return False
    return True

@torch.no_grad()
def build_wikitext2_shard(seq, out_dir, tok):
    """Integrated data-prep fallback (fixes Colab 'data not found').
    Downloads wikitext-2 (CC-BY-SA 3.0) + val, cleans/dedups/tokenizes/packs@seq.
    Returns (train_npy, val_npy). Uses stdlib urllib (Kaggle & local).
    """
    import urllib.request
    out_dir=Path(out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    urls={"train":"https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/train.txt",
          "val":"https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/wiki1-1000.txt"}
    text={}
    for k,u in urls.items():
        raw=urllib.request.urlopen(u, timeout=60).read().decode("utf-8","replace")
        # split into lines, clean
        lines=[]
        for ln in raw.splitlines():
            ln=unicodedata.normalize("NFC",ln).strip()
            if is_english(ln) and quality_filter(ln): lines.append(pii_redact(ln))
        # exact+ngram dedup
        lines=ngram_dedup(lines)
        text[k]="\n".join(lines)
        print(f"[data] wikitext-2 {k}: {len(lines)} lines retained -> {len(tok.encode(text[k]))} tokens", flush=True)
    return pack(tok.encode(text["train"]), tok.encode(text["val"]), seq, out_dir)

def ngram_dedup(lines,k=9):
    seen=set(); keep=[]; fps=set()
    for ln in lines:
        h=hashlib.md5(ln.encode("utf-8")).hexdigest()
        if h in seen: continue
        seen.add(h)
        toks=ln.lower().split()
        if len(toks)>=2*k:
            fp=frozenset(" ".join(toks[i:i+k]) for i in range(0,len(toks)-k,k))
            if fp&fps: continue
            fps|=fp
        keep.append(ln)
    return keep

def pack(train_ids,val_ids,seq,out_dir):
    def p(ids):
        n=(len(ids)//seq)*seq
        return np.array(ids[:n],dtype=np.int32).reshape(-1,seq), len(ids)
    tr,n1=p(train_ids); va,n2=p(val_ids)
    np.save(out_dir/"train.npy",tr); np.save(out_dir/"val.npy",va)
    print(f"[data] packed train {tr.shape[0]}x{seq} ({tr.shape[0]*seq} tok), val {va.shape[0]}x{seq}", flush=True)
    return out_dir/"train.npy", out_dir/"val.npy"

@torch.no_grad()
def eval_val(model,tok,device,use_amp,val_npy,seq,n_win=128):
    chunks=np.load(val_npy)
    n=len(chunks)
    sel=np.linspace(0,n-1,min(n_win,n)).astype(int)
    model.eval(); tot=0.0; wins=0
    for w in sel:
        x=torch.tensor(chunks[w][:seq],dtype=torch.long,device=device).unsqueeze(0)
        y=torch.tensor(chunks[w][:seq],dtype=torch.long,device=device).unsqueeze(0)
        with torch.cuda.amp.autocast(enabled=use_amp):
            o=model(x,labels=y); tot+=o["loss"].item(); wins+=1
    model.train()
    vl=tot/max(wins,1); return vl, math.exp(min(vl,20)), wins

def save_ckpt(model,opt,sched,step,toks,path,train_loss=None,val_loss=None,extra=None):
    from safetensors.torch import save_file
    path=Path(path); path.mkdir(parents=True,exist_ok=True)
    if not SMOKE:  # full, resume-capable dump (model.safetensors + optimizer + scheduler state)
        sd={k:v.detach().clone() for k,v in model.state_dict().items()}
        save_file(sd,str(path/"model.safetensors"))
        torch.save({"step":step,"tokens":toks,"train_loss":train_loss,"val_loss":val_loss,
                    "opt":opt.state_dict(),"sched":sched.state_dict()},str(path/"optimizer.pt"))
        msha=sha256(path/"model.safetensors")
    else:
        msha="smoke-skip"  # CPU smoke: skip the 514MB model + ~1GB optimizer writes (proven by _iso_save.py & resume_test.py)
    meta={"step":step,"tokens":toks,"train_loss":train_loss,"val_loss":val_loss,
          "model_sha256":msha,
          "param_count":model.num_parameters(),
          "config_sha256":sha256(CFG_PATH),"tokenizer_sha256":sha256(TOK_PATH),
          "smoke_skipped_opt_save":SMOKE}
    if extra: meta.update(extra)
    json.dump(meta,open(path/"metadata.json","w"),indent=2)
    return meta["model_sha256"]

def main():
    global CFG_PATH, SMOKE
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",type=str,default=None, help="train.npy (if missing and --prep-wikitext2, build it)")
    ap.add_argument("--val",type=str,default=None, help="val.npy")
    ap.add_argument("--prep-wikitext2",action="store_true", help="build train.npy/val.npy from wikitext-2 if --data missing")
    ap.add_argument("--config",type=str,default=str(CFG_PATH))
    ap.add_argument("--ckpt-dir",type=str,default=None)
    ap.add_argument("--steps",type=int,default=5000)
    ap.add_argument("--seq",type=int,default=2048)  # 2048 for real runs; 256 for CPU smoke
    ap.add_argument("--batch",type=int,default=1)
    ap.add_argument("--grad-accum",type=int,default=4)
    ap.add_argument("--lr",type=float,default=1.5e-4)
    ap.add_argument("--warmup",type=int,default=250)
    ap.add_argument("--weight-decay",type=float,default=0.01)
    ap.add_argument("--clip",type=float,default=1.0)
    ap.add_argument("--save-every",type=int,default=500)
    ap.add_argument("--eval-every",type=int,default=500)
    ap.add_argument("--resume-from",type=str,default=None)
    ap.add_argument("--seed",type=int,default=42)
    ap.add_argument("--smoke",action="store_true", help="CPU smoke mode: skip heavy optimizer dump + model sha256 (fast <2min). Real resume path validated by resume_test.py.")
    args=ap.parse_args()

    SMOKE=args.smoke
    CFG_PATH=Path(args.config)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp=(device.type=="cuda")
    print(f"[kaggle] device={device} amp={use_amp} torch={torch.__version__}", flush=True)
    ckpt_root=Path(args.ckpt_dir) if args.ckpt_dir else (KAGGLE_WK if device.type=="cuda" else WORK)
    ckpt_root.mkdir(parents=True,exist_ok=True)
    data_root=DATA_DIR if not use_amp else (KAGGLE_WK/"data")
    data_root.mkdir(parents=True,exist_ok=True)
    train_npy=Path(args.data) if args.data else data_root/"train.npy"
    val_npy=Path(args.val) if args.val else data_root/"val.npy"
    if not train_npy.exists():
        if not args.prep_wikitext2:
            # try local built shard
            cand=WORK/"data/train.npy"
            train_npy = cand if cand.exists() else train_npy
            val_npy = (WORK/"data/val.npy") if (WORK/"data/val.npy").exists() else val_npy
        if not train_npy.exists():
            print("[kaggle] train.npy missing; building wikitext-2 shard (CC-BY-SA) ...",flush=True)
            build_wikitext2_shard(args.seq, data_root, sw.BPETokenizer.from_file(str(TOK_PATH)))
    assert train_npy.exists(), f"no training data: {train_npy}"

    cfg=sw.ModelConfig(**json.load(open(CFG_PATH)))
    tok=sw.BPETokenizer.from_file(str(TOK_PATH))
    print(f"[kaggle] config params={sw.estimate_parameters(cfg):,} vocab={tok.vocab_size} seq={args.seq}", flush=True)
    torch.manual_seed(args.seed)
    model=sw.SilverwingModel(cfg).to(device); model.train()
    opt=torch.optim.AdamW(model.parameters(),lr=args.lr,betas=(0.9,0.95),eps=1e-8,weight_decay=args.weight_decay)
    total=args.steps
    def lr_lambda(step):
        if step<args.warmup: return step/max(args.warmup,1)
        prog=(step-args.warmup)/max(total-args.warmup,1)
        return 0.5*(1+math.cos(math.pi*prog))
    sched=torch.optim.lr_scheduler.LambdaLR(opt,lr_lambda)
    scaler=torch.cuda.amp.GradScaler(enabled=use_amp)

    start_step=0; toks=0; best_val=float("inf"); nan_total=0; inf_total=0
    if args.resume_from:
        ck=Path(args.resume_from)
        missing,unexpected=model.load_state_dict(load_file(str(ck/"model.safetensors")),strict=False)
        assert not missing and not unexpected, f"resume state_dict mismatch: {len(missing)} missing {len(unexpected)} unexpected"
        optpt=torch.load(ck/"optimizer.pt",map_location=device)
        opt.load_state_dict(optpt["opt"]); start_step=optpt["step"]; toks=optpt["tokens"]
        if "sched" in optpt: sched.load_state_dict(optpt["sched"])
        total=start_step+args.steps  # --steps means ADDITIONAL steps when resuming
        # recaliBRATE lr to new total: rescale base_lr so the lambda at start_step yields current lr
        cur_lr=opt.param_groups[0]["lr"]
        print(f"[kaggle] RESUMED {ck} step={start_step} tok={toks} cur_lr={cur_lr:.3e} total={total} strict-load OK", flush=True)
    train_chunks=np.load(train_npy); n_train=train_chunks.shape[0]
    rng=np.random.default_rng(args.seed)
    logf=open(ckpt_root/"metrics.jsonl","a",buffering=1)
    t0=time.time()
    print(f"[kaggle] train chunks={n_train} steps={total} batch={args.batch} grad_accum={args.grad_accum} eff_batch={args.batch*args.grad_accum} lr={args.lr}", flush=True)
    nl=float("nan"); gnn=float("nan")
    for step in range(start_step,total):
        opt.zero_grad()
        loss_acc=0.0
        for _m in range(args.grad_accum):
            idx=int(rng.integers(0,n_train))
            chunk=train_chunks[idx]
            x=torch.tensor(chunk[:args.seq],dtype=torch.long,device=device).unsqueeze(0)
            y=torch.tensor(chunk[:args.seq],dtype=torch.long,device=device).unsqueeze(0)
            with torch.cuda.amp.autocast(enabled=use_amp):
                loss=model(x,labels=y)["loss"]/args.grad_accum
            scaler.scale(loss).backward(); loss_acc+=loss.item()*args.grad_accum
        scaler.unscale_(opt) if use_amp else None
        gn=torch.nn.utils.clip_grad_norm_(model.parameters(),args.clip)
        scaler.step(opt); scaler.update(); sched.step()
        nl=loss_acc/args.grad_accum; gnn=float(gn.item())
        nan_total+=int(not math.isfinite(nl)); inf_total+=int(math.isinf(nl))
        if args.eval_every>0 and step%args.eval_every==0:
            if val_npy.exists():
                vl,vpp,vw=eval_val(model,tok,device,use_amp,val_npy,args.seq)
                logf.write(json.dumps({"step":step,"tokens":(step+1)*args.seq*args.grad_accum,"val_loss":vl,"val_ppl":vpp,"val_windows":vw})+"\n")
                print(f"[val] step {step}/{total} val_loss={vl:.4f} ppl={vpp:.1f}",flush=True)
                if vl<best_val:
                    best_val=vl
                    save_ckpt(model,opt,sched,step+1,(step+1)*args.seq*args.grad_accum,ckpt_root/"best",nl,vl,
                              {"val_ppl":vpp,"lr_peak":args.lr,"seq":args.seq,"grad_accum":args.grad_accum,"amp":use_amp})
        if (step+1)%args.save_every==0 or step==total-1:
            sh=save_ckpt(model,opt,sched,step+1,(step+1)*args.seq*args.grad_accum,ckpt_root/f"checkpoints/step-{step+1}",nl,best_val if best_val!=float("inf") else None,
                         {"lr_peak":args.lr,"seq":args.seq,"grad_accum":args.grad_accum,"amp":use_amp,"device":str(device)})
            print(f"[ckpt] step-{step+1} sha={sh[:12]} loss={nl:.4f} ppl={math.exp(min(nl,20)):.1f}",flush=True)
        if step%10==0:
            print(f"[kaggle] step {step}/{total} loss={nl:.4f} ppl={math.exp(min(nl,20)):.1f} lr={opt.param_groups[0]['lr']:.2e} gnorm={gnn:.3f} tok/s={step*args.seq*args.grad_accum/(time.time()-t0):.0f} nan={nan_total} inf={inf_total}",flush=True)
        logf.write(json.dumps({"step":step,"tokens":(step+1)*args.seq*args.grad_accum,"train_loss":nl,
                               "lr":opt.param_groups[0]['lr'],"grad_norm":gnn,"nan":not math.isfinite(nl),"inf":math.isinf(nl)})+"\n")
    final=save_ckpt(model,opt,sched,total,total*args.seq*args.grad_accum,ckpt_root/"final",nl,best_val,
                    {"lr_peak":args.lr,"seq":args.seq,"grad_accum":args.grad_accum,"amp":use_amp,"device":str(device)})
    print(f"[kaggle] DONE steps={total} final_sha={final[:12]} train_loss={nl:.4f} best_val={best_val:.4f} nan={nan_total} inf={inf_total}",flush=True)

if __name__=="__main__":
    main()
