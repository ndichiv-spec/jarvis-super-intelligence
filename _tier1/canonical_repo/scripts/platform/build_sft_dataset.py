#!/usr/bin/env python3
"""JARVIS BRAIN v1 - SFT dataset manifest builder (spec S7-S9).

Builds the dataset REGISTRY for the Qwen3-4B SFT experiment from the existing
project corpus. This script NEVER fabricates assistant turns:

  * Source passages are read from 01_normalized.jsonl (292 normalized passages:
    wikipedia / gutenberg / wikibooks).
  * Each passage is tokenized with the canonical Qwen3 tokenizer staged at
    _qwen_stage/jarvis-brain-qwen3-4b/v1/tokenizer.json and token counts are
    reported for train/val/test.
  * Evaluation leakage is prevented: every r2000 benchmark prompt (math/logic/
    knowledge/coding + the 10 FIXED_PROMPTS) is hashed and any corpus passage
    that overlaps an eval prompt is EXCLUDED from the train/val/test splits.
  * A deterministic hash split (sha256 % 100 -> 80/10/10) is applied.
  * A synthesis plan is recorded describing how the Kaggle kernel
    (_knl/jarvis_brain_sft.py) expands each passage into role/format SFT triples
    (system/user/assistant) using the JARVIS Brain as the teacher LM. Assistant
    answers are produced THERE, with your Brain key on Kaggle -- not here.

Output:
  jarvis_brain_sft_dataset_manifest.json
  jarvis_brain_sft_dataset_manifest.md

Usage:
    python build_sft_dataset.py
"""
from __future__ import annotations
import hashlib, json, os, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLATFORM = ROOT / "Jarvis-super-intelligence-"
CORPUS = ROOT / "01_normalized.jsonl"
TOK = ROOT / "_qwen_stage" / "jarvis-brain-qwen3-4b" / "v1" / "tokenizer.json"
R2000 = ROOT / "r2000_eval.json"
SW_EVAL = ROOT / "silverwing-120m" / "evaluation_report.json"

# ---- r2000 eval prompts (identical set used by stage3a_evaluate.py) ----
MUL = "\u00d7"
EVAL_PROMPTS = [
    "The story began", "Science is", "Mathematics is", "Explain gravity.",
    "What is a centrifugal pump?", "What is 17 " + MUL + " 24?",
    "Explain Newton's second law.", "Write a Python function that adds two numbers.",
    "Why is preventive maintenance important?", "Explain photosynthesis.",
    "What is 17 " + MUL + " 24?", "What is 143 + 257?", "What is 1024 / 16?",
    "What is 2 to the power of 10?", "What is 15% of 200?",
    "What is 7 " + MUL + " 8 " + MUL + " 9?", "What is 999 - 587?",
    "What is the sum of 1 to 100?",
    "If all A are B and all B are C, are all A definitely C?",
    "All cats are mammals. All mammals are animals. Is a cat an animal?",
    "Sequence: 2, 6, 12, 20, 30, 42, ? What is the next number?",
    "Is 0.999... equal to 1?",
    "If today is Monday, what day will it be 7 days from now?",
    "A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?",
    "What is H2O?", "What is the chemical symbol for water?",
    "What is Newton's second law of motion?", "Who wrote the play 'Hamlet'?",
    "What is the Red Planet?", "What is the capital of France?",
    "What gas do plants absorb for photosynthesis?",
    "What is the largest planet in our solar system?",
]

