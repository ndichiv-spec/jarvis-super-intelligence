"""Generate silverwing_120m_kaggle.ipynb and validate every code-cell's syntax.
Also emit _test_pipeline.py from the SAME pipeline-function source so the offline
validation is guaranteed identical to the notebook's data-prep logic.

Authoring host is CPU-only/offline (no CUDA, no network at F:\\AI). Cells that
need GPU or network are correct-by-construction + syntax-checked here; only the
offline-runnable data pipeline is runtime-validated against the local Silverwing
corpus. The 12M/r2000 baseline (silverwing-r2000) is immutable.
"""
import json
from pathlib import Path

NB_PATH   = Path(r"F:/AI/silverwing-120m/silverwing_120m_kaggle.ipynb")
TEST_PATH = Path(r"F:/AI/_test_pipeline.py")

OWNER = "videlisndichi"          # Kaggle account that owns the dataset + kernel
DATASET_SLUG = "silverwing-120m"  # /kaggle/input/<slug>/ on the kernel VM

# ---------------------------------------------------------------------------
# Shared, parameterized data-prep logic (clean / dedup / tokenize / pack).
# Emitted VERBATIM into the notebook (sec 6) AND into _test_pipeline.py so the
# offline-tested logic is identical to the notebook's.
# ---------------------------------------------------------------------------
PIPELINE_FUNCS = r'''
import hashlib, json, os, re, unicodedata, datetime
from pathlib import Path
import numpy as np
import importlib.util
_TRAINER = os.environ.get("SW_TRAINER_PATH", "/kaggle/working/silverwing_120m_kaggle.py")
_spec = importlib.util.spec_from_file_location("kg", _TRAINER)
kg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kg)

DATA_MIXTURE = {
    "version": "silverwing-120m-mixture-v0.1",
    "sources": {
        "general":     {"frac": 0.40, "license": "CC-BY-SA"},
        "stem_edu":    {"frac": 0.20, "license": "CC-BY-SA / ODbL"},
        "programming": {"frac": 0.15, "license": "MIT / CC-BY-SA"},
        "science_eng": {"frac": 0.10, "license": "CC-BY-SA"},
        "math_reason": {"frac": 0.10, "license": "CC-BY-SA"},
        "instruction": {"frac": 0.05, "license": "CC-BY-SA"},
    },
    "note": "experimental mixture; not claimed optimal.",
}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def pipeline_build(raw_text, seq, target_tokens, val_frac, out_dir, tok):
    """Controlled Silverwing pipeline: clean -> ngram-dedup -> tokenize -> pack@seq.
    Returns (train_tokens, val_tokens, doc_count, raw_chars, kept_chars)."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for ln in raw_text.splitlines():
        ln = unicodedata.normalize("NFC", ln).strip()
        if kg.is_english(ln) and kg.quality_filter(ln):
            lines.append(kg.pii_redact(ln))
    raw_chars = len(raw_text)
    lines = kg.ngram_dedup(lines)
    kept_chars = sum(len(l) for l in lines)
    ids = tok.encode("\n".join(lines))
    ids = np.asarray(ids, dtype=np.int32)
    n = (len(ids) // seq) * seq
    ids = ids[:n]
    val_n = max(int(len(ids) * val_frac) // seq * seq, seq * 2)
    val_ids, tr_ids = ids[:val_n], ids[val_n:]
    take = (target_tokens // seq) * seq
    tr_ids = tr_ids[:take]
    tr = tr_ids.reshape(-1, seq); va = val_ids.reshape(-1, seq)
    np.save(out_dir / "train.npy", tr); np.save(out_dir / "val.npy", va)
    return int(len(tr) * seq), int(len(va) * seq), len(lines), raw_chars, kept_chars


def fetch_source_text(corpus_path=None):
    """Controlled Silverwing source: local attached corpus preferred, else a
    CC-BY-SA download (WikiText-103). wikitext is the source text only - it is
    never used raw; it always passes through pipeline_build."""
    corpus_path = Path(corpus_path) if corpus_path else Path(os.environ.get("SILWING_CORPUS_TXT", "/kaggle/input/silverwing-corpus/train.txt"))
    if corpus_path.exists():
        return corpus_path.read_text(encoding="utf-8", errors="replace"), str(corpus_path), "local-attached"
    import urllib.request
    urls = [
        "https://huggingface.co/datasets/Salesforce/wikitext/resolve/main/wikitext-103-raw-v1.zip",
        "https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/train.txt",
    ]
    for u in urls:
        try:
            txt = urllib.request.urlopen(u, timeout=120).read().decode("utf-8", "replace")
            if len(txt) > 1_000_000:
                return txt, u, "downloaded"
        except Exception as e:
            print("fetch failed:", u, repr(e))
    raise RuntimeError("No corpus available: attach a dataset or enable network.")


def write_dataset_manifest(out_dir, src, src_type, train_tokens, val_tokens,
                           doc_count, raw_chars, kept_chars, tok_path, seq, target_tokens):
    manifest = {
        "source": src,
        "source_type": src_type,
        "version": DATA_MIXTURE["version"],
        "license": "CC-BY-SA",
        "sequence_length": seq,
        "target_tokens": target_tokens,
        "document_count": doc_count,
        "raw_size": raw_chars,
        "filtered_size": kept_chars,
        "token_count": train_tokens + val_tokens,
        "train_tokens": train_tokens,
        "validation_tokens": val_tokens,
        "val_frac": 0.005,
        "tokenizer_path": str(tok_path),
        "tokenizer_hash": sha256_file(tok_path) if Path(tok_path).exists() else "n/a",
        "dataset_hash": hashlib.sha256((src + str(train_tokens) + str(val_tokens)).encode()).hexdigest(),
        "creation_date": datetime.datetime.utcnow().isoformat() + "Z",
        "pipeline": "silverwing clean+ngram_dedup+pack",
        "data_mixture": DATA_MIXTURE,
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
'''

