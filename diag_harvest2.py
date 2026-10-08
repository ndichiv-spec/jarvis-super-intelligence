import os
R = r"F:/AI/_research"

def show(fn, cap=300):
    p = os.path.join(R, fn)
    if not os.path.exists(p):
        print(f"\n### {fn}: MISSING"); return
    L = open(p, encoding="utf-8", errors="replace").read().split("\n")
    out = []; blank = False
    for l in L[:cap]:
        s = l.rstrip()
        if s == "":
            if not blank: out.append("")
            blank = True
        else:
            blank = False; out.append(s)
    print(f"\n===== {fn} ({len(L)} lines) =====")
    print("\n".join(out))

for f in ["autogpt_blocks.txt", "autogpt_api.txt", "autogpt_dataflow.txt", "agents_sdk.txt"]:
    show(f)

# A2A v1 spec: TaskState enum + AgentCard JSON example + JSON-RPC methods
p = os.path.join(R, "a2a_spec_v1.txt")
L = open(p, encoding="utf-8", errors="replace").read().split("\n")
def find_all(needle, limit=8):
    return [i for i, l in enumerate(L) if needle in l][:limit]

print("\n===== a2a_spec_v1.txt : TaskState enum literals =====")
for i in find_all("inputRequired"):
    print(f"  {i+1}| {L[i].strip()}")
print("\n-- surrounding a 'pending'/'working'/'completed' block --")
for i in find_all('"pending"'):
    for j in range(i, min(i + 14, len(L))):
        print(f"  {j+1}| {L[j].strip()}")
print("\n===== JSON-RPC methods =====")
for m in ["message:send","tasks.get","tasks.list","tasks.cancel","tasks.pushNotification","tasks.resubscribe","protocol.instantiate"]:
    hits = find_all(m, 2)
    if hits:
        print(f"  {m}: line {hits[0]+1}")

print("\n===== AgentCard fields (keys) =====")
for i, l in enumerate(L):
    if "AgentCard" in l and ("requires" in l.lower() or "required" in l.lower() or "url" in l.lower()):
        print(f"  {i+1}| {L[i].strip()[:140]}")
        for j in range(i+1, min(i+12, len(L))):
            print(f"  {j+1}| {L[j].strip()[:140]}")
        break
