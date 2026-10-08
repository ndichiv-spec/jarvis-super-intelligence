import sys, asyncio
sys.path.insert(0, 'F:/AI')
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

from jarvis_backend.capabilities.tools import ToolCapability
tc = ToolCapability()
print("Registered tools:", sorted(tc._registered_tools.keys()))
print("Tool count:", len(tc._registered_tools))
print()

# Check capability health for all 15
from jarvis_backend.capability import get_orchestrator
orchestrator = get_orchestrator()
asyncio.run(orchestrator.registry.health_all())
statuses = orchestrator.get_all_status()
for cap_id, info in sorted(statuses['capabilities'].items()):
    s = info['status']
    print(f"  {cap_id}: {s}")

print()

# Check MCP catalog
from jarvis_backend.mcp_server import _TOOL_CATALOG
print("MCP tools:", sorted(_TOOL_CATALOG.keys()))

print()

# Check if new tables exist in persistence
from jarvis_backend.persistence import initialize_persistence
import sqlalchemy as sa
engine = initialize_persistence()
insp = sa.inspect(engine)
existing = set(insp.get_table_names())
expected_new = [
    "jarvis_science_solutions",
    "jarvis_hypotheses",
    "jarvis_learning_episodes",
    "jarvis_tech_technologies",
    "jarvis_tech_frontiers",
    "jarvis_tech_predictions",
    "jarvis_research_items",
    "jarvis_knowledge_graph",
    "jarvis_research_feeds",
]
print("New tables in DB:")
for t in expected_new:
    print(f"  {t}: {'FOUND' if t in existing else 'MISSING'}")
