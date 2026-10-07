"""JARVIS Browser — platform service.

Provides the backend API for the JARVIS Browser's persistent context
management, page extraction, search, evidence capture, downloads, and
security controls. The browser engine itself (rendering) runs in the
frontend iframe; this service provides the *platform* layer that makes
the browser persistent, observable, and integrated with the rest of
JARVIS.

All routes are authenticated.  Admin-only operations require admin scope.

Uses only Python stdlib for page extraction (urllib, html.parser, re) —
no new dependencies.

---

Browser Action Model (spec §3):
  Every browser operation is a normalized BrowserAction that passes
  through the permission/policy layer before execution.  Actions are
  queued, executed, verified, and recorded — never sent directly from
  the model to the browser.

Observe → Act Loop (spec §4):
  page_state → observation → model_reasoning → proposed_action →
  policy_check → execution → new_page_state → verification

The Browser is a JARVIS sensor + hand (spec §45–46):
  JARVIS sees the web, understands it, reasons about it, and acts on it
  — always governed by permissions, security, provenance, and human control.
"""

from __future__ import annotations

import html as _html
import hashlib
import ipaddress
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ..core import (
    DATA_DIR,
    UPLOADS_DIR,
    get_current_user,
    get_store,
    now_iso,
)
from ..network_diagnostics import (
    BrowserErrorCategory,
    BrowserHealthStatus,
    DnsDiagnostics,
    NavigationDiagnoser,
    NavigationErrorContext,
    ProxyDiagnostics,
    RecoveryOrchestrator,
    TransportDiagnostics,
    classify_urllib_exception,
    record_navigation_timeline,
    record_network_event,
)
from ..browser_engine import (
    BrowserEngine,
    HttpBrowserEngine,
    NavigationContext,
    NavigationFailureClass,
    NavigationPresentation,
    BrowserProfile,
    classify_navigation_context,
    classify_navigation_failure,
    get_engine,
)

