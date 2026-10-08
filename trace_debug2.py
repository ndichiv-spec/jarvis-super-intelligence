import subprocess, time, os, sys, threading, json, urllib.request

JARVIS_DIR = r'F:\AI\Jarvis-super-intelligence-'
os.chdir(JARVIS_DIR)

# Start backend with logging
proc = subprocess.Popen(
    [sys.executable, 'jarvis_api.py'],
    cwd=JARVIS_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env={**os.environ, 'PYTHONUNBUFFERED': '1'},
)
print(f'Backend started, PID={proc.pid}')

# Wait for ready
for i in range(30):
    time.sleep(2)
    try:
        r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)
        print(f'Backend ready (attempt {i+1})')
        break
    except Exception as e:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors='replace')
            print(f'Backend exited! Output:\n{out[:5000]}')
            sys.exit(1)
        if i % 5 == 4:
            print(f'  Waiting... ({e})')
else:
    print('Backend did not start')
    sys.exit(1)

# Now test login
print('\n=== Login test ===')
payload = json.dumps({
    "identifier": "ndichiv@gmail.com",
    "password": "videlis@254"
}).encode("utf-8")
req = urllib.request.Request(
    f'http://127.0.0.1:8000/api/v1/auth/login',
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=10)
data = json.loads(r.read().decode())
token = data["access_token"]
print(f'Login OK')

# Test ai_process with auto model (should go through brain -> fabric)
print('\n=== ai_process test (auto model) ===')
payload = json.dumps({
    "message": "Hello, what is 2+2?",
    "session_id": "debug-auto-test",
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f'http://127.0.0.1:8000/api/v1/ai/process',
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    elapsed = time.time() - start
    result = json.loads(r.read().decode())
    print(f'  ({elapsed:.1f}s) Response: {result.get("response")}')
    print(f'  Model: {result.get("model")}, Provider: {result.get("provider")}')
except Exception as e:
    elapsed = time.time() - start
    print(f'  ({elapsed:.1f}s) Error: {e}')

# Test follow-up with same session
print('\n=== ai_process follow-up (auto model) ===')
payload = json.dumps({
    "message": "What did I just ask?",
    "session_id": "debug-auto-test",
    "model": "auto",
    "stream": False
}).encode("utf-8")
req = urllib.request.Request(
    f'http://127.0.0.1:8000/api/v1/ai/process',
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    method="POST"
)
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    elapsed = time.time() - start
    result = json.loads(r.read().decode())
    print(f'  ({elapsed:.1f}s) Response: {result.get("response")}')
    print(f'  Model: {result.get("model")}, Provider: {result.get("provider")}')
except Exception as e:
    elapsed = time.time() - start
    print(f'  ({elapsed:.1f}s) Error: {e}')

# Check if backend is still alive
print(f'\nBackend alive: {proc.poll() is None}')

# Read any output
import select
ready, _, _ = select.select([proc.stdout], [], [], 0)
if ready:
    out = proc.stdout.read1(4096).decode(errors='replace')
    print(f'\nBackend output tail:\n{out[-2000:]}')
