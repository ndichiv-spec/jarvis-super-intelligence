import sys

path = r'F:\AI\Jarvis-super-intelligence-\jarvis_backend/routers/ai.py'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# Detect line endings
CRLF = '\r\n' if '\r\n' in content else '\n'
print(f"File uses {'CRLF' if CRLF == '\r\\n' else 'LF'} line endings")

# --- Fix 1: ai_process non-verify path -> use chat_service.send_message ---
old_call = (
    '    try:' + CRLF +
    '        result = await provider_gateway.chat(' + CRLF +
    '            [{"role": "user", "content": text}], model=model,' + CRLF +
    '            _bypass_gateway=_bypass,' + CRLF +
    '        )' + CRLF +
    '    except ChatError as e:' + CRLF +
    '        raise HTTPException(status_code=502, detail=str(e))' + CRLF +
    '    except Exception as e:  # noqa: BLE001' + CRLF +
    '        raise HTTPException(status_code=502, detail=f"AI backend failure: {e}")' + CRLF +
    '    return {' + CRLF +
    '        "response": result["content"],' + CRLF +
    '        "model": result.get("model"),' + CRLF +
    '        "provider": result.get("provider", "silverwing"),' + CRLF +
    '        "latency_ms": result.get("latency_ms"),' + CRLF +
    '        "tokens_used": (result.get("usage") or {}).get("total_tokens"),' + CRLF +
    '        "session_id": body.session_id,' + CRLF +
    '    }'
)

new_call = (
    '    # Route through ChatService so the session is created/managed, the message' + CRLF +
    '    # is persisted, and the full conversation history is passed to the provider' + CRLF +
    '    # (maintaining continuity across turns). Previously this called' + CRLF +
    '    # provider_gateway.chat with only the current message, so the model never' + CRLF +
    '    # saw prior turns in the session.' + CRLF +
    '    from ..chat_service import chat_service' + CRLF +
    CRLF +
    '    session_id = body.session_id or str(uuid.uuid4())' + CRLF +
    '    user_id = user["id"]' + CRLF +
    '    chat_service.create_session(user_id, session_id, text)' + CRLF +
    CRLF +
    '    try:' + CRLF +
    '        result = await chat_service.send_message(' + CRLF +
    '            user_id, session_id, text,' + CRLF +
    '            model=model,' + CRLF +
    '            client_message_id=getattr(body, "client_message_id", None),' + CRLF +
    '        )' + CRLF +
    '    except ChatError as e:' + CRLF +
    '        raise HTTPException(status_code=502, detail=str(e))' + CRLF +
    '    except Exception as e:  # noqa: BLE001' + CRLF +
    '        raise HTTPException(status_code=502, detail=f"AI backend failure: {e}")' + CRLF +
    '    return {' + CRLF +
    '        "response": result.get("message"),' + CRLF +
    '        "model": result.get("model"),' + CRLF +
    '        "provider": result.get("provider", "silverwing"),' + CRLF +
    '        "latency_ms": result.get("latency_ms"),' + CRLF +
    '        "tokens_used": (result.get("usage") or {}).get("total_tokens") or 0,' + CRLF +
    '        "session_id": session_id,' + CRLF +
    '        "message_id": result.get("message_id"),' + CRLF +
    '        "status": result.get("status", "COMPLETED"),' + CRLF +
    '    }'
)

if old_call not in content:
    print("FAIL: old_call not found")
    idx = content.find('try:' + CRLF + '        result = await provider_gateway.chat(')
    if idx >= 0:
        print(f"Found at {idx}")
        print(repr(content[idx:idx+600]))
    sys.exit(1)
content = content.replace(old_call, new_call)
print("FIX 1 applied: ai_process routes through chat_service.send_message")

# --- Fix 2: ai_status default status -> "degraded" ---
old_status = '    data = {"status": "ready", **ai_service.settings()}'
new_status = '    data = {"status": "degraded", **ai_service.settings()}'
if old_status not in content:
    print("FAIL: old_status not found")
    sys.exit(1)
content = content.replace(old_status, new_status)
print("FIX 2 applied: ai_status default status is 'degraded'")

# --- Fix 3: Add _probe_silverwing_chat helper before _probe_endpoint ---
old_probe_end = '    except OSError:\r\n        return False\r\n\r\n\r\nasync def _probe_endpoint(endpoint: str) -> bool:\r\n    return await asyncio.to_thread(_endpoint_reachable, endpoint)'

