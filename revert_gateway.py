import sys

path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/gateway.py'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# REVERT: Remove the asyncio.wait_for wrapping around the brain call
# The brain endpoint fails fast (connection refused) without it.
# The asyncio.wait_for + asyncio.to_thread combo can cause thread pool exhaustion
# on Windows, leading to event loop starvation.

old_brain = (
    '        start = time.perf_counter()\r\n'
    '        # Use a shorter connect timeout so a stale Brain endpoint that accepts\r\n'
    '        # TCP connections but never responds fails fast instead of blocking for\r\n'
    '        # the full 300s inference deadline.\r\n'
    '        brain_connect_timeout = min(float(deadline), 10.0)\r\n'
    '        try:\r\n'
    '            data = await asyncio.wait_for(\r\n'
    '                asyncio.to_thread(\r\n'
    '                    _ext._openai_compatible_post, post_url, payload, key,\r\n'
    '                    provider=provider, timeout=float(deadline),\r\n'
    '                ),\r\n'
    '                timeout=brain_connect_timeout,\r\n'
    '            )\r\n'
    '        except asyncio.TimeoutError:\r\n'
    '            raise ChatError(\r\n'
    '                ErrorCategory.TIMEOUT,\r\n'
    '                "The JARVIS Brain endpoint did not respond within the time limit.",\r\n'
    '                detail=f"provider={provider} connect_timeout={brain_connect_timeout}s",\r\n'
    '                retryable=True,\r\n'
    '            )\r\n'
    '        except HTTPException as e:'
)

new_brain = (
    '        start = time.perf_counter()\r\n'
    '        try:\r\n'
    '            data = await asyncio.to_thread(\r\n'
    '                _ext._openai_compatible_post, post_url, payload, key,\r\n'
    '                provider=provider, timeout=float(deadline),\r\n'
    '            )\r\n'
    '        except HTTPException as e:'
)

if old_brain in content:
    content = content.replace(old_brain, new_brain)
    print("REVERTED: Removed asyncio.wait_for wrapping around brain call")
else:
    # Try LF
    old_brain_lf = old_brain.replace('\r\n', '\n')
    new_brain_lf = new_brain.replace('\r\n', '\n')
    if old_brain_lf in content:
        content = content.replace(old_brain_lf, new_brain_lf)
        print("REVERTED (LF): Removed asyncio.wait_for wrapping around brain call")
    else:
        print("WARN: brain timeout pattern not found (already reverted?)")

# Also revert the Silverwing httpx connect timeout change — the Silverwing runtime
# path is only reached when brain AND fabric both fail. In normal operation
# (brain unreachable + Google works), the Silverwing path is never tried.
# The connect timeout change is fine to keep, but let's simplify it to avoid
# any issues. Actually, keep it — it's a real improvement.

# Keep: FIX 4 (from exc)
old_raise = '        except Exception as exc:  # noqa: BLE001 -- network / transport\r\n            raise from_provider_exception(exc)'
new_raise = '        except Exception as exc:  # noqa: BLE001 -- network / transport\r\n            raise from_provider_exception(exc) from exc'

if old_raise in content:
    content = content.replace(old_raise, new_raise)
    print("FIX 4 still applied: 'from exc' chaining")
elif new_raise in content:
    print("FIX 4 already applied: 'from exc' chaining")
else:
    # Check LF
    old_raise_lf = old_raise.replace('\r\n', '\n')
    new_raise_lf = new_raise.replace('\r\n', '\n')
    if old_raise_lf in content:
        content = content.replace(old_raise_lf, new_raise_lf)
        print("FIX 4 still applied (LF): 'from exc' chaining")
    elif new_raise_lf in content:
        print("FIX 4 already applied (LF): 'from exc' chaining")
    else:
        print("WARN: from_exc pattern not found")

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("gateway.py reverted brain timeout fix, kept from exc fix")
