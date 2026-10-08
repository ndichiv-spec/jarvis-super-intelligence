"""
Start the correct Silverwing runtime for inference testing
"""
import subprocess
import sys
import time
import urllib.request
import json

repo_root = 'F:/AI'
jarvis_dir = 'F:/AI/Jarvis-super-intelligence-'

print('Starting correct Silverwing runtime...')

# Apply environment
import os
os.environ.setdefault('SILVERWING_ENDPOINT', 'http://127.0.0.1:8010')
os.environ.setdefault('SILVERWING_MODEL', 'silverwing-120m-base-v1')
os.environ.setdefault('SILVERWING_TIMEOUT', '300')
os.environ.setdefault('SILVERWING_BACKEND', 'torch')

# Start silverwing_runtime.server
env = os.environ.copy()
env['PYTHONPATH'] = f'{repo_root};{jarvis_dir}'

proc = subprocess.Popen(
    [sys.executable, '-m', 'silverwing_runtime.server'],
    cwd=repo_root,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

print(f'Silverwing runtime PID: {proc.pid}')

# Wait for it to become healthy
for i in range(30):
    time.sleep(1)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f'Health check: {json.dumps(data)}')
            if data.get('status') == 'healthy':
                print('Silverwing runtime is HEALTHY!')
                break
    except Exception as e:
        if i < 5:
            print(f'Waiting... ({i+1}): {e}')
        elif i == 10:
            # Print process output for debugging
            poll = proc.poll()
            if poll is not None:
                stdout, _ = proc.communicate()
                print('Process exited:', stdout[:500])
            else:
                print('Process is running, waiting for health...')
else:
    print('Warning: Silverwing runtime did not become healthy in 30 seconds')

# Check if process is still running
poll = proc.poll()
if poll is not None:
    print('ERROR: Process exited early')
else:
    print(f'Silverwing runtime running on port 8010 (PID: {proc.pid})')