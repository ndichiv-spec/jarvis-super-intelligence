"""
Phase 2 Functional Validation - Test the real AI request path
"""

import sys
import os
import json
import asyncio
import time
from datetime import datetime

sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')
from jarvis_runtime import load_environment, SILVERWING_BACKEND_ROOT, ensure_import_paths

# Load environment
load_environment()

print("=" * 80)
print("PHASE 2 FUNCTIONAL VALIDATION")
print("=" * 80)
print(f"Test started at: {datetime.now().isoformat()}")
print()

# ============================================================================
# TEST 1: Provider Availability Matrix
# ============================================================================
print("TEST 1: Provider Availability Matrix")
print("-" * 40)

providers_info = []

# Check Silverwing
try:
    ensure_import_paths()
    from model_provider import ModelConfig
    mc = ModelConfig()
    
    # Check cloud keys
    cloud_key = mc.any_cloud_key() if hasattr(mc, 'any_cloud_key') else None
    
    providers_info.append({
        'provider': 'Silverwing',
        'configured': True,
        'credentials_present': bool(cloud_key),
        'status': 'READY' if cloud_key else 'NOT_CONFIGURED'
    })
    print(f"Silverwing: configured=YES, credentials={cloud_key is not None}, status=READY" if cloud_key else f"Silverwing: configured=YES, credentials=NO, status=NOT_CONFIGURED")
except Exception as e:
    providers_info.append({
        'provider': 'Silverwing', 
        'configured': False,
        'credentials_present': False,
        'status': f'ERROR: {str(e)[:50]}'
    })
    print(f"Silverwing: ERROR - {e}")

# Check Phase 6 providers (OpenAI, NVIDIA, Google, AWS, HF)
phase6_providers = ['openai', 'nvidia', 'google', 'aws', 'hf']
for p in phase6_providers:
    env_key = os.environ.get(f'{p.upper()}_API_KEY') or os.environ.get(f'{p.upper()}_KEY')
    env_endpoint = os.environ.get(f'{p.upper()}__ENDPOINT')
    
    if env_key:
        providers_info.append({
            'provider': p,
            'configured': True,
            'credentials_present': True,
            'status': 'READY'
        })
        print(f"{p}: configured=YES, credentials=YES, status=READY")
    else:
        providers_info.append({
            'provider': p,
            'configured': False,
            'credentials_present': False,
            'status': 'NOT_CONFIGURED'
        })
        print(f"{p}: configured=NO, credentials=NO, status=NOT_CONFIGURED")

print()

# ============================================================================
# TEST 2: Check AI Gateway Status
# ============================================================================
print("TEST 2: AI Gateway Configuration")
print("-" * 40)

print(f"SILVERWING_ENDPOINT: {os.environ.get('SILVERWING_ENDPOINT', 'NOT SET')}")
print(f"SILVERWING_MODEL: {os.environ.get('SILVERWING_MODEL', 'NOT SET')}")
print(f"JARVIS_BRAIN_ENDPOINT: {os.environ.get('JARVIS_BRAIN_ENDPOINT', 'NOT SET')}")
print(f"JARVIS_MODEL: {os.environ.get('JARVIS_MODEL', 'NOT SET')}")
print()

# ============================================================================
# TEST 3: Test Gateway Chat Method
# ============================================================================
print("TEST 3: ProviderGateway.chat() Test")
print("-" * 40)

async def test_gateway_chat():
    from jarvis_backend.gateway import ProviderGateway, ChatError, ErrorCategory
    from jarvis_runtime import ensure_import_paths
    
    ensure_import_paths()
    
    gateway = ProviderGateway()
    
    test_messages = [
        {"role": "user", "content": "Hello, who are you?"}
    ]
    
    start_time = time.time()
    try:
        result = await gateway.chat(
            messages=test_messages,
            model=None,
            timeout=10.0
        )
        elapsed = time.time() - start_time
        
        print(f"SUCCESS: Got response")
        print(f"Latency: {elapsed:.2f}s")
        print(f"Provider: {result.get('provider', 'unknown')}")
        print(f"Model: {result.get('model', 'unknown')}")
        print(f"Backend: {result.get('backend', 'unknown')}")
        print(f"Content preview: {result.get('content', '')[:200]}...")
        
        return {
            'status': 'SUCCESS',
            'provider': result.get('provider'),
            'model': result.get('model'),
            'latency_ms': result.get('latency_ms', int(elapsed * 1000)),
            'content': result.get('content', '')[:500]
        }
    except ChatError as e:
        elapsed = time.time() - start_time
        print(f"ChatError: {e.category} - {e.message}")
        if e.detail:
            print(f"Detail: {e.detail}")
        return {
            'status': 'PROVIDER_UNAVAILABLE',
            'error': e.message,
            'detail': e.detail if e.detail else None
        }
    except Exception as e:
        print(f"Exception: {type(e).__name__} - {e}")
        return {
            'status': 'ERROR',
            'error': str(e)
        }

result = asyncio.run(test_gateway_chat())
print()

# ============================================================================
# TEST 4: Test Direct Silverwing Router
# ============================================================================
print("TEST 4: Direct Silverwing ModelRouter Test")
print("-" * 40)

def test_silverwing_direct():
    ensure_import_paths()
    from model_provider import ModelRouter, ModelManager
    
    try:
        # Create router
        manager = ModelManager()
        registry = manager.registry if hasattr(manager, 'registry') else None
        router = ModelRouter(registry=registry, manager=manager) if registry else ModelRouter()
        
        messages = [{"role": "user", "content": "Hello, who are you?"}]
        
        start_time = time.time()
        response = router.route_and_chat(messages, model="silverwing-120m-base-v1")
        elapsed = time.time() - start_time
        
        print(f"SUCCESS: Got response")
        print(f"Latency: {elapsed:.2f}s")
        print(f"Response type: {type(response)}")
        print(f"Response content: {str(response)[:500]}...")
        
        return {
            'status': 'SUCCESS',
            'latency_s': elapsed,
            'response_preview': str(response)[:500]
        }
    except Exception as e:
        print(f"Exception: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'ERROR',
            'error': str(e)
        }

result_4 = test_silverwing_direct()
print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("SUMMARY")
print("=" * 80)
print()
print("Provider Status:")
for p in providers_info:
    print(f"  {p['provider']}: {p['status']}")
print()
print(f"Gateway Chat Test: {result.get('status', 'UNKNOWN')}")
print(f"Direct Silverwing Test: {result_4.get('status', 'UNKNOWN')}")
print()
print(f"Test completed at: {datetime.now().isoformat()}")