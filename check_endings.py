path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/gateway.py'
with open(path, 'rb') as f:
    raw = f.read()
print(f'Total bytes: {len(raw)}')
crlf = b'\r\n'
lf = b'\n'
cr = b'\r'
print(f'CRLF count: {raw.count(crlf)}')
print(f'LF count: {raw.count(lf)}')
print(f'CR count: {raw.count(cr)}')
print(f'Pure LF (LF - CRLF): {raw.count(lf) - raw.count(crlf)}')
print(f'Pure CR (CR - CRLF): {raw.count(cr) - raw.count(crlf)}')

# Show bytes around stream_chat position
idx = raw.find(b'async def stream_chat(')
print(f'\nFound async def stream_chat at position {idx}')
print(repr(raw[idx:idx+300]))
