import sys

path = r'F:\AI\Jarvis-super-intelligence-\frontend/web/src/components/real-ai-chat.tsx'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# Detect line endings
CRLF = '\r\n' if '\r\n' in content else '\n'
print(f"File uses {'CRLF' if CRLF == chr(13)+chr(10) else 'LF'} line endings")

# FIX 1: Expand SendLifecycle type to include missing states
# Current type:
# type SendLifecycle =
#   | "IDLE"
#   | "THINKING"
#   | "STREAMING"
#   | "COMPLETED"
#   | "PROVIDER_UNAVAILABLE"
#   | "OFFLINE"
#   | "RATE_LIMITED"
#   | "FAILED"
#   | "STREAM_INTERRUPTED";
old_type = (
    'type SendLifecycle =\r\n'
    '  | "IDLE"\r\n'
    '  | "THINKING"\r\n'
    '  | "STREAMING"\r\n'
    '  | "COMPLETED"\r\n'
    '  | "PROVIDER_UNAVAILABLE"\r\n'
    '  | "OFFLINE"\r\n'
    '  | "RATE_LIMITED"\r\n'
    '  | "FAILED"\r\n'
    '  | "STREAM_INTERRUPTED";'
)

new_type = (
    'type SendLifecycle =\r\n'
    '  | "IDLE"\r\n'
    '  | "CONNECTING"\r\n'
    '  | "THINKING"\r\n'
    '  | "STREAMING"\r\n'
    '  | "TOOL_EXECUTION"\r\n'
    '  | "COMPLETED"\r\n'
    '  | "PROVIDER_UNAVAILABLE"\r\n'
    '  | "OFFLINE"\r\n'
    '  | "RATE_LIMITED"\r\n'
    '  | "NETWORK_ERROR"\r\n'
    '  | "AUTH_REQUIRED"\r\n'
    '  | "FAILED"\r\n'
    '  | "STREAM_INTERRUPTED";'
)

if old_type not in content:
    # Try LF
    old_type_lf = old_type.replace('\r\n', '\n')
    new_type_lf = new_type.replace('\r\n', '\n')
    if old_type_lf in content:
        content = content.replace(old_type_lf, new_type_lf)
        print("FIX 1 applied (LF): SendLifecycle expanded with CONNECTING, TOOL_EXECUTION, NETWORK_ERROR, AUTH_REQUIRED")
    else:
        print("FAIL: SendLifecycle type not found")
        # Show what's actually there
        idx = content.find('type SendLifecycle')
        if idx >= 0:
            print(repr(content[idx:idx+300]))
        sys.exit(1)
else:
    content = content.replace(old_type, new_type)
    print("FIX 1 applied (CRLF): SendLifecycle expanded with CONNECTING, TOOL_EXECUTION, NETWORK_ERROR, AUTH_REQUIRED")

# FIX 2: Update LIFECYCLE_LABEL to include new states
old_label = (
    'const LIFECYCLE_LABEL: Record<SendLifecycle, string> = {\r\n'
    '  IDLE: "",\r\n'
    '  THINKING: "Thinking",\r\n'
    '  STREAMING: "Streaming",\r\n'
    '  COMPLETED: "Completed",\r\n'
    '  PROVIDER_UNAVAILABLE: "Provider unavailable",\r\n'
    '  OFFLINE: "Offline",\r\n'
    '  RATE_LIMITED: "Rate limited",\r\n'
    '  FAILED: "Failed",\r\n'
    '  STREAM_INTERRUPTED: "Interrupted",\r\n'
    '};'
)

new_label = (
    'const LIFECYCLE_LABEL: Record<SendLifecycle, string> = {\r\n'
    '  IDLE: "",\r\n'
    '  CONNECTING: "Connecting",\r\n'
    '  THINKING: "Thinking",\r\n'
    '  STREAMING: "Streaming",\r\n'
    '  TOOL_EXECUTION: "Using tool",\r\n'
    '  COMPLETED: "Completed",\r\n'
    '  PROVIDER_UNAVAILABLE: "Provider unavailable",\r\n'
    '  OFFLINE: "Offline",\r\n'
    '  RATE_LIMITED: "Rate limited",\r\n'
    '  NETWORK_ERROR: "Network error",\r\n'
    '  AUTH_REQUIRED: "Authentication required",\r\n'
    '  FAILED: "Failed",\r\n'
    '  STREAM_INTERRUPTED: "Interrupted",\r\n'
    '};'
)

