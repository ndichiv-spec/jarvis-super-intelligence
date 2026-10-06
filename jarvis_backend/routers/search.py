"""JARVIS Global Search — Federated Search Architecture (spec §26–31, §63).

Searches across all platform domains without making information disappear
into isolated subsystems.  Returns normalised results with a ``source``
field so the frontend can group by domain.

Searchable domains:
  - knowledge       (key-value knowledge store)
  - memory          (cognitive memory)
  - chat            (chat sessions + history)
  - agents          (agent definitions)
  - tasks           (task definitions)
  - browser         (history, bookmarks, evidence, page states)
  - notes           (user notes)
  - reminders       (user reminders)
  - research        (global knowledge / ArXiv web search)
  - missions        (browser missions, if any)

All text matches implement a simple case-insensitive substring search with
optional field scoping.  No external search engine is required — this uses
only Python stdlib.

Permission-aware: results are filtered so a user only sees items they
have access to (``user_id`` field must match, or the item has no ``user_id``
i.e. it is global/public).
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import json as _json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core import get_current_user, get_store, now_iso
from ..browser_engine import NavigationFailureClass

router = APIRouter(prefix="/api/v1/search", tags=["search"])


# --------------------------------------------------------------------------- #
# Domain enumeration (spec §63)
# --------------------------------------------------------------------------- #

class SearchDomain(str, Enum):
    """Searchable platform domains."""
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    CHAT = "chat"
    AGENTS = "agents"
    TASKS = "tasks"
    BROWSER = "browser"
    NOTES = "notes"
    REMINDERS = "reminders"
    RESEARCH = "research"
    MISSIONS = "missions"
    EVIDENCE = "evidence"
    LEARNING = "learning"   # lessons, datasets, training runs, model revisions (spec §41)
    ALL = "all"


# Domains searched by default when domain == "all"
_DEFAULT_DOMAINS: List[SearchDomain] = [
    SearchDomain.KNOWLEDGE,
    SearchDomain.MEMORY,
    SearchDomain.CHAT,
    SearchDomain.AGENTS,
    SearchDomain.TASKS,
    SearchDomain.BROWSER,
    SearchDomain.NOTES,
    SearchDomain.RESEARCH,
    SearchDomain.EVIDENCE,
    SearchDomain.LEARNING,
]

# Per-domain search weight — higher means ranked higher in results
_DOMAIN_WEIGHTS: Dict[str, float] = {
    "knowledge": 1.0,
    "memory": 1.0,
    "chat": 0.9,
    "agents": 0.8,
    "tasks": 0.8,
    "browser": 1.0,
    "notes": 1.0,
    "reminders": 0.9,
    "research": 0.7,
    "missions": 0.7,
    "evidence": 0.9,
    "learning": 1.1,
}


# --------------------------------------------------------------------------- #
# Search query model
# --------------------------------------------------------------------------- #

class SearchQuery(BaseModel):
    """Federated search request (spec §26, §63)."""
    query: str
    domain: Optional[str] = "all"  # domain name or "all"
    limit: int = Field(default=20, ge=1, le=100)
    # Optional filters
    user_id: Optional[str] = None
    # Whether to include web/arxiv search (slower — may be disabled by caller)
    include_web: bool = True
    # Highlight matching terms in snippets
    highlight: bool = True
    # Include semantic similarity if available (falls back to text match)
    semantic: bool = False


class SearchResult(BaseModel):
    """Normalised search result (spec §27, §30).

    Every result, regardless of its originating domain, is normalised into this
    common contract so the frontend can render a single unified list while still
    distinguishing the source domain.
    """
    id: str
    source: str  # domain e.g. "knowledge", "browser", "research", "learning"
    title: str
    snippet: str = ""
    url: Optional[str] = None
    score: float = 0.0
    relevance: float = 0.0  # 0.0 – 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    permissions: Dict[str, Any] = Field(default_factory=dict)
    # Spec §30 — additional context for cross-system inspection + handoff.
    type: str = ""            # object type e.g. "knowledge", "history", "lesson", "training_run"
    domain: str = ""          # mirrored from source for convenience
    route: str = ""           # frontend route to open this object, e.g. "/knowledge/{id}"
    related_objects: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_score: Optional[float] = None  # contributes to ranking when semantic rerank ran


class SearchResponse(BaseModel):
    """Federated search response (spec §27)."""
    query: str
    total_results: int
    results: List[SearchResult] = Field(default_factory=list)
    domains_searched: List[str] = Field(default_factory=list)
    took_ms: float = 0.0
    highlights: Dict[str, List[str]] = Field(default_factory=dict)  # terms matched per result
    semantic: bool = False          # whether semantic reranking was applied
    semantic_backend: str = ""       # "neural" / "fingerprint" / "" if not used

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# --------------------------------------------------------------------------- #
# Text matching helpers
# --------------------------------------------------------------------------- #

def _normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.lower().strip())


def _extract_searchable_text(item: Dict[str, Any], fields: List[str]) -> str:
    """Extract searchable text from an item using specified fields."""
    parts = []
    for field_name in fields:
        val = item.get(field_name, "")
        if val is None:
            continue
        if isinstance(val, (dict, list)):
            val = _json.dumps(val)
        parts.append(str(val))
    return _normalize_text(" ".join(parts))


def _highlight(text: str, query_terms: List[str], max_snippet: int = 300) -> str:
    """Create a snippet with query terms highlighted (wrapped in ****)."""
    if not text or not query_terms:
        return text[:max_snippet] if text else ""
    # Find the first occurrence of any query term
    best_idx = len(text)
    for term in query_terms:
        idx = text.lower().find(term.lower())
        if idx != -1 and idx < best_idx:
            best_idx = idx
    snippet_start = max(0, best_idx - 50)
    snippet_end = min(len(text), best_idx + max_snippet)
    snippet = text[snippet_start:snippet_end]
    for term in query_terms:
        # Case-insensitive highlight
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        snippet = pattern.sub(lambda m: f"=={m.group()}=={term.lower()}", snippet)
    return snippet


def _compute_relevance(query_terms: List[str], searchable_text: str, field_matches: Dict[str, int]) -> float:
    """Compute a relevance score for a search result.

    Uses a simple BM25-like approach: term frequency in searchable text,
    boosted by matches in important fields (title > content).
    """
    if not searchable_text:
        return 0.0

    tf = 0
    for term in query_terms:
        tf += searchable_text.count(term.lower())

    # Field-weighted relevance
    field_score = 0.0
    for field_name, count in field_matches.items():
        weight = 3.0 if field_name in ("title", "name", "heading", "question", "claim", "url_domain") else 1.0
        field_score += count * weight

    # Normalize by length (simple)
    text_len = len(searchable_text.split())
    if text_len > 0:
        # tf/idf-like normalization
        normalized_tf = tf / text_len
    else:
        normalized_tf = 0.0

    relevance = (normalized_tf + field_score * 0.1) / (len(query_terms) + 1)
    return min(relevance, 1.0)


# --------------------------------------------------------------------------- #
# Cross-system routing + relationship helpers (spec §30, §51-53)
# --------------------------------------------------------------------------- #

def _default_route(source: str, item_id: str) -> str:
    """Frontend route that opens an object from its source domain."""
    routes = {
        "knowledge": f"/knowledge/{item_id}",
        "memory": f"/memory/{item_id}",
        "chat": f"/chat/{item_id}",
        "agents": f"/agents/{item_id}",
        "tasks": f"/tasks/{item_id}",
        "browser": f"/browser/session/{item_id}",
        "evidence": f"/browser/evidence/{item_id}",
        "notes": f"/notes/{item_id}",
        "reminders": f"/reminders/{item_id}",
        "research": f"/research/{item_id}",
        "missions": f"/missions/{item_id}",
        "learning": f"/learning/{item_id}",
    }
    return routes.get(source, f"/{source}/{item_id}")


def _related_objects(source: str, item_id: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build cross-system links for a result (spec §51-53, §30)."""
    related: List[Dict[str, Any]] = []
    # Browser evidence links back to its source URL and page state.
    if source in ("browser", "evidence"):
        url = item.get("url")
        if url:
            related.append({"id": url, "type": "url", "relation": "source_url"})
        sid = item.get("session_id") or item.get("tab_id")
        if sid:
            related.append({"id": sid, "type": "session", "relation": "session"})
    # Knowledge items may carry a source URL and tags.
    if source == "knowledge":
        url = item.get("url")
        if url:
            related.append({"id": url, "type": "url", "relation": "source_url"})
    # Learning items link to their lineage / training run.
    if source == "learning":
        run_id = item.get("task_id") or item.get("training_run_id")
        if run_id:
            related.append({"id": run_id, "type": "training_run", "relation": "training_run"})
        rev = item.get("output_revision") or item.get("model_revision")
        if rev:
            related.append({"id": rev, "type": "model_revision", "relation": "model_revision"})
    return related


