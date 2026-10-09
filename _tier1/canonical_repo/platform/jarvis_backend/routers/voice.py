"""Voice: speak (TTS), listen (ASR), transcribe (upload), profiles, voices."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.responses import Response

from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

_TTS_AVAILABLE = False
try:  # pragma: no cover
    from voice.tts import speak, init_tts  # type: ignore

    _TTS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _TTS_AVAILABLE = False


class SpeakIn(BaseModel):
    text: str
    profile_name: Optional[str] = None
    voice: str = "alloy"
    model: str = "gpt-4o-mini-tts"
    session_id: Optional[str] = None


MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
OPENAI_AUDIO_URL = "https://api.openai.com/v1/audio"


def _openai_audio_key() -> str | None:
    from ..core import _read_secret_setting

    return _read_secret_setting("OPENAI_API_KEY") or _read_secret_setting(
        "JARVIS_API_KEY_OPENAI"
    )


class ListenIn(BaseModel):
    timeout: int = 5
    phrase_time_limit: int = 10


class ProfileIn(BaseModel):
    name: str
    rate: int = 150
    volume: float = 1.0


@router.post("/speak")
async def speak(body: SpeakIn, user: Dict[str, Any] = Depends(get_current_user)):
    text = body.text.strip()
    if not text or len(text) > 4000:
        raise HTTPException(status_code=400, detail="text must contain 1-4000 characters")
    api_key = _openai_audio_key()
    if not api_key:
        if not _TTS_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="TTS unavailable: configure OPENAI_API_KEY or install the local voice.tts engine.",
            )
        raise HTTPException(status_code=501, detail="The configured local TTS adapter is not available.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            result = await client.post(
                f"{OPENAI_AUDIO_URL}/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": body.model,
                    "voice": body.voice,
                    "input": text,
                    "response_format": "mp3",
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="TTS provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="TTS provider is unavailable.") from exc
    if result.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="TTS provider rejected its configured credential.")
    if result.status_code == 429:
        raise HTTPException(status_code=503, detail="TTS provider rate limit reached.")
    if result.status_code != 200 or not result.content:
        raise HTTPException(
            status_code=502,
            detail=f"TTS provider failed (HTTP {result.status_code}).",
        )
    return Response(
        content=result.content,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Jarvis-Voice-Status": "completed",
        },
    )


@router.post("/listen")
async def listen(body: ListenIn, user: Dict[str, Any] = Depends(get_current_user)):
    del body, user
    raise HTTPException(
        status_code=501,
        detail="Microphone capture is an endpoint permission; upload an audio recording to /transcribe.",
    )


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    filename = file.filename or "audio"
    audio = await file.read(MAX_AUDIO_UPLOAD_BYTES + 1)
    await file.close()
    if len(audio) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="audio upload exceeds 25 MiB.")
    if not audio:
        raise HTTPException(status_code=400, detail="audio upload is empty.")
    api_key = _openai_audio_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ASR unavailable: configure OPENAI_API_KEY for the speech transcription provider.",
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
            result = await client.post(
                f"{OPENAI_AUDIO_URL}/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": "gpt-4o-mini-transcribe"},
                files={
                    "file": (
                        os.path.basename(filename)[:128],
                        audio,
                        file.content_type or "application/octet-stream",
                    )
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="ASR provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="ASR provider is unavailable.") from exc
    if result.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="ASR provider rejected its configured credential.")
    if result.status_code == 429:
        raise HTTPException(status_code=503, detail="ASR provider rate limit reached.")
    if result.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"ASR provider failed (HTTP {result.status_code}).",
        )
    transcript = result.json().get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise HTTPException(status_code=502, detail="ASR provider returned no transcript.")

    conversation_id = session_id
    chat_result = None
    from ..errors import ChatError

    if session_id:
        from ..chat_service import chat_service

        try:
            chat_service.get_session(user["id"], session_id)
        except ChatError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.safe_message,
            ) from exc
    else:
        from ..chat_service import chat_service

        conversation_id = chat_service.create_session(user["id"])["id"]
    from ..chat_service import chat_service

    stable_message_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"jarvis-voice:{user['id']}:{conversation_id}:{hashlib.sha256(audio).hexdigest()}",
    )
    chat_result = await chat_service.send_message(
        user["id"], conversation_id, transcript.strip(),
        client_message_id=f"voice-{stable_message_id}",
    )
    return {
        "success": True,
        "status": "COMPLETED",
        "transcript": transcript.strip(),
        "session_id": conversation_id,
        "chat": chat_result,
    }


@router.post("/profile/create")
async def create_profile(body: ProfileIn):
    misc = get_store("misc").load()
    profiles = misc.setdefault("voice_profiles", {})
    profiles[body.name] = {
        "name": body.name,
        "rate": body.rate,
        "volume": body.volume,
        "created_at": now_iso(),
    }
    get_store("misc").save()
    return profiles[body.name]


@router.get("/profile/list")
async def list_profiles():
    misc = get_store("misc").load()
    return {"profiles": list(misc.get("voice_profiles", {}).values())}


@router.post("/profile")
async def save_profile(body: ProfileIn):
    misc = get_store("misc").load()
    profiles = misc.setdefault("voice_profiles", {})
    profiles[body.name] = {
        "name": body.name, "rate": body.rate, "volume": body.volume,
        "created_at": now_iso(),
    }
    get_store("misc").save()
    return profiles[body.name]


@router.get("/profile")
async def get_profiles():
    misc = get_store("misc").load()
    return {"profiles": list(misc.get("voice_profiles", {}).values())}


@router.get("/voices")
async def list_voices():
    voices = ["default", "nova", "alloy", "echo", "fable", "onyx", "shimmer"]
    return {"voices": voices}


@router.get("/status")
async def voice_status():
    configured = bool(_openai_audio_key())
    asr_available = configured
    tts_available = configured
    return {
        "status": "CONFIGURED_UNVERIFIED" if configured else "DEGRADED",
        "tts_available": tts_available,
        "asr_available": asr_available,
        "asr_status": "configured_unverified" if configured else "NOT_CONFIGURED",
        "tts_availability_reason": (
            None if tts_available
            else "Configure OPENAI_API_KEY for the speech synthesis provider."
        ),
        "asr_availability_reason": (
            None if asr_available
            else "Configure OPENAI_API_KEY for the speech transcription provider."
        ),
        "provider": "openai" if configured else None,
        "audio_streaming_available": False,
        "command_websocket_available": True,
    }
