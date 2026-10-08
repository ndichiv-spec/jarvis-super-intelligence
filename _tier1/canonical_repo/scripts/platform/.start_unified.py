"""Start JARVIS platform with the Brain runtime connected to NVIDIA NIM as the remote provider."""
import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path
import urllib.request
import urllib.error
import json

ROOT = Path("F:/AI")
JARVIS_DIR = ROOT / "Jarvis-super-intelligence-"

# Add to path
for p in [str(ROOT), str(JARVIS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env
env_file = ROOT / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                idx = line.find('=')
                if idx > 0:
                    k = line[:idx]
                    v = line[idx+1:]
                    if v:
                        os.environ[k] = v

# Configure Brain runtime with NVIDIA NIM as remote backend
# (.env values were loaded above and win; these are fallback defaults only).
os.environ.setdefault("JARVIS_BRAIN_BACKEND", "remote")
os.environ.setdefault(
    "JARVIS_BRAIN_REMOTE_ENDPOINT",
    os.environ.get("JARVIS_NVIDIA_ENDPOINT", "https://integrate.api.nvidia.com/v1"),
)
os.environ.setdefault(
    "JARVIS_BRAIN_REMOTE_API_KEY",
    os.environ.get("JARVIS_NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY", ""),
)
os.environ.setdefault(
    "JARVIS_BRAIN_REMOTE_MODEL",
    os.environ.get("JARVIS_NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
)
os.environ.setdefault("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8011/v1")
os.environ.setdefault("JARVIS_BRAIN_API_KEY", "brain-secret-key-JARVIS-123456")
os.environ.setdefault("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1")
os.environ.setdefault("JARVIS_BRAIN_REMOTE_TIMEOUT", "120")

# Platform env
os.environ.setdefault("PYTHONPATH", str(ROOT) + ";" + str(JARVIS_DIR))
os.environ.setdefault("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")
os.environ.setdefault("SILVERWING_MODEL", "silverwing-120m-base-v1")
os.environ.setdefault("SILVERWING_BACKEND", "torch")
os.environ.setdefault("JARVIS_SECRET_KEY", "d2657854d2a143b35b2c0cfe9c730dc491d95e935bab20dbb6b6fc21db772c99")

print(f"[env] JARVIS_BRAIN_BACKEND = {os.environ['JARVIS_BRAIN_BACKEND']}")
print(f"[env] JARVIS_BRAIN_REMOTE_ENDPOINT = {os.environ['JARVIS_BRAIN_REMOTE_ENDPOINT']}")
print(f"[env] JARVIS_BRAIN_REMOTE_API_KEY = {'<set>' if os.environ.get('JARVIS_BRAIN_REMOTE_API_KEY') else '<UNSET>'}")
print(f"[env] JARVIS_BRAIN_REMOTE_MODEL = {os.environ.get('JARVIS_BRAIN_REMOTE_MODEL', '(unset)')}")
print(f"[env] JARVIS_NVIDIA_API_KEY = {'<set>' if os.environ.get('JARVIS_NVIDIA_API_KEY') else '<UNSET>'}")

def _stream(name, proc):
    if proc.stdout is None:
        return
    try:
        for raw in iter(proc.stdout.readline, ""):
            line = raw.rstrip("\n")
            if line:
                print(f"[{name}] {line}", flush=True)
    except (ValueError, OSError):
        pass

def http_json(url, headers=None, timeout=5.0):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace")) if e.fp else None
    except Exception as e:
        return 0, {"error": str(e)}

def wait_for(url, label, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, data = http_json(url, timeout=3)
        if code:
            print(f"[ok] {label} up: HTTP {code}", flush=True)
            return True
        time.sleep(2)
    print(f"[warn] {label} not up after {timeout}s", flush=True)
    return False

procs = []
def cleanup(signum=None, frame=None):
    for p in procs:
        try:
            p.terminate()
        except:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

env = os.environ.copy()
env["PYTHONPATH"] = str(ROOT) + ";" + str(JARVIS_DIR)

# Enable the real browser/search path on the platform child so the
# live research fabric can reach the Internet via HttpBrowserEngine.
# Left OUT of .env (unit-test env stays gated -> BROWSER_UNAVAILABLE).  See
# tests/test_tool_registry.py:100 and research_engine/tool_registry.py.
env["JARVIS_BROWSER_SEARCH_ENABLED"] = "1"

# 1. Start Brain runtime (:8011) with remote backend
print("[start] Brain runtime (:8011) with remote backend (NVIDIA NIM)...", flush=True)
brain_proc = subprocess.Popen(
    [sys.executable, "-m", "brain_runtime.server"],
    cwd=str(ROOT),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)
procs.append(brain_proc)
threading.Thread(target=_stream, args=("brain", brain_proc), daemon=True).start()

# Wait for brain to start
time.sleep(5)
code, data = http_json("http://127.0.0.1:8011/health", timeout=3)
if code:
    print(f"[brain] health: HTTP {code}, status={data.get('status')}, available={data.get('available')}, backend={data.get('backend')}", flush=True)

# 2. Start Silverwing runtime (:8010)
print("[start] Silverwing runtime (:8010)...", flush=True)
sw_env = env.copy()
sw_proc = subprocess.Popen(
    [sys.executable, "-m", "silverwing_runtime.server"],
    cwd=str(ROOT),
    env=sw_env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)
procs.append(sw_proc)
threading.Thread(target=_stream, args=("runtime", sw_proc), daemon=True).start()

if not wait_for("http://127.0.0.1:8010/v1/health", "runtime", timeout=120):
    pass

# 3. Start platform (:8000)
print("[start] JARVIS platform (:8000)...", flush=True)
platform_proc = subprocess.Popen(
    [sys.executable, "jarvis_api.py"],
    cwd=str(JARVIS_DIR),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)
procs.append(platform_proc)
threading.Thread(target=_stream, args=("platform", platform_proc), daemon=True).start()

if not wait_for("http://127.0.0.1:8000/health", "platform", timeout=90):
    pass

# Final status
print("\n=== STATUS ===", flush=True)
for name, url in [("brain", "http://127.0.0.1:8011/health"), ("runtime", "http://127.0.0.1:8010/v1/health"), ("platform", "http://127.0.0.1:8000/health")]:
    code, data = http_json(url, timeout=3)
    if code:
        status = data.get("status", "?")
        available = data.get("available", False) if data else False
        backend = data.get("backend", "?")
        print(f"  {name}: UP (HTTP {code}, status={status}, available={available}, backend={backend})", flush=True)
    else:
        print(f"  {name}: DOWN", flush=True)

print("\nAll services started. Press Ctrl-C to stop.", flush=True)
try:
    while True:
        time.sleep(2)
except KeyboardInterrupt:
    cleanup()
