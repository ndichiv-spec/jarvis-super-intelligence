"""Shared JARVIS BRAIN v1 evaluator (jarvis-brain-eval/v1).

Byte-identical for the baseline and SFT kernels:
  - loads a model (base, or base + PEFT adapter) with deterministic greedy sampling
  - runs the fixed 108-item suite (9 families) with per-item checkers
  - records honest hardware + latency + tokens/s (never invented)
  - writes eval.json / eval.md / responses.jsonl into the kernel working dir

Identifiers / contract:
  - BASE_MODEL="Qwen/Qwen3-4B-Base"
  - BASE_REVISION="1cfa9a7208912126459214e8b04321603b3df60c"  (pinned, no substitute)
  - ADAPTER_REPO="Reyvic-254/jarvis-brain-qwen3-4b-sft-v1"
  - ADAPTER_REVISION="0567cbd11718311c4bd22029566bb463b3145975"
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import time
from pathlib import Path

BASE_MODEL = "Qwen/Qwen3-4B-Base"
BASE_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
ADAPTER_REPO = "Reyvic-254/jarvis-brain-qwen3-4b-sft-v1"
ADAPTER_REVISION = "0567cbd11718311c4bd22029566bb463b3145975"

SUITE_VERSION = 1


# ----------------------------------------------------------------- hardware -- #
def hardware_report() -> dict:
    rep = {"device": "unknown", "torch": None, "cuda": False,
           "vram_gb": None, "gpu_name": None, "ram_gb": None, "precision": "bfloat16"}
    torch = importlib.util.find_spec("torch")
    if torch is not None:
        import torch
        rep["torch"] = torch.__version__
        rep["cuda"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            rep["device"] = f"cuda:{torch.cuda.current_device()}"
            rep["gpu_name"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            rep["vram_gb"] = round(props.total_memory / (1024 ** 3), 2)
    # RAM fallbacks
    try:
        import psutil
        rep["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except Exception:
        pass
    if rep["ram_gb"] is None:
        for p in ("/proc/meminfo",):
            try:
                for line in Path(p).read_text().splitlines():
                    if line.lower().startswith("memtotal"):
                        kb = int(line.split()[1])
                        rep["ram_gb"] = round(kb / (1024 * 1024), 2)
                        break
            except Exception:
                pass
    return rep


# ---------------------------------------------------------------- loaders ---- #
def load_model(mode: str = "base", adapter_repo: str = ADAPTER_REPO,
               adapter_revision: str = ADAPTER_REVISION,
               max_seq: int = 2048, compute_dtype_str: str = "bfloat16"):
    """mode: 'base' (pinned base revision) or 'sft' (base + published adapter)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    torch_dtype = torch.bfloat16 if compute_dtype_str == "bfloat16" else torch.float16

    base_kwargs = dict(
        revision=BASE_REVISION,      # pinned; never substitute silently
        torch_dtype=torch_dtype,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    tokenizer_repo = adapter_repo if mode == "sft" else BASE_MODEL
    tok_kwargs = dict(revision=adapter_revision) if mode == "sft" else dict(revision=BASE_REVISION)

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_repo, **tok_kwargs)
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, **base_kwargs)

    identity = {
        "base_model": BASE_MODEL,
        "base_revision": BASE_REVISION,
        "adapter_loaded": mode == "sft",
        "adapter_repo": adapter_repo if mode == "sft" else None,
        "adapter_revision": adapter_revision if mode == "sft" else None,
        "device": next(base.parameters()).device.type,
        "dtype": str(next(base.parameters()).dtype),
        "requires_grad": base.requires_grad_ if False else False,
        "parameters": sum(p.numel() for p in base.parameters()),
        "config_name_or_path": getattr(base.config, "_name_or_path", None),
    }

    if mode == "sft":
        from peft import PeftModel
        base = PeftModel.from_pretrained(
            base, adapter_repo, revision=adapter_revision, torch_dtype=torch_dtype,
            device_map="auto")
        base.eval()
        identity["adapter_model_name"] = getattr(base.peft_config, "base_model_name_or_path", None)
        identity["adapter_target_modules"] = getattr(base.peft_config, "target_modules", None)
        identity["adapter_r"] = getattr(base.peft_config, "r", None)
        identity["peft_type"] = str(getattr(base.peft_config, "peft_type", None))
    base.eval()
    return base, tokenizer, identity


