"""Video analysis, frame extraction, video info; image generation."""

from __future__ import annotations

import os
import uuid
import asyncio
import base64
import httpx as _httpx
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, Response

from ..core import (
    UPLOADS_DIR,
    _read_secret_setting,
    ai_service,
    get_current_user,
    now_iso,
)
from ..connectors.crypto import ConnectorCryptoError
from ..media_storage import (
    MAX_MEDIA_BYTES,
    MediaReferenceError,
    decrypt_source_url,
    is_allowed_provider_url,
    load_authorized_media,
    media_path,
    register_generated_image,
    revoke_media,
)

router = APIRouter(prefix="/api/v1", tags=["media"])


class VideoUrlIn(BaseModel):
    video_url: str


async def _save_from_upload(file: UploadFile) -> str:
    name = f"{uuid.uuid4()}-{os.path.basename(file.filename or 'video')}"
    path = UPLOADS_DIR / name
    with path.open("wb") as fh:
        fh.write(await file.read())
    return str(path)


@router.post("/video/analyze")
async def video_analyze(file: Optional[UploadFile] = File(None),
                        video_url: Optional[str] = Form(None)):
    if file is not None:
        path = await _save_from_upload(file)
        name = file.filename or ""
    elif video_url:
        path = video_url
        name = video_url
    else:
        raise HTTPException(status_code=400, detail="Provide a file or video_url")
    return {
        "analysis": await ai_service.chat(f"Analyze video: {name}"),
        "file": name,
        "path": path,
        "duration_seconds": None,
        "frames": 0,
        "objects_detected": [],
    }


@router.post("/video/extract-frames")
async def video_extract_frames(file: UploadFile = File(...),
                               num_frames: int = Form(10)):
    path = await _save_from_upload(file)
    return {
        "success": True,
        "file": file.filename,
        "frames_extracted": 0,
        "frames_dir": None,
        "requested": num_frames,
    }


@router.post("/video/info")
async def video_info(file: UploadFile = File(...)):
    path = await _save_from_upload(file)
    return {
        "success": True,
        "filename": file.filename,
        "path": path,
        "size": os.path.getsize(path),
        "codec": None,
        "duration": None,
        "resolution": None,
        "fps": None,
    }


class ImageGenerateIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    provider: Optional[str] = None
    size: str = Field(default="1024x1024", max_length=16)
    quality: str = "standard"
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    num_images: int = Field(default=1, ge=1, le=4)
    model_name: Optional[str] = None


def _image_provider_key(provider: str, settings: tuple[str, ...]) -> str | None:
    for setting in settings:
        key = _read_secret_setting(setting)
        if key:
            return key
    if os.environ.get("JARVIS_IMAGE_PROVIDER", "").strip().lower() == provider:
        return _read_secret_setting("JARVIS_IMAGE_PROVIDER_API_KEY")
    return None


def _parse_size(size: str):
    parts = size.lower().split("x")
    if len(parts) != 2 or any(not part.isdecimal() for part in parts):
        raise HTTPException(status_code=400, detail="size must be WIDTHxHEIGHT")
    width, height = (int(part) for part in parts)
    supported = {(1024, 1024), (1024, 1792), (1792, 1024)}
    if (width, height) not in supported:
        raise HTTPException(
            status_code=400,
            detail="size must be 1024x1024, 1024x1792, or 1792x1024",
        )
    return width, height


def _configured_image_provider() -> str:
    providers = (
        ("openai", ("OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI")),
        ("replicate", ("REPLICATE_API_KEY",)),
        ("stability", ("STABILITY_API_KEY",)),
    )
    preferred = os.environ.get("JARVIS_IMAGE_PROVIDER", "").strip().lower()
    if preferred:
        matching = next(
            ((name, settings) for name, settings in providers if name == preferred),
            None,
        )
        if matching is None:
            raise HTTPException(
                status_code=503,
                detail="JARVIS_IMAGE_PROVIDER must be openai, replicate, or stability.",
            )
        provider, settings = matching
        if not _image_provider_key(provider, settings):
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Image generation is configured for {provider}, but its "
                    f"credential is missing. Set {settings[0]} on the server."
                ),
            )
        return provider
    for provider, settings in providers:
        if _image_provider_key(provider, settings):
            return provider
    raise HTTPException(
        status_code=503,
        detail=(
            "Image generation is not configured. Set OPENAI_API_KEY, "
            "REPLICATE_API_KEY, or STABILITY_API_KEY on the server."
        ),
    )


