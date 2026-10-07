"""Stage 3A --- Stage 4: Evaluation harness.

Loads a Silverwing checkpoint, runs:
  * validation loss/perplexity on the COMMON held-out val set (data_pipeline
    val.txt) so r2000 and r3000 are compared apples-to-apples,
  * the 10 fixed generation prompts (temperature 0.8, top_p 0.9, 64 new tokens),
  * a small but REAL benchmark suite (math/logic/coding/knowledge) where every
    score comes from actually executing or parsing the model's own output.

Usage: python stage3a_evaluate.py --ckpt <dir> --label <r2000|r3000> --out <json>
"""
from __future__ import annotations
import argparse, json, math, re, os, sys, traceback
from pathlib import Path

# Kaggle kernel VM: silverwing_train.py, the r2000 tokenizer and the common
# val.txt are staged into /kaggle/working by the notebook (cell 3). Fall back to
# the author host's local F:\AI paths when running offline.
import os as _os
KAGGLE_WK = "/kaggle/working"
TRAIN_DIR_LOCAL  = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
R2000_TOK_LOCAL  = r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json"
COMMON_VAL_LOCAL = r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/val.txt"

def _wk(name):
    return _os.path.exists(_os.path.join(KAGGLE_WK, name))

TRAIN_DIR  = KAGGLE_WK if _wk("silverwing_train.py") else TRAIN_DIR_LOCAL
R2000_TOK  = (KAGGLE_WK + "/r2000_tokenizer.json") if _wk("r2000_tokenizer.json") else R2000_TOK_LOCAL
COMMON_VAL = (KAGGLE_WK + "/val.txt") if _wk("val.txt") else COMMON_VAL_LOCAL

sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw  # noqa: E402
import torch  # noqa: E402
from safetensors.torch import load_file  # noqa: E402

DEVICE = torch.device("cpu")
MAX_LEN = 256  # matches training seq_len

FIXED_PROMPTS = [
    "The story began", "Science is", "Mathematics is", "Explain gravity.",
    "What is a centrifugal pump?", "What is 17 × 24?",
    "Explain Newton's second law.",
    "Write a Python function that adds two numbers.",
    "Why is preventive maintenance important?", "Explain photosynthesis.",
]

