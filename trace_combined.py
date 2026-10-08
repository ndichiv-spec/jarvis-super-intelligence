import subprocess, os, sys, time, json, urllib.request
from dotenv import dotenv_values

env = dict(os.environ)
config = dotenv_values(r"F:\AI\.env")
for k, v in config.items():
    if v is not None and v.strip():
        env[k] = v
env["JARVIS_MODEL"] = "google:gemini-2.5-flash"
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
sys.stdout.flush()

for i in range(30):
    time.sleep(1)
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        print(f"Backend alive: {r.status}")
        sys.stdout.flush()
        break
    except Exception:
        if i % 5 == 4:
            print(f"  ...waiting ({i+1}s)")
            sys.stdout.flush()
else:
    print("Backend failed to start")
    sys.exit(1)

time.sleep(2)

# Login
BASE = "http://127.0.0.1:8000"
payload = json.dumps({"identifier": "ndichiv@gmail.com", "password": "videlis@254"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}, method="POST")
r = urllib.request.urlopen(req, timeout=10)
token = json.loads(r.read().decode())["access_token"]
print("Login OK")
sys.stdout.flush()

# Non-streaming with explicit model - print full response
print("\n=== Non-streaming: google:gemini-2.5-flash (full response) ===")
payload = json.dumps({"message": "What is 2+2?", "session_id": "debug1", "model": "google:gemini-2.5-flash", "stream": False}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/v1/ai/process", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    print(f"  ({elapsed:.1f}s) Status: {r.status}")
    print(f"  Full response: {json.dumps(result, indent=2)[:1000]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"  ({time.time()-start:.1f}s) HTTP {e.code}: {body[:500]}")
except Exception as e:
    print(f"  ({time.time()-start:.1f}s) Error: {type(e).__name__}: {e}")

sys.stdout.flush()

# SSE with explicit model - print all events
print("\n=== SSE: google:gemini-2.5-flash (all events) ===")
payload = json.dumps({"message": "What is 2+2?", "session_id": "debug2", "stream": True, "model": "google:gemini-2.5-flash", "max_tokens": 100}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/chat/stream", data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
start = time.time()
r = urllib.request.urlopen(req, timeout=30)
for line in r:
    chunk = line.decode("utf-8", errors="replace").strip()
    if chunk.startswith("data: "):
        e = json.loads(chunk[6:])
        elapsed = time.time() - start
        etype = e.get("type")
        if etype == "delta":
            text = e.get("text", "")[:80]
            print(f"  ({elapsed:.1f}s) delta: {text}")
        else:
            print(f"  ({elapsed:.1f}s) {etype}: {json.dumps(e)[:300]}")
        if etype in ("complete", "error"):
            break

print("\n=== DONE ===")
sys.stdout.flush()
