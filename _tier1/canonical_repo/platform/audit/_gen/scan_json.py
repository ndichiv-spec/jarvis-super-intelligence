"""Diagnostic-only: scan a JSON file for common hand-write defects.

Writes nothing but stdout. Used only to locate bracket/quote transposition
and unclosed-array defects so they can be repaired with exact string edits.
"""
import sys, re, json

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
lines = text.split("\n")

# 1) Try a clean parse first.
try:
    json.loads(text)
    print("PARSE_OK:", path)
    sys.exit(0)
except json.JSONDecodeError as e:
    print("PARSE_FAIL:", path, "->", e.msg, "line", e.lineno, "col", e.colno, "char", e.pos)
    ln = e.lineno
    for i in range(max(0, ln - 3), min(len(lines), ln + 2)):
        mark = ">> " if i + 1 == ln else "   "
        print(f"{mark}{i+1}| {lines[i]}")
    print("--- now scanning for ALL defect signatures ---")

# 2) Unclosed single-line array value: ": [ ... ," with no ']' close on the line
print("\n[A] unclosed single-line array values (start '[' end ',' / '\"' but no ']'):")
for i, l in enumerate(lines):
    s = l.strip()
    if re.match(r'^"[^"]+"\s*:\s*\[.*', s) and (s.endswith(",") or s.endswith('"')):
        # count brackets on the line
        if s.count("[") > s.count("]"):
            print(f"  {i+1}| {l}")

# 3) Transposed closing ']"' (bracket before closing quote) at a value end, e.g. animation)]"
print("\n[B] transposed ']\"' (bracket inside the string):")
for i, l in enumerate(lines):
    # find )]\"  or  ]\"  that closes an array value with the quote AFTER the bracket
    if re.search(r'\]\"', l):
        print(f"  {i+1}| {l}")

# 4) Missing comma between consecutive key-value lines (value line ends with quote/char, next line is a bare key)
print("\n[C] possible missing commas (key-value line not ending in , or [ or {, followed by a key line):")
for i in range(len(lines) - 1):
    cur = lines[i].strip()
    nxt = lines[i + 1].strip()
    # cur looks like a closing string value (ends with ") or ] or })
    if re.match(r'^\"[^\"]+\":.*[\"\]\}]$', cur) and not cur.endswith(","):
        if re.match(r'^\"', nxt) and nxt.endswith(","):
            print(f"  {i+1}| {cur}")
            print(f"  {i+2}| {nxt}")

# 5) Malformed double-colon key ": "":
print("\n[D] malformed '\"\":' keys:")
for i, l in enumerate(lines):
    if re.search(r'\"\":\s', l):
        print(f"  {i+1}| {l}")

# 6) Stray lone ']' or '[' imbalance summary per line
print("\n[E] lines where [# != ]# on a single line (not counting strings is hard; manual review):")
for i, l in enumerate(lines):
    if l.count("[") != l.count("]") and re.search(r':\s*\[', l) and l.strip().startswith('"'):
        print(f"  {i+1}| opens={l.count('[')} closes={l.count(']')} | {l}")

print("\n[END]")
