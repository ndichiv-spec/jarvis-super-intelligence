import sys, os
sys.path.insert(0, r"F:\AI")
sys.path.insert(0, r"F:\AI\Jarvis-super-intelligence-")
from dotenv import load_dotenv
load_dotenv(r"F:\AI\.env")

from providers.bootstrap import bootstrap_fabric
from providers.routing import ProviderRouter, TaskClassifier

registry = bootstrap_fabric()
router = ProviderRouter(registry=registry, priority="")
classifier = TaskClassifier()

profile = classifier.classify("chat")
candidates = list(router.candidates(profile))
print(f"Total candidates: {len(candidates)}")
for c in candidates:
    print(f"  {c.adapter.provider_id} / {c.model.qualified_id} -- reason: {c.reason}")

ordered = list(router._ordered(candidates))
print(f"\nOrdered ({len(ordered)}):")
for i, c in enumerate(ordered):
    print(f"  [{i}] {c.adapter.provider_id} / {c.model.qualified_id}")

decision = router.route(profile)
print(f"\nSelected: {decision.selected_provider} / {decision.selected_model}")
print(f"Fallback chain:")
for fb in decision.fallback_chain:
    print(f"  {fb}")
