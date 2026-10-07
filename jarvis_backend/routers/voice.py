"""Voice: speak (TTS), listen (ASR), transcribe (upload), profiles, voices."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..capability import ExecutionContext
from ..capabilities.voice import VoiceCapability
from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

_TTS_AVAILABLE = False
_TTS_VERIFIED = False
try:  # pragma: no cover
    from voice.tts import speak as _tts_speak, init_tts  # type: ignore

    _TTS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _TTS_AVAILABLE = False


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    profile_name: Optional[str] = Field(default=None, max_length=100)


class ListenIn(BaseModel):
    timeout: int = Field(default=5, ge=1, le=30)
    phrase_time_limit: int = Field(default=10, ge=1, le=60)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rate: int = Field(default=150, ge=80, le=300)
    volume: float = Field(default=1.0, ge=0, le=1)


@router.post("/speak")
async def speak(body: SpeakIn, _user: dict = Depends(get_current_user)):
    global _TTS_VERIFIED
    if not _TTS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={"code": "NOT_CONFIGURED", "message": "No text-to-speech provider is configured."},
        )
    try:
        _tts_speak(body.text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "FAILED", "message": f"Text-to-speech failed: {type(exc).__name__}"},
        ) from exc
    _TTS_VERIFIED = True
    return {"status": "COMPLETED", "spoken": True}


@router.post("/listen")
async def listen(body: ListenIn, _user: dict = Depends(get_current_user)):
    raise HTTPException(
        status_code=503,
        detail={"code": "NOT_CONFIGURED", "message": "No speech-to-text provider is configured."},
    )


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_AUDIO_TYPE", "message": "Unsupported audio file type."},
        )
    try:
        audio = await file.read(25 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if len(audio) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail={"code": "AUDIO_TOO_LARGE", "message": "Audio file exceeds the 25 MiB limit."},
        )
    if not audio:
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_AUDIO", "message": "Audio file is empty."},
        )

    result = await VoiceCapability().execute(
        {"action": "transcribe", "audio_data": {"data": audio, "filename": filename}},
        ExecutionContext(user_id=str(user["id"]), session_id=f"transcription-{uuid.uuid4().hex}"),
    )
    if not result.success:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "VOICE_PROVIDER_UNAVAILABLE",
                "message": "Speech transcription is unavailable or failed. Check the configured voice provider.",
            },
        )
    return result.data


@router.post("/profile/create")
async def create_profile(
    body: ProfileIn,
    user: dict = Depends(get_current_user),
):
    misc = get_store("misc").load()
    profiles = misc.setdefault("voice_profiles", {})
    profile_key = f"{user['id']}:{body.name}"
    profiles[profile_key] = {
        "name": body.name,
        "user_id": user["id"],
        "rate": body.rate,
        "volume": body.volume,
        "created_at": now_iso(),
    }
    get_store("misc").save()
    return {key: value for key, value in profiles[profile_key].items() if key != "user_id"}


@router.get("/profile/list")
async def list_profiles(user: dict = Depends(get_current_user)):
    misc = get_store("misc").load()
    profiles = [
        {key: value for key, value in profile.items() if key != "user_id"}
        for profile in misc.get("voice_profiles", {}).values()
        if profile.get("user_id") == user["id"]
    ]
    return {"profiles": profiles}


@router.post("/profile")
async def save_profile(
    body: ProfileIn,
    user: dict = Depends(get_current_user),
):
    misc = get_store("misc").load()
    profiles = misc.setdefault("voice_profiles", {})
    profile_key = f"{user['id']}:{body.name}"
    profiles[profile_key] = {
        "name": body.name, "user_id": user["id"], "rate": body.rate, "volume": body.volume,
        "created_at": now_iso(),
    }
    get_store("misc").save()
    return {key: value for key, value in profiles[profile_key].items() if key != "user_id"}


@router.get("/profile")
async def get_profiles(user: dict = Depends(get_current_user)):
    return await list_profiles(user)


@router.get("/voices")
async def list_voices(user: dict = Depends(get_current_user)):
    voices = ["default", "nova", "alloy", "echo", "fable", "onyx", "shimmer"]
    return {"voices": voices}


@router.get("/status")
async def voice_status():
    status = (
        "PARTIALLY_AVAILABLE" if _TTS_VERIFIED
        else "CONFIGURED" if _TTS_AVAILABLE
        else "NOT_CONFIGURED"
    )
    return {
        "status": status,
        "tts_available": _TTS_VERIFIED,
        "tts_configured": _TTS_AVAILABLE,
        "asr_available": False,
        "streaming_available": False,
        "tts_status": "AVAILABLE" if _TTS_VERIFIED else (
            "CONFIGURED" if _TTS_AVAILABLE else "NOT_CONFIGURED"
        ),
        "asr_status": "NOT_CONFIGURED",
    }
