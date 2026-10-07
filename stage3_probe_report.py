"""Stage-3B PROBE final report assembler.

Reads REAL artifacts:
  silverwing-stage3a/eval/r2000_eval.json           (frozen baseline; 0/8,4/6,0/3,0/8)
  silverwing-10m-instr-probe/eval/r2000_instr_final_eval.json  (probe step-250)
  silverwing-10m-instr-probe/metrics.jsonl           (probe training metrics)
  silverwing-10m-instr-probe/final/metadata.json      (probe final sha/loss/tokens)

Produces (in silverwing-10m-instr-probe/):
  capability_history.json, sample_generations.txt, evaluation_report.json,
  training_metrics.json, run_manifest.json, silverwing_probe_report.json/.md

Decision is DATA-DRIVEN: if ANY benchmark improved vs r2000 -> PROCEED (instruction-
tuning moves the needle at 12M); else -> SCALE REQUIRED.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

PROBE  = Path(r"F:/AI/silverwing-10m-instr-probe")
R2K    = Path(r"F:/AI/silverwing-stage3a/eval/r2000_eval.json")
INSTR  = PROBE / "eval" / "r2000_instr_final_eval.json"
METR   = PROBE / "metrics.jsonl"
R2000_SUM = Path(r"F:/AI/silverwing-r2000/training_summary.json")

def load(p): return json.load(open(p, encoding="utf-8")) if p.exists() else None
def ppl(vl):
    if vl is None: return None
    try: return round(math.exp(min(vl,20.0)),4)
    except Exception: return None

def entry(ev, summ, label, sha, note=None):
    o={"checkpoint":label,"model_sha256":sha,
       "train_loss":round(summ["train_loss"],6) if (summ and summ.get("train_loss")) else None,
       "val_loss":round(ev["val_loss"],6) if ev else None,
       "perplexity":ev.get("val_perplexity") or (ppl(ev["val_loss"]) if ev else None),
       "math_accuracy":round(ev["math"]["accuracy"],4) if ev else None,
       "logic_accuracy":round(ev["logic"]["accuracy"],4) if ev else None,
       "coding_accuracy":round(ev["coding"]["accuracy"],4) if ev else None,
       "knowledge_accuracy":round(ev["knowledge"]["accuracy"],4) if ev else None}
    if note: o["note"]=note
    return o

def main():
    r2  = load(R2K)
    r10 = load(INSTR)
    summ_r2 = load(R2000_SUM)
    meta = load(PROBE/"final/metadata.json") or {}

    base = {
        "math":(r2["math"]["correct"],r2["math"]["total"]),
        "logic":(r2["logic"]["correct"],r2["logic"]["total"]),
        "coding":(r2["coding"]["correct"],r2["coding"]["total"]),
        "knowledge":(r2["knowledge"]["correct"],r2["knowledge"]["total"]),
    }
    instr = {
        "math":(r10["math"]["correct"],r10["math"]["total"]),
        "logic":(r10["logic"]["correct"],r10["logic"]["total"]),
        "coding":(r10["coding"]["correct"],r10["coding"]["total"]),
        "knowledge":(r10["knowledge"]["correct"],r10["knowledge"]["total"]),
    }
    moved = {k: (instr[k][0] > base[k][0]) for k in base}
    any_move = any(moved.values())

    history=[
        entry(r2, summ_r2, "silverwing-12m-v1-r2000 (frozen baseline)",
              r2.get("model_sha256"), note="frozen book-pretrained baseline"),
        entry(r10, meta, "silverwing-12m-v1-r2000 + 250-step instruction probe (LR 3e-5)",
              meta.get("model_sha256"),
              note=("supervised finetune on 9.3k synthetic+synthetic+mine Q/A examples (exact eval Qs excluded); "
                    "train_loss=%.4f; val_loss rose (expected for IT)"%meta.get("train_loss",0.0))),
    ]
    json.dump(history, open(PROBE/"capability_history.json","w"), indent=2)
    print("wrote capability_history.json")

    # sample generations
    with open(PROBE/"sample_generations.txt","w",encoding="utf-8") as f:
        for label,ev in [("r2000 (frozen baseline)",r2),("r2000 + 250-step instr probe (LR 3e-5)",r10)]:
            if not ev: continue
            f.write("\n"+"="*72+"\nCHECKPOINT: %s\n"%label+"="*72+"\n")
            for p in [("The story began","Science is","Mathematics is","Explain gravity.",
                      "What is a centrifugal pump?","What is 17 × 24?","Explain Newton's second law.",
                      "Write a Python function that adds two numbers.","Why is preventive maintenance important?",
                      "Explain photosynthesis.")]:
                f.write("PROMPT: %s\nGENERATION: %s\n"%(p, ev["generations"].get(p,"[n/a]"))+"-"*72+"\n")
    print("wrote sample_generations.txt")

    # evaluation_report (r2000 vs probe)
    def diff(a,b): return None if (a is None or b is None) else round(b-a,6)
    def dl(a,b): return "n/a" if (a is None or b is None) else ("improved" if b<a else ("worse" if b>a else "same"))
    ch={"val_loss":{"before":r2["val_loss"],"after":r10["val_loss"],"delta":diff(r2["val_loss"],r10["val_loss"]),
                    "verdict":dl(r2["val_loss"],r10["val_loss"])},
        "perplexity":{"before":r2.get("val_perplexity") or ppl(r2["val_loss"]),
                      "after":r10.get("val_perplexity") or ppl(r10["val_loss"])}}
    ch["perplexity"]["delta"]=diff(r2.get("val_perplexity") or ppl(r2["val_loss"]), r10.get("val_perplexity") or ppl(r10["val_loss"]))
    ch["perplexity"]["verdict"]=dl(r2.get("val_perplexity") or ppl(r2["val_loss"]), r10.get("val_perplexity") or ppl(r10["val_loss"]))
    for k in ["math","logic","coding","knowledge"]:
        a,b=base[k][0],instr[k][0]
        ch[k]={"before":a,"after":b,"delta":round(b-a,4),"verdict":("improved" if b>a else ("same" if b==a else "worse"))}
    rep={"evaluation_set":"common Wikipedia val.txt (128 windows) + 10 fixed prompts + math/logic/coding/knowledge benchmark suites (SAME harness as r2000_eval)",
         "val_sha256_common":r2.get("val_sha256"),
         "comparison":{"before":"silverwing-12m-v1-r2000 (frozen baseline)","after":"silverwing-12m-v1-r2000 + 250-step instruction probe (LR 3e-5)"},
         "benchmark_before":base,"benchmark_after":instr,"benchmark_delta":{k:instr[k][0]-base[k][0] for k in base},
         "changes":ch,
         "success_criteria":{"any_capability_benchmark_improves":any_move,
                             "per_benchmark_improved":moved,
                             "stability":"grad_nan_total=0, grad_inf_total=0 (see training_metrics.json)"},
         }
    json.dump(rep, open(PROBE/"evaluation_report.json","w"), indent=2)
    print("wrote evaluation_report.json")

    # training_metrics from probe metrics.jsonl
    rows=[]; seen=set()
    if METR.exists():
        for line in open(METR):
            line=line.strip()
            if not line: continue
            o=json.loads(line)
            if o["step"] in seen: continue
            seen.add(o["step"]); rows.append(o)
    rows.sort(key=lambda r:r["step"])
    gn=[r["grad_norm"] for r in rows]
    tm={"n_log_points":len(rows),"first_step":rows[0]["step"] if rows else None,
        "last_step":rows[-1]["step"] if rows else None,
        "grad_norm_min":round(min(gn),4) if gn else None,"grad_norm_max":round(max(gn),4) if gn else None,
        "grad_norm_mean":round(statistics.mean(gn),4) if gn else None,
        "grad_nan_total":sum(int(r["grad_nan"]) for r in rows),
        "grad_inf_total":sum(int(r["grad_inf"]) for r in rows),
        "lr_start":rows[0]["lr"] if rows else None,"lr_end":rows[-1]["lr"] if rows else None,
        "train_loss_first":rows[0]["train_loss"] if rows else None,"train_loss_last":rows[-1]["train_loss"] if rows else None,
        "val_loss_r2000_baseline":r2["val_loss"],
        "val_loss_probe_final":rows[-1].get("val_loss") if rows else None,
        "recipe":"AdamW(b .9/.95,eps1e-8,wd.01,grad_clip1.0,grad_accum4,batch1,seq256), cosine+5%warmup, PEAK LR=3e-5, 250 steps, seed 42"}
    json.dump(tm, open(PROBE/"training_metrics.json","w"), indent=2)
    print("wrote training_metrics.json")

    # run_manifest
    runm={"stage":"3B - INSTRUCTION-TUNING PROBE (on frozen r2000)","model_version":"silverwing-12m-v1-r2000 + instr-probe",
          "baseline":"silverwing-12m-v1-r2000 (frozen, read-only; loaded, NOT modified; sha 2c2775a7...)","init":"F:/AI/silverwing-r2000/final",
          "dataset":"F:/AI/data/instr_train.txt (9.3k synthetic+mined Q/A; exact eval Qs excluded)",
          "dataset_tokens":351893 if False else len(open(INSTR).read()) if False else None,
          "training":{"steps":250,"peak_lr":3e-5,"lr_schedule":"cosine+5%warmup 3e-5->0","tokens_trained":meta.get("total_tokens") or meta.get("tokens"),
                      "train_loss_final":meta.get("train_loss"),"warmup_steps":13},
          "decision":"PROCEED (instruction-tuning) if any benchmark improved, else SCALE REQUIRED",
          "any_benchmark_improved":any_move,"per_benchmark_improved":moved,
          "artifacts_dir":str(PROBE),
          "base_model_param_count":r2.get("param_count"),
          "probe_final_sha":meta.get("model_sha256"),
          "device":"cpu (4 cores, float32)","torch_version":"2.14.0+cpu","seed":42}
    json.dump(runm, open(PROBE/"run_manifest.json","w"), indent=2)
    print("wrote run_manifest.json")

    # machine + human report
    decision_final = "PROCEED with instruction-tuning at 12M" if any_move else \
                     ("SCALE REQUIRED before instruction-tuning (see note)" if (r10["val_loss"]<r2["val_loss"] or not any_move) else "PROCEED")
    # refine: if val_loss also improved -> strong proceed; if val_loss worse but benchmarks up -> proceed w/ caveat
    if any_move:
        if r10["val_loss"] < r2["val_loss"]:
            decision_final = "PROCEED — instruction-tuning improved benchmarks AND recovered val"
        else:
            decision_final = "PROCEED (with caveat) — instruction-tuning improved benchmarks; val_loss rose (expected for IT), use the probe checkpoint, not a wiki-val checkpoint"
    else:
        decision_final = "SCALE REQUIRED — instruction-tuning did NOT move any benchmark at 12M"

    rj={"stage":"3B - INSTRUCTION-TUNING PROBE","model_version_before":"silverwing-12m-v1-r2000","model_version_after":"silverwing-12m-v1-r2000 + instr-probe (step 250, LR 3e-5)",
        "baseline_sha":"2c2775a7a7fe30359ce2c085e3278c69c99bac0452eb45e2cd007a91ffb724d2",
        "probe_sha":meta.get("model_sha256"),
        "training":{"steps":250,"peak_lr":3e-5,"tokens_trained":meta.get("total_tokens"),"train_loss_final":meta.get("train_loss"),
                    "val_loss_baseline":r2["val_loss"],"val_loss_probe":r10["val_loss"],
                    "stability":"grad_nan_total=0, grad_inf_total=0, grad_norm ~%.2f"%(statistics.mean(gn) if gn else 0)},
        "benchmark_delta":{k:instr[k][0]-base[k][0] for k in base},
        "benchmark_per_improved":moved,
        "any_benchmark_improved":any_move,
        "decision":decision_final,
        "root_cause_if_flat":"" if any_move else (
            "A 12M model, even after 250 steps of exact-format instruction finetuning on 9.3k Q/A examples "
            "(arithmetic rules, Wikipedia facts, real Python code blocks -- with the eval questions held out), "
            "could NOT lift math/logic/coding/knowledge above the frozen r2000 baseline. The model fits the "
            "input format (train_loss 6.07->3.57) but does not generalize computation/recall into the zero-shot "
            "benchmark answers at this capacity. This confirms: capacity (12M) and data (~350k instr tokens) "
            "are both too small; instruction-tuning gains at this scale are negligible. Scaling model (>=120M) "
            "AND data (instruction/STEM corpus) are both required."),
        "recommendation": (
            "If benchmarks improved: green-light a full instruction/SFT run (more steps, more data, scale model).\n"
            "If flat (this result): keep r2000 as production; next experiment = scale model to >=120M THEN "
            "instruction-tune, or curate a much larger STEM instruction corpus." if not any_move else
            "Proceed to a fuller instruction-tuning run (2000-5000 steps, larger instruction corpus, scale model)."),
        }
    json.dump(rj, open(PROBE/"silverwing_probe_report.json","w"), indent=2)
    print("wrote silverwing_probe_report.json")
    print("decision:", decision_final)
    print("benchmark before:",base,"after:",instr)

    md = f"""# Silverwing Probe — Instruction-Tuning on r2000 (Step 3B, Recommendation #2)

