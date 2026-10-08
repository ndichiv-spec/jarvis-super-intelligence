import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SESSION_ID = "fix-verify"

def login():
    payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
print("Login OK")

# Test 1: Non-streaming ai_process (uses chat_service.send_message -> _generate)
print("\n=== Non-streaming ai_process (chat_service path) ===")
payload = json.dumps({"message": "What is 2+2?", "session_id": SESSION_ID, "model": "auto", "stream": False}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) {result.get('response')} [model={result.get('model')}, provider={result.get('provider')}]")

# Test 2: Non-streaming follow-up (conversation continuity)
print("\n=== Non-streaming follow-up (continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID, "model": "auto", "stream": False}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) {result.get('response')} [model={result.get('model')}, provider={result.get('provider')}]")

# Test 3: SSE streaming (first message)
print("\n=== SSE streaming (first message) ===")
payload = json.dumps({"message": "Hello, what is 3+3?", "session_id": SESSION_ID + "-sse", "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=30)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        etype = e.get("type")
        if etype == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, streamed={e.get('streamed')}]")
            break
        elif etype == "error":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) ERROR [{e.get('category')}]: {e.get('message')}")
            break
        elif etype == "chunk":
            pass  # Skip chunks

# Test 4: SSE streaming follow-up (continuity)
print("\n=== SSE streaming follow-up (continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID + "-sse", "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=30)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        etype = e.get("type")
        if etype == "complete":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) {e.get('content')} [provider={e.get('provider')}, streamed={e.get('streamed')}]")
            break
        elif etype == "error":
            elapsed = time.time() - start
            print(f"  ({elapsed:.1f}s) ERROR [{e.get('category')}]: {e.get('message')}")
            break
        elif etype == "chunk":
            pass  # Skip chunks

print("\n=== All tests completed ===")
