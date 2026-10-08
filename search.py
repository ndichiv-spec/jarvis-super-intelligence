import os
for logname in ['jarvis_err.log', 'jarvis_out.log', 'jarvis_frontend_err.log', 'jarvis_frontend_out.log']:
    path = os.path.join(r'F:\AI', logname)
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                low = line.lower()
                if 'refused' in low or ('developer' in low and 'login' in low) or 'dev login' in low:
                    print(f'=== {logname}:{i} ===')
                    print(line)
                    break
    except Exception as e:
        pass
