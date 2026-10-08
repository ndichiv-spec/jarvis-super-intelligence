"""Stage 3A --- RULE 1 (freeze baseline) + RULE 2 (verify before training).

All values (hashes, token counts, params, losses) are computed from real files.
Nothing is fabricated. If any verification check fails, the script exits nonzero
so Stage 3 training is never started from an invalid checkpoint.
"""
from __future__ import annotations
import sys, os, json, shutil, hashlib, datetime, stat
from pathlib import Path

PY = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
BASELINE_SRC_FINAL = Path(r"F:/AI/silverwing-r2000/final")
BASELINE_SRC_TOK   = Path(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
BASELINE_SRC_SUMMARY = Path(r"F:/AI/silverwing-r2000/training_summary.json")
# The corpus the r2000 baseline was trained on (4 public-domain books)
BASELINE_BOOKS_DIR = Path(r"F:/AI/silverwing/data")

BASELINE_DST = Path(r"F:/AI/baselines/silverwing-12m-v1-r2000")

EXPECTED_PARAMS = 12_440_448
EXPECTED_VOCAB = 8192

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def make_readonly(p: Path):
    # Windows read-only flag via os.chmod
    os.chmod(p, stat.S_IREAD)

# ----------------------------------------------------------------------------
print("=" * 70)
print("STAGE 3A - RULE 1: FREEZE BASELINE")
print("=" * 70)
BASELINE_DST.mkdir(parents=True, exist_ok=True)

# 1. Copy model artifacts (NOT the optimizer — it is training state, not a model)
files_to_copy = {
    "config.json":         BASELINE_SRC_FINAL / "config.json",
    "metadata.json":       BASELINE_SRC_FINAL / "metadata.json",
    "model.safetensors":   BASELINE_SRC_FINAL / "model.safetensors",
    "tokenizer_manifest.json": BASELINE_SRC_FINAL / "tokenizer_manifest.json",
}
(BASELINE_DST / "tokenizer").mkdir(parents=True, exist_ok=True)
files_to_copy["tokenizer/tokenizer.json"] = BASELINE_SRC_TOK

for dest, src in files_to_copy.items():
    dst = BASELINE_DST / dest
    shutil.copy2(src, dst)
    print(f"  copied {src.name} -> {dst}")

# 2. Compute hashes + manifest
file_entries = {}
for dest, _ in files_to_copy.items():
    p = BASELINE_DST / dest
    file_entries[dest] = {
        "path": dest,
        "bytes": p.stat().st_size,
        "sha256": sha256(p),
    }

ckpt_meta = json.load(open(BASELINE_DST / "metadata.json"))
train_summary = json.load(open(BASELINE_SRC_SUMMARY))

# 3. Baseline dataset manifest (the 4 books r2000 trained on)
books = ["alice.txt", "frankenstein.txt", "pride_prejudice.txt", "sherlock.txt"]
book_entries = []
total_chars = 0
for b in books:
    p = BASELINE_BOOKS_DIR / b
    if p.exists():
        txt = p.read_text(encoding="utf-8", errors="replace")
        book_entries.append({"file": b, "chars": len(txt)})
        total_chars += len(txt)

manifest = {
    "baseline_name": "silverwing-12m-v1-r2000",
    "created_utc": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    "source_checkpoint": str(BASELINE_SRC_FINAL),
    "architecture": "Silverwing-12M",
    "architecture_detail": "6 layers / d_model 384 / 8 Q heads / 2 KV heads / GQA / RoPE(theta=10000) / RMSNorm / SwiGLU / tied embeddings",
    "params": EXPECTED_PARAMS,
    "files": file_entries,
    "checkpoint_metadata": ckpt_meta,
    "training_summary": train_summary,
    "dataset_manifest": {
        "name": "silverwing-baseline-corpus-v1",
        "sources": [
            {"name": "Project Gutenberg", "license": "Public Domain (US)",
             "books": book_entries, "total_chars": total_chars}
        ],
        "total_characters": total_chars,
        "note": "r2000 baseline was trained exclusively on these 4 public-domain books; training_tokens in summary counts packed/repeated tokens consumed, not unique corpus tokens.",
    },
    "read_only": True,
    "integrity": "DO NOT MODIFY — baseline preserved for Stage 3A comparison.",
}
mf = BASELINE_DST / "manifest.json"
json.dump(manifest, open(mf, "w"), indent=2)
print(f"  wrote {mf}")

# 4. Baseline dataset_manifest.json (standalone, top-level friendly)
dsm = manifest["dataset_manifest"]
json.dump(dsm, open(BASELINE_DST / "dataset_manifest.json", "w"), indent=2)
print(f"  wrote {BASELINE_DST / 'dataset_manifest.json'}")

# 5. Mark everything read-only
for root, dirs, files in os.walk(BASELINE_DST):
    for fn in files:
        make_readonly(Path(root) / fn)
print("  baseline files marked read-only")
print("BASELINE FREEZE COMPLETE.\n")

# ----------------------------------------------------------------------------
print("=" * 70)
print("STAGE 3A - RULE 2: VERIFY CHECKPOINT BEFORE TRAINING")
print("=" * 70)
import importlib
TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw  # noqa: E402

import torch  # noqa: E402

results = {}
def check(name, cond, detail=""):
    results[name] = bool(cond)
    flag = "PASS" if cond else "FAIL"
    print(f"  [{flag}] {name}  {detail}")

# Load config
cfg = sw.ModelConfig(**json.load(open(BASELINE_DST / "config.json")))
check("config_loads", cfg is not None, f"vocab={cfg.vocab_size} layers={cfg.n_layers}")
check("config_matches_12m",
      cfg.n_layers == 6 and cfg.d_model == 384 and cfg.n_heads == 8
      and cfg.n_kv_heads == 2 and cfg.vocab_size == 8192
      and cfg.tie_word_embeddings is True, str(cfg))

# Build model + load weights
model = sw.SilverwingModel(cfg)
from safetensors.torch import load_file
state = load_file(str(BASELINE_DST / "model.safetensors"))
missing, unexpected = model.load_state_dict(state, strict=False)
check("weights_load", len(unexpected) == 0,
      f"unexpected={len(unexpected)} keys; missing={len(missing)}")

# Parameter count
n = model.num_parameters()
est = sw.estimate_parameters(cfg)
check("param_count", n == EXPECTED_PARAMS and est == EXPECTED_PARAMS,
      f"actual={n:,} est={est:,} expected={EXPECTED_PARAMS:,}")

# Forward + output shape + finite loss
ids = torch.tensor([[cfg.bos_token_id, 10, 20, 30, cfg.eos_token_id]], dtype=torch.long)
model.eval()
with torch.no_grad():
    out = model(ids, labels=ids)
logits = out["logits"]
check("output_shape", tuple(logits.shape) == (1, ids.shape[1], cfg.vocab_size),
      f"logits={tuple(logits.shape)} expected (1,5,{cfg.vocab_size})")
check("loss_finite", out["loss"] is not None and torch.isfinite(out["loss"]).item(),
      f"loss={out['loss'].item():.4f}")

# No NaN / Inf in weights
has_nan = any(torch.isnan(p).any().item() for p in model.parameters())
has_inf = any(torch.isinf(p).any().item() for p in model.parameters())
check("no_nan_weights", not has_nan, "")
check("no_inf_weights", not has_inf, "")

# Tokenizer loads + roundtrip
tok = sw.BPETokenizer.from_file(str(BASELINE_DST / "tokenizer" / "tokenizer.json"))
check("tokenizer_loads", tok is not None and tok.vocab_size == EXPECTED_VOCAB,
      f"vocab_size={tok.vocab_size}")
enc = tok.encode("Hello world")
dec = tok.decode(enc)
check("tokenizer_roundtrip", dec.strip().lower() == "hello world", repr(dec))

# Validation evaluation works
val_file = BASELINE_BOOKS_DIR / "splits" / "val.txt"
val_text = val_file.read_text(encoding="utf-8", errors="replace")
val_ids = tok.encode(val_text)
vl, vp = sw.evaluate_model(model, val_ids, cfg, torch.device("cpu"), 256)
check("val_eval_works", vl is not None and vl == vl and vp == vp and vp > 0,
      f"val_loss={vl:.4f} ppl={vp:.2f} (n_val_tokens={len(val_ids)})")

# Generation works on the 10 fixed prompts
PROMPTS = [
    "The story began", "Science is", "Mathematics is", "Explain gravity.",
    "What is a centrifugal pump?", "What is 17 × 24?",
    "Explain Newton's second law.",
    "Write a Python function that adds two numbers.",
    "Why is preventive maintenance important?", "Explain photosynthesis.",
]
gen_results = {}
model.eval()
ok = 0
for p in PROMPTS:
    try:
        ids = torch.tensor([tok.encode(p)], dtype=torch.long)
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=40, temperature=0.8)
        text = tok.decode(g[0].cpu().tolist())
        gen_results[p] = text
        if len(text) > len(p):
            ok += 1
    except Exception as e:
        gen_results[p] = f"[ERROR {e}]"
check("generation_works", ok == len(PROMPTS),
      f"{ok}/{len(PROMPTS)} prompts produced output")

# Save generation samples + verify report
sample_dir = BASELINE_DST / "verification"
sample_dir.mkdir(exist_ok=True)
with open(sample_dir / "sample_generations.txt", "w", encoding="utf-8") as f:
    for p, t in gen_results.items():
        f.write(f"PROMPT: {p}\nGENERATION: {t}\n{'-'*60}\n")
json.dump({"all_passed": all(results.values()), "checks": results,
           "val_loss": vl, "val_ppl": vp, "param_count": n,
           "model_sha256": sha256(BASELINE_DST / "model.safetensors")},
          open(sample_dir / "verify_results.json", "w"), indent=2)

print("\n" + "=" * 70)
if all(results.values()):
    print("RULE 2 VERIFICATION: ALL CHECKS PASSED — checkpoint is valid, training may proceed.")
    print("=" * 70)
    sys.exit(0)
else:
    print("RULE 2 VERIFICATION: FAILED — see above. STOP (do not train).")
    print("=" * 70)
    sys.exit(1)
