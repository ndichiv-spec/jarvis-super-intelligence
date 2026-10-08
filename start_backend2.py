import subprocess, os, sys, time
from dotenv import dotenv_values

env = dict(os.environ)
config = dotenv_values(r"F:\AI\.env")
for k, v in config.items():
    if v is not None and v.strip():
        env[k] = v

# Use a model that's actually available
env["JARVIS_MODEL"] = "google:gemini-2.5-flash"
# Don't set SILVERWING_ENDPOINT so the HTTP runtime path is skipped
env.pop("SILVERWING_ENDPOINT", None)
env.pop("SILVERWING_MODEL", None)
env.pop("SILVERWING_TIMEOUT", None)

# Start backend from workspace root so load_dotenv finds F:\AI/.env
proc = subprocess.Popen(
    [sys.executable, r"Jarvis-super-intelligence-\jarvis_api.py"],
    cwd=r"F:\AI",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
print(f"Backend PID: {proc.pid}")

for i in range(30):
    time.sleep(1)
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        print(f"Backend alive: {r.status}")
        break
    except Exception:
        if i % 5 == 4:
            print(f"  ...waiting ({i+1}s)")
else:
    print("Backend failed to start")
    sys.exit(1)
