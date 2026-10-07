import re

with open('jarvis_backend/routers/browser.py', 'r') as f:
    content = f.read()
lines = content.split('\n')

# Find route function definitions and show the return statements
route_pattern = re.compile(r'@router\.(?:get|post|put|delete)\("([^"]+)"')
func_pattern = re.compile(r'async def (\w+)\(')

# Find all function names and their line numbers
for i, line in enumerate(lines, 1):
    m = func_pattern.match(line)
    if m:
        name = m.group(1)
        if name not in ('__init__',):
            # Find the route decorator just before (within 5 lines)
            found_route = False
            for j in range(i-1, max(0, i-10), -1):
                rm = route_pattern.search(lines[j-1])
                if rm:
                    route_path = rm.group(1)
                    found_route = True
                    break
            if found_route:
                print(f"  {route_path} -> {name}()")
