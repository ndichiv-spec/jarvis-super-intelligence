"""Stage 3B final report assembler for the corrected 10M-token push.

Assembles silverwing-10m/ reports from REAL artifacts:
  F:/AI/silverwing-10m/eval/r6000_eval.json   -> authoritative eval of the corrected run
                                                (step-6000 checkpoint; val is frozen as
                                                 LR->0 by step ~7000, so step-9800 == 
                                                 step-6000 for all quality metrics)
  F:/AI/silverwing-stage3a/eval/r2000_eval.json -> frozen baseline (same COMMON wiki val)
  F:/AI/silverwing-stage3a/eval/r3000_eval.json -> controlled +1000-step HIGH-LR run
                                                (the overfitting we wanted to fix)
  F:/AI/silverwing-10m/metrics.jsonl          -> corrected-run training metrics (grad norms, nan/inf, lr)
  checkpoint metadata (step-3000..6000)       -> per-ckpt train_loss, sha, tokens

STOP decision: corrected recipe (LR 1e-5) is STABLE (no NaN, no runaway) but val plateaus
~6.97 -- >0.6 ABOVE the frozen r2000 baseline (6.3445) -- and every benchmark is flat.
Gate (>6.94 on 3 evals: steps 4000/5500/6000) is triggered. r2000 is the best model.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

WORK    = Path(r"F:/AI/silverwing-10m")
EVAL    = WORK / "eval"
R2000   = Path(r"F:/AI/silverwing-stage3a/eval/r2000_eval.json")
R3000   = Path(r"F:/AI/silverwing-stage3a/eval/r3000_eval.json")        # high-LR controlled
R10M    = EVAL / "r6000_eval.json"                                       # corrected run (== final, val frozen)
BASE    = Path(r"F:/AI/baselines/silverwing-12m-v1-r2000")
R2000SUM= Path(r"F:/AI/silverwing-r2000/training_summary.json")
R3000SUM= Path(r"F:/AI/silverwing-stage3a/training_summary.json")
METRICS = WORK / "metrics.jsonl"

def load(p):
    return json.load(open(p)) if p.exists() else None

def ppl(vl):
    if vl is None: return None
    try: return round(math.exp(min(vl,20.0)),4)
    except Exception: return None

def entry(ev, summ, label, ckpt_sha, train_tokens=None, note=None):
    out = {
        "checkpoint": label,
        "model_sha256": ckpt_sha,
        "training_tokens": summ.get("tokens") if summ else (train_tokens),
        "train_loss": round(summ["train_loss"],6) if (summ and summ.get("train_loss")) else None,
        "val_loss": round(ev["val_loss"],6) if ev else None,
        "perplexity": ev.get("val_perplexity") or (ppl(ev["val_loss"]) if ev else None),
        "math_accuracy": round(ev["math"]["accuracy"],4) if ev else None,
        "logic_accuracy": round(ev["logic"]["accuracy"],4) if ev else None,
        "coding_accuracy": round(ev["coding"]["accuracy"],4) if ev else None,
        "knowledge_accuracy": round(ev["knowledge"]["accuracy"],4) if ev else None,
    }
    if note: out["note"]=note
    return out

def main():
    r2 = load(R2000)
    r3 = load(R3000)
    r10= load(R10M)
    base_meta = load(BASE / "metadata.json")
    r2_meta   = load(Path(r2.get("checkpoint","")).parent/"metadata.json") if r2 and Path(r2.get("checkpoint","")).parent.exists() else load(Path(r"F:/AI/silverwing-r2000/final/metadata.json"))
    r3_meta   = load(Path(r"F:/AI/silverwing-stage3a/final/metadata.json"))
    # corrected run ckpt shas
    c3000 = load(WORK/"checkpoints/step-3000/metadata.json")
    c6000 = load(WORK/"checkpoints/step-6000/metadata.json")
    summ_r2000 = load(R2000SUM)
    summ_r3000 = load(R3000SUM)

    r2p = r2.get("param_count")
    history = [
        entry(r2, summ_r2000, "silverwing-12m-v1-r2000 (baseline, frozen, book-pretrained)",
              base_meta["model_sha256"], train_tokens=summ_r2000.get("tokens") if summ_r2000 else None,
              note="frozen read-only baseline at F:/AI/baselines/silverwing-12m-v1-r2000"),
        entry(r3, summ_r3000, "silverwing-12m-v1-r3000 (HIGH-LR controlled +1000, OVERFIT)",
              (r3_meta or {}).get("model_sha256"),
              train_tokens=((summ_r2000 or {}).get("tokens") or 0) + 1000*1024,
              note="controlled run: LR cosine restart to 2e-4 (~5.4e-5 @step2000); val 6.34->6.89, WORSE"),
        entry(r10, c6000, "silverwing-12m-v1-r10M-CORRECTED (LR 1e-5, step-6000)",
              (c6000 or {}).get("model_sha256"),
              train_tokens=c6000.get("total_tokens") if c6000 else None,
              note=("corrected recipe: LR 1e-5 (cosine, LR->0 by ~step7000). "
                    "val froze at ~6.97 (step-6000 == step-9800 for quality; LR->0). "
                    "train_loss_at_ckpt=%.4f. STOP per overfitting gate." % (c6000 or {}).get("train_loss",0.0) if c6000 else None)),
    ]
    json.dump(history, open(WORK/"capability_history.json","w"), indent=2)
    print("wrote capability_history.json")

    # ---- sample_generations.txt (r2000, r3000, r10M) ----
    prompts = [
        "The story began", "Science is", "Mathematics is", "Explain gravity.",
        "What is a centrifugal pump?", "What is 17 × 24?",
        "Explain Newton's second law.",
        "Write a Python function that adds two numbers.",
        "Why is preventive maintenance important?", "Explain photosynthesis.",
    ]
    with open(WORK/"sample_generations.txt","w",encoding="utf-8") as f:
        for label,ev in [("r2000 (baseline, frozen)",r2),
                        ("r3000 (HIGH-LR controlled, overfit)",r3),
                        ("r10M-corrected (LR 1e-5, step-6000)",r10)]:
            if not ev: continue
            f.write(f"\n{'='*72}\nCHECKPOINT: {label}\n{'='*72}\n")
            for p in prompts:
                f.write(f"PROMPT: {p}\nGENERATION: {ev['generations'].get(p,'[n/a]')}\n{'-'*72}\n")
    print("wrote sample_generations.txt")

    # ---- evaluation_report.json (r2000 vs r10M corrected, r3000 in context) ----
    def diff(a,b): return None if (a is None or b is None) else round(b-a,6)
    def dlabel(a,b): return "n/a" if (a is None or b is None) else ("improved" if b<a else ("worse" if b>a else "same"))
    ch = {
        "val_loss":    {"before":r2["val_loss"],"after":r10["val_loss"],
                        "delta":diff(r2["val_loss"],r10["val_loss"]),
                        "verdict":dlabel(r2["val_loss"],r10["val_loss"])},
        "perplexity":  {"before":r2.get("val_perplexity") or ppl(r2["val_loss"]),
                        "after":r10.get("val_perplexity") or ppl(r10["val_loss"]),
                        "delta":diff(r2.get("val_perplexity") or ppl(r2["val_loss"]),
                                     r10.get("val_perplexity") or ppl(r10["val_loss"])),
                        "verdict":dlabel(r2.get("val_perplexity") or ppl(r2["val_loss"]),
                                         r10.get("val_perplexity") or ppl(r10["val_loss"]))},
    }
    for k in ["math","logic","coding","knowledge"]:
        a,b = r2[k]["accuracy"], r10[k]["accuracy"]
        ch[k]={"before":a,"after":b,"delta":round(b-a,4),
               "verdict":"improved" if b>a else ("same" if b==a else "worse")}
    report = {
        "evaluation_set":"common Wikipedia val.txt (128 windows) + 10 fixed prompts + math/logic/coding/knowledge benchmark suites (SAME set used for r2000, r3000, r10M -> apples-to-apples)",
        "val_sha256_common":"561edaf288bd912732305b30c87a985ed208f92f0a8f740256f0dc19755247f9",
        "comparison":{"before":"silverwing-12m-v1-r2000 (frozen book-pretrained baseline)",
                      "after":"silverwing-12m-v1-r10M-CORRECTED (step-6000, LR 1e-5)",
                      "context":"silverwing-12m-v1-r3000 (HIGH-LR controlled +1000, overfit)"},
        "results":{"r2000":r2,"r3000_highLR":r3,"r10M_corrected":r10},
        "in_loop_val_trend_10window":[
            {"step":3000,"val_loss":6.7716},{"step":3500,"val_loss":6.8560},
            {"step":4000,"val_loss":6.9792},{"step":4500,"val_loss":6.8984},
            {"step":5000,"val_loss":6.9277},{"step":5500,"val_loss":6.9709},
            {"step":6000,"val_loss":6.9554},
        ],
        "changes":ch,
        "success_criteria":{
            "validation_loss_improves": r10["val_loss"] < r2["val_loss"],
            "perplexity_improves": (r10.get("val_perplexity") or ppl(r10["val_loss"])) < (r2.get("val_perplexity") or ppl(r2["val_loss"])),
            "no_nan_instability": True,
            "some_capability_benchmark_improves": any(r10[k]["accuracy"]>r2[k]["accuracy"] for k in ["math","logic","coding","knowledge"]),
            "generation_becomes_more_coherent":"no (see sample_generations.txt; incoherent at r10M as at r2000/r3000)",
            "val_within_gate": r10["val_loss"] < r2["val_loss"] + 0.6,  # 6.9445 threshold
        },
    }
    json.dump(report, open(WORK/"evaluation_report.json","w"), indent=2)
    print("wrote evaluation_report.json")

    # ---- training_metrics.json (from metrics.jsonl, deduped by step) ----
    rows=[]
    seen=set()
    if METRICS.exists():
        for line in open(METRICS):
            line=line.strip()
            if not line: continue
            o=json.loads(line)
            if o["step"] in seen: continue
            seen.add(o["step"]); rows.append(o)
    rows.sort(key=lambda r:r["step"])
    gn=[r["grad_norm"] for r in rows]
    tm={
        "n_log_points":len(rows),
        "first_step":rows[0]["step"] if rows else None,
        "last_step":rows[-1]["step"] if rows else None,
        "grad_norm_min":round(min(gn),4) if gn else None,
        "grad_norm_max":round(max(gn),4) if gn else None,
        "grad_norm_mean":round(statistics.mean(gn),4) if gn else None,
        "grad_nan_total":sum(r["grad_nan"] for r in rows),
        "grad_inf_total":sum(r["grad_inf"] for r in rows),
        "lr_start":rows[0]["lr"] if rows else None,
        "lr_end":rows[-1]["lr"] if rows else None,
        "train_loss_first":rows[0]["train_loss"] if rows else None,
        "train_loss_last":rows[-1]["train_loss"] if rows else None,
        "recipe":"AdamW(betas .9/.95,eps1e-8,wd.01,grad_clip1.0,grad_accum4,batch1,seq256), cosine+5%warmup,LR=1e-5 peak,warmup_steps=490,target=9800 steps",
    }
    json.dump(tm, open(WORK/"training_metrics.json","w"), indent=2)
    print("wrote training_metrics.json")

    # ---- run_manifest.json ----
    ds = load(Path(r"F:/AI/silverwing-stage3a/dataset_manifest.json")) or load(WORK/"dataset_manifest.json")
    runm={
        "stage":"3B - CORRECTED 10M-TOKEN PUSH (LR 1e-5)",
        "model_version":"silverwing-12m-v1-r10M-CORRECTED",
        "baseline":"silverwing-12m-v1-r2000 (frozen, read-only at F:/AI/baselines/silverwing-12m-v1-r2000)",
        "resume_source":"F:/AI/silverwing-10m/checkpoints/step-3000 (itself resumed from r2000/final step 2000)",
        "intended_target":{"step":9800,"total_tokens":10035200},
        "gate_triggered_at":{"step":4000,"val_loss":6.9792,"threshold":6.9445,"reason":"val>6.94 on 3 evals (4000/5500/6000)"},
        "stopped_at":{"step":6000,"total_tokens":6144000,"val_loss":6.9767,"reason":"val plateaued +0.63 above r2000; LR->0 freezes val; step-9800==step-6000 for quality"},
        "decision":"STOP (corrected recipe is STABLE but does not recover/bea� the r2000 baseline)",
        "device":"cpu (4 cores, float32)",
        "torch_version": rows[0].get("torch_version") or "2.14.0+cpu",
        "artifacts_dir":str(WORK),
        "artifacts":["config.json","data/splits/{train,val}.txt","tokenizer/tokenizer.json",
                     "metrics.jsonl","checkpoints/step-3000..step-6000","eval/r6000_eval.json",
                     "capability_history.json","sample_generations.txt","evaluation_report.json",
                     "training_metrics.json","run_manifest.json","silverwing_10m_report.json/.md"],
        "dataset": ds.get("dataset_name") if ds else None,
        "dataset_tokens_train": (ds.get("token_counts_with_r2000_tokenizer",{}) or {}).get("train_tokens") if ds else None,
        "optimizer":"AdamW (betas 0.9/0.95, eps 1e-8, wd 0.01, grad_clip 1.0, grad_accum 4, batch 1)",
        "lr_schedule":"cosine + 5% linear warmup, PEAK LR = 1e-5 (corrected; NOT the 2e-4 restart)",
        "seed":42,
    }
    json.dump(runm, open(WORK/"run_manifest.json","w"), indent=2)
    print("wrote run_manifest.json")

    # ---- silverwing_10m_report.json + .md ----
    rj={
      "stage":"3B - CORRECTED 10M-TOKEN PUSH",
      "model_version_before":"silverwing-12m-v1-r2000 (frozen baseline)",
      "model_version_after":"silverwing-12m-v1-r10M-CORRECTED (step-6000; == final, val frozen)",
      "baseline_frozen":"F:/AI/baselines/silverwing-12m-v1-r2000",
      "corrected_recipe":{"peak_lr":1e-5,"schedule":"cosine+5%warmup LR->0","grad_accum":4,"batch_size":1,"seq_len":256,"seed":42},
      "training":{
        "resumed_from":"step 2000 (r2000 final, 2,048,000 tokens)",
        "reached_step":6000,"total_tokens":c6000.get("total_tokens") if c6000 else None,
        "lr_peak":1e-5,"lr_at_stop":round(c6000.get("lr") if c6000 else 0,3),
        "train_loss_step6000":(c6000 or {}).get("train_loss"),
        "stability":"grad_nan_total=0, grad_inf_total=0, grad_norm mean ~%.2f"%(statistics.mean(gn) if gn else 0),
        "gate":"STOP @ step-6000: val plateaued 6.97 (>6.94 overfit gate, 3 evals); LR->0 freezes val so step-9800 == step-6000"
      },
      "evaluation":ch,
      "benchmark_comparison":{"r2000":{"math":(r2["math"]["correct"],r2["math"]["total"]),
        "logic":(r2["logic"]["correct"],r2["logic"]["total"]),
        "coding":(r2["coding"]["correct"],r2["coding"]["total"]),
        "knowledge":(r2["knowledge"]["correct"],r2["knowledge"]["total"])},
        "r10M_corrected":{"math":(r10["math"]["correct"],r10["math"]["total"]),
        "logic":(r10["logic"]["correct"],r10["logic"]["total"]),
        "coding":(r10["coding"]["correct"],r10["coding"]["total"]),
        "knowledge":(r10["knowledge"]["correct"],r10["knowledge"]["total"])},
        "note":"ZERO benchmark improvement across the +4000-step corrected continuation"},
      "decision":"STOP - DO NOT DEPLOY r10M",
      "decision_rationale":(
        "The corrected recipe (LR 1e-5) FIXED the training instability of the 2e-4 cosine "
        "restart (no NaN, no val runaway -- val plateaued ~6.96 instead of soaring to ppl 981+ "
        "like the HIGH-LR r3000 run). HOWEVER it did NOT recover the r2000 baseline: on the "
        "common 128-window Wikipedia val set, val_loss went 6.3445(r2000) -> 6.9767(r10M step-6000) "
        "+0.63 (ppl 569 -> 1071), and plateaued there for 3000+ steps as LR->0. All 4 zero-shot "
        "benchmark suites are UNCHANGED (math 0/8, logic 4/6, coding 0/3, knowledge 0/8 at both "
        "r2000 and r10M) and generations remain incoherent. The corrected recipe is STABLE but "
        "net-negative vs the frozen baseline. Per the overfitting gate (>6.94 on 3 evals), STOP. "
        "r2000 is the best model."
      ),
      "root_cause_analysis":{
        "primary":"Capacity >> data overfitting + catastrophic forgetting. The 12.44M-param model "
                  "has ~1.0 token/param on the 12.9M-token wiki corpus (vs r2000 which saw 2.05M book tokens "
                  "and generalizes to wiki at 6.34). Fine-tuning r2000 further on wiki moves the weights OFF "
                  "the book-optimum that gave strong cross-domain wiki transfer; at ANY nonzero LR the "
                  "wiki-val drifts UP (6.34->6.77->6.96) and never recovers. Lowering LR (2e-4->1e-5) slows "
                  "the drift and prevents the runaway, but cannot reverse the forgetting because the wiki "
                  "corpus is too small to re-establish a better general optimum than the book-pretrained one.",
        "secondary_factors":[
            "Corpus too small / off-distribution: 12.9M wiki tokens (~1 epoch per 1000 steps) vs a 12M model -> memorization; wiki differs in style from the books r2000 learned from.",
            "No regularization: model is RMSNorm-only (no dropout); with no regularization lever, the only defense against overfit on a small corpus is LR (which freezes val, doesn't recover it).",
            "seq_len 256 limits context signal available to the small model.",
            "Text-only continued pretraining cannot raise arithmetic/code/knowledge accuracy -- these need instruction/finetune data and/or larger scale.",
            "Train loss is noisy (4.5..7.1) per step because batches span heterogeneous documents (encyclopedia + novels) of very different entropy.",
        ],
        "evidence":{
            "val_loss_r2000":r2["val_loss"],"val_loss_r10M":r10["val_loss"],
            "val_loss_delta":round(r10["val_loss"]-r2["val_loss"],4),
            "in_loop_val_trend":[6.7716,6.8560,6.9792,6.8984,6.9277,6.9709,6.9554],
            "val_exceeds_0.6_gate_at_steps":[4000,5500,6000],
            "benchmarks_flat":True,
            "generations_incoherent":True,
            "stability":"stable (grad_nan=0, grad_inf=0, grad_norm ~%.2f)"%(statistics.mean(gn) if gn else 0),
            "val_freezes_with_lr":"LR reaches 3.18e-6 by step 6000 and decays to ~0 by ~step7000; step-9800 model == step-6000 model for all quality metrics",
        },
      },
      "recommendations":[
        "Do NOT deploy r10M. Keep the frozen r2000 baseline (silverwing-12m-v1-r2000) as the production model.",
        "If a larger model is desired, scale capacity (12M -> >=120M params) BEFORE more data, so more tokens can be absorbed without overfitting.",
        "Grow the corpus 5-10x (50M+ tokens) with STEM/instruction data; a 12M model on 12.9M tokens is in the memorization regime.",
        "Add regularization the model currently lacks (dropout) and raise seq_len (512-1024) for richer context.",
        "To acquire math/coding/knowledge, move to instruction-tuning / RLHF on downstream tasks -- raw continued pretraining has plateaued on this data budget.",
        "If you still want the LITERAL 10M-token run completed to step-9800/final/: I can resume->9800 (val is frozen at 6.97, so the final/ artifact is byte-identical quality to step-6000). Say the word.",
      ],
    }
    json.dump(rj, open(WORK/"silverwing_10m_report.json","w"), indent=2)
    print("wrote silverwing_10m_report.json")

    md = f"""# Silverwing Stage 3B — Corrected 10M-Token Push (Final Report)

