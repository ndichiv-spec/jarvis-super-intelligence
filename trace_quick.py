import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

# Check health
try:
    r = urllib.request.urlopen(f"{BASE}/health", timeout=5)
    print(f"Health: {r.status}")
except Exception as e:
    print(f"Health: FAILED - {e}")

# Login
payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
r = urllib.request.urlopen(req, timeout=10)
token = json.loads(r.read().decode())["access_token"]
print("Login OK")

# Simple SSE test
print("SSE test...")
payload = json.dumps({"message": "Hello", "session_id": "quick-test-2", "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
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
            content = e.get("content", "")
            provider = e.get("provider")
            model_name = e.get("model")
            streamed = e.get("streamed")
            print(f"  ({elapsed:.1f}s) {content} [provider={provider}, model={model_name}, streamed={streamed}]")
            break
        elif etype == "chunk":
            text = e.get("content", "")[:50]
            print(f"  chunk: {text}")
        elif etype == "error":
            elapsed = time.time() - start
            msg = e.get("message", "")
            cat = e.get("category", "")
            print(f"  ({elapsed:.1f}s) ERROR [{cat}]: {msg}")
            break
        else:
            print(f"  {etype}: {json.dumps(e)[:100]}")

# Second call - follow-up
print("SSE follow-up...")
payload = json.dumps({"message": "What was my previous question?", "session_id": "quick-test-2", "stream": True, "model": "auto", "max_tokens": 50}).encode("utf-8")
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
            content = e.get("content", "")
            print(f"  ({elapsed:.1f}s) {content}")
            break
        elif etype == "error":
            elapsed = time.time() - start
            msg = e.get("message", "")
            cat = e.get("category", "")
            print(f"  ({elapsed:.1f}s) ERROR [{cat}]: {msg}")
            break
        elif etype == "chunk":
            text = e.get("content", "")[:50]
            print(f"  chunk: {text}")
        else:
            pass