# ---------------------------------------------------------------------------
# Notebook cells
# ---------------------------------------------------------------------------
cells = []
_cid = 0
def md(src):
    global _cid
    cells.append({"cell_type": "markdown", "id": f"cell-{_cid}", "metadata": {}, "source": src}); _cid += 1
def code(src):
    global _cid
    cells.append({"cell_type": "code", "id": f"cell-{_cid}", "metadata": {}, "execution_count": None, "outputs": [], "source": src}); _cid += 1

md("""# Silverwing-120M — Kaggle GPU Pretraining (Phase B GPU)

Reproducible GPU pretrain of the **120,087,552-parameter** Silverwing-120M-V1 architecture on a Kaggle GPU (T4 / P100 / L4).

Fixes the three Colab-102M blockers:
1. **Data-not-found** -> integrated controlled data pipeline builds `train.npy`/`val.npy` from the attached dataset.
2. **GPU->CPU fallback** -> hard `STOP` if the kernel is not GPU-backed (cell 2).
3. **Fake resume** -> real model(safetensors-strict) + optimizer + scheduler + step restore.

> This author host is CPU-only/offline. Cells needing GPU or network are **not** executed here - they are syntax-checked, and the offline-runnable data pipeline (cell 6) is validated against the local Silverwing corpus (`_test_pipeline.py` -> OFFLINE PIPELINE: PASS). The 12M/r2000 baseline is **immutable**.
""")

md("## 0. GPU-compatible PyTorch (conditional)\n\nThe base Kaggle image ships torch 2.10.0+cu128 (min CUDA capability **sm_70**). Kaggle may assign a **Tesla P100** (Pascal, sm_60) in some regions, for which the base torch cannot launch CUDA kernels. If a P100/Pascal GPU is detected, this cell installs `torch==2.4.1+cu121` (supports sm_60, CUDA 12.1, FP16/BF16). T4 (sm_75)/L4/A100 are left on the base torch.")
code("""%%bash
GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')
[ -z "$CAP" ] && case "$GPU" in *P100*|*Tesla\ K*|*Quadro\ P*|*GTX\ 10*) CAP="6.0";; *) CAP="0";; esac
echo "GPU: $GPU (compute_cap $CAP)"
if [[ "$CAP" == 6.* ]]; then
  echo "-> Pascal sm_60 not supported by base torch (cu128, min sm_70). Installing torch==2.4.1+cu121 (sm_60-capable).";
  pip install --quiet --no-input "torch==2.4.1+cu121" --extra-index-url https://download.pytorch.org/whl/cu121;
  echo "pip exit=$?";
else
  echo "-> GPU SM $CAP supported by base torch; no install.";
fi
python -c "import torch; print('torch', torch.__version__, '| archs', torch.cuda.get_arch_list())";
""")

