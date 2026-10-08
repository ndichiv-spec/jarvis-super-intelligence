import sys
import os
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

# Check environment variables for AI configuration
print('=== AI Configuration Check ===')
print('SILVERWING_ENDPOINT:', os.environ.get('SILVERWING_ENDPOINT', 'NOT SET'))
print('JARVIS_BRAIN_ENDPOINT:', os.environ.get('JARVIS_BRAIN_ENDPOINT', 'NOT SET'))
print('JARVIS_MODEL:', os.environ.get('JARVIS_MODEL', 'NOT SET'))
print('OPENAI_API_KEY:', 'SET' if os.environ.get('OPENAI_API_KEY') else 'NOT SET')
print('NVIDIA_API_KEY:', 'SET' if os.environ.get('NVIDIA_API_KEY') else 'NOT SET')

# Check if any cloud keys are configured
from pathlib import Path
env_file = Path('F:/AI/Jarvis-super-intelligence-/.env')
if env_file.exists():
    print('\n.env file exists:', env_file)
else:
    print('\n.env file NOT FOUND')