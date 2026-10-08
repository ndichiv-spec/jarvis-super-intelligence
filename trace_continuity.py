import urllib.request, json

BASE = "http://127.0.0.1:8000"
SESSION_ID = "audit-trace-continuity"

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

def sse_chat(token, message, model=None):
    """Send a message via the SSE streaming endpoint and collect all events."""
    payload = json.dumps({
        "message": message,
        "session_id": SESSION_ID,
        "stream": True,
        "model": model or "auto",
        "max_tokens": 100,
        "temperature": 0.7
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=60)
    events = []
    for line in r:
        chunk = line.decode("utf-8", errors="replace").strip()
        if chunk.startswith("data: "):
            data = json.loads(chunk[6:])
            events.append(data)
    return events

token = login()
print("=== Login OK ===")

# Test 1: Set up context
print("\n=== TEST 1: SSE — My name is Test ===")
events = sse_chat(token, "My name is Test. What is 2+2?")
for e in events:
    print(f"  {e.get('type', '?')}: {json.dumps(e)[:200]}")

# Test 2: Conversation continuity
print("\n=== TEST 2: SSE — What did I just tell you? ===")
events = sse_chat(token, "What did I just tell you?")
for e in events:
    print(f"  {e.get('type', '?')}: {json.dumps(e)[:200]}")

# Test 3: Check conversation history
print("\n=== TEST 3: Check session history ===")
req = urllib.request.Request(
    f"{BASE}/api/chat/history/{SESSION_ID}",
    headers={"Authorization": f"Bearer {token}"},
    method="GET"
)
r = urllib.request.urlopen(req, timeout=10)
history = json.loads(r.read().decode())
print(json.dumps(history, indent=2)[:2000])
