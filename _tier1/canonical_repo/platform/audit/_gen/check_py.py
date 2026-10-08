"""Flag likely broken list/dict literals in a .py source: lines whose
double-quote count is odd (an unterminated string) OR where a ']' or '}'
closes a collection immediately after a non-quote, non-whitespace char
(e.g. 'py]' = missing closing quote). Diagnostic only."""
import sys
path = sys.argv[1]
out = []
for i, l in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
    s = l.strip()
    if not s:
        continue
    if s.startswith("#"):
        continue
    q = l.count('"')
    # ignore escaped quotes (rough)
    if '"' in l:
        odd = (q % 2) == 1
    else:
        odd = False
    # ']' not preceded by '"' or ']' (suspicious: e.g. 'py]')
    import re
    close_bad = re.search(r'(?<!\")\]', l) and not l.strip().startswith("]")
    open_bad = re.search(r'\[(?!.*\])', l) is None
    if odd:
        out.append((i, "ODD_QUOTES", l))
    if re.search(r'\w\]', l) and not re.search(r'\w\"]', l):
        # word-char immediately followed by ] (no quote): likely 'py]'
        out.append((i, "WORD_BEFORE_BRACKET", l))
for i, flag, l in out:
    print(f"{i:5d} {flag:14s} | {l}")
print("checked", max(range(1, i+1) for i,_,_ in [(0,0,0)]+(out)) if out else 0, "lines; hits:", len(out))
