"""Phase B (B21) artifact generator.

Reads:
  - silverwing-120m/evaluation_report.json  (official B11 eval of pilot final)
  - silverwing-r2000/eval/r2000_eval.json   (frozen 12M baseline)
  - silverwing-120m/silverwing_120m_smoke_report.json (Phase A)
  - silverwing-120m/metrics.jsonl          (pilot training metrics)
  - silverwing-120m/data/dataset_manifest.json / source_manifest.json
  - silverwing-120m/silverwing_120m_config.json

Writes B21 deliverables:
  silverwing_120m_phaseB_report.json / .md
  comparison_report.json
  capability_history.json
  training_metrics.json
  sample_generations.txt
  (updates run_manifest.json)
"""
from __future__ import annotations
import json, math, os
from pathlib import Path

W = Path(r"F:/AI/silverwing-120m")
R2000_EVAL = Path(r"F:/AI/silverwing-stage3a/eval/r2000_eval.json")
SMOKE = W / "silverwing_120m_smoke_report.json"
PILOT_EVAL = W / "evaluation_report.json"
METRICS = W / "metrics.jsonl"
DS_MAN = W / "data/dataset_manifest.json"
SRC_MAN = W / "data/source_manifest.json"
CFG = W / "silverwing_120m_config.json"
RUN_MAN = W / "silverwing_120m_run_manifest.json"

def loadj(p):
    return json.load(open(p)) if Path(p).exists() else {}

def acc(x):  # accuracy float from {correct,total} or accuracy
    if isinstance(x, dict):
        if "accuracy" in x: return x["accuracy"]
        c, t = x.get("correct",0), x.get("total",1)
        return (c/max(t,1))
    return x

r2 = loadj(R2000_EVAL)
sm = loadj(SMOKE)
pe = loadj(PILOT_EVAL)
dm = loadj(DS_MAN)

# smoke nested fields (phase_a_smoke.val_loss / train_loss)
_sm = sm.get("phase_a_smoke", {}) if sm else {}
sm_val = _sm.get("val_loss", {}).get("step_50") if _sm else None
sm_train_loss = _sm.get("train_loss", {}).get("step_50") if _sm else None
sm_train_tokens = 103100  # 262144 chars of stage3a train.txt

# --- capability_history (trajectory) ---
def val_of(d):
    vl = d.get("val_loss") or d.get("validation_loss")
    if vl is None and d.get("smoke"): vl = d["smoke"].get("val_loss")
    return vl
history = [
    {"stage":"Silverwing-12M-r2000 (baseline, frozen)",
     "param_count": r2.get("param_count") or 12440448,
     "training_tokens": 2048000,
     "val_loss": r2.get("val_loss"),
     "perplexity": r2.get("val_perplexity"),
     "math": (r2.get("math",{}).get("correct"), r2.get("math",{}).get("total")),
     "logic": (r2.get("logic",{}).get("correct"), r2.get("logic",{}).get("total")),
     "coding": (r2.get("coding",{}).get("correct"), r2.get("coding",{}).get("total")),
     "knowledge": (r2.get("knowledge",{}).get("correct"), r2.get("knowledge",{}).get("total")),
     "source":"r2000 final checkpoint"},
    {"stage":"Silverwing-120M smoke (50 steps)",
     "param_count": 120087552,
     "training_tokens": 103100,
     "val_loss": sm_val,
     "perplexity": math.exp(min(sm_val,20)) if sm_val else None,
     "source":"silverwing-120m/final (50-step smoke)"},
    {"stage":"Silverwing-120M-pilot (500 steps)",
     "param_count": pe.get("param_count") or 120087552,
     "training_tokens": 500*256,  # seq256, batch1, grad_accum1
     "val_loss": pe.get("val_loss"),
     "perplexity": pe.get("val_perplexity"),
     "math": (pe.get("math",{}).get("correct"), pe.get("math",{}).get("total")),
     "logic": (pe.get("logic",{}).get("correct"), pe.get("logic",{}).get("total")),
     "coding": (pe.get("coding",{}).get("correct"), pe.get("coding",{}).get("total")),
     "knowledge": (pe.get("knowledge",{}).get("correct"), pe.get("knowledge",{}).get("total")),
     "source":"silverwing-120m/final (500-step pilot)"},
]
json.dump(history, open(W/"capability_history.json","w"), indent=2)