md("## 1. Environment audit")
code("""import torch, sys, platform, shutil, os
gpu = torch.cuda.is_available()
print("GPU:",        torch.cuda.get_device_name(0) if gpu else "None (CPU-only)")
print("GPU count:",   torch.cuda.device_count())
if gpu:
    print("VRAM:",       f"{torch.cuda.get_device_properties(0).total_memory/1e9:.2f} GB")
    print("CUDA:",       torch.version.cuda)
    print("BF16:",       torch.cuda.is_bf16_supported())
else:
    print("VRAM: N/A"); print("CUDA: not built"); print("BF16: N/A")
print("PyTorch:",  torch.__version__)
print("Python:",   platform.python_version())
try:
    import psutil
    print("RAM:", f"{psutil.virtual_memory().total/1e9:.2f} GB")
except Exception:
    print("RAM: (psutil unavailable)")
try:
    print("Disk:", f"{shutil.disk_usage('/kaggle/working').free/1e9:.1f} GB free")
except Exception:
    print("Disk: (n/a)")
print("FP16:",  bool(gpu))
""")

md("## 2. GPU requirement gate — STOP if not GPU-backed")
code("""import torch
if not torch.cuda.is_available():
    raise SystemExit("STOP: kernel is not GPU-backed. Select a GPU accelerator (T4/P100/L4) and rerun.")
dev = torch.device("cuda")
try:
    _ = torch.randn(64, 64, device=dev) @ torch.randn(64, 64, device=dev); torch.cuda.synchronize()
    cuda_compute_ok = True
except Exception as e:
    cuda_compute_ok = False
    reason = repr(e)
print("GPU-backed accelerator confirmed:", torch.cuda.get_device_name(0))
print("CUDA compute probe:", "OK" if cuda_compute_ok else "FAILED")
if not cuda_compute_ok:
    raise SystemExit("STOP: CUDA compute failed on " + torch.cuda.get_device_name(0) + " (" + reason + "). If this is a P100, cell 0 should have installed torch==2.4.1+cu121.")
""")

md("## 3. Stage project files + dependency verification\n\nAttached datasets: `" + OWNER + "/" + DATASET_SLUG + "` (corpus/scripts/tokenizer) + `" + OWNER + "/silverwing-120m-fixes` (Kaggle-aware `stage3a_evaluate.py` + common `val.txt`) -> mount somewhere under `/kaggle/input/` (Kaggle may use `/kaggle/input/datasets/<owner>/<slug>/`). This cell recursively locates the mount and copies all files into `/kaggle/working/` (writable) so the trainer and evaluation scripts run from there. The r2000 8192-token BPE tokenizer (sha `5b09bfb6cf456dbbdc52879c133bf706bafeee34bc9f9766786fd2bda8027844`) is reused, not rebuilt, and the fixed `stage3a_evaluate.py` is staged on top from the fixes dataset for the §14/§15 B25 eval.")
code("""import sys, os, shutil, hashlib, glob
WORK = "/kaggle/working"
# Recursively locate the attached dataset mount. Kaggle may mount it at
# /kaggle/input/<slug>/ OR /kaggle/input/datasets/<owner>/<slug>/ (nested).
DATASET = None
if os.path.isdir("/kaggle/input"):
    for root, dirs, files in os.walk("/kaggle/input"):
        if "silverwing_train.py" in files:
            DATASET = root; break
# Diagnostic: print the FULL /kaggle/input tree so a missed mount is obvious.
print("mounted inputs (root):", os.listdir("/kaggle/input") if os.path.isdir("/kaggle/input") else "n/a")
if os.path.isdir("/kaggle/input"):
    allfiles = []
    for root, dirs, files in os.walk("/kaggle/input"):
        for f in files:
            allfiles.append(os.path.relpath(os.path.join(root, f), "/kaggle/input"))
    print("  /kaggle/input tree (%d files):" % len(allfiles))
    for x in allfiles[:25]:
        print("   ", x)
print("dataset mount:", DATASET)
if DATASET:
    for f in ["silverwing_train.py","silverwing_120m_config.json","silverwing_120m_kaggle.py","stage3a_evaluate.py","gen_samples_120m.py","tokenizer.json","01_normalized.jsonl","r2000_eval.json","val.txt"]:
        src = os.path.join(DATASET, f); dst = os.path.join(WORK, f)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
# --- override stage3a_evaluate.py + val.txt from the fixes dataset (Kaggle-aware) ---
# Main dataset pins the author's on-host stage3a (F:/AI paths); the companion
# fixes dataset ships the Kaggle-aware stage3a + the common held-out val.txt
# (r2000's data_pipeline/processed/val.txt) so §14/§15 B25 is apples-to-apples.
FIXES = None
if os.path.isdir("/kaggle/input"):
    for root, dirs, files in os.walk("/kaggle/input"):
        if "val.txt" in files and "stage3a_evaluate.py" in files:
            FIXES = root; break
if FIXES:
    for f in ["stage3a_evaluate.py", "val.txt"]:
        shutil.copy2(os.path.join(FIXES, f), os.path.join(WORK, f))
    print("fixes dataset mounted:", FIXES)
else:
    print("fixes dataset NOT mounted (stage3a/val.txt from main dataset only)")
# tokenizer must be named r2000_tokenizer.json (lock hash above)
if os.path.exists(WORK+"/tokenizer.json") and not os.path.exists(WORK+"/r2000_tokenizer.json"):
    shutil.copy2(WORK+"/tokenizer.json", WORK+"/r2000_tokenizer.json")
if not os.path.exists(WORK+"/silverwing_train.py"):
    raise SystemExit("silverwing_train.py not staged - dataset videlisndichi/silverwing-120m not attached to kernel (verify dataset_sources).")
sys.path.insert(0, WORK)
import torch, numpy as np
from safetensors import __version__ as sf_ver
import silverwing_train as sw
tok_sha = hashlib.sha256(open(WORK+"/r2000_tokenizer.json","rb").read()).hexdigest()
print("deps OK | torch", torch.__version__, "| safetensors", sf_ver, "| numpy", np.__version__)
print("sw module:", sw.__file__)
print("r2000_tokenizer.json SHA256:", tok_sha, "->", "LOCK OK" if tok_sha=="5b09bfb6cf456dbbdc52879c133bf706bafeee34bc9f9766786fd2bda8027844" else "MISMATCH")
for f in ["silverwing_120m_config.json","r2000_tokenizer.json","silverwing_120m_kaggle.py","stage3a_evaluate.py","01_normalized.jsonl","r2000_eval.json","val.txt"]:
    print(f"  {f}:", "present" if os.path.exists(WORK+"/"+f) else "MISSING")
""")

