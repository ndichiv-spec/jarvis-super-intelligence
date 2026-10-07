import subprocess
import os

os.chdir(r'F:/AI/Jarvis-super-intelligence-')

# Get the original content from git
result = subprocess.run(['git', 'show', 'HEAD:jarvis_backend/chat_service.py'], 
                       capture_output=True, text=True)
if result.returncode == 0:
    print("Successfully retrieved original file from git")
    print(f"Length: {len(result.stdout)} bytes")
    # Save it
    with open(r'F:/AI/Jarvis-super-intelligence-/jarvis_backend/chat_service.py', 'w') as f:
        f.write(result.stdout)
    print("File restored")
else:
    print(f"Error: {result.stderr}")