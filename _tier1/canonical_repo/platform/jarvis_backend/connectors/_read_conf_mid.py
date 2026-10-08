p = "F:/AI/Jarvis-super-intelligence-/tests/conftest.py"
lines = open(p, encoding="utf-8").read().split("\n")
print("total:", len(lines))
for i in range(75, 175):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}")
