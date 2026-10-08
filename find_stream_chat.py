path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/gateway.py'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# Find the actual stream_chat method text
idx = content.find('async def stream_chat(')
# Find the end of the method (next def at same indent level or end of class)
end_idx = content.find('\r\n    async def ', idx + 10)
if end_idx == -1:
    end_idx = content.find('\r\n\r\n    def ', idx + 10)
print(f"Method at position {idx}, ends around {end_idx}")
snippet = content[idx:idx+1200]
print(repr(snippet))
