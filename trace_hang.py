import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

# Login
payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
r = urllib.request.urlopen(req, timeout=10)
token = json.loads(r.read().decode())["access_token"]
print("Login OK")

# Test non-streaming with explicit google model (bypasses brain)
print("=== ai_process with google:gemini-2.5-flash ===")
payload = json.dumps({"message": "Hi", "session_id": "hang-test", "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    resp = result.get("response", "")
    print(f"  ({elapsed:.1f}s) {resp}")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")

# Test non-streaming with auto model (goes through brain -> fabric)
print("=== ai_process with auto model ===")
payload = json.dumps({"message": "Hi", "session_id": "hang-test", "model": "auto"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    resp = result.get("response", "")
    print(f"  ({elapsed:.1f}s) {resp}")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Error: {e}")
