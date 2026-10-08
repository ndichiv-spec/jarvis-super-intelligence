import sys, os
sys.path.insert(0, r"F:\AI")
sys.path.insert(0, r"F:\AI\Jarvis-super-intelligence-")
from dotenv import load_dotenv
load_dotenv(r"F:\AI\.env")

from providers.bootstrap import bootstrap_fabric
from providers.base import ProviderRequest
import time

registry = bootstrap_fabric()
adapter = registry.get("nvidia")
print(f"NVIDIA adapter: {adapter}, configured: {adapter.configured}")

health = adapter.health(force=True)
print(f"Healthy: {health.is_healthy}, Models: {health.models_found}")

# Try chat
req = ProviderRequest(
    messages=[{"role": "user", "content": "What is 2+2?"}],
    model="nvidia/nemotron-3-ultra-550b-a55b",
    stream=False,
    timeout=60,
)
start = time.time()
try:
    resp = adapter.chat(req)
    elapsed = time.time() - start
    print(f"({elapsed:.1f}s) Response: {resp.text[:200]}")
    print(f"  Provider: {resp.provider}, Model: {resp.model}")
except Exception as e:
    elapsed = time.time() - start
    print(f"({elapsed:.1f}s) Error: {type(e).__name__}: {str(e)[:300]}")