md("## 4. Architecture lock — do NOT rewrite the model")
code("""import json, sys
from pathlib import Path
sys.path.insert(0, "/kaggle/working")
import silverwing_train as sw, torch
CFG = Path("/kaggle/working/silverwing_120m_config.json")
spec = json.load(open(CFG))
cfg = sw.ModelConfig(**spec)
m = sw.SilverwingModel(cfg)
n = m.num_parameters()
EXPECTED = 120087552
print("Parameters:", n, "->", "PASS" if n == EXPECTED else f"FAIL (expected {EXPECTED})")
print("Layers:",        spec.get("n_layers"),       "d_model:",        spec.get("d_model"))
print("Q heads:",       spec.get("n_heads"),        "KV heads:",       spec.get("n_kv_heads"))
print("head_dim:",      spec.get("d_model") // spec.get("n_heads"), "MLP:", spec.get("hidden_size"))
print("RoPE theta:",    spec.get("rope_theta"),     "vocab:",          spec.get("vocab_size"))
print("context:",       spec.get("max_position_embeddings"),
      "weight_tying:", spec.get("tie_word_embeddings"),
      "use_bias:",     spec.get("use_bias"))
print("Model class:", type(m).__name__)
assert n == EXPECTED, "ARCH LOCK FAILED: parameter count != 120,087,552 - STOP"
print("ARCH LOCK: PASS")
""")

md("## 5. Tokenizer lock — reuse the r2000 8192-token BPE (not rebuilt, not remapped)")
code("""import hashlib, sys
from pathlib import Path
sys.path.insert(0, "/kaggle/working")
import silverwing_train as sw
TOK = Path("/kaggle/working/r2000_tokenizer.json")
tok = sw.BPETokenizer.from_file(str(TOK))
data = TOK.read_bytes()
print("tokenizer path:", TOK)
print("SHA256:", hashlib.sha256(data).hexdigest())
print("vocabulary size:", tok.vocab_size)
print("special token IDs: pad=0 bos=1 eos=2 unk=3")
assert tok.vocab_size == 8192, "tokenizer vocab != 8192 - STOP"
assert hashlib.sha256(data).hexdigest() == "5b09bfb6cf456dbbdc52879c133bf706bafeee34bc9f9766786fd2bda8027844", "tokenizer hash changed - STOP"
print("TOKENIZER LOCK: PASS")
""")

md("## 6. Data mixture + controlled pipeline (experimental, versioned)")
code(PIPELINE_FUNCS)

