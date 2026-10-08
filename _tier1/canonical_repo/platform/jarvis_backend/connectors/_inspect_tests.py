import os
root = "F:/AI/Jarvis-super-intelligence-/tests"
print("=== files ===")
for f in sorted(os.listdir(root)):
    p = os.path.join(root, f)
    if os.path.isfile(p):
        print(f"{f}  ({os.path.getsize(p)}b)")
print("\n=== conftest? ===")
for cand in ["conftest.py", "conftest.py"]:
    p = os.path.join(root, cand)
    print(cand, os.path.exists(p))
print("\n=== pytest.ini / setup.cfg / pyproject ===")
for cand in ["../pytest.ini", "../setup.cfg", "../pyproject.toml"]:
    p = os.path.join(root, cand)
    print(cand, os.path.exists(p))
print("\n=== HEAD of test_phase1_auth.py ===")
with open(os.path.join(root, "test_phase1_auth.py"), encoding="utf-8") as fh:
    for i, l in enumerate(fh):
        if i > 60: break
        print(l.rstrip())