# Check which line ending is used
if old_probe_end in content:
    print("Found _probe_endpoint with CRLF")
    probe_old = old_probe_end
    probe_new = old_probe_end.replace(
        '    return await asyncio.to_thread(_endpoint_reachable, endpoint)',
        '    return await asyncio.to_thread(_endpoint_reachable, endpoint)\r\n\r\n\r\n'
        'async def _probe_silverwing_chat(endpoint: str) -> bool:\r\n'
        '    """Probe whether the Silverwing runtime can actually serve chat completions.\r\n\r\n'
        '    A TCP-open /v1/health returning 200 is NOT proof the runtime can infer.\r\n'
        '    This sends a tiny real inference request with a short timeout and\r\n'
        '    returns True only when the runtime returns a parseable response.\r\n'
        '    """\r\n'
        '    if not endpoint:\r\n'
        '        return False\r\n'
        '    if endpoint.lower().endswith("/v1") or endpoint.lower().endswith("/chat/completions"):\r\n'
        '        post_url = endpoint.rstrip("/") + "/chat/completions"\r\n'
        '    elif endpoint.lower().endswith("/v1/chat/completions"):\r\n'
        '        post_url = endpoint\r\n'
        '    else:\r\n'
        '        post_url = endpoint.rstrip("/") + "/v1/chat/completions"\r\n\r\n'
        '    import httpx\r\n'
        '    try:\r\n'
        '        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:\r\n'
        '            resp = await client.post(post_url, json={\r\n'
        '                "model": "silverwing-120m-base-v1",\r\n'
        '                "messages": [{"role": "user", "content": "ok"}],\r\n'
        '                "max_tokens": 1,\r\n'
        '            }, headers={"Content-Type": "application/json"})\r\n'
        '            if resp.status_code < 500:\r\n'
        '                data = resp.json()\r\n'
        '                choices = data.get("choices") or []\r\n'
        '                if choices and (choices[0].get("message") or {}).get("content"):\r\n'
        '                    return True\r\n'
        '    except Exception:\r\n'
        '        pass\r\n'
        '    return False'
    )
    content = content.replace(probe_old, probe_new)
    print("FIX 3 applied: Added _probe_silverwing_chat helper (CRLF)")
elif 'async def _probe_endpoint(endpoint: str) -> bool:\n    return await asyncio.to_thread(_endpoint_reachable, endpoint)' in content:
    print("Found _probe_endpoint with LF")
    LF = '\n'
    probe_old = '    except OSError:\n        return False\n\n\nasync def _probe_endpoint(endpoint: str) -> bool:\n    return await asyncio.to_thread(_endpoint_reachable, endpoint)'
    probe_new = probe_old.replace(
        '    return await asyncio.to_thread(_endpoint_reachable, endpoint)',
        '    return await asyncio.to_thread(_endpoint_reachable, endpoint)\n\n\n'
        'async def _probe_silverwing_chat(endpoint: str) -> bool:\n'
        '    """Probe whether the Silverwing runtime can actually serve chat completions.\n\n'
        '    A TCP-open /v1/health returning 200 is NOT proof the runtime can infer.\n'
        '    This sends a tiny real inference request with a short timeout and\n'
        '    returns True only when the runtime returns a parseable response.\n'
        '    """\n'
        '    if not endpoint:\n'
        '        return False\n'
        '    if endpoint.lower().endswith("/v1") or endpoint.lower().endswith("/chat/completions"):\n'
        '        post_url = endpoint.rstrip("/") + "/chat/completions"\n'
        '    elif endpoint.lower().endswith("/v1/chat/completions"):\n'
        '        post_url = endpoint\n'
        '    else:\n'
        '        post_url = endpoint.rstrip("/") + "/v1/chat/completions"\n\n'
        '    import httpx\n'
        '    try:\n'
        '        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:\n'
        '            resp = await client.post(post_url, json={\n'
        '                "model": "silverwing-120m-base-v1",\n'
        '                "messages": [{"role": "user", "content": "ok"}],\n'
        '                "max_tokens": 1,\n'
        '            }, headers={"Content-Type": "application/json"})\n'
        '            if resp.status_code < 500:\n'
        '                data = resp.json()\n'
        '                choices = data.get("choices") or []\n'
        '                if choices and (choices[0].get("message") or {}).get("content"):\n'
        '                    return True\n'
        '    except Exception:\n'
        '        pass\n'
        '    return False'
    )
    content = content.replace(probe_old, probe_new)
    print("FIX 3 applied: Added _probe_silverwing_chat helper (LF)")
