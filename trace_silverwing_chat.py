import urllib.request, json, time

SW = "http://127.0.0.1:8010"

# Test different model names with Silverwing
models = ["silverwing-120m-base-v1", "jarvis-brain-qwen3-4b-v1", "jarvis-brain-qwen3-4b-sft-v1"]

for model in models:
    print(f"\n=== Silverwing chat with model={model} (timeout 8s) ===")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
        "max_tokens": 10
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SW}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        start = time.time()
        r = urllib.request.urlopen(req, timeout=8)
        elapsed = time.time() - start
        body = r.read().decode()
        print(f"  Status: {r.status} (took {elapsed:.1f}s)")
        print(f"  Body: {body[:300]}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Error after {elapsed:.1f}s: {e}")

# Also try with no model specified
print(f"\n=== Silverwing chat with no model (timeout 8s) ===")
payload = json.dumps({
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": False,
    "max_tokens": 10
}).encode("utf-8")
req = urllib.request.Request(
    f"{SW}/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    start = time.time()
    r = urllib.request.urlopen(req, timeout=8)
    elapsed = time.time() - start
    body = r.read().decode()
    print(f"  Status: {r.status} (took {elapsed:.1f}s)")
    print(f"  Body: {body[:300]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"  Error after {elapsed:.1f}s: {e}")

# Try with just the model name from models list
print(f"\n=== Silverwing /v1/models (to get exact model IDs) ===")
req = urllib.request.Request(f"{SW}/v1/models")
try:
    r = urllib.request.urlopen(req, timeout=5)
    models_data = json.loads(r.read().decode())
    for m in models_data.get("data", []):
        print(f"  - {m.get('id')} (backend={m.get('backend')}, status={m.get('status')}, health={m.get('health')})")
except Exception as e:
    print(f"  Error: {e}")
