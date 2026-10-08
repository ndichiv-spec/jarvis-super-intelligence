import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SW = "http://127.0.0.1:8010"
BRAIN = "http://127.0.0.1:8011/v1"

def login():
    payload = json.dumps({
        "identifier": "ndichiv@gmail.com",
        "password": "videlis@254"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
print("=== Login OK ===")

# Test Silverwing health
print("\n=== Silverwing /v1/health ===")
req = urllib.request.Request(f"{SW}/v1/health")
try:
    r = urllib.request.urlopen(req, timeout=5)
    print(f"Status: {r.status}")
    print(f"Body: {json.loads(r.read().decode())}")
except Exception as e:
    print(f"Error: {e}")

# Test Silverwing models
print("\n=== Silverwing /v1/models ===")
req = urllib.request.Request(f"{SW}/v1/models")
try:
    r = urllib.request.urlopen(req, timeout=5)
    print(f"Status: {r.status}")
    print(f"Body: {r.read().decode()[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test Silverwing chat completions
print("\n=== Silverwing /v1/chat/completions (timeout 10s) ===")
payload = json.dumps({
    "model": "silverwing-120m-base-v1",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{SW}/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    start = time.time()
    r = urllib.request.urlopen(req, timeout=10)
    elapsed = time.time() - start
    print(f"Status: {r.status} (took {elapsed:.1f}s)")
    print(f"Body: {r.read().decode()[:500]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Error after {elapsed:.1f}s: {e}")

# Test Silverwing streaming
print("\n=== Silverwing /v1/chat/completions (stream=True, timeout 10s) ===")
payload = json.dumps({
    "model": "silverwing-120m-base-v1",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": True
}).encode("utf-8")
req = urllib.request.Request(
    f"{SW}/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    start = time.time()
    r = urllib.request.urlopen(req, timeout=10)
    elapsed = time.time() - start
    print(f"Status: {r.status} (took {elapsed:.1f}s)")
    content = r.read(500).decode("utf-8", errors="replace")
    print(f"Body (first 500 chars): {content}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Error after {elapsed:.1f}s: {e}")

# Test Brain endpoint (should fail)
print("\n=== Brain /v1/chat/completions ===")
payload = json.dumps({
    "model": "nvidia/nemotron-3-ultra-550b-a55b",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{BRAIN}/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": "Bearer test"},
    method="POST"
)
try:
    r = urllib.request.urlopen(req, timeout=5)
    print(f"Status: {r.status}")
    print(f"Body: {r.read().decode()[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test /api/v1/ai/status (to confirm what the frontend sees)
print("\n=== /api/v1/ai/status ===")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/status",
    headers={"Authorization": f"Bearer {token}"},
    method="GET"
)
try:
    r = urllib.request.urlopen(req, timeout=30)
    data = json.loads(r.read().decode())
    print(json.dumps(data, indent=2)[:2000])
except Exception as e:
    print(f"Error: {e}")