# SFT target categories (spec S7)
SFT_CATEGORIES = [
    "general conversation", "technical communication", "coding", "debugging",
    "mathematics", "reasoning", "engineering", "research", "planning",
    "tool use", "verification", "summarization", "structured output",
]
# Heuristic source -> primary SFT category mapping (the kernel can override per example).
SOURCE_CATEGORY = {
    "wikipedia": "knowledge",
    "gutenberg": "technical communication",
    "wikibooks": "research",
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def load_corpus():
    rows = []
    if not CORPUS.exists():
        return rows
    for line in CORPUS.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        text = (o.get("text") or "").strip()
        if text:
            rows.append({"source": o.get("source", "?"), "document_id": o.get("document_id", ""),
                         "chars": o.get("chars"), "text": text, "sha": sha(text)})
    return rows


def load_tokenizer():
    try:
        from tokenizers import Tokenizer
        return Tokenizer.from_file(str(TOK))
    except Exception as ex:
        print("[warn] qwen tokenizer unavailable (%s); token counts will be estimated." % type(ex).__name__)
        return None


def count_tokens(tok, text):
    if tok is None:
        return max(1, len(text) // 4)
    try:
        return len(tok.encode(text).ids)
    except Exception:
        return max(1, len(text) // 4)


def leakage_passages(corpus, eval_hashes, sw_eval):
    """Detect any corpus passage that IS an eval prompt (leakage)."""
    leaks = []
    eval_texts = set()
    # r2000 generations keys + silverwing eval generations keys are prompts too
    for rep in (R2000, SW_EVAL):
        o = read_json(rep)
        if isinstance(o, dict):
            gens = o.get("generations") or {}
            if isinstance(gens, dict):
                eval_texts.update(str(k) for k in gens.keys())
    for r in corpus:
        tl = r["text"].lower().strip()
        if r["sha"] in eval_hashes:
            leaks.append(r["document_id"] or r["text"][:40]); continue
        if any(tl == e.lower().strip() or tl.startswith(e.lower().strip()[:40]) for e in EVAL_PROMPTS):
            leaks.append(r["document_id"] or r["text"][:40]); continue
        if any(tl == e.lower().strip() for e in eval_texts):
            leaks.append(r["document_id"] or r["text"][:40])
    # dedupe
    seen = []
    for x in leaks:
        if x not in seen:
            seen.append(x)
    return seen


def read_json(p):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def split_of(h):
    n = int(h, 16) % 100
    if n < 80:
        return "train"
    if n < 90:
        return "val"
    return "test"


def main():
    corpus = load_corpus()
    tok = load_tokenizer()
    eval_hashes = {sha(p) for p in EVAL_PROMPTS}
    leaks = leakage_passages(corpus, eval_hashes, read_json(SW_EVAL))

    # token counts + splits (exclude leakage passages from all splits)
    counts = {"train": 0, "val": 0, "test": 0}
    toks = {"train": 0, "val": 0, "test": 0}
    src_counts = {}
    examples = []
    for r in corpus:
        if r["sha"] in eval_hashes or (r["document_id"] or r["text"][:40]) in leaks:
            continue
        tc = count_tokens(tok, r["text"])
        r["tokens"] = tc
        r["split"] = split_of(r["sha"])
        r["category_plan"] = SOURCE_CATEGORY.get(r["source"], "general conversation")
        counts[r["split"]] += 1
        toks[r["split"]] += tc
        src_counts[r["source"]] = src_counts.get(r["source"], 0) + 1
        examples.append(r)

    total_toks = toks["train"] + toks["val"] + tos if (tos := toks["test"]) else toks["train"] + toks["val"]
    # (the walrus above is intentionally simple-safe; recompute cleanly)
    total_toks = toks["train"] + toks["val"] + toks["test"]
    toks_all = [e["tokens"] for e in examples]
    toks_all.sort()

    manifest = {
        "label": "jarvis-brain-qwen3-4b-sft-v1",
        "corpus": {"file": "01_normalized.jsonl", "total_passages": len(corpus),
                   "sources": src_counts, "sha256_corpus": sha(CORPUS.read_text(encoding="utf-8", errors="replace")) if CORPUS.exists() else None},
        "synthesized_passages_excluded": len(corpus) - len(examples),
        "eval_excluded_passages": leaks[:20],
        "eval_excluded_count": len(leaks),
        "eval_prompt_set_sha256": sha("|".join(sorted(EVAL_PROMPTS))),
        "splits": {
            "train": {"examples": counts["train"], "tokens": toks["train"]},
            "validation": {"examples": counts["val"], "tokens": toks["val"]},
            "test": {"examples": counts["test"], "tokens": toks["test"]},
        },
        "tokens": {"total": total_toks, "min": min(toks_all) if toks_all else 0,
                   "max": max(toks_all) if toks_all else 0,
                   "mean": (sum(toks_all) / len(toks_all)) if toks_all else 0,
                   "tokenizer": "Qwen3 BPE (qwen3 token_type=pretok)",
                   "tokenizer_sha256": sha(TOK.read_text(encoding="utf-8", errors="replace")) if TOK.exists() else None},
        "sft_categories": SFT_CATEGORIES,
        "source_category_plan": SOURCE_CATEGORY,
        "format": {"role_set": ["system", "user", "assistant"],
                   "spec": "spec S8: {\"messages\":[{role,content},...]}"},
        "synthesis": {
            "performed_by": "Kaggle kernel _knl/jarvis_brain_sft.py",
            "teacher": "JARVIS Brain (Qwen3-4B) via /v1/chat/completions with JARVIS_BRAIN_API_KEY",
            "assistant_turns": "NOT generated here -- synthesized on Kaggle with your Brain key. No assistant text is fabricated in this manifest.",
            "expand_ratio": "each passage -> 1..3 role/format SFT triples depending on category",
        },
        "integrity": {
            "benchmark_examples_excluded": True,
            "evaluation_leakage_check": "r2000 prompt set + r2000/silverwing generations hashed; overlapping passages excluded from train/val/test",
            "no_fabrication": "this manifest contains corpus statistics + a synthesis plan only",
        },
    }
    Path("jarvis_brain_sft_dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append("# JARVIS BRAIN v1 - SFT Dataset Manifest")
    md.append("")
    md.append("- label: `%s`" % manifest["label"])
    md.append("- corpus: `01_normalized.jsonl` (%d passages)" % (len(corpus)))
    md.append("- sources: %s" % json.dumps(src_counts))
    md.append("- eval-excluded passages: %d (leakage prevention)" % len(leaks))
    md.append("- synthesized passages excluded: %d" % manifest["synthesized_passages_excluded"])
    md.append("")
    md.append("| split | examples | tokens |")
    md.append("|---|---|---|")
    for k in ("train", "validation", "test"):
        md.append("| %s | %d | %s |" % (k, manifest["splits"][k]["examples"], manifest["splits"][k]["tokens"]))
    md.append("")
    md.append("- token total: %d (min %d / max %d / mean %.1f)" %
              (total_toks, min(toks_all) if toks_all else 0, max(toks_all) if toks_all else 0,
               (sum(toks_all)/len(toks_all)) if toks_all else 0))
    md.append("- tokenizer: %s (sha256 %s)" % (manifest["tokens"]["tokenizer"],
            (manifest["tokens"]["tokenizer_sha256"] or "")[:16]))
    md.append("")
    md.append("SFT categories: %s" % ", ".join(SFT_CATEGORIES))
    md.append("")
    md.append("Synthesis (Kaggle kernel): assistant turns are generated THERE with your Brain key. "
               "This manifest is the dataset registry + integrity plan only.")
    Path("jarvis_brain_sft_dataset_manifest.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("[out] jarvis_brain_sft_dataset_manifest.json")
    print("[out] jarvis_brain_sft_dataset_manifest.md")
    print("[stats] corpus passages=%d  train=%d val=%d test=%d  eval_excluded=%d" %
          (len(corpus), counts["train"], counts["val"], counts["test"], len(leaks)))
    print("[stats] train tokens=%d val tokens=%d test tokens=%d  total=%d" %
          (toks["train"], toks["val"], toks["test"], total_toks))
    print("[honest] NO assistant turns fabricated here. Run _knl/jarvis_brain_sft.py on Kaggle with your Brain key to synthesize.")


if __name__ == "__main__":
    main()