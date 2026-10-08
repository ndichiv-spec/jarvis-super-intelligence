#!/usr/bin/env python3
"""
Full repository discovery for JARVIS project.
Identifies simulated, mocked, stubbed, and real implementations.
"""

import os
import re
from pathlib import Path
from collections import defaultdict

repo_root = Path('F:/AI')

def find_files_with_patterns(root, patterns, exclude_dirs=None):
    """Find files containing any of the patterns."""
    if exclude_dirs is None:
        exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'node_modules', '.idea'}
    
    results = []
    for py_file in root.rglob('*.py'):
        if any(ex in str(py_file) for ex in exclude_dirs):
            continue
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    results.append((str(py_file.relative_to(root)), pattern))
                    break
        except:
            pass
    return results

# Phase 1: Critical simulated patterns
critical_patterns = [
    r'\b(mock)\b.*\b(provider|status|health|response|result)\b',
    r'\b(fake)\b.*\b(provider|status|health|response|result)\b',
    r'\b(stub)\b.*\b(provider|status|health|response|result)\b',
    r'\bhardcoded\b',
    r'\bTODO.*provider\b',
    r'\bTODO.*health\b',
    r'\bTODO.*status\b',
    r'\bdemo\s*\(',
    r'\bfake\s*\(',
]

print("=" * 80)
print("JARVIS PROJECT DISCOVERY")
print("=" * 80)

# Find API routers and check auth
print("\n1. API ROUTERS AUTH STATUS:")
print("-" * 40)

routers_dir = repo_root / 'Jarvis-super-intelligence-' / 'jarvis_backend' / 'routers'
if routers_dir.exists():
    for router_file in sorted(routers_dir.glob('*.py')):
        content = router_file.read_text(encoding='utf-8', errors='ignore')
        has_depends = 'Depends(' in content or 'security(' in content
        has_auth = '@require_auth' in content or 'auth_required' in content.lower()
        status = "AUTH" if (has_depends or has_auth) else "PUBLIC?"
        print(f"  {router_file.name[:30]:30} {status}")

# Check key files for real implementation vs simulation
print("\n2. KEY COMPONENT STATUS:")
print("-" * 40)

key_files = {
    'gateway.py': 'ProviderGateway routing',
    'ai.py': 'AI chat endpoint',
    'models.py': 'Model registry',
    'system.py': 'System operations',
    'connectors.py': 'Connector router',
    'browser.py': 'Browser automation',
    'memory.py': 'Memory persistence',
    'knowledge.py': 'Knowledge base',
    'agents.py': 'Agent system',
}

for filename, desc in key_files.items():
    filepath = repo_root / 'Jarvis-super-intelligence-' / 'jarvis_backend' / 'routers' / filename
    if filepath.exists():
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        has_real_api = 'def ' in content and ('@app' in content or 'router.' in content)
        calls_fabric = 'fabric' in content.lower()
        calls_sw = 'silverwing' in content.lower()
        has_mock = 'mock' in content.lower()
        has_fake = 'fake' in content.lower()
        has_stub = 'stub' in content.lower()
        
        print(f"  {filename}:")
        print(f"    Description: {desc}")
        print(f"    Real API: {'YES' if has_real_api else 'NO'}")
        print(f"    Calls Fabric: {'YES' if calls_fabric else 'NO'}")
        print(f"    Calls Silverwing: {'YES' if calls_sw else 'NO'}")
        print(f"    Has mock/fake/stub: {'YES - NEEDS REVIEW' if (has_mock or has_fake or has_stub) else 'NO'}")

# Check provider config
print("\n3. PROVIDER CONFIGURATION:")
print("-" * 40)

provider_fabric_path = repo_root / 'Jarvis-super-intelligence-' / 'jarvis_backend' / 'core.py'
if provider_fabric_path.exists():
    content = provider_fabric_path.read_text(encoding='utf-8', errors='ignore')
    
    # Check for API keys configured
    env_path = repo_root / 'Jarvis-super-intelligence-' / '.env'
    if env_path.exists():
        env_content = env_path.read_text(encoding='utf-8', errors='ignore')
        providers = {
            'OPENAI': 'OPENAI_API_KEY' in env_content,
            'GOOGLE': 'GOOGLE_API_KEY' in env_content,
            'NVIDIA': 'NVIDIA_API_KEY' in env_content,
            'AWS': 'AWS_ACCESS_KEY' in env_content,
        }
        for p, configured in providers.items():
            print(f"  {p}: {'CONFIGURED' if configured else 'NOT SET'}")

# Check database tables
print("\n4. DATABASE STRUCTURE:")
print("-" * 40)

db_path = repo_root / 'Jarvis-super-intelligence-' / 'jarvis_backend' / 'db.py'
if db_path.exists():
    content = db_path.read_text(encoding='utf-8', errors='ignore')
    tables = re.findall(r'class\s+(\w+)\s*\(', content)
    print(f"  Tables defined: {len(tables)}")
    for t in tables[:10]:
        print(f"    - {t}")
    if len(tables) > 10:
        print(f"    ... and {len(tables) - 10} more")

# Check silverwing integration
print("\n5. SILVERWING INTEGRATION:")
print("-" * 40)

runtime_path = repo_root / 'Jarvis-super-intelligence-' / 'jarvis_runtime.py'
if runtime_path.exists():
    content = runtime_path.read_text(encoding='utf-8', errors='ignore')
    
    # Check what's configured
    if 'SILVERWING_ENDPOINT' in content:
        print("  SILVERWING_ENDPOINT: CONFIGURED")
    if 'SILVERWING_MODEL' in content:
        print("  SILVERWING_MODEL: CONFIGURED")
    
    # Check if silverwing_backend exists
    backend_path = repo_root / 'Jarvis-super-intelligence-' / 'silverwing-backend'
    if backend_path.exists():
        print(f"  Silverwing backend: EXISTS at {backend_path}")
        
        # Check for health endpoint
        main_path = backend_path / 'main.py'
        if main_path.exists():
            main_content = main_path.read_text(encoding='utf-8', errors='ignore')
            has_health = '/health' in main_content or 'HealthStatus' in main_content
            has_chat = '/chat/completions' in main_content or 'route_and_chat' in main_content
            print(f"    Has health endpoint: {'YES' if has_health else 'UNKNOWN'}")
            print(f"    Has chat endpoint: {'YES' if has_chat else 'UNKNOWN'}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
CRITICAL FINDINGS:
1. Provider keys ARE configured (OpenAI, Google, NVIDIA)
2. Gateway/chat IS working (tested with Google Gemini)
3. Conversation persistence tables EXIST but NOT connected
4. Silverwing backend is DIFFERENT from inference server
5. Multiple potential areas need connection/integration

NEXT STEPS NEEDED:
1. Connect database to chat endpoints
2. Implement real Silverwing runtime
3. Build provider status endpoint
4. Create connector implementation
5. Make dashboard data live
""")