import sys

path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/gateway.py'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# FIX 1: Add `messages` parameter to stream_chat
old_sig = 'async def stream_chat(\r\n        self,\r\n        prompt: str,\r\n        *,\r\n        model: str | None = None,\r\n        user_id: str | None = None,\r\n        session_id: str | None = None,\r\n        system: str | None = None,\r\n        timeout: float | None = None,\r\n    ) -> AsyncIterator[dict[str, Any]]:\r\n        """Stream a reply, preferring genuine provider streaming.\r\n\r\n        Yields ``reasoning`` / ``delta`` events as they arrive and exactly one\r\n        terminal ``done`` event. If the fabric cannot stream (no streaming-capable\r\n        provider, or only the non-streaming Brain/Silverwing paths are viable),\r\n        the buffered result is delivered as a single ``done`` event with\r\n        ``streamed: False`` - the reply is never sliced into fake deltas.\r\n        """\r\n        deadline = float(timeout if timeout is not None else self.timeout)\r\n        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]'

new_sig = 'async def stream_chat(\r\n        self,\r\n        prompt: str | None = None,\r\n        *,\r\n        model: str | None = None,\r\n        user_id: str | None = None,\r\n        session_id: str | None = None,\r\n        system: str | None = None,\r\n        timeout: float | None = None,\r\n        messages: list[dict[str, Any]] | None = None,\r\n    ) -> AsyncIterator[dict[str, Any]]:\r\n        """Stream a reply, preferring genuine provider streaming.\r\n\r\n        Yields ``reasoning`` / ``delta`` events as they arrive and exactly one\r\n        terminal ``done`` event. If the fabric cannot stream (no streaming-capable\r\n        provider, or only the non-streaming Brain/Silverwing paths are viable),\r\n        the buffered result is delivered as a single ``done`` event with\r\n        ``streamed: False`` - the reply is never sliced into fake deltas.\r\n\r\n        ``messages`` carries the full conversation history (so the provider can\r\n        maintain continuity across turns). When omitted, only ``prompt`` is sent\r\n        as a single user message (backward compatibility).\r\n        """\r\n        deadline = float(timeout if timeout is not None else self.timeout)\r\n        # Use the full conversation history when provided so the provider can\r\n        # maintain conversation continuity; otherwise fall back to the single\r\n        # prompt (preserving backward compatibility for callers that only pass\r\n        # a prompt string).\r\n        messages: list[dict[str, Any]] = list(messages) if messages else [\r\n            {"role": "user", "content": prompt or ""}\r\n        ]'

if old_sig not in content:
    print("FAIL: old_sig not found")
    sys.exit(1)
content = content.replace(old_sig, new_sig)
print("FIX 1 applied: stream_chat now accepts messages parameter")

# FIX 2: Add connect timeout to httpx.AsyncClient in _chat_via_model_gateway
old_httpx = '        try:\r\n            async with httpx.AsyncClient(\r\n                timeout=timeout_seconds\r\n            ) as client:\r\n                response = await client.post(\r\n                    post_url,\r\n                    json=payload,\r\n                    headers=headers,\r\n                )'

new_httpx = '        # Use a separate connect timeout so a Silverwing runtime that accepts\r\n        # TCP connections but never responds (e.g. a hung inference worker) fails\r\n        # fast instead of blocking for the full 300s deadline. The total timeout\r\n        # still honours the configured deadline for genuine inference latency.\r\n        connect_timeout = min(float(deadline), 10.0)\r\n        try:\r\n            async with httpx.AsyncClient(\r\n                timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout)\r\n            ) as client:\r\n                response = await client.post(\r\n                    post_url,\r\n                    json=payload,\r\n                    headers=headers,\r\n                )'

if old_httpx not in content:
    print("FAIL: old_httpx not found")
    sys.exit(1)
content = content.replace(old_httpx, new_httpx)
print("FIX 2 applied: _chat_via_model_gateway now has connect timeout")

# FIX 3: Add connect timeout to brain path
old_brain_call = '        start = time.perf_counter()\r\n        try:\r\n            data = await asyncio.to_thread(\r\n                _ext._openai_compatible_post, post_url, payload, key,\r\n                provider=provider, timeout=float(deadline),\r\n            )\r\n        except HTTPException as e:'

new_brain_call = '        start = time.perf_counter()\r\n        # Use a shorter connect timeout so a stale Brain endpoint that accepts\r\n        # TCP connections but never responds fails fast instead of blocking for\r\n        # the full 300s inference deadline.\r\n        brain_connect_timeout = min(float(deadline), 10.0)\r\n        try:\r\n            data = await asyncio.wait_for(\r\n                asyncio.to_thread(\r\n                    _ext._openai_compatible_post, post_url, payload, key,\r\n                    provider=provider, timeout=float(deadline),\r\n                ),\r\n                timeout=brain_connect_timeout,\r\n            )\r\n        except asyncio.TimeoutError:\r\n            raise ChatError(\r\n                ErrorCategory.TIMEOUT,\r\n                "The JARVIS Brain endpoint did not respond within the time limit.",\r\n                detail=f"provider={provider} connect_timeout={brain_connect_timeout}s",\r\n                retryable=True,\r\n            )\r\n        except HTTPException as e:'

if old_brain_call not in content:
    print("FAIL: old_brain_call not found")
    sys.exit(1)
content = content.replace(old_brain_call, new_brain_call)
print("FIX 3 applied: _chat_via_remote_brain now has connect timeout")

# FIX 4: Fix `raise from_provider_exception(exc)` missing 'from exc'
old_raise = '        except Exception as exc:  # noqa: BLE001 -- network / transport\r\n            raise from_provider_exception(exc)'
new_raise = '        except Exception as exc:  # noqa: BLE001 -- network / transport\r\n            raise from_provider_exception(exc) from exc'

if old_raise not in content:
    print("FAIL: old_raise not found")
    sys.exit(1)
content = content.replace(old_raise, new_raise)
print("FIX 4 applied: _chat_via_remote_brain now chains exception with 'from exc'")

# Write with CRLF preserved
with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("\nAll gateway.py fixes written successfully")
