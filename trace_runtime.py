import urllib.request, json, sys

BASE = "http://127.0.0.1:8000"
SESSION_ID = "audit-trace-001"

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
    token = body["access_token"]
    print("=== LOGIN === OK, got token")
    return token

def ai_process(token, message, stream=False, model=None):
    payload = json.dumps({
        "message": message,
        "session_id": SESSION_ID,
        "model": model or "auto",
        "stream": stream,
        "max_tokens": 100,
        "temperature": 0.7
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/v1/ai/process",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST"
    )
    if stream:
        r = urllib.request.urlopen(req, timeout=30)
        return r  # streaming response
    else:
        body = json.loads(r.read().decode("utf-8", errors="replace"))
        return body

token = login()

# Test 1: Non-streaming first message
print("\n=== TEST 1: Non-streaming — 'Hello JARVIS. My name is Test.' ===")
try:
    resp = ai_process(token, "Hello JARVIS. My name is Test.", stream=False)
    print("Response:", json.dumps(resp, indent=2, ensure_ascii=False)[:3000])
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:3000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Second message — conversation continuity
print("\n=== TEST 2: Non-streaming — 'What did I just tell you?' ===")
try:
    resp = ai_process(token, "What did I just tell you?", stream=False)
    print("Response:", json.dumps(resp, indent=2, ensure_ascii=False)[:3000])
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:2000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Streaming
print("\n=== TEST 3: Streaming — 'What is the capital of France?' ===")
try:
    r = ai_process(token, "What is the capital of France?", stream=True)
    print(f"Status: {r.status}")
    content_type = r.headers.get("Content-Type", "")
    print(f"Content-Type: {content_type}")
    chunks = []
    for line in r:
        chunk = line.decode("utf-8", errors="replace")
        chunks.append(chunk)
        print(f"  CHUNK: {chunk[:200]}")
    print(f"Total chunks: {len(chunks)}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print("Body:", e.read().decode("utf-8", errors="replace")[:2000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