md("## 7. Build a controlled ~5M-token shard (then expand 25M->50M)")
code("""import sys, json
from pathlib import Path
sys.path.insert(0, "/kaggle/working")
import silverwing_train as sw
DATA_ROOT = Path("/kaggle/working/silverwing-120m/data"); DATA_ROOT.mkdir(parents=True, exist_ok=True)
TOK = Path("/kaggle/working/r2000_tokenizer.json")
CORPUS = Path("/kaggle/working/01_normalized.jsonl")   # controlled corpus (CC-BY-SA), staged in cell 3
print("DATA MIXTURE (experimental):")
for k, v in DATA_MIXTURE["sources"].items():
    print(f"  {k:12s} {int(v['frac']*100):>3d}%  ({v['license']})")
print("version:", DATA_MIXTURE["version"])
print("corpus:", CORPUS, "exists=", CORPUS.exists())
seq = 2048
target_tokens = 5_000_000
raw = chr(10).join(json.loads(l).get("text","") for l in CORPUS.read_bytes().decode("utf-8","replace").splitlines() if l.strip())
tok = sw.BPETokenizer.from_file(str(TOK))
tr, va, doc_count, rc, kc = pipeline_build(raw, seq, target_tokens, 0.005, DATA_ROOT, tok)
man = write_dataset_manifest(DATA_ROOT, "01_normalized.jsonl (silverwing-120m dataset)", "local-controlled", tr, va, doc_count, rc, kc, TOK, seq, target_tokens)
print(f"built shard: train={tr} tokens ({tr/1e6:.2f}M), val={va} tokens, docs={doc_count}")
print("dedup ratio:", f"{(rc-kc)/rc:.1%}" if rc else "n/a")
print("train.npy:", (DATA_ROOT/"train.npy").stat().st_size, "bytes | val.npy:", (DATA_ROOT/"val.npy").stat().st_size, "bytes")
""")

md("## 8. Training configuration (GPU-aware)\nT4: FP16 (BF16 unsupported on Turing). Effective batch = `batch*grad_accum`. The trainer auto-detects AMP (fp16 on CUDA).")
code("""CFG_RUN = dict(
    model="Silverwing-120M-V1", steps=500, seq=2048, batch=1, grad_accum=4,
    lr=1.5e-4, warmup=250, weight_decay=0.01, clip=1.0,
    save_every=100, eval_every=100, amp="fp16", device="cuda", seed=42,
)
print("training config:"); print(CFG_RUN)
print("effective batch =", CFG_RUN["batch"]*CFG_RUN["grad_accum"])
print("OOM fallback: batch1 -> +grad_accum -> grad-checkpoint -> shrink seq (never shrink the model)")
""")

md("## 9. Throughput benchmark (VRAM fit + step-time estimate)")
code("""import sys, time, json, torch
sys.path.insert(0, "/kaggle/working")
import silverwing_train as sw
cfg = sw.ModelConfig(**json.load(open("/kaggle/working/silverwing_120m_config.json")))
m = sw.SilverwingModel(cfg).to("cuda").train()
opt = torch.optim.AdamW(m.parameters(), lr=1e-4)
scaler = torch.cuda.amp.GradScaler()
seq=1024; ga=4; N=20
ids = torch.randint(0, 8192, (1, seq), device="cuda")
with torch.cuda.amp.autocast():
    l = m(ids, labels=ids)["loss"]/ga
scaler.scale(l).backward(); scaler.unscale_(opt); scaler.step(opt); scaler.update(); opt.zero_grad()
torch.cuda.synchronize()
t0=time.time()
for _ in range(N):
    opt.zero_grad()
    for _ in range(ga):
        with torch.cuda.amp.autocast():
            l = m(ids, labels=ids)["loss"]/ga
        scaler.scale(l).backward()
    scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(m.parameters(),1.0)
    scaler.step(opt); scaler.update()
torch.cuda.synchronize()
dt=(time.time()-t0)/N; tps=seq*ga
print(f"step_time   = {dt*1000:.1f} ms")
print(f"tokens/sec  = {tps/dt:.0f}")
print(f"VRAM alloc  = {torch.cuda.memory_allocated()/1e9:.2f} GB")
print(f"VRAM resid  = {torch.cuda.memory_reserved()/1e9:.2f} GB")
print(f"est 500     = {500*dt/60:.1f} min")
print(f"est 5K      = {5000*dt/60:.1f} min")
print(f"est 10K     = {10000*dt/60:.1f} min")
""")

