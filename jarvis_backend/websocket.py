"""WebSocket and socket.io-chat endpoints for the JARVIS dashboard.

Registers WebSocket routes on the shared FastAPI app, including a unified
/ws/chat handler that supports both the plain-JSON protocol and a minimal
socket.io-over-WebSocket protocol.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .core import ai_service, get_store, now_iso
from .routers.auth import consume_websocket_ticket

router = APIRouter()

_connections: Dict[str, list] = {}


async def _require_websocket_ticket(ws: WebSocket) -> bool:
    ticket = ws.query_params.get("ticket", "")
    if consume_websocket_ticket(ticket, ws.headers.get("origin")):
        return True
    await ws.close(code=4401, reason="authentication required")
    return False


async def _safe_send(ws: WebSocket, data: str) -> None:
    try:
        await ws.send_text(data)
    except Exception:  # noqa: BLE001
        pass


def _sio_frame(payload: str) -> str:
    return f"{len(payload)}:{payload}"


def _looks_like_socketio(msg: str) -> bool:
    return bool(
        msg.startswith("0{") or msg == "40" or msg.startswith("40") or
        msg == "2" or msg.startswith("2:") or msg == "3" or
        msg.startswith("42") or msg[:1].isdigit() and ":" in msg
    )


@router.websocket("/ws/chat")
async def ws_chat_unified(ws: WebSocket):
    """Unified /ws/chat: plain-JSON chat or minimal socket.io protocol."""
    if not await _require_websocket_ticket(ws):
        return
    await ws.accept()
    sid = str(uuid.uuid4())[:20]
    _connections.setdefault("chat", []).append(ws)
    sio_mode = False
    try:
        while True:
            msg = await ws.receive_text()
            if not sio_mode and _looks_like_socketio(msg):
                sio_mode = True
            if sio_mode:
                # engine.io / socket.io framing
                await _handle_sio(ws, msg, sid)
                continue
            # plain JSON chat
            try:
                parsed = json.loads(msg)
            except Exception:  # noqa: BLE001
                parsed = {"type": "message", "content": msg}
            if parsed.get("type") == "message":
                reply = await ai_service.chat(parsed.get("content", ""))
                await _safe_send(ws, json.dumps(
                    {"type": "chat_complete", "content": reply}
                ))
            else:
                await _safe_send(ws, json.dumps(
                    {"type": "ack", "event": parsed.get("type"), "timestamp": now_iso()}
                ))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        if ws in _connections.get("chat", []):
            _connections["chat"].remove(ws)


async def _handle_sio(ws: WebSocket, msg: str, sid: str) -> None:
    payload = msg.split(":", 1)[1] if ":" in msg else msg
    if msg.startswith("0") or payload == "":
        await _safe_send(ws, _sio_frame(
            '0{"sid":"' + sid + '","upgrades":[],"pingInterval":25000,"pingTimeout":20000}'
        ))
        return
    if payload.startswith("40"):
        await _safe_send(ws, _sio_frame("40"))
        return
    if payload.startswith("2"):
        await _safe_send(ws, _sio_frame("3"))
        return
    if payload.startswith("42"):
        try:
            event_data = json.loads(payload[2:])
            event = event_data[0]
            data = event_data[1] if len(event_data) > 1 else {}
            if event in ("message", "chat_message"):
                content = data.get("content", "") if isinstance(data, dict) else str(data)
                reply = await ai_service.chat(content)
                await _safe_send(ws, _sio_frame(
                    '42["complete",{"content":' + json.dumps(reply) + '}]'
                ))
            else:
                await _safe_send(ws, _sio_frame('42["complete",{"content":"ok"}]'))
        except Exception:  # noqa: BLE001
            await _safe_send(ws, _sio_frame('42["complete",{"content":"ok"}]'))


@router.websocket("/ws/{topic}")
async def ws_topic(ws: WebSocket, topic: str):
    if not await _require_websocket_ticket(ws):
        return
    if topic not in ("health", "agents", "monitoring", "dashboard", "components"):
        await ws.close(code=4004, reason="unknown topic")
        return
    await ws.accept()
    _connections.setdefault(topic, []).append(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception:  # noqa: BLE001
                msg = {"type": "ack", "timestamp": now_iso()}
            await _safe_send(ws, json.dumps(
                {"type": "ack", "event": msg.get("type"), "timestamp": now_iso()}
            ))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        if ws in _connections.get(topic, []):
            _connections[topic].remove(ws)


@router.websocket("/api/v1/voice/ws/chat")
async def ws_voice_chat(ws: WebSocket):
    if not await _require_websocket_ticket(ws):
        return
    await ws.accept()
    _connections.setdefault("voice", []).append(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception:  # noqa: BLE001
                msg = {"content": data}
            text = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            await _safe_send(ws, json.dumps({"type": "voice_transcript", "text": text, "final": True}))
            await _safe_send(ws, json.dumps({"type": "voice_command", "command": text, "processed": True}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connections.get("voice", []):
            _connections["voice"].remove(ws)


@router.websocket("/api/v1/stark/ws/chat")
async def ws_stark_chat(ws: WebSocket):
    if not await _require_websocket_ticket(ws):
        return
    await ws.accept()
    _connections.setdefault("stark", []).append(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception:  # noqa: BLE001
                msg = {"message": data}
            text = msg.get("message") or msg.get("content") or str(msg)
            reply = await ai_service.chat(text)
            await _safe_send(ws, json.dumps({"type": "stark_response", "message": reply, "mode": "stark"}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connections.get("stark", []):
            _connections["stark"].remove(ws)