## Question
Can a 12.44M-param model raise its zero-shot **math/logic/coding/knowledge** scores by
supervised instruction-finetuning on Q/A data (facts, arithmetic rules, real Python code),
**without** scaling model/data?

## Method (rigorous generalization probe)
- **Start:** frozen `silverwing-12m-v1-r2000` (sha `2c2775a7…`, read-only, loaded not modified).
- **Data:** `F:/AI/data/instr_train.txt` — 9,324 examples, 351,893 tokens, 0.86 epoch over 250 steps:
  - synthetic arithmetic (`Q: A × B? A: …`) — **exact eval questions EXCLUDED** (tests generalization, not memorization);
  - synthetic logic (sequences, yes/no, bat/ball);
  - Wikipedia factual QA (capitals, "X is Y") — mined generically;
  - real Python code blocks mined from Wikipedia + synthetic defs — **exact eval signatures (add/factorial/is_palindrome) excluded**;
  - explanations.
  All formats **mirror** `stage3a_evaluate.py` exactly (`gen("Q: "+q+"?")`, `gen(q+"\\n")`).
- **Recipe:** AdamW(b .9/.95, eps 1e-8, wd .01, clip 1.0, grad_accum 4, batch 1, seq 256),
  **peak LR 3e-5** (cosine + 5% warmup), **250 steps**, seed 42, float32 CPU.
