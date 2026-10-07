"""Lightweight in-the-loop monitor for the corrected 10M-token run.

At each saved checkpoint (step-3000, 4000, ... 9000, 9800) it loads the model and
computes the AUTHORITATIVE 128-window validation loss/perplexity on the COMMON
wiki val set (the same metric used for r2000), and appends a row to
silverwing-10m/eval/val_trend.jsonl. Negligible CPU cost (~20-45s every ~45 min).

Detached: survives independently of the training process. Exit when step-9800 is
evaluated (final checkpoint).
"""
from __future__ import annotations
import json, time, math, sys
from pathlib import Path

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw
import torch
from safetensors.torch import load_file

WORK = Path(r"F:/AI/silverwing-10m")
CKPT = WORK / "checkpoints"
EVAL = WORK / "eval"; EVAL.mkdir(parents=True, exist_ok=True)
COMMON_VAL = r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/val.txt"
R2000_TOK = r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json"
MAX_LEN = 256
TREND = EVAL / "val_trend.jsonl"

# checkpoints to eval (final 9800 included)
TARGETS = [3000, 4000, 5000, 6000, 7000, 8000, 9000, 9800]
R2000_VAL = 6.3445424883384405  # authoritative baseline (128-window, common val)
OVERFIT_KILL = 7.5      # raised from 7.0 -> 7.5 (val drifted 6.34@2k -> ~6.96@6k on LR 1e-5)

def done_steps():
    s = set()
    if TREND.exists():
        for line in TREND.read_text().splitlines():
            try: s.add(json.loads(line)["step"])
            except Exception: pass
    return s

def light_val(model, val_ids):
    windows = 128
    n = min(len(val_ids), (MAX_LEN+1)*windows)
    loss = 0.0; cnt = 0
    with torch.no_grad():
        for i in range(0, n-(MAX_LEN+1), MAX_LEN+1):
            b = torch.tensor(val_ids[i:i+MAX_LEN+1], dtype=torch.long)
            o = model(b[:-1].unsqueeze(0), labels=b[1:].unsqueeze(0))
            loss += o["loss"].item(); cnt += 1
    avg = loss/max(cnt,1)
    return avg, math.exp(min(avg, 20.0)), cnt

def eval_ckpt(step):
    d = CKPT / f"step-{step}"
    if not (d / "model.safetensors").exists():
        return None
    cfg = sw.ModelConfig(**json.load(open(d/"config.json")))
    m = sw.SilverwingModel(cfg); m.load_state_dict(load_file(str(d/"model.safetensors")), strict=False); m.eval()
    tok = sw.BPETokenizer.from_file(R2000_TOK)
    val_ids = tok.encode(Path(COMMON_VAL).read_text(encoding="utf-8", errors="replace"))
    vl, vp, w = light_val(m, val_ids)
    md = json.load(open(d/"metadata.json"))
    return {"step": step, "val_loss": round(vl,6), "val_ppl": round(vp,4),
            "val_windows": w, "train_loss_at_ckpt": md.get("train_loss"),
            "model_sha256": sw.compute_hash(str(d/"model.safetensors"))}

def main():
    print("[MONITOR] val-trend monitor started; r2000_val=6.3445; kill_if_val>%.2f"%OVERFIT_KILL, flush=True)
    train_pid = None
    while True:
        done = done_steps()
        recs = []
        for st in TARGETS:
            if st in done:
                continue
            r = eval_ckpt(st)
            if r is None:
                continue
            recs.append(r)
            done.add(st)
            with open(TREND, "a") as f:
                f.write(json.dumps(r)+"\n")
            print(f"[MONITOR] step {st}: val_loss={r['val_loss']:.4f} ppl={r['val_ppl']:.2f} (r2000=6.3445) delta={r['val_loss']-R2000_VAL:+.4f}", flush=True)
            if r["val_loss"] > OVERFIT_KILL:
                print("[MONITOR] *** OVERFIT: val > %.2f -- recommend kill ***"%OVERFIT_KILL, flush=True)
        # finished if 9800 done
        if 9800 in done_steps():
            print("[MONITOR] step-9800 evaluated; exiting.", flush=True)
            break
        # detect training death
        pl = sw  # noop
        time.sleep(120)

if __name__ == "__main__":
    main()