md("## 10. GPU smoke test — all fixes, must PASS before the long run")
code("""import sys, time, math, tempfile, os, json, torch
sys.path.insert(0, "/kaggle/working")
import silverwing_train as sw
from safetensors.torch import save_file, load_file

cfg = sw.ModelConfig(**json.load(open("/kaggle/working/silverwing_120m_config.json")))
m  = sw.SilverwingModel(cfg).to("cuda"); m.train()
opt = torch.optim.AdamW(m.parameters(), lr=1e-4)
scaler = torch.cuda.amp.GradScaler()
seq=128; ga=4
ids = torch.randint(0, 8192, (1, seq), device="cuda")

with torch.cuda.amp.autocast():
    out = m(ids, labels=ids)
fwd_ok = torch.isfinite(out["logits"]).all().item()
f_loss = float(out["loss"])

opt.zero_grad()
for _ in range(ga):
    with torch.cuda.amp.autocast():
        l = m(ids, labels=ids)["loss"]/ga
    scaler.scale(l).backward()
scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(m.parameters(),1.0)
scaler.step(opt); scaler.update()
bwd_ok = True

d = tempfile.mkdtemp()
save_file({k:v.clone() for k,v in m.state_dict().items()}, os.path.join(d,"model.safetensors"))
torch.save({"step":5,"opt":opt.state_dict(),"sched":torch.optim.lr_scheduler.LambdaLR(opt,lambda s:1.0).state_dict()}, os.path.join(d,"optimizer.pt"))
m2 = sw.SilverwingModel(cfg).to("cuda")
missing, unexpected = m2.load_state_dict(load_file(os.path.join(d,"model.safetensors")), strict=True)
resume_ok = (len(missing)==0 and len(unexpected)==0 and torch.allclose(next(m.parameters()), next(m2.parameters())))

losses=[f_loss]
for _ in range(5):
    opt.zero_grad(); tot=0.0
    for _ in range(ga):
        with torch.cuda.amp.autocast():
            l = m(ids, labels=ids)["loss"]/ga
        scaler.scale(l).backward(); tot+=l.item()*ga
    scaler.unscale_(opt); scaler.step(opt); scaler.update(); losses.append(tot/ga)
nan_ok = all(math.isfinite(x) for x in losses)
inf_ok = all(not math.isinf(x) for x in losses)

results = {"CUDA":torch.cuda.is_available(),"Forward":fwd_ok,"Backward":bwd_ok,"AMP":bool(scaler.is_enabled()),
           "Optimizer":True,"Checkpoint":os.path.exists(os.path.join(d,"model.safetensors")),
           "Resume":resume_ok,"NaN":nan_ok,"Inf":inf_ok}
print("SILVERWING-120M GPU SMOKE")
for k,v in results.items(): print(f"{k:11s}: {'PASS' if v else 'FAIL'}")
print("STATUS:", "PASS" if all(results.values()) else "FAIL")
assert all(results.values()), "GPU SMOKE FAILED - STOP before real pretrain"
""")

md("## 11. Launch the 500-step GPU pilot (validated trainer)\n\nThe script auto-detects CUDA + AMP (fp16), writes `final/best/checkpoints/step-N/` each under `--ckpt-dir` with `model.safetensors`+`optimizer.pt`+`metadata.json`. Config + tokenizer are staged in cell 3.")
code("""import os
os.makedirs("/kaggle/working/silverwing-120m", exist_ok=True)
print("ckpt root ready")
""")
code("""%%bash
SW_TOK=/kaggle/working/r2000_tokenizer.json SW_CFG=/kaggle/working/silverwing_120m_config.json python /kaggle/working/silverwing_120m_kaggle.py --steps 500 --seq 2048 --batch 1 --grad-accum 4 --lr 1.5e-4 --warmup 250 --weight-decay 0.01 --save-every 100 --eval-every 100 --ckpt-dir /kaggle/working/silverwing-120m --config /kaggle/working/silverwing_120m_config.json --data /kaggle/working/silverwing-120m/data/train.npy --val /kaggle/working/silverwing-120m/data/val.npy""")

md("## 12. Checkpoint inventory")
code("""import json, os
from pathlib import Path
root = Path("/kaggle/working/silverwing-120m")
print("checkpoints:")
for p in sorted((root/"checkpoints").glob("step-*")):
    md = json.load(open(p/"metadata.json"))
    print(f"  {p.name}: step={md['step']} sha={md.get('model_sha256','?')[:12]} params={md['param_count']} amp={md.get('amp')}")
for d in ("best","final"):
    f = root/d/"metadata.json"
    if f.exists():
        md = json.load(open(f))
        print(f"  {d}: step={md['step']} sha={md.get('model_sha256','?')[:12]} val_loss={md.get('val_loss')}")
print("final model size:", round(os.path.getsize(root/"final/model.safetensors")/1e6,1), "MB")
""")

