import subprocess, os, sys, time

os.chdir(r"F:\AI")
env = dict(os.environ)
# Load .env manually to ensure Google API key is present
from dotenv import dotenv_values
config = dotenv_values(r"F:\AI\.env")
for k, v in config.items():
    if v is not None:
        env[k] = v

# Set the model explicitly to use gemini-2.5-flash (gemini-2.5-pro is deprecated)
env["JARVIS_MODEL"] = "google:gemini-2.5-flash"

proc = subprocess.Popen(
    [sys.executable, "jarvis_api.py"],
    cwd=r"F:\AI\Jarvis-super-intelligence-",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
print(f"Backend PID: {proc.pid}")

# Wait for startup
for i in range(30):
    time.sleep(1)
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        print(f"Backend alive: {r.status}")
        proc.stdout.close()
        break
    except Exception as e:
        if i % 5 == 4:
            print(f"  ...waiting ({i+1}s)")
else:
    print("Backend failed to start")
    sys.exit(1)

print("Backend started successfully")