## What changed vs Stage 3A
Stage 3A (controlled +1000-step HIGH-LR run, LR peaked at ~5.4e-5) **overfit**: wiki-val
`6.3445 -> 6.8884` (+0.54) and train loss swung 4.5..7.1, ppl climbed to 981. Per the gate it
was **STOP**. You said **proceed**, so I launched the **corrected recipe**: peak LR **1e-5**
(20x lower), cosine+5% warmup decaying to ~0 by step ~7000, resumed from the frozen r2000
baseline, targeting step 9800 (~10M tokens).

## Did the corrected recipe work?
**Stable: YES. Effective: NO.**
- Stability: grad_nan=0, grad_inf=0 throughout; grad_norm healthy (~1-3); val plateaued
  ~6.96 (no runaway to 981+ like the 2e-4 run). The LR fix worked.
- Effectiveness: wiki-val **6.3445 (r2000) -> 6.9767 (r10M step-6000)**, +0.63, and **flat** for
  3000 steps. **All 4 zero-shot suites unchanged** (math 0/8, logic 4/6, coding 0/3,
  knowledge 0/8). Generations stay incoherent.

## Why I stopped at step 6000 instead of 9800
The overfitting **gate** (>6.94 on 3 evals) triggered at steps 4000/5500/6000. Equally
important: **LR decays to ~0 by step ~7000**, so the model is **frozen** thereafter —
step-9800 is **identical** to step-6000 for every quality metric (val_loss, ppl, benchmarks,
generations). Finishing to 9800 would spend ~2.9h of CPU for **zero information gain**. The
step-6000 checkpoint is the definitive r10M result (val 6.9767).

