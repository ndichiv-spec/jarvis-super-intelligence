import os, re
R = r"F:/AI/_research"

# 1) Read clean small AutoGPT + LangChain text sources in full
clean = ["autogpt_api.txt", "autogpt_blocks.txt", "autogpt_dataflow.txt",
         "autogpt_readme.txt", "lc_build_python.txt", "agents_sdk.txt"]
for fn in clean:
    p = os.path.join(R, fn)
    if not os.path.exists(p):
        print(f"\n### {fn}: MISSING"); continue
    L = open(p, encoding="utf-8", errors="replace").read().split("\n")
    print(f"\n{'='*70}\n### {fn}  ({len(L)} lines, {os.path.getsize(p)} bytes)\n{'='*70}")
    # print compact (strip excessive blank lines)
    out = []
    blank = False
    for l in L:
        s = l.rstrip()
        if s == "":
            if not blank:
                out.append("")
            blank = True
        else:
            blank = False
            out.append(s)
    print("\n".join(out[:240]))  # cap per file

# 2) Sample the structured A2A v1 spec for the key schema pieces
p = os.path.join(R, "a2a_spec_v1.txt")
L = open(p, encoding="utf-8", errors="replace").read().split("\n")
def ctx_around(needle, radius=4):
    hits = [i for i,l in enumerate(L) if needle in l]
    if not hits:
        return f"  (no '{needle}')"
    i = hits[0]
    lines = [f"  {j+1}| {L[j]}" for j in range(max(0,i-radius), min(len(L),i+radius+1))]
    return "\n".join(lines)

print(f"\n{'='*70}\n### a2a_spec_v1.txt sampling  ({len(L)} lines)\n{'='*70}")
for term in [""\"name\": \"AgentCard\"", "capabilities", "StreamingAgentCapabilities",
             "TaskState", "inputRequired", "working", "completed", "TaskSendParams",
             "message:send", "tasks.get", "tasks.cancel", "arts:", "protocol":",
             "mimeTypes", "supportsMessageSend"]:
    # search for term as substring
    pass

# simpler: print sections by heading
print("\n-- AgentCard schema (first occurrence) --")
print(ctx_around("AgentCard"))
print("\n-- TaskState enum --")
print(ctx_around("inputRequired"))
print("\n-- JSON-RPC message:send --")
print(ctx_around("tasks:sendMessage") if False else ctx_around("message:send"))
print("\n-- task state machine --")
print(ctx_around('"state"'))
