import sys

path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/chat_service.py'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

if '\r\n' in content:
    print("File uses CRLF line endings")
else:
    print("File uses LF line endings")

# FIX 5: stream_message should pass conversation history to stream_chat
# Currently it passes just `content` (the current message string)
# Change it to pass self._history(user_id, session_id) as `messages`
old_call = '''                if can_stream:
                    async for event in gateway.stream_chat(
                        content, model=model, user_id=user_id,
                        session_id=session_id, system=streaming_system,
                    ):'''

new_call = '''                if can_stream:
                    async for event in gateway.stream_chat(
                        model=model, user_id=user_id,
                        session_id=session_id, system=streaming_system,
                        messages=self._history(user_id, session_id),
                    ):'''

if old_call not in content:
    print("FAIL: old_call not found")
    # Show what's actually there
    idx = content.find('async for event in gateway.stream_chat(')
    if idx >= 0:
        print(repr(content[idx:idx+200]))
    sys.exit(1)
content = content.replace(old_call, new_call)
print("FIX 5 applied: stream_message now passes conversation history to stream_chat")

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("chat_service.py fixes written successfully")
