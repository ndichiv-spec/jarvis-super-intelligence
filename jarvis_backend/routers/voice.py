"""Voice: speak (TTS), listen (ASR), transcribe (upload), profiles, voices."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

_TTS_AVAILABLE = False
try:  # pragma: no cover
    from voice.tts import speak as _tts_speak, init_tts  # type: ignore

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
    return {"status": "COMPLETED", "spoken": True}


@router.post("/listen")
async def listen(body: ListenIn):
    raise HTTPException(
        status_code=503,
        detail={"code": "NOT_CONFIGURED", "message": "No speech-to-text provider is configured."},
    )


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    raise HTTPException(
        status_code=503,
        detail={"code": "NOT_CONFIGURED", "message": "No speech-to-text provider is configured."},
    )


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
async def list_voices():
    voices = ["default", "nova", "alloy", "echo", "fable", "onyx", "shimmer"]
    return {"voices": voices}


@router.get("/status")
async def voice_status():
    status = "PARTIALLY_AVAILABLE" if _TTS_AVAILABLE else "NOT_CONFIGURED"
    return {
        "status": status,
        "tts_available": _TTS_AVAILABLE,
        "asr_available": False,
        "streaming_available": False,
        "tts_status": "AVAILABLE" if _TTS_AVAILABLE else "NOT_CONFIGURED",
        "asr_status": "NOT_CONFIGURED",
    }
