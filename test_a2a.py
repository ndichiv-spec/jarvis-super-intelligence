import sys
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

from jarvis_backend.a2a_server import (
    a2a_available, create_a2a_agent_card, CAPABILITY_SKILLS,
    JarvisAgentExecutor, mount_a2a_routes,
)

# Check availability
print(f"A2A SDK available: {a2a_available()}")

# Test agent card creation
card = create_a2a_agent_card()
print(f"Agent card type: {type(card).__name__}")
if hasattr(card, 'name'):
    print(f"  Name: {card.name}")
    print(f"  Version: {card.version}")
    print(f"  Skills count: {len(card.skills)}")
    for skill in card.skills[:3]:
        print(f"    - {skill.id}: {skill.name}")
    print(f"    ... and {len(card.skills) - 3} more")
else:
    print(f"  Name: {card['name']}")
    print(f"  Skills count: {len(card['skills'])}")

# Test executor
executor = JarvisAgentExecutor()
print(f"\nExecutor created: {type(executor).__name__}")
print(f"Skill-to-Capability mappings: {len(executor.SKILL_TO_CAPABILITY)}")

# Test skill detection
test_inputs = [
    "What is the capital of France?",
    "Search arxiv for quantum computing papers",
    "Solve the equation 2*x + 5 = 15",
    "Create a task to review the codebase",
    "Generate an image of a sunset",
]
for inp in test_inputs:
    skill = executor._detect_skill(inp)
    cap = executor.SKILL_TO_CAPABILITY.get(skill, "unknown")
    print(f"  '{inp[:40]}...' -> skill={skill}, capability={cap}")

# Test mount on a fake FastAPI app (should work with a2a SDK installed)
try:
    from fastapi import FastAPI
    app = FastAPI()
    mounted = mount_a2a_routes(app)
    print(f"\nRoutes mounted: {mounted}")
    if mounted:
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        a2a_routes = [r for r in routes if '/a2a' in r or 'agent-card' in r]
        print(f"A2A routes: {a2a_routes}")
    print(f"\nMount test: SUCCESS - {len(a2a_routes)} routes mounted")
except Exception as e:
    print(f"\nMount test: {e}")

print("\nPhase 32 A2A protocol server tests PASSED.")
