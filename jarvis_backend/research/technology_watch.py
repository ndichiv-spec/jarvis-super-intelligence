"""Curated, provenance-preserving watch of upstream AI/backend releases."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..core import get_store

REFRESH_INTERVAL = timedelta(hours=6)
MAX_ITEMS_PER_SOURCE = 5
MAX_STORED_ITEMS = 200

SOURCES: tuple[dict[str, str], ...] = (
    {
        "id": "fastapi",
        "name": "FastAPI",
        "repository": "fastapi/fastapi",
        "url": "https://github.com/fastapi/fastapi",
        "focus": "Python API framework",
    },
    {
        "id": "mcp-python-sdk",
        "name": "MCP Python SDK",
        "repository": "modelcontextprotocol/python-sdk",
        "url": "https://github.com/modelcontextprotocol/python-sdk",
        "focus": "Model Context Protocol",
    },
    {
        "id": "huggingface-hub",
        "name": "Hugging Face Hub",
        "repository": "huggingface/huggingface_hub",
        "url": "https://github.com/huggingface/huggingface_hub",
        "focus": "Hub APIs and hosted Jobs",
    },
    {
        "id": "kaggle-cli",
        "name": "Kaggle CLI",
        "repository": "Kaggle/kaggle-cli",
        "url": "https://github.com/Kaggle/kaggle-cli",
        "focus": "Kaggle API and notebooks",
    },
    {
        "id": "nvidia-nemo",
        "name": "NVIDIA NeMo",
        "repository": "NVIDIA/NeMo",
        "url": "https://github.com/NVIDIA/NeMo",
        "focus": "Model training and customization",
    },
    {
        "id": "vllm",
        "name": "vLLM",
        "repository": "vllm-project/vllm",
        "url": "https://github.com/vllm-project/vllm",
        "focus": "High-throughput model serving",
    },
)

_refresh_lock = asyncio.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _normalize_release(source: dict[str, str], release: Any) -> dict[str, str] | None:
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return None

    tag = release.get("tag_name")
    url = release.get("html_url")
    if not isinstance(tag, str) or not tag.strip():
        return None
    if not isinstance(url, str) or not url.startswith(
        f"https://github.com/{source['repository']}/releases/tag/"
    ):
        return None

    published = release.get("published_at")
    body = release.get("body")
    return {
        "id": f"{source['id']}:{tag[:120]}",
        "source_id": source["id"],
        "source_name": source["name"],
        "repository": source["repository"],
        "title": str(release.get("name") or tag)[:300],
        "tag": tag[:120],
        "url": url[:1000],
        "published_at": published[:40] if isinstance(published, str) else "",
        "summary": body[:5000] if isinstance(body, str) else "",
        "retrieved_at": _utc_now().isoformat(),
        "content_trust": "external_release_notes_untrusted",
    }


async def _fetch_source(
    client: httpx.AsyncClient, source: dict[str, str]
) -> list[dict[str, str]]:
    response = await client.get(
        f"https://api.github.com/repos/{source['repository']}/releases",
        params={"per_page": MAX_ITEMS_PER_SOURCE},
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "JARVIS-Technology-Watch",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("GitHub release response was not a list")
    return [
        item
        for release in payload[:MAX_ITEMS_PER_SOURCE]
        if (item := _normalize_release(source, release)) is not None
    ]


def _read_state() -> dict[str, Any]:
    state = get_store("technology_watch").load()
    return state if isinstance(state, dict) else {}


def get_watch_status() -> dict[str, Any]:
    state = _read_state()
    updates = state.get("items", [])
    if not isinstance(updates, list):
        updates = []
    from ..bio_growth_worker import get_bio_growth_worker

    return {
        "sources": [dict(source) for source in SOURCES],
        "items": updates[:MAX_STORED_ITEMS],
        "last_attempt_at": state.get("last_attempt_at"),
        "last_success_at": state.get("last_success_at"),
        "last_errors": state.get("last_errors", []),
        "refresh_interval_seconds": int(REFRESH_INTERVAL.total_seconds()),
        "automatic_refresh": get_bio_growth_worker().running,
        "content_notice": (
            "Release notes are external, untrusted input. They are evidence only; "
            "JARVIS does not execute instructions from them or change code."
        ),
    }


async def refresh_watch(
    *,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch releases from the fixed source list, preserving provenance."""
    async with _refresh_lock:
        state = _read_state()
        last_attempt = _parse_timestamp(state.get("last_attempt_at"))
        now = _utc_now()
        if (
            not force
            and last_attempt is not None
            and now - last_attempt < REFRESH_INTERVAL
        ):
            return {
                **get_watch_status(),
                "status": "throttled",
                "new_items": 0,
            }

        state["last_attempt_at"] = now.isoformat()
        store = get_store("technology_watch")
        store.save()

        existing = state.get("items", [])
        if not isinstance(existing, list):
            existing = []
        by_id = {
            item["id"]: item
            for item in existing
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        errors: list[dict[str, str]] = []
        factory = client_factory or httpx.AsyncClient

        async with factory(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            for source in SOURCES:
                try:
                    releases = await _fetch_source(client, source)
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({
                        "source_id": source["id"],
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    })
                    continue
                for release in releases:
                    by_id[release["id"]] = release

        items = sorted(
            by_id.values(),
            key=lambda item: (item.get("published_at", ""), item.get("id", "")),
            reverse=True,
        )[:MAX_STORED_ITEMS]
        state["items"] = items
        state["last_errors"] = errors
        if len(errors) < len(SOURCES):
            state["last_success_at"] = now.isoformat()
        store.save()

        previous_ids = {
            row["id"]
            for row in existing
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        status = "ok"
        if errors:
            status = "partial" if len(errors) < len(SOURCES) else "unavailable"
        return {
            **get_watch_status(),
            "status": status,
            "new_items": sum(1 for item_id in by_id if item_id not in previous_ids),
        }