if old_label not in content:
    old_label_lf = old_label.replace('\r\n', '\n')
    new_label_lf = new_label.replace('\r\n', '\n')
    if old_label_lf in content:
        content = content.replace(old_label_lf, new_label_lf)
        print("FIX 2 applied (LF): LIFECYCLE_LABEL updated")
    else:
        print("FAIL: LIFECYCLE_LABEL not found")
        idx = content.find('const LIFECYCLE_LABEL')
        if idx >= 0:
            print(repr(content[idx:idx+500]))
        sys.exit(1)
else:
    content = content.replace(old_label, new_label)
    print("FIX 2 applied (CRLF): LIFECYCLE_LABEL updated")

# FIX 3: Update LIFECYCLE_CLASS to include new states
old_class = (
    'const LIFECYCLE_CLASS: Record<SendLifecycle, string> = {\r\n'
    '  IDLE: "",\r\n'
    '  THINKING: "border-cyan-500/40 text-cyan-300",\r\n'
    '  STREAMING: "border-cyan-500/40 text-cyan-300",\r\n'
    '  COMPLETED: "border-green-500/40 text-green-400",\r\n'
    '  PROVIDER_UNAVAILABLE: "border-amber-500/40 text-amber-400",\r\n'
    '  OFFLINE: "border-red-500/40 text-red-400",\r\n'
    '  RATE_LIMITED: "border-amber-500/40 text-amber-400",\r\n'
    '  FAILED: "border-red-500/40 text-red-400",\r\n'
    '  STREAM_INTERRUPTED: "border-yellow-500/40 text-yellow-400",\r\n'
    '};'
)

new_class = (
    'const LIFECYCLE_CLASS: Record<SendLifecycle, string> = {\r\n'
    '  IDLE: "",\r\n'
    '  CONNECTING: "border-blue-500/40 text-blue-300 animate-pulse",\r\n'
    '  THINKING: "border-cyan-500/40 text-cyan-300",\r\n'
    '  STREAMING: "border-cyan-500/40 text-cyan-300",\r\n'
    '  TOOL_EXECUTION: "border-purple-500/40 text-purple-300",\r\n'
    '  COMPLETED: "border-green-500/40 text-green-400",\r\n'
    '  PROVIDER_UNAVAILABLE: "border-amber-500/40 text-amber-400",\r\n'
    '  OFFLINE: "border-red-500/40 text-red-400",\r\n'
    '  RATE_LIMITED: "border-amber-500/40 text-amber-400",\r\n'
    '  NETWORK_ERROR: "border-red-500/40 text-red-400",\r\n'
    '  AUTH_REQUIRED: "border-yellow-500/40 text-yellow-400",\r\n'
    '  FAILED: "border-red-500/40 text-red-400",\r\n'
    '  STREAM_INTERRUPTED: "border-yellow-500/40 text-yellow-400",\r\n'
    '};'
)

if old_class not in content:
    old_class_lf = old_class.replace('\r\n', '\n')
    new_class_lf = new_class.replace('\r\n', '\n')
    if old_class_lf in content:
        content = content.replace(old_class_lf, new_class_lf)
        print("FIX 3 applied (LF): LIFECYCLE_CLASS updated")
    else:
        print("FAIL: LIFECYCLE_CLASS not found")
        idx = content.find('const LIFECYCLE_CLASS')
        if idx >= 0:
            print(repr(content[idx:idx+500]))
        sys.exit(1)
else:
    content = content.replace(old_class, new_class)
    print("FIX 3 applied (CRLF): LIFECYCLE_CLASS updated")

# FIX 4: Update CATEGORY_TO_LIFECYCLE to include AUTHENTICATION_ERROR -> AUTH_REQUIRED
# and INTERNAL_ERROR -> FAILED, and NETWORK_ERROR stays as OFFLINE but we want
# NETWORK_ERROR -> NETWORK_ERROR
old_cat = (
    'const CATEGORY_TO_LIFECYCLE: Record<string, SendLifecycle> = {\r\n'
    '  RATE_LIMITED: "RATE_LIMITED",\r\n'
    '  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",\r\n'
    '  STREAM_INTERRUPTED: "STREAM_INTERRUPTED",\r\n'
    '  NETWORK_ERROR: "OFFLINE",\r\n'
    '  TIMEOUT: "OFFLINE",\r\n'
    '  INTERNAL_ERROR: "FAILED",\r\n'
    '  UNKNOWN_ERROR: "FAILED",\r\n'
    '  AUTHENTICATION_ERROR: "FAILED",\r\n'
    '  AUTHORIZATION_ERROR: "FAILED",\r\n'
    '  VALIDATION_ERROR: "FAILED",\r\n'
    '  POLICY_ERROR: "FAILED",\r\n'
    '  RESOURCE_EXHAUSTED: "RATE_LIMITED",\r\n'
    '};'
)

