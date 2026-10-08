p = "jarvis_backend/chat_service.py"
L = open(p, encoding="utf-8").read().split("\n")
print(f"chat_service.py = {len(L)} lines")
print("\n--- lines containing 'stream_message' or 'def stream' or 'ChatStreamChunk' ---")
for i, l in enumerate(L):
    if "stream_message" in l or "def stream" in l or "ChatStreamChunk" in l:
        print(f"{i+1:5d}| {l}")
print("\n--- lines containing 'yield' or '\"type\"' or \"'type'\" ---")
for i, l in enumerate(L):
    if ("yield" in l) or ('"type"' in l) or ("'type'" in l):
        print(f"{i+1:5d}| {l}")
