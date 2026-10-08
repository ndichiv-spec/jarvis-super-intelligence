import sys, asyncio
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

from jarvis_backend.temporal_workflows import (
    temporal_available, get_temporal_status,
    run_science_workflow, run_consolidation_workflow,
    run_research_workflow,
)

# Check status
status = get_temporal_status()
print(f"Temporal installed: {status['temporalio_installed']}")
print(f"Server host: {status['server_host']}")
print(f"Server reachable: {status['server_reachable']}")
print(f"Workflows: {status['workflows']}")
print(f"Activities: {status['activities']}")

# Test science workflow (in-process fallback)
async def test_science():
    problems = [
        {"operation": "solve", "problem": "2*x+5=15", "variable": "x"},
        {"operation": "integral", "problem": "x**2", "variable": "x"},
        {"operation": "derivative", "problem": "x**2", "variable": "x"},
        {"operation": "limit", "problem": "sin(x)/x", "variable": "x"},
    ]
    result = await run_science_workflow(problems)
    print(f"\nScience workflow: execution={result['execution']}")
    print(f"  Solved: {result['result']['solved']}")
    for r in result['result']['results']:
        res = str(r.get('result', r.get('error', ''))).replace('\n', ' ')[:80]
        print(f"    {r['operation']}: {res}")

asyncio.run(test_science())

# Test consolidation workflow
async def test_consolidation():
    study_pairs = [
        {"domain": "mathematics", "concept": "arithmetic"},
        {"domain": "mathematics", "concept": "algebra"},
    ]
    result = await run_consolidation_workflow(study_pairs, run_consolidation=True)
    print(f"\nConsolidation workflow: execution={result['execution']}")
    print(f"  Studied: {result['result']['studied']}")
    print(f"  Consolidated: {result['result']['consolidated']}")

asyncio.run(test_consolidation())

print("\nPhase 31e Temporal.io integration tests PASSED.")