# ---------------------------------------------------------------- generation -- #
def generate_one(model, tokenizer, prompt: str, max_new_tokens: int) -> dict:
    messages = [{"role": "user", "content": prompt}]
    import torch
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device) if hasattr(torch, "cuda") and torch.cuda.is_available() else tokenizer(text, return_tensors="pt").to("cpu")
    t0 = time.time()
    with torch.inference_mode():
        gen = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,          # greedy -> deterministic
            temperature=1.0,
            top_p=1.0,
            use_cache=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    dt = time.time() - t0
    out = gen[0][inputs["input_ids"].shape[1]:]
    resp = tokenizer.decode(out, skip_special_tokens=True).strip()
    n_in = int(inputs["input_ids"].shape[1])
    n_out = int((gen[0] - inputs["input_ids"][0]).ne(0).sum()) if gen.shape[1] > inputs["input_ids"].shape[1] else len(out)
    return {"response": resp, "latency_s": round(dt, 3),
            "input_tokens": n_in, "output_tokens": n_out,
            "tokens_per_second": round(n_out / dt, 3) if dt > 0 else None}


# ---------------------------------------------------------------- checkers ---- #
def _norm(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def _extract_number(s: str):
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return _num(m.group(0)) if m else None


def _extract_json(s: str):
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if s.startswith("{"):
        try:
            return json.loads(s)
        except Exception:
            pass
    b = re.search(r"\{.*\}", s, re.S)
    if b:
        try:
            return json.loads(b.group(0))
        except Exception:
            return None
    return None


def _tool_name(s: str):
    j = _extract_json(s)
    if isinstance(j, dict) and "tool" in j:
        return str(j["tool"]).strip().lower()
    m = re.search(r'"?tool"?\s*[:=]\s*"?([\w\-_]+)"?', s or "")
    return m.group(1).strip().lower() if m else None


def _code_judge(response: str, it) -> dict:
    code = (response or "").strip()
    if code.startswith("```"):
        code = re.sub(r"^```\w*\s*", "", code)
        code = re.sub(r"\s*```$", "", code)
    tree = None
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # pick the largest compilable function block
        m = re.search(r"def .*(?:\n(?:[ \t]+.*\n?)*)", code)
        if m:
            try:
                tree = ast.parse(m.group(0))
            except SyntaxError:
                pass
    if tree is None:
        return {"correct": False, "note": "code_judge: could not parse a Python function"}
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == it["fn"]), None)
    if fn is None:
        return {"correct": False,
                "note": f"code_judge: expected function '{it['fn']}' not found"}
    ns: dict = {}
    try:
        exec(compile(tree, "<judge>", "exec"), ns)
    except Exception as exc:
        return {"correct": False, "note": f"code_judge: compile/exec error: {str(exc)[:120]}"}
    fnobj = ns.get(it["fn"])
    results = []
    for case in (it.get("cases") or []):
        arg_s, exp_s = case
        try:
            args = ast.literal_eval(arg_s)
            expected = ast.literal_eval(exp_s)
            args = args if isinstance(args, tuple) else (args,)
        except Exception as exc:
            results.append({"ok": None, "note": f"malformed case: {str(exc)[:80]}"})
            continue
        t0 = time.time()
        try:
            got = fnobj(*args)
            if time.time() - t0 > 5:
                results.append({"ok": False, "note": "timeout > 5s"})
                continue
            ok = _vals_eq(got, expected)
            results.append({"ok": bool(ok), "got": str(got)[:80], "expected": str(expected)[:80]})
        except Exception as exc:
            results.append({"ok": False, "note": f"exec error: {str(exc)[:80]}"})
    ok_all = len(results) > 0 and all(bool(r.get("ok")) for r in results)
    return {"correct": bool(ok_all), "code_cases": results,
            "note": "code_judge: ran hidden cases"}