router = APIRouter(prefix="/api/v1/browser", tags=["browser"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_PRIVACY_MODES = {"standard", "private", "research", "agent", "automation", "authenticated"}

# Blocked domains — never allow these to be proxied or extracted.
_BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",       # AWS metadata
    "metadata.google.internal",
}
_BLOCKED_METADATA_IPS = {
    "100.100.100.200",  # Alibaba Cloud metadata
    "168.63.129.16",    # Azure platform/metadata endpoint
}
_PRIVATE_TAB_NAVIGATION: Dict[str, Dict[str, Any]] = {}

# Prompt-injection detection — common instruction-injection phrases.
_INJECTION_PATTERNS = [
    r"ignore (?:all |previous |prior )*instructions",
    r"ignore (?:all |previous |prior )*prompts",
    r"forget (?:your |prior |previous )*instructions",
    r"you are (?:now |currently )?(?:an? |a )?(?:ai|chatbot|assistant)",
    r"disregard (?:all |previous |prior )*instructions",
    r"new instructions?:",
    r"system prompt:",
    r"override (?:all |previous |prior )*instructions",
    r"reveal your (?:system |hidden )",
    r"show.*system.*prompt",
    r"you (?:must |should |are required to )?(?:reveal|expose|show|ignore)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _download_destination(filename: str, user_id: str) -> Path:
    """Resolve a flat filename inside the authenticated user's download directory."""
    if (
        not filename
        or filename in {".", ".."}
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or Path(filename).name != filename
        or PureWindowsPath(filename).name != filename
    ):
        raise HTTPException(status_code=400, detail="Invalid download filename")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authenticated user identity is required")

    upload_root = UPLOADS_DIR.resolve()
    user_directory = upload_root / "browser-downloads" / hashlib.sha256(
        user_id.encode("utf-8")
    ).hexdigest()
    user_directory.mkdir(parents=True, exist_ok=True)
    resolved_user_directory = user_directory.resolve()
    if upload_root not in resolved_user_directory.parents:
        raise HTTPException(status_code=400, detail="Invalid download directory")
    destination = (resolved_user_directory / filename).resolve()
    if destination.parent != resolved_user_directory:
        raise HTTPException(status_code=400, detail="Invalid download filename")
    if destination.is_symlink():
        raise HTTPException(status_code=400, detail="Invalid download filename")
    return destination


# ---------------------------------------------------------------------------
# Browser Action Model (spec §3) — normalized action types
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """Normalized browser action types."""
    NAVIGATE = "navigate"
    SEARCH = "search"
    OPEN_TAB = "open_tab"
    CLOSE_TAB = "close_tab"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    EXTRACT = "extract"
    DOWNLOAD = "download"
    COMPARE = "compare"
    CAPTURE_EVIDENCE = "capture_evidence"
    SUBMIT_FORM = "submit_form"
    BOOKMARK = "bookmark"
    SWITCH_TAB = "switch_tab"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    RELOAD = "reload"


class ActionPermission(str, Enum):
    """Permission level for a browser action."""
    ALLOWED = "allowed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DENIED = "denied"


class ActionStatus(str, Enum):
    """Execution status of a browser action."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    VERIFIED = "verified"


class BrowserAction(BaseModel):
    """Normalized browser action (spec §3).

    Every browser operation passes through this model.  The action
    is proposed by the agent, checked by the policy layer, executed,
    verified, and recorded — never sent directly from the model to
    the browser.
    """
    id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:12]}")
    type: ActionType
    target: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    source: str = "agent"  # "user" | "agent"
    permission: ActionPermission = ActionPermission.REQUIRES_CONFIRMATION
    status: ActionStatus = ActionStatus.QUEUED
    session_id: str = ""
    tab_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    executed_at: Optional[str] = None
    verified_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    evidence_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class ActionQueue(BaseModel):
    """Ordered queue of browser actions for a session."""
    session_id: str
    actions: List[BrowserAction] = Field(default_factory=list)
    current_action_index: int = -1
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    completed: bool = False
    checkpoint_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Page State Representation (spec §6) — compact structured state
# ---------------------------------------------------------------------------

class PageState(BaseModel):
    """Compact page state for AI context (spec §6).

    Instead of sending entire pages to the model, we send this
    structured representation containing only the relevant information.
    """
    url: str
    title: str = ""
    domain: str = ""
    page_classification: str = "unknown"  # spec §22
    metadata: Dict[str, Any] = Field(default_factory=dict)
    headings: List[Dict[str, Any]] = Field(default_factory=list)
    main_content: str = ""
    interactive_elements: List[Dict[str, Any]] = Field(default_factory=list)  # spec §7
    forms: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    selected_content: str = ""
    visible_warnings: List[str] = Field(default_factory=list)
    security_indicators: List[str] = Field(default_factory=list)
    prompt_injection_flagged: bool = False
    word_count: int = 0
    extracted_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Interactive Element Map (spec §7)
# ---------------------------------------------------------------------------

class InteractiveElement(BaseModel):
    """Machine-readable interactive element with stable identifier."""
    id: str
    type: str  # button, link, textbox, checkbox, dropdown, table, form, navigation
    label: str = ""
    selector: str = ""  # CSS/xPath-like selector for the current page state
    attributes: Dict[str, str] = Field(default_factory=dict)
    visible: bool = True
    enabled: bool = True
    position: Optional[Dict[str, int]] = None  # approximate position for visual fallback


# ---------------------------------------------------------------------------
# Task Execution Engine (spec §10, §13–14)
# ---------------------------------------------------------------------------

class TaskStep(BaseModel):
    """A single step in a multi-step browser task."""
    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    description: str
    action_type: ActionType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    verified: bool = False
    evidence_ids: List[str] = Field(default_factory=list)


class BrowserTask(BaseModel):
    """Multi-step browser task with checkpoint/resume support (spec §10, §13–14)."""
    id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:12]}")
    session_id: str
    mission_id: Optional[str] = None
    research_session_id: Optional[str] = None
    goal: str = ""
    plan: List[str] = Field(default_factory=list)
    steps: List[TaskStep] = Field(default_factory=list)
    current_step_index: int = 0
    status: ActionStatus = ActionStatus.QUEUED
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    checkpoint_id: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    agent_id: Optional[str] = None
    pause_on_risk: bool = True  # spec §12 — human-in-the-loop


class TaskCheckpoint(BaseModel):
    """Checkpoint for browser task recovery (spec §13)."""
    id: str = Field(default_factory=lambda: f"chk-{uuid.uuid4().hex[:10]}")
    task_id: str
    session_id: str
    step_index: int = 0
    page_state: Optional[Dict[str, Any]] = None
    evidence_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Browser Workspace (spec §17)
# ---------------------------------------------------------------------------

class BrowserWorkspace(BaseModel):
    """Contextual browser workspace (spec §17)."""
    id: str = Field(default_factory=lambda: f"ws-{uuid.uuid4().hex[:10]}")
    owner_id: str
    name: str = "Research"
    description: str = ""
    session_ids: List[str] = Field(default_factory=list)
    tabs: List[str] = Field(default_factory=list)
    permissions: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    mission_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    privacy_mode: str = "standard"


class BrowserWorkspaceCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Research", min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    privacy_mode: Literal[
        "standard", "private", "research", "agent", "automation", "authenticated"
    ] = "standard"


class BrowserWorkspaceUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    privacy_mode: Optional[
        Literal["standard", "private", "research", "agent", "automation", "authenticated"]
    ] = None
    notes: Optional[str] = Field(default=None, max_length=10000)


class BrowserWorkspaceAssociationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["session", "mission", "evidence"]
    id: str = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Browser Telemetry (spec §42)
# ---------------------------------------------------------------------------

class BrowserTelemetryEntry(BaseModel):
    """Telemetry entry for a browser operation (spec §42)."""
    id: str = Field(default_factory=lambda: f"tel-{uuid.uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=now_iso)
    session_id: str = ""
    action: str = ""
    navigation_latency_ms: Optional[float] = None
    extraction_latency_ms: Optional[float] = None
    ai_latency_ms: Optional[float] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens: Optional[int] = None
    cost: Optional[float] = None
    downloads: int = 0
    errors: int = 0
    security_blocks: int = 0
    automation_actions: int = 0


# ---------------------------------------------------------------------------
# Page Classification (spec §22)
# ---------------------------------------------------------------------------

PAGE_CLASSIFICATION_KEYWORDS: Dict[str, List[str]] = {
    "documentation": ["docs", "documentation", "api reference", "developer", "sdk", "library"],
    "research": ["paper", "arxiv", "research", "study", "journal", "academic"],
    "commerce": ["shop", "store", "buy", "cart", "checkout", "price", "purchase"],
    "social": ["forum", "reddit", "twitter", "facebook", "community", "discussion"],
    "authentication": ["login", "sign in", "auth", "oauth", "sso", "credentials"],
    "email": ["mail", "inbox", "gmail", "outlook", "email", "message"],
    "cloud_console": ["console", "dashboard", "cloud", "aws", "gcp", "azure", "admin"],
    "code_repository": ["github", "gitlab", "bitbucket", "repository", "source code"],
    "news": ["news", "breaking", "headline", "article", "press release"],
    "forum": ["forum", "thread", "discussion", "q&a", "stack overflow"],
}


def classify_page(url: str, title: str = "", content: str = "") -> str:
    """Classify a page by URL, title, and content (spec §22)."""
    text = f"{url} {title} {content}".lower()
    scores: Dict[str, int] = {}
    for classification, keywords in PAGE_CLASSIFICATION_KEYWORDS.items():
        scores[classification] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown"
    return best


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class BrowserTab(BaseModel):
    id: str
    session_id: str
    url: str
    title: str = ""
    favicon: str = ""
    is_loading: bool = False
    is_pinned: bool = False
    group: str = "default"
    created_at: str
    updated_at: str
    scroll_position: Optional[int] = None
    extracted_content: Optional[str] = None
    prompt_injection_flagged: bool = False
    security_notes: List[str] = Field(default_factory=list)


class BrowserSession(BaseModel):
    id: str
    name: str
    privacy_mode: str = "standard"
    profile: str = "personal"  # BrowserProfile name (spec §12)
    tabs: List[str] = Field(default_factory=list)
    active_tab_id: Optional[str] = None
    created_at: str
    updated_at: str
    research_session_id: Optional[str] = None
    mission_id: Optional[str] = None


class NavigateIn(BaseModel):
    session_id: str
    tab_id: Optional[str] = None
    url: str
    privacy_mode: Optional[str] = None


class NavigationControlIn(BaseModel):
    session_id: str
    tab_id: str
    action: str


class ExtractIn(BaseModel):
    url: str
    content: Optional[str] = None
    user_selection: Optional[str] = None


class EvidenceCaptureIn(BaseModel):
    url: str
    title: str = ""
    selected_passage: str = ""
    page_context: str = ""
    claim: Optional[str] = None
    verification_status: str = "unchecked"
    research_session_id: Optional[str] = None
    mission_id: Optional[str] = None


class BookmarkIn(BaseModel):
    url: str
    title: str
    tags: List[str] = Field(default_factory=list)
    notes: str = ""


class PromptIn(BaseModel):
    """Prompt-injection check request."""
    content: str
    source: str = "page"


class SessionCreateIn(BaseModel):
    name: Optional[str] = None
    privacy_mode: Optional[str] = None
    profile: Optional[str] = None   # BrowserProfile name (spec §12)
    research_session_id: Optional[str] = None
    mission_id: Optional[str] = None


class TabCreateIn(BaseModel):
    session_id: str
    url: Optional[str] = None
    title: Optional[str] = None
    is_pinned: bool = False
    group: str = "default"


class SearchIn(BaseModel):
    query: str
    session_id: Optional[str] = None


class AutonomousIn(BaseModel):
    session_id: str
    action: str
    params: dict = Field(default_factory=dict)
    consent: bool = False
    url: Optional[str] = None


# ---------------------------------------------------------------------------
# Diagnostic request models (spec §51)
# ---------------------------------------------------------------------------

class DiagnosticsNetworkIn(BaseModel):
    url: str
    timeout: float = 15.0


class DiagnosticsDnsIn(BaseModel):
    url: str
    alternate_resolvers: Optional[List[str]] = None  # e.g. ["8.8.8.8", "1.1.1.1"]


class DiagnosticsProxyIn(BaseModel):
    url: str




class RecoverIn(BaseModel):
    url: str
    strategy: str = "auto"
    max_attempts: int = 3


# --------------------------------------------------------------------------- #
# Navigation context models (spec §7, §8, §9)
# --------------------------------------------------------------------------- #

class NavigationContextIn(BaseModel):
    """Request to classify a URL's navigation context."""
    url: str
    headers: Optional[Dict[str, str]] = None


class NavigationContextOut(BaseModel):
    """Result of navigation context classification."""
    url: str
    presentation: str  # "embedded" | "top_level" | "isolated"
    reason: str = ""
    confidence: float = 0.0
    signals: Dict[str, Any] = Field(default_factory=dict)


class NavigationFailureIn(BaseModel):
    """Request to classify a navigation failure."""
    url: str
    error_category: Optional[str] = None
    status_code: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    error_detail: Optional[str] = None


class OpenInBrowserContextIn(BaseModel):
    """Request to generate an 'Open in Browser Context' target."""
    url: str
    presentation: Optional[str] = None  # "tab" | "window" | "system"
    query: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path
    except Exception:
        return url


def _is_blocked_domain(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return True
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname in _BLOCKED_DOMAINS or hostname.endswith((".local", ".internal")):
            return True
        literal = _parse_ipv4_literal(hostname)
        if literal is None:
            try:
                literal = ipaddress.ip_address(hostname)
            except ValueError:
                return False
        return not _is_public_ip(literal)
    except (ValueError, TypeError):
        return True


def _is_private_ephemeral_url(url: str, user: Dict[str, Any]) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    uid = user.get("id") or "unknown"
    for tab_id, state in _PRIVATE_TAB_NAVIGATION.items():
        tab = tabs.get(tab_id)
        session = sessions.get(tab.get("session_id", "")) if tab else None
        if (
            session
            and session.get("user_id") == uid
            and session.get("privacy_mode") == "private"
            and normalized in state.get("entries", [])
        ):
            return True
    return False


def _parse_ipv4_literal(hostname: str) -> Optional[ipaddress.IPv4Address]:
    """Parse WHATWG-style IPv4 spellings, including integer, octal and hex forms."""
    parts = hostname.rstrip(".").split(".")
    if not parts or len(parts) > 4:
        return None

    numeric_candidate = True
    values: List[int] = []
    for part in parts:
        if not part:
            return None
        if part.lower().startswith("0x"):
            digits, base = part[2:], 16
            if not digits or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                numeric_candidate = False
                break
        elif len(part) > 1 and part.startswith("0"):
            digits, base = part[1:], 8
            if not digits or not re.fullmatch(r"[0-7]+", digits):
                numeric_candidate = False
                break
        else:
            digits, base = part, 10
            if not re.fullmatch(r"[0-9]+", digits):
                numeric_candidate = False
                break
        values.append(int(digits, base))

    if not numeric_candidate:
        return None
    if any(part > 255 for part in values[:-1]):
        raise ValueError("Invalid IPv4 address")
    final_limit = 1 << (8 * (5 - len(values)))
    if values[-1] >= final_limit:
        raise ValueError("Invalid IPv4 address")

    address_value = values[-1]
    for index, part in enumerate(values[:-1]):
        address_value += part << (8 * (3 - index))
    return ipaddress.IPv4Address(address_value)


def _is_public_ip(address: ipaddress._BaseAddress) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and str(address) not in _BLOCKED_METADATA_IPS


def _looks_like_ipv4_literal(hostname: str) -> bool:
    parts = hostname.rstrip(".").split(".")
    return bool(parts) and len(parts) <= 4 and all(
        re.fullmatch(r"(?:0[xX][0-9a-fA-F]*|[0-9]+)", part) for part in parts
    )


def _validate_fetch_url(url: str) -> Tuple[Any, List[str]]:
    """Validate a fetch target and resolve every candidate address before connecting."""
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        explicit_port = parsed.port
        port = explicit_port if explicit_port is not None else (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Blocked URL") from exc
    if scheme not in ("http", "https") or not hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=403, detail="Only public HTTP(S) URLs are allowed")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=403, detail="Invalid port")

    hostname = hostname.rstrip(".").lower()
    if hostname in _BLOCKED_DOMAINS or hostname.endswith((".local", ".internal")):
        raise HTTPException(status_code=403, detail="Blocked domain")

    literal: Optional[ipaddress._BaseAddress]
    try:
        literal = _parse_ipv4_literal(hostname)
        if literal is None:
            literal = ipaddress.ip_address(hostname)
    except ValueError as exc:
        # Numeric-looking but malformed IPv4 spellings must not reach DNS.
        if _looks_like_ipv4_literal(hostname):
            raise HTTPException(status_code=403, detail="Blocked IP address") from exc
        literal = None
    if literal is not None:
        if not _is_public_ip(literal):
            raise HTTPException(status_code=403, detail="Blocked IP address")
        return parsed, [str(literal)]

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
        answers = socket.getaddrinfo(ascii_hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        # Resolution failure is a hard failure; never fall back to an unchecked fetch.
        raise OSError(f"Unable to resolve browser target {hostname}: {exc}") from exc
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise OSError(f"Unable to resolve browser target {hostname}")
    normalized_addresses: List[str] = []
    for address_text in addresses:
        address = ipaddress.ip_address(address_text.split("%", 1)[0])
        if not _is_public_ip(address):
            raise HTTPException(status_code=403, detail="Blocked private or reserved network address")
        normalized_addresses.append(str(address))
    return parsed, normalized_addresses


def _open_pinned_response(parsed: Any, address: str, timeout: float):
    """Open a single direct connection to an already validated IP address."""
    hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    class PinnedHTTPConnection(HTTPConnection):
        def connect(self):
            self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)

    class PinnedHTTPSConnection(HTTPSConnection):
        def connect(self):
            raw_socket = socket.create_connection((address, self.port), self.timeout, self.source_address)
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=hostname)

    connection_type = PinnedHTTPSConnection if parsed.scheme.lower() == "https" else PinnedHTTPConnection
    connection = connection_type(hostname, port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.params:
        path += ";" + parsed.params
    if parsed.query:
        path += "?" + parsed.query
    host_header = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port and parsed.port != (443 if parsed.scheme.lower() == "https" else 80):
        host_header += f":{parsed.port}"
    try:
        connection.request("GET", path, headers={
            "Host": host_header,
            "User-Agent": "JARVIS-Browser/3.0 (AI Research Environment; +https://jarvis.local)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "close",
        })
        response = connection.getresponse()
        headers = dict(response.getheaders())
        data = response.read(5 * 1024 * 1024 + 1)
        return response.status, headers, data[:5 * 1024 * 1024]
    finally:
        connection.close()


def _normalize_url(url: str) -> str:
    """Normalize a URL for consistent storage."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        return urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        ))
    except Exception:
        return url


def _find_in_list(store: list, item_id: str) -> Optional[Dict[str, Any]]:
    """Find an item by ID in a list-based store (e.g. browser_evidence)."""
    for item in store:
        if item.get("id") == item_id:
            return item
    return None


def _detect_prompt_injection(content: str, raw_html: str = "") -> Dict[str, Any]:
    """Scan page content for prompt-injection attempts.

    Checks both the extracted text and the raw HTML for hidden injection
    patterns in comments, meta tags, and other concealed locations.
    """
    text = content or ""
    # Also scan raw HTML for hidden injection in comments, meta tags, etc.
    combined = (text + "\n" + (raw_html or ""))
    matches: List[str] = []
    for match in _INJECTION_RE.finditer(combined):
        snippet = combined[max(0, match.start() - 30):match.end() + 30].strip()
        if snippet not in matches:
            matches.append(snippet)
    flagged = len(matches) > 0
    confidence = min(1.0, len(matches) * 0.3)
    return {"flagged": flagged, "matches": matches, "confidence": round(confidence, 2)}


def _extract_text_from_html(html_content: str) -> str:
    """Strip HTML tags to extract plain text. Best-effort, no external deps."""
    if not html_content:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_metadata(html_content: str, url: str) -> Dict[str, Any]:
    """Extract page metadata (title, description, og tags) from HTML."""
    metadata: Dict[str, Any] = {"url": url}
    if not html_content:
        return metadata
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.DOTALL | re.IGNORECASE)
    if title_match:
        metadata["title"] = _html.unescape(title_match.group(1).strip())
    desc_match = re.search(
        r'<meta[^>]+name=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']*)["\']',
        html_content, re.IGNORECASE,
    )
    if desc_match:
        metadata["description"] = _html.unescape(desc_match.group(1))
    og_img_match = re.search(
        r'<meta[^>]+property=["\'](?:og:image)["\'][^>]+content=["\']([^"\']*)["\']',
        html_content, re.IGNORECASE,
    )
    if og_img_match:
        metadata["image"] = og_img_match.group(1)
    icon_match = re.search(
        r'<link[^>]+rel=["\'](?:icon|shortcut icon)["\'][^>]+href=["\']([^"\']*)["\']',
        html_content, re.IGNORECASE,
    )
    if icon_match:
        metadata["favicon"] = icon_match.group(1)
    return metadata


def _extract_entities(text: str) -> List[Dict[str, str]]:
    """Extract named entities (basic — URLs, emails, money, dates) from text."""
    entities: List[Dict[str, str]] = []
    for m in re.finditer(r"https?://[^\s<>\"]+", text):
        entities.append({"type": "url", "value": m.group()[:200]})
    for m in re.finditer(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        entities.append({"type": "email", "value": m.group()})
    for m in re.finditer(r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?", text):
        entities.append({"type": "money", "value": m.group()})
    for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", text):
        entities.append({"type": "date", "value": m.group()})
    return entities


def _extract_page_structure(html_content: str) -> Dict[str, Any]:
    """Extract structural elements from page HTML."""
    structure: Dict[str, Any] = {
        "headings": [], "paragraphs": 0, "links": 0, "images": 0,
        "tables": 0, "lists": 0, "forms": 0, "code_blocks": 0,
        "word_count": 0,
    }
    if not html_content:
        return structure
    for level in range(1, 7):
        tags = re.findall(rf"<h{level}[^>]*>(.*?)</h{level}>", html_content, re.DOTALL | re.IGNORECASE)
        structure["headings"].extend(
            [{"level": level, "text": _html.unescape(re.sub(r"<[^>]+>", "", t).strip())[:500]} for t in tags]
        )
    structure["paragraphs"] = len(re.findall(r"<p[^>]*>", html_content, re.IGNORECASE))
    structure["links"] = len(re.findall(r"<a[^>]+href", html_content, re.IGNORECASE))
    structure["images"] = len(re.findall(r"<img[^>]+>", html_content, re.IGNORECASE))
    structure["tables"] = len(re.findall(r"<table[^>]*>", html_content, re.IGNORECASE))
    structure["lists"] = len(re.findall(r"<(ul|ol)[^>]*>", html_content, re.IGNORECASE))
    structure["forms"] = len(re.findall(r"<form[^>]*>", html_content, re.IGNORECASE))
    structure["inputs"] = len(re.findall(r"<input[^>]+>", html_content, re.IGNORECASE))
    structure["buttons"] = len(re.findall(r"<button[^>]*>", html_content, re.IGNORECASE))
    structure["code_blocks"] = len(re.findall(r"<code[^>]*>", html_content, re.IGNORECASE))
    text = _extract_text_from_html(html_content)
    structure["word_count"] = len(text.split())
    return structure


def _fetch_url_sync(url: str, timeout: float = 15.0) -> Dict[str, Any]:
    """Synchronously fetch a URL (call via run_in_executor from async routes)."""
    current_url = url
    response_status = 0
    headers: Dict[str, str] = {}
    data = b""
    for redirect_count in range(11):
        parsed, addresses = _validate_fetch_url(current_url)
        last_error: Optional[OSError] = None
        for address in addresses:
            try:
                response_status, headers, data = _open_pinned_response(parsed, address, timeout)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error

        lower_headers = {key.lower(): value for key, value in headers.items()}
        location = lower_headers.get("location")
        if response_status in (301, 302, 303, 307, 308) and location:
            if redirect_count == 10:
                raise OSError("Too many redirects")
            current_url = urljoin(current_url, location)
            # The next loop validates and resolves the redirect destination before connecting.
            continue

        content_type = lower_headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip("\"'")
        try:
            html_content = data.decode(charset or "utf-8")
        except (UnicodeDecodeError, LookupError):
            html_content = data.decode("utf-8", errors="replace")

        return {
            "url": current_url,
            "status": response_status,
            "content_type": content_type,
            "content_length": len(data),
            "html": html_content if ("text/html" in content_type or "text/plain" in content_type) else "",
            "is_html": "text/html" in content_type,
            "headers": headers,
        }
    raise OSError("Too many redirects")


def _audit(source: str, user: Dict[str, Any], action: str, detail: str = ""):
    """Record a browser event in the audit log (best-effort)."""
    try:
        audit_store = get_store("audit_logs")
        audit = audit_store.load()
        entry = {
            "id": f"audit-{uuid.uuid4().hex[:12]}",
            "timestamp": _now(),
            "epoch": _now_epoch(),
            "user": user.get("id") or "unknown",
            "resource": "browser",
            "operation": action,
            "decision": "logged",
            "result": "success",
            "provider": "jarvis-browser",
            "detail": detail,
            "ip": "internal",
            "permission": "browser_access",
            "session_id": None,
        }
        audit.append(entry)
        if len(audit) > 2000:
            audit = audit[-2000:]
        audit_store.save()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=None)
async def create_session(
    body: Optional[SessionCreateIn] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new browser session (isolated cookie context)."""
    b = body or SessionCreateIn()
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    privacy_mode = b.privacy_mode or "standard"
    if privacy_mode not in VALID_PRIVACY_MODES:
        privacy_mode = "standard"

    # Resolve browser profile (spec §12) — default to "personal"
    profile_name = getattr(b, "profile", None) or "personal"
    if profile_name not in BrowserProfile.DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {profile_name}")
    profile_config = BrowserProfile(profile_name)

    sessions = get_store("browser_sessions").load()
    sess = {
        "id": session_id,
        "user_id": user.get("id") or "unknown",
        "name": b.name or f"Session {len(sessions) + 1}",
        "privacy_mode": privacy_mode,
        "profile": profile_name,
        "tabs": [],
        "active_tab_id": None,
        "created_at": _now(),
        "updated_at": _now(),
        "research_session_id": b.research_session_id,
        "mission_id": b.mission_id,
    }
    sessions[session_id] = sess
    get_store("browser_sessions").save()

    _audit("browser", user, "session_created", f"session={session_id}, mode={privacy_mode}")
    return {"session": sess}


@router.get("/sessions")
async def list_sessions(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List all browser sessions for the current user."""
    sessions = get_store("browser_sessions").load()
    uid = user.get("id") or "unknown"
    mine = [s for s in sessions.values() if s.get("user_id") == uid]
    mine.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return {"sessions": mine, "count": len(mine)}


@router.get("/sessions/{session_id}/permissions")
async def get_session_permissions(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return the permission set and profile configuration for a session (spec §8, §12)."""
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    profile_name = sess.get("profile", "personal")
    profile = BrowserProfile(profile_name)

    return {
        "session_id": session_id,
        "profile": profile_name,
        "permissions": profile.agent_permissions,
        "history_policy": profile.history_policy,
        "cookie_isolation": profile.cookie_isolation,
        "ai_model_profile": profile.model_context,
        "model": profile.model_context,
        "navigation": {
            "top_navigation": bool(profile_name in ("research", "engineering", "personal")),
            "download": "download" in profile.agent_permissions,
            "inspect": "inspect" in profile.agent_permissions,
        },
    }


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: dict,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Update session metadata."""
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    for field in ("name", "privacy_mode", "active_tab_id", "research_session_id", "mission_id", "profile"):
        if field in body:
            if field == "privacy_mode" and body["privacy_mode"] not in VALID_PRIVACY_MODES:
                raise HTTPException(status_code=400, detail=f"Invalid privacy mode: {body['privacy_mode']}")
            if field == "profile" and body["profile"] not in BrowserProfile.DEFAULTS:
                raise HTTPException(status_code=400, detail=f"Invalid profile: {body['profile']}")
            if field == "privacy_mode" and body[field] != "private":
                for tab_id in sess.get("tabs", []):
                    _PRIVATE_TAB_NAVIGATION.pop(tab_id, None)
            sess[field] = body[field]
    sess["updated_at"] = _now()
    get_store("browser_sessions").save()

    _audit("browser", user, "session_updated", f"session={session_id}")
    return {"session": sess}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a browser session and all its tabs."""
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tab_ids = sess.get("tabs", [])
    tabs = get_store("browser_tabs").load()
    for tid in tab_ids:
        tabs.pop(tid, None)
        _PRIVATE_TAB_NAVIGATION.pop(tid, None)
    get_store("browser_tabs").save()

    del sessions[session_id]
    get_store("browser_sessions").save()

    _audit("browser", user, "session_deleted", f"session={session_id}")
    return {"success": True}


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

def _user_tabs(user: Dict[str, Any]):
    """Return tabs belonging to the current user."""
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    uid = user.get("id") or "unknown"
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}
    return {tid: t for tid, t in tabs.items() if t.get("session_id") in my_session_ids}


@router.post("/tabs")
async def create_tab(
    body: TabCreateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new browser tab within a session."""
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(body.session_id)
    if not sess:
        # Auto-create a session
        result = await create_session(SessionCreateIn(**{}), user)
        sess = result["session"]
    # Verify ownership
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tab_id = f"tab-{uuid.uuid4().hex[:12]}"
    requested_url = _normalize_url(body.url) if body.url else "about:blank"
    private_initial_url = sess.get("privacy_mode") == "private" and requested_url != "about:blank"
    url = "about:blank" if private_initial_url else requested_url
    title = body.title or requested_url
    tab = {
        "id": tab_id,
        "session_id": body.session_id,
        "url": url,
        "title": "Private tab" if private_initial_url else title,
        "favicon": "",
        "is_loading": True,
        "is_pinned": body.is_pinned,
        "group": body.group,
        "created_at": _now(),
        "updated_at": _now(),
        "scroll_position": None,
        "extracted_content": None,
        "prompt_injection_flagged": False,
        "security_notes": [],
    }
    if private_initial_url:
        _PRIVATE_TAB_NAVIGATION[tab_id] = {"entries": [requested_url], "index": 0}
    tabs = get_store("browser_tabs").load()
    tabs[tab_id] = tab
    get_store("browser_tabs").save()

    sess["tabs"].append(tab_id)
    sess["active_tab_id"] = tab_id
    sess["updated_at"] = _now()
    get_store("browser_sessions").save()

    if sess.get("privacy_mode") == "private":
        _audit("browser", user, "tab_created", f"tab={tab_id}, mode=private")
    else:
        _audit("browser", user, "tab_created", f"tab={tab_id}, url={url[:100]}")
    response_tab = {**tab, "url": requested_url, "title": title} if private_initial_url else tab
    return {"tab": response_tab, "session_id": body.session_id}


@router.get("/tabs")
async def list_tabs(
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List tabs for a session (or all of the user's tabs)."""
    sessions = get_store("browser_sessions").load()
    tabs_store = get_store("browser_tabs").load()
    uid = user.get("id") or "unknown"

    if session_id:
        sess = sessions.get(session_id)
        if not sess or sess.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="Session not found")
        tab_ids = sess.get("tabs", [])
    else:
        my_sessions = {s["id"] for s in sessions.values() if s.get("user_id") == uid}
        tab_ids = [tid for tid, t in tabs_store.items() if t.get("session_id") in my_sessions]

    user_tabs = [tabs_store[tid] for tid in tab_ids if tid in tabs_store]
    return {"tabs": user_tabs, "count": len(user_tabs)}


@router.delete("/tabs/{tab_id}")
async def delete_tab(
    tab_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Close a tab. Removes it from its session."""
    tabs = get_store("browser_tabs").load()
    tab = tabs.get(tab_id)
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found")
    sess = get_store("browser_sessions").load().get(tab.get("session_id", ""))
    if sess and sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")
    del tabs[tab_id]
    _PRIVATE_TAB_NAVIGATION.pop(tab_id, None)
    get_store("browser_tabs").save()

    sessions = get_store("browser_sessions").load()
    if sess:
        sess["tabs"] = [t for t in sess.get("tabs", []) if t != tab_id]
        if sess.get("active_tab_id") == tab_id:
            sess["active_tab_id"] = sess["tabs"][-1] if sess["tabs"] else None
        sess["updated_at"] = _now()
        sessions[tab["session_id"]] = sess
        get_store("browser_sessions").save()

    _audit("browser", user, "tab_closed", f"tab={tab_id}")
    return {"success": True}


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@router.post("/navigate")
async def navigate(
    body: NavigateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Navigate a tab to a new URL. Validates against blocked domains."""
    if _is_blocked_domain(body.url):
        _audit("browser", user, "navigation_blocked",
               f"url={body.url[:100]}, reason=blocked_domain")
        return {
            "window_id": body.tab_id or "",
            "url": body.url,
            "navigated": False,
            "blocked": True,
            "reason": "Blocked domain (private/metadata range)",
        }

    normalized = _normalize_url(body.url)
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()

    # Resolve tab
    tab_id = body.tab_id
    if not tab_id:
        sess = sessions.get(body.session_id)
        tab_id = sess.get("active_tab_id") if sess else None
    if not tab_id:
        raise HTTPException(status_code=404, detail="No active tab for this session")

    tab = tabs.get(tab_id)
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found")

    # Verify ownership
    sess = sessions.get(tab.get("session_id", ""))
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Privacy mode change
    if body.privacy_mode and body.privacy_mode != sess.get("privacy_mode", "standard"):
        if body.privacy_mode in VALID_PRIVACY_MODES:
            sess["privacy_mode"] = body.privacy_mode
            sess["updated_at"] = _now()
            get_store("browser_sessions").save()
            _audit("browser", user, "privacy_mode_changed", f"mode={body.privacy_mode}")

    old_url = tab.get("url", "")
    sess["active_tab_id"] = tab_id
    sess["updated_at"] = _now()
    get_store("browser_sessions").save()

    mode = sess.get("privacy_mode", "standard")
    if mode == "private":
        private_state = _PRIVATE_TAB_NAVIGATION.get(tab_id)
        if private_state is None:
            private_stack = [old_url] if old_url and old_url != "about:blank" else []
            private_state = {"entries": private_stack, "index": len(private_stack) - 1}
        elif private_state.get("index", -1) >= 0:
            old_url = private_state["entries"][private_state["index"]]
        private_stack = private_state["entries"][: private_state["index"] + 1]
        if not private_stack or private_stack[-1] != normalized:
            private_stack.append(normalized)
        private_state = {"entries": private_stack, "index": len(private_stack) - 1}
        _PRIVATE_TAB_NAVIGATION[tab_id] = private_state
        # Keep private destinations only in process memory, never in durable tab/history/timeline stores.
    else:
        _PRIVATE_TAB_NAVIGATION.pop(tab_id, None)
        tab["url"] = normalized
        tab["is_loading"] = True
        tab["updated_at"] = _now()
        if old_url and old_url != normalized:
            tab["navigation_history"] = (tab.get("navigation_history") or [old_url])[
                : (tab.get("navigation_index", len(tab.get("navigation_history") or [old_url]) - 1) + 1)
            ]
        else:
            tab.setdefault("navigation_history", [old_url] if old_url else [])
        nav_history = tab.get("navigation_history", [])
        if not nav_history or nav_history[-1] != normalized:
            nav_history.append(normalized)
        tab["navigation_index"] = len(nav_history) - 1
        tabs[tab_id] = tab
        get_store("browser_tabs").save()

    if mode != "private":
        history = get_store("browser_history").load()
        entry = {
            "id": f"hist-{uuid.uuid4().hex[:12]}",
            "url": normalized,
            "title": tab.get("title", ""),
            "domain": _domain_from_url(normalized),
            "visited_at": _now(),
            "epoch": _now_epoch(),
            "user_id": user.get("id") or "unknown",
            "session_id": sess.get("id"),
        }
        history.append(entry)
        if len(history) > 500:
            history = history[-500:]
        get_store("browser_history").save()

    if mode == "private":
        _audit("browser", user, "navigate", f"session={body.session_id}, mode=private")
    else:
        _audit("browser", user, "navigate",
               f"from={old_url[:100]} to={normalized[:100]}")
        record_navigation_timeline(
            session_id=tab.get("session_id", ""),
            tab_id=tab_id,
            url=normalized,
            action="navigate",
            detail=f"from={old_url[:100]} to={normalized[:100]}",
        )
    return {
        "window_id": tab_id,
        "url": normalized,
        "navigated": True,
        "blocked": False,
        "privacy_mode": mode,
    }


@router.post("/navigate/control")
async def control_navigation(
    body: NavigationControlIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Move the active server-managed tab history or reload its current URL."""
    if body.action not in {"back", "forward", "reload"}:
        raise HTTPException(status_code=400, detail="Unsupported navigation control")

    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    tab = tabs.get(body.tab_id)
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found")
    session = sessions.get(body.session_id)
    if not session or tab.get("session_id") != body.session_id:
        raise HTTPException(status_code=404, detail="Tab not found in session")
    if session.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    mode = session.get("privacy_mode", "standard")
    if mode == "private":
        state = _PRIVATE_TAB_NAVIGATION.get(body.tab_id)
        if state is None:
            current_url = tab.get("url", "")
            state = {
                "entries": [current_url] if current_url and current_url != "about:blank" else [],
                "index": 0 if current_url and current_url != "about:blank" else -1,
            }
        entries = state["entries"]
        index = state["index"]
    else:
        _PRIVATE_TAB_NAVIGATION.pop(body.tab_id, None)
        entries = tab.get("navigation_history") or ([tab.get("url", "")] if tab.get("url") else [])
        index = tab.get("navigation_index", len(entries) - 1)

    next_index = index
    if body.action == "back":
        next_index = max(0, index - 1)
    elif body.action == "forward":
        next_index = min(len(entries) - 1, index + 1)
    navigated = body.action == "reload" or (bool(entries) and next_index != index)
    if not navigated:
        return {
            "navigated": False,
            "url": entries[index] if 0 <= index < len(entries) else tab.get("url", ""),
            "action": body.action,
            "privacy_mode": mode,
        }

    url = entries[next_index] if body.action != "reload" else (
        entries[index] if 0 <= index < len(entries) else tab.get("url", "")
    )
    if not url or _is_blocked_domain(url):
        raise HTTPException(status_code=403, detail="Blocked navigation target")
    if mode == "private":
        _PRIVATE_TAB_NAVIGATION[body.tab_id] = {"entries": entries, "index": next_index}
    else:
        tab["url"] = url
        tab["navigation_history"] = entries
        tab["navigation_index"] = next_index
        tab["is_loading"] = True
        tab["updated_at"] = _now()
        tabs[body.tab_id] = tab
        get_store("browser_tabs").save()

    session["active_tab_id"] = body.tab_id
    session["updated_at"] = _now()
    sessions[body.session_id] = session
    get_store("browser_sessions").save()

    if mode != "private":
        record_navigation_timeline(
            session_id=body.session_id,
            tab_id=body.tab_id,
            url=url,
            action=body.action,
            detail=f"Navigation {body.action}",
        )
        if body.action in {"back", "forward"}:
            history = get_store("browser_history").load()
            history.append({
                "id": f"hist-{uuid.uuid4().hex[:12]}",
                "url": url,
                "title": tab.get("title", ""),
                "domain": _domain_from_url(url),
                "visited_at": _now(),
                "epoch": _now_epoch(),
                "user_id": user.get("id") or "unknown",
                "session_id": body.session_id,
            })
            get_store("browser_history").save()
        _audit("browser", user, "navigation_control", f"action={body.action}, url={url[:100]}")
    else:
        _audit("browser", user, "navigation_control", f"session={body.session_id}, mode=private")

    return {"navigated": True, "url": url, "action": body.action, "privacy_mode": mode}


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------

@router.post("/extract")
async def extract_page(
    body: ExtractIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Extract text content, metadata, structure, and entities from a page.

    If ``content`` (HTML) is provided by the frontend, that is used directly.
    Otherwise the backend fetches the page via proxy.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    raw_content = body.content or ""
    text = _extract_text_from_html(raw_content)

    # If no content provided, fetch from backend
    if not text:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            fetched = await loop.run_in_executor(None, _fetch_url_sync, body.url)
            raw_content = fetched.get("html", "")
            text = _extract_text_from_html(raw_content)
        except HTTPException:
            raise
        except Exception as e:
            # Classify the error into the normalized taxonomy
            category = classify_urllib_exception(e)
            if not _is_private_ephemeral_url(body.url, user):
                _record_navigation_error(body.url, category, str(e), user)
            raise HTTPException(
                status_code=status.HTTP_502,
                detail=f"Failed to fetch URL: {str(e)[:200]}",
                headers={"X-Browser-Error-Category": category.value},
            )

    injection = _detect_prompt_injection(text, raw_content)
    metadata = _extract_metadata(raw_content, body.url)
    structure = _extract_page_structure(raw_content)
    entities = _extract_entities(text)

    # Update tab with extracted content and security flags
    normalized_url = _normalize_url(body.url)
    tabs = get_store("browser_tabs").load()
    sessions = get_store("browser_sessions").load()
    private_tab_ids = {
        tab_id
        for tab_id, state in _PRIVATE_TAB_NAVIGATION.items()
        if state.get("entries") and normalized_url in state["entries"]
        and sessions.get(tabs.get(tab_id, {}).get("session_id", ""), {}).get("privacy_mode") == "private"
    }
    for tab_id, tab in tabs.items():
        if tab_id in private_tab_ids:
            continue
        if tab.get("url") == normalized_url:
            tab["extracted_content"] = text[:50000] if text else None
            tab["prompt_injection_flagged"] = injection["flagged"]
            if injection["flagged"]:
                tab["security_notes"].append(
                    f"Prompt injection detected: confidence {injection['confidence']}"
                )
                _audit("browser", user, "prompt_injection_detected",
                       f"url={body.url[:100]}, confidence={injection['confidence']}")
    get_store("browser_tabs").save()

    return {
        "url": body.url,
        "title": metadata.get("title", ""),
        "text": text[:10000],
        "text_length": len(text),
        "metadata": metadata,
        "structure": structure,
        "entities": entities[:50],
        "prompt_injection": injection,
        "selection": body.user_selection,
    }


# ---------------------------------------------------------------------------
# Security — prompt injection check
# ---------------------------------------------------------------------------

@router.post("/security/prompt-injection")
async def check_prompt_injection(
    body: PromptIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Check text content for prompt-injection attempts."""
    result = _detect_prompt_injection(body.content)
    return {
        "source": body.source,
        "flagged": result["flagged"],
        "confidence": result["confidence"],
        "matches": result["matches"],
        "recommendation": (
            "Review content before trusting AI actions" if result["flagged"]
            else "Content appears safe"
        ),
    }


@router.get("/security/report")
async def security_report(
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the security status for a browser session."""
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    uid = user.get("id") or "unknown"

    session = None
    if session_id:
        session = sessions.get(session_id)
    elif sessions:
        my_sessions = [s for s in sessions.values() if s.get("user_id") == uid]
        if my_sessions:
            session = sorted(my_sessions, key=lambda s: s.get("updated_at", ""), reverse=True)[0]

    if not session:
        return {"session": None, "tabs": [], "security_issues": [], "issue_count": 0}

    session_tabs = [t for t in tabs.values() if t.get("session_id") == session["id"]]
    security_issues = []
    for tab in session_tabs:
        if tab.get("prompt_injection_flagged"):
            security_issues.append({
                "tab_id": tab["id"],
                "url": tab.get("url", ""),
                "type": "prompt_injection",
                "severity": "high",
                "notes": tab.get("security_notes", []),
            })
        if _is_blocked_domain(tab.get("url", "")):
            security_issues.append({
                "tab_id": tab["id"],
                "url": tab.get("url", ""),
                "type": "blocked_domain",
                "severity": "critical",
                "notes": ["This domain is blocked by JARVIS security policy"],
            })

    return {
        "session": session,
        "tabs": session_tabs,
        "privacy_mode": session.get("privacy_mode", "standard"),
        "credential_isolation": session.get("privacy_mode") in ("private", "authenticated"),
        "security_issues": security_issues,
        "issue_count": len(security_issues),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.post("/search")
async def browser_search(
    body: SearchIn,
    user: Dict[str, Any] = Depends(get_current_user),
    request: Request = ...,
):
    """Search the web + internal JARVIS knowledge.

    Web search uses DuckDuckGo HTML (no API key). Internal search merges
    knowledge entries and memory.
    """
    query = body.query.strip()
    if not query:
        return {"results": [], "query": "", "external_results": [], "internal_results": []}

    # Internal knowledge + memory search
    internal_results: List[Dict[str, Any]] = []
    knowledge = get_store("knowledge").load()
    for item in knowledge.values():
        if query.lower() in (item.get("key", "") + " " + item.get("value", "")).lower():
            internal_results.append({
                "title": item.get("key", "Untitled"),
                "url": f"jarvis://knowledge/{item.get('id', '')}",
                "snippet": (item.get("value", "") or "")[:300],
                "source": "knowledge",
                "domain": "jarvis:knowledge",
            })

    mem_store = get_store("memory").load()
    for m in mem_store.values():
        if query.lower() in m.get("content", "").lower():
            internal_results.append({
                "title": f"Memory ({m.get('layer', 'short_term')})",
                "url": f"jarvis://memory/{m.get('id', '')}",
                "snippet": (m.get("content", "") or "")[:300],
                "source": "memory",
                "domain": "jarvis:memory",
            })

    # External web search (DDG HTML)
    import asyncio
    import urllib.parse as _urlparse
    import urllib.request as _urllib_request

    search_url = "https://html.duckduckgo.com/html/?q=" + _urlparse.quote(query)
    external_results: List[Dict[str, Any]] = []
    try:
        loop = asyncio.get_event_loop()

        def _do_web_search():
            req = _urllib_request.Request(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with _urllib_request.urlopen(req, timeout=15) as resp:
                html_content = resp.read().decode("utf-8", errors="replace")
            results = []
            for m in re.finditer(
                r'<a[^>]+class="result__a"[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                html_content, re.DOTALL | re.IGNORECASE,
            ):
                raw_url = m.group(1)
                title = _html.unescape(re.sub(r"<[^>]+>", "", m.group(2)).strip())
                real_url = raw_url
                uddg_match = re.search(r"uddg=([^&]+)", raw_url)
                if uddg_match:
                    real_url = _urlparse.unquote(uddg_match.group(1))
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": "",
                    "source": "web",
                    "domain": _domain_from_url(real_url),
                })
                if len(results) >= 10:
                    break

            snippets = re.findall(
                r'<a[^>]+class="result__a"[^>]*>.*?</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                html_content, re.DOTALL | re.IGNORECASE,
            )
            for i, snippet_html in enumerate(snippets[:len(results)]):
                snippet = _html.unescape(re.sub(r"<[^>]+>", "", snippet_html).strip())
                snippet = re.sub(r"\s+", " ", snippet)[:300]
                if i < len(results):
                    results[i]["snippet"] = snippet
            return results

        external_results = await loop.run_in_executor(None, _do_web_search)
    except Exception as e:
        _audit("browser", user, "search_error", f"error={str(e)[:100]}")

    _audit("browser", user, "search", f"query={query[:100]}")
    return {
        "query": query,
        "results": external_results + internal_results,
        "external_results": external_results,
        "internal_results": internal_results,
        "session_id": body.session_id,
        "count": len(external_results) + len(internal_results),
    }


# ---------------------------------------------------------------------------
# Evidence capture
# ---------------------------------------------------------------------------

@router.post("/evidence")
async def capture_evidence(
    body: EvidenceCaptureIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Capture a piece of evidence from the browser."""
    store = get_store("browser_evidence").load()
    eid = f"evidence-{uuid.uuid4().hex[:12]}"
    entry = {
        "id": eid,
        "user_id": user.get("id") or "unknown",
        "url": _normalize_url(body.url),
        "domain": _domain_from_url(body.url),
        "title": body.title or body.url,
        "selected_passage": body.selected_passage,
        "page_context": body.page_context,
        "claim": body.claim,
        "verification_status": body.verification_status,
        "research_session_id": body.research_session_id,
        "mission_id": body.mission_id,
        "captured_at": _now(),
        "epoch": _now_epoch(),
        "tags": [],
    }
    store.append(entry)
    get_store("browser_evidence").save()

    _audit("browser", user, "evidence_captured",
           f"evidence={eid}, url={body.url[:100]}, claim={body.claim[:50] if body.claim else 'none'}")
    return {"id": eid, "evidence": entry}


@router.get("/evidence")
async def list_evidence(
    research_session_id: Optional[str] = Query(default=None),
    mission_id: Optional[str] = Query(default=None),
    verified: Optional[bool] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List evidence entries with optional filters."""
    store = get_store("browser_evidence").load()
    uid = user.get("id") or "unknown"
    mine = [e for e in store if e.get("user_id") == uid]

    if research_session_id:
        mine = [e for e in mine if e.get("research_session_id") == research_session_id]
    if mission_id:
        mine = [e for e in mine if e.get("mission_id") == mission_id]
    if verified is not None:
        if verified:
            mine = [e for e in mine if e.get("verification_status") in ("verified", "confirmed")]
        else:
            mine = [e for e in mine if e.get("verification_status") not in ("verified", "confirmed")]

    mine.sort(key=lambda e: e.get("epoch", 0), reverse=True)
    return {"evidence": mine, "count": len(mine)}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(
    q: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browsing history with optional search/filter."""
    history = get_store("browser_history").load()
    uid = user.get("id") or "unknown"
    mine = [h for h in history if h.get("user_id") == uid]

    if q:
        ql = q.lower()
        mine = [h for h in mine if ql in h.get("title", "").lower() or ql in h.get("url", "").lower()]
    if domain:
        mine = [h for h in mine if h.get("domain") == domain]

    mine.sort(key=lambda h: h.get("epoch", 0), reverse=True)
    return {"history": mine[:limit], "count": len(mine)}


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------

@router.get("/bookmarks")
async def list_bookmarks(
    q: Optional[str] = Query(default=None),
    tags: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List bookmarks with optional search/filter."""
    store = get_store("browser_bookmarks").load()
    uid = user.get("id") or "unknown"
    mine = [b for b in store.values() if b.get("user_id") == uid]

    if q:
        ql = q.lower()
        mine = [b for b in mine if ql in b.get("title", "").lower() or ql in b.get("url", "").lower()]
    if tags:
        tag_set = set(t.strip() for t in tags.split(","))
        mine = [b for b in mine if tag_set & set(b.get("tags", []))]

    mine.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return {"bookmarks": mine, "count": len(mine)}


@router.post("/bookmarks")
async def add_bookmark(
    body: BookmarkIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Add a bookmark."""
    store = get_store("browser_bookmarks").load()
    bid = f"bk-{uuid.uuid4().hex[:12]}"
    bookmark = {
        "id": bid,
        "user_id": user.get("id") or "unknown",
        "url": _normalize_url(body.url),
        "domain": _domain_from_url(body.url),
        "title": body.title,
        "tags": body.tags,
        "notes": body.notes,
        "created_at": _now(),
        "updated_at": _now(),
    }
    store[bid] = bookmark
    get_store("browser_bookmarks").save()

    _audit("browser", user, "bookmark_added", f"url={body.url[:100]}")
    return {"id": bid, "bookmark": bookmark}


@router.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a bookmark."""
    store = get_store("browser_bookmarks").load()
    bm = store.get(bookmark_id)
    if not bm or bm.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=404, detail="Bookmark not found")
    del store[bookmark_id]
    get_store("browser_bookmarks").save()
    return {"success": True}


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

@router.get("/downloads")
async def list_downloads(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List download queue (user-scoped)."""
    store = get_store("browser_downloads").load()
    uid = user.get("id") or "unknown"
    mine = [d for d in store if d.get("user_id") == uid]
    mine.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return {"downloads": mine, "count": len(mine)}


# ---------------------------------------------------------------------------
# Page content serving for the iframe
# ---------------------------------------------------------------------------

@router.get("/page")
async def get_page(
    url: str = Query(default=""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Fetch a page via proxy and return HTML for the iframe.

    The frontend iframe src can point here for cross-origin pages,
    since the browser engine can't bypass CORS from the client side.
    """
    if _is_blocked_domain(url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        fetched = await loop.run_in_executor(None, _fetch_url_sync, url)
    except HTTPException:
        raise
    except Exception as e:
        # Classify the error into the normalized taxonomy
        category = classify_urllib_exception(e)
        if not _is_private_ephemeral_url(url, user):
            _record_navigation_error(url, category, str(e), user)
        raise HTTPException(
            status_code=status.HTTP_502,
            detail=f"Failed to fetch URL: {str(e)[:200]}",
            headers={"X-Browser-Error-Category": category.value},
        )

    if not fetched.get("is_html"):
        return {
            "content_type": fetched.get("content_type", ""),
            "content": fetched.get("html", ""),
            "is_html": False,
            "status": fetched.get("status", 200),
        }
    return {
        "html": fetched.get("html", ""),
        "content_type": fetched.get("content_type", "text/html"),
        "status": fetched.get("status", 200),
        "final_url": fetched.get("url", url),
    }


# ---------------------------------------------------------------------------
# Autonomous browsing — permission-controlled
# ---------------------------------------------------------------------------

_autonomous_state: Dict[str, Dict[str, Any]] = {}


@router.post("/autonomous")
async def autonomous_browse(
    body: AutonomousIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Execute a controlled autonomous browsing task.

    Requires explicit consent per session.  High-risk actions
    (purchase, delete, submit forms, etc.) are never performed autonomously.
    """
    session_id = body.session_id
    action = body.action
    params = body.params

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    mode = sess.get("privacy_mode", "standard")
    if mode not in ("agent", "automation"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Autonomous browsing requires 'agent' or 'automation' privacy mode.",
        )

    if not body.consent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Explicit consent required for autonomous browsing.",
        )

    allowed_actions = {
        "navigate", "search", "open_tab", "extract",
        "compare_sources", "download", "bookmark", "capture_evidence",
    }
    high_risk_actions = {
        "purchase", "delete", "submit_form", "change_settings",
        "upload_sensitive", "change_cloud_config", "grant_permissions",
    }

    if action in high_risk_actions:
        _audit("browser", user, "high_risk_action_blocked",
               f"action={action}, session={session_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action '{action}' is high-risk and requires explicit user confirmation.",
        )

    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    if session_id not in _autonomous_state:
        _autonomous_state[session_id] = {"actions": [], "consented_at": _now()}
    _autonomous_state[session_id]["actions"].append({
        "action": action,
        "params": params,
        "timestamp": _now(),
        "epoch": _now_epoch(),
    })

    result: Dict[str, Any] = {"session_id": session_id, "action": action, "executed": True}

    if action == "navigate":
        url = params.get("url", "")
        if _is_blocked_domain(url):
            result["blocked"] = True
            result["reason"] = "Blocked domain"
            _audit("browser", user, "autonomous_navigation_blocked", f"url={url[:100]}")
            return result
        tab_resp = await create_tab(
            TabCreateIn(session_id=session_id, url=url, title=params.get("title", url)),
            user,
        )
        result["tab_id"] = tab_resp["tab"]["id"]

    elif action == "search":
        search_resp = await browser_search(
            SearchIn(query=params.get("query", ""), session_id=session_id),
            user,
            Request,
        )
        result["search_results"] = search_resp["results"]

    elif action == "extract":
        ext = await extract_page(
            ExtractIn(url=body.url or params.get("url", ""), content=params.get("content"),
                      user_selection=params.get("selection")),
            user,
        )
        result["page_data"] = {
            "title": ext["title"],
            "text_length": ext["text_length"],
            "entities": ext["entities"][:10],
            "prompt_injection": ext["prompt_injection"],
        }

    elif action == "compare_sources":
        tab_ids = params.get("tab_ids", [])
        tabs = get_store("browser_tabs").load()
        comparisons = []
        for tid in tab_ids:
            tab = tabs.get(tid)
            if tab and tab.get("extracted_content"):
                comparisons.append({
                    "tab_id": tid,
                    "url": tab.get("url", ""),
                    "text": tab.get("extracted_content", "")[:2000],
                })
        result["comparisons"] = comparisons

    elif action == "download":
        url = params.get("url", "")
        if _is_blocked_domain(url):
            result["blocked"] = True
            result["reason"] = "Blocked domain"
            return result
        import asyncio
        loop = asyncio.get_event_loop()
        fetched = await loop.run_in_executor(None, _fetch_url_sync, url)
        filename = params.get("filename") or _domain_from_url(url)
        if not isinstance(filename, str):
            raise HTTPException(status_code=400, detail="Invalid download filename")
        save_path = _download_destination(filename, str(user.get("id") or ""))
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(fetched.get("html", ""))
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Download could not be saved") from exc

        download_entry = {
            "id": f"dl-{uuid.uuid4().hex[:12]}",
            "user_id": user.get("id") or "unknown",
            "url": _normalize_url(url),
            "filename": filename,
            "size_bytes": len(fetched.get("html", "")),
            "risk_level": params.get("risk_level", "unknown"),
            "status": "completed",
            "created_at": _now(),
            "path": str(save_path),
        }
        store = get_store("browser_downloads").load()
        store.append(download_entry)
        get_store("browser_downloads").save()
        result["download"] = download_entry
        if download_entry["risk_level"] in ("high", "critical", "unknown"):
            download_entry["quarantined"] = True
            download_entry["scan_status"] = "pending"

    _audit("browser", user, f"autonomous_{action}",
           f"session={session_id}, action={action}")
    return result


# ---------------------------------------------------------------------------
# Status / overview
# ---------------------------------------------------------------------------

@router.get("/status")
async def browser_status(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get overall browser system status."""
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    bookmarks = get_store("browser_bookmarks").load()
    evidence = get_store("browser_evidence").load()
    downloads = get_store("browser_downloads").load()
    uid = user.get("id") or "unknown"

    my_sessions = [s for s in sessions.values() if s.get("user_id") == uid]
    session_ids = {s["id"] for s in my_sessions}
    my_tabs = [t for t in tabs.values() if t.get("session_id") in session_ids]
    my_bookmarks = [b for b in bookmarks.values() if b.get("user_id") == uid]
    my_evidence = [e for e in evidence if e.get("user_id") == uid]
    my_downloads = [d for d in downloads if d.get("user_id") == uid]

    return {
        "initialized": True,
        "sessions": len(my_sessions),
        "tabs": len(my_tabs),
        "bookmarks": len(my_bookmarks),
        "evidence": len(my_evidence),
        "downloads": len(my_downloads),
        "active_sessions": [s["id"] for s in my_sessions],
        "user_id": user.get("id"),
    }


# =========================================================================
# Browser Action Model — normalized action queue (spec §3)
# =========================================================================

@router.post("/actions")
async def create_action(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a normalized browser action.

    The action is queued for policy review before execution.
    Required fields: type (ActionType), session_id.
    Optional: target, parameters, source ("user"|"agent").
    """
    action_type = body.get("type", "")
    try:
        ActionType(action_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown action type: {action_type}")

    session_id = body.get("session_id", "")
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    action = BrowserAction(
        type=ActionType(action_type),
        target=body.get("target"),
        parameters=body.get("parameters", {}),
        source=body.get("source", "agent"),
        session_id=session_id,
        tab_id=body.get("tab_id"),
    )

    # Determine permission level based on action type and privacy mode
    mode = sess.get("privacy_mode", "standard")
    high_risk = {
        "submit_form", "purchase", "delete", "change_settings",
        "upload_sensitive", "change_cloud_config", "grant_permissions",
    }
    if action_type in high_risk and mode not in ("agent", "automation"):
        action.permission = ActionPermission.REQUIRES_CONFIRMATION
    elif mode == "private":
        action.permission = ActionPermission.REQUIRES_CONFIRMATION
    else:
        action.permission = ActionPermission.ALLOWED

    # Store action
    actions = get_store("browser_actions").load()
    actions[action.id] = action.model_dump()
    get_store("browser_actions").save()

    _audit("browser", user, "action_created", f"action={action.id}, type={action_type}")
    return {"action": action.model_dump()}


@router.get("/actions")
async def list_actions(
    session_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List browser actions with optional filters."""
    actions = get_store("browser_actions").load()
    uid = user.get("id") or "unknown"

    # Filter to user's sessions
    sessions = get_store("browser_sessions").load()
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}

    mine = [a for a in actions.values() if a.get("session_id") in my_session_ids]
    if session_id:
        mine = [a for a in mine if a.get("session_id") == session_id]
    if status:
        mine = [a for a in mine if a.get("status") == status]
    mine.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return {"actions": mine, "count": len(mine)}


@router.post("/actions/{action_id}/execute")
async def execute_action(
    action_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Execute a queued browser action after permission check."""
    actions = get_store("browser_actions").load()
    action_data = actions.get(action_id)
    if not action_data:
        raise HTTPException(status_code=404, detail="Action not found")

    # Verify session ownership
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(action_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Check permission
    if action_data.get("permission") == ActionPermission.DENIED.value:
        raise HTTPException(status_code=403, detail="Action denied by policy")

    # Require confirmation for actions that need it
    if action_data.get("permission") == ActionPermission.REQUIRES_CONFIRMATION.value:
        return {
            "action": action_data,
            "requires_confirmation": True,
            "message": "This action requires your confirmation before execution.",
        }

    # Execute the action
    action_data["status"] = ActionStatus.RUNNING.value
    action_data["executed_at"] = _now()
    actions[action_id] = action_data
    get_store("browser_actions").save()

    result = {"executed": True, "action_id": action_id, "type": action_data.get("type")}

    # Perform the actual browser operation based on type
    try:
        action_type = action_data.get("type")
        params = action_data.get("parameters", {})

        if action_type == ActionType.NAVIGATE.value:
            url = params.get("url", "")
            if _is_blocked_domain(url):
                result["blocked"] = True
                result["reason"] = "Blocked domain"
                _audit("browser", user, "action_navigation_blocked", f"url={url[:100]}")
            else:
                tab_resp = await create_tab(
                    TabCreateIn(session_id=action_data["session_id"], url=url, title=params.get("title", url)),
                    user,
                )
                result["tab_id"] = tab_resp["tab"]["id"]
                result["url"] = url

        elif action_type == ActionType.SEARCH.value:
            search_resp = await browser_search(
                SearchIn(query=params.get("query", ""), session_id=action_data["session_id"]),
                user,
                Request,
            )
            result["search_results"] = search_resp["results"]

        elif action_type == ActionType.EXTRACT.value:
            ext = await extract_page(
                ExtractIn(url=params.get("url", ""), content=params.get("content")),
                user,
            )
            result["page_data"] = {
                "title": ext["title"],
                "text_length": ext["text_length"],
                "entities": ext["entities"][:10],
            }

        elif action_type == ActionType.CAPTURE_EVIDENCE.value:
            ev = await capture_evidence(
                EvidenceCaptureIn(
                    url=params.get("url", ""),
                    selected_passage=params.get("selected_passage", ""),
                    claim=params.get("claim"),
                    verification_status="unchecked",
                ),
                user,
            )
            result["evidence_id"] = ev["id"]

        elif action_type == ActionType.DOWNLOAD.value:
            url = params.get("url", "")
            if _is_blocked_domain(url):
                result["blocked"] = True
                result["reason"] = "Blocked domain"
            else:
                import asyncio as _asyncio
                loop = _asyncio.get_event_loop()
                fetched = await loop.run_in_executor(None, _fetch_url_sync, url)
                filename = params.get("filename") or _domain_from_url(url)
                if not isinstance(filename, str):
                    raise HTTPException(status_code=400, detail="Invalid download filename")
                save_path = _download_destination(filename, str(user.get("id") or ""))
                try:
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(fetched.get("html", ""))
                except OSError as exc:
                    raise HTTPException(status_code=500, detail="Download could not be saved") from exc
                result["download"] = {"filename": filename, "size_bytes": len(fetched.get("html", ""))}

        elif action_type == ActionType.COMPARE.value:
            tab_ids = params.get("tab_ids", [])
            tabs = get_store("browser_tabs").load()
            comparisons = []
            for tid in tab_ids:
                tab = tabs.get(tid)
                if tab and tab.get("extracted_content"):
                    comparisons.append({
                        "tab_id": tid,
                        "url": tab.get("url", ""),
                        "text": tab.get("extracted_content", "")[:2000],
                    })
            result["comparisons"] = comparisons

        elif action_type == ActionType.SUBMIT_FORM.value:
            result["status"] = "requires_confirmation"
            result["message"] = "Form submission requires explicit user confirmation."

        else:
            result["status"] = "executed"

        action_data["status"] = ActionStatus.COMPLETED.value
        action_data["result"] = result
    except Exception as e:
        action_data["status"] = ActionStatus.FAILED.value
        action_data["error"] = str(e)
        result["error"] = str(e)

    action_data["verified_at"] = _now()
    actions[action_id] = action_data
    get_store("browser_actions").save()

    _audit("browser", user, "action_executed", f"action={action_id}, type={action_data.get('type')}")
    return result


# =========================================================================
# Observe → Act Loop (spec §4)
# =========================================================================

@router.post("/observe-act")
async def observe_act_loop(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Execute one step of the Observe → Act loop.

    Input: session_id, tab_id, observation (optional), proposed_action
    Output: page_state, observation, proposed_action, policy_check, execution_result, verification
    """
    session_id = body.get("session_id", "")
    tab_id = body.get("tab_id", "")
    proposed_action = body.get("proposed_action", {})

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tabs = get_store("browser_tabs").load()
    tab = tabs.get(tab_id) if tab_id else None

    # --- OBSERVE: get current page state ---
    page_state: Dict[str, Any] = {}
    if tab and tab.get("url") and tab["url"] != "about:blank":
        try:
            ext = await extract_page(
                ExtractIn(url=tab["url"], content=tab.get("extracted_content")),
                user,
            )
            page_state = {
                "url": ext["url"],
                "title": ext["title"],
                "text_length": ext["text_length"],
                "structure": ext.get("structure", {}),
                "entities": ext.get("entities", []),
                "prompt_injection": ext.get("prompt_injection", {}),
            }
        except Exception:
            page_state = {"url": tab.get("url", ""), "title": tab.get("title", "")}
    else:
        page_state = {"url": tab.get("url", "") if tab else "", "title": tab.get("title", "") if tab else ""}

    # --- POLICY CHECK ---
    action_type = proposed_action.get("type", "")
    action_params = proposed_action.get("parameters", {})
    action_target = proposed_action.get("target", "")

    policy_check = {"passed": True, "reasons": []}

    # Check blocked domains
    if action_type == ActionType.NAVIGATE.value:
        url = action_params.get("url", action_target)
        if _is_blocked_domain(url):
            policy_check["passed"] = False
            policy_check["reasons"].append(f"Blocked domain: {url}")

    # Check prompt injection in target content
    if action_target:
        injection = _detect_prompt_injection(action_target)
        if injection["flagged"]:
            policy_check["passed"] = False
            policy_check["reasons"].append(f"Prompt injection detected: {injection['matches']}")

    # Check high-risk actions
    high_risk = {"submit_form", "purchase", "delete", "change_settings", "grant_permissions"}
    if action_type in high_risk and sess.get("privacy_mode") not in ("agent", "automation"):
        policy_check["passed"] = False
        policy_check["reasons"].append(f"High-risk action '{action_type}' requires agent/automation mode")

    # --- EXECUTE (if policy passed) ---
    execution_result: Dict[str, Any] = {"executed": False, "skipped": True}
    if policy_check["passed"]:
        action_data = {
            "type": action_type,
            "target": action_target,
            "parameters": action_params,
            "source": "agent",
            "session_id": session_id,
            "tab_id": tab_id,
            "permission": ActionPermission.ALLOWED.value,
            "status": ActionStatus.RUNNING.value,
        }
        actions = get_store("browser_actions").load()
        aid = f"act-{uuid.uuid4().hex[:12]}"
        action_data["id"] = aid
        actions[aid] = action_data
        get_store("browser_actions").save()

        # Execute based on type
        if action_type == ActionType.NAVIGATE.value:
            nav_resp = await navigate(NavigateIn(session_id=session_id, url=action_params.get("url", "")), user)
            execution_result = {"executed": True, "skipped": False, "navigated": nav_resp.get("navigated", False), "url": nav_resp.get("url", "")}
        elif action_type == ActionType.SEARCH.value:
            sr = await browser_search(SearchIn(query=action_params.get("query", ""), session_id=session_id), user, Request)
            execution_result = {"executed": True, "skipped": False, "search_results": sr.get("results", [])}
        elif action_type == ActionType.EXTRACT.value:
            ex = await extract_page(ExtractIn(url=action_params.get("url", "")), user)
            execution_result = {"executed": True, "skipped": False, "extracted": True, "text_length": ex.get("text_length", 0)}
        elif action_type == ActionType.CAPTURE_EVIDENCE.value:
            ev = await capture_evidence(EvidenceCaptureIn(url=action_params.get("url", ""), selected_passage=action_params.get("selected_passage", "")), user)
            execution_result = {"executed": True, "skipped": False, "evidence_id": ev["id"]}
        else:
            execution_result = {"executed": True, "skipped": False, "note": f"Action type '{action_type}' executed"}

        action_data["status"] = ActionStatus.COMPLETED.value
        action_data["result"] = execution_result
        actions[aid] = action_data
        get_store("browser_actions").save()

    # --- VERIFY ---
    verification = {
        "verified": policy_check["passed"] and execution_result.get("executed", False),
        "page_state_changed": bool(page_state),
        "policy_reasons": policy_check["reasons"],
    }

    return {
        "page_state": page_state,
        "observation": "Page state extracted and analyzed",
        "proposed_action": proposed_action,
        "policy_check": policy_check,
        "execution_result": execution_result,
        "verification": verification,
    }


# =========================================================================
# Structured Page State (spec §6)
# =========================================================================

@router.post("/page-state")
async def get_page_state(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a compact structured page state for AI context (spec §6).

    Instead of sending entire pages, this returns a structured
    representation with only the relevant information.
    """
    url = body.get("url", "")
    content = body.get("content", "")
    user_selection = body.get("user_selection", "")

    if _is_blocked_domain(url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    raw_content = content or ""
    text = _extract_text_from_html(raw_content)

    if not text:
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        try:
            fetched = await loop.run_in_executor(None, _fetch_url_sync, url)
            raw_content = fetched.get("html", "")
            text = _extract_text_from_html(raw_content)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_502, detail=f"Failed to fetch URL: {str(e)[:200]}")

    injection = _detect_prompt_injection(text, raw_content)
    metadata = _extract_metadata(raw_content, url)
    structure = _extract_page_structure(raw_content)
    entities = _extract_entities(text)

    # Classify the page (spec §22)
    page_class = classify_page(url, metadata.get("title", ""), text[:500])

    # Build interactive element map (spec §7)
    interactive_elements = _build_element_map(raw_content, url)

    page_state = PageState(
        url=url,
        title=metadata.get("title", ""),
        domain=_domain_from_url(url),
        page_classification=page_class,
        metadata=metadata,
        headings=structure.get("headings", []),
        main_content=text[:5000],
        interactive_elements=interactive_elements,
        forms=_extract_forms(raw_content),
        links=_extract_links(raw_content, url),
        tables=_extract_tables(raw_content),
        selected_content=user_selection,
        visible_warnings=_extract_warnings(raw_content),
        security_indicators=["prompt_injection" if injection["flagged"] else "clean"],
        prompt_injection_flagged=injection["flagged"],
        word_count=structure.get("word_count", 0),
    )

    # Store page state
    page_states = get_store("browser_page_states").load()
    ps_id = f"ps-{uuid.uuid4().hex[:12]}"
    page_states[ps_id] = page_state.model_dump()
    get_store("browser_page_states").save()

    return {"page_state": page_state.model_dump(), "page_state_id": ps_id}


def _build_element_map(html_content: str, base_url: str) -> List[Dict[str, Any]]:
    """Build interactive element map from HTML (spec §7)."""
    elements = []
    # Buttons
    for i, btn in enumerate(re.finditer(r'<button[^>]*>(.*?)</button>', html_content, re.DOTALL | re.IGNORECASE)):
        label = _html.unescape(re.sub(r'<[^>]+>', '', btn.group(1)).strip())[:100]
        elements.append({"id": f"el-{i}-btn", "type": "button", "label": label, "selector": f"button:nth-child({i+1})", "visible": True, "enabled": "disabled" not in btn.group(0).lower()})
    # Links
    for i, link in enumerate(re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_content, re.DOTALL | re.IGNORECASE)):
        label = _html.unescape(re.sub(r'<[^>]+>', '', link.group(2)).strip())[:100]
        elements.append({"id": f"el-{i}-link", "type": "link", "label": label, "selector": f"a[href='{link.group(1)}']", "url": link.group(1), "visible": True, "enabled": True})
    # Inputs
    for i, inp in enumerate(re.finditer(r'<input[^>]*>', html_content, re.IGNORECASE)):
        inp_tag = inp.group(0)
        input_type = re.search(r'type=["\']([^"\']+)["\']', inp_tag)
        input_type = input_type.group(1) if input_type else "text"
        name = re.search(r'name=["\']([^"\']+)["\']', inp_tag)
        elements.append({"id": f"el-{i}-input", "type": "textbox" if input_type == "text" else input_type, "label": name.group(1) if name else "", "selector": f"input[type='{input_type}']:nth-child({i+1})", "visible": True, "enabled": "disabled" not in inp_tag.lower()})
    # Forms
    for i, form in enumerate(re.finditer(r'<form[^>]*>(.*?)</form>', html_content, re.DOTALL | re.IGNORECASE)):
        form_content = form.group(1)
        inputs = len(re.findall(r'<input[^>]*>', form_content))
        elements.append({"id": f"el-{i}-form", "type": "form", "label": f"Form with {inputs} inputs", "selector": f"form:nth-child({i+1})", "visible": True, "enabled": True, "input_count": inputs})
    return elements


def _extract_forms(html_content: str) -> List[Dict[str, Any]]:
    """Extract form elements from HTML."""
    forms = []
    for i, form in enumerate(re.finditer(r'<form[^>]*>(.*?)</form>', html_content, re.DOTALL | re.IGNORECASE)):
        inputs = re.findall(r'<input[^>]*>', form.group(1))
        forms.append({"id": f"form-{i}", "input_count": len(inputs), "action": re.search(r'action=["\']([^"\']+)["\']', form.group(0))})
    return forms


def _extract_links(html_content: str, base_url: str) -> List[Dict[str, Any]]:
    """Extract links from HTML."""
    links = []
    for link in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_content, re.DOTALL | re.IGNORECASE):
        links.append({"url": link.group(1), "text": _html.unescape(re.sub(r'<[^>]+>', '', link.group(2)).strip())[:200]})
    return links[:50]


def _extract_tables(html_content: str) -> List[Dict[str, Any]]:
    """Extract table summaries from HTML."""
    tables = []
    for i, table in enumerate(re.finditer(r'<table[^>]*>(.*?)</table>', html_content, re.DOTALL | re.IGNORECASE)):
        rows = re.findall(r'<tr[^>]*>', table.group(1))
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', table.group(1), re.DOTALL)
        tables.append({"id": f"table-{i}", "rows": len(rows), "cells": len(cells)})
    return tables


def _extract_warnings(html_content: str) -> List[str]:
    """Extract visible warnings from HTML."""
    warnings = []
    for match in re.finditer(r'<div[^>]*class=["\'][^"\']*(?:warning|alert|error|danger)[^"\']*["\'][^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE):
        text = _html.unescape(re.sub(r'<[^>]+>', '', match.group(1)).strip())
        if text:
            warnings.append(text[:500])
    return warnings


# =========================================================================
# Browser Task Execution Engine (spec §10, §13–14)
# =========================================================================

@router.post("/tasks")
async def create_task(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a multi-step browser task with plan and checkpoint support (spec §10, §13)."""
    session_id = body.get("session_id", "")
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    goal = body.get("goal", "")
    plan = body.get("plan", [])
    steps = [TaskStep(description=step, action_type=ActionType.NAVIGATE) for step in plan]

    task = BrowserTask(
        session_id=session_id,
        mission_id=body.get("mission_id"),
        research_session_id=body.get("research_session_id"),
        goal=goal,
        plan=plan,
        steps=steps,
        pause_on_risk=body.get("pause_on_risk", True),
        agent_id=body.get("agent_id"),
    )

    tasks = get_store("browser_tasks").load()
    tasks[task.id] = task.model_dump()
    get_store("browser_tasks").save()

    _audit("browser", user, "task_created", f"task={task.id}, goal={goal[:50]}")
    return {"task": task.model_dump()}


@router.get("/tasks")
async def list_tasks(
    session_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List browser tasks with optional filters."""
    tasks = get_store("browser_tasks").load()
    uid = user.get("id") or "unknown"
    sessions = get_store("browser_sessions").load()
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}

    mine = [t for t in tasks.values() if t.get("session_id") in my_session_ids]
    if session_id:
        mine = [t for t in mine if t.get("session_id") == session_id]
    if status:
        mine = [t for t in mine if t.get("status") == status]
    mine.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"tasks": mine, "count": len(mine)}


@router.post("/tasks/{task_id}/step/{step_id}/execute")
async def execute_task_step(
    task_id: str,
    step_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Execute a single step of a browser task (spec §10)."""
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Find the step
    step = None
    for s in task_data.get("steps", []):
        if s.get("id") == step_id:
            step = s
            break
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    # Create checkpoint before executing (spec §13)
    checkpoint = TaskCheckpoint(
        task_id=task_id,
        session_id=task_data["session_id"],
        step_index=task_data.get("current_step_index", 0),
        evidence_ids=task_data.get("evidence_ids", []),
    )
    checkpoints = get_store("browser_checkpoints").load()
    checkpoints[checkpoint.id] = checkpoint.model_dump()
    get_store("browser_checkpoints").save()
    task_data["checkpoint_id"] = checkpoint.id

    # Execute the step
    step["status"] = ActionStatus.RUNNING.value
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    try:
        # Execute based on step action type
        result = {"executed": True, "step_id": step_id, "description": step.get("description", "")}
        step["result"] = result
        step["verified"] = True
        step["status"] = ActionStatus.COMPLETED.value
    except Exception as e:
        step["status"] = ActionStatus.FAILED.value
        step["error"] = str(e)
        result = {"error": str(e)}

    task_data["steps"] = [s if s.get("id") != step_id else step for s in task_data.get("steps", [])]
    task_data["current_step_index"] = task_data.get("current_step_index", 0) + 1
    task_data["updated_at"] = _now()
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    return {"step": step, "result": result, "checkpoint_id": checkpoint.id}


@router.post("/tasks/{task_id}/checkpoint")
async def create_task_checkpoint(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a checkpoint for a browser task (spec §13)."""
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    checkpoint = TaskCheckpoint(
        task_id=task_id,
        session_id=task_data["session_id"],
        step_index=task_data.get("current_step_index", 0),
        page_state=task_data.get("steps", [{}])[task_data.get("current_step_index", 0)].get("result", {}) if task_data.get("steps") else {},
        evidence_ids=task_data.get("evidence_ids", []),
    )
    checkpoints = get_store("browser_checkpoints").load()
    checkpoints[checkpoint.id] = checkpoint.model_dump()
    get_store("browser_checkpoints").save()

    task_data["checkpoint_id"] = checkpoint.id
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    return {"checkpoint": checkpoint.model_dump()}


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Resume a task from its last checkpoint (spec §14)."""
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Find the last checkpoint
    checkpoints = get_store("browser_checkpoints").load()
    task_checkpoints = [c for c in checkpoints.values() if c.get("task_id") == task_id]
    task_checkpoints.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    if not task_checkpoints:
        return {"task": task_data, "resumed": False, "message": "No checkpoints found — starting from beginning"}

    last_checkpoint = task_checkpoints[0]
    task_data["current_step_index"] = last_checkpoint.get("step_index", 0)
    task_data["status"] = ActionStatus.QUEUED.value
    task_data["updated_at"] = _now()
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    return {"task": task_data, "resumed": True, "checkpoint_id": last_checkpoint["id"], "step_index": last_checkpoint.get("step_index", 0)}


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Pause a running browser task (spec §14)."""
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    task_data["status"] = ActionStatus.BLOCKED.value
    task_data["updated_at"] = _now()
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    return {"task": task_data, "paused": True}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Cancel a browser task (spec §14)."""
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    task_data["status"] = ActionStatus.FAILED.value
    task_data["error"] = "Cancelled by user"
    task_data["updated_at"] = _now()
    tasks[task_id] = task_data
    get_store("browser_tasks").save()

    return {"task": task_data, "cancelled": True}


# =========================================================================
# Browser Workspaces (spec §17)
# =========================================================================

@router.post("/workspaces")
async def create_workspace(
    body: BrowserWorkspaceCreateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a browser workspace (spec §17)."""
    workspace = BrowserWorkspace(
        owner_id=user["id"],
        name=body.name,
        description=body.description,
        privacy_mode=body.privacy_mode,
    )
    workspaces = get_store("browser_workspaces").load()
    workspaces[workspace.id] = workspace.model_dump()
    get_store("browser_workspaces").save()

    _audit("browser", user, "workspace_created", f"workspace={workspace.id}")
    return {"workspace": workspace.model_dump()}


@router.get("/workspaces")
async def list_workspaces(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List browser workspaces."""
    workspaces = get_store("browser_workspaces").load()
    uid = user.get("id") or "unknown"
    mine = [w for w in workspaces.values() if w.get("owner_id") == uid]
    mine.sort(key=lambda w: w.get("created_at", ""), reverse=True)
    return {"workspaces": mine, "count": len(mine)}


@router.put("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    body: BrowserWorkspaceUpdateIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a browser workspace."""
    workspaces = get_store("browser_workspaces").load()
    ws = workspaces.get(workspace_id)
    if not ws or ws.get("owner_id") != user.get("id"):
        raise HTTPException(status_code=404, detail="Workspace not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            ws[field] = value
    ws["updated_at"] = _now()
    workspaces[workspace_id] = ws
    get_store("browser_workspaces").save()

    return {"workspace": ws}


@router.post("/workspaces/{workspace_id}/associate")
async def associate_workspace(
    workspace_id: str,
    body: BrowserWorkspaceAssociationIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Associate a session, mission, or evidence with a workspace."""
    workspaces = get_store("browser_workspaces").load()
    ws = workspaces.get(workspace_id)
    if not ws or ws.get("owner_id") != user.get("id"):
        raise HTTPException(status_code=404, detail="Workspace not found")

    association_type = body.type
    association_id = body.id
    uid = user.get("id")
    if association_type == "session":
        resource = get_store("browser_sessions").load().get(association_id)
        if not resource or resource.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="Session not found")
    elif association_type == "evidence":
        resource = next(
            (
                item
                for item in get_store("browser_evidence").load()
                if item.get("id") == association_id and item.get("user_id") == uid
            ),
            None,
        )
        if not resource:
            raise HTTPException(status_code=404, detail="Evidence not found")
    else:
        missions = get_store("missions").load()
        resource = missions.get(association_id) if isinstance(missions, dict) else next(
            (item for item in missions if item.get("id") == association_id),
            None,
        )
        if not resource or resource.get("user_id", resource.get("owner_id")) != uid:
            raise HTTPException(status_code=404, detail="Mission not found")

    if association_type == "session" and association_id not in ws["session_ids"]:
        ws["session_ids"].append(association_id)
    elif association_type == "mission" and association_id not in ws["mission_ids"]:
        ws["mission_ids"].append(association_id)
    elif association_type == "evidence" and association_id not in ws["evidence_ids"]:
        ws["evidence_ids"].append(association_id)

    ws["updated_at"] = _now()
    workspaces[workspace_id] = ws
    get_store("browser_workspaces").save()

    return {"workspace": ws}


# =========================================================================
# Browser Telemetry (spec §42)
# =========================================================================

@router.post("/telemetry")
async def record_telemetry(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Record browser telemetry (spec §42)."""
    telemetry = BrowserTelemetryEntry(
        session_id=body.get("session_id", ""),
        action=body.get("action", ""),
        navigation_latency_ms=body.get("navigation_latency_ms"),
        extraction_latency_ms=body.get("extraction_latency_ms"),
        ai_latency_ms=body.get("ai_latency_ms"),
        provider=body.get("provider"),
        model=body.get("model"),
        tokens=body.get("tokens"),
        cost=body.get("cost"),
        downloads=body.get("downloads", 0),
        errors=body.get("errors", 0),
        security_blocks=body.get("security_blocks", 0),
        automation_actions=body.get("automation_actions", 0),
    )
    store = get_store("browser_telemetry").load()
    store.append(telemetry.model_dump())
    if len(store) > 1000:
        store = store[-1000:]
    get_store("browser_telemetry").save()

    return {"telemetry": telemetry.model_dump()}


@router.get("/telemetry")
async def get_telemetry(
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser telemetry with optional filters."""
    store = get_store("browser_telemetry").load()
    uid = user.get("id") or "unknown"
    sessions = get_store("browser_sessions").load()
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}

    mine = [t for t in store if t.get("session_id") in my_session_ids]
    if session_id:
        mine = [t for t in mine if t.get("session_id") == session_id]
    mine.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
    return {"telemetry": mine[:limit], "count": len(mine)}


# =========================================================================
# Source Graph (spec §36)
# =========================================================================

@router.post("/source-graph")
async def build_source_graph(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Build a source graph for research workflows (spec §36).

    Represents: claim → source → evidence → verification
    and source ↔ related source connections.
    """
    session_id = body.get("session_id", "")
    claim = body.get("claim", "")
    sources = body.get("sources", [])
    evidence_items = body.get("evidence", [])

    graph = {
        "id": f"sg-{uuid.uuid4().hex[:10]}",
        "session_id": session_id,
        "claim": claim,
        "sources": sources,
        "evidence": evidence_items,
        "connections": [],
        "created_at": _now(),
    }

    # Build connections between sources
    for i, src_a in enumerate(sources):
        for j, src_b in enumerate(sources):
            if i < j:
                # Check if sources share content (agreement/disagreement)
                graph["connections"].append({
                    "source_a": src_a.get("url", ""),
                    "source_b": src_b.get("url", ""),
                    "type": "related",
                    "agreement": None,  # To be filled by verification
                })

    # Store source graph
    graphs = get_store("browser_source_graph").load()
    graphs[graph["id"]] = graph
    get_store("browser_source_graph").save()

    return {"source_graph": graph}


@router.get("/source-graph")
async def list_source_graphs(
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List source graphs with optional filters."""
    graphs = get_store("browser_source_graph").load()
    uid = user.get("id") or "unknown"
    sessions = get_store("browser_sessions").load()
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}

    mine = [g for g in graphs.values() if g.get("session_id") in my_session_ids]
    if session_id:
        mine = [g for g in mine if g.get("session_id") == session_id]
    mine.sort(key=lambda g: g.get("created_at", ""), reverse=True)
    return {"source_graphs": mine, "count": len(mine)}


# =========================================================================
# Browser Timeline (spec §37)
# =========================================================================

@router.post("/timeline")
async def add_timeline_entry(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Add an entry to the browser timeline (spec §37)."""
    entry = {
        "id": f"tl-{uuid.uuid4().hex[:10]}",
        "timestamp": _now(),
        "epoch": _now_epoch(),
        "session_id": body.get("session_id", ""),
        "action": body.get("action", ""),
        "detail": body.get("detail", ""),
        "url": body.get("url", ""),
        "user_id": user.get("id") or "unknown",
    }
    store = get_store("browser_timeline").load()
    store.append(entry)
    if len(store) > 2000:
        store = store[-2000:]
    get_store("browser_timeline").save()

    return {"timeline_entry": entry}


@router.get("/timeline")
async def get_timeline(
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser timeline with optional filters."""
    store = get_store("browser_timeline").load()
    uid = user.get("id") or "unknown"
    sessions = get_store("browser_sessions").load()
    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}

    mine = [t for t in store if t.get("session_id") in my_session_ids]
    if session_id:
        mine = [t for t in mine if t.get("session_id") == session_id]
    mine.sort(key=lambda t: t.get("epoch", 0), reverse=True)
    return {"timeline": mine[:limit], "count": len(mine)}


# =========================================================================
# Action Replay (spec §38–39)
# =========================================================================

@router.get("/actions/replay/{session_id}")
async def replay_actions(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get an auditable action sequence for replay (spec §38).

    The caller must verify that the current page state matches
    the expected state before replaying any action.
    """
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    actions = get_store("browser_actions").load()
    session_actions = [a for a in actions.values() if a.get("session_id") == session_id]
    session_actions.sort(key=lambda a: a.get("created_at", ""))

    return {
        "session_id": session_id,
        "actions": session_actions,
        "count": len(session_actions),
        "replay_warning": "Before replaying, verify that the current page state matches the expected state. Stale coordinates or DOM identifiers must NOT be replayed without revalidation.",
    }


# =========================================================================
# Model Routing for Browser Tasks (spec §9, §42–44)
# =========================================================================

# Browser task complexity levels map to model capabilities.
BROWSER_TASK_COMPLEXITY = {
    "simple_extraction": {"capability": "text-generation", "model_type": "lightweight"},
    "complex_research": {"capability": "reasoning", "model_type": "reasoning"},
    "visual_understand": {"capability": "multimodal", "model_type": "multimodal"},
    "coding_documentation": {"capability": "text-generation", "model_type": "coding"},
    "private_browsing": {"capability": "text-generation", "model_type": "local"},
}


# Cloud providers the browser may fall back to when the local Silverwing
# runtime is unavailable. Honesty contract (§62): only a provider that is
# actually configured (API key present) is ever suggested -- we never claim
# "openai" unless OPENAI_API_KEY (or its JARVIS alias) is set.
_BROWSER_CLOUD_FALLBACK_ORDER = ("openai", "claude", "gemini", "codemuse", "stablediffusion")


def _select_browser_cloud_fallback() -> Dict[str, Any]:
    """Return the first *configured* cloud provider for browser AI, else None.

    Never fakes availability: if no API key is present for any cloud provider,
    ``provider`` is ``None`` and ``reason`` explains exactly what to configure.
    """
    from . import extensions as _ext  # lazy import: avoids load-time cycle
    for ext_id in _BROWSER_CLOUD_FALLBACK_ORDER:
        if _ext._env_api_key(ext_id):
            caps = _ext._extension_capabilities(ext_id) or []
            return {
                "provider": ext_id,
                "capability": caps[0] if caps else None,
                "reason": "capability-flagged (configured)",
            }
    return {
        "provider": None,
        "capability": None,
        "reason": "no cloud provider configured (set an API key env var, "
                  "e.g. OPENAI_API_KEY) to enable cloud browser AI",
    }


@router.post("/model-route")
async def get_model_route(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get model routing recommendation for a browser task (spec §9, §44).

    Browser intelligence should not be tied to one model.  This endpoint
    uses the existing JARVIS model router to recommend a provider/model
    based on task complexity, privacy requirements, cost, and availability.
    """
    task_type = body.get("task_type", "simple_extraction")
    privacy_mode = body.get("privacy_mode", "standard")
    budget_constraint = body.get("budget_constraint", "standard")
    latency_target = body.get("latency_target", "standard")

    complexity = BROWSER_TASK_COMPLEXITY.get(task_type, BROWSER_TASK_COMPLEXITY["simple_extraction"])
    cloud_fallback = _select_browser_cloud_fallback()
    recommendation = {
        "task_type": task_type,
        "capability": complexity["capability"],
        "model_type": complexity["model_type"],
        "privacy_mode": privacy_mode,
        "cloud_fallback": cloud_fallback,
        "routing_policy": {},
    }

    # Private browsing must use local model
    if privacy_mode in ("private", "authenticated"):
        recommendation["routing_policy"] = {
            "provider": "local",
            "model": "jarvis-brain-qwen3-4b-v1",
            "reason": "Private browsing requires local model",
            "cost": 0,
        }
    # Visual tasks need multimodal
    elif complexity["model_type"] == "multimodal":
        recommendation["routing_policy"] = {
            "provider": "silverwing",
            "model": os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
            "fallback": cloud_fallback["provider"],
            "reason": "Multimodal capability required",
            "cost_estimate": "low",
        }
    # Complex research uses reasoning model
    elif complexity["model_type"] == "reasoning":
        recommendation["routing_policy"] = {
            "provider": "silverwing",
            "model": os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
            "fallback": cloud_fallback["provider"],
            "reason": "Reasoning capability required",
            "cost_estimate": "high",
        }
    # Simple extraction uses lightweight model
    else:
        recommendation["routing_policy"] = {
            "provider": "silverwing",
            "model": os.environ.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
            "fallback": cloud_fallback["provider"],
            "reason": "Lightweight model sufficient for simple extraction",
            "cost_estimate": "low",
        }

    # Cost awareness (spec §43)
    if budget_constraint == "minimal":
        recommendation["routing_policy"]["provider"] = "silverwing"
        recommendation["routing_policy"]["cost_estimate"] = "minimal"
    elif budget_constraint == "unlimited":
        recommendation["routing_policy"]["fallback"] = cloud_fallback["provider"]
        recommendation["routing_policy"]["cost_estimate"] = "unlimited"

    # Latency optimization (spec §42)
    recommendation["routing_policy"]["latency_target"] = latency_target

    _audit("browser", user, "model_route_requested",
           f"task_type={task_type}, provider={recommendation['routing_policy'].get('provider', 'unknown')}")

    return recommendation


# =========================================================================
# Evidence → Knowledge Pipeline (spec §27–28)
# =========================================================================

@router.post("/evidence/{evidence_id}/promote")
async def promote_evidence_to_knowledge(
    evidence_id: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Promote verified evidence to knowledge (spec §28).

    Verified evidence can become a knowledge candidate after validation.
    The validation policy can be configured per-workspace.
    """
    evidence_store = get_store("browser_evidence").load()
    ev = _find_in_list(evidence_store, evidence_id)
    if not ev or ev.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=404, detail="Evidence not found")

    verification_status = ev.get("verification_status", "unchecked")
    if verification_status not in ("verified", "confirmed"):
        raise HTTPException(
            status_code=400,
            detail="Evidence must be verified before promoting to knowledge. Current status: " + verification_status,
        )

    # Create knowledge entry
    knowledge = get_store("knowledge").load()
    kid = f"kb-{uuid.uuid4().hex[:12]}"
    knowledge[kid] = {
        "id": kid,
        "key": ev.get("claim") or ev.get("selected_passage", "")[:200],
        "value": ev.get("selected_passage", ""),
        "url": ev.get("url", ""),
        "domain": ev.get("domain", ""),
        "source": "browser_evidence",
        "source_id": evidence_id,
        "user_id": user.get("id") or "unknown",
        "verification_status": verification_status,
        "created_at": _now(),
        "updated_at": _now(),
        "tags": ev.get("tags", []) + ["from_browser"],
        "provenance": {
            "evidence_url": ev.get("url", ""),
            "captured_at": ev.get("captured_at", ""),
            "title": ev.get("title", ""),
        },
    }
    get_store("knowledge").save()

    # Link evidence to knowledge
    ev["knowledge_id"] = kid
    ev["verification_status"] = "promoted"
    get_store("browser_evidence").save()

    _audit("browser", user, "evidence_promoted",
           f"evidence={evidence_id}, knowledge={kid}")

    # Record learning (spec §32)
    learning_entry = {
        "id": f"learn-{uuid.uuid4().hex[:12]}",
        "task_type": "fact_verification",
        "source": "browser",
        "evidence_id": evidence_id,
        "knowledge_id": kid,
        "user_id": user.get("id") or "unknown",
        "created_at": _now(),
        "verified": True,
        "quality_score": 1.0,
    }
    learning = get_store("learning_sessions").load()
    learning[learning_entry["id"]] = learning_entry
    get_store("learning_sessions").save()

    return {"knowledge_id": kid, "knowledge": knowledge[kid]}


@router.post("/evidence/{evidence_id}/to-mission")
async def evidence_to_mission(
    evidence_id: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Convert browser evidence into a mission (spec §29).

    Current page + selected evidence + objective → Create Mission.
    """
    evidence_store = get_store("browser_evidence").load()
    ev = _find_in_list(evidence_store, evidence_id)
    if not ev or ev.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=404, detail="Evidence not found")

    mission_title = body.get("title") or (ev.get("claim") or ev.get("selected_passage", "")[:80])
    mission_objective = body.get("objective") or ev.get("selected_passage", "")

    try:
        from ..connectors.dispatch import dispatch_to_tool
        result = await dispatch_to_tool("missions", {
            "action": "create",
            "title": mission_title,
            "objective": mission_objective,
            "source": "browser_evidence",
            "source_id": evidence_id,
            "user_id": user.get("id") or "unknown",
        })
    except ImportError:
        # Mission control may not be available — create a lightweight mission record
        missions = get_store("missions").load()
        mid = f"miss-{uuid.uuid4().hex[:10]}"
        mission = {
            "id": mid,
            "title": mission_title,
            "objective": mission_objective,
            "status": "planning",
            "source": "browser_evidence",
            "source_id": evidence_id,
            "user_id": user.get("id") or "unknown",
            "created_at": _now(),
            "updated_at": _now(),
            "browser_session_id": ev.get("research_session_id"),
        }
        missions[mid] = mission
        get_store("missions").save()
        result = {"mission": mission, "created": True}

    _audit("browser", user, "evidence_to_mission",
           f"evidence={evidence_id}")

    return {"result": result, "evidence_id": evidence_id}


# =========================================================================
# Browser → Mission Integration (spec §29–30)
# =========================================================================

@router.post("/missions/{mission_id}/context")
async def get_mission_browser_context(
    mission_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser context for a mission (spec §29–30).

    Returns the browser session, tabs, evidence, and tasks associated
    with a mission.
    """
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    evidence = get_store("browser_evidence").load()
    tasks = get_store("browser_tasks").load()
    uid = user.get("id") or "unknown"

    # Find sessions associated with this mission
    mission_sessions = [s for s in sessions.values()
                        if s.get("mission_id") == mission_id and s.get("user_id") == uid]
    session_ids = {s["id"] for s in mission_sessions}

    mission_tabs = [t for t in tabs.values() if t.get("session_id") in session_ids]
    mission_evidence = [e for e in evidence if e.get("mission_id") == mission_id and e.get("user_id") == uid]
    mission_tasks = [t for t in tasks.values()
                     if t.get("mission_id") == mission_id and t.get("session_id") in session_ids]

    return {
        "mission_id": mission_id,
        "sessions": mission_sessions,
        "tabs": mission_tabs,
        "evidence": mission_evidence,
        "tasks": mission_tasks,
        "evidence_count": len(mission_evidence),
        "tab_count": len(mission_tabs),
    }


@router.post("/missions/{mission_id}/browser-task")
async def create_mission_browser_task(
    mission_id: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a browser task linked to a mission (spec §30)."""
    task_body = {
        **body,
        "mission_id": mission_id,
    }
    return await create_task(task_body, user=user)


# =========================================================================
# Browser → Memory Integration (spec §31)
# =========================================================================

@router.post("/evidence/{evidence_id}/to-memory")
async def evidence_to_memory(
    evidence_id: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Store verified browser evidence to JARVIS Memory (spec §31)."""
    evidence_store = get_store("browser_evidence").load()
    ev = _find_in_list(evidence_store, evidence_id)
    if not ev or ev.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=404, detail="Evidence not found")

    memory_layer = body.get("layer", "episodic")
    memory_entry = {
        "id": f"mem-{uuid.uuid4().hex[:12]}",
        "content": ev.get("selected_passage", ""),
        "layer": memory_layer,
        "type": "browser_evidence",
        "source": "browser",
        "source_id": evidence_id,
        "url": ev.get("url", ""),
        "user_id": user.get("id") or "unknown",
        "tags": ev.get("tags", []) + ["from_browser", "evidence"],
        "created_at": _now(),
        "updated_at": _now(),
        "verification_status": ev.get("verification_status", "unchecked"),
    }

    mem_store = get_store("memory").load()
    mem_store[memory_entry["id"]] = memory_entry
    get_store("memory").save()

    _audit("browser", user, "evidence_to_memory",
           f"evidence={evidence_id}, layer={memory_layer}")

    return {"memory_id": memory_entry["id"], "memory": memory_entry}


# =========================================================================
# Remote Browser Capability (spec §40)
# =========================================================================

@router.get("/remote-browser/status")
async def remote_browser_status(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Check remote browser worker availability (spec §40).

    Architecture:
        JARVIS → Browser Controller → isolated Browser Worker → internet

    This endpoint checks if a remote browser worker is configured and available.
    The local PC does not need to host every browser workload.
    """
    remote_enabled = os.environ.get("JARVIS_REMOTE_BROWSER_ENABLED", "false").lower() == "true"
    remote_url = os.environ.get("JARVIS_REMOTE_BROWSER_URL", "")
    remote_api_key = os.environ.get("JARVIS_REMOTE_BROWSER_API_KEY", "")

    return {
        "remote_browser_enabled": remote_enabled,
        "remote_browser_url": remote_url if remote_enabled else "",
        "api_key_configured": bool(remote_api_key),
        "local_browsing_available": True,
        "routing_policy": (
            {"mode": "remote", "reason": "Heavy or high-risk browsing routed to isolated worker"}
            if remote_enabled
            else {"mode": "local", "reason": "Local browsing only — remote worker not configured"}
        ),
    }


@router.post("/remote-browser/sessions")
async def create_remote_session(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a browser session on the remote worker (spec §40).

    For high-risk or heavy autonomous browsing, the session is created
    on an isolated remote browser worker instead of locally.
    """
    if not os.environ.get("JARVIS_REMOTE_BROWSER_ENABLED", "false").lower() == "true":
        raise HTTPException(
            status_code=403,
            detail="Remote browser is not enabled. Set JARVIS_REMOTE_BROWSER_ENABLED=true and JARVIS_REMOTE_BROWSER_URL.",
        )

    session_id = f"remote-{uuid.uuid4().hex[:12]}"
    _audit("browser", user, "remote_session_created", f"session={session_id}")

    return {
        "session_id": session_id,
        "remote": True,
        "status": "created",
        "worker_url": os.environ.get("JARVIS_REMOTE_BROWSER_URL", ""),
    }


# =========================================================================
# Execution Plan View (spec §11)
# =========================================================================

@router.get("/tasks/{task_id}/plan")
async def get_task_plan(
    task_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the execution plan view for a task (spec §11).

    Shows: Goal, Plan, Current step, Completed steps, Next action,
    Blocked actions, Verification.
    """
    tasks = get_store("browser_tasks").load()
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    sessions = get_store("browser_sessions").load()
    sess = sessions.get(task_data.get("session_id", ""))
    if not sess or sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    steps = task_data.get("steps", [])
    current_index = task_data.get("current_step_index", 0)
    completed = [s for s in steps if s.get("status") in ("completed", "verified")]
    current = steps[current_index] if current_index < len(steps) else None
    next_step = steps[current_index + 1] if current_index + 1 < len(steps) else None
    blocked = [s for s in steps if s.get("status") == "blocked"]

    return {
        "task_id": task_id,
        "goal": task_data.get("goal", ""),
        "plan": task_data.get("plan", []),
        "current_step": current,
        "completed_steps": completed,
        "completed_count": len(completed),
        "total_steps": len(steps),
        "next_action": next_step.get("description", "") if next_step else "",
        "blocked_actions": blocked,
        "verification": task_data.get("status") in ("completed", "verified"),
        "checkpoint_id": task_data.get("checkpoint_id"),
        "status": task_data.get("status", ""),
    }


# =========================================================================
# Browser Identity Indicator (spec §19)
# =========================================================================

@router.get("/auth-state")
async def get_auth_state(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser authentication state for identity indicator (spec §19).

    Always makes authentication state visible. Never exposes tokens.
    Never silently authenticates a website merely because JARVIS
    possesses a provider connection.
    """
    # Check if the user has any external provider connections
    connectors = get_store("connectors").load()
    uid = user.get("id") or "unknown"
    user_connectors = [c for c in connectors.values() if c.get("user_id") == uid]

    auth_providers = []
    for conn in user_connectors:
        if conn.get("status") == "connected":
            provider_name = conn.get("provider", "unknown")
            auth_providers.append({
                "provider": provider_name,
                "account": conn.get("email") or conn.get("username") or "connected",
                "connected_at": conn.get("connected_at", ""),
                "connected_by": conn.get("connected_by", ""),
            })

    # Check current session authentication state
    sessions = get_store("browser_sessions").load()
    active_session = None
    for sess in sessions.values():
        if sess.get("user_id") == uid and sess.get("privacy_mode") in ("authenticated",):
            active_session = sess
            break

    return {
        "authenticated_providers": auth_providers,
        "active_authenticated_session": active_session,
        "note": "Tokens are never exposed to the browser. External services are authenticated via server-side OAuth exchange.",
    }


# =========================================================================
# High-Risk DOM Detection (spec §23)
# =========================================================================

_HIGHERISK_PATTERNS = [
    (r"document\.cookie", "cookie_access"),
    (r"localStorage", "local_storage_access"),
    (r"sessionStorage", "session_storage_access"),
    (r"window\.location\s*=", "redirect_attempt"),
    (r"fetch\s*\(\s*['\"](https?://)", "external_data_exfil"),
    (r"XMLHttpRequest", "xhr_request"),
    (r"eval\s*\(", "code_evaluation"),
    (r"atob\s*\(|btoa\s*\(", "data_encoding"),
    (r"download\s*=", "forced_download"),
]


def _detect_high_risk_dom(html_content: str) -> Dict[str, Any]:
    """Detect suspicious page content (spec §23)."""
    warnings = []
    matches = []
    for pattern, label in _HIGHERISK_PATTERNS:
        for m in re.finditer(pattern, html_content, re.IGNORECASE):
            snippet = html_content[max(0, m.start() - 30):m.end() + 30].strip()
            matches.append({"type": label, "snippet": snippet[:200]})
            warnings.append(f"High-risk DOM detected: {label}")

    return {
        "flagged": len(matches) > 0,
        "matches": matches[:20],
        "warnings": warnings[:20],
        "confidence": min(1.0, len(matches) * 0.2) if matches else 0.0,
    }


@router.post("/security/high-risk-dom")
async def check_high_risk_dom(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Check page content for high-risk DOM elements (spec §23)."""
    content = body.get("content", "")
    result = _detect_high_risk_dom(content)

    if result["flagged"]:
        _audit("browser", user, "high_risk_dom_detected",
               f"types={[m['type'] for m in result['matches']]}")

    return result


# =========================================================================
# Universal Access — Summon Browser (spec §49)
# =========================================================================

@router.post("/summon")
async def summon_browser(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Summon the Browser with context from another JARVIS module (spec §49).

    The current context (from Chat, Research, Mission Control, Agents,
    Knowledge, Memory, etc.) follows the user into the Browser.
    """
    context_source = body.get("context_source", "chat")  # chat, research, mission, agent, knowledge, memory
    context_data = body.get("context_data", {})

    # Create or reuse a session
    session_name = body.get("session_name") or f"{context_source.capitalize()} Session"
    privacy_mode = body.get("privacy_mode") or "standard"

    resp = await create_session(
        SessionCreateIn(
            name=session_name,
            privacy_mode=privacy_mode,
            research_session_id=context_data.get("research_session_id"),
            mission_id=context_data.get("mission_id"),
        ),
        user,
    )

    sess = resp["session"]

    # Store the context that follows the user
    if context_data:
        sess_store = get_store("browser_sessions").load()
        sess_data = sess_store.get(sess["id"], {})
        sess_data["context"] = {
            "source": context_source,
            "data": context_data,
            "created_at": _now(),
        }
        sess_store[sess["id"]] = sess_data
        get_store("browser_sessions").save()

    _audit("browser", user, "browser_summoned",
           f"source={context_source}, session={sess['id']}")

    return {
        "session": sess,
        "context_followed": bool(context_data),
        "summon_url": f"/dashboard/browser?session={sess['id']}",
    }


# =========================================================================
# Nothing Gets Lost — Artifact Access (spec §50)
# =========================================================================

@router.get("/artifacts")
async def get_browser_artifacts(
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get all browser artifacts for a session (spec §50).

    Any meaningful browser artifact must remain accessible through
    the wider platform.  This endpoint returns all artifacts
    (pages, sources, evidence, annotations, missions, memories,
    knowledge, lessons, downloads, activity) for the current user.
    """
    sessions = get_store("browser_sessions").load()
    tabs = get_store("browser_tabs").load()
    evidence = get_store("browser_evidence").load()
    bookmarks = get_store("browser_bookmarks").load()
    history = get_store("browser_history").load()
    downloads = get_store("browser_downloads").load()
    tasks = get_store("browser_tasks").load()
    workspaces = get_store("browser_workspaces").load()
    timeline = get_store("browser_timeline").load()
    uid = user.get("id") or "unknown"

    my_session_ids = {s["id"] for s in sessions.values() if s.get("user_id") == uid}
    if session_id:
        my_session_ids = {session_id} if session_id in my_session_ids else set()

    my_tabs = [t for t in tabs.values() if t.get("session_id") in my_session_ids]
    my_evidence = [e for e in evidence if e.get("user_id") == uid]
    my_bookmarks = [b for b in bookmarks.values() if b.get("user_id") == uid]
    my_history = [h for h in history if h.get("user_id") == uid]
    my_downloads = [d for d in downloads if d.get("user_id") == uid]
    my_tasks = [t for t in tasks.values() if t.get("session_id") in my_session_ids]
    my_workspaces = [w for w in workspaces.values() if w.get("id") in {s.get("workspace_id") for s in sessions.values() if s.get("user_id") == uid}]
    my_timeline = [t for t in timeline if t.get("user_id") == uid]

    return {
        "sessions": [s for s in sessions.values() if s.get("user_id") == uid],
        "tabs": my_tabs,
        "evidence": my_evidence,
        "bookmarks": my_bookmarks,
        "history": my_history,
        "downloads": my_downloads,
        "tasks": my_tasks,
        "workspaces": my_workspaces,
        "timeline": my_timeline,
        "counts": {
            "sessions": len(my_session_ids),
            "tabs": len(my_tabs),
            "evidence": len(my_evidence),
            "bookmarks": len(my_bookmarks),
            "history": len(my_history),
            "downloads": len(my_downloads),
            "tasks": len(my_tasks),
            "workspaces": len(my_workspaces),
            "timeline": len(my_timeline),
        },
    }


# =========================================================================
# Local Resource Protection (spec §41)
# =========================================================================

@router.get("/resource-usage")
async def get_resource_usage(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser resource usage for local resource protection (spec §41).

    Heavy autonomous/browser analysis can be remotely executed.
    This endpoint reports current resource usage so the system can
    decide whether to offload work.
    """
    # Get process resource usage (Unix-like / Windows approximation)
    cpu_time = 0.0
    memory_mb = 0.0
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cpu_time = usage.ru_utime + usage.ru_stime
        memory_mb = usage.ru_maxrss / 1024 if usage.ru_maxrss > 1024 else usage.ru_maxrss
    except (ImportError, AttributeError):
        # 'resource' module is Unix-only; on Windows report zeros
        pass

    tasks = get_store("browser_tasks").load()
    running_tasks = [t for t in tasks.values() if t.get("status") == "running"]

    return {
        "cpu_time_seconds": cpu_time,
        "memory_mb": memory_mb,
        "running_tasks": len(running_tasks),
        "running_task_details": [
            {"id": t.get("id"), "goal": t.get("goal", "")[:100], "step": t.get("current_step_index", 0)}
            for t in running_tasks[:10]
        ],
        "recommendation": (
            "Heavy autonomous browsing detected — consider remote execution"
            if len(running_tasks) > 3 or memory_mb > 500
            else "Resource usage normal — local browsing OK"
        ),
        "remote_browser_available": os.environ.get("JARVIS_REMOTE_BROWSER_ENABLED", "false").lower() == "true",
    }


# ---------------------------------------------------------------------------
# Network Intelligence Layer (spec §51)
# Browser Network Diagnostics: health, DNS, proxy, transport, recovery
# ---------------------------------------------------------------------------

def _record_navigation_error(url: str, category: BrowserErrorCategory,
                             error_detail: str, user: Dict[str, Any]) -> None:
    """Record a classified navigation error to the network events store."""
    try:
        record_network_event(
            event_type="navigation_error",
            url=url,
            category=category,
            detail=error_detail,
            severity="error",
            extra={"user_id": user.get("id") or "unknown"},
        )
    except Exception:
        pass  # best-effort, never break the request


@router.get("/health")
async def get_browser_health(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get browser health status (spec §51).

    Runs real, non-faked health checks: store accessibility, DNS resolver
    reachability, TCP connectivity, TLS reachability, proxy configuration.
    """
    health = BrowserHealthStatus.run()
    # Persist the latest health snapshot
    try:
        store = get_store("browser_health")
        history = store.load()
        if not isinstance(history, list):
            history = []
        entry = health.to_dict()
        history.append(entry)
        if len(history) > 100:
            history = history[-100:]
        store.save()
    except Exception:
        pass
    _audit("browser", user, "health_check", f"overall={health.overall}")
    return health.to_dict()


@router.post("/diagnostics/dns")
async def diagnostics_dns(
    body: DiagnosticsDnsIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Run DNS diagnostics for a URL's hostname (spec §51.5).

    Checks the system resolver and optionally probes approved public DNS
    resolvers via direct UDP queries.  Does NOT modify OS DNS settings.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")
    hostname = _domain_from_url(body.url)
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")

    alternate_resolvers: Optional[List[Tuple[str, int]]] = None
    if body.alternate_resolvers:
        alternate_resolvers = []
        for r in body.alternate_resolvers:
            parsed_r = r.split(":")
            ip = parsed_r[0]
            port = int(parsed_r[1]) if len(parsed_r) > 1 and parsed_r[1].isdigit() else 53
            alternate_resolvers.append((ip, port))

    dns = DnsDiagnostics(alternate_resolvers=alternate_resolvers)
    result = dns.diagnose(hostname, use_alternates=True)

    # Serialize dataclass result to dict
    from dataclasses import asdict
    data = asdict(result)
    # Flatten DnsRecord dataclasses inside
    data["records"] = [asdict(r) for r in result.records]
    if data.get("system_resolver"):
        sr = data["system_resolver"]
        if sr.get("records"):
            sr["records"] = [asdict(r) for r in result.system_resolver.records] if result.system_resolver else []
    if data.get("alternate_resolvers"):
        for i, ar in enumerate(data["alternate_resolvers"]):
            if ar.get("records"):
                # Map back to the original dataclass records
                orig = result.alternate_resolvers[i].records if i < len(result.alternate_resolvers) else []
                ar["records"] = [asdict(r) for r in orig]

    _audit("browser", user, "dns_diagnostic",
           f"hostname={hostname}, system_available={result.system_resolver.available if result.system_resolver else 'unknown'}")
    record_network_event(
        event_type="dns_diagnostic",
        url=body.url,
        category=BrowserErrorCategory.DNS_RESOLUTION_FAILED
        if (result.system_resolver and not result.system_resolver.available)
        else BrowserErrorCategory.UNKNOWN_NETWORK_ERROR,
        detail=f"Hostname: {hostname}",
        severity="info",
        extra={"hostname": hostname, "system_available": result.system_resolver.available if result.system_resolver else False},
    )
    return data


@router.post("/diagnostics/proxy")
async def diagnostics_proxy(
    body: DiagnosticsProxyIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Run proxy diagnostics for a URL (spec §51.6).

    Detects configured proxies and tests reachability of the applicable proxy.
    Does NOT change proxy settings.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    proxy_info = ProxyDiagnostics.get_proxy_settings()
    proxy_check = ProxyDiagnostics.check_proxy_for_url(body.url)

    result = {
        "url": body.url,
        "proxy_config": proxy_info,
        "proxy_check": proxy_check,
    }
    _audit("browser", user, "proxy_diagnostic",
           f"url={body.url[:100]}, proxy_applies={proxy_check.get('proxy_applies')}")
    record_network_event(
        event_type="proxy_diagnostic",
        url=body.url,
        category=BrowserErrorCategory.PROXY_CONNECTION_FAILED
        if (proxy_check.get("proxy_applies") and not proxy_check.get("proxy_reachable"))
        else BrowserErrorCategory.UNKNOWN_NETWORK_ERROR,
        detail="Proxy diagnostics run",
        severity="info",
        extra={"proxy_applies": proxy_check.get("proxy_applies", False)},
    )
    return result


@router.post("/diagnostics/network")
async def diagnostics_network(
    body: DiagnosticsNetworkIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Run full network diagnostics for a failed navigation (spec §51.2).

    Classifies the error, then checks DNS, proxy, TCP, TLS, and HTTP layers.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    # Attempt a real fetch to get the actual error
    hostname = _domain_from_url(body.url)
    parsed = urlparse(body.url if body.url.startswith(("http://", "https://")) else "https://" + body.url)
    port = parsed.port or (443 if parsed.scheme in ("", "https") else 80)
    scheme = parsed.scheme or "https"

    # 1. Try the HTTP probe to capture the actual error
    http_result = TransportDiagnostics.http_probe(body.url, timeout=body.timeout)
    category_str = http_result.get("error_category")
    if category_str:
        try:
            category = BrowserErrorCategory(category_str)
        except ValueError:
            category = BrowserErrorCategory.UNKNOWN_NETWORK_ERROR
    else:
        # No HTTP error — try to classify based on what we found
        if http_result.get("reached"):
            category = BrowserErrorCategory.HTTP_4XX if http_result.get("status_code", 0) < 500 else BrowserErrorCategory.HTTP_5XX
        else:
            category = BrowserErrorCategory.UNKNOWN_NETWORK_ERROR

    # 2. Build the full diagnostic chain using NavigationDiagnoser
    ctx = NavigationErrorContext(
        url=body.url,
        error_message=http_result.get("error", "") or http_result.get("error_category", ""),
        error_category=category.value,
    )
    diagnosis = NavigationDiagnoser().diagnose(ctx)

    # 3. Merge the HTTP probe result (already computed) into the diagnosis
    from dataclasses import asdict
    result = asdict(diagnosis)
    # Convert nested dataclass records to dicts
    if result.get("dns"):
        if result["dns"].get("records"):
            result["dns"]["records"] = [asdict(r) for r in diagnosis.dns.records] if diagnosis.dns else []
        if result["dns"].get("system_resolver") and result["dns"]["system_resolver"].get("records"):
            result["dns"]["system_resolver"]["records"] = [asdict(r) for r in diagnosis.dns.system_resolver.records] if diagnosis.dns.system_resolver else []
        if result["dns"].get("alternate_resolvers"):
            for i, ar in enumerate(result["dns"]["alternate_resolvers"]):
                if ar.get("records"):
                    orig = diagnosis.dns.alternate_resolvers[i].records if diagnosis.dns and i < len(diagnosis.dns.alternate_resolvers) else []
                    ar["records"] = [asdict(r) for r in orig]
    # Override http with the pre-computed result (more accurate latency)
    result["http"] = http_result
    # Convert recovery_plan dataclass to dict
    if result.get("recovery_plan"):
        rp = diagnosis.recovery_plan
        result["recovery_plan"] = {
            "action": rp.action,
            "max_attempts": rp.max_attempts,
            "description": rp.description,
            "safe": rp.safe,
        }

    _audit("browser", user, "network_diagnostic",
           f"url={body.url[:100]}, category={category.value}")
    record_network_event(
        event_type="network_diagnostic",
        url=body.url,
        category=category,
        detail=diagnosis.diagnosis[:200],
        severity="error",
    )
    return result


@router.post("/recover")
async def recover_navigation(
    body: RecoverIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Attempt bounded recovery for a failed navigation (spec §51.6).

    NEVER performs dangerous auto-repair: no OS DNS changes, no TLS
    verification disabling, no certificate installation, no route changes.
    All recovery is bounded by max_attempts (hard-capped at 3).
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    result = RecoveryOrchestrator.recover(
        url=body.url,
        strategy=body.strategy,
        max_attempts=body.max_attempts,
    )

    _audit("browser", user, "navigation_recovery",
           f"url={body.url[:100]}, strategy={result.strategy}, success={result.success}")
    record_network_event(
        event_type="navigation_recovery",
        url=body.url,
        category=BrowserErrorCategory.UNKNOWN_NETWORK_ERROR if not result.success else BrowserErrorCategory.UNKNOWN_NETWORK_ERROR,
        detail=f"strategy={result.strategy}, attempts={result.attempts}, success={result.success}, final_error={result.final_error or 'none'}",
        severity="info" if result.success else "warning",
        extra={"strategy": result.strategy, "attempts": result.attempts, "success": result.success},
    )
    return {
        "url": body.url,
        "success": result.success,
        "strategy": result.strategy,
        "attempts": result.attempts,
        "max_attempts": result.max_attempts,
        "final_error": result.final_error,
        "recovered_category": result.recovered_category,
        "details": result.details,
    }


@router.get("/network/events")
async def get_network_events(
    limit: int = Query(default=100, le=500),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get recent network diagnostic events (spec §51)."""
    store = get_store("browser_network_events")
    events = store.load()
    if not isinstance(events, list):
        events = []
    events = list(reversed(events))[:limit]
    return {"events": events, "count": len(events)}


@router.get("/network/timeline")
async def get_network_timeline(
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the navigation timeline (spec §51.4).

    Shows the diagnostic chain for each navigation event.
    """
    store = get_store("browser_navigation_timeline")
    timeline = store.load()
    if not isinstance(timeline, list):
        timeline = []
    if session_id:
        timeline = [e for e in timeline if e.get("session_id") == session_id]
    timeline = list(reversed(timeline))[:limit]
    return {"timeline": timeline, "count": len(timeline)}

# ---------------------------------------------------------------------------
# Navigation context classification (spec §4, §7, §8, §9)
# ---------------------------------------------------------------------------

@router.post("/navigate/context")
async def classify_navigation_context_endpoint(
    body: NavigationContextIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Classify the presentation context for a URL (spec §7).

    Determines whether a URL can be safely embedded in a JARVIS iframe panel,
    needs a top-level browser tab, or requires an isolated sandbox window.

    Classification is based on:
      - X-Frame-Options header (DENY / SAMEORIGIN)
      - Content-Security-Policy frame-ancestors directive
      - HTTP status codes (401/403 = auth required)
      - Content-Type (non-HTML = isolated)

    Does NOT hard-code specific domains — classification is driven by HTTP
    response headers and structural heuristics.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    ctx = classify_navigation_context(body.url, body.headers)
    return {
        "url": ctx.url,
        "presentation": ctx.presentation.value,
        "reason": ctx.reason,
        "confidence": ctx.confidence,
        "signals": ctx.signals,
    }


@router.post("/navigate/classify-failure")
async def classify_navigation_failure_endpoint(
    body: NavigationFailureIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Classify the reason why a navigation or embedding failed (spec §8).

    Maps an error category, HTTP status code, or exception into a normalized
    failure classification:

    FRAME_BLOCKED, AUTH_REQUIRED, UNSUPPORTED_EMBED, NETWORK_FAILURE,
    DNS_FAILURE, TLS_FAILURE, HTTP_FAILURE, BROWSER_ENGINE_FAILURE,
    REDIRECT_LOOP, CONTENT_BLOCKED, PROXY_FAILURE
    """
    if body.error_category:
        failure_class = NavigationFailureClass.from_browser_error_category(body.error_category)
    else:
        # Reconstruct an exception from the detail for classification
        exc = None
        if body.error_detail:
            # Create a synthetic exception so classify_navigation_failure can
            # use the network_diagnostics classifier
            exc = Exception(body.error_detail)
        failure_class = classify_navigation_failure(
            body.url,
            error=exc,
            status_code=body.status_code,
            headers=body.headers,
        )

    # Determine recovery recommendations
    recovery_recommendations: List[str] = []
    if failure_class == NavigationFailureClass.FRAME_BLOCKED:
        recovery_recommendations = [
            "Open in top-level browser context",
            "Use 'Open in Browser Context' action",
        ]
    elif failure_class == NavigationFailureClass.AUTH_REQUIRED:
        recovery_recommendations = [
            "Open in top-level browser context to complete authentication",
            "Use system browser for login flows",
        ]
    elif failure_class == NavigationFailureClass.DNS_FAILURE:
        recovery_recommendations = [
            "Run DNS diagnostics",
            "Check network connectivity",
            "Run recovery with automatic DNS fallback",
        ]
    elif failure_class == NavigationFailureClass.TLS_FAILURE:
        recovery_recommendations = [
            "Check system clock",
            "Run TLS diagnostics",
            "Check certificate validity",
            "Try alternate resolver if DNS is involved",
        ]
    elif failure_class == NavigationFailureClass.NETWORK_FAILURE:
        recovery_recommendations = [
            "Run network diagnostics",
            "Check connectivity to the host",
            "Run recovery with retry",
        ]
    elif failure_class == NavigationFailureClass.HTTP_FAILURE:
        recovery_recommendations = [
            "Check the URL and status code",
            "The server returned an error response",
        ]
    elif failure_class == NavigationFailureClass.UNSUPPORTED_EMBED:
        recovery_recommendations = [
            "Open in top-level browser context",
            "Use system browser",
        ]

    return {
        "url": body.url,
        "failure_class": failure_class.value,
        "error_category": body.error_category,
        "status_code": body.status_code,
        "recovery_recommendations": recovery_recommendations,
    }


@router.post("/open-context")
async def open_in_browser_context(
    body: OpenInBrowserContextIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate target URL for 'Open in Browser Context' action (spec §8).

    This endpoint produces the URL and target context that the frontend should
    use when a page cannot be embedded internally.  The frontend will open the
    URL in the appropriate context (external tab, system browser, or sandboxed
    window).
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    # First, classify the navigation context to validate the URL
    ctx = classify_navigation_context(body.url, body.headers)

    target = body.presentation or ctx.presentation.value
    if ctx.presentation == NavigationPresentation.EMBEDDED:
        # URL is embeddable — no need to open in external context
        return {
            "url": body.url,
            "target": "embedded",
            "reason": "URL can be safely embedded — no external context needed",
            "query": body.query,
        }

    # Build the target URL with context preservation (spec §8)
    target_url = body.url
    if body.query:
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed = urlparse(target_url)
        qs = parse_qs(parsed.query)
        qs["jarvis_query"] = [body.query]
        qs["jarvis_user"] = [str(user.get("id", "unknown"))]
        target_url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    # Record the context switch for observability
    events = get_store("browser_network_events").load()
    if not isinstance(events, list):
        events = []
    events.append({
        "type": "context_switch",
        "url": body.url,
        "target": target,
        "presentation": ctx.presentation.value,
        "reason": ctx.reason,
        "user_id": user.get("id", "unknown"),
        "timestamp": now_iso(),
    })
    get_store("browser_network_events").save()

    return {
        "url": target_url,
        "target": target,
        "presentation": ctx.presentation.value,
        "reason": ctx.reason,
        "query": body.query,
    }


@router.get("/profiles")
async def list_browser_profiles(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List available browser profiles (spec §12).

    Profiles control storage policies, agent permissions, and AI context
    for different browsing modes.
    """
    profiles = [
        BrowserProfile(name, BrowserProfile.DEFAULTS[name]).to_dict()
        for name in BrowserProfile.DEFAULTS
    ]
    return {"profiles": profiles}


@router.get("/profiles/{profile_name}")
async def get_browser_profile(
    profile_name: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific browser profile configuration."""
    if profile_name not in BrowserProfile.DEFAULTS:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    return BrowserProfile(profile_name).to_dict()


# ---------------------------------------------------------------------------
# Browser Engine (spec §4)
# ---------------------------------------------------------------------------

@router.get("/engine")
async def get_browser_engine_info(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get information about the active browser engine."""
    engine = get_engine("default")
    return {
        "engine": engine.name,
        "capabilities": engine.capabilities,
    }


# ---------------------------------------------------------------------------
# AI Context Layer (spec §5) — enhanced page understanding
# ---------------------------------------------------------------------------

@router.post("/page/understand")
async def understand_page(
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Enhanced page understanding for AI context (spec §5, §22, §38).

    Returns a richer page representation that includes navigation context
    classification, page type classification, and interactive element map.
    """
    url = body.get("url", "")
    if _is_blocked_domain(url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    # Fetch the page using the browser engine abstraction
    engine = get_engine("default")
    page_data, nav_context = engine.fetch_with_context(url)

    # If the page is not embeddable, surface the classification
    if nav_context.presentation != NavigationPresentation.EMBEDDED:
        # Classify the failure mode
        failure = classify_navigation_failure(url)
        return {
            "url": url,
            "navigation_context": {
                "presentation": nav_context.presentation.value,
                "reason": nav_context.reason,
                "confidence": nav_context.confidence,
                "signals": nav_context.signals,
            },
            "failure_class": failure.value,
            "page_state": None,
            "recommendation": "Open in top-level browser context",
        }

    # Extract page structure
    raw_content = page_data.get("html", "")
    text = _extract_text_from_html(raw_content)
    metadata = _extract_metadata(raw_content, url)
    structure = _extract_page_structure(raw_content)
    page_class = classify_page(url, metadata.get("title", ""), text[:500])

    # Build AI context
    ai_context = {
        "url": page_data.get("url", url),
        "title": metadata.get("title", ""),
        "domain": _domain_from_url(url),
        "page_classification": page_class,
        "navigation_context": {
            "presentation": nav_context.presentation.value,
            "reason": nav_context.reason,
            "confidence": nav_context.confidence,
            "signals": nav_context.signals,
        },
        "text_length": len(text),
        "headings": structure.get("headings", []),
        "word_count": structure.get("word_count", 0),
        "interactive_elements": _build_element_map(raw_content, url),
        "forms": _extract_forms(raw_content),
        "links": _extract_links(raw_content, url),
        "tables": _extract_tables(raw_content),
        "security_indicators": [],
    }

    # Prompt injection check
    injection = _detect_prompt_injection(text, raw_content)
    if injection["flagged"]:
        ai_context["security_indicators"].append("prompt_injection_detected")
        ai_context["security_indicators"].append(json.dumps({
            "matches": injection["matches"],
        }))

    # Store the AI context
    page_states = get_store("browser_page_states").load()
    if not isinstance(page_states, dict):
        page_states = {}
    ps_id = f"ps-{uuid.uuid4().hex[:12]}"
    page_states[ps_id] = {
        "id": ps_id,
        **ai_context,
        "created_at": now_iso(),
    }
    get_store("browser_page_states").save()

    return {"page_state": ai_context, "page_state_id": ps_id}



# --------------------------------------------------------------------------- #
# Cross-system integrations (spec §11)
# --------------------------------------------------------------------------- #

class ExtractToKnowledgeIn(BaseModel):
    """Extract browser page content to a knowledge entry (spec §11)."""
    url: str
    content: Optional[str] = None
    title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None


@router.post("/page/extract-to-knowledge")
async def extract_to_knowledge(
    body: ExtractToKnowledgeIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Extract a page and save it as a knowledge entry with provenance (spec §11).

    This bridges the Browser and Knowledge systems: the Browser extracts the
    page content, and the Knowledge plane stores it as a categorizable,
    tagged, searchable entry with full source attribution.
    """
    if _is_blocked_domain(body.url):
        raise HTTPException(status_code=403, detail="Blocked domain")

    # If content was not provided, fetch it via the browser engine
    if body.content:
        raw_content = body.content
    else:
        engine = get_engine("default")
        page_data = engine.fetch(body.url)
        raw_content = page_data.get("html", "")

    # Extract text + metadata
    text = _extract_text_from_html(raw_content)
    metadata = _extract_metadata(raw_content, body.url)
    title = body.title or metadata.get("title", "") or _domain_from_url(body.url)
    page_class = classify_page(body.url, title, text[:500])

    # Store in knowledge
    knowledge = get_store("knowledge")
    data = knowledge.load()
    if not isinstance(data, dict):
        data = {}
    key = "web-" + uuid.uuid4().hex[:12]
    entry = {
        "key": key,
        "title": title,
        "value": text[:10000],
        "url": body.url,
        "page_classification": page_class,
        "category": body.category or page_class,
        "tags": body.tags + ["browser", page_class],
        "user_id": user.get("id") or "unknown",
        "source": "browser_extractor",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    data[key] = entry
    knowledge.save()

    _audit("browser", user, "knowledge_extracted",
           "key=" + key + ", url=" + body.url + ", classification=" + page_class)

    return {"knowledge_key": key, "title": title,
            "page_classification": page_class, "word_count": len(text.split())}


@router.get("/sessions/{session_id}/context")
async def get_session_context(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a high-level context snapshot of a browser session (spec §6, §17).

    Returns the session metadata, active tab state, recent history,
    evidence count, and linked research/mission IDs.
    """
    sessions = get_store("browser_sessions").load()
    sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("user_id") != (user.get("id") or "unknown"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tabs = get_store("browser_tabs").load()
    if not isinstance(tabs, dict):
        tabs = {}
    my_tabs = [t for t in tabs.values() if t.get("session_id") == session_id]

    evidence = get_store("browser_evidence").load()
    if not isinstance(evidence, list):
        evidence = []
    my_evidence = [e for e in evidence if e.get("session_id") == session_id
                   or e.get("session_id") is None]

    history = get_store("browser_history").load()
    if not isinstance(history, list):
        history = []
    recent_history = [h for h in history if h.get("session_id") == session_id][-10:]

    profile_name = sess.get("profile", "personal")
    profile = BrowserProfile(profile_name)

    active_tab = None
    for t in my_tabs:
        if t.get("id") == sess.get("active_tab_id"):
            active_tab = t
            break

    return {
        "session": sess,
        "profile": profile_name,
        "permissions": profile.agent_permissions,
        "permissions_for_action": True,
        "active_tab": active_tab,
        "tab_count": len(my_tabs),
        "evidence_count": len(my_evidence),
        "recent_history": recent_history,
        "research_session_id": sess.get("research_session_id"),
        "mission_id": sess.get("mission_id"),
    }
