"""Video analysis, frame extraction, video info; image generation."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx as _httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator

from ..core import DATA_DIR, get_current_user, now_iso
from ..persistence import ArtifactRepository

router = APIRouter(prefix="/api/v1", tags=["media"])
_logger = logging.getLogger(__name__)
_IMAGE_LIMIT_WINDOW_S = 60
_IMAGE_LIMIT_PER_USER = 5
_IMAGE_ARTIFACT_MAX_BYTES = 25 * 1024 * 1024
_IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_IMAGE_SIGNATURES = {
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda data: (
        len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ),
}
_image_rate_buckets: dict[str, list[float]] = {}
_image_rate_lock = threading.Lock()


class VideoUrlIn(BaseModel):
    video_url: str


def _video_not_configured() -> None:
    raise HTTPException(
        status_code=501,
        detail="Video decoding and frame analysis are not configured.",
    )


@router.post("/video/analyze")
async def video_analyze(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    _video_not_configured()


@router.post("/video/extract-frames")
async def video_extract_frames(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    _video_not_configured()


@router.post("/video/info")
async def video_info(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    _video_not_configured()


class ImageGenerateIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(None, max_length=255)
    provider: str | None = None
    size: str = Field("1024x1024", max_length=9)
    quality: str = "standard"
    style: str | None = Field(None, max_length=100)
    negative_prompt: str | None = Field(None, max_length=4000)
    num_images: int = Field(1, ge=1, le=4)
    model_name: str | None = None

    @validator("prompt")
    def prompt_must_not_be_blank(cls, value: str) -> str:  # noqa: N805
        if not value.strip():
            raise ValueError("prompt is required")
        return value

    @validator("size")
    def size_must_be_bounded_dimensions(cls, value: str) -> str:  # noqa: N805
        try:
            width, height = (int(part) for part in value.lower().split("x"))
        except (TypeError, ValueError):
            raise ValueError("size must use WIDTHxHEIGHT dimensions")
        if not (256 <= width <= 1792 and 256 <= height <= 1792):
            raise ValueError("image dimensions must be between 256 and 1792 pixels")
        return f"{width}x{height}"

    @validator("quality")
    def quality_must_be_supported(cls, value: str) -> str:  # noqa: N805
        if value not in {"standard", "hd"}:
            raise ValueError("quality must be standard or hd")
        return value

    @validator("style")
    def style_must_be_supported(cls, value: str | None) -> str | None:  # noqa: N805
        if value is not None and value not in {"natural", "vivid"}:
            raise ValueError("style must be natural or vivid")
        return value


@router.get("/image/providers")
async def image_provider_status(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    provider_keys = {
        "openai": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("JARVIS_API_KEY_OPENAI")),
        "stability": bool(os.environ.get("STABILITY_API_KEY")),
        "replicate": bool(os.environ.get("REPLICATE_API_KEY")),
    }
    return {
        "providers": {
            provider: {
                "configured": configured,
                "status": "CONFIGURED" if configured else "NOT_CONFIGURED",
            }
            for provider, configured in provider_keys.items()
        }
    }


def _parse_size(size: str):
    width, height = size.lower().split("x")
    return int(width), int(height)


def _image_rate_allowed(user_id: str) -> bool:
    now = time.monotonic()
    with _image_rate_lock:
        cutoff = now - _IMAGE_LIMIT_WINDOW_S
        bucket = [timestamp for timestamp in _image_rate_buckets.get(user_id, []) if timestamp > cutoff]
        if len(bucket) >= _IMAGE_LIMIT_PER_USER:
            _image_rate_buckets[user_id] = bucket
            return False
        bucket.append(now)
        _image_rate_buckets[user_id] = bucket
        return True


@router.post("/image/generate")
async def image_generate(
    body: ImageGenerateIn,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    prompt = (body.prompt or "").strip()
    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=403, detail="Authenticated user identity is required")
    session_id = body.session_id
    if session_id:
        from ..chat_service import chat_service
        from ..errors import ChatError

        try:
            chat_service.get_session(user_id, session_id)
        except ChatError as exc:
            raise HTTPException(status_code=exc.status_code or 404, detail=exc.safe_message) from exc
    if not _image_rate_allowed(user_id):
        raise HTTPException(status_code=429, detail="Image generation rate limit exceeded")
    provider = (body.provider or "replicate").lower()
    width, height = _parse_size(body.size)
    if provider == "openai":
        if body.size not in {"1024x1024", "1792x1024", "1024x1792"}:
            raise HTTPException(
                status_code=422,
                detail="OpenAI image generation supports 1024x1024, 1792x1024, or 1024x1792.",
            )
        if body.num_images != 1:
            raise HTTPException(status_code=422, detail="OpenAI DALL-E 3 supports one image per request.")
        if body.negative_prompt:
            raise HTTPException(status_code=422, detail="OpenAI image generation does not support negative prompts.")
    elif width > 1536 or height > 1536:
        raise HTTPException(status_code=422, detail="This provider supports dimensions up to 1536 pixels.")
    if provider != "openai" and (body.quality != "standard" or body.style not in (None, "natural")):
        raise HTTPException(
            status_code=422,
            detail="Quality and style controls are only supported by OpenAI image generation.",
        )
    if provider == "stability" and body.negative_prompt:
        raise HTTPException(status_code=422, detail="Stability negative prompts are not supported by this integration.")
    try:
        if provider == "replicate":
            result = await _generate_replicate(prompt, body, width, height)
        elif provider == "stability":
            result = await _generate_stability(prompt, body, width, height)
        elif provider == "openai":
            result = await _generate_openai_image(prompt, body, width, height)
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Image provider '{provider}' is not implemented. "
                       "Supported: replicate, stability, openai.",
            )
    except HTTPException:
        raise
    except _httpx.HTTPStatusError as exc:
        _logger.warning("Image provider returned an HTTP error (%s)", exc.response.status_code)
        raise HTTPException(status_code=502, detail="Image provider request failed")
    except (TimeoutError, _httpx.RequestError, ValueError) as exc:
        _logger.warning("Image provider request could not be completed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Image provider request could not be completed")
    persisted_images = await _persist_image_results(
        result,
        user_id=user_id,
        provider=provider,
        prompt=prompt,
        width=width,
        height=height,
        session_id=session_id,
    )
    if not persisted_images:
        raise HTTPException(status_code=502, detail="Image provider returned no usable image data")
    conversation_messages = None
    if session_id:
        from ..chat_service import chat_service

        conversation_messages = chat_service.record_generated_images(
            user_id,
            session_id,
            prompt,
            persisted_images,
        )
    return {
        **result,
        "images": persisted_images,
        "count": len(persisted_images),
        "conversation_messages": conversation_messages,
    }


def _user_image_directory(user_id: str) -> Path:
    return DATA_DIR / "artifacts" / "images" / hashlib.sha256(
        user_id.encode("utf-8")
    ).hexdigest()


async def _download_provider_image(url: str) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Image provider returned an invalid artifact URL") from exc
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or not (hostname == "replicate.delivery" or hostname.endswith(".replicate.delivery"))
    ):
        raise HTTPException(status_code=502, detail="Image provider returned an untrusted artifact URL")

    async with _httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream("GET", url, headers={"Accept": "image/*"}) as response:
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail="Generated image could not be retrieved from its provider",
                )
            mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if mime_type not in _IMAGE_MIME_EXTENSIONS:
                raise HTTPException(status_code=502, detail="Image provider returned an unsupported image type")
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > _IMAGE_ARTIFACT_MAX_BYTES
                except ValueError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="Image provider returned an invalid image size",
                    ) from exc
                if too_large:
                    raise HTTPException(status_code=502, detail="Image provider returned an invalid image size")
            chunks: list[bytes] = []
            total_size = 0
            async for chunk in response.aiter_bytes():
                total_size += len(chunk)
                if total_size > _IMAGE_ARTIFACT_MAX_BYTES:
                    raise HTTPException(status_code=502, detail="Image provider returned an invalid image size")
                chunks.append(chunk)
    if not total_size:
        raise HTTPException(status_code=502, detail="Image provider returned an invalid image size")
    return b"".join(chunks), mime_type


async def _persist_image_results(
    result: dict[str, Any],
    *,
    user_id: str,
    provider: str,
    prompt: str,
    width: int,
    height: int,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    directory = _user_image_directory(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    persisted: list[dict[str, Any]] = []

    for image in result.get("images", []):
        if not isinstance(image, dict):
            continue
        mime_type = "image/png"
        image_bytes: bytes
        encoded = image.get("base64")
        if isinstance(encoded, str) and encoded:
            if encoded.startswith("data:"):
                header, separator, encoded = encoded.partition(",")
                if not separator or header.split(";", 1)[0][5:].lower() not in _IMAGE_MIME_EXTENSIONS:
                    continue
                mime_type = header.split(";", 1)[0][5:].lower()
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                continue
            if not image_bytes or len(image_bytes) > _IMAGE_ARTIFACT_MAX_BYTES:
                continue
        elif isinstance(image.get("url"), str):
            image_bytes, mime_type = await _download_provider_image(image["url"])
        else:
            continue

        if mime_type not in _IMAGE_SIGNATURES or not _IMAGE_SIGNATURES[mime_type](image_bytes):
            raise HTTPException(
                status_code=502,
                detail="Image provider returned data that is not a valid supported image.",
            )

        file_path = directory / f"{uuid.uuid4().hex}{_IMAGE_MIME_EXTENSIONS[mime_type]}"
        try:
            await asyncio.to_thread(file_path.write_bytes, image_bytes)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Generated image could not be stored") from exc

        stored = False
        try:
            artifact_id = ArtifactRepository.store_artifact(
                capability="image.generate",
                artifact_type="image.generated",
                file_path=str(file_path),
                file_size=len(image_bytes),
                mime_type=mime_type,
                metadata={
                    "owner_id": user_id,
                    "prompt": prompt,
                    "provider": provider,
                    "model": image.get("model") or result.get("model"),
                    "width": width,
                    "height": height,
                },
                session_id=session_id,
                correlation_id=uuid.uuid4().hex,
                provenance=f"image_generation_{provider}",
            )
            if not isinstance(artifact_id, str) or not artifact_id:
                raise RuntimeError("Artifact storage did not return an artifact identifier")
            stored = True
        finally:
            if not stored:
                file_path.unlink(missing_ok=True)

        persisted.append({
            "artifact_id": artifact_id,
            "url": f"/api/v1/image/artifacts/{artifact_id}",
            "prompt": prompt,
            "model": image.get("model") or result.get("model") or provider,
            "width": width,
            "height": height,
            "mime_type": mime_type,
        })
    return persisted


@router.get("/image/artifacts/{artifact_id}")
async def get_image_artifact(
    artifact_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    download: bool = False,
):
    user_id = user.get("id") if user else None
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=403, detail="Authenticated user identity is required")
    artifact = ArtifactRepository.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Image artifact not found")
    if (
        artifact.get("capability") != "image.generate"
        or artifact.get("artifact_type") != "image.generated"
    ):
        raise HTTPException(status_code=404, detail="Image artifact not found")
    try:
        metadata = json.loads(artifact.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Image artifact not found")
    if not isinstance(metadata, dict) or metadata.get("owner_id") != user_id:
        raise HTTPException(status_code=404, detail="Image artifact not found")

    path = Path(str(artifact.get("file_path") or "")).resolve()
    directory = _user_image_directory(user_id).resolve()
    if directory not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Image artifact not found")
    mime_type = artifact.get("mime_type")
    if mime_type not in _IMAGE_MIME_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Image artifact not found")
    return FileResponse(
        path,
        media_type=mime_type,
        filename=path.name if download else None,
        headers={"Cache-Control": "private, no-store"},
    )


async def _generate_replicate(prompt: str, body: ImageGenerateIn, width: int, height: int):
    key = os.environ.get("REPLICATE_API_KEY", "")
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
        if m.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid Replicate API key")
        if m.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Replicate model '{model}' not found")
        mj = m.json()
        if not isinstance(mj, dict):
            raise HTTPException(status_code=502, detail="Replicate returned an invalid model response")
        latest_version = mj.get("latest_version")
        latest_id = latest_version.get("id") if isinstance(latest_version, dict) else None
        versions = mj.get("versions")
        first_version = versions[0] if isinstance(versions, list) and versions else {}
        vid = latest_id or (first_version.get("id") if isinstance(first_version, dict) else None)
        if not isinstance(vid, str) or not vid:
            raise HTTPException(status_code=502, detail=f"Could not resolve version for Replicate model '{model}'")
        # 2) create a prediction
        r = await c.post("https://api.replicate.com/v1/predictions",
                         headers=h, json={"version": vid, "input": inp})
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid Replicate API key")
        if r.status_code == 402:
            raise HTTPException(status_code=402,
                                detail="Replicate account has insufficient credit. Add credit at https://replicate.com/account/billing")
        if r.status_code != 201:
            raise HTTPException(status_code=502, detail=f"Replicate request failed: HTTP {r.status_code}")
        pred = r.json()
    if not isinstance(pred, dict):
        raise HTTPException(status_code=502, detail="Replicate returned an invalid prediction response")
    urls = pred.get("urls")
    poll_url = urls.get("get") if isinstance(urls, dict) else None
    if not poll_url and isinstance(pred.get("id"), str):
        poll_url = f"https://api.replicate.com/v1/predictions/{pred['id']}"
    if not isinstance(poll_url, str):
        raise HTTPException(status_code=502, detail="Replicate returned an invalid prediction URL")
    parsed_poll_url = urlsplit(poll_url)
    try:
        poll_port = parsed_poll_url.port
    except ValueError:
        raise HTTPException(status_code=502, detail="Replicate returned an invalid prediction URL")
    path_parts = parsed_poll_url.path.split("/")
    if (
        parsed_poll_url.scheme != "https"
        or parsed_poll_url.hostname != "api.replicate.com"
        or poll_port not in (None, 443)
        or parsed_poll_url.username is not None
        or parsed_poll_url.password is not None
        or parsed_poll_url.query
        or parsed_poll_url.fragment
        or len(path_parts) != 4
        or path_parts[:3] != ["", "v1", "predictions"]
        or not path_parts[3]
    ):
        raise HTTPException(status_code=502, detail="Replicate returned an invalid prediction URL")
    output = None
    async with _httpx.AsyncClient(timeout=10) as c:
        for _ in range(40):
            pr = await c.get(poll_url, headers=h)
            pj = pr.json()
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
    key = os.environ.get("STABILITY_API_KEY", "")
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
        if r.status_code == 404:
            raise HTTPException(status_code=401,
                                detail="Stability API key not accepted by provider (HTTP 404) -- verify key/scope and model slug")
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Stability request failed: HTTP {r.status_code}")
        ct = r.headers.get("content-type", "")
        data = r.content
    images = []
    content_type = ct.split(";", 1)[0].strip().lower()
    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            j = r.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Stability returned an invalid image response.",
            ) from exc
        if not isinstance(j, dict):
            raise HTTPException(status_code=502, detail="Stability returned an invalid image response.")
        encoded_images = []
        if isinstance(j.get("image"), str):
            encoded_images.append(j["image"])
        elif isinstance(j.get("images"), list):
            for item in j["images"]:
                if isinstance(item, dict):
                    encoded = item.get("base64") or item.get("b64") or item.get("image")
                    if isinstance(encoded, str):
                        encoded_images.append(encoded)
        images = [
            {"base64": encoded, "prompt": prompt, "model": model}
            for encoded in encoded_images
        ]
    else:
        if content_type not in _IMAGE_MIME_EXTENSIONS:
            raise HTTPException(
                status_code=502,
                detail="Stability returned an unsupported image content type.",
            )
        images.append({
            "base64": f"data:{content_type};base64,{base64.b64encode(data).decode()}",
            "prompt": prompt,
            "model": model,
        })
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "stability", "model": model, "timestamp": now_iso()}


async def _generate_openai_image(prompt: str, body: ImageGenerateIn, width: int, height: int):
    key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("JARVIS_API_KEY_OPENAI", "")
    if not key:
        raise HTTPException(status_code=401,
                            detail="OpenAI API key not configured. Set OPENAI_API_KEY.")
    size = f"{width}x{height}"
    async with _httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.openai.com/v1/images/generations",
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                         json={"prompt": prompt, "n": max(1, min(4, body.num_images)),
                               "size": size, "quality": body.quality,
                               "style": body.style or "natural",
                               "response_format": "b64_json"})
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid OpenAI API key")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenAI image request failed: HTTP {r.status_code}")
        d = r.json()
    images = [{"base64": im.get("b64_json"), "prompt": prompt, "model": "dall-e-3"}
              for im in (d.get("data") or []) if im.get("b64_json")]
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "openai", "model": "dall-e-3", "timestamp": now_iso()}
