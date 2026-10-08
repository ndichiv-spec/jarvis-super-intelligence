import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SESSION_ID = "timeout-debug"

def login():
    payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
print("Login OK")

# Test 1: SSE streaming (should work - Google fabric streaming)
print("\n=== SSE streaming test (auto model) ===")
payload = json.dumps({"message": "What is 2+2?", "session_id": SESSION_ID, "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        if e.get("type") == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, model={e.get('model')}, streamed={e.get('streamed')}]")
            break

# Test 2: SSE follow-up (testing continuity)
print("\n=== SSE follow-up (testing continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID, "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        if e.get("type") == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, model={e.get('model')}, streamed={e.get('streamed')}]")
            break

# Test 3: ai_process non-streaming with explicit google model (bypass brain)
print("\n=== ai_process (google:gemini-2.5-flash, bypasses brain) ===")
payload = json.dumps({"message": "What is 3+3?", "session_id": SESSION_ID, "stream": False, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    elapsed = time.time() - start
    result = json.loads(r.read().decode())
    print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")

# Test 4: ai_process follow-up with same session (using chat_service now)
print("\n=== ai_process follow-up (google model, continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID, "stream": False, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    elapsed = time.time() - start
    result = json.loads(r.read().decode())
    print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")
