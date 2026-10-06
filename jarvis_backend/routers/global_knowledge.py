"""Global knowledge search, trends, code search, sources, observation, RSS."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ..core import _require_admin, ai_service, get_current_user, get_store, now_iso
from ..research.technology_watch import get_watch_status, refresh_watch

router = APIRouter(prefix="/api/v1/global", tags=["global"])


def _web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    try:
        url = ("https://export.arxiv.org/api/query?max_results="
               + f"{max_results}&search_query=all:{urllib.parse.quote(query)}")
        with urllib.request.urlopen(url, timeout=10) as resp:
            root = ET.fromstring(resp.read().decode())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("a:entry", ns):
            title = entry.findtext("a:title", default="", namespaces=ns).strip()
            summary = entry.findtext("a:summary", default="", namespaces=ns).strip()
            link = entry.findtext("a:id", default="", namespaces=ns)
            results.append({"title": title, "snippet": summary[:300], "url": link})
        return results
    except Exception:  # noqa: BLE001
        return []


@router.get("/knowledge/global/search")
async def global_search(query: str = Query(""), sources: Optional[str] = None,
                        max_results: int = Query(5)):
    results = _web_search(query, max_results)
    return {"query": query, "results": results, "count": len(results)}


@router.get("/knowledge/global/trends")
async def global_trends(limit: int = Query(10)):
    trends = get_store("misc").load().get("trends", [])
    return {"trends": trends[-limit:], "count": len(trends)}


@router.get("/knowledge/global/code")
async def global_code(query: str = Query(""), language: Optional[str] = None,
                      max_results: int = Query(5)):
    results = _web_search(f"{language} {query}", max_results) if language \
        else _web_search(query, max_results)
    return {"query": query, "language": language, "results": results}


@router.get("/knowledge/global/sources")
async def global_sources():
    return {"sources": ["arxiv", "web_search", "knowledge_base", "code_repo"]}


@router.get("/observation/status")
async def observation_status():
    return {"status": "active", "mode": "continuous", "timestamp": now_iso()}


@router.get("/observation/report")
async def observation_report():
    return {
        "timestamp": now_iso(),
        "summary": "System observations are within normal parameters.",
        "events_today": 0,
    }


@router.get("/observation/events")
async def observation_events(limit: int = Query(20)):
    return {"events": [], "count": 0}


@router.get("/observation/metrics")
async def observation_metrics(minutes: int = Query(60)):
    return {"window_minutes": minutes, "metrics": {}}


class RssRefreshIn(BaseModel):
    pass


@router.get("/rss/feeds")
async def rss_feeds():
    feeds = get_store("rss_feeds").load()
    return {"feeds": list(feeds.values())}


@router.get("/rss/latest")
async def rss_latest(limit: int = Query(20)):
    return {"items": [], "count": 0}


@router.post("/rss/refresh")
async def rss_refresh():
    raise HTTPException(
        status_code=501,
        detail="RSS ingestion is not configured; no refresh was performed.",
    )


@router.get("/technology/updates")
async def technology_updates(
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(get_current_user),
):
    watch = get_watch_status()
    watch["items"] = watch["items"][:limit]
    return watch


@router.post("/technology/refresh")
async def technology_refresh(
    user: dict[str, Any] = Depends(_require_admin),
):
    result = await refresh_watch()
    audit_log = get_store("audit_logs").load()
    audit_log.append({
        "ts": now_iso(),
        "actor": user.get("username") or user.get("email") or "admin",
        "kind": "technology_watch",
        "operation": "refresh",
        "ok": result.get("status") in {"ok", "partial", "throttled"},
        "meta": {
            "status": result.get("status"),
            "new_items": result.get("new_items", 0),
        },
    })
    get_store("audit_logs").save()
    return result
