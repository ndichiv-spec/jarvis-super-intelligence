import sys, os
sys.path.insert(0, r"F:\AI")
sys.path.insert(0, r"F:\AI\Jarvis-super-intelligence-")
from dotenv import load_dotenv
load_dotenv(r"F:\AI\.env")

from providers.bootstrap import bootstrap_fabric
from providers.base import ProviderRequest
import time

registry = bootstrap_fabric()

# Test direct NVIDIA chat
adapter = registry.get("nvidia")
print(f"NVIDIA adapter configured: {adapter.configured}")

req = ProviderRequest(
    messages=[{"role": "user", "content": "Hello, what is the capital of France?"}],
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

# Test streaming
print("\n--- Streaming test ---")
req2 = ProviderRequest(
    messages=[{"role": "user", "content": "Count to 3 in French."}],
    model="nvidia/nemotron-3-ultra-550b-a55b",
    stream=True,
    timeout=60,
)
start = time.time()
try:
    chunks = []
    for chunk in adapter.chat_stream(req2):
        elapsed = time.time() - start
        if chunk.done:
            print(f"({elapsed:.1f}s) DONE: text_len={len(chunks)}")
        elif chunk.text:
            print(f"({elapsed:.1f}s) delta: {chunk.text[:60]}")
            chunks.append(chunk.text)
        else:
            print(f"({elapsed:.1f}s) chunk: {chunk}")
        if elapsed > 30:
            print("TIMEOUT - breaking")
            break
    full_text = "".join(c for c in chunks)
    print(f"Full: {full_text[:200]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"({elapsed:.1f}s) Error: {type(e).__name__}: {str(e)[:300]}")