def _image_provider_readiness() -> dict[str, dict[str, Any]]:
    """Expose provider configuration without treating credentials as health."""
    providers = {
        "openai": {
            "label": "OpenAI DALL-E 3",
            "configured": bool(
                _image_provider_key(
                    "openai", ("OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI"),
                )
            ),
            "credential": "OPENAI_API_KEY",
        },
        "stability": {
            "label": "Stable Diffusion",
            "configured": bool(_image_provider_key(
                "stability", ("STABILITY_API_KEY",),
            )),
            "credential": "STABILITY_API_KEY",
        },
        "replicate": {
            "label": "Replicate",
            "configured": bool(_image_provider_key(
                "replicate", ("REPLICATE_API_KEY",),
            )),
            "credential": "REPLICATE_API_KEY",
        },
    }
    preferred = os.environ.get("JARVIS_IMAGE_PROVIDER", "").strip().lower()
    if preferred:
        selected_provider = (
            preferred
            if preferred in providers and providers[preferred]["configured"]
            else None
        )
    else:
        selected_provider = next(
            (
                provider for provider in ("openai", "replicate", "stability")
                if providers[provider]["configured"]
            ),
            None,
        )
    for provider, status in providers.items():
        status["availability"] = (
            "configured_unverified" if status["configured"] else "not_configured"
        )
        status["availability_reason"] = (
            None if status["configured"]
            else f"Configure {status['credential']} on the server."
        )
        status["summary"] = (
            "Credential configured; provider health has not been verified."
            if status["configured"] else status["availability_reason"]
        )
        status["features"] = ["text_to_image"]
        status["selected"] = provider == selected_provider
        status.pop("credential")
    return providers


async def generate_image_for_owner(
    *,
    owner_id: str,
    prompt: str,
    provider: str | None = None,
    size: str = "1024x1024",
    num_images: int = 1,
) -> dict[str, Any]:
    """Run one configured provider and persist its verified output for its owner."""
    prompt = prompt.strip()
    if not owner_id:
        raise HTTPException(status_code=401, detail="authenticated owner is required")
    if not prompt or len(prompt) > 4000:
        raise HTTPException(status_code=400, detail="prompt must contain 1-4000 characters")
    if type(num_images) is not int or not 1 <= num_images <= 4:
        raise HTTPException(status_code=400, detail="num_images must be between 1 and 4")
    width, height = _parse_size(size)
    selected_provider = (provider or _configured_image_provider()).lower()
    if selected_provider not in {"openai", "replicate", "stability"}:
        raise HTTPException(
            status_code=501,
            detail=f"Image provider '{selected_provider}' is not implemented.",
        )
    if selected_provider == "openai" and num_images != 1:
        raise HTTPException(
            status_code=400,
            detail="OpenAI image generation currently supports one image per request.",
        )

    body = ImageGenerateIn(
        prompt=prompt,
        provider=selected_provider,
        size=size,
        num_images=num_images,
    )
    try:
        if selected_provider == "replicate":
            result = await _generate_replicate(prompt, body, width, height)
        elif selected_provider == "stability":
            result = await _generate_stability(prompt, body, width, height)
        else:
            result = await _generate_openai_image(prompt, body, width, height)
    except HTTPException:
        raise
    except _httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Image provider timed out.") from exc
    except _httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Image provider is unavailable.") from exc

    raw_images = result.get("images")
    if not isinstance(raw_images, list):
        raise HTTPException(
            status_code=502,
            detail="Image provider returned an invalid result.",
        )
    images = []
    for image in raw_images[:num_images]:
        if not isinstance(image, dict):
            continue
        images.append(register_generated_image(
            owner_id=owner_id,
            image=image,
            provider=selected_provider,
            model=str(image.get("model") or result.get("model") or selected_provider),
            prompt=prompt,
            width=width,
            height=height,
        ))
    if not images:
        raise HTTPException(
            status_code=502,
            detail="Image provider completed without a storable image output.",
        )
    result.update(
        images=images,
        count=len(images),
        media_refs=[image["media_ref"] for image in images],
        provider=selected_provider,
    )
    return result