new_cat = (
    'const CATEGORY_TO_LIFECYCLE: Record<string, SendLifecycle> = {\r\n'
    '  RATE_LIMITED: "RATE_LIMITED",\r\n'
    '  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",\r\n'
    '  STREAM_INTERRUPTED: "STREAM_INTERRUPTED",\r\n'
    '  NETWORK_ERROR: "NETWORK_ERROR",\r\n'
    '  TIMEOUT: "OFFLINE",\r\n'
    '  INTERNAL_ERROR: "FAILED",\r\n'
    '  UNKNOWN_ERROR: "FAILED",\r\n'
    '  AUTHENTICATION_ERROR: "AUTH_REQUIRED",\r\n'
    '  AUTHORIZATION_ERROR: "AUTH_REQUIRED",\r\n'
    '  VALIDATION_ERROR: "FAILED",\r\n'
    '  POLICY_ERROR: "FAILED",\r\n'
    '  RESOURCE_EXHAUSTED: "RATE_LIMITED",\r\n'
    '};'
)

if old_cat not in content:
    old_cat_lf = old_cat.replace('\r\n', '\n')
    new_cat_lf = new_cat.replace('\r\n', '\n')
    if old_cat_lf in content:
        content = content.replace(old_cat_lf, new_cat_lf)
        print("FIX 4 applied (LF): CATEGORY_TO_LIFECYCLE updated")
    else:
        print("FAIL: CATEGORY_TO_LIFECYCLE not found")
        idx = content.find('const CATEGORY_TO_LIFECYCLE')
        if idx >= 0:
            print(repr(content[idx:idx+600]))
        sys.exit(1)
else:
    content = content.replace(old_cat, new_cat)
    print("FIX 4 applied (CRLF): CATEGORY_TO_LIFECYCLE updated")

# FIX 5: Make the assistant message start in CONNECTING state, not THINKING
# When sendMessage creates an assistant message, it sets status: "THINKING".
# The real flow is: user sends -> frontend connects (CONNECTING) ->
# backend starts thinking (THINKING) -> streaming (STREAMING)
old_assistant_msg = '        status: "THINKING",\r\n'
new_assistant_msg = '        status: "CONNECTING",\r\n'

if old_assistant_msg not in content:
    old_assistant_msg_lf = old_assistant_msg.replace('\r\n', '\n')
    new_assistant_msg_lf = new_assistant_msg.replace('\r\n', '\n')
    if old_assistant_msg_lf in content:
        content = content.replace(old_assistant_msg_lf, new_assistant_msg_lf)
        print("FIX 5 applied (LF): Assistant message starts in CONNECTING state")
    else:
        print("WARN: Could not find 'status: \"THINKING\"' in sendMessage (may have changed)")
else:
    content = content.replace(old_assistant_msg, new_assistant_msg)
    print("FIX 5 applied (CRLF): Assistant message starts in CONNECTING state")

# FIX 6: In runStream, emit CONNECTING when fetch starts, then THINKING on first event
# Currently runStream sets THINKING on 'typing' and 'meta' events. But there's no
# explicit CONNECTING -> THINKING transition. The assistant message already starts
# as CONNECTING (from sendMessage), and the first SSE event (typing/meta) transitions
# to THINKING. This is correct.
# But we need to handle the case where the fetch succeeds (response.ok) and we
# should transition from CONNECTING to THINKING. Currently the first 'typing' event
# handles this. That's fine.

# FIX 7: In runStream error handling, add AUTH_REQUIRED handling
# When the backend returns 401/403, set the state to AUTH_REQUIRED
old_fetch_err = (
    '      if (!response.ok || !response.body) {\r\n'
    '        let category: string | undefined;\r\n'
    '        let detail = `Request failed (HTTP ${response.status})`;'
)

new_fetch_err = (
    '      if (!response.ok || !response.body) {\r\n'
    '        // Map HTTP status to a truthful lifecycle state\r\n'
    '        let category: string | undefined;\r\n'
    '        let detail = `Request failed (HTTP ${response.status})`;'
)

# Check if this already has the comment
if old_fetch_err not in content:
    # Maybe it already has the comment, try without
    old_fetch_err2 = '      if (!response.ok || !response.body) {\r\n        let category: string | undefined;\r\n        let detail = `Request failed (HTTP ${response.status})`;'
    new_fetch_err2 = old_fetch_err
    if old_fetch_err2 in content:
        content = content.replace(old_fetch_err2, new_fetch_err2)
        print("FIX 7 applied: Added AUTH_REQUIRED note in fetch error")
    else:
        print("WARN: Could not find fetch error block (may already be modified)")
