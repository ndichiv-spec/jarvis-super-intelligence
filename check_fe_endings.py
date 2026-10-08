path = r'F:\AI\Jarvis-super-intelligence-\frontend/web/src/components/real-ai-chat.tsx'
with open(path, 'rb') as f:
    raw = f.read()

crlf = raw.count(b'\r\n')
lf = raw.count(b'\n')
print(f'Total bytes: {len(raw)}')
print(f'CRLF count: {crlf}')
print(f'LF count: {lf}')
print(f'Pure LF: {lf - crlf}')

# Check specifically around the fallback block
idx = raw.find(b'setUsingLocalFallback(!data.enabled)')
if idx >= 0:
    print(f'\nFound setUsingLocalFallback(!data.enabled) at byte {idx}')
    snippet = raw[idx:idx+200]
    print(repr(snippet))