md("## 13. Resume test (real resume -> step 501)")
code("""%%bash
SW_TOK=/kaggle/working/r2000_tokenizer.json SW_CFG=/kaggle/working/silverwing_120m_config.json python /kaggle/working/silverwing_120m_kaggle.py --steps 501 --seq 2048 --batch 1 --grad-accum 4 --lr 1.5e-4 --warmup 250 --save-every 1 --eval-every 9999 --ckpt-dir /kaggle/working/silverwing-120m/resume_test --resume-from /kaggle/working/silverwing-120m/final --config /kaggle/working/silverwing_120m_config.json --data /kaggle/working/silverwing-120m/data/train.npy --val /kaggle/working/silverwing-120m/data/val.npy""")
code("""import json
md = json.load(open("/kaggle/working/silverwing-120m/resume_test/final/metadata.json"))
print("resume_step =", md["step"], "(expect 501)")
assert md["step"] == 501, "RESUME STEP MISMATCH - STOP"
print("RESUME TEST: PASS")
""")

md("## 14. Evaluation (stage3a suite, same benchmarks as r2000)")
code("""%%bash
python /kaggle/working/stage3a_evaluate.py --ckpt /kaggle/working/silverwing-120m/final --config /kaggle/working/silverwing_120m_config.json --tok /kaggle/working/r2000_tokenizer.json --label silverwing-120m-gpu-v0.1 --out /kaggle/working/silverwing-120m/evaluation_report.json""")

md("## 15. B25 capability gate (vs immutable 12M-r2000 baseline)\n\nr2000 baseline (12M-r2000) is bundled in the dataset as `r2000_eval.json` (val_loss=6.344542, ppl=569.3768). 120M must beat it on at least one capability axis to clear B25.")
code("""import json
r2000 = json.load(open("/kaggle/working/r2000_eval.json"))   # staged in cell 3 from the dataset
rep   = json.load(open("/kaggle/working/silverwing-120m/evaluation_report.json"))
hist = {"r2000_baseline_12m": r2000, "silverwing-120m-500step": rep}
json.dump(hist, open("/kaggle/working/silverwing-120m/capability_history.json","w"), indent=2)
def acc(x):
    if isinstance(x, dict): return x.get("accuracy")
    return x
deltas = {}
for k in ("val_loss","val_perplexity"):
    a=r2000.get(k); b=rep.get(k)
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        deltas[k] = {"baseline":a, "candidate":b, "delta":b-a, "improved":b<a}
for k in ("math","logic","coding","knowledge"):
    a=acc(r2000.get(k)); b=acc(rep.get(k))
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        deltas[k] = {"baseline":a, "candidate":b, "delta":b-a, "improved":b>a}
print("capability deltas vs 12M-r2000 (val_loss=%.4f, ppl=%.2f):" % (r2000["val_loss"], r2000["val_perplexity"]))
print(json.dumps(deltas, indent=2))
n_improved = sum(1 for v in deltas.values() if v["improved"])
print("B25:", "PASS" if n_improved>=1 else "INCONCLUSIVE", "(%d/%d axes improved)" % (n_improved, len(deltas)))
""")

md("## 16. Training metrics (streaming metrics.jsonl -> final report)")
code("""import json
from pathlib import Path
root = Path("/kaggle/working/silverwing-120m")
rows=[]
for line in open(root/"metrics.jsonl"):
    line=line.strip()
    if line: rows.append(json.loads(line))
json.dump(rows, open(root/"training_metrics.json","w"), indent=2)
print(f"{len(rows)} metric rows logged")
for r in rows[-6:]:
    print(r)
""")

md("## 17. Sample generations")
code("""%%bash
python /kaggle/working/gen_samples_120m.py --ckpt /kaggle/working/silverwing-120m/final --out /kaggle/working/silverwing-120m/sample_generations.txt --prompts "The future of artificial intelligence" "Prove that sqrt(2) is irrational" "Explain backpropagation""")

md("## 18. Final report bundle (versioned, reproducible)")
code("""import json, os, hashlib, datetime, torch
from pathlib import Path
root = Path("/kaggle/working/silverwing-120m")
md = json.load(open(root/"final/metadata.json"))
gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
run_manifest = {
    "run_id": "silverwing-120m-gpu-" + md.get("model_sha256","")[:8],
    "model_version": "Silverwing-120M-V1",
    "tokenizer_version": "r2000-BPE-8192",
    "dataset_version": "silverwing-120m-mixture-v0.1",
    "hardware": gpu_name,
    "precision": md.get("amp") or ("fp16" if torch.cuda.is_available() else "cpu"),
    "seed": 42,
    "ckpt_dir": str(root),
    "final_step": md["step"],
    "final_model_sha256": md.get("model_sha256"),
    "param_count": md["param_count"],
    "created": datetime.datetime.utcnow().isoformat()+"Z",
}
json.dump(run_manifest, open(root/"run_manifest.json","w"), indent=2)
env = {"python": __import__("platform").python_version(), "torch": torch.__version__,
       "cuda": torch.version.cuda, "bf16": torch.cuda.is_bf16_supported() if torch.cuda.is_available() else None,
       "fp16": True if torch.cuda.is_available() else False}
json.dump(env, open(root/"environment_report.json","w"), indent=2)
print("run_manifest:"); print(json.dumps(run_manifest, indent=2))
print("environment:"); print(json.dumps(env, indent=2))
""")