else:
    content = content.replace(old_fetch_err, new_fetch_err)
    print("FIX 7 applied: Added AUTH_REQUIRED note in fetch error")

# FIX 8: Emit a CONNECTING event when the SSE connection is established
# After the response.ok check passes, before processing stream, emit CONNECTING
# to show the user that the connection to the provider is being established.
old_stream_start = (
    '      setBackendConnected(true);\r\n'
    '      setUsingLocalFallback(false);\r\n'
    '\r\n'
    '      const reader = response.body.getReader();'
)

new_stream_start = (
    '      setBackendConnected(true);\r\n'
    '      setUsingLocalFallback(false);\r\n'
    '      // Signal that the SSE stream connection is established;\r\n'
    '      // the first backend event (typing/meta) will transition to THINKING.\r\n'
    '      patch({ status: "CONNECTING" });\r\n'
    '\r\n'
    '      const reader = response.body.getReader();'
)

if old_stream_start not in content:
    old_stream_start_lf = old_stream_start.replace('\r\n', '\n')
    new_stream_start_lf = new_stream_start.replace('\r\n', '\n')
    if old_stream_start_lf in content:
        content = content.replace(old_stream_start_lf, new_stream_start_lf)
        print("FIX 8 applied (LF): Emit CONNECTING when SSE stream established")
    else:
        print("WARN: Could not find stream start block")
else:
    content = content.replace(old_stream_start, new_stream_start)
    print("FIX 8 applied (CRLF): Emit CONNECTING when SSE stream established")

# FIX 9: Add TOOL_EXECUTION state for activity events
# Currently activity events set status to THINKING. They should show TOOL_EXECUTION.
old_activity = '                patch({ toolCalls: observedToolCalls, status: "THINKING" });'
new_activity = '                patch({ toolCalls: observedToolCalls, status: "TOOL_EXECUTION" });'

if old_activity not in content:
    print("WARN: Could not find activity patch line")
else:
    content = content.replace(old_activity, new_activity)
    print("FIX 9 applied: Activity events now show TOOL_EXECUTION state")

# FIX 10: Add AUTH_REQUIRED handling for 401/403 HTTP responses
# In the fetch error handling, map 401/403 to AUTH_REQUIRED
old_err_category = '        throw Object.assign(new Error(detail), { category });'
new_err_category = '''        // Map auth-related HTTP status to AUTH_REQUIRED lifecycle
        if (response.status === 401 || response.status === 403) {
          category = "AUTHENTICATION_ERROR";
        }
        throw Object.assign(new Error(detail), { category });'''

if old_err_category not in content:
    print("WARN: Could not find error throw line")
else:
    content = content.replace(old_err_category, new_err_category)
    print("FIX 10 applied: 401/403 now maps to AUTHENTICATION_ERROR category")

# FIX 11: In the SystemStatus interface, update brain field to include more detail
old_brain_iface = '  brain?: { configured: boolean; healthy: boolean };'
new_brain_iface = '  brain?: { configured: boolean; healthy: boolean; detail?: string; latency_ms?: number | null };'

if old_brain_iface not in content:
    print("WARN: Could not find brain interface (may already be expanded)")
else:
    content = content.replace(old_brain_iface, new_brain_iface)
    print("FIX 11 applied: SystemStatus brain interface expanded")

# FIX 12: In loadSystemStatus, handle the new status values truthfully
# When status is "degraded", set usingLocalFallback based on enabled
old_fallback = '''      setUsingLocalFallback(!data.enabled);
    } catch (error) {
      console.error("Failed to load system status:", error);
      setBackendConnected(false);
      setUsingLocalFallback(true);
    }'''

new_fallback = '''      setUsingLocalFallback(!data.enabled);
      // When the platform is degraded (no real provider can execute),
      // reflect this in the UI so the user knows replies may not be real.
      if (data.status === "degraded" && !data.enabled) {
        setUsingLocalFallback(true);
      }
    } catch (error) {
      console.error("Failed to load system status:", error);
      setBackendConnected(false);
      setUsingLocalFallback(true);
    }'''

if old_fallback not in content:
    old_fallback_lf = old_fallback.replace('\r\n', '\n')
    new_fallback_lf = new_fallback.replace('\r\n', '\n')
    if old_fallback_lf in content:
        content = content.replace(old_fallback_lf, new_fallback_lf)
        print("FIX 12 applied (LF): loadSystemStatus handles degraded status")
    else:
        print("WARN: Could not find fallback block")
else:
    content = content.replace(old_fallback, new_fallback)
    print("FIX 12 applied (CRLF): loadSystemStatus handles degraded status")

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("\nreal-ai-chat.tsx fixes written successfully")
