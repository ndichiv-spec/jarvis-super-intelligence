import py_compile, sys, os
BASE = "F:/AI/Jarvis-super-intelligence-"
files = [
    "jarvis_backend/embeddings.py",
    "jarvis_backend/research/autonomous_research.py",
    "jarvis_backend/capabilities/research_cortex.py",
    "jarvis_backend/routers/bio_growth.py",
    "jarvis_backend/main.py",
]
errors = []
for f in files:
    full = os.path.join(BASE, f)
    try:
        py_compile.compile(full, doraise=True)
        print(f"  OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"  FAIL: {f}: {e}")
        errors.append(f)
if errors:
    print(f"\n{len(errors)} files with errors")
    sys.exit(1)
else:
    print(f"\nALL {len(files)} FILES COMPILED OK")
