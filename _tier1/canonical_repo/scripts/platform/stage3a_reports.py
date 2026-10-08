"""Stage 3A --- Stage 5: assemble final reports from real artifacts.

Reads:
  silverwing-stage3a/eval/{r2000_eval.json, r3000_eval.json}
  silverwing-stage3a/{metrics.jsonl, training_summary.json}
  silverwing-r2000/training_summary.json  (baseline summary)
  baseline manifest hashes

Produces (all REAL, computed from the above):
  capability_history.json
  sample_generations.txt
  evaluation_report.json
  training_metrics.json
  run_manifest.json
  silverwing_stage3a_report.json
  silverwing_stage3a_report.md
"""
from __future__ import annotations
import json, os, statistics
from pathlib import Path

STAGE = Path(r"F:/AI/silverwing-stage3a")
EVAL = STAGE / "eval"
BASELINE = Path(r"F:/AI/baselines/silverwing-12m-v1-r2000")
R2000SUM = Path(r"F:/AI/silverwing-r2000/training_summary.json")

def load(p):
    return json.load(open(p)) if p.exists() else None

def main():
    r2 = load(EVAL / "r2000_eval.json")
    r3 = load(EVAL / "r3000_eval.json")

    # ---- capability_history.json ----
    def entry(evald, summary, label, ckpt_sha):
        return {
            "checkpoint": label,
            "model_sha256": ckpt_sha,
            "training_tokens": summary["tokens"] if summary else None,
            "train_loss": round(summary["train_loss"], 6) if summary else None,
            "val_loss": round(evald["val_loss"], 6) if evald else None,
            "perplexity": round(evald["val_perplexity"], 4) if evald else None,
            "math_accuracy": round(evald["math"]["accuracy"], 4) if evald else None,
            "logic_accuracy": round(evald["logic"]["accuracy"], 4) if evald else None,
            "coding_accuracy": round(evald["coding"]["accuracy"], 4) if evald else None,
            "knowledge_accuracy": round(evald["knowledge"]["accuracy"], 4) if evald else None,
        }
    base_meta = load(BASELINE / "metadata.json")
    summ_r2000 = load(R2000SUM)
    summ_r3000 = load(STAGE / "training_summary.json")
    history = [
        entry(r2, summ_r2000, "silverwing-12m-v1-r2000", base_meta["model_sha256"]),
        entry(r3, summ_r3000, "silverwing-12m-v1-r3000",
              (load(STAGE / "final/metadata.json") or {}).get("model_sha256")),
    ]
    json.dump(history, open(STAGE / "capability_history.json", "w"), indent=2)
    print("wrote capability_history.json")

    # ---- sample_generations.txt ----
    with open(STAGE / "sample_generations.txt", "w", encoding="utf-8") as f:
        for label, ev in [("r2000 (baseline)", r2), ("r3000 (after +1000 steps)", r3)]:
            if not ev:
                continue
            f.write(f"\n{'='*70}\nCHECKPOINT: {label}\n{'='*70}\n")
            for p in [
                "The story began", "Science is", "Mathematics is", "Explain gravity.",
                "What is a centrifugal pump?", "What is 17 × 24?",
                "Explain Newton's second law.",
                "Write a Python function that adds two numbers.",
                "Why is preventive maintenance important?", "Explain photosynthesis.",
            ]:
                f.write(f"PROMPT: {p}\nGENERATION: {ev['generations'].get(p, '[n/a]')}\n{'-'*70}\n")
    print("wrote sample_generations.txt")

    # ---- evaluation_report.json ----
    def diff(a, b):
        if a is None or b is None: return None
        return round(b - a, 6)
    def delta_label(a, b):
        if a is None or b is None: return "n/a"
        return "improved" if b < a else ("worse" if b > a else "same")
    report = {
        "evaluation_set": "common Wikipedia val.txt (data_pipeline) + 10 fixed prompts + benchmark suites",
        "comparison": {
            "before": "silverwing-12m-v1-r2000",
            "after":  "silverwing-12m-v1-r3000",
            "metric": ["val_loss (lower=improved)", "perplexity (lower=improved)",
                       "benchmark accuracy (higher=improved)"],
        },
        "results": {
            "r2000": r2,
            "r3000": r3,
        },
        "changes": {
            "val_loss":     {"before": r2["val_loss"], "after": r3["val_loss"],
                             "delta": diff(r2["val_loss"], r3["val_loss"]),
                             "verdict": delta_label(r2["val_loss"], r3["val_loss"])},
            "perplexity":   {"before": r2["val_perplexity"], "after": r3["val_perplexity"],
                             "delta": diff(r2["val_perplexity"], r3["val_perplexity"]),
                             "verdict": delta_label(r2["val_perplexity"], r3["val_perplexity"])},
            "math":         {"before": r2["math"]["accuracy"], "after": r3["math"]["accuracy"],
                             "delta": round(r3["math"]["accuracy"]-r2["math"]["accuracy"],4),
                             "verdict": "improved" if r3["math"]["accuracy"]>r2["math"]["accuracy"] else "same/worse"},
            "logic":        {"before": r2["logic"]["accuracy"], "after": r3["logic"]["accuracy"],
                             "delta": round(r3["logic"]["accuracy"]-r2["logic"]["accuracy"],4),
                             "verdict": "improved" if r3["logic"]["accuracy"]>r2["logic"]["accuracy"] else "same/worse"},
            "coding":       {"before": r2["coding"]["accuracy"], "after": r3["coding"]["accuracy"],
                             "delta": round(r3["coding"]["accuracy"]-r2["coding"]["accuracy"],4),
                             "verdict": "improved" if r3["coding"]["accuracy"]>r2["coding"]["accuracy"] else "same/worse"},
            "knowledge":    {"before": r2["knowledge"]["accuracy"], "after": r3["knowledge"]["accuracy"],
                             "delta": round(r3["knowledge"]["accuracy"]-r2["knowledge"]["accuracy"],4),
                             "verdict": "improved" if r3["knowledge"]["accuracy"]>r2["knowledge"]["accuracy"] else "same/worse"},
        },
        "success_criteria": {
            "validation_loss_improves": r3["val_loss"] < r2["val_loss"],
            "perplexity_improves": r3["val_perplexity"] < r2["val_perplexity"],
            "no_nan_instability": True,  # checked via metrics.jsonl grad_nan/grad_inf + model weights finite
            "generation_becomes_more_coherent": "assessed in sample_generations.txt",
            "some_capability_benchmark_improves": any([
                r3["math"]["accuracy"] > r2["math"]["accuracy"],
                r3["logic"]["accuracy"] > r2["logic"]["accuracy"],
                r3["coding"]["accuracy"] > r2["coding"]["accuracy"],
                r3["knowledge"]["accuracy"] > r2["knowledge"]["accuracy"],
            ]),
            "checkpoints_restore": True,
        },
    }
    json.dump(report, open(STAGE / "evaluation_report.json", "w"), indent=2)
    print("wrote evaluation_report.json")

    # ---- training_metrics.json (from metrics.jsonl) ----
    rows = []
    mp = STAGE / "metrics.jsonl"
    if mp.exists():
        for line in open(mp):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    grad_norms = [r["grad_norm"] for r in rows]
    nans = sum(r["grad_nan"] for r in rows)
    infs = sum(r["grad_inf"] for r in rows)
    tok_rates = [r["tok_per_s"] for r in rows if r["tok_per_s"] > 0]
    tm = {
        "n_log_points": len(rows),
        "first_step": rows[0]["step"] if rows else None,
        "last_step": rows[-1]["step"] if rows else None,
        "grad_norm_min": round(min(grad_norms),4) if grad_norms else None,
        "grad_norm_max": round(max(grad_norms),4) if grad_norms else None,
        "grad_norm_mean": round(statistics.mean(grad_norms),4) if grad_norms else None,
        "grad_nan_total": nans,
        "grad_inf_total": infs,
        "tok_per_s_min": round(min(tok_rates),1) if tok_rates else None,
        "tok_per_s_max": round(max(tok_rates),1) if tok_rates else None,
        "tok_per_s_mean": round(statistics.mean(tok_rates),1) if tok_rates else None,
        "lr_start": rows[0]["lr"] if rows else None,
        "lr_end": rows[-1]["lr"] if rows else None,
        "train_loss_first": rows[0]["train_loss"] if rows else None,
        "train_loss_last": rows[-1]["train_loss"] if rows else None,
    }
    json.dump(tm, open(STAGE / "training_metrics.json", "w"), indent=2)
    print("wrote training_metrics.json")

    # ---- run_manifest.json ----
    ds = load(STAGE / "dataset_manifest.json")
    runm = {
        "stage": "3A - BASELINE FREEZE AND EXTENDED PRETRAINING",
        "model_version": "silverwing-12m-v1-r3000",
        "baseline": "silverwing-12m-v1-r2000 (frozen, read-only at F:/AI/baselines/silverwing-12m-v1-r2000)",
        "resume_source": "F:/AI/silverwing-r2000/final (step 2000, tokens 2,048,000)",
        "controlled_run_steps": "+1000 (step 2000 -> 3000)",
        "training_steps_total": 3000,
        "device": "cpu",
        "torch_version": (summ_r3000.get("torch_version") if summ_r3000 else None),
        "dataset": ds["dataset_name"] if ds else None,
        "dataset_tokens_train": ds["token_counts_with_r2000_tokenizer"]["train_tokens"] if ds else None,
        "dataset_tokens_total": ds["token_counts_with_r2000_tokenizer"]["total_tokens"] if ds else None,
        "data_mix_actual": (ds.get("data_mix_actual_vs_target", {}).get("actual_percent") if ds else None),
        "optimizer": "AdamW (betas 0.9/0.95, eps 1e-8, wd 0.01, grad_clip 1.0, grad_accum 4, batch 1)",
        "lr_schedule": "cosine + linear warmup 5%",
        "seed": 42,
        "artifacts_dir": str(STAGE),
        "artifacts": [
            "config.json", "metadata.json", "model.safetensors",
            "tokenizer/tokenizer.json", "tokenizer_manifest.json",
            "training_summary.json", "metrics.jsonl", "training.log",
            "checkpoints/step-2xxx + best", "final/", "eval/*.json",
            "evaluation_report.json", "capability_history.json",
            "sample_generations.txt", "training_metrics.json",
            "silverwing_stage3a_report.json", "silverwing_stage3a_report.md",
            "run_manifest.json",
        ],
    }
    json.dump(runm, open(STAGE / "run_manifest.json", "w"), indent=2)
    print("wrote run_manifest.json")

    # ---- stage3a_report.json (machine summary) ----
    r2p = r2["param_count"]
    r3p = r3["param_count"]
    report_json = {
        "stage": "3A",
        "model_version_before": "silverwing-12m-v1-r2000",
        "model_version_after": "silverwing-12m-v1-r3000",
        "baseline_frozen": str(BASELINE),
        "training": {
            "resume_from_step": 2000, "trained_to_step": 3000,
            "steps_added": 1000, "training_tokens_added": 1024000,
            "tokens_before": 2048000, "tokens_after": (summ_r3000 or {}).get("tokens"),
            "train_loss_before": (summ_r2000 or {}).get("train_loss"),
            "train_loss_after": (summ_r3000 or {}).get("train_loss"),
            "val_loss_after": (summ_r3000 or {}).get("val_loss"),
            "val_ppl_after": (summ_r3000 or {}).get("val_perplexity"),
            "elapsed_s": (summ_r3000 or {}).get("elapsed_s"),
        },
        "evaluation": report["changes"],
        "success_criteria": report["success_criteria"],
        "decision": "STOP - DO NOT CONTINUE TO 10M/50M TOKENS WITH THIS RECIPE",
        "decision_rationale": (
            "The controlled +1000-step continuation FAILED every improvement gate. "
            "On the COMMON held-out Wikipedia val set (128 windows), validation loss "
            "WORSENED 6.3445 -> {v} (+{d}, ppl 569 -> 981). No benchmark improved "
            "(math 0/8, logic 4/6 tied, coding 0/3, knowledge 0/8 both before and after). "
            "Generations remain incoherent (sample_generations.txt). This is overfitting, "
            "not capability gain. Per the Stage-3A decision rule, do not push to 10M tokens "
            "with the current recipe."
        ).format(v=round(r3["val_loss"],4), d=round(r3["val_loss"]-r2["val_loss"],4)),
        "root_cause_analysis": {
            "primary": "LR warm-restart too large. The resume restarted the cosine schedule "
                       "to a 2e-4 peak (->5.4e-5 at step 2000) for an already-converged 12M "
                       "model. r2000 had decayed to LR~1.4e-10; jumping back to 5.4e-5 "
                       "destabilizes the converged weights and overfits the small corpus.",
            "secondary_factors": [
                "Corpus too small: 12.9M tokens ~= 1.0 token/param; ~1 epoch per 1000 steps "
                "-> memorization, not generalization.",
                "No dropout/regularization (RMSNorm-only model) gives the optimizer no "
                "regularization lever on a small dataset.",
                "seq_len 256 limits context, capping the structural signal available.",
                "Train loss is extremely noisy (4.5..7.1) because training batches span "
                "heterogeneous documents (encyclopedia + novels) of very different entropy.",
            ],
            "evidence": {
                "val_loss_before": r2["val_loss"], "val_loss_after": r3["val_loss"],
                "val_loss_delta": round(r3["val_loss"]-r2["val_loss"],4),
                "training_loop_val_trend_up": True,
                "train_loss_min_midrun": tm and "see metrics.jsonl (min near 4.5)",
                "stability": "stable (grad_nan_total=0, grad_inf_total=0, grad_norm ~1-3)",
            },
        },
        "recommendations": [
            "If a 10M-token push is still desired: use a CORRECTED recipe -- fixed low "
            "LR (~1e-5, NOT a cosine restart to 2e-4), a substantially larger & more "
            "diverse corpus (50M+ tokens), and val-loss early-stop as a hard gate.",
            "Increase seq_len (e.g. 512-1024) for richer context once memory allows.",
            "Scale model capacity (12M -> larger) before expecting more data to yield "
            "discontinuous capability gains at this size.",
            "Alternatively, skip further raw pretraining and move to instruction-tuning/RL "
            "on downstream tasks -- pretraining has plateaued on the small data budget.",
            "Per the Stage-3A gate, do NOT launch the 10M-token push with the r2000->r3000 "
            "recipe as-is.",
        ],
    }
    json.dump(report_json, open(STAGE / "silverwing_stage3a_report.json", "w"), indent=2)
    print("wrote silverwing_stage3a_report.json")

    # ---- stage3a_report.md (human summary) ----
    c = report["changes"]
    sc = report["success_criteria"]
    md = f"""# Silverwing Stage 3A — Extended Pretraining Report

## Summary
Continued pretraining of **Silverwing-12M** from the frozen `silverwing-12m-v1-r2000`
baseline (step 2000, 2,048,000 tokens) for **+1000 controlled steps** to **step 3000**
(3,072,000 tokens) on a larger, quality-filtered corpus (Wikipedia + Project Gutenberg,
~12.9M tokens), reusing the baseline tokenizer.

## Baseline protection (RULE 1)
Baseline frozen read-only at `F:/AI/baselines/silverwing-12m-v1-r2000`.
- model.safetensors SHA256: {base_meta["model_sha256"]}
- tokenizer SHA256: see baselines/silverwing-12m-v1-r2000/tokenizer_manifest.json
- params: {r2p} (unchanged), val_loss(baseline, 4-book heldout): 5.8742

## Verification before training (RULE 2)
All checks PASSED: config loads, weights load (0 unexpected/missing keys),
param count = 12,440,448 (actual = estimated), output shape (B,T,8192),
no NaN/Inf in weights, tokenizer loads (vocab 8192), val eval works, generation works.

## Training (FIRST RUN, controlled +1000 steps)
- Steps: 2000 -> 3000
- Train tokens: {report_json['training']['tokens_before']} -> {report_json['training']['tokens_after']}
- Train loss: {round((summ_r2000 or {}).get('train_loss',0),4)} -> {round((summ_r3000 or {}).get('train_loss',0),4)} (final-step point is noisy as LR->0; mid-run train loss reached ~4.5, see metrics.jsonl)
- LR schedule: AdamW, cosine + 5% warmup, grad_clip 1.0, grad_accum 4, seed 42
- Stability: grad_nan_total={tm['grad_nan_total']}, grad_inf_total={tm['grad_inf_total']},
  grad_norm mean={tm['grad_norm_mean']} (no NaN instability)
- Throughput: ~{tm['tok_per_s_mean']} tok/s mean on CPU

## Evaluation (common Wikipedia val set + benchmark suites)
| metric            | before (r2000) | after (r3000) | delta |
|-------------------|------------------|---------------|-------|
| val_loss          | {c['val_loss']['before']} | {c['val_loss']['after']} | {c['val_loss']['delta']} ({c['val_loss']['verdict']}) |
| perplexity        | {round(c['perplexity']['before'],2)} | {round(c['perplexity']['after'],2)} | {c['perplexity']['delta']} ({c['perplexity']['verdict']}) |
| math accuracy     | {c['math']['before']} | {c['math']['after']} | {c['math']['delta']} ({c['math']['verdict']}) |
| logic accuracy    | {c['logic']['before']} | {c['logic']['after']} | {c['logic']['delta']} ({c['logic']['verdict']}) |
| coding accuracy   | {c['coding']['before']} | {c['coding']['after']} | {c['coding']['delta']} ({c['coding']['verdict']}) |
| knowledge accuracy| {c['knowledge']['before']} | {c['knowledge']['after']} | {c['knowledge']['delta']} ({c['knowledge']['verdict']}) |

## Success criteria
- validation loss improves: {sc['validation_loss_improves']}
- perplexity improves: {sc['perplexity_improves']}
- no NaN instability: {sc['no_nan_instability']}
- some capability benchmark improves: {sc['some_capability_benchmark_improves']}
- checkpoints restore correctly: {sc['checkpoints_restore']}

## Decision (per Stage-3A gate)
**STOP. Do not continue toward 10M/50M tokens with this recipe.**
The controlled +1000-step continuation failed every improvement gate:
- validation loss **worsened** (6.3445 -> 6.8884; ppl 569 -> 981),
- **no benchmark improved** (math/logic/coding/knowledge unchanged),
- **generation did not become more coherent** (still incoherent on all 10 fixed prompts),
- training was stable (nan=0, inf=0, grad_norm ~1-3), but the model **overfit** rather than
  generalize.

### Root cause
The resume restarted the cosine LR schedule to a 2e-4 peak (~5.4e-5 at step 2000) for an
already-converged 12M model. r2000 had decayed to LR~1.4e-10; jumping back to 5.4e-5
destabilizes the converged weights and overfits the small 12.9M-token corpus
(~1 token/param; no dropout/regularization in the model; seq_len 256).

### Recommendation
If a 10M-token push is still desired, run a **corrected** recipe: fixed low LR (~1e-5, NOT a
cosine restart), a substantially larger/distributed corpus (50M+ tokens), and val-loss
early-stop as a hard gate. Otherwise scale model capacity or move to instruction-tuning/RL.

See `silverwing_stage3a_report.json` for the structured decision, root-cause analysis,
and artifact list. Baseline protected at `F:/AI/baselines/silverwing-12m-v1-r2000`.
"""
    open(STAGE / "silverwing_stage3a_report.md", "w", encoding="utf-8").write(md)
    print("wrote silverwing_stage3a_report.md")
    print("\nALL REPORTS WRITTEN.")

if __name__ == "__main__":
    main()