# ---------------- benchmarks (real checks) ----------------
MATH_QS = [
    ("What is 17 × 24?", 408),
    ("What is 143 + 257?", 400),
    ("What is 1024 / 16?", 64),
    ("What is 2 to the power of 10?", 1024),
    ("What is 15% of 200?", 30),
    ("What is 7 × 8 × 9?", 504),
    ("What is 999 - 587?", 412),
    ("What is the sum of 1 to 100?", 5050),
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
    ("What is the chemical symbol for water?", ["H2O", "H₂O", "h2o"]),
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

def first_int(s):
    m = re.search(r"-?\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None

def gen(model, tok, prompt, max_new=64, temperature=0.8, top_p=0.9):
    ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
    with torch.no_grad():
        g = model.generate(ids, max_new_tokens=max_new, temperature=temperature, top_p=top_p)
    return tok.decode(g[0].tolist())

def extract_py(text):
    """Extract a python code block (or a def block) from generated text."""
    # prefer fenced block
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # fall back: from first 'def ' to a blank line run or end
    i = text.find("def ")
    if i == -1:
        return ""
    head = text[i:]
    lines = head.split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            break
        out.append(ln)
    return "\n".join(out)

def run_code_check(code, test_expr, fname):
    try:
        ns = {}
        exec(code, ns)
        r = eval(test_expr, ns)
        return bool(r)
    except Exception:
        return False

def evaluate(model, tok, label):
    res = {"label": label, "param_count": model.num_parameters()}

    # ---- common val loss / ppl (128 windows x 257 tokens ~ 33k tokens) ----
    val_text = Path(COMMON_VAL).read_text(encoding="utf-8", errors="replace")
    val_ids = tok.encode(val_text)
    windows = 128
    n = min(len(val_ids), (MAX_LEN + 1) * windows)
    vloss = 0.0; vcount = 0
    with torch.no_grad():
        for i in range(0, n - (MAX_LEN + 1), MAX_LEN + 1):
            batch = torch.tensor(val_ids[i:i + MAX_LEN + 1], dtype=torch.long)
            input_ids = batch[:-1].unsqueeze(0)
            labels = batch[1:].unsqueeze(0)
            o = model(input_ids, labels=labels)
            vloss += o["loss"].item(); vcount += 1
    avg = vloss / max(vcount, 1)
    res["val_loss"] = avg
    res["val_perplexity"] = math.exp(min(avg, 20.0))
    res["val_windows"] = vcount
    res["val_tokens_evaluated"] = vcount * MAX_LEN
    res["val_sha256"] = sw.compute_hash(str(COMMON_VAL))

    # ---- 10 fixed generation prompts ----
    gens = {}
    for p in FIXED_PROMPTS:
        try:
            gens[p] = gen(model, tok, p, max_new=64)
        except Exception as e:
            gens[p] = f"[ERROR {e}]"
    res["generations"] = gens

    # ---- MATH ----
    math_ok = 0
    for q, exp in MATH_QS:
        out = gen(model, tok, "Q: " + q + "?", max_new=40, temperature=0.5, top_p=0.95)
        got = first_int(out)
        if got is not None and got == exp:
            math_ok += 1
    res["math"] = {"correct": math_ok, "total": len(MATH_QS), "accuracy": math_ok / len(MATH_QS)}

    # ---- LOGIC ----
    logic_ok = 0
    for q, kws in LOGIC_QS:
        out = gen(model, tok, "Q: " + q + "?", max_new=40, temperature=0.5, top_p=0.95).lower()
        if any(k in out for k in kws):
            logic_ok += 1
    res["logic"] = {"correct": logic_ok, "total": len(LOGIC_QS), "accuracy": logic_ok / len(LOGIC_QS)}

    # ---- KNOWLEDGE ----
    know_ok = 0
    for q, kws in KNOW_QS:
        out = gen(model, tok, "Q: " + q, max_new=40, temperature=0.5, top_p=0.95).lower()
        if any(k in out for k in kws):
            know_ok += 1
    res["knowledge"] = {"correct": know_ok, "total": len(KNOW_QS), "accuracy": know_ok / len(KNOW_QS)}

    # ---- CODING ----
    code_ok = 0
    code_details = []
    for q, fname, test in CODE_QS:
        out = gen(model, tok, q + "\n", max_new=120, temperature=0.5, top_p=0.95)
        code = extract_py(out)
        ok = run_code_check(code, test, fname)
        if ok:
            code_ok += 1
        code_details.append({"prompt": q.strip(), "passed": ok, "extracted_len": len(code)})
    res["coding"] = {"correct": code_ok, "total": len(CODE_QS), "accuracy": code_ok / len(CODE_QS),
                     "details": code_details}
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=None,
                    help="model config json (staged silverwing_120m_config.json)")
    ap.add_argument("--tok", default=None,
                    help="tokenizer json (staged r2000_tokenizer.json)")
    args = ap.parse_args()

    ckpt = Path(args.ckpt)
    # Config lives in the staged config (ckpt dir only has metadata.json, not config.json)
    cfg_path = args.config or str(ckpt / "config.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.environ.get("SW_CFG", KAGGLE_WK + "/silverwing_120m_config.json")
    config = sw.ModelConfig(**json.load(open(cfg_path)))
    model = sw.SilverwingModel(config).to(DEVICE)
    model.load_state_dict(load_file(str(ckpt / "model.safetensors")), strict=False)
    model.eval()
    tok = sw.BPETokenizer.from_file(args.tok or R2000_TOK)
    print(f"[EVAL] {args.label}: params={model.num_parameters():,} tok=vocab={tok.vocab_size} device={DEVICE}")
    res = evaluate(model, tok, args.label)
    res["checkpoint"] = str(ckpt)
    res["model_sha256"] = sw.compute_hash(str(ckpt / "model.safetensors"))
    json.dump(res, open(args.out, "w"), indent=2)
    print(f"[EVAL] {args.label}: val_loss={res['val_loss']:.4f} ppl={res['val_perplexity']:.2f} "
          f"math={res['math']['accuracy']:.2f} logic={res['logic']['accuracy']:.2f} "
          f"coding={res['coding']['accuracy']:.2f} knowledge={res['knowledge']['accuracy']:.2f}")
    print(f"[EVAL] wrote {args.out}")

if __name__ == "__main__":
    main()
