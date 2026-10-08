import os

backend_plan = r'F:\AI\Jarvis-super-intelligence-\docs\backend\BACKEND_UPGRADE_PLAN.md'
print('=== BACKEND PLAN ===')
print(f'File: {backend_plan}')
print(f'Exists: {os.path.exists(backend_plan)}')
print(f'Size: {os.path.getsize(backend_plan)} bytes')
with open(backend_plan, 'rb') as f:
    raw = f.read()
text = raw.decode('utf-8', errors='replace')
lines = text.split(chr(10))
print(f'Lines: {len(lines)}')

frontend_plan = r'F:\AI\Jarvis-super-intelligence-\docs/frontend/FRONTEND_UPGRADE_PLAN.md'
with open(frontend_plan, 'rb') as f:
    raw = f.read()
text2 = raw.decode('utf-8', errors='replace')
lines2 = text2.split(chr(10))
print(f'\n=== FRONTEND PLAN ===')
print(f'Lines: {len(lines2)}')
print(f'Cross-ref BACKEND_UPGRADE_PLAN: {"BACKEND_UPGRADE_PLAN" in text2}')
print(f'Mentions tsc: {"tsc" in text2}')
print(f'Mentions pytest: {"pytest" in text2}')

# Check section headers in backend plan
print(f'\n=== BACKEND PLAN SECTIONS ===')
for line in lines:
    stripped = line.strip()
    if stripped.startswith('## ') and len(stripped) < 100:
        print(f'  {stripped}')
