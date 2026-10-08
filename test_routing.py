import sys, os
sys.path.insert(0, r"F:\AI")
sys.path.insert(0, r"F:\AI\Jarvis-super-intelligence-")
from dotenv import load_dotenv
load_dotenv(r"F:\AI\.env")

from providers.bootstrap import bootstrap_fabric
from providers.routing import TaskProfile, TaskClassifier, TaskPrivacy

registry = bootstrap_fabric()
router = TaskClassifier(registry)

# Route a simple chat task
profile = TaskProfile(
    description="Simple math question",
    capabilities=frozenset({"chat"}),
    privacy=TaskPrivacy.PUBLIC,
)

decision = router.route(profile)
print(f"Selected provider: {decision.selected_provider}")
print(f"Selected model: {decision.selected_model}")
print(f"Candidate count: {decision.candidate_count}")
print(f"Fallback chain: {decision.fallback_chain}")
print(f"Reason: {decision.reason}")

# Now test with explicit nvidia model through the fabric
from providers.base import ProviderRequest
from providers.routing import ProviderRouter

# Test if "nvidia" is in _PHASE6_PROVIDER_IDS
from jarvis_backend.gateway import _PHASE6_PROVIDER_IDS
print(f"\nPhase6 provider IDs: {_PHASE6_PROVIDER_IDS}")
