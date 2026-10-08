import subprocess, time, os, sys, json, urllib.request

JARVIS_DIR = r'F:\AI\Jarvis-super-intelligence-'
os.chdir(JARVIS_DIR)

# Kill any existing processes
subprocess.run(['taskkill', '/f', '/im', 'python.exe'], capture_output=True)
time.sleep(2)

# Start backend
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
    except:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors='replace')
            print(f'Backend exited! {out[:3000]}')
            sys.exit(1)
else:
    print('Backend did not start')
    sys.exit(1)

# Login
payload = json.dumps({'identifier': 'ndichiv@gmail.com', 'password': 'videlis@254'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
r = urllib.request.urlopen(req, timeout=10)
token = json.loads(r.read().decode())['access_token']
print('Login OK')

# Test 1: ai_process with auto model
print('=== ai_process auto model ===')
payload = json.dumps({'message': 'What is 2+2?', 'session_id': 'debug-test1', 'model': 'auto', 'stream': False}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/ai/process', data=payload, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='POST')
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    resp = result.get('response')
    print(f'  ({elapsed:.1f}s) Response: {resp}')
except Exception as e:
    elapsed = time.time() - start
    print(f'  ({elapsed:.1f}s) Error: {e}')

# Test 2: Follow-up with same session
print('=== ai_process follow-up ===')
payload = json.dumps({'message': 'What did I ask?', 'session_id': 'debug-test1', 'model': 'auto', 'stream': False}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/ai/process', data=payload, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='POST')
start = time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
    result = json.loads(r.read().decode())
    elapsed = time.time() - start
    resp = result.get('response')
    print(f'  ({elapsed:.1f}s) Response: {resp}')
except Exception as e:
    elapsed = time.time() - start
    print(f'  ({elapsed:.1f}s) Error: {e}')

print(f'Backend alive: {proc.poll() is None}')
