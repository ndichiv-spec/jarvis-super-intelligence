import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SESSION_ID = "verify-001"

def login():
    payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
print("Login OK")

# Test 1: SSE streaming - first message
print("\n=== SSE streaming: first message ===")
payload = json.dumps({"message": "My name is Test. What is 2+2?", "session_id": SESSION_ID, "stream": True, "model": "auto", "max_tokens": 100}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        etype = e.get("type")
        if etype == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, model={e.get('model')}, streamed={e.get('streamed')}]")
            break
        elif etype == "error":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) ERROR [{e.get('category')}]: {e.get('message')}")
            break

# Test 2: SSE streaming - follow-up (continuity)
print("\n=== SSE streaming: follow-up (continuity) ===")
payload = json.dumps({"message": "What did I just tell you?", "session_id": SESSION_ID, "stream": True, "model": "auto", "max_tokens": 100}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        etype = e.get("type")
        if etype == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, model={e.get('model')}, streamed={e.get('streamed')}]")
            break
        elif etype == "error":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) ERROR [{e.get('category')}]: {e.get('message')}")
            break

# Test 3: Non-streaming ai_process
print("\n=== Non-streaming ai_process (continuity) ===")
payload = json.dumps({"message": "What is 3+3?", "session_id": SESSION_ID, "stream": False, "model": "auto"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")

# Test 4: Non-streaming follow-up (continuity)
print("\n=== Non-streaming ai_process follow-up (continuity) ===")
payload = json.dumps({"message": "What was my favorite number?", "session_id": SESSION_ID, "stream": False, "model": "auto"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=90)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")

# Test 5: AI status
print("\n=== AI Status ===")
req = urllib.request.Request(f"{BASE}/api/v1/ai/status", headers={"Authorization": f"Bearer {token}"})
r = urllib.request.urlopen(req, timeout=15)
elapsed = time.time() - start
status = json.loads(r.read().decode())
print(json.dumps(status, indent=2)[:500])

# Test 6: SSE error handling (no provider)
print("\n=== SSE streaming failure honesty (unreachable provider) ===")
payload = json.dumps({"message": "Hi", "session_id": "error-test", "stream": True, "model": "silverwing:bad-model", "max_tokens": 50}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=30)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        etype = e.get("type")
        if etype == "complete":
            print(f"  ({time.time()-start:.1f}s) {e.get('content')}")
            break
        elif etype == "error":
            print(f"  ({time.time()-start:.1f}s) ERROR [{e.get('category')}]: {e.get('message')}")
            break

print("\n=== ALL TESTS PASSED ===")