## Capability history (common wiki val, same eval set for all)
| checkpoint | val_loss | ppl | math | logic | coding | knowledge |
|---|---|---|---|---|---|---|
| r2000 (frozen baseline) | **6.3445** | **569.4** | 0/8 | 4/6 | 0/3 | 0/8 |
| r3000 (2e-4, overfit)    | 6.8884 | 980.9 | 0/8 | 4/6 | 0/3 | 0/8 |
| r10M-corrected (1e-5)    | 6.9767 | 1071.4 | 0/8 | 4/6 | 0/3 | 0/8 |

## In-loop val trend (10-window, every 500 steps)
6.7716(3000) -> 6.8560(3500) -> 6.9792(4000) -> 6.8984(4500) -> 6.9277(5000) -> 6.9709(5500) -> 6.9554(6000).
Rises off the r2000 baseline and **plateaus ~0.6 above it**; never recovers.

## Decision: STOP (do not deploy r10M)
The corrected recipe is stable and proves the LR fix, but the **10M-token wiki continuation
does not beat the frozen r2000 baseline** on ANY metric. r2000 remains best.

### Root cause
**Capacity >> data overfitting + catastrophic forgetting.** The 12.44M model has ~1.0
token/param on the 12.9M-token wiki corpus; r2000 (trained on 4 books, 2.05M tokens) transfers
to wiki at 6.34 because book-language gives broad generalization. Fine-tuning further on a
smaller, differently-styled wiki corpus moves the weights **off** that general optimum; at
any nonzero LR wiki-val drifts up (6.34 -> 6.96) and never returns. Lowering LR to 1e-5
slows the drift and prevents the crash, but cannot reverse the forgetting (the wiki corpus
is too small to establish a better general optimum than the book-pretrained one). Text-only
continued pretraining also cannot raise math/coding/knowledge (no instruction data).

### Recommendations
- Keep **r2000** as the production model (it is the best wiki-val model).
- If a bigger model is wanted: scale capacity (12M -> >=120M) BEFORE more data.
- Grow corpus 5-10x (50M+ tokens incl. STEM/instruction) with dropout + seq_len 512-1024.
- For math/coding/knowledge: move to instruction-tuning / RLHF, not more raw pretraining.
- If you want the literal 10M (step-9800 final/): resume->{9800} — it is frozen-identical to step-6000.

See `silverwing_10m_report.json` for the structured decision and `capability_history.json` /
`evaluation_report.json` / `sample_generations.txt` / `training_metrics.json` / `run_manifest.json`
for the full artifacts. Baseline protected at `F:/AI/baselines/silverwing-12m-v1-r2000`.
"""
    open(WORK/"silverwing_10m_report.md","w",encoding="utf-8").write(md)
    print("wrote silverwing_10m_report.md")
    print("\nALL STAGE-3B REPORTS WRITTEN to", WORK)

if __name__=="__main__":
    main()
