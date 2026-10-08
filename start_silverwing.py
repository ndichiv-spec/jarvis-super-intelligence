import subprocess
import sys
import time
import os

sw_path = 'F:/AI/Jarvis-super-intelligence-/silverwing-backend'
print('Starting Silverwing backend...')

# Use uvicorn to start the Silverwing server
proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8010'],
    cwd=sw_path,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

print(f'Silverwing PID: {proc.pid}')
time.sleep(3)

# Check if it's running
import urllib.request
import json
try:
    with urllib.request.urlopen('http://127.0.0.1:8010/v1/health', timeout=5) as response:
        data = json.loads(response.read().decode())
        print('Silverwing Health:', json.dumps(data, indent=2))
except Exception as e:
    print('Health check error:', e)
    # Check process status
    poll = proc.poll()
    if poll is not None:
        stdout, stderr = proc.communicate()
        print('Process exited with code:', poll)
        print('Stdout:', stdout.decode()[:1000])
        print('Stderr:', stderr.decode()[:1000])
    else:
        print('Process is running')

# Keep the process reference
print('\nSilverwing server started in background, PID:', proc.pid)