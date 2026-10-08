import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SESSION_ID = "audit-trace-nonstreaming"

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

# Test non-streaming with session history
print("\n=== TEST 1: Non-streaming - Set up context ===")
payload = json.dumps({
    "message": "My favorite color is blue. What is 3+3?",
    "session_id": SESSION_ID,
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/process",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=30)
result = json.loads(r.read().decode())
print(f"  Response: {result.get('response')}")
print(f"  Model: {result.get('model')}, Provider: {result.get('provider')}")
print(f"  Latency: {result.get('latency_ms')}ms")

# Test 2: Conversation continuity through non-streaming endpoint
print("\n=== TEST 2: Non-streaming - What did I just tell you? ===")
payload = json.dumps({
    "message": "What did I just tell you?",
    "session_id": SESSION_ID,
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/process",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=30)
result = json.loads(r.read().decode())
print(f"  Response: {result.get('response')}")
print(f"  Model: {result.get('model')}, Provider: {result.get('provider')}")

# Test /ai/status truthfulness
print("\n=== TEST 3: /ai/status truthfulness ===")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/status",
    headers={"Authorization": f"Bearer {token}"},
    method="GET"
)
r = urllib.request.urlopen(req, timeout=30)
data = json.loads(r.read().decode())
print(f"  status: {data.get('status')}")
print(f"  enabled: {data.get('enabled')}")
print(f"  platform_status: {data.get('platform_status')}")
print(f"  silverwing: {json.dumps(data.get('silverwing', {}), indent=2)}")
print(f"  brain: {json.dumps(data.get('brain', {}), indent=2)}")
