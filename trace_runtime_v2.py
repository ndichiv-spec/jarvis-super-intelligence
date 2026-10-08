import urllib.request, json, sys

BASE = "http://127.0.0.1:8000"
SESSION_ID = "audit-trace-v2"

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
    body = json.loads(r.read().decode("utf-8", errors="replace"))
    print("=== LOGIN === OK")
    return body["access_token"]

def ai_process(token, message, model=None):
    payload = json.dumps({
        "message": message,
        "session_id": SESSION_ID,
        "model": model or "auto",
        "stream": False,
        "max_tokens": 100,
        "temperature": 0.7
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/v1/ai/process",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read().decode("utf-8", errors="replace"))

token = login()

# Test 1: Set up context
print("\n=== TEST 1: My name is Test ===")
try:
    resp1 = ai_process(token, "My name is Test. What is 2+2?")
    print(json.dumps(resp1, indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:1000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Conversation continuity
print("\n=== TEST 2: What did I just tell you? ===")
try:
    resp2 = ai_process(token, "What did I just tell you?")
    print(json.dumps(resp2, indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:1000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Silverwing runtime direct
print("\n=== TEST 3: Silverwing runtime /v1/chat/completions ===")
payload = json.dumps({
    "model": "silverwing-120m-base-v1",
    "messages": [{"role": "user", "content": "Hello from Silverwing test"}],
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8010/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    r = urllib.request.urlopen(req, timeout=30)
    print(json.dumps(json.loads(r.read().decode()), indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:500])
except Exception as e:
    print(f"Error: {e}")

# Test 4: SSE streaming endpoint
print("\n=== TEST 4: SSE streaming /api/chat/stream ===")
payload = json.dumps({
    "message": "Count to 5",
    "session_id": SESSION_ID + "-sse",
    "stream": True,
    "model": "auto"
}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/chat/stream",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
try:
    r = urllib.request.urlopen(req, timeout=30)
    print(f"Status: {r.status}")
    ct = r.headers.get("Content-Type", "")
    print(f"Content-Type: {ct}")
    for i, line in enumerate(r):
        chunk = line.decode("utf-8", errors="replace").strip()
        if chunk:
            print(f"  LINE {i}: {chunk[:300]}")
            if i > 50:
                print("  ... (truncated)")
                break
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:1000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Check /ai/models endpoint
print("\n=== TEST 5: /api/v1/ai/models ===")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/models",
    headers={"Authorization": f"Bearer {token}"},
    method="GET"
)
try:
    r = urllib.request.urlopen(req, timeout=15)
    data = json.loads(r.read().decode())
    print(json.dumps(data, indent=2)[:3000])
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:500])
except Exception as e:
    print(f"Error: {e}")