@router.post("/image/generate")
async def image_generate(
    body: ImageGenerateIn,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        result = await generate_image_for_owner(
            owner_id=str(user["id"]),
            prompt=body.prompt,
            provider=body.provider,
            size=body.size,
            num_images=body.num_images,
        )
    except HTTPException:
        raise
    except (MediaReferenceError, ConnectorCryptoError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


@router.get("/image/providers")
async def image_provider_status(
    _user: dict[str, Any] = Depends(get_current_user),
):
    providers = _image_provider_readiness()
    preferred = os.environ.get("JARVIS_IMAGE_PROVIDER", "").strip().lower()
    selected_provider = next(
        (name for name, status in providers.items() if status["selected"]),
        None,
    )
    return {
        "providers": providers,
        "selected_provider": selected_provider,
        "selection_mode": "explicit" if preferred else "automatic",
    }


@router.get("/media/{asset_id}")
async def get_generated_media(
    asset_id: str,
    expires: int,
    signature: str,
):
    record = load_authorized_media(
        asset_id=asset_id,
        expires=expires,
        signature=signature,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Media reference is invalid or expired.")
    path = media_path(record)
    if path is not None:
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Media output is unavailable.")
        return FileResponse(
            path,
            media_type=str(record.get("content_type") or "image/png"),
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    try:
        source_url = decrypt_source_url(record)
    except ConnectorCryptoError as exc:
        raise HTTPException(status_code=503, detail="Stored media cannot be decrypted.") from exc
    except MediaReferenceError as exc:
        raise HTTPException(status_code=502, detail="Stored media source is invalid.") from exc
    if not source_url or not is_allowed_provider_url(source_url):
        raise HTTPException(status_code=404, detail="Media output is unavailable.")
    try:
        async with _httpx.AsyncClient(
            timeout=_httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False,
        ) as client:
            upstream = await client.get(source_url)
    except _httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Media provider timed out.") from exc
    except _httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Media provider is unavailable.") from exc
    content_type = upstream.headers.get("content-type", "").split(";", 1)[0].lower()
    content = upstream.content
    if (
        upstream.status_code != 200
        or not content_type.startswith("image/")
        or len(content) > MAX_MEDIA_BYTES
    ):
        raise HTTPException(status_code=502, detail="Media provider returned invalid image data.")
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/media/{asset_id}")
async def revoke_generated_media(
    asset_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    if not revoke_media(asset_id=asset_id, owner_id=str(user["id"])):
        raise HTTPException(status_code=404, detail="Media output not found.")
    return {"success": True, "revoked": True}


async def _generate_replicate(prompt: str, body: ImageGenerateIn, width: int, height: int):
    key = _image_provider_key("replicate", ("REPLICATE_API_KEY",)) or ""
    if not key:
        raise HTTPException(status_code=401,
                            detail="Replicate API key not configured. Set REPLICATE_API_KEY.")
    model = body.model_name or "stability-ai/sdxl"
    owner, _, name = model.partition("/")
    if not name:
        owner, name = "stability-ai", "sdxl"
    h = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
    inp = {"prompt": prompt, "width": width, "height": height,
           "num_outputs": max(1, min(4, body.num_images)),
           "guidance_scale": 7.5, "num_inference_steps": 30}
    if body.negative_prompt:
        inp["negative_prompt"] = body.negative_prompt
    async with _httpx.AsyncClient(timeout=30) as c:
        # 1) resolve the model's latest version (model-specific POST .../predictions
        #    404s on Replicate's REST; the version+general endpoint is correct).
        m = await c.get(f"https://api.replicate.com/v1/models/{owner}/{name}", headers=h)
        if m.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid Replicate API key")
        if m.status_code == 429:
            raise HTTPException(status_code=503, detail="Replicate rate limit reached.")
        if m.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Replicate model '{model}' not found")
        try:
            mj = m.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="Replicate returned invalid model metadata.",
            ) from exc
        if not isinstance(mj, dict):
            raise HTTPException(
                status_code=502,
                detail="Replicate returned invalid model metadata.",
            )
        vid = (mj.get("latest_version") or {}).get("id") or (mj.get("versions") or [{}])[0].get("id")
        if not vid:
            raise HTTPException(status_code=502, detail=f"Could not resolve version for Replicate model '{model}'")
        # 2) create a prediction
        r = await c.post("https://api.replicate.com/v1/predictions",
                         headers=h, json={"version": vid, "input": inp})
        if r.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid Replicate API key")
        if r.status_code == 429:
            raise HTTPException(status_code=503, detail="Replicate rate limit reached.")
        if r.status_code == 402:
            raise HTTPException(status_code=402,
                                detail="Replicate account has insufficient credit. Add credit at https://replicate.com/account/billing")
        if r.status_code != 201:
            raise HTTPException(status_code=502, detail=f"Replicate request failed: HTTP {r.status_code}")
        try:
            pred = r.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="Replicate returned invalid prediction data.",
            ) from exc
        if not isinstance(pred, dict):
            raise HTTPException(
                status_code=502,
                detail="Replicate returned invalid prediction data.",
            )
    poll_url = (pred.get("urls") or {}).get("get") or f"https://api.replicate.com/v1/predictions/{pred.get('id')}"
    output = None
    async with _httpx.AsyncClient(timeout=10) as c:
        for _ in range(40):
            pr = await c.get(poll_url, headers=h)
            if pr.status_code == 429:
                raise HTTPException(status_code=503, detail="Replicate rate limit reached.")
            if pr.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Replicate prediction status failed: HTTP {pr.status_code}",
                )
            try:
                pj = pr.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Replicate returned invalid prediction status.",
                ) from exc
            if not isinstance(pj, dict):
                raise HTTPException(
                    status_code=502,
                    detail="Replicate returned invalid prediction status.",
                )
            if pj.get("status") == "succeeded" and pj.get("output"):
                output = pj.get("output")
                break
            if pj.get("status") in ("failed", "canceled", "error"):
                raise HTTPException(status_code=502,
                                  detail=f"Replicate prediction {pj.get('status')}")
            await asyncio.sleep(1.0)
    images = []
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str):
                images.append({"url": item, "prompt": prompt, "model": model})
            elif isinstance(item, dict):
                images.append({"url": item.get("url"), "base64": item.get("base64"),
                               "prompt": prompt, "model": model})
    elif isinstance(output, str):
        images.append({"url": output, "prompt": prompt, "model": model})
    elif isinstance(output, dict):
        images.append({"url": output.get("url"), "base64": output.get("base64"),
                       "prompt": prompt, "model": model})
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "replicate", "model": model, "timestamp": now_iso()}


