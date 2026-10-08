import subprocess, os, sys, time, json, urllib.request
from dotenv import dotenv_values

env = dict(os.environ)
config = dotenv_values(r"F:\AI\.env")
for k, v in config.items():
    if v is not None and v.strip():
        env[k] = v
env["JARVIS_MODEL"] = "nvidia:nemotron-3-ultra-550b-a55b"
env.pop("SILVERWING_ENDPOINT", None)

proc = subprocess.Popen(
    [sys.executable, "-u", r"Jarvis-super-intelligence-\jarvis_api.py"],
    cwd=r"F:\AI",
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
print(f"Backend PID: {proc.pid}")
for i in range(30):
    time.sleep(1)
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        print(f"Backend alive: {r.status}")
        break
    except Exception:
        if i % 5 == 4:
            print(f"  ...waiting ({i+1}s)")
else:
    print("Backend failed to start")
    sys.exit(1)

time.sleep(2)
BASE = "http://127.0.0.1:8000"

# Login
payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
r = urllib.request.urlopen(req, timeout=10)
token = json.loads(r.read().decode())["access_token"]
print("Login OK")

# === Test 1: Non-streaming with explicit NVIDIA model ===
print("\n=== Non-streaming: nvidia:nemotron-3-ultra-550b-a55b ===")
payload = json.dumps({"message": "What is 2+2?", "session_id": "test1", "model": "nvidia:nemotron-3-ultra-550b-a55b", "stream": False}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Status: {r.status}")
    print(f"  response: '{result.get('response')}'")
    print(f"  provider: {result.get('provider')}")
    print(f"  model: {result.get('model')}")
    print(f"  status: {result.get('status')}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"  ({time.time()-start:.1f}s) HTTP {e.code}: {body[:500]}")
except Exception as e:
    print(f"  ({time.time()-start:.1f}s) Error: {type(e).__name__}: {str(e)[:300]}")

sys.stdout.flush()

# === Test 2: SSE streaming with explicit NVIDIA model ===
print("\n=== SSE: nvidia:nemotron-3-ultra-550b-a55b (all events) ===")
payload = json.dumps({"message": "What is the capital of France?", "session_id": "test2", "stream": True, "model": "nvidia:nemotron-3-ultra-550b-a55b", "max_tokens": 100}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        elapsed = time.time() - start
        etype = e.get("type")
        if etype == "delta":
            print(f"  ({elapsed:.1f}s) delta: {e.get('text', '')[:60]}")
        elif etype == "complete":
            print(f"  ({elapsed:.1f}s) complete: {json.dumps(e)[:300]}")
        else:
            print(f"  ({elapsed:.1f}s) {etype}: {json.dumps(e)[:200]}")
        if etype in ("complete", "error"):
            break

sys.stdout.flush()

# === Test 3: SSE streaming with model=auto (default) ===
print("\n=== SSE: model=auto (default) ===")
payload = json.dumps({"message": "Count to 3.", "session_id": "test3", "stream": True}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=60)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        elapsed = time.time() - start
        etype = e.get("type")
        if etype == "delta":
            print(f"  ({elapsed:.1f}s) delta: {e.get('text', '')[:60]}")
        elif etype == "complete":
            print(f"  ({elapsed:.1f}s) complete: {json.dumps(e)[:300]}")
        else:
            print(f"  ({elapsed:.1f}s) {etype}: {json.dumps(e)[:200]}")
        if etype in ("complete", "error"):
            break

print("\n=== DONE ===")
sys.stdout.flush()