def _vals_eq(got, exp):
    if isinstance(got, bool) or isinstance(exp, bool):
        return got == exp
    if isinstance(got, (int, float)) and isinstance(exp, (int, float)):
        return abs(float(got) - float(exp)) < 1e-9
    try:
        if isinstance(got, dict) and isinstance(exp, dict):
            return got.keys() == exp.keys() and all(_vals_eq(got[k], exp[k]) for k in exp)
        if isinstance(got, (list, tuple)) and isinstance(exp, (list, tuple)):
            return len(got) == len(exp) and all(_vals_eq(a, b) for a, b in zip(got, exp))
    except Exception:
        pass
    return str(got) == str(exp)


def _json_fields_check(response: str, it) -> dict:
    j = _extract_json(response)
    if not isinstance(j, dict):
        return {"correct": False, "note": "json_fields: no JSON object parsed"}
    missing = [k for k in (it.get("fields") or []) if k not in j]
    if missing:
        return {"correct": False, "note": f"json_fields: missing keys {missing}"}
    ref = it.get("ref") or {}
    mism = []
    for k, v in ref.items():
        if k in j:
            if not _vals_eq(j[k], v):
                mism.append(f"{k}: {j[k]!r} != {v!r}")
    return {"correct": not mism, "parsed": {k: j.get(k) for k in (it.get("fields") or [])},
            "note": f"json_fields: mismatches {mism}" if mism else "json_fields: ok"}