def _check_learning_permissions(item: Dict[str, Any], user_id: Optional[str]) -> None:
    """Raise 403 if ``user_id`` may not view a learning artifact (spec §15)."""
    owner = item.get("user_id")
    if owner and owner != "system" and owner != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this object")


# Structured query parsing (spec §40 — field scoping via ``field:value`` syntax).
_STRUCT_FIELD_RE = re.compile(r"^([a-z_]+):(?:[^\s]+)$")


def _parse_structured_query(query: str) -> Tuple[str, Dict[str, str]]:
    """Extract ``field:value`` tokens from a free-text query.

    Recognised modifiers:
      - ``type:<x>``    — restrict by object type (e.g. ``type:lesson``)
      - ``domain:<x>`` — restrict by source domain
      - ``after:<iso>``— lower-bound timestamp

    Returns ``(free_text, modifiers)``.
    """
    modifiers: Dict[str, str] = {}
    tokens = query.split()
    free: List[str] = []
    for tok in tokens:
        m = _STRUCT_FIELD_RE.match(tok)
        if m and m.group(1) in ("type", "domain", "after", "tag"):
            modifiers[m.group(1)] = tok.split(":", 1)[1]
        else:
            free.append(tok)
    return " ".join(free), modifiers


# --------------------------------------------------------------------------- #
# Search history (spec §44)
# --------------------------------------------------------------------------- #

def _record_search_history(user_id: Optional[str], query: str, domains: List[str],
                           result_count: int) -> None:
    """Append a search event to the persisted search_history store."""
    try:
        history_store = get_store("search_history")
        history = history_store.load()
        if not isinstance(history, list):
            history = []
        history.append({
            "user_id": user_id,
            "query": query,
            "domains": domains,
            "result_count": result_count,
            "timestamp": now_iso(),
        })
        # Bound history to last 1000 entries.
        history = history[-1000:]
        history_store.save()
    except Exception:  # noqa: BLE001
        pass


