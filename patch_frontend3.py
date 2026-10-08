path = r'F:\AI\Jarvis-super-intelligence-\frontend/web/src/components/real-ai-chat.tsx'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# Fix the status mapping: currently maps "ready" -> "online", everything else -> "offline"
# Should map "ready" -> "online", "degraded" -> "degraded", else -> "offline"
old_mapping = 'status: data.status === "ready" ? "online" : "offline",'
new_mapping = 'status: data.status === "ready" ? "online" : (data.status === "degraded" ? "degraded" : "offline"),'

if old_mapping in content:
    content = content.replace(old_mapping, new_mapping)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print('FIX applied: status mapping now handles "degraded" state')
else:
    # Try with LF
    old_mapping_lf = old_mapping
    new_mapping_lf = new_mapping
    if old_mapping_lf in content:
        content = content.replace(old_mapping_lf, new_mapping_lf)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        print('FIX applied (LF): status mapping now handles "degraded" state')
    else:
        print('WARN: status mapping not found (already modified?)')
        idx = content.find('data.status ===')
        if idx >= 0:
            print(repr(content[idx-20:idx+100]))
