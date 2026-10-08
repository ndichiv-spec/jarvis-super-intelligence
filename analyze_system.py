import re

# Check the corrupted file
path = 'F:/AI/Jarvis-super-intelligence-/jarvis_backend/routers/system.py'
with open(path, 'r') as f:
    content = f.read()

lines = content.split('\n')
print(f'Corrupted file total lines: {len(lines)}')

# Find all "def " function definitions
funcs = []
for i, line in enumerate(lines):
    if line.strip().startswith('def ') or line.strip().startswith('async def '):
        funcs.append((i+1, line.strip()))

print(f'\nAll function definitions found ({len(funcs)} total):')
for ln, fn in funcs:
    print(f'{ln}: {fn}')

# Look for _confined_path
print('\n\nLooking for _confined_path and launch_app:')
found_confined = False
found_launch = False
for i, line in enumerate(lines):
    if '_confined_path' in line and 'def ' in line:
        print(f'Found _confined_path definition at line {i+1}')
        found_confined = True
    if 'launch_app' in line and 'def ' in line:
        print(f'Found launch_app definition at line {i+1}')
        found_launch = True

if not found_confined:
    print('WARNING: _confined_path NOT found in file!')
if not found_launch:
    print('WARNING: launch_app NOT found in file!')

# Show last 100 lines
print('\n\nLast 100 lines of file:')
for i in range(max(0, len(lines)-100), len(lines)):
    print(f'{i+1}: {lines[i][:100]}...' if len(lines[i]) > 100 else f'{i+1}: {lines[i]}')