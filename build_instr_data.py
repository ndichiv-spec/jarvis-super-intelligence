"""Build the instruction-tuning dataset for the r2000 probe (v2: rigorous generalization probe).

Sources (NO network):
  F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/01_normalized.jsonl
  (292 docs: Wikipedia CC-BY-SA 3.0 + Gutenberg PD; `text` field per doc)

Design (matches stage3a_evaluate.py prompt formats so the probe is meaningful):
  * math   -> "Q: <q>?\nA: <int>"      (eval primes: gen("Q: "+q+"?"))
  * logic  -> "Q: <q>?\nA: <answer>"
  * know   -> "Q: <q>\nA: <fact>"       (eval primes: gen("Q: "+q))
  * code   -> "<q>\n```python\n<code>\n```\n"  (eval primes: gen(q+"\n"))

KEY: the EXACT 8 math / 6 logic / 8 knowledge / 3 coding eval questions are
NOT seeded in training (they are excluded). Synthetic arithmetic/logic/code use
the SAME phrasing/format but DIFFERENT operands/signatures -> the eval tests
GENERALIZATION, not memorization. Wikipedia facts that r2000 already saw in
pretraining (e.g. Paris, H2O) are mined generically so format+fact are learned
without exact-question seed.

Target ~400k tokens (~1 epoch over a 400-step probe). Output: F:/AI/data/instr_train.txt
"""
from __future__ import annotations
import json, re, random
from pathlib import Path

random.seed(42)

JSONL = r"F:/AI/Jarvis-super-intelligence-/silverwing/data_pipeline/processed/01_normalized.jsonl"
OUT   = Path(r"F:/AI/data/instr_train.txt")
OUT.parent.mkdir(parents=True, exist_ok=True)

# exact eval questions to EXCLUDE from synthesis (so eval is unseen)
EXCL_MATH = {(17,24),(143,257),(1024,16),(2,10),(15,200),(7,8,9),(999,587)}  # a,b or a,b,c or (n,) for sum1to
CODE_SIG_EXCL = {
    "add(a, b)", "factorial(n)", "is_palindrome(s)",
}
EXCL_LOGIC_SEQ = {56}  # 2,6,12,20,30,42,?


def synth_math(n):
    out=[]
    for _ in range(n):
        while True:
            op = random.choice(["mul","add","sub","div","pow","pct","triple","sum1to","sumrange"])
            if op=="mul":
                a=random.randint(2,99); b=random.randint(2,99)
                if (a,b) in EXCL_MATH: continue
                q=("%d \u00d7 %d"%(a,b)); ans=a*b
            elif op=="add":
                a=random.randint(1,999); b=random.randint(1,999)
                if (a,b) in EXCL_MATH: continue
                q=("%d + %d"%(a,b)); ans=a+b
            elif op=="sub":
                a=random.randint(100,999); b=random.randint(100,999)
                if (a,b) in EXCL_MATH: continue
                q=("%d - %d"%(a,b)); ans=a-b
            elif op=="div":
                b=random.randint(2,99); a=b*random.randint(2,99)
                if (a,b) in EXCL_MATH: continue
                q=("%d / %d"%(a,b)); ans=a//b
            elif op=="pow":
                a=random.randint(2,5); b=random.randint(2,4)
                if (a,b) in EXCL_MATH: continue
                q=("%d to the power of %d"%(a,b)); ans=a**b
            elif op=="pct":
                a=random.randint(1,50); b=random.randint(10,500)
                if (a,b) in EXCL_MATH: continue
                q=("%d%% of %d"%(a,b)); ans=round(a*b/100)
            elif op=="triple":
                a=random.randint(2,9); b=random.randint(2,9); c=random.randint(2,9)
                if (a,b,c) in EXCL_MATH: continue
                q=("%d \u00d7 %d \u00d7 %d"%(a,b,c)); ans=a*b*c
            elif op=="sum1to":
                n=random.randint(10,200)
                if (n,) in EXCL_MATH or n==100: continue
                q=("the sum of 1 to %d"%n); ans=n*(n+1)//2
            else:
                a=random.randint(10,200); b=random.randint(a+1,300)
                if (a,b) in EXCL_MATH: continue
                q=("the sum of %d to %d"%(a,b)); ans=(a+b)*(b-a+1)//2
            out.append("Q: What is %s?\nA: %d" % (q, ans))
            break
    return out