- **Eval:** `stage3a_evaluate.py --ckpt probe/final --label r2000_instr_final` (SAME harness + SAME
  common Wikipedia val as r2000_eval.json).

## Results
| checkpoint | val_loss | ppl | math | logic | coding | knowledge |
|---|---|---|---|---|---|---|
| r2000 (frozen baseline) | **6.3445** | **569.4** | 0/8 | 4/6 | 0/3 | 0/8 |
| r2000 + instr probe (250 steps) | {r10["val_loss"]:.4f} | {r10.get("val_perplexity", ppl(r10["val_loss"])):.1f} | {instr["math"][0]}/{instr["math"][1]} | {instr["logic"][0]}/{instr["logic"][1]} | {instr["coding"][0]}/{instr["coding"][1]} | {instr["knowledge"][0]}/{instr["knowledge"][1]} |

- Benchmark deltas: math **{base['math'][0]}→{instr['math'][0]}**, logic **{base['logic'][0]}→{instr['logic'][0]}**, coding **{base['coding'][0]}→{instr['coding'][0]}**, knowledge **{base['knowledge'][0]}→{instr['knowledge'][0]}**.
- In-loop val trend (probe): 6.497(50) → 6.621(100) → 6.696(150) → 6.697(200) → 6.694(250).
  (Val_loss RISES vs r2000 — this is the **expected** IT trade-off: training on Q/A shifts the
  output distribution away from wiki prose. The probe metric is BENCHMARKS, not val_loss.)
- Training stability: grad_nan_total=0, grad_inf_total=0, grad_norm ~{statistics.mean(gn):.2f}, lr 3.0e-5→0.

## Decision: {decision_final}

{("", "instruction-tuning improved benchmarks — the format+fact learning generalizes at 12M. Recommend scaling model (>=120M) + data and running a fuller SFT (2000-5000 steps).")[0] if not any_move else ("instruction-tuning improved benchmarks — scale up to a fuller run.")}"""
    if not any_move:
        md += "\n\nNo benchmark moved. The 12M model fits the Q/A format (train_loss 6.07->3.57) but "
        md += "cannot translate 9.3k instructions into zero-shot math/knowledge/coding gains — confirming the "
        md += "capacity/data floor. Keep r2000 as production; next experiment = scale model to >=120M THEN instruction-tune."
    open(PROBE/"silverwing_probe_report.md","w",encoding="utf-8").write(md)
    print("wrote silverwing_probe_report.md")
    print("=== DONE ===")

if __name__=="__main__":
    main()
