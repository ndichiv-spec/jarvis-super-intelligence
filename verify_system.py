import py_compile
import re

path = 'F:/AI/Jarvis-super-intelligence-/jarvis_backend/routers/system.py'
with open(path, 'r') as f:
    content = f.read()

lines = content.split('\n')
print(f'Total lines: {len(lines)}')

# Verify syntax
try:
    py_compile.compile(path, doraise=True)
    print('Syntax: VALID')
except py_compile.PyCompileError as e:
    print(f'Syntax ERROR: {e}')
    exit(1)

# Check for all expected functions
expected_funcs = [
    '_confined_path', 'launch_app', 'system_status', 'capabilities', 
    'system_dashboard', 'list_processes', 'kill_process', 
    'get_provider_settings', 'update_provider_settings', 
    'list_files', 'read_file', 'get_clipboard', 'set_clipboard',
    '_audit_system_launch', 'take_screenshot', 'list_windows', 'file_structure'
]

print('\nFunction coverage:')
for func in expected_funcs:
    found = f'def {func}' in content or f'async def {func}' in content
    status = 'OK' if found else 'MISSING'
    print(f'  [{status}] {func}')

# Check for _DENY_COMMANDS
if '_DENY_COMMANDS' in content:
    print('\n_DENY_COMMANDS: OK')
else:
    print('\n_DENY_COMMANDS: MISSING')

# Check for _SECRET_SHAPES
if '_SECRET_SHAPES' in content:
    print('_SECRET_SHAPES: OK')
else:
    print('_SECRET_SHAPES: MISSING')

# Count duplicated docstrings
doc_count = content.count('"""System control, processes')
print(f'\nDocstring duplication count: {doc_count}')

# Count duplicated router definitions
router_count = content.count('router = APIRouter(prefix="/api/v1/system"')
print(f'Router definition count: {router_count}')