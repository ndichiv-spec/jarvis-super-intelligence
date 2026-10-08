found = False
for logname in ['jarvis_err.log', 'jarvis_out.log', 'jarvis_frontend_err.log', 'jarvis_frontend_out.log']:
    try:
        with open(r'F:\AI\\' + logname, encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if 'refuse' in line.lower():
                    print(logname, i+1)
                    print(line)
                    found = True
                    break
            if found: break
    except Exception:
        pass
if not found:
    print('none')
