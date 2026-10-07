#!/usr/bin/env python3
"""JARVIS BRAIN v1 - Qwen3-4B base baseline benchmark (spec S5/S6/S25).

Runs the project's REAL r2000 benchmark (math/logic/knowledge/coding) with the
IDENTICAL scorers used by silverwing's stage3a_evaluate.py, so Qwen3-4B and
Silverwing-120M are compared apples-to-apples.

Columns:
  * Qwen3-4B (jarvis-brain-qwen3-4b-v1) -> via the remote JARVIS Brain, an
    OpenAI-compatible /v1/chat/completions endpoint. Bearer auth uses
    JARVIS_BRAIN_API_KEY resolved through the project secret vault
    (infrastructure.vault.manager) -- never a raw os.environ read, never
    printed, never written to logs.
  * Silverwing-120M + r2000 -> read from the EXISTING local evaluation
    reports (silverwing-120m/evaluation_report.json, r2000_eval.json). These
    are real, already-measured numbers; they are NOT re-run here.

Honesty: if JARVIS_BRAIN_ENDPOINT / JARVIS_BRAIN_API_KEY are not set, the Qwen
column is reported as "unconfigured" -- never fabricated. A network/401
against the Brain is reported as unhealthy, not faked.

Usage:
    python jarvis_brain_baseline.py            # all columns
    python jarvis_brain_baseline.py --brain      # Qwen column only (if configured)
    python jarvis_brain_baseline.py --compare-only # reuse existing reports, no Brain call
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, sys, tempfile, time, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent            # F:\AI
PLATFORM = ROOT / "Jarvis-super-intelligence-"    # jarvis_backend lives here
for _p in (str(ROOT), str(PLATFORM)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx  # noqa: E402

MUL = "\u00d7"
# ---- r2000 benchmark (mirrored from stage3a_evaluate.py) ----
FIXED_PROMPTS = [
    "The story began", "Science is", "Mathematics is", "Explain gravity.",
    "What is a centrifugal pump?", "What is 17 " + MUL + " 24?",
    "Explain Newton's second law.",
    "Write a Python function that adds two numbers.",
    "Why is preventive maintenance important?", "Explain photosynthesis.",
]
MATH_QS = [
    ("What is 17 " + MUL + " 24?", 408), ("What is 143 + 257?", 400),
    ("What is 1024 / 16?", 64), ("What is 2 to the power of 10?", 1024),
    ("What is 15% of 200?", 30), ("What is 7 " + MUL + " 8 " + MUL + " 9?", 504),
    ("What is 999 - 587?", 412), ("What is the sum of 1 to 100?", 5050),
]
LOGIC_QS = [
    ("If all A are B and all B are C, are all A definitely C?", ["yes", "true", "definitely", "correct"]),
    ("All cats are mammals. All mammals are animals. Is a cat an animal?", ["yes", "true", "definitely"]),
    ("Sequence: 2, 6, 12, 20, 30, 42, ? What is the next number?", [str(n) for n in range(1, 200)]),
    ("Is 0.999... equal to 1?", ["yes", "equal", "true"]),
    ("If today is Monday, what day will it be 7 days from now?", ["monday"]),
    ("A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?", ["0.05", "5 cents", "5c", "$0.05"]),
]
KNOW_QS = [
    ("What is H2O?", ["water"]),
    ("What is the chemical symbol for water?", ["H2O", "H\u2082O", "h2o"]),
    ("What is Newton's second law of motion?", ["force", "mass", "acceleration", "f = ma", "f=ma"]),
    ("Who wrote the play 'Hamlet'?", ["shakespeare"]),
    ("What is the Red Planet?", ["mars"]),
    ("What is the capital of France?", ["paris"]),
    ("What gas do plants absorb for photosynthesis?", ["carbon dioxide", "co2"]),
    ("What is the largest planet in our solar system?", ["jupiter"]),
]
CODE_QS = [
    ("Write a Python function add(a, b) that returns a + b.\n```python\n", "add", "add(2, 3) == 5 and add(-1, 1) == 0"),
    ("Write a Python function factorial(n) returning n!.\n```python\n", "factorial", "factorial(5) == 120 and factorial(0) == 1"),
    ("Write a Python function is_palindrome(s) that returns True if s reads the same forwards and backwards.\n```python\n", "is_palindrome", "is_palindrome('racecar') and not is_palindrome('hello')"),
]
SYSTEM = "You are JARVIS Brain (Qwen3-4B). Answer concisely and precisely."
TIMEOUT = 120.0


def first_int(s):
    m = re.search(r"-?\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None


def kw_match(out, kws):
    o = (out or "").lower()
    return any(k.lower() in o for k in kws)


def extract_py(text):
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    i = text.find("def ")
    if i == -1:
        return ""
    lines = text[i:].split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            break
        out.append(ln)
    return "\n".join(out)


def run_code_check(code, test_expr):
    """Execute model-generated code in a sandboxed subprocess with a timeout."""
    if not code.strip():
        return False
    payload = "code = " + repr(code) + "\n"
    payload += "test_expr = " + repr(test_expr) + "\n"
    payload += "try:\n    exec(code, globals())\n    print('OK=' + repr(eval(test_expr)))\n"
    payload += "except Exception as e:\n    print('ERR=' + repr(e))\n"
    try:
        with tempfile.NamedTemporaryFile("w", suffix="_chk.py", delete=False, encoding="utf-8") as f:
            f.write(payload); path = f.name
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        os.unlink(path)
        return r.returncode == 0 and "OK=" in (r.stdout or "")
    except Exception:
        return False


async def brain_chat(endpoint, key, model, prompt, temperature, max_tokens, top_p):
    url = endpoint.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature, "max_tokens": max_tokens, "top_p": top_p}
    t0 = time.time()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 401:
            raise PermissionError("Brain rejected API key (HTTP 401)")
        r.raise_for_status()
        j = r.json()
    content = j["choices"][0]["message"]["content"]
    usage = j.get("usage", {})
    return {"content": content, "latency_ms": ms, "usage": usage}


async def run_qwen_brain(endpoint, key, model):
    results = {"status": "measured", "endpoint": endpoint, "model": model,
               "config_source": "vault:infrastructure.vault.manager",
               "categories": {}, "generations": {}, "latency_ms_total": 0,
               "n_requests": 0, "errors": []}
    for p in FIXED_PROMPTS:
        try:
            r = await brain_chat(endpoint, key, model, p, 0.8, 64, 0.9)
            results["generations"][p] = r["content"]
            results["latency_ms_total"] += r["latency_ms"]
            results["n_requests"] += 1
        except Exception as e:
            results["generations"][p] = "[ERROR " + type(e).__name__ + ": " + str(e)[:120] + "]"
            results["errors"].append({"prompt": p, "error": type(e).__name__})
    ok = 0; det = []
    for q, exp in MATH_QS:
        try:
            out = (await brain_chat(endpoint, key, model, "Q: " + q + "?", 0.5, 40, 0.95))["content"]
            results["n_requests"] += 1
            got = first_int(out)
            passed = got is not None and got == exp
            ok += int(passed)
            det.append({"q": q, "expected": exp, "got": got, "passed": passed})
        except Exception as e:
            results["errors"].append({"q": q, "error": type(e).__name__})
            det.append({"q": q, "expected": exp, "got": None, "passed": False})
    results["categories"]["math"] = {"correct": ok, "total": len(MATH_QS), "accuracy": ok / len(MATH_QS), "details": det}
    ok = 0; det = []
    for q, kws in LOGIC_QS:
        out = (await brain_chat(endpoint, key, model, "Q: " + q + "?", 0.5, 40, 0.95))["content"]
        results["n_requests"] += 1
        p = kw_match(out, kws); ok += int(p); det.append({"q": q, "passed": p, "snippet": out[:80]})
    results["categories"]["logic"] = {"correct": ok, "total": len(LOGIC_QS), "accuracy": ok / len(LOGIC_QS), "details": det}
    ok = 0; det = []
    for q, kws in KNOW_QS:
        out = (await brain_chat(endpoint, key, model, "Q: " + q, 0.5, 40, 0.95))["content"]
        results["n_requests"] += 1
        p = kw_match(out, kws); ok += int(p); det.append({"q": q, "passed": p, "snippet": out[:80]})
    results["categories"]["knowledge"] = {"correct": ok, "total": len(KNOW_QS), "accuracy": ok / len(KNOW_QS), "details": det}
    ok = 0; det = []
    for q, fname, test in CODE_QS:
        out = (await brain_chat(endpoint, key, model, q + "\n", 0.5, 120, 0.95))["content"]
        results["n_requests"] += 1
        code = extract_py(out)
        p = run_code_check(code, test); ok += int(p)
        det.append({"prompt": q.strip(), "passed": p, "extracted_len": len(code)})
    results["categories"]["coding"] = {"correct": ok, "total": len(CODE_QS), "accuracy": ok / len(CODE_QS), "details": det}
    return results


def read_report(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def column_from_report(rep):
    if not rep:
        return None
    cats = {}
    for k in ("math", "logic", "knowledge", "coding"):
        v = rep.get(k)
        if isinstance(v, dict):
            cats[k] = {"correct": v.get("correct"), "total": v.get("total"), "accuracy": v.get("accuracy")}
    return {"label": rep.get("label"), "param_count": rep.get("param_count"),
            "val_loss": rep.get("val_loss"), "val_perplexity": rep.get("val_perplexity"),
            "categories": cats, "generations": rep.get("generations"),
            "checkpoint": rep.get("checkpoint"), "model_sha256": rep.get("model_sha256")}


def write_md(report, path):
    lines = ["# JARVIS BRAIN v1 - Qwen3-4B Baseline"]
    lines.append("")
    lines.append("- status: %s" % report["status"])
    lines.append("- endpoint: %s" % (report.get("endpoint") or "(unset)"))
    lines.append("- model: %s" % report.get("model"))
    lines.append("- api key: resolved via secret vault (%s); value: [REDACTED]" % report.get("config_source", "env"))
    lines.append("- requests: %s" % report.get("n_requests", 0))
    lines.append("- latency total: %s ms" % report.get("latency_ms_total", 0))
    lines.append("")
    lines.append("| category | correct | total | accuracy |")
    lines.append("|---|---|---|---|")
    for k, v in report.get("categories", {}).items():
        lines.append("| %s | %s | %s | %s |" % (k, v.get("correct"), v.get("total"), v.get("accuracy")))
    lines.append("")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", action="store_true")
    ap.add_argument("--compare-only", action="store_true")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(str(ROOT / ".env"), override=False)
    except Exception as ex:
        print("[warn] python-dotenv unavailable (%s); env-only config" % type(ex).__name__)
    try:
        import _env as e
        e.apply()
    except Exception as ex:
        print("[warn] _env.apply() failed (%s)" % type(ex).__name__)

    from jarvis_backend.gateway import (_jarvis_brain_endpoint, _jarvis_brain_api_key,
                                        _jarvis_brain_api_key_configured)
    from jarvis_backend.core import admin_email

    endpoint = _jarvis_brain_endpoint()
    key_ok = _jarvis_brain_api_key_configured()
    model = os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1")
    print("[env] JARVIS_ADMIN_EMAIL =", admin_email())
    print("[env] JARVIS_BRAIN_ENDPOINT =", repr(endpoint or "(unset)"))
    print("[env] JARVIS_BRAIN_MODEL =", repr(model))
    print("[env] JARVIS_BRAIN_API_KEY configured =", key_ok, " value: [REDACTED]")

    if args.compare_only:
        qwen = {"status": "skipped", "endpoint": endpoint or None, "model": model,
                "categories": {}, "generations": {}, "note": "--compare-only"}
    elif key_ok and endpoint:
        try:
            qwen = asyncio.run(run_qwen_brain(endpoint, _jarvis_brain_api_key(), model))
        except Exception as ex:
            qwen = {"status": "error", "endpoint": endpoint, "model": model,
                    "categories": {}, "generations": {},
                    "error": type(ex).__name__ + ": " + str(ex)[:200]}
    else:
        qwen = {"status": "unconfigured", "endpoint": endpoint or None, "model": model,
                "categories": {}, "generations": {}, "config_source": "vault:infrastructure.vault.manager",
                "detail": ("JARVIS_BRAIN_ENDPOINT and/or JARVIS_BRAIN_API_KEY not set. "
                           "Set them in F:/AI/.env (never commit a real key) or inject via env, then re-run.")}

    sw = column_from_report(read_report(ROOT / "silverwing-120m/evaluation_report.json"))
    r2 = column_from_report(read_report(ROOT / "r2000_eval.json"))

    Path("qwen3_4b_baseline.json").write_text(json.dumps(qwen, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(qwen, "qwen3_4b_baseline.md")
    print("[out] qwen3_4b_baseline.json / .md  (status=%s)" % qwen["status"])

    comparison = {
        "purpose": "JARVIS BRAIN v1 - Qwen3-4B baseline vs Silverwing-120M vs r2000 (identical r2000 benchmark).",
        "benchmark_source": "stage3a_evaluate.py (FIXED_PROMPTS + MATH/LOGIC/KNOW/CODE_QS)",
        "fairness": ("Qwen column is scored with the SAME scorers (first_int / keyword / exec-subprocess) "
                     "as Silverwing. Silverwing/r2000 columns are real existing reports, not re-run. "
                     "No results are fabricated: an unconfigured Brain is reported as 'unconfigured'."),
        "columns": {"qwen3_4b_v1": qwen, "silverwing_120m_pilot": sw, "r2000": r2},
        "env": {"JARVIS_ADMIN_EMAIL": admin_email(), "JARVIS_BRAIN_MODEL": model,
                "brain_endpoint_set": bool(endpoint), "brain_api_key_configured": key_ok},
    }
    Path("jarvis_brain_comparison.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[out] jarvis_brain_comparison.json")
    if qwen["status"] == "unconfigured":
        print("[honest] Qwen baseline NOT measured: Brain not configured. Set JARVIS_BRAIN_ENDPOINT + JARVIS_BRAIN_API_KEY and re-run.")


if __name__ == "__main__":
    main()