else:
    print("FAIL: _probe_endpoint pattern not found")
    sys.exit(1)

# --- Fix 4: Silverwing health block + platform_status ---
old_sw_block = (
    '    data["silverwing"] = {' + CRLF +
    '        "configured": bool(sw_endpoint),' + CRLF +
    '        "reachable": sw_up,' + CRLF +
    '        "healthy": sw_up,' + CRLF +
    '        "status": "healthy" if sw_up else "unreachable",' + CRLF +
    '        "last_checked": now_iso() if sw_up else None,' + CRLF +
    '        "errors": None if sw_up else "runtime not reachable" if sw_endpoint else "not configured",' + CRLF +
    '        "model": _os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),' + CRLF +
    '    }' + CRLF +
    '    if sw_up and not data.get("enabled"):' + CRLF +
    '        data["enabled"] = True' + CRLF +
    '        data["provider"] = "silverwing"'
)

new_sw_block = (
    '    # A TCP-reachable runtime is not necessarily able to serve chat: the' + CRLF +
    '    # Silverwing :8010 health endpoint returns 200 while /v1/chat/completions' + CRLF +
    '    # can hang indefinitely. Probe the actual chat endpoint so "healthy"' + CRLF +
    '    # is only reported when a real inference is possible.' + CRLF +
    '    sw_can_chat = await _probe_silverwing_chat(sw_endpoint) if sw_up else False' + CRLF +
    '    data["silverwing"] = {' + CRLF +
    '        "configured": bool(sw_endpoint),' + CRLF +
    '        "reachable": sw_up,' + CRLF +
    '        "healthy": sw_can_chat,' + CRLF +
    '        "status": "healthy" if sw_can_chat else ("reachable" if sw_up else "unreachable"),' + CRLF +
    '        "last_checked": now_iso() if sw_up else None,' + CRLF +
    '        "errors": None if sw_can_chat else ("runtime /v1/chat/completions not responding" if sw_up else ("runtime not reachable" if sw_endpoint else "not configured")),' + CRLF +
    '        "model": _os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),' + CRLF +
    '    }' + CRLF +
    '    if sw_can_chat and not data.get("enabled"):' + CRLF +
    '        data["enabled"] = True' + CRLF +
    '        data["provider"] = "silverwing"'
)

if old_sw_block not in content:
    print("FAIL: old_sw_block not found, trying LF variant")
    old_sw_block_lf = old_sw_block.replace(CRLF, '\n')
    new_sw_block_lf = new_sw_block.replace(CRLF, '\n')
    if old_sw_block_lf in content:
        content = content.replace(old_sw_block_lf, new_sw_block_lf)
        print("FIX 4 applied: Silverwing health probes /v1/chat/completions (LF)")
    else:
        print("FAIL: old_sw_block not found even with LF")
        sys.exit(1)
else:
    content = content.replace(old_sw_block, new_sw_block)
    print("FIX 4 applied: Silverwing health probes /v1/chat/completions (CRLF)")

old_platform = (
    '    # Platform status: ONLINE when at least one provider is available' + CRLF +
    '    data["platform_status"] = "online" if data.get("enabled") else "degraded"' + CRLF +
    '    return data'
)

new_platform = (
    '    # Platform status: ONLINE only when a real provider can execute.' + CRLF +
    '    _real_provider = bool(data.get("enabled")) and (' + CRLF +
    '        sw_can_chat' + CRLF +
    '        or (data.get("brain") and data["brain"].get("healthy"))' + CRLF +
    '    )' + CRLF +
    '    data["platform_status"] = "online" if _real_provider else "degraded"' + CRLF +
    '    if not _real_provider:' + CRLF +
    '        data["status"] = "degraded"' + CRLF +
    '    return data'
)

if old_platform not in content:
    print("FAIL: old_platform not found, trying LF variant")
    old_platform_lf = old_platform.replace(CRLF, '\n')
    new_platform_lf = new_platform.replace(CRLF, '\n')
    if old_platform_lf in content:
        content = content.replace(old_platform_lf, new_platform_lf)
        print("FIX 5 applied: platform_status reflects real provider (LF)")
    else:
        print("FAIL: old_platform not found even with LF")
        sys.exit(1)
else:
    content = content.replace(old_platform, new_platform)
    print("FIX 5 applied: platform_status reflects real provider (CRLF)")

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("\nrouters/ai.py fixes written successfully")
