import urllib.request, json, time

BASE = "http://127.0.0.1:8000"
SESSION_ID = "final-test"

def login():
    payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
print("Login OK")

# Test 1: Non-streaming with explicit google model
print("\n=== Non-streaming: google:gemini-2.5-flash ===")
payload = json.dumps({"message": "My name is Test. What is 2+2?", "session_id": SESSION_ID, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")

# Test 2: Non-streaming follow-up (continuity)
print("\n=== Non-streaming follow-up (continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) {result.get('response')} [provider={result.get('provider')}, model={result.get('model')}]")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")

# Test 3: SSE streaming with explicit google model
print("\n=== SSE streaming: google:gemini-2.5-flash ===")
payload = json.dumps({"message": "Hello, what is 3+3?", "session_id": SESSION_ID + "-sse", "stream": True, "model": "google:gemini-2.5-flash", "max_tokens": 100}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=30)
final_text = ""
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
        elif etype == "delta":
            final_text += e.get("text", "")
        elif etype in ("typing", "meta"):
            pass

# Test 4: SSE streaming follow-up (continuity)
print("\n=== SSE streaming follow-up (continuity) ===")
payload = json.dumps({"message": "What was my previous question?", "session_id": SESSION_ID + "-sse", "stream": True, "model": "google:gemini-2.5-flash", "max_tokens": 100}).encode("utf-8")
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
        elif etype in ("typing", "meta", "delta"):
            pass

print("\n=== ALL TESTS DONE ===")