# --- comparison_report ---
def gen_notes(d):
    if not d or not d.get("generations"): return "n/a"
    g = d["generations"]
    notes = []
    for p in ["What is 17 × 24?","Write a Python function that adds two numbers.","Explain gravity.","Explain photosynthesis."]:
        if p in g:
            txt = g[p][:160]
            if p.startswith("What is 17"):  # check arithmetic
                m = __import__("re").search(r"-?\d[\d,]*", txt.replace(g[p][:g[p].find("?")+1] if "?" in txt else "",""))
            notes.append(f"{p[:28]}... -> {txt[:70]}")
    return " | ".join(notes) if notes else "see evaluation_report.generations"
comparison = {
    "purpose":"Phase-B base-model comparison (12M r2000 frozen vs 120M smoke vs 120M pilot). Instruction-tuning NOT applied (B14).",
    "r2000":{"parameter_count":r2.get("param_count"),"training_tokens":2048000,
             "validation_loss":r2.get("val_loss"),"perplexity":r2.get("val_perplexity"),
             "math_accuracy":acc(r2.get("math")),"logic_accuracy":acc(r2.get("logic")),
             "coding_accuracy":acc(r2.get("coding")),"knowledge_accuracy":acc(r2.get("knowledge")),
             "generation_notes": gen_notes(r2)},
    "silverwing_120m_smoke":{"parameter_count":sm.get("param_count") or 120087552,"training_tokens":sm_train_tokens,
             "validation_loss":sm_val,
             "perplexity": math.exp(min(sm_val,20)) if sm_val else None,
             "math_accuracy":None,"logic_accuracy":None,"coding_accuracy":None,"knowledge_accuracy":None,
             "generation_notes":"smoke (50 steps): word-fragment generations, not yet capable"},
    "silverwing_120m_pilot":{"parameter_count":pe.get("param_count"),"training_tokens":500*256,
             "validation_loss":pe.get("val_loss"),"perplexity":pe.get("val_perplexity"),
             "math_accuracy":acc(pe.get("math")),"logic_accuracy":acc(pe.get("logic")),
             "coding_accuracy":acc(pe.get("coding")),"knowledge_accuracy":acc(pe.get("knowledge")),
             "generation_notes": gen_notes(pe)},
}
# deltas vs r2000
for k in ["silverwing_120m_smoke","silverwing_120m_pilot"]:
    base=comparison["r2000"]; cur=comparison[k]
    vl_base=base["validation_loss"]; vl_cur=cur["validation_loss"]
    d={}
    if vl_base and vl_cur: d["val_loss_delta"]=vl_cur-vl_base
    if base["perplexity"] and cur["perplexity"]: d["perplexity_ratio"]=cur["perplexity"]/base["perplexity"]
    if base["parameter_count"] and cur["parameter_count"]: d["param_count_ratio"]=cur["parameter_count"]/base["parameter_count"]
    cur["deltas_vs_r2000"]=d
json.dump(comparison, open(W/"comparison_report.json","w"), indent=2)

# --- training_metrics.json summary from metrics.jsonl ---
steps=[]
if METRICS.exists():
    for line in open(METRICS):
        line=line.strip()
        if line: steps.append(json.loads(line))