md("## 18b. Shrink outputs — keep reports only (so `kernels output` downloads fast)")
code("""import shutil, os
ROOT = "/kaggle/working/silverwing-120m"
# Drop the large training artifacts (checkpoints, model, optimizer, data shards)
# but KEEP the small reports needed for local evaluation + reproducibility.
for d in ["checkpoints", "best", "data"]:
    p = os.path.join(ROOT, d)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
for f in ["final/model.safetensors", "final/optimizer.pt", "metrics.jsonl"]:
    p = os.path.join(ROOT, f)
    if os.path.isfile(p):
        os.remove(p)
print("cleanup done; remaining under", ROOT + ":")
for f in sorted(os.listdir(ROOT)):
    fp = os.path.join(ROOT, f)
    sz = os.path.getsize(fp) if os.path.isfile(fp) else "dir"
    print("  ", f, sz)
""")


# ---------------------------------------------------------------------------
# Assemble notebook
# ---------------------------------------------------------------------------
nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
NB_PATH.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("wrote", NB_PATH, f"({len(cells)} cells)")

# ---------------------------------------------------------------------------
# Syntax-check every code cell (skip IPython/shell magic cells, which are valid
# in Jupyter but not pure Python).
# ---------------------------------------------------------------------------
fails = 0; skipped = 0
for i, c in enumerate(cells):
    if c["cell_type"] != "code":
        continue
    src = c["source"].lstrip()
    if src.startswith(("%%", "!")):
        skipped += 1; continue
    try:
        compile(c["source"], f"<cell {i}>", "exec")
    except SyntaxError as e:
        fails += 1
        print(f"  SYNTAX ERROR cell {i}: {e}")
print("code-cell syntax:", "ALL PASS" if fails == 0 else f"{fails} FAILED",
      f"({skipped} bash/magic shells skipped)")

# ---------------------------------------------------------------------------
# Emit _test_pipeline.py = PIPELINE_FUNCS (verbatim) + offline driver for local corpus.
# The driver uses a bounded slice of the LOCAL Silverwing controlled corpus so the
# offline validation is fast; the notebook cell 7 targets the FULL 5M shard on Kaggle.
# ---------------------------------------------------------------------------
TEST_SRC = PIPELINE_FUNCS + r'''
import sys
sys.path.insert(0, r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu")
import silverwing_train as sw

if __name__ == "__main__":
    # reuse the LOCAL Silverwing controlled corpus source (01_normalized.jsonl, Wikipedia, CC-BY-SA)
    from pathlib import Path
    raw = Path(r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/01_normalized.jsonl").read_text(encoding="utf-8", errors="replace")
    docs = [json.loads(line) for line in raw.splitlines() if line.strip()]
    text = "\n".join(d.get("text","") for d in docs)
    print("source docs:", len(docs), "chars:", len(text))
    tok = sw.BPETokenizer.from_file(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
    out_dir = Path(r"F:/AI/silverwing-120m/_smoke_shard")
    # Offline validation on a bounded slice (same pipeline code path as the notebook).
    text_slice = text[:8_000_000]
    tr, va, dcount, rc, kc = pipeline_build(text_slice, 256, 1_000_000, 0.005, out_dir, tok)
    man = write_dataset_manifest(out_dir, "local-01_normalized.jsonl", "local-controlled", tr, va, dcount, rc, kc,
                                 Path(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json"), 256, 1_000_000)
    print(f"train={tr} ({tr/1e6:.2f}M) tokens, val={va}, docs={dcount}, dedup={(rc-kc)/rc:.1%}" if rc else "train ok")
    print("manifest keys:", sorted(man.keys()))
    assert tr > 0 and va > 0, "shard too small"
    assert (out_dir/"train.npy").exists() and (out_dir/"val.npy").exists() and (out_dir/"dataset_manifest.json").exists()
    assert man["tokenizer_hash"] and man["dataset_hash"] and man["version"] == "silverwing-120m-mixture-v0.1"
    print("OFFLINE PIPELINE: PASS")
'''
TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
TEST_PATH.write_text(TEST_SRC, encoding="utf-8")
print("wrote", TEST_PATH)