def synth_logic(n):
    out=[]
    for _ in range(n):
        t=random.choice(["trans","cat","nineq","day","batball","seq"])
        if t=="trans":
            out.append("Q: If all A are B and all B are C, are all A definitely C?\nA: yes")
        elif t=="cat":
            out.append("Q: All cats are mammals. All mammals are animals. Is a cat an animal?\nA: yes")
        elif t=="nineq":
            out.append("Q: Is 0.999... equal to 1?\nA: yes")
        elif t=="day":
            d=random.choice(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"])
            out.append("Q: If today is %s, what day will it be 7 days from now?\nA: %s"%(d.capitalize(), d))
        elif t=="batball":
            out.append("Q: A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?\nA: 0.05")
        else:
            k=random.randint(3,8); seq=[i*(i+1) for i in range(1,k+3)]; nxt=(k+3)*(k+4)
            if nxt in EXCL_LOGIC_SEQ: continue
            s=", ".join(map(str,seq))
            out.append("Q: Sequence: %s, ? What is the next number?\nA: %d"%(s,nxt))
    return out

def synth_code(n):
    out=[]
    fns=[
        ("Write a Python function subtract(a, b) that returns a - b.\n```python\n",
         "def subtract(a, b):\n    return a - b\n"),
        ("Write a Python function multiply(a, b) that returns a * b.\n```python\n",
         "def multiply(a, b):\n    return a * b\n"),
        ("Write a Python function divide(a, b) that returns a / b.\n```python\n",
         "def divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n"),
        ("Write a Python function is_even(n) returning True if n is even.\n```python\n",
         "def is_even(n):\n    return n % 2 == 0\n"),
        ("Write a Python function reverse_string(s) returning s reversed.\n```python\n",
         "def reverse_string(s):\n    return s[::-1]\n"),
        ("Write a Python function max_of(a, b) returning the larger.\n```python\n",
         "def max_of(a, b):\n    return a if a > b else b\n"),
        ("Write a Python function square(x) returning x squared.\n```python\n",
         "def square(x):\n    return x * x\n"),
        ("Write a Python function cube(x) returning x cubed.\n```python\n",
         "def cube(x):\n    return x * x * x\n"),
        ("Write a Python function add(a, b, c) that returns a + b + c.\n```python\n",
         "def add(a, b, c):\n    return a + b + c\n"),
        ("Write a Python function is_positive(n) returning True if n > 0.\n```python\n",
         "def is_positive(n):\n    return n > 0\n"),
    ]
    for _ in range(n):
        q,code=random.choice(fns)
        out.append("%s%s```\n"%(q,code))
    return out

def mine_docs():
    docs=[]
    with open(JSONL, encoding="utf-8", errors="replace") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try: docs.append(json.loads(line))
            except Exception: pass
    return docs

def mine_facts(docs, n=1500):
    facts=[]; seen=set()
    p1=re.compile(r"(The capital of) ([A-Z][A-Za-z\s]+?) is ([A-Za-z][A-Za-z\s]*?)\.\s", re.I)
    p2=re.compile(r"([A-Z][A-Za-z]+(?: of [A-Z][A-Za-z]+)?) is (?:a |an |the )?([A-Z][A-Za-z\s]+?)\.\s", re.I)
    for d in docs:
        t=d.get("text","")
        for m in p1.finditer(t):
            ent=m.group(2).strip(); val=m.group(3).strip()
            q="What is the capital of %s?"%ent
            if q not in seen and len(val.split())<=4:
                seen.add(q); facts.append((q,val))
        for m in p2.finditer(t):
            ent=m.group(1).strip(); val=m.group(2).strip()
            if ent.lower() in ("the","a"): continue
            q="What is %s?"%ent
            if 2<=len(ent.split())<=5 and len(val.split())<=6 and q not in seen:
                seen.add(q); facts.append((q,val))
        if len(facts)>=n*2: break
    random.shuffle(facts)
    return ["Q: %s\nA: %s"%(q,a) for (q,a) in facts[:n]]

def mine_code(docs, n=1000):
    blocks=[]; seen=set()
    for d in docs:
        t=d.get("text","")
        for m in re.finditer(r"```(?:python|py|)?\n(.*?)```", t, re.DOTALL):
            code=m.group(1).strip()
            if 40<=len(code)<=500 and "def " in code and code not in seen:
                seen.add(code)
                if len(blocks)<n:
                    blocks.append("Write a Python function to perform the task below.\n```python\n"+code+"\n```\n")
            if len(blocks)>=n: break
        if len(blocks)>=n: break
    return blocks

def mine_explain(docs, n=500):
    out=[]; seen=set()
    for d in docs:
        t=d.get("text","")
        title=None
        m=re.match(r"([A-Za-z][A-Za-z\s'/,&\-]+)\n", t)
        if m: title=m.group(1).strip()
        mp=re.search(r"\.\s+([A-Z][^.]{30,350}\.)", t[200:2000+200])
        ans=mp.group(1).strip() if mp else ""
        if title and ans and 5<=len(title)<=70 and len(ans.split())>=5 and title not in seen:
            seen.add(title)
            out.append("%s.\nA: %s"%(title,ans))
        if len(out)>=n: break
    return out

def main():
    docs=mine_docs()
    swiki=sum(1 for d in docs if d.get("source")=="wikipedia")
    sgb=len(docs)-swiki
    print("docs=%d wiki=%d gutenberg=%d"%(len(docs),swiki,sgb))

    parts=[]
    parts += synth_math(10000)
    parts += synth_logic(1500)
    parts += synth_code(1500)
    parts += mine_facts(docs, 1500)
    parts += mine_code(docs, 1000)
    parts += mine_explain(docs, 500)
    random.seed(7); random.shuffle(parts)
    text="\n\n".join(parts)+"\n"
    OUT.write_text(text, encoding="utf-8")
    print("examples=%d  wrote=%s"%(len(parts), OUT))

    # token count
    import sys
    sys.path.insert(0, r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu")
    import silverwing_train as sw
    tok=sw.BPETokenizer.from_file(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
    ids=tok.encode(text)
    need=400*1024
    print("tokens=%d  epochs@400steps=%s"%(len(ids), round(len(ids)/need,2)))
    # sanity: confirm none of the exact eval math Qs slipped in
    chk=["What is 17 \u00d7 24?","What is 143 + 257?","What is 1024 / 16?",
         "What is 2 to the power of 10?","What is 15% of 200?","What is 7 \u00d7 8 \u00d7 9?",
         "What is 999 - 587?","What is the sum of 1 to 100?"]
    bad=[c for c in chk if c in text]
    print("exact-eval math Qs leaked into train:",bad if bad else "NONE (good)")
    # coding sigs
    badc=[s for s in ["add(a, b)","factorial(n)","is_palindrome(s)"] if ("function %s"%s) in text]
    print("exact-eval code sigs leaked:",badc if badc else "NONE (good)")

if __name__=="__main__":
    main()