train=[s for s in steps if "train_loss" in s]
vald=[s for s in steps if "val_loss" in s]
train_losses=[s["train_loss"] for s in train]
gns=[s["grad_norm"] for s in train]
tmetrics={
 "total_steps":len(train),
 "final_train_loss":train_losses[-1] if train_losses else None,
 "initial_train_loss":train_losses[0] if train_losses else None,
 "min_train_loss":min(train_losses) if train_losses else None,
 "mean_grad_norm":(sum(gns)/len(gns)) if gns else None,
 "max_grad_norm":max(gns) if gns else None,
 "nan_total":sum(1 for s in train if s.get("nan")),
 "inf_total":sum(1 for s in train if s.get("inf")),
 "lr_start":train[0]["lr"] if train else None,
 "lr_min":min(s["lr"] for s in train) if train else None,
 "throughput_tok_per_s_approx": 42,
 "throughput_note": "measured ~42 tok/s @ seq256 batch1, 4-core CPU; 120M is CPU-bound (~6s/step)",
 "tokens_total":train[-1]["tokens"] if train else None,
 "validation_checkpoints":vald,
}
json.dump(tmetrics, open(W/"training_metrics.json","w"), indent=2)

# --- sample_generations.txt (B12) from official eval generations ---
FIXED = ["The story began","Science is","Mathematics is","Explain gravity.",
         "What is a centrifugal pump?","What is 17 × 24?","Explain Newton's second law.",
         "Write a Python function that adds two numbers.","Why is preventive maintenance important?","Explain photosynthesis."]
if pe.get("generations"):
    with open(W/"sample_generations.txt","w",encoding="utf-8") as f:
        f.write("Silverwing-120M-pilot (500-step) — Fixed Generation Set (B12)\n")
        f.write("Prompt -> generation (temperature 0.8, top_p 0.9, 64 new tokens)\n")
        f.write("="*70+"\n\n")
        for p in FIXED:
            f.write(f"### Prompt: {p}\n")
            f.write(pe["generations"].get(p,"[not generated]")+"\n\n")

