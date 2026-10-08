import os
found = []
for root, dirs, files in os.walk(r'F:\AI'):
    for f in files:
        if f.endswith(('.txt', '.md', '.log', '.json', '.py', '.js', '.ts')):
            try:
                path = os.path.join(root, f)
                if os.path.getsize(path) > 5*1024*1024:
                    continue
                with open(path, encoding='utf-8', errors='replace') as fh:
                    for i, line in enumerate(fh, 1):
                        if 'refused' in line.lower() and ('login' in line.lower() or 'auth' in line.lower() or 'developer' in line.lower()):
                            found.append((path, i, line))
                            break
                if len(found) >= 10: break
            except:
                pass
    if len(found) >= 10: break
for p, i, l in found:
    print(f'{p}:{i}:{l}', end='')
