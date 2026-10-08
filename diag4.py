import os, re, glob

base = r"F:\AI\Jarvis-super-intelligence-"
hits = []
for root, _, files in os.walk(base):
    # skip noisy dirs
    if any(seg in root for seg in ("node_modules", ".git", "data", "jarvis_data", "__pycache__")):
        continue
    for fn in files:
        if fn.endswith(".py"):
            p = os.path.join(root, fn)
            try:
                lines = open(p, encoding="utf-8").read().split("\n")
            except Exception:
                continue
            for i, l in enumerate(lines):
                if "JARVIS_TEST_MODE" in l:
                    hits.append((p, i + 1, l.strip()))

print("JARVIS_TEST_MODE occurrences (file, line, text):")
for p, ln, t in hits:
    print(f"  {p.replace(base,'')}:{ln}: {t}")

# Show the function containing each core.py occurrence (±8 lines)
cp = os.path.join(base, "jarvis_backend/core.py")
if os.path.exists(cp):
    lines = open(cp, encoding="utf-8").read().split("\n")
    print("\n=== core.py JARVIS_TEST_MODE context ===")
    for idx, l in enumerate(lines):
        if "JARVIS_TEST_MODE" in l:
            s = max(0, idx - 8); e = min(len(lines), idx + 9)
            print(f"\n-- around core.py:{idx+1} --")
            for j in range(s, e):
                mark = ">>>" if j == idx else "   "
                print(f"{mark} {j+1:5d}| {lines[j]}")

# main.py app object + uvicorn / include_router context
mp = os.path.join(base, "jarvis_backend/main.py")
if os.path.exists(mp):
    lines = open(mp, encoding="utf-8").read().split("\n")
    print("\n=== main.py: app/uvicorn/include_router/system ===")
    for idx, l in enumerate(lines):
        s = l.strip()
        if ("app " in l and ("=" in l)) or "uvicorn.run" in l or "include_router" in l or "system" in s.lower():
            print(f"  {idx+1:5d}| {l}")