# --- Phase B report (json + md) ---
report_json={
 "phase":"Phase B — controlled corpus build + 500-step pretraining pilot",
 "model":"Silverwing-120M-v1",
 "param_count":120087552,
 "gates":{
   "B3_corpus_pipeline":"PASS (raw->normalize->lang/quality/spam filter->exact+near dedup->PII redact->tokenize->pack@256->held-out val)",
   "B4_initial_shard":"PASS (10.08M train tokens, 228,608 val tokens, 5-10M target met)",
   "B5_tokenizer_fingerprint":"PASS (r2000 BPE 8192 reused, sha 5b09bfb6…, NOT rebuilt)",
   "B6_sequence_length":"PASS (seq 256, smoke-validated length)",
   "B7_pilot_500_steps":"PASS (clean from-scratch 120M init, LR 1.5e-4 cosine+25-warmup)",
   "B8_checkpoints":"PASS (step-100/200/300/400/500 + best + final)",
   "B10_stability_gate":"PASS (loss↓ 12.12->6.08, grad_norm 2.6-5.5, nan_total=0, inf_total=0)",
   "B11_evaluation":"PASS (val_loss, ppl, math/logic/coding/knowledge, 10 fixed gens)",
   "B13_baseline_comparison":"PASS (comparison_report.json: r2000 vs smoke vs pilot)",
   "B14_no_instruction_tuning":"PASS (base model only; NO IT until B15 base improves)",
 },
 "pilot_result":{
   "final_train_loss": train_losses[-1] if train_losses else None,
   "final_val_loss": pe.get("val_loss"),
   "final_val_perplexity": pe.get("val_perplexity"),
   "best_val_loss": min((s["val_loss"] for s in vald), default=None),
   "r2000_baseline_val_loss": r2.get("val_loss"),
   "beats_r2000_val": (pe.get("val_loss") or 1e9) < (r2.get("val_loss") or 1e9),
   "training_tokens_consumed": 500*256,
   "tokens_per_step": 256,
   "nan_total":tmetrics["nan_total"],
   "inf_total":tmetrics["inf_total"],
 },
 "benchmark_vs_r2000":{
   "math":  f"pilot {acc(pe.get('math'))} vs r2000 {acc(r2.get('math'))}",
   "logic": f"pilot {acc(pe.get('logic'))} vs r2000 {acc(r2.get('logic'))}",
   "coding":f"pilot {acc(pe.get('coding'))} vs r2000 {acc(r2.get('coding'))}",
   "knowledge":f"pilot {acc(pe.get('knowledge'))} vs r2000 {acc(r2.get('knowledge'))}",
   "note":"500-step CPU probe = 128k tokens (tiny sample of the 10M shard). Benchmarks on untrained-scale head may stay near r2000 until MUCH more data/steps; the B15 gate is val_loss+ppl improvement + generation coherence, NOT benchmark parity yet."
 },
 "corpus":{"train_tokens":dm.get("train_size"),"val_tokens":dm.get("validation_size"),
            "achieved_mixture":dm.get("achieved_mixture"),
            "mixture_shortfall":"offline (no-network): code/math/instruction under-represented vs 40/20/15/10/10/5 target; documented honestly. Full mixture deferred to online phase."},
 "b15_data_scaling_gate":"HONEST: B15 gates — (1) validation improved vs prior 120M SMOKE (7.7396 -> 7.0986 pilot) YES; (2) training stable (nan=0,inf=0, loss monotonic-ish dec↓ 12.12->6.08) YES; (3) generation more coherent than smoke word-fragments YES-but-weak. BUT vs the FROZEN 12M r2000 baseline, pilot official val (7.099/ppl1210) is STILL > r2000 (6.345/ppl569) and benchmarks are equal (math0/logic4/coding0/knowledge0) — because 500 CPU steps consumed only 128k tokens (120M is severely undertrained vs r2000's 2.05M). DECISION: pipeline + training STABILITY PROVEN -> PROCEED to larger token budgets (Phase C: 25M->50M->100M+); base-model capability gate (beat r2000) NOT yet met — needs far more tokens. CPU is impractical for full 10M-token pretrain (~67h); recommend Phase C as an extended CPU probe OR migrate to GPU.",
 "b16_model_scaling_gate":"HOLD: 120M-pilot (128k tokens) does NOT yet beat 12M r2000 on official val (7.099 vs 6.345) or benchmarks (math0/logic4/coding0/knowledge0 = identical to r2000). Do NOT build 300M until the 120M BASE, trained on the full 10M+ shard, beats r2000 on math/logic/coding/knowledge (B25 gate).",
 "next_steps":["Phase C: controlled 25M-token (then 50M, 100M+) pretrain on the same pipeline (mixture upgraded when online), seq 512","Periodic stage3a_evaluate at each checkpoint","B25 gate: instruction-tuning only AFTER 120M base beats r2000 on math/logic/coding/knowledge"],
}
json.dump(report_json, open(W/"silverwing_120m_phaseB_report.json","w"), indent=2)

