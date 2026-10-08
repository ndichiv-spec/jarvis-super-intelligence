import inspect

c_mod = "jarvis_backend.core"
core = __import__(c_mod, fromlist=["x"])
src = inspect.getsource(core)
lines = src.split("\n")
print(f"core.py total source lines: {len(lines)}")

pats = ["def start_backend", "def ensure_owner", "def seed_default", "test-password-for-testing",
        'is_admin": True', 'is_admin":', "def ensure_owner_or_admin", "admin@jarvis.local"]
for pat in pats:
    idxs = [i for i, l in enumerate(lines) if pat in l]
    print(f"  {pat!r}: {len(idxs)} hits -> lines {[i+1 for i in idxs[:8]]}")

# Print the first occurrence context of start_backend and the test-password seed
def show(pat, radius=14):
    idxs = [i for i, l in enumerate(lines) if pat in l]
    if not idxs:
        print(f"  (no occurrence of {pat})")
        return
    i = idxs[0]
    print(f"\n=== context for {pat!r} (first hit @ line {i+1}) ===")
    for j in range(max(0, i-radius), min(len(lines), i+radius+1)):
        mark = ">>>" if j == i else "   "
        print(f"{mark} {j+1:5d}| {lines[j]}")

for p in ["def start_backend", "test-password-for-testing"]:
    show(p)
