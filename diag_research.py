import os
R = r"F:/AI/_research"
files = {
 "langgraph_stream.txt": ["checkpoint", "checkpointer", "Checkpoint", "interrupt", "stream", "StreamingMode", "StateGraph", "add_edge", "START", "END"],
 "autogpt_docs.txt": ["Blocks", "agent loop", "tools", "memory", "streaming", "AgentServer", "Loop", "Planner", "execution"],
 "agents_sdk.txt": ["streaming", "handoff", "Handoff", "tool", "Tool", "Runner", "MCP", "Agent", "stream"],
 "crew_readme.txt": ["Agent", "Task", "Crew", "role", "backchannel", "execution", "memory"],
 "cursor_docs.txt": ["indexing", "Codebase indexing", "stream", "Auth", "token", "embedding", "Breadcrumbs"],
 "cody_docs.txt": ["indexing", "embedding", "auth", "stream", "Codebase", "telemetry"],
 "hf_agents_smolagents.txt": ["Tool", "agent", "streaming", "tool_answer", "CodeAgent", "ManagedAgent"],
 "a2a_spec_v1.txt": ["AgentCard", "capabilities", "streaming", "stream", "task", "TaskState", "json-rpc", "message:send"],
}
for fn, terms in files.items():
    p = os.path.join(R, fn)
    if not os.path.exists(p):
        print(f"\n### {fn}: MISSING"); continue
    L = open(p, encoding="utf-8", errors="replace").read().split("\n")
    print(f"\n### {fn} ({len(L)} lines, {os.path.getsize(p)} bytes)")
    for t in terms:
        hits = [i for i, l in enumerate(L) if t in l]
        if hits:
            i = hits[0]
            ctx = " ".join(L[i].split())[:160]
            print(f"  first '{t}' @ line {i+1}: {ctx}")