async def _generate_stability(prompt: str, body: ImageGenerateIn, width: int, height: int):
    key = _image_provider_key("stability", ("STABILITY_API_KEY",)) or ""
    if not key:
        raise HTTPException(status_code=401,
                            detail="Stability API key not configured. Set STABILITY_API_KEY.")
    model = body.model_name or "sdxl-1024-positivity"
    url = f"https://api.stability.ai/v2beta/stable-image/generation/{model}/image"
    async with _httpx.AsyncClient(timeout=40) as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {key}"},
                         files={"prompt": (None, prompt)},
                         data={"width": str(min(max(width, 256), 1536)),
                               "height": str(min(max(height, 256), 1536)),
                               "num_images": str(max(1, min(4, body.num_images)) or 1)})
        if r.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid Stability API key")
        if r.status_code == 429:
            raise HTTPException(status_code=503, detail="Stability rate limit reached.")
        if r.status_code == 404:
            raise HTTPException(status_code=401,
                                detail="Stability API key not accepted by provider (HTTP 404) -- verify key/scope and model slug")
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Stability request failed: HTTP {r.status_code}")
        ct = r.headers.get("content-type", "")
        data = r.content
    images = []
    if "json" in ct:
        try:
            j = r.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="Stability provider returned invalid JSON image data.",
            ) from exc
        if isinstance(j, dict) and isinstance(j.get("image"), str):
            images.append({
                "base64": j["image"], "prompt": prompt, "model": model,
            })
        elif isinstance(j, dict) and isinstance(j.get("images"), list):
            for image in j["images"]:
                if isinstance(image, dict):
                    encoded = (
                        image.get("base64") or image.get("b64") or image.get("image")
                    )
                    if isinstance(encoded, str):
                        images.append({
                            "base64": encoded, "prompt": prompt, "model": model,
                        })
        if not images:
            raise HTTPException(
                status_code=502,
                detail="Stability provider returned no supported image data.",
            )
    else:
        images.append({"base64": base64.b64encode(data).decode(), "prompt": prompt, "model": model})
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "stability", "model": model, "timestamp": now_iso()}


async def _generate_openai_image(prompt: str, body: ImageGenerateIn, width: int, height: int):
    key = _image_provider_key(
        "openai", ("OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI"),
    ) or ""
    if not key:
        raise HTTPException(status_code=401,
                            detail="OpenAI API key not configured. Set OPENAI_API_KEY.")
    size = f"{width}x{height}"
    async with _httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.openai.com/v1/images/generations",
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                         json={"prompt": prompt, "n": max(1, min(4, body.num_images)),
                               "size": size, "response_format": "b64_json"})
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid OpenAI API key")
        if r.status_code == 429:
            raise HTTPException(status_code=503, detail="OpenAI image rate limit reached.")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenAI image request failed: HTTP {r.status_code}")
        try:
            d = r.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="OpenAI returned invalid image data.",
            ) from exc
    if not isinstance(d, dict) or not isinstance(d.get("data"), list):
        raise HTTPException(
            status_code=502,
            detail="OpenAI returned invalid image data.",
        )
    images = [
        {"base64": im["b64_json"], "prompt": prompt, "model": "dall-e-3"}
        for im in d["data"]
        if isinstance(im, dict) and isinstance(im.get("b64_json"), str)
    ]
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "openai", "model": "dall-e-3", "timestamp": now_iso()}
