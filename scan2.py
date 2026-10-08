# look for specific keywords
found = []
for logname in ['jarvis_err.log', 'jarvis_out.log']:
    try:
        with open(r'F:\AI\\' + logname, encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                low = line.lower()
                if 'refused' in low or 'unauthorized' in low or 'forbidden' in low or ('developer' in low and 'account' in low):
                    found.append((logname, i+1, line[:150]))
                    if len(found) >= 10: break
            if len(found) >= 10: break
    except:
        pass
for f in found:
    print(f[0], f[1], f[2])
if not found:
    print('none')
