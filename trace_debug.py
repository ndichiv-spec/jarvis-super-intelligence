import urllib.request, json, time

BASE = "http://127.0.0.1:8000"

def login():
    payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read().decode())["access_token"]

token = login()
session_id = f"debug-test-{int(time.time())}"

# Test non-streaming with explicit google model to bypass brain
print("=== Non-streaming with google:gemini-2.5-flash ===")
payload = json.dumps({"message": "Hello, my name is Debug.", "session_id": session_id, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) Response: {result.get('response')}")

# Second call with same session
print("\n=== Non-streaming follow-up (checking continuity) ===")
payload = json.dumps({"message": "What did I just tell you?", "session_id": session_id, "model": "google:gemini-2.5-flash"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
elapsed = time.time() - start
result = json.loads(r.read().decode())
print(f"  ({elapsed:.1f}s) Response: {result.get('response')}")

# Check backend logs for clues
print("\n=== Checking backend for any issues ===")
import os
pid = None
# Find the backend PID
import subprocess
result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'], capture_output=True, text=True)
print(f"Python processes:\n{result.stdout[:500]}")