def _filter_by_user(items: List[Dict[str, Any]], user_id: Optional[str]) -> List[Dict[str, Any]]:
    """Filter items visible to the user (permission-aware filtering, spec §15)."""
    if not user_id:
        return items
    result = []
    for item in items:
        item_user = item.get("user_id") if isinstance(item, dict) else None
        if item_user is None or item_user == "system" or item_user == user_id:
            result.append(item)
    return result


def _search_text_in_items(
    items: List[Dict[str, Any]],
    query_terms: List[str],
    search_fields: List[str],
    source: str,
    url_field: Optional[str] = None,
    title_fields: List[str] = None,
    snippet_fields: List[str] = None,
    timestamp_field: str = "created_at",
) -> List[SearchResult]:
    """Generic text search across a list of dict items."""
    results: List[SearchResult] = []
    norm_query = " ".join(query_terms).lower()
    title_fields = title_fields or search_fields[:1]
    snippet_fields = snippet_fields or search_fields

    for item in items:
        if not isinstance(item, dict):
            continue

        searchable = _extract_searchable_text(item, search_fields)
        matches_all = True
        field_matches = {}
        for term in query_terms:
            term_lower = term.lower()
            field_count = 0
            for field_name in search_fields:
                val = item.get(field_name, "")
                if val is None:
                    continue
                val_str = str(val).lower() if not isinstance(val, (dict, list)) else _json.dumps(val).lower()
                cnt = val_str.count(term_lower)
                field_count += cnt
                if cnt > 0 and field_name in title_fields:
                    field_count += cnt  # double-weight title matches
            if field_count == 0:
                matches_all = False
            field_matches[term] = field_count

        if not matches_all:
            # At least one term must match for inclusion
            if not any(field_matches.values()):
                continue

        # Extract title
        title = ""
        for tf in title_fields:
            val = item.get(tf, "")
            if val:
                title = str(val)[:100]
                break

        # Extract snippet
        snippet_text = ""
        for sf in snippet_fields:
            val = item.get(sf, "")
            if val:
                snippet_text = str(val)[:500]
                break

        # Extract URL
        url = None
        if url_field:
            url = item.get(url_field)

        # Timestamp
        ts = item.get(timestamp_field, item.get("updated_at", item.get("timestamp", "")))

        relevance = _compute_relevance(query_terms, searchable, field_matches)
        if relevance > 0:
            # Apply domain weight
            weighted_score = relevance * _DOMAIN_WEIGHTS.get(source, 1.0)
            highlight_terms = [t for t, c in field_matches.items() if c > 0]
            item_type = item.get("type") or item.get("_learning_type") or source
            item_id = str(item.get("id", item.get("key", item.get("_id", ""))))
            route = item.get("url") or item.get("route") or _default_route(source, item_id)
            results.append(SearchResult(
                id=item_id,
                source=source,
                title=title or f"{source} result",
                snippet=_highlight(snippet_text, query_terms),
                url=url,
                score=weighted_score,
                relevance=weighted_score / (_DOMAIN_WEIGHTS.get(source, 1.0) + 0.01),
                metadata={k: v for k, v in item.items() if k not in ("id",)},
                timestamp=ts,
                permissions={"user_id": item.get("user_id", "")},
                domain=source,
                type=item_type,
                route=route,
                related_objects=_related_objects(source, item_id, item),
            ))

    return results


# --------------------------------------------------------------------------- #
# Domain-specific search implementations
# --------------------------------------------------------------------------- #

def _search_knowledge(user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("knowledge")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, [], "knowledge",
        search_fields=["content", "key", "value", "title"],
        title_fields=["key", "title"],
        snippet_fields=["value", "content"],
        timestamp_field="created_at",
    )


def _search_knowledge_with_query(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("knowledge")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["content", "key", "value", "title", "tags"],
        source="knowledge",
        title_fields=["key", "title"],
        snippet_fields=["value", "content"],
        timestamp_field="created_at",
    )


def _search_memory(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("memory")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["content", "key", "value", "text", "memory", "tags"],
        source="memory",
        title_fields=["key", "title"],
        snippet_fields=["value", "content", "text", "memory"],
        timestamp_field="created_at",
    )


def _search_notes(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("notes")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["title", "content", "tags", "body", "text"],
        source="notes",
        title_fields=["title", "name"],
        snippet_fields=["content", "body", "text"],
        timestamp_field="created_at",
    )


def _search_reminders(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("reminders")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["title", "content", "note", "tags", "description"],
        source="reminders",
        title_fields=["title", "name"],
        snippet_fields=["content", "note", "description"],
        timestamp_field="created_at",
    )


