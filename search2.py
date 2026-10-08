# search
path = r'F:\AI\jarvis_err.log'
with open(path, encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f, 1):
        if 'refused' in line:
            print(i, line[:100])
            break
