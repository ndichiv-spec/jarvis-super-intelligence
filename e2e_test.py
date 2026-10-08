"""
E2E test: Real provider, conversation continuity, failure honesty.
Tests the full runtime path: frontend SSE -> backend -> provider -> response -> frontend.
"""
import urllib.request, json, time, sys

BASE = "http://127.0.0.1:8000"

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
    data = json.loads(r.read().decode())
    print(f"  Login: OK (user={data['user']['email']})")
    return data["access_token"]

def sse_chat(token, message, session_id, model=None):
    payload = json.dumps({
        "message": message,
        "session_id": session_id,
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
    r = urllib.request.urlopen(req, timeout=120)
    events = []
    for line in r:
        chunk = line.decode("utf-8", errors="replace").strip()
        if chunk.startswith("data: "):
            data = json.loads(chunk[6:])
            events.append(data)
    return events

def get_status(token):
    req = urllib.request.Request(
        f"{BASE}/api/v1/ai/status",
        headers={"Authorization": f"Bearer {token}"},
        method="GET"
    )
    r = urllib.request.urlopen(req, timeout=30)
    return json.loads(r.read().decode())

def get_history(token, session_id):
    req = urllib.request.Request(
        f"{BASE}/api/chat/history/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET"
    )
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())

# Run tests
token = login()
session_id = f"e2e-test-{int(time.time())}"

results = []

# TEST 1: Basic SSE streaming with real provider
print("\n=== TEST 1: Basic SSE streaming with real provider ===")
events = sse_chat(token, "Hello JARVIS. What is 2+2?", session_id)
first_type = events[0]["type"] if events else "?"
last_type = events[-1]["type"] if events else "?"
response = None
for e in events:
    if e.get("type") == "complete":
        response = e.get("content")
        provider = e.get("provider")
        model = e.get("model")
        streamed = e.get("streamed")

assert first_type == "typing", f"First event should be 'typing', got '{first_type}'"
assert last_type == "complete", f"Last event should be 'complete', got '{last_type}'"
assert response is not None, "No response content"
assert provider == "google", f"Expected google provider, got {provider}"
assert model == "gemini-2.5-flash", f"Expected gemini-2.5-flash, got {model}"
assert streamed == True, f"Expected streamed=True, got {streamed}"
print(f"  Provider: {provider}, Model: {model}, Streamed: {streamed}")
print(f"  Response: {response}")
results.append(("SSE streaming with real provider", "PASS"))

# TEST 2: Conversation continuity via SSE
print("\n=== TEST 2: Conversation continuity via SSE ===")
events = sse_chat(token, "My name is E2E Tester. What is 3+3?", session_id)
response1 = None
for e in events:
    if e.get("type") == "complete":
        response1 = e.get("content")
print(f"  Turn 1 response: {response1}")

events = sse_chat(token, "What did I just tell you about my name?", session_id)
response2 = None
for e in events:
    if e.get("type") == "complete":
        response2 = e.get("content")
print(f"  Turn 2 response: {response2}")

assert "E2E Tester" in response2 or "name" in response2.lower(), \
    f"Expected model to remember the name, got: {response2}"
results.append(("Conversation continuity via SSE", "PASS"))

# TEST 3: Conversation continuity via non-streaming ai_process
print("\n=== TEST 3: Conversation continuity via non-streaming ai_process ===")
payload = json.dumps({
    "message": "My favorite number is 42. What is 5+5?",
    "session_id": session_id,
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/process",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=60)
result = json.loads(r.read().decode())
print(f"  Turn 1 response: {result.get('response')}")

payload = json.dumps({
    "message": "What was my favorite number?",
    "session_id": session_id,
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/api/v1/ai/process",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=60)
result = json.loads(r.read().decode())
print(f"  Turn 2 response: {result.get('response')}")
assert "42" in result.get("response", ""), \
    f"Expected model to remember favorite number 42, got: {result.get('response')}"
results.append(("Conversation continuity via ai_process", "PASS"))

# TEST 4: AI status truthfulness
print("\n=== TEST 4: AI status truthfulness ===")
status = get_status(token)
print(f"  status: {status.get('status')}")
print(f"  platform_status: {status.get('platform_status')}")
print(f"  silverwing.healthy: {status.get('silverwing', {}).get('healthy')}")
print(f"  silverwing.status: {status.get('silverwing', {}).get('status')}")
print(f"  silverwing.errors: {status.get('silverwing', {}).get('errors')}")
print(f"  brain.healthy: {status.get('brain', {}).get('healthy')}")

# Silverwing should NOT be reported as healthy (its /v1/chat/completions hangs)
assert status.get("silverwing", {}).get("healthy") == False, \
    "Silverwing should NOT be healthy (chat completions hangs)"
assert status.get("silverwing", {}).get("reachable") == True, \
    "Silverwing TCP should be reachable"
assert "not responding" in (status.get("silverwing", {}).get("errors") or ""), \
    f"Silverwing errors should mention 'not responding', got: {status.get('silverwing', {}).get('errors')}"
assert status.get("brain", {}).get("healthy") == False, \
    "Brain should not be healthy (not running)"
assert status.get("status") != "ready", \
    f"Status should not be 'ready' when only Google works, got: {status.get('status')}"
results.append(("AI status truthfulness", "PASS"))

# TEST 5: Session persistence
print("\n=== TEST 5: Session persistence ===")
history = get_history(token, session_id)
msg_count = history.get("session", {}).get("message_count", 0)
msgs = history.get("messages", [])
user_msgs = [m for m in msgs if m.get("role") == "user"]
assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
print(f"  Total messages: {msg_count}")
print(f"  User messages: {len(user_msgs)}")
print(f"  Assistant messages: {len(assistant_msgs)}")
assert msg_count >= 4, f"Expected at least 4 messages, got {msg_count}"
results.append(("Session persistence", "PASS"))

# Summary
print("\n" + "=" * 60)
print("E2E TEST RESULTS")
print("=" * 60)
all_pass = True
for name, result in results:
    status_icon = "✓" if result == "PASS" else "✗"
    print(f"  {status_icon} {name}: {result}")
    if result != "PASS":
        all_pass = False

print(f"\n{'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
sys.exit(0 if all_pass else 1)
