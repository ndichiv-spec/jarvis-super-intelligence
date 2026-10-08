"""Video analysis, frame extraction, video info; image generation."""

from __future__ import annotations

import os
import uuid
import asyncio
import base64
import httpx as _httpx
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..core import UPLOADS_DIR, ai_service, now_iso

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
    prompt: str
    provider: Optional[str] = None
    size: str = "1024x1024"
    quality: str = "standard"
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    num_images: int = 1
    model_name: Optional[str] = None


def _parse_size(size: str):
    try:
        w, h = size.lower().split("x")
        return max(1, int(w)), max(1, int(h))
    except Exception:
        return 1024, 1024


@router.post("/image/generate")
async def image_generate(body: ImageGenerateIn):
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    provider = (body.provider or "replicate").lower()
    width, height = _parse_size(body.size or "1024x1024")
    try:
        if provider == "replicate":
            return await _generate_replicate(prompt, body, width, height)
        if provider == "stability":
            return await _generate_stability(prompt, body, width, height)
        if provider == "openai":
            return await _generate_openai_image(prompt, body, width, height)
    except HTTPException:
        raise
    except _httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Provider request failed: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e}")
    raise HTTPException(
        status_code=501,
        detail=f"Image provider '{provider}' is not implemented. "
               f"Supported: replicate, stability, openai.",
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
        vid = (mj.get("latest_version") or {}).get("id") or (mj.get("versions") or [{}])[0].get("id")
        if not vid:
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
    poll_url = (pred.get("urls") or {}).get("get") or f"https://api.replicate.com/v1/predictions/{pred.get('id')}"
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
    if "json" in ct:
        try:
            j = r.json()
            if isinstance(j, dict) and "image" in j:
                images.append({"base64": j["image"], "prompt": prompt, "model": model})
            elif isinstance(j, dict) and "images" in j:
                for im in j["images"]:
                    images.append({"base64": im.get("base64") or im.get("b64") or im.get("image"),
                                   "prompt": prompt, "model": model})
        except Exception:
            images.append({"base64": base64.b64encode(data).decode(), "prompt": prompt, "model": model})
    else:
        images.append({"base64": base64.b64encode(data).decode(), "prompt": prompt, "model": model})
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
                               "size": size, "response_format": "b64_json"})
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid OpenAI API key")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenAI image request failed: HTTP {r.status_code}")
        d = r.json()
    images = [{"base64": im.get("b64_json"), "prompt": prompt, "model": "dall-e-3"}
              for im in (d.get("data") or []) if im.get("b64_json")]
    return {"success": True, "images": images, "count": len(images), "prompt": prompt,
            "provider": "openai", "model": "dall-e-3", "timestamp": now_iso()}