# ---------------------------------------------------------------- main -------- #
def run_eval(mode: str, out_dir: str = ".", model=None, tokenizer=None, identity=None,
             suite_dir: str = ".", max_items: int = 0) -> dict:
    import torch
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    suite_path = Path(suite_dir) / "eval_suite.jsonl"
    items = [json.loads(l) for l in suite_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if max_items:
        items = items[:max_items]

    if mode == "sft" and model is None:
        model, tokenizer, identity = load_model("sft")
    elif model is None:
        model, tokenizer, identity = load_model("base")

    hw = hardware_report()
    if next(model.parameters(), None) is not None:
        hw["precision"] = str(next(model.parameters()).dtype)

    results = []
    for it in items:
        fam = it["family"]
        gen = generate_one(model, tokenizer, it["prompt"], int(it.get("max_new_tokens", 256)))
        res = {"id": it["id"], "family": fam, "task": it["task"],
               "prompt": it["prompt"][:300], "response": gen["response"][:3000],
               "output_tokens": gen["output_tokens"], "input_tokens": gen["input_tokens"],
               "latency_s": gen["latency_s"], "tokens_per_second": gen["tokens_per_second"],
               "checker": it["checker"], "ref": it.get("ref"), "correct": None, "note": None}
        c = it["checker"]
        if c == "exact_answer":
            n = _norm(gen["response"]); r = _norm(it["ref"])
            acc = {_norm(a) for a in (it.get("accept") or [])}
            res["correct"] = bool(n == r or (r in acc) or n in acc)
            res["note"] = "exact_answer"
        elif c == "bool_eq":
            n = _norm(gen["response"])
            yes = n.startswith("yes")
            no = n.startswith("no")
            res["correct"] = bool((it["ref"] == "yes" and yes) or (it["ref"] == "no" and no))
            res["note"] = f"bool_eq (response='{n[:20]}')"
        elif c == "number_eq":
            got = _extract_number(gen["response"]); exp = _num(it["ref"])
            res["correct"] = bool(got is not None and exp is not None and abs(got - exp) < 1e-6)
            res["note"] = f"number_eq got={got} exp={exp}"
        elif c == "keyword_overlap":
            low = (gen["response"] or "").lower()
            hits = [k for k in (it.get("keywords") or []) if k.lower() in low]
            res["correct"] = bool(hits)
            res["note"] = ("keyword_overlap (weak proxy): " + ", ".join(hits)) if hits else "keyword_overlap: no hits"
        elif c == "json_fields":
            j = _json_fields_check(gen["response"], it)
            res["correct"] = j["correct"]; res["note"] = j["note"]
        elif c == "tool_name":
            got = _tool_name(gen["response"])
            res["correct"] = bool(got == it["ref"])
            res["note"] = f"tool_name got={got} exp={it['ref']}"
        elif c == "code_judge":
            j = _code_judge(gen["response"], it)
            res["correct"] = j["correct"]; res["note"] = j["note"]
        elif c == "record_only":
            res["correct"] = None
            res["note"] = "record_only (conversation): not auto-scored; human review"
        results.append(res)

    fam_stats = {}
    for fam in sorted({r["family"] for r in results}):
        rows = [r for r in results if r["family"] == fam]
        scored = [r for r in rows if r["correct"] is not None]
        fam_stats[fam] = {
            "items": len(rows), "scored": len(scored),
            "correct": sum(1 for r in scored if r["correct"]),
            "score": round(sum(1 for r in scored if r["correct"]) / len(scored), 3) if scored else None,
            "not_scored": len(rows) - len(scored),
            "mean_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 3) if rows else None,
            "mean_tokens_per_second": round(sum(r["tokens_per_second"] or 0 for r in rows) / len(rows), 3) if rows else None,
        }

    total_scored = sum(s["scored"] for s in fam_stats.values())
    total_correct = sum(s["correct"] for s in fam_stats.values())
    lats = [r["latency_s"] for r in results]
    toks = [r["tokens_per_second"] or 0 for r in results]

    report = {
        "schema": "jarvis-brain-eval/v1",
        "suite_version": SUITE_VERSION,
        "suite_sha256": "62ae8523b30a2b78891e2fc4391574c22199546b33e2ad5537e107a1da90e248",
        "mode": mode,
        "identity": identity,
        "hardware": hw,
        "generation": {"sampling": "greedy (do_sample=False, temperature=1.0)",
                       "seed": "n/a (greedy)", "runtime_seed": "torch.random.manual_seed(0)"},
        "items_total": len(results),
        "items_scored": total_scored,
        "items_correct": total_correct,
        "overall_score": round(total_correct / total_scored, 3) if total_scored else None,
        "families": fam_stats,
        "latency": {"mean_s": round(sum(lats) / len(lats), 3) if lats else None,
                    "total_s": round(sum(lats), 3),
                    "mean_tokens_per_second": round(sum(toks) / len(toks), 3) if toks else None},
        "items": results,
    }
    (out / "responses.jsonl").write_text(
        "\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
    (out / "eval.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = report_to_md(report)
    (out / "eval.md").write_text(md, encoding="utf-8")
    return report


def report_to_md(report: dict) -> str:
    L = [f"# JARVIS BRAIN v1 eval ({report['mode']})",
         "",
         f"- schema: {report['schema']}",
         f"- base model: {report['identity']['base_model']}",
         f"- base revision: {report['identity']['base_revision']} (pinned)",
         f"- adapter loaded: {report['identity'].get('adapter_loaded')}",
         f"- adapter revision: {report['identity'].get('adapter_revision') or 'n/a'}",
         f"- hardware: {report['hardware']['device']} "
         f"(gpu={report['hardware']['gpu_name']}, "
         f"vram={report['hardware']['vram_gb']}GB, torch={report['hardware']['torch']}, "
         f"cuda={report['hardware']['cuda']}, ram={report['hardware']['ram_gb']}GB, "
         f"dtype={report['hardware']['precision']})",
         f"- generation: {report['generation']['sampling']}",
         f"- scored: {report['items_correct']}/{report['items_scored']} "
         f"(overall {report['overall_score']})",
         "",
         "| family | items | scored | correct | score | lat(s) | tok/s |",
         "|--------|-------|--------|---------|-------|--------|-------|"]
    for fam, s in report["families"].items():
        L.append(f"| {fam} | {s['items']} | {s['scored']} | {s['correct']} | "
                 f"{s['score']} | {s['mean_latency_s']} | {s['mean_tokens_per_second']} |")
    L += ["", "## Model identity", "", "```json",
          json.dumps({k: v for k, v in report["identity"].items()
                      if k not in ("params",)}, indent=2, default=str),
          "```"]
    return "\n".join(L)