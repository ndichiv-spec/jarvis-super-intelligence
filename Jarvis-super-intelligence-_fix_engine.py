"""Fix deploy_candidate PRODUCTION transition and check_budget list indexing."""
import sys
sys.path.insert(0, '.')
import os
os.environ['JARVIS_TEST_MODE'] = '1'

with open('jarvis_backend/self_improvement_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: deploy_candidate PRODUCTION mode - needs to go through DEPLOYED_SHADOW first
old_prod = '''        if mode == DeploymentMode.SHADOW.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
        elif mode == DeploymentMode.CANARY.value:
            candidate.transition(CandidateStatus.DEPLOYED_CANARY)
        elif mode == DeploymentMode.PRODUCTION.value:
            candidate.transition(CandidateStatus.DEPLOYED)'''

new_prod = '''        if mode == DeploymentMode.SHADOW.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
        elif mode == DeploymentMode.CANARY.value:
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
            candidate.transition(CandidateStatus.DEPLOYED_CANARY)
        elif mode == DeploymentMode.PRODUCTION.value:
            # Production requires going through shadow -> canary -> deployed
            candidate.transition(CandidateStatus.DEPLOYED_SHADOW)
            candidate.transition(CandidateStatus.DEPLOYED_CANARY)
            candidate.transition(CandidateStatus.DEPLOYED)'''

if old_prod in content:
    content = content.replace(old_prod, new_prod, 1)
    print("FIXED: deploy_candidate PRODUCTION transition")
else:
    print("WARNING: deploy_candidate pattern not found")

# Fix 2: check_budget - provenance is a list, not a dict
old_budget = '''        user_id = cycle.provenance.get(0, "").split(":")[0] if cycle.provenance else "system"'''

new_budget = '''        user_id = cycle.provenance[0].split(":")[0] if cycle.provenance else "system"'''

if old_budget in content:
    content = content.replace(old_budget, new_budget, 1)
    print("FIXED: check_budget list indexing")
else:
    print("WARNING: check_budget pattern not found")

with open('jarvis_backend/self_improvement_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