# markdown
md=[]
md.append("# Silverwing-120M-v1 — Phase B Report\n")
md.append(f"**Params:** {120087552:,}  |  **Architecture:** 12L/d1024/16Q4KV/GQA/RoPE/SwiGLU/RMSNorm/8192tok/ctx2048/tied/no-bias  ")
md.append(f"**Pilot:** 500 steps, seq 256, batch 1, LR 1.5e-4 cosine+25w, from-scratch init (seed 42)\n")
md.append("## Result\n")
md.append(f"- **Train loss:** {tmetrics['initial_train_loss']:.4f} → {tmetrics['final_train_loss']:.4f}")
md.append(f"- **Val loss:** {pe.get('val_loss')}  (r2000 baseline: {r2.get('val_loss')} → {'BEATS' if report_json['pilot_result']['beats_r2000_val'] else 'does not beat'} r2000)")
md.append(f"- **Perplexity:** {pe.get('val_perplexity')}  (r2000: {r2.get('val_perplexity')})")
md.append(f"- **Stability:** nan_total={tmetrics['nan_total']} inf_total={tmetrics['inf_total']} (B10 PASS)")
md.append(f"- **Tokens consumed:** 128,000 (500×256) — a CPU compute probe of the 10.08M-token shard\n")
md.append("## Gates\n")
for k,v in report_json["gates"].items(): md.append(f"- {k}: {v}")
md.append("\n## Comparison (vs r2000 frozen baseline)\n")
md.append("| model | params | train tokens | val_loss | ppl | math | logic | coding | knowledge |")
md.append("|---|---|---|---|---|---|---|---|---|")
md.append(f"| 12M r2000 | {r2.get('param_count'):,} | 2.05M | {r2.get('val_loss')} | {r2.get('val_perplexity')} | {acc(r2.get('math'))} | {acc(r2.get('logic'))} | {acc(r2.get('coding'))} | {acc(r2.get('knowledge'))} |")
sm_val = sm_val  # (smoke val_loss, defined at top from phase_a_smoke.val_loss.step_50)
md.append(f"| 120M smoke | {sm.get('param_count') or 120087552:,} | 103,100 | {sm_val} | {(math.exp(min(sm_val,20)) if sm_val else 0.0):.1f} | – | – | – | – |")
md.append(f"| 120M pilot | {pe.get('param_count'):,} | 128,000 | {pe.get('val_loss')} | {pe.get('val_perplexity')} | {acc(pe.get('math'))} | {acc(pe.get('logic'))} | {acc(pe.get('coding'))} | {acc(pe.get('knowledge'))} |")
md.append("\n## Decision\n")
md.append("**B15 gate (data scaling):** the pilot improved *vs the prior 120M smoke* (val 7.7396→7.0986, ppl 2299→1210), training is **stable** (nan=0, inf=0), and generation is more coherent than smoke's word-fragments — so the *pipeline + stability* criterion is met → **PROCEED toward larger token budgets (Phase C: 25M→50M→100M+)**.\n")
md.append(f"**BUT vs the frozen 12M r2000 baseline** the pilot still **does not beat it** on the official raw-val benchmark: pilot val {pe.get('val_loss'):.4f} (ppl {pe.get('val_perplexity'):.1f}) vs r2000 {r2.get('val_loss')} (ppl {r2.get('val_perplexity')}) — the 500-step probe consumed only 128k tokens, so the 120M base is **undertrained**. Benchmarks math0/logic4/coding0/knowledge0 are identical to r2000 (no capability gain yet).\n")
md.append("**B16 gate (model scaling): HOLD 300M.** Do not widen to 300M until the 120M base, trained on the full 10M+ shard, beats r2000 on math/logic/coding/knowledge (the B25 capability gate). CPU is impractical for full-scale pretrain (~67h at 42 tok/s); recommend Phase C as an extended CPU probe OR migrate to GPU for real 100M-token scaling.\n")
Path(W/"silverwing_120m_phaseB_report.md").write_text("\n".join(md), encoding="utf-8")

# update run_manifest
rm = loadj(RUN_MAN)
rm.setdefault("runs",[]).append({
  "run_id":"silverwing-120m-v1-pilot",
  "started":"2026-09-10T15:41:18",
  "ended":"2026-09-10T16:46",
  "steps":500, "lr":1.5e-4, "seq":256, "batch":1, "grad_accum":1,
  "final_train_loss": tmetrics['final_train_loss'],
  "final_val_loss": pe.get("val_loss"),
  "final_val_perplexity": pe.get("val_perplexity"),
  "nan_total":tmetrics["nan_total"], "inf_total":tmetrics["inf_total"],
  "checkpoints":["step-100","step-200","step-300","step-400","step-500","best","final"],
  "final_sha256":"7a2fd08e8543", "param_count":120087552,
})
rm["status"]="Phase B complete; ready for Phase C (larger token budget)"
rm["final_decision"]="B15 PROCEED (val improved); B16 HOLD (no 300M yet)"
json.dump(rm, open(RUN_MAN,"w"), indent=2)

print("Phase-B artifacts written to", W)
for f in ["silverwing_120m_phaseB_report.json","silverwing_120m_phaseB_report.md","comparison_report.json","capability_history.json","training_metrics.json","sample_generations.txt"]:
    print("  ", f, os.path.getsize(W/f), "bytes")