def _search_chat(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    results: List[SearchResult] = []

    # Search chat sessions
    sessions_store = get_store("chat_sessions")
    sessions_data = sessions_store.load()
    if isinstance(sessions_data, dict) and sessions_data:
        items = list(sessions_data.values())
        items = _filter_by_user(items, user_id)
        session_results = _search_text_in_items(
            items, query_terms,
            search_fields=["name", "title", "topic", "summary", "user_id"],
            source="chat",
            title_fields=["name", "title"],
            snippet_fields=["summary", "topic"],
            timestamp_field="created_at",
        )
        for r in session_results:
            r.metadata["type"] = "session"
        results.extend(session_results)

    # Search chat history messages
    history_store = get_store("chat_history")
    history_data = history_store.load()
    if isinstance(history_data, dict) and history_data:
        items = list(history_data.values())
        items = _filter_by_user(items, user_id)
        msg_results = _search_text_in_items(
            items, query_terms,
            search_fields=["content", "message", "role", "model", "session_id"],
            source="chat",
            title_fields=["role", "model"],
            snippet_fields=["content", "message"],
            timestamp_field="created_at",
        )
        for r in msg_results:
            r.metadata["type"] = "message"
        results.extend(msg_results)

    return results


def _search_agents(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("agents")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    # Agents are typically not user-scoped, but check user_id
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["name", "description", "role", "capabilities", "system_prompt", "id"],
        source="agents",
        title_fields=["name", "id"],
        snippet_fields=["description", "system_prompt"],
        timestamp_field="created_at",
    )


def _search_tasks(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    store = get_store("tasks")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["name", "description", "task_type", "status", "result", "error", "goal"],
        source="tasks",
        title_fields=["name", "goal"],
        snippet_fields=["description", "result", "error"],
        timestamp_field="created_at",
    )


def _search_browser(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    results: List[SearchResult] = []

    # Browser history
    history_store = get_store("browser_history")
    history_data = history_store.load()
    if isinstance(history_data, list) and history_data:
        items = _filter_by_user(history_data, user_id)
        hist_results = _search_text_in_items(
            items, query_terms,
            search_fields=["url", "title", "domain"],
            source="browser",
            title_fields=["title"],
            snippet_fields=["url", "title"],
            timestamp_field="visited_at",
        )
        for r in hist_results:
            r.metadata["type"] = "history"
            r.url = r.url or r.metadata.get("url")
        results.extend(hist_results)

    # Browser bookmarks
    bookmarks_store = get_store("browser_bookmarks")
    bookmarks_data = bookmarks_store.load()
    if isinstance(bookmarks_data, dict) and bookmarks_data:
        items = list(bookmarks_data.values())
        items = _filter_by_user(items, user_id)
        bm_results = _search_text_in_items(
            items, query_terms,
            search_fields=["url", "title", "tags", "notes", "domain"],
            source="browser",
            title_fields=["title"],
            snippet_fields=["notes", "url"],
            timestamp_field="created_at",
        )
        for r in bm_results:
            r.metadata["type"] = "bookmark"
            r.url = r.url or r.metadata.get("url")
        results.extend(bm_results)

    # Browser evidence
    evidence_store = get_store("browser_evidence")
    evidence_data = evidence_store.load()
    if isinstance(evidence_data, list) and evidence_data:
        items = _filter_by_user(evidence_data, user_id)
        ev_results = _search_text_in_items(
            items, query_terms,
            search_fields=["url", "title", "selected_passage", "page_context", "claim", "tags", "domain"],
            source="evidence",
            title_fields=["title", "claim"],
            snippet_fields=["selected_passage", "page_context"],
            timestamp_field="created_at",
        )
        for r in ev_results:
            r.url = r.url or r.metadata.get("url")
        results.extend(ev_results)

    # Browser page states
    page_states_store = get_store("browser_page_states")
    page_data = page_states_store.load()
    if isinstance(page_data, dict) and page_data:
        items = list(page_data.values())
        ps_results = _search_text_in_items(
            items, query_terms,
            search_fields=["url", "title", "main_content", "headings", "domain"],
            source="browser",
            title_fields=["title"],
            snippet_fields=["main_content", "url"],
            timestamp_field="extracted_at",
        )
        for r in ps_results:
            r.metadata["type"] = "page_state"
            r.url = r.url or r.metadata.get("url")
        results.extend(ps_results)

    return results


def _search_missions(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    """Search browser missions (if they exist in a missions store)."""
    store = get_store("browser_tasks")
    data = store.load()
    if not isinstance(data, dict) or not data:
        return []
    items = list(data.values())
    items = _filter_by_user(items, user_id)
    return _search_text_in_items(
        items, query_terms,
        search_fields=["goal", "description", "error", "id", "mission_id"],
        source="missions",
        title_fields=["goal", "id"],
        snippet_fields=["description", "error", "plan"],
        timestamp_field="updated_at",
    )


def _search_research(query_terms: List[str], user_id: Optional[str]) -> List[SearchResult]:
    """Search via web (ArXiv) for research content (spec §30).

    Uses the existing global_knowledge ArXiv search pattern.  This is the
    only domain that performs external web requests — it's opt-in via
    ``include_web=True`` and rate-limited by the caller.
    """
    results: List[SearchResult] = []
    query_str = " ".join(query_terms)
    if not query_str:
        return results

    # Search ArXiv via their public API
    encoded = urllib.parse.urlencode({"search_query": f"all:{query_str}", "max_results": "5", "sortBy": "relevance"})
    url = f"http://export.arxiv.org/api/query?{encoded}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Search/1.0 (+http://jarvis.local)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return results

    # Parse Atom XML entries
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return results

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        summary_el = entry.find("atom:summary", ns)
        summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
        link_el = entry.find("atom:link[@rel='alternate']", ns)
        link = link_el.get("href") if link_el is not None else ""
        id_el = entry.find("atom:id", ns)
        paper_id = id_el.text.strip() if id_el is not None and id_el.text else ""
        updated_el = entry.find("atom:updated", ns)
        updated = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

        relevance = _compute_relevance(query_terms, _normalize_text(title + " " + summary), {})
        results.append(SearchResult(
            id=paper_id,
            source="research",
            title=title[:100],
            snippet=_highlight(summary, query_terms),
            url=link,
            score=relevance * _DOMAIN_WEIGHTS.get("research", 0.7),
            relevance=relevance,
            metadata={"type": "arxiv", "paper_id": paper_id},
            timestamp=updated,
        ))

    return results


def _search_learning(query: str, user_id: Optional[str], query_terms: List[str]) -> List[SearchResult]:
    """Search the learning arena datasets (spec §35-36, §58).

    Delegates to the shared learning-bridge singleton so that learning data
    created at runtime (feedback, lessons, training runs) is searchable without
    a dedicated database.
    """
    from .learning_bridge import get_learning_searchable_items
    items = get_learning_searchable_items(user_id=user_id)
    return _search_text_in_items(
        items,
        query_terms,
        ["title", "question", "claim", "name", "content", "answer", "explanation", "description", "text"],
        source="learning",
        url_field=None,
        title_fields=["title", "question", "claim", "name"],
        snippet_fields=["content", "answer", "explanation", "description", "text"],
        timestamp_field="timestamp",
    )


# --------------------------------------------------------------------------- #
# Domain searcher registry
# --------------------------------------------------------------------------- #

_DOMAIN_SEARCHERS = {
    SearchDomain.KNOWLEDGE: _search_knowledge_with_query,
    SearchDomain.MEMORY: _search_memory,
    SearchDomain.NOTES: _search_notes,
    SearchDomain.REMINDERS: _search_reminders,
    SearchDomain.CHAT: _search_chat,
    SearchDomain.AGENTS: _search_agents,
    SearchDomain.TASKS: _search_tasks,
    SearchDomain.BROWSER: _search_browser,
    SearchDomain.EVIDENCE: _search_browser,  # evidence is included in browser search
    SearchDomain.MISSIONS: _search_missions,
    SearchDomain.RESEARCH: _search_research,
    SearchDomain.LEARNING: _search_learning,
}


# --------------------------------------------------------------------------- #
# Federated search execution
# --------------------------------------------------------------------------- #

def _resolve_domains(domain_param: str) -> List[SearchDomain]:
    """Resolve the domain parameter into a list of domains to search."""
    if domain_param == "all" or domain_param == "":
        return list(_DEFAULT_DOMAINS)
    try:
        return [SearchDomain(domain_param)]
    except ValueError:
        return list(_DEFAULT_DOMAINS)


def _run_federated_search(
    query: str,
    domains: List[SearchDomain],
    user_id: Optional[str],
    limit: int,
    include_web: bool,
    semantic: bool = False,
) -> Tuple[List[SearchResult], float, Dict[str, Any]]:
    """Run search across multiple domains in parallel (spec §26).

    Uses a thread pool to search domains concurrently for performance.
    When ``semantic`` is True and a ranker is available, results are
    re-ranked by neural/fingerprint semantic similarity (spec §43, §57).
    Returns ``(results, took_ms, ranking_info)``.
    """
    start = datetime.now(timezone.utc)
    query_terms = [t for t in re.split(r'[\s,;]+', query.strip()) if t]
    if not query_terms:
        return [], 0.0, {}

    all_results: List[SearchResult] = []
    effective_domains = []

    for dom in domains:
        if dom == SearchDomain.EVIDENCE:
            # Evidence is searched alongside browser
            continue
        if dom == SearchDomain.RESEARCH and not include_web:
            continue
        effective_domains.append(dom)

    with ThreadPoolExecutor(max_workers=min(len(effective_domains), 5)) as pool:
        future_map = {}
        for dom in effective_domains:
            searcher = _DOMAIN_SEARCHERS.get(dom)
            if searcher:
                future_map[pool.submit(searcher, query_terms, user_id)] = dom

        for future in as_completed(future_map, timeout=30):
            dom = future_map[future]
            try:
                results = future.result()
                all_results.extend(results)
            except Exception:
                # A single domain failing shouldn't break the whole search
                continue

    # Sort by score (descending) primarily, then by timestamp (most recent first)
    # Use two stable passes so we can handle string timestamps correctly.
    all_results.sort(key=lambda r: r.timestamp or "", reverse=True)
    all_results.sort(key=lambda r: r.score, reverse=True)

    ranking_info: Dict[str, Any] = {"method": "text"}
    # Semantic reranking (spec §43, §57) — optional, never required.
    if semantic and all_results:
        try:
            from ..semantic_index import get_ranker
            ranker = get_ranker()
            if ranker.available():
                candidates = [(r.title + " " + r.snippet) for r in all_results]
                ranked = ranker.rerank(query, candidates, top_k=len(all_results))
                if ranked:
                    new_order: List[SearchResult] = []
                    scores_by_idx: Dict[int, float] = {idx: sc for idx, sc in ranked}
                    for idx, _ in ranked:
                        r = all_results[idx]
                        r.semantic_score = scores_by_idx[idx]
                        new_order.append(r)
                    # Preserve any items not returned by reranker (score <= 0.0).
                    seen = {id(r) for r in new_order}
                    for r in all_results:
                        if id(r) not in seen:
                            new_order.append(r)
                    all_results = new_order
                    ranking_info = {"method": ranker.backend(), "reranked": True,
                                    "top_k": len(ranked)}
        except Exception as exc:  # noqa: BLE001 — semantic is best-effort
            ranking_info = {"method": "text", "reranked": False, "error": str(exc)[:200]}

    all_results = all_results[:limit]

    elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    return all_results, elapsed_ms, ranking_info


# --------------------------------------------------------------------------- #
# API endpoints (spec §26, §63)
# --------------------------------------------------------------------------- #

@router.get("/", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., description="Search query"),
    domain: str = Query(default="all", description="Search domain (or 'all')"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    include_web: bool = Query(default=True, description="Include web search (slower)"),
    highlight: bool = Query(default=True, description="Highlight matches in snippets"),
    semantic: bool = Query(default=False, description="Semantic reranking (spec §43)"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Federated global search across all platform domains (spec §26, §63).

    Searches across:
      - **Knowledge** — key-value knowledge store
      - **Memory** — cognitive memory entries
      - **Chat** — conversation sessions and messages
      - **Agents** — agent definitions
      - **Tasks** — task definitions
      - **Browser** — history, bookmarks, evidence, page states
      - **Notes** — user notes
      - **Research** — ArXiv web search (when include_web=true)
      - **Learning** — lessons, datasets, training runs, model revisions

    Results are normalised into a common schema with a ``source`` field
    indicating the domain, and an ``id`` for cross-system object inspection.

    Does NEVER fabricate results.  Each result is backed by real data
    stored in a platform collection.
    """
    user_id = user.get("id")
    # Structured query parsing: extract field modifiers (spec §40).
    free_text, modifiers = _parse_structured_query(q)
    if free_text != q:
        # Use only the free-text portion for candidate generation.
        search_query = free_text
    else:
        search_query = q
    requested_domain = modifiers.get("domain", domain)
    domains = _resolve_domains(requested_domain)

    results, took_ms, ranking_info = _run_federated_search(
        query=search_query or q,
        domains=domains,
        user_id=user_id,
        limit=limit,
        include_web=include_web,
        semantic=semantic,
    )

    # Apply structured filters on the candidate set (spec §40).
    type_filter = modifiers.get("type")
    after_filter = modifiers.get("after")
    if type_filter or after_filter:
        filtered: List[SearchResult] = []
        for r in results:
            if type_filter and r.type != type_filter:
                continue
            if after_filter and r.timestamp and r.timestamp < after_filter:
                continue
            filtered.append(r)
        results = filtered

    # Record this search in history (spec §44).
    _record_search_history(user_id, q, [d.value for d in domains], len(results))

    # Build highlights
    highlights: Dict[str, List[str]] = {}
    query_lower = q.lower()
    for r in results:
        matched_terms = []
        for term in query_lower.split():
            if term and term in (r.snippet.lower() + r.title.lower()):
                matched_terms.append(term)
        if matched_terms:
            highlights[r.id] = matched_terms

    return SearchResponse(
        query=q,
        total_results=len(results),
        results=results,
        domains_searched=[d.value for d in domains if not (d == SearchDomain.EVIDENCE)],
        took_ms=round(took_ms, 2),
        highlights=highlights if highlight else {},
        semantic=ranking_info.get("reranked", False),
        semantic_backend=ranking_info.get("method", ""),
    )


@router.post("/", response_model=SearchResponse)
async def global_search_post(
    body: SearchQuery,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """POST variant of global search — for longer queries and structured input."""
    user_id = user.get("id")
    domains = _resolve_domains(body.domain or "all")

    results, took_ms, ranking_info = _run_federated_search(
        query=body.query,
        domains=domains,
        user_id=user_id,
        limit=body.limit,
        include_web=body.include_web,
        semantic=body.semantic,
    )

    highlights: Dict[str, List[str]] = {}
    query_lower = body.query.lower()
    for r in results:
        matched_terms = [t for t in query_lower.split() if t and t in (r.snippet.lower() + r.title.lower())]
        if matched_terms and body.highlight:
            highlights[r.id] = matched_terms

    return SearchResponse(
        query=body.query,
        total_results=len(results),
        results=results,
        domains_searched=[d.value for d in domains if d != SearchDomain.EVIDENCE],
        took_ms=round(took_ms, 2),
        highlights=highlights if body.highlight else {},
        semantic=ranking_info.get("reranked", False),
        semantic_backend=ranking_info.get("method", ""),
    )


@router.get("/domains", response_model=List[str])
async def list_search_domains(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List all searchable domains (spec §26)."""
    return [d.value for d in SearchDomain if d != SearchDomain.ALL]


@router.get("/suggest")
async def search_suggestions(
    q: str = Query(..., description="Partial query for suggestions"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get search suggestions based on existing platform data.

    Returns matching titles and recent queries from all domains.
    """
    user_id = user.get("id")
    suggestions: List[str] = []

    if _normalize_text(q):
        # Search browser history for URL suggestions
        history_store = get_store("browser_history")
        history = history_store.load()
        if isinstance(history, list):
            for entry in history:
                if not isinstance(entry, dict):
                    continue
                if not _filter_by_user([entry], user_id):
                    continue
                title = str(entry.get("title", "")).lower()
                if _normalize_text(q) in title or q.lower() in str(entry.get("url", "")).lower():
                    suggestions.append(entry.get("title", entry.get("url", ""))[:80])
                    if len(suggestions) >= 10:
                        break

        # Search bookmarks
        bookmarks_store = get_store("browser_bookmarks")
        bookmarks = bookmarks_store.load()
        if isinstance(bookmarks, dict):
            for entry in bookmarks.values():
                title = str(entry.get("title", "")).lower()
                if _normalize_text(q) in title:
                    suggestions.append(entry.get("title", "")[:80])
                    if len(suggestions) >= 10:
                        break

    return {"query": q, "suggestions": suggestions[:10]}


@router.get("/status")
async def search_status(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Report the health and availability of each search domain (spec §18)."""
    statuses: Dict[str, Any] = {}
    for domain in SearchDomain:
        if domain == SearchDomain.ALL:
            continue
        searcher = _DOMAIN_SEARCHERS.get(domain)
        if searcher is None:
            statuses[domain.value] = {"available": False, "reason": "Not implemented"}
            continue

        try:
            # Quick probe — search with a single char to test availability
            store_name_map = {
                SearchDomain.KNOWLEDGE: "knowledge",
                SearchDomain.MEMORY: "memory",
                SearchDomain.CHAT: "chat_sessions",
                SearchDomain.AGENTS: "agents",
                SearchDomain.TASKS: "tasks",
                SearchDomain.BROWSER: "browser_history",
                SearchDomain.NOTES: "notes",
                SearchDomain.REMINDERS: "reminders",
                SearchDomain.RESEARCH: "research",
                SearchDomain.EVIDENCE: "browser_evidence",
                SearchDomain.MISSIONS: "browser_tasks",
            }
            store_name = store_name_map.get(domain, domain.value)
            store = get_store(store_name)
            data = store.load()

            count = 0
            if isinstance(data, dict):
                count = len(data)
            elif isinstance(data, list):
                count = len(data)

            statuses[domain.value] = {
                "available": True,
                "item_count": count,
                "include_web": domain == SearchDomain.RESEARCH,
            }
        except Exception as e:
            statuses[domain.value] = {"available": False, "error": str(e)[:200]}

    return {
        "domains": statuses,
        "healthy": all(s.get("available", False) for s in statuses.values()),
    }


@router.get("/history")
async def search_history(
    limit: int = Query(default=50, ge=1, le=200, description="Max recent searches"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Recent + saved search history for the caller (spec §44)."""
    user_id = user.get("id")
    history_store = get_store("search_history")
    raw = history_store.load()
    if not isinstance(raw, list):
        raw = []
    # Scope to the user (system searches have user_id=None are excluded).
    items = [h for h in raw if h.get("user_id") == user_id]
    items = items[-limit:]
    items.reverse()  # most-recent first
    return {"history": items}


@router.post("/explain")
async def search_explain(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Structured query inspection + ranking explanation (spec §38, §43).

    Splits a query into free-text and structured modifiers, shows which domains
    were searched, and reports the ranking method used.
    """
    query = body.get("query", "")
    user_id = user.get("id")
    free_text, modifiers = _parse_structured_query(query)
    requested_domain = modifiers.get("domain", "all")
    domains = _resolve_domains(requested_domain)

    results, took_ms, ranking_info = _run_federated_search(
        query=free_text or query,
        domains=domains,
        user_id=user_id,
        limit=body.get("limit", 10),
        include_web=body.get("include_web", True),
        semantic=body.get("semantic", False),
    )

    return {
        "query": query,
        "parsed": {
            "free_text": free_text,
            "modifiers": modifiers,
        },
        "domains_searched": [d.value for d in domains if d != SearchDomain.EVIDENCE],
        "domains_requested": body.get("domain", requested_domain),
        "ranking": {
            "method": ranking_info.get("method", "text"),
            "semantic": ranking_info.get("reranked", False),
            "top_k": ranking_info.get("top_k"),
        },
        "result_count": len(results),
        "took_ms": round(took_ms, 2),
        "top_results": [r.model_dump() for r in results[: body.get("limit", 10)]],
    }


# --------------------------------------------------------------------------- #
# Search → Platform handoffs (spec §35–42)
# --------------------------------------------------------------------------- #

@router.post("/to/browser")
async def search_to_browser(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Search → Browser handoff (spec §35).

    Given a search query, navigate a browser session to the result URL.
    """
    query = body.get("query", "")
    session_id = body.get("session_id", "")
    tab_id = body.get("tab_id")

    user_id = user.get("id")
    domains = _resolve_domains(body.get("domain", "all"))

    # Exclude web search from handoff — we need concrete platform results
    handoff_domains = [d for d in domains if d != SearchDomain.RESEARCH]

    results, took_ms, _ = _run_federated_search(
        query=query,
        domains=handoff_domains,
        user_id=user_id,
        limit=body.get("limit", 10),
        include_web=False,
    )

    # Pick the best result and navigate to it
    if results:
        best = results[0]
        target_url = best.url or best.metadata.get("url", "")
        if target_url:
            from ..browser_engine import classify_navigation_context
            nav_ctx = classify_navigation_context(target_url)
            return {
                "query": query,
                "navigated": True,
                "target_url": target_url,
                "navigation_context": {
                    "presentation": nav_ctx.presentation.value,
                    "reason": nav_ctx.reason,
                    "confidence": nav_ctx.confidence,
                },
                "session_id": session_id,
                "tab_id": tab_id,
                "result": best.model_dump(),
            }

    return {
        "query": query,
        "navigated": False,
        "target_url": "",
        "reason": "No navigable results found",
        "session_id": session_id,
        "tab_id": tab_id,
    }


@router.post("/to/research")
async def search_to_research(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Search → Research handoff (spec §36).

    Given a search query, create a research session with the query as a
    starting question and seed it with search results.
    """
    query = body.get("query", "")
    user_id = user.get("id")

    results, took_ms, _ = _run_federated_search(
        query=query,
        domains=_DEFAULT_DOMAINS,
        user_id=user_id,
        limit=body.get("limit", 10),
        include_web=True,
    )

    # Build the research session
    from ..core import get_store
    sessions_store = get_store("browser_sessions")
    sessions = sessions_store.load()
    if not isinstance(sessions, dict):
        sessions = {}

    import uuid
    session_id = f"research-{uuid.uuid4().hex[:12]}"
    sessions[session_id] = {
        "id": session_id,
        "user_id": user_id,
        "name": f"Research: {query[:80]}",
        "type": "research",
        "query": query,
        "privacy_mode": "research",
        "tabs": [],
        "active_tab_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "seed_results": [r.model_dump() for r in results],
    }
    sessions_store.save()

    return {
        "research_session_id": session_id,
        "query": query,
        "seeded_results": len(results),
        "took_ms": round(took_ms, 2),
        "results": [r.model_dump() for r in results],
    }


@router.post("/to/knowledge")
async def search_to_knowledge(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Search → Knowledge handoff (spec §37).

    Promote a search result to a knowledge entry.
    """
    query = body.get("query", "")
    result_id = body.get("result_id", "")
    user_id = user.get("id")

    results, _, _ = _run_federated_search(
        query=query,
        domains=_DEFAULT_DOMAINS,
        user_id=user_id,
        limit=10,
        include_web=False,
    )

    # Find the matching result
    matching = None
    for r in results:
        if r.id == result_id or r.id == results[0].id:
            matching = r
            break
    if matching is None:
        matching = results[0] if results else None

    if matching:
        knowledge_store = get_store("knowledge")
        data = knowledge_store.load()
        if not isinstance(data, dict):
            data = {}

        import uuid
        key = f"search-{uuid.uuid4().hex[:12]}"
        entry = {
            "key": key,
            "title": matching.title,
            "value": matching.snippet or matching.metadata.get("content", "") or "No content available",
            "source": matching.source,
            "source_id": matching.id,
            "user_id": user_id,
            "tags": matching.metadata.get("tags", []),
            "url": matching.url,
            "metadata": matching.metadata,
            "created_at": now_iso(),
        }
        data[key] = entry
        knowledge_store.save()

        return {"promoted": True, "knowledge_key": key, "entry": entry}

    return {"promoted": False, "reason": "No matching search result to promote"}


# --------------------------------------------------------------------------- #
# Cross-system object inspection (spec §17)
# --------------------------------------------------------------------------- #

@router.get("/inspect/{source}/{item_id}")
async def inspect_object(
    source: str,
    item_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Cross-system object inspection (spec §17).

    Given a source domain and item ID (from search results), retrieve the
    full object regardless of which domain it lives in.
    """
    user_id = user.get("id")

    # Learning artifacts live in the in-memory learning arena bridge (spec §41),
    # not in a JSON store — resolve them separately.
    if source == "learning":
        from ..learning_bridge import get_learning_searchable_items
        for item in get_learning_searchable_items(user_id=user_id):
            if item.get("id") == item_id or item.get("key") == item_id:
                _check_learning_permissions(item, user_id)
                return {"source": "learning", "id": item_id, "object": item}
        raise HTTPException(status_code=404, detail=f"Object not found: learning/{item_id}")

    # Map source to store and search key
    store_map = {
        "knowledge": ("knowledge", "key"),
        "memory": ("memory", "id"),
        "chat": ("chat_sessions", "id"),
        "agents": ("agents", "id"),
        "tasks": ("tasks", "id"),
        "browser": ("browser_history", "id"),
        "notes": ("notes", "id"),
        "reminders": ("reminders", "id"),
        "research": ("browser_evidence", "id"),
        "evidence": ("browser_evidence", "id"),
        "missions": ("browser_tasks", "id"),
    }

    if source not in store_map:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

    store_name, key_field = store_map[source]
    store = get_store(store_name)
    data = store.load()

    found = None
    if isinstance(data, dict):
        found = data.get(item_id)
        if found is None:
            # Try looking up by key field
            for v in data.values():
                if isinstance(v, dict) and str(v.get(key_field, "")) == item_id:
                    found = v
                    break
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get("id", "")) == item_id:
                found = item
                break

    if found is None:
        raise HTTPException(status_code=404, detail=f"Object not found: {source}/{item_id}")

    # Permission check
    item_user = found.get("user_id") if isinstance(found, dict) else None
    if item_user and item_user != user_id and item_user != "system":
        raise HTTPException(status_code=403, detail="Not authorized to view this object")

    return {
        "source": source,
        "id": item_id,
        "object": found,
    }
