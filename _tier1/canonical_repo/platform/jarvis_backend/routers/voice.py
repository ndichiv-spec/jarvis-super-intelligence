"""Voice: speak (TTS), listen (ASR), transcribe (upload), profiles, voices."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..core import UPLOADS_DIR, get_store, now_iso

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


class ListenIn(BaseModel):
    timeout: int = 5
    phrase_time_limit: int = 10


class ProfileIn(BaseModel):
    name: str
    rate: int = 150
    volume: float = 1.0


@router.post("/speak")
async def speak(body: SpeakIn):
    if not _TTS_AVAILABLE:
        return {
            "success": False,
            "status": "NOT_IMPLEMENTED",
            "spoken": False,
            "text": body.text[:200],
        }
    try:
        speak(body.text)
    except Exception as exc:
        return {
            "success": False,
            "status": "FAILED",
            "spoken": False,
            "error": type(exc).__name__,
            "text": body.text[:200],
        }
    return {
        "success": True,
        "status": "COMPLETED",
        "spoken": True,
        "text": body.text[:200],
    }


@router.post("/listen")
async def listen(body: ListenIn):
    return {
        "success": False,
        "status": "NOT_IMPLEMENTED",
        "transcript": "",
        "recognized": False,
        "note": "ASR requires a microphone service; configure one to enable listening.",
    }


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    filename = file.filename or "audio"
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    name = f"{uuid.uuid4()}.{ext}"
    path = UPLOADS_DIR / name
    with path.open("wb") as fh:
        fh.write(await file.read())
    return {
        "success": False,
        "status": "NOT_IMPLEMENTED",
        "transcript": "",
        "filename": name,
        "note": "Speech-to-text engine not configured.",
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
    asr_available = False
    tts_available = _TTS_AVAILABLE
    return {
        "status": "READY" if tts_available and asr_available else "DEGRADED",
        "tts_available": tts_available,
        "asr_available": asr_available,
        "asr_status": "NOT_IMPLEMENTED",
        "audio_streaming_available": False,
        "command_websocket_available": True,
    }
