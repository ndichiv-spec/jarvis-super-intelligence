"""Extensions marketplace: install, list, manage plugins and extensions.

The marketplace catalog (``_default_extensions``) is a *code-defined* set of
extensions — each one wires into a website/service (GitHub, Docker, Claude,
OpenCode, AWS, Slack, …) and maps to concrete capability tokens the AI can
request. Browsing the catalog, listing installed extensions and reading
capabilities is **public** (no session required) so the Extensions page loads
for everyone; installing / enabling / uninstalling / connecting remain
admin-gated. Each installed extension persists its own connection state in
Jarvis's KV storage (its own "storage space").

Flow: ``install`` (creates a needs-connection record in KV) → ``launch``
(returns the service authorize/config URL so the user can grant access) →
``connect`` (acknowledge: marks the connection persisted in Jarvis storage) →
optionally ``disable``/``uninstall``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import json
import time
import hmac
import hashlib
import base64
import httpx
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from ..core import get_current_user, get_optional_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/extensions", tags=["extensions"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ExtensionInstallIn(BaseModel):
    extension_id: str
    config: Dict[str, Any] = {}


class ExtensionUninstallIn(BaseModel):
    extension_id: str


class ExtensionUpdateIn(BaseModel):
    # ``extension_id`` is carried in the URL path; kept optional in the body for
    # backward compatibility but ignored by the handler.
    extension_id: Optional[str] = None
    config: Dict[str, Any] = {}
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Catalog + logos
# ---------------------------------------------------------------------------
def _logo(ext_id: str) -> str:
    """Real favicon/logo URL served by Google's favicon proxy — the logo as it
    appears on the service's own site. Empty for Jarvis-internal concepts, in
    which case the UI falls back to the emoji ``icon``."""
    domain = _LOGO_DOMAINS.get(ext_id)
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


_LOGO_DOMAINS: Dict[str, str] = {
    "claude": "anthropic.com", "openai": "openai.com", "gemini": "google.com",
    "whisper": "huggingface.co", "stablediffusion": "huggingface.co",
    "github": "github.com", "gitlab": "gitlab.com", "opencode": "opencode.so",
    "cursor": "cursor.so", "vscode": "code.visualstudio.com", "docker": "docker.com",
    "kubernetes": "kubernetes.io", "terraform": "hashicorp.com", "ansible": "ansible.com",
    "jenkins": "jenkins.io", "aws": "aws.amazon.com", "gcp": "cloud.google.com",
    "azure": "azure.microsoft.com", "supabase": "supabase.com", "vultr": "vultr.com",
    "postgres": "postgresql.org", "redis": "redis.io", "mongodb": "mongodb.com",
    "elasticsearch": "elastic.co", "slack": "slack.com", "discord": "discord.com",
    "telegram": "telegram.org", "whatsapp": "whatsapp.com", "google-workspace": "google.com",
    "translate": "cloud.google.com", "calendar": "calendar.google.com",
    "notion": "notion.so", "linear": "linear.app", "jira": "atlassian.com",
    "trello": "trello.com", "figma": "figma.com", "canva": "canva.com",
    "wikipedia": "wikipedia.org", "brave-search": "brave.com", "arxiv": "arxiv.org",
    "exa": "exa.ai", "youtube": "youtube.com", "stripe": "stripe.com",
    "paypal": "paypal.com", "shopify": "shopify.com", "ssh": "openssh.com",
}


def _e(ext_id: str, name: str, desc: str, category: str, icon: str) -> Dict[str, Any]:
    return {
        "id": ext_id, "name": name, "desc": desc,
        "category": category, "icon": icon,
        "logo": _logo(ext_id),
        "installed": False, "enabled": False,
    }


def _rows():
    """(id, name, desc, category, icon) tuples for the full marketplace."""
    return [
        # Core
        ("memory", "Persistent Memory Bank", "Long-term agent memory with vector retrieval", "core", "🧠"),
        ("knowledge", "Knowledge Graph", "Persisted knowledge bases and vector stores", "core", "🔗"),
        ("scheduler", "Task Scheduler", "Cron schedules and recurring agent tasks", "core", "⏰"),
        ("voice", "Voice Interface", "Voice input, wake-word and speech output", "core", "🎙️"),
        ("monitoring", "System Monitor", "Host metrics, logs and process inspection", "core", "📈"),
        # AI
        ("claude", "Claude (Anthropic)", "Chat and analyze with Claude via API", "ai", "🤖"),
        ("openai", "OpenAI", "GPT chat, embeddings and image generation", "ai", "🧠"),
        ("gemini", "Google Gemini", "Gemini chat and content generation", "ai", "☄️"),
        ("nvidia", "NVIDIA NIM", "OpenAI-compatible hosted inference (NIM)", "ai", "🟢"),
        ("codemuse", "CodeMuse", "AI code understanding, review and Q&A", "ai", "👁️"),
        ("whisper", "Whisper STT", "Speech-to-text transcription", "ai", "🎤"),
        ("stablediffusion", "Stable Diffusion", "AI image generation", "ai", "🎨"),
        # Development
        ("github", "GitHub", "Repos, pull requests and issues", "development", "🐙"),
        ("gitlab", "GitLab", "Repos, pipelines and issues", "development", "🦊"),
        ("opencode", "OpenCode", "Run OpenCode agents and CLI tasks", "development", "🅾️"),
        ("cursor", "Cursor IDE", "Cursor IDE integration", "development", "🖱️"),
        ("vscode", "VS Code Server", "Remote VS Code tasks and terminals", "development", "🟦"),
        ("docker", "Docker", "Images, containers and builds", "development", "🐳"),
        ("webhooks", "Webhook Manager", "Create webhook endpoints and listeners", "development", "🔗"),
        # DevOps / Cloud / Infra
        ("kubernetes", "Kubernetes", "Pods, deploys and cluster logs", "devops", "☸️"),
        ("terraform", "Terraform", "Plan and apply infrastructure as code", "devops", "🧱"),
        ("ansible", "Ansible", "Run playbooks and manage inventory", "devops", "🎛️"),
        ("jenkins", "Jenkins", "Jobs and build triggers", "devops", "🛠️"),
        ("aws", "AWS", "List and provision AWS resources", "cloud", "☁️"),
        ("gcp", "Google Cloud", "List and provision GCP resources", "cloud", "🌥️"),
        ("azure", "Azure", "List and provision Azure resources", "cloud", "🔷"),
        ("supabase", "Supabase", "Database and auth via Supabase", "cloud", "🛡️"),
        ("vultr", "Vultr", "Instances and bare-metal provisioning", "cloud", "⚡"),
        # Data / Storage
        ("database", "Database (Generic)", "Query and manage SQL/NoSQL stores", "data", "🗄️"),
        ("postgres", "PostgreSQL", "Query and write PostgreSQL databases", "data", "🐘"),
        ("redis", "Redis", "Key/value access and pub/sub", "data", "🔴"),
        ("mongodb", "MongoDB", "Document queries and writes", "data", "🍃"),
        ("elasticsearch", "Elasticsearch", "Search and index management", "data", "🔍"),
        ("analytics", "Analytics Dashboard", "Track AI usage and metrics", "data", "📊"),
        # Communication
        ("slack", "Slack", "Send and receive Slack messages", "communication", "💬"),
        ("discord", "Discord", "Discord channels and messages", "communication", "🎮"),
        ("telegram", "Telegram", "Telegram bots and messages", "communication", "📱"),
        ("whatsapp", "WhatsApp", "Send and read WhatsApp messages", "communication", "💚"),
        ("google-workspace", "Google Workspace", "Gmail, Drive, Calendar and Sheets", "communication", "🌐"),
        ("translate", "Translation Engine", "Translate 100+ languages in place", "communication", "🌍"),
        # Productivity / Design
        ("calendar", "Calendar Sync", "Sync events and schedules", "productivity", "📅"),
        ("files", "Cloud Files", "Access cloud storage drives", "productivity", "☁️"),
        ("notion", "Notion", "Pages and databases in Notion", "productivity", "📝"),
        ("linear", "Linear", "Issues and cycles", "productivity", "📈"),
        ("jira", "Jira", "Tickets and boards", "productivity", "🎫"),
        ("trello", "Trello", "Cards and boards", "productivity", "📌"),
        ("figma", "Figma", "Read and update Figma design files", "design", "🎨"),
        ("canva", "Canva", "Design generation and export", "design", "🖼️"),
        ("slack-sync", "Slack Sync", "Two-way Slack conversation sync", "productivity", "💬"),
        # Research
        ("wikipedia", "Wikipedia", "Search and summarize Wikipedia", "research", "📚"),
        ("brave-search", "Brave Search", "Web search and page fetch", "research", "🔍"),
        ("arxiv", "arXiv", "Academic paper search and digest", "research", "📄"),
        ("exa", "Exa", "AI-powered deep-web research", "research", "🔬"),
        ("youtube", "YouTube", "Search video and fetch captions", "research", "📺"),
        # Commerce
        ("stripe", "Stripe", "Charges and customer data", "commerce", "💳"),
        ("paypal", "PayPal", "Transactions and payments", "commerce", "🅿️"),
        ("shopify", "Shopify", "Products and orders", "commerce", "🛒"),
        # System
        ("ssh", "SSH / Remote Shell", "Remote shell execution and tunnels", "system", "🖥️"),
        ("terminal", "Local Terminal", "Local shell tasks and scripts", "system", "💻"),
        ("process", "Process Manager", "List and inspect host processes", "system", "⚙️"),
    ]


def _default_extensions() -> Dict[str, Dict[str, Any]]:
    ext = {}
    for row in _rows():
        ext[row[0]] = _e(*row)
    return ext


# Real, public-facing URL for each external service's own web interface — the
# page the user opens to confirm / grant JARVIS access. External services
# resolve here so pressing Connect opens *that* app (not a Jarvis settings
# page). Extensions not listed here are internal/local (memory, database,
# terminal, …) and have no external UI, so ``_launch_url`` falls back to the
# scoped Jarvis settings deep-link.
_CONNECT_URLS: Dict[str, str] = {
    "claude": "https://claude.ai/login",
    "openai": "https://platform.openai.com/",
    "gemini": "https://gemini.google.com/",
    "codemuse": "https://codemuse.io/",
    "whisper": "https://huggingface.co/",
    "stablediffusion": "https://huggingface.co/",
    "github": "https://github.com/login",
    "gitlab": "https://gitlab.com/",
    "opencode": "https://opencode.so/",
    "cursor": "https://cursor.sh/",
    "vscode": "https://code.visualstudio.com/",
    "docker": "https://hub.docker.com/",
    "kubernetes": "https://kubernetes.io/",
    "terraform": "https://developer.hashicorp.com/terraform",
    "ansible": "https://www.ansible.com/",
    "jenkins": "https://www.jenkins.io/",
    "aws": "https://console.aws.amazon.com/",
    "gcp": "https://console.cloud.google.com/",
    "azure": "https://portal.azure.com/",
    "supabase": "https://supabase.com/",
    "vultr": "https://www.vultr.com/",
    "postgres": "https://www.postgresql.org/",
    "redis": "https://redis.io/",
    "mongodb": "https://www.mongodb.com/",
    "elasticsearch": "https://www.elastic.co/",
    "slack": "https://slack.com/",
    "discord": "https://discord.com/",
    "telegram": "https://web.telegram.org/",
    "whatsapp": "https://web.whatsapp.com/",
    "google-workspace": "https://workspace.google.com/",
    "translate": "https://translate.google.com/",
    "calendar": "https://calendar.google.com/",
    "notion": "https://www.notion.so/",
    "linear": "https://linear.app/",
    "jira": "https://www.atlassian.com/software/jira",
    "trello": "https://trello.com/",
    "figma": "https://www.figma.com/",
    "canva": "https://www.canva.com/",
    "wikipedia": "https://www.wikipedia.org/",
    "brave-search": "https://search.brave.com/",
    "arxiv": "https://arxiv.org/",
    "exa": "https://exa.ai/",
    "youtube": "https://www.youtube.com/",
    "stripe": "https://dashboard.stripe.com/",
    "paypal": "https://www.paypal.com/",
    "shopify": "https://www.shopify.com/",
}


def _launch_url(ext_id: str) -> str:
    """URL for the service's own interface to confirm / grant the JARVIS
    connection. External services resolve to their real web app / UI so that
    pressing Connect opens *that* app (not a Jarvis settings page); local
    extensions without an external UI fall back to the scoped settings
    deep-link.

    Full OAuth authorization-code wiring per service lands here in a deployment
    that registers OAuth apps (configured via ``JARVIS_OAUTH_CLIENTS``); for now
    this hands the user the service's own interface to confirm the connection,
    and the ``/connect`` acknowledge call records the connection in Jarvis KV
    and turns the extension's capabilities live on the platform."""
    return _CONNECT_URLS.get(ext_id) or f"/dashboard/settings?connect={ext_id}"


# ---------------------------------------------------------------------------
# OAuth handoff (optional, secret-free at the code level)
# ---------------------------------------------------------------------------
# When a provider entry exists in the ``JARVIS_OAUTH_CLIENTS`` env var (JSON),
# Connect performs a real OAuth authorization-code handoff: ``/launch`` returns
# the provider's ``authorize_url``; the service redirects back to
# ``/oauth/callback/{ext}`` where JARVIS exchanges the code for tokens
# (using ``client_secret`` read from env — never sent to the browser) and
# records the connection as validated on the backend.
#
# With no config for an extension, the platform falls back to the service's own
# app URL + a manual confirm-gate on the frontend (no OAuth secrets required).
# Example env value:
#   {"github": {"client_id":"...","client_secret":"...",
#               "authorize_url":"https://github.com/login/oauth/authorize",
#               "token_url":"https://github.com/login/oauth/access_token",
#               "scope":"repo,user:email"}}
def _oauth_config(ext_id: str) -> Optional[Dict[str, Any]]:
    raw = os.environ.get("JARVIS_OAUTH_CLIENTS")
    if not raw:
        return None
    try:
        clients = json.loads(raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
    cfg = clients.get(ext_id)
    if not isinstance(cfg, dict) or not cfg.get("client_id"):
        return None
    return cfg


def _oauth_authorize_url(ext_id: str, user_id: str) -> Optional[str]:
    """OAuth ``authorize`` URL for an extension, or None if it has no config."""
    if ext_id == "github":
        return None
    cfg = _oauth_config(ext_id)
    if not cfg:
        return None
    # state is base64(json{ext,uid,t}) + HMAC-SHA256(secret). It binds the
    # redirect to this extension + user so the callback can validate safely.
    payload = base64.urlsafe_b64encode(
        json.dumps({"ext": ext_id, "uid": user_id, "t": int(time.time())}).encode()
    ).decode().rstrip("=")
    sig = hmac.new(
        os.environ.get("JARVIS_SECRET_KEY", "").encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    state = f"{payload}.{sig}"
    backend_base = os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000")
    redirect_uri = f"{backend_base}/api/v1/extensions/oauth/callback/{ext_id}"
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if cfg.get("scope"):
        params["scope"] = cfg["scope"]
    sep = "&" if "?" in cfg["authorize_url"] else "?"
    return f"{cfg['authorize_url']}{sep}{urlencode(params)}"


# ---------------------------------------------------------------------------
# API-key handoff (optional, secret-free at the code level)
# ---------------------------------------------------------------------------
# External services whose JARVIS connection is an API key issued from the
# service's own console (OpenAI, Claude, Gemini, Hugging Face-hosted Whisper /
# Stable Diffusion). ``/launch`` advertises these with ``connect_type="api_key"``
# and the key-creation console URL; ``/connect`` accepts a key (or
# auto-detects it from the environment), validates it LIVE against the provider,
# and only then flips the connection to validated, so the extension's
# capabilities go live on the platform immediately with no demo state. The
# validated key is also injected into the process environment so the cloud
# provider routing path can use it without a restart; the raw key is never
# persisted to Jarvis KV (only metadata + a masked reference), matching how
# OAuth tokens are handled.
_API_KEY_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "key_env": ["OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI"],
        "console_url": "https://platform.openai.com/api-keys",
        "validator": "_validate_openai_key",
    },
    "claude": {
        "key_env": ["ANTHROPIC_API_KEY", "JARVIS_API_KEY_CLAUDE"],
        "console_url": "https://console.anthropic.com/settings/keys",
        "validator": "_validate_claude_key",
    },
    "gemini": {
        "key_env": ["GOOGLE_API_KEY", "JARVIS_API_KEY_GEMINI",
                    "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"],
        "console_url": "https://aistudio.google.com/apikey",
        "validator": "_validate_gemini_key",
    },
    # NVIDIA NIM (spec sections 1-8). OpenAI-compatible /v1 surface; auth via
    # NVIDIA_API_KEY (env) -- the credential for Brain -> NVIDIA, distinct from
    # JARVIS_BRAIN_API_KEY which protects the local Brain boundary (spec 33).
    "nvidia": {
        "key_env": ["NVIDIA_API_KEY", "JARVIS_API_KEY_NVIDIA"],
        "console_url": "https://catalog.ngc.nvidia.com/models",
        "validator": "_validate_nvidia_key",
    },
    "whisper": {
        "key_env": ["HF_TOKEN", "JARVIS_API_KEY_WHISPER"],
        "console_url": "https://huggingface.co/settings/tokens",
        "validator": "_validate_hf_key",
    },
    "stablediffusion": {
        "key_env": ["HF_TOKEN", "JARVIS_API_KEY_STABLEDIFFUSION"],
        "console_url": "https://huggingface.co/settings/tokens",
        "validator": "_validate_hf_key",
    },
    "codemuse": {
        "key_env": ["JARVIS_API_KEY_CODEMUSE"],
        "console_url": "https://codemuse.io/",
        "validator": None,  # no public validation endpoint
    },
}


def _connect_type(ext_id: str) -> str:
    """Connection strategy for an extension: ``oauth`` (OAuth app registered),
    ``api_key`` (console-issued API key) or ``confirm`` (manual confirm-gate)."""
    if _oauth_config(ext_id):
        return "oauth"
    if ext_id in _API_KEY_PROVIDERS:
        return "api_key"
    return "confirm"


def _api_key_env_names(ext_id: str) -> List[str]:
    prov = _API_KEY_PROVIDERS.get(ext_id) or {}
    return prov.get("key_env", [])


def _env_api_key(ext_id: str) -> Optional[str]:
    """First non-empty API-key env var for an API-key provider (None if unset)."""
    for name in _api_key_env_names(ext_id):
        val = os.environ.get(name)
        if val:
            return val
    return None


def _validate_openai_key(key):
    """(verified, err) -- GET /v1/models is a free call that authenticates."""
    try:
        r = httpx.get("https://api.openai.com/v1/models",
                      headers={"Authorization": f"Bearer {key}"}, timeout=10)
    except httpx.HTTPError:
        return (None, None)  # network error -> cannot verify, accept as "stored"
    if r.status_code == 200:
        return (True, None)
    if r.status_code in (401, 403):
        return (False, "invalid OpenAI API key")
    return (None, None)


def _validate_claude_key(key):
    try:
        r = httpx.get("https://api.anthropic.com/v1/models",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      timeout=10)
    except httpx.HTTPError:
        return (None, None)
    if r.status_code == 200:
        return (True, None)
    if r.status_code in (401, 403):
        return (False, "invalid Anthropic API key")
    return (None, None)


def _validate_gemini_key(key):
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                      params={"key": key}, timeout=10)
    except httpx.HTTPError:
        return (None, None)
    if r.status_code == 200:
        return (True, None)
    if r.status_code in (401, 403):
        return (False, "invalid Google API key")
    return (None, None)


def _validate_hf_key(key):
    try:
        r = httpx.get("https://huggingface.co/api/whoami",
                      headers={"Authorization": f"Bearer {key}"}, timeout=10)
    except httpx.HTTPError:
        return (None, None)
    if r.status_code == 200:
        return (True, None)
    if r.status_code in (401, 403):
        return (False, "invalid Hugging Face token")
    return (None, None)


def _validate_nvidia_key(key):
    """GET /v1/models authenticates the key (free call). Mirrors _validate_openai_key.

    Returns ``(verified, err)``: ``(True, None)`` when the key is confirmed,
    ``(False, msg)`` when the provider definitively rejects it (401/403), and
    ``(None, None)`` when verification is inconclusive (network error / 5xx) so
    the key is still accepted as ``stored`` for the matrix.
    """
    try:
        r = httpx.get(NVIDIA_NIM_MODELS_URL,
                      headers={"Authorization": f"Bearer {key}"}, timeout=10)
    except Exception:
        return (None, None)  # network error -> cannot verify, accept as "stored"
    if r.status_code == 200:
        return (True, None)
    if r.status_code in (401, 403):
        return (False, "invalid NVIDIA API key")
    return (None, None)


def _discover_nvidia_models(key) -> Dict[str, Any]:
    """NVIDIAModelDiscovery (spec section 5).

    Queries ``GET https://integrate.api.nvidia.com/v1/models`` with the real
    key and returns ``{configured, models, selected, override, override_applied,
    error}``. ``JARVIS_NVIDIA_MODEL`` is honored as a *selection hint* only when
    it matches a discovered model -- the first chat-capable model is selected
    otherwise. A model is never silently returned that was not discovered.
    """
    headers = {"Authorization": f"Bearer {key}", "accept": "application/json"}
    try:
        r = httpx.get(NVIDIA_NIM_MODELS_URL, headers=headers, timeout=10)
    except httpx.HTTPError:
        return {"configured": False, "models": [], "selected": None,
                "error": "network error contacting NVIDIA"}
    if r.status_code == 401:
        return {"configured": False, "models": [], "selected": None,
                "error": "invalid NVIDIA API key"}
    if r.status_code != 200:
        return {"configured": False, "models": [], "selected": None,
                "error": f"NVIDIA models endpoint returned HTTP {r.status_code}"}
    models: List[Dict[str, Any]] = []
    for m in (r.json().get("data") or []):
        mid = m.get("id") or m.get("name")
        if not mid:
            continue
        models.append({
            "model_id": mid,
            "provider": "nvidia",
            "capabilities": _nvidia_model_caps(mid),
            "availability": "online",
            "owned_by": m.get("owned_by"),
            "object": m.get("object"),
        })
    override = os.environ.get("JARVIS_NVIDIA_MODEL")
    chosen = None
    if override:
        chosen = next((m["model_id"] for m in models if m["model_id"] == override), None)
    if not chosen and models:
        chosen = _prefer_chat_capable(models)
    return {"configured": True, "models": models, "selected": chosen,
            "override": bool(override), "override_applied": (override == chosen)}


# NVIDIA NIM chat default that is actually invocable on a standard NVIDIA key
# (falls back gracefully when offline). Many advertised ids (e.g. llama-3.1
# nemotron 70B, nemotron-4) return HTTP 404 "Function not found" unless the
# account is granted access.
_NVIDIA_CHAT_DEFAULT = "nvidia/nemotron-3-ultra-550b-a55b"

_NON_CHAT_TOKENS = ("embed", "rerank", "asr", "tts", "speech", "vocoder")


def _nvidia_model_caps(mid: str) -> List[str]:
    """Conservative capability inference for a live NVIDIA catalog id.

    Only ``chat``/``generate`` is claimed for ids that clearly name a generative
    instruction/chat model; embed/speech models advertise nothing.
    """
    if any(tok in mid for tok in _NON_CHAT_TOKENS):
        return []
    return ["chat", "generate"]


def _prefer_chat_capable(models: List[Dict[str, Any]]) -> str:
    """Pick the best discovered chat model instead of blindly taking index 0.

    Preference: the documented NVIDIA default if present, else the first id that
    looks chat-capable (contains 'instruct' or 'chat'), else the first entry.
    Only discovered models are ever considered.
    """
    def _is_chat(m: Dict[str, Any]) -> bool:
        mid = m["model_id"]
        return bool(m.get("capabilities")) and not any(
            tok in mid for tok in _NON_CHAT_TOKENS
        )

    chat_models = [m for m in models if _is_chat(m)]
    if not chat_models:
        return models[0]["model_id"]
    for preferred in (_NVIDIA_CHAT_DEFAULT, "nvidia/nemotron-3-super-120b-a12b",
                      "mistralai/mistral-nemotron"):
        for m in chat_models:
            if m["model_id"] == preferred:
                return m["model_id"]
    for m in chat_models:
        mid = m["model_id"]
        if "instruct" in mid or "chat" in mid:
            return mid
    return chat_models[0]["model_id"]


_VALIDATORS = {
    "_validate_openai_key": _validate_openai_key,
    "_validate_claude_key": _validate_claude_key,
    "_validate_gemini_key": _validate_gemini_key,
    "_validate_hf_key": _validate_hf_key,
    "_validate_nvidia_key": _validate_nvidia_key,
}


def _validate_api_key(ext_id, key):
    """Live-validate a provider API key.

    Returns ``(verified, err)``. ``verified`` is True when the key was confirmed
    valid, None when it could not be verified (offline / non-validated provider)
    and the key is accepted as ``stored``; ``err`` is set when the key is
    definitively rejected (HTTP 401/403).
    """
    prov = _API_KEY_PROVIDERS.get(ext_id) or {}
    name = prov.get("validator")
    fn = _VALIDATORS.get(name) if name else None
    if not fn:
        return (None, None)  # no validator -> accept as "stored"
    return fn(key)


def _extension_capabilities(ext_id: str) -> List[str]:
    cap_map: Dict[str, List[str]] = {
        # core
        "memory": ["memory.read", "memory.write", "memory.forget"],
        "knowledge": ["knowledge.ingest", "knowledge.query"],
        "scheduler": ["scheduler.list", "scheduler.create", "scheduler.run"],
        "voice": ["voice.listen", "voice.speak"],
        "monitoring": ["monitoring.metrics", "monitoring.alerts"],
        # ai
        "claude": ["claude.chat", "claude.generate", "claude.analyze"],
        "openai": ["openai.chat", "openai.generate", "openai.images"],
        "gemini": ["gemini.chat", "gemini.generate"],
        "nvidia": ["nvidia.chat", "nvidia.generate"],
        "codemuse": ["codemuse.chat", "codemuse.analyze"],
        "whisper": ["whisper.transcribe", "whisper.detect"],
        "stablediffusion": ["imagine.generate", "imagine.style"],
        # development
        "github": [],
        "gitlab": ["gitlab.read", "gitlab.write", "gitlab.pr"],
        "opencode": ["opencode.run", "opencode.build", "opencode.test"],
        "cursor": ["cursor.generate", "cursor.edit"],
        "vscode": ["vscode.tasks", "vscode.terminal"],
        "docker": ["docker.images", "docker.containers", "docker.build", "docker.push"],
        "webhooks": ["webhooks.create", "webhooks.manage"],
        # devops / cloud / infra
        "kubernetes": ["k8s.pods", "k8s.deploy", "k8s.logs"],
        "terraform": ["tf.plan", "tf.apply", "tf.destroy"],
        "ansible": ["ansible.play", "ansible.run"],
        "jenkins": ["jenkins.jobs", "jenkins.build"],
        "aws": ["aws.list", "aws.provision", "aws.inspect"],
        "gcp": ["gcp.list", "gcp.provision"],
        "azure": ["azure.list", "azure.provision"],
        "supabase": ["supabase.db", "supabase.auth"],
        "vultr": ["vultr.instances", "vultr.deploy"],
        # data / storage
        "database": ["database.query", "database.write"],
        "postgres": ["postgres.query", "postgres.write"],
        "redis": ["redis.get", "redis.set", "redis.scan"],
        "mongodb": ["mongo.query", "mongo.write"],
        "elasticsearch": ["elastic.search", "elastic.write"],
        "analytics": ["analytics.read", "analytics.report", "analytics.alerts"],
        # communication
        "slack": ["slack.send", "slack.receive"],
        "discord": ["discord.send", "discord.receive"],
        "telegram": ["telegram.send", "telegram.receive"],
        "whatsapp": ["whatsapp.send", "whatsapp.read"],
        "google-workspace": ["gsuite.read", "gsuite.write"],
        "translate": ["translate.text", "translate.document"],
        # productivity / design
        "calendar": ["calendar.read", "calendar.write", "calendar.delete"],
        "files": ["files.read", "files.write", "files.delete"],
        "notion": ["notion.read", "notion.write"],
        "linear": ["linear.issues", "linear.create"],
        "jira": ["jira.tickets", "jira.create"],
        "trello": ["trello.cards", "trello.create"],
        "figma": ["figma.read", "figma.update"],
        "canva": ["canva.design", "canva.export"],
        "slack-sync": ["slack.sync", "slack.stream"],
        # research
        "wikipedia": ["wiki.search", "wiki.summarize"],
        "brave-search": ["web.search", "web.fetch"],
        "arxiv": ["arxiv.search", "arxiv.summarize"],
        "exa": ["exa.search", "exa.summarize"],
        "youtube": ["youtube.search", "youtube.caption"],
        # commerce
        "stripe": ["stripe.charges", "stripe.customers"],
        "paypal": ["paypal.transactions", "paypal.payments"],
        "shopify": ["shopify.products", "shopify.orders"],
        # system
        "ssh": ["ssh.exec", "ssh.tunnels"],
        "terminal": ["terminal.exec"],
        "process": ["process.list", "process.inspect"],
    }
    return cap_map.get(ext_id, [])


def _installed_state(data: Dict[str, Any], ext_id: str) -> Dict[str, Any]:
    """Return the persisted install record for an extension (empty dict if not
    yet installed)."""
    return data["installed"].get(ext_id, {})


def _require_admin(user: Dict[str, Any]) -> Dict[str, Any]:
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


def _extensions_store() -> Dict[str, Any]:
    """Return the live ``extensions`` KV collection, ensuring an ``installed``
    namespace exists. The catalog itself (``available``) is always derived from
    code, so it lives only in this process; only install state is persisted.

    Returned object is the store's cached reference, so callers mutate it and
    call ``get_store("extensions").save()`` (no-arg) to flush.
    """
    store = get_store("extensions")
    data = store.load()
    if not isinstance(data, dict) or "installed" not in data:
        data.clear()
        data["installed"] = {}
        store.save()
    # Older GitHub extension callbacks wrote plaintext tokens into the shared
    # extension record. Migrate them once into the encrypted per-user OAuth vault.
    installed = data.get("installed")
    github = installed.get("github") if isinstance(installed, dict) else None
    if isinstance(github, dict) and "oauth_token" in github:
        legacy_tokens = github.pop("oauth_token")
        user_id = github.get("connected_by")
        access_token = legacy_tokens.get("access_token") if isinstance(legacy_tokens, dict) else None
        if isinstance(user_id, (str, int)) and isinstance(access_token, str) and access_token:
            from ..connectors import oauth as oauth_store

            oauth_store.save_tokens("github", str(user_id), {
                "access_token": access_token,
                "refresh_token": legacy_tokens.get("refresh_token"),
                "expires_at": legacy_tokens.get("expires_at"),
                "scope": legacy_tokens.get("scope"),
                "provider": "github",
            })
        github["connected"] = False
        github["status"] = "connection_managed_in_connections_center"
        github.pop("connected_at", None)
        store.save()
    return data


def _public_view(ext_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Build the public catalog entry, merging persisted install/ connection
    state (so everyone sees what's installed/enabled/connected without auth)."""
    ext_data = dict(_default_extensions()[ext_id])
    inst = _installed_state(data, ext_id)
    ext_data["installed"] = bool(inst)
    ext_data["enabled"] = inst.get("enabled", False)
    ext_data["connected"] = inst.get("connected", False)
    ext_data["status"] = inst.get("status", "available" if not inst else (
        "connected" if inst.get("connected") else "needs_connection"))
    ext_data["config"] = inst.get("config", {})
    ext_data["installed_at"] = inst.get("installed_at")
    ext_data["connected_at"] = inst.get("connected_at")
    ext_data["launch_url"] = _launch_url(ext_id)
    ext_data["connect_type"] = _connect_type(ext_id)
    ext_data["key_env"] = ((_API_KEY_PROVIDERS.get(ext_id, {}) or {}).get("key_env") or [None])[0]
    ext_data["caps"] = _extension_capabilities(ext_id)
    if ext_id == "github":
        ext_data["connected"] = False
        ext_data["status"] = "Manage authorization in Connections"
        ext_data["config"] = {}
        ext_data["connected_at"] = None
        ext_data["caps"] = []
    return ext_data


class ExtensionConnectIn(BaseModel):
    """Body for POST /{ext}/connect. ``api_key`` is optional because API-key
    services can also be connected from an env var (e.g. OPENAI_API_KEY)."""
    extension_id: Optional[str] = None  # path carries it; kept for compat
    api_key: Optional[str] = None



class ExtensionInvokeIn(BaseModel):
    """Body for POST /{ext}/invoke -- ask a connected extension to run one of
    its capabilities against its REAL service. ``api_key`` overrides the env key
    that POST /connect injected; ``params`` are the capability arguments."""
    capability: str
    api_key: Optional[str] = None
    params: Dict[str, Any] = {}


# Install-record fields that must never be returned to a client.
_SENSITIVE_STATE_FIELDS = ("oauth_token", "api_key")


def _sanitize_install_state(inst: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of an install record with persisted secrets stripped (used by the
    admin-only ``/installed`` view) before it reaches a client."""
    clean = dict(inst)
    for field in _SENSITIVE_STATE_FIELDS:
        clean.pop(field, None)
    return clean


# ---------------------------------------------------------------------------
# Extension service invocation -- 'Jarvis USES a connected extension's service'
# ---------------------------------------------------------------------------
# Each API-key provider maps to a handler that calls the provider's real API.
# A bad key is rejected live by the provider (401), never by a demo gate.
# ---------------------------------------------------------------------------
# Generic OpenAI-compatible transport (spec section 6). Reused by every
# OpenAI-shaped provider -- OpenAI and NVIDIA NIM -- so we never introduce a
# second HTTP client. ``provider`` parameterizes the error message so a 401 is
# reported with the correct provider name (never a misleading "OpenAI" string
# for an NVIDIA failure).
# ---------------------------------------------------------------------------
NVIDIA_NIM_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_MODELS_URL = f"{NVIDIA_NIM_BASE}/models"
NVIDIA_NIM_CHAT_URL = f"{NVIDIA_NIM_BASE}/chat/completions"


def _openai_compatible_post(url: str, payload: Dict[str, Any], key: str,
                            *, provider: str = "openai", timeout: float = 30) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "nvidia":
        # NVIDIA NIM recommends an explicit accept header.
        headers["accept"] = "application/json"
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 500
        if code in (401, 403):
            raise HTTPException(status_code=401, detail=f"invalid {provider} API key")
        if code == 429:
            raise HTTPException(status_code=429, detail=f"{provider} rate limit exceeded")
        if code >= 500:
            raise HTTPException(status_code=502, detail=f"{provider} service error ({code})")
        raise HTTPException(status_code=400, detail=f"{provider} request error ({code})")
    except httpx.HTTPError as e:
        # Transport-level failure (connect refused / DNS / TLS): the endpoint was
        # NOT reached, which is distinct from a 5xx it answered. 503 -> the
        # gateway maps this to PROVIDER_UNAVAILABLE (honest fallback), while a
        # real 5xx (502) stays retryable TIMEOUT.
        raise HTTPException(status_code=503, detail=f"{provider} unreachable: {type(e).__name__}")
    return r.json()


def _openai_json_post(url: str, payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Backward-compatible wrapper over :func:`_openai_compatible_post`.

    Preserved at its original 3-arg signature (and name) so existing tests that
    ``monkeypatch`` ``_openai_json_post`` continue to work; OpenAI is the default
    provider. ``_invoke_openai`` calls this wrapper; ``_invoke_nvidia`` calls
    ``_openai_compatible_post`` directly with ``provider="nvidia"``.
    """
    return _openai_compatible_post(url, payload, key, provider="openai")


def _invoke_openai(ext_id: str, capability: str, params: Dict[str, Any], key: str) -> Dict[str, Any]:
    if capability == "openai.chat":
        messages = params.get("messages") or params.get("conversation", [])
        if not messages:
            raise HTTPException(status_code=400, detail="openai.chat requires 'messages'")
        payload: Dict[str, Any] = {"model": params.get("model", "gpt-4o-mini"), "messages": messages}
        if params.get("system"):
            payload["messages"] = [{"role": "system", "content": params["system"]}] + payload["messages"]
        if params.get("max_tokens"):
            payload["max_tokens"] = int(params["max_tokens"])
        data = _openai_json_post("https://api.openai.com/v1/chat/completions", payload, key)
        return {"provider": "openai", "content": data["choices"][0]["message"]["content"],
                "model": data.get("model"), "usage": data.get("usage", {})}
    if capability == "openai.generate":
        inp = params.get("input") or params.get("text")
        if not inp:
            raise HTTPException(status_code=400, detail="openai.generate requires 'input'")
        payload = {"model": params.get("model", "text-embedding-3-small"), "input": inp}
        data = _openai_json_post("https://api.openai.com/v1/embeddings", payload, key)
        return {"provider": "openai", "data": data.get("data", []), "model": data.get("model")}
    if capability == "openai.images":
        prompt = params.get("prompt") or params.get("description")
        if not prompt:
            raise HTTPException(status_code=400, detail="openai.images requires 'prompt'")
        payload = {"prompt": prompt, "n": int(params.get("n", 1)),
                   "size": params.get("size", "512x512")}
        data = _openai_json_post("https://api.openai.com/v1/images/generations", payload, key)
        return {"provider": "openai", "images": [u.get("url") for u in data.get("data", [])]}
    raise HTTPException(status_code=400, detail=f"Unsupported OpenAI capability: {capability}")


def _invoke_nvidia(ext_id: str, capability: str, params: Dict[str, Any], key: str) -> Dict[str, Any]:
    # NVIDIA NIM exposes an OpenAI-compatible /v1/chat/completions surface.
    # Reuse the shared OpenAI-compatible transport (no second HTTP client).
    if capability != "nvidia.chat":
        raise HTTPException(status_code=400, detail=f"Unsupported NVIDIA capability: {capability}")
    messages = params.get("messages") or params.get("conversation", [])
    if not messages:
        raise HTTPException(status_code=400, detail="nvidia.chat requires 'messages'")
    # §5: do not hard-code a model until /v1/models has been queried. Honor
    # params.model / JARVIS_NVIDIA_MODEL; otherwise discover first.
    model = params.get("model") or os.environ.get("JARVIS_NVIDIA_MODEL") or ""
    if not model:
        disc = _discover_nvidia_models(key)
        models = disc.get("models", [])
        if not models:
            raise HTTPException(
                status_code=503,
                detail="NVIDIA NIM is configured but no models could be discovered",
            )
        model = disc.get("selected") or models[0]["model_id"]
    payload: Dict[str, Any] = {"model": model, "messages": messages}
    if params.get("system"):
        payload["messages"] = [{"role": "system", "content": params["system"]}] + payload["messages"]
    if params.get("max_tokens"):
        payload["max_tokens"] = int(params["max_tokens"])
    data = _openai_compatible_post(NVIDIA_NIM_CHAT_URL, payload, key, provider="nvidia")
    return {"provider": "nvidia", "capability": capability,
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model") or model,
            "usage": data.get("usage", {})}


def _invoke_claude(ext_id: str, capability: str, params: Dict[str, Any], key: str) -> Dict[str, Any]:
    # Anthropic Messages API serves chat / generate / analyze.
    if capability not in ("claude.chat", "claude.generate", "claude.analyze"):
        raise HTTPException(status_code=400, detail=f"Unsupported Claude capability: {capability}")
    messages = params.get("messages") or params.get("conversation", [])
    if not messages:
        raise HTTPException(status_code=400, detail="claude.chat requires 'messages'")
    payload: Dict[str, Any] = {"model": params.get("model", "claude-3-5-sonnet-20241022"),
                               "messages": messages, "max_tokens": params.get("max_tokens", 1024)}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 500
        if code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid Anthropic API key")
        if code == 429:
            raise HTTPException(status_code=429, detail="Claude rate limit exceeded")
        raise HTTPException(status_code=502 if code >= 500 else 400, detail=f"Claude error ({code})")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Claude request failed: {type(e).__name__}")
    d = r.json()
    content = (d.get("content") or [{}])[0].get("text", "")
    return {"provider": "claude", "capability": capability, "content": content,
            "model": d.get("model"), "usage": d.get("usage", {})}


def _invoke_gemini(ext_id: str, capability: str, params: Dict[str, Any], key: str) -> Dict[str, Any]:
    # Google Gemini generateContent endpoint (key passed as ?key=).
    if capability not in ("gemini.chat", "gemini.generate"):
        raise HTTPException(status_code=400, detail=f"Unsupported Gemini capability: {capability}")
    model = params.get("model", "gemini-1.5-flash")
    prompt = params.get("prompt") or params.get("text")
    if prompt is None and params.get("messages") is None:
        raise HTTPException(status_code=400, detail="gemini.chat requires 'messages' or 'prompt'")
    if prompt is not None:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
    else:
        contents = []
        for m in params.get("messages", []):
            role = m.get("role", "user")
            text = m.get("content") or m.get("text", "")
            contents.append({"role": role, "parts": [{"text": text}]})
    payload = {"contents": contents}
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key}, json=payload, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 500
        if code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid Google API key")
        if code == 400:
            # Google surfaces invalid API keys on the ?key= path as a 400
            # INVALID_ARGUMENT ('API key not valid'); normalize to 401 so a bad
            # key is reported consistently across all providers.
            try:
                _msg = (e.response.json().get("error", {}) or {}).get("message", "").lower()
            except Exception:
                _msg = ""
            if "api key" in _msg or "apikey" in _msg:
                raise HTTPException(status_code=401, detail="invalid Google API key")
            raise HTTPException(status_code=400, detail=f"Gemini error ({code})")
        raise HTTPException(status_code=502 if code >= 500 else 400, detail=f"Gemini error ({code})")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gemini request failed: {type(e).__name__}")
    d = r.json()
    text = ""
    candidates = d.get("candidates") or []
    if candidates:
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if parts:
            text = parts[0].get("text", "")
    return {"provider": "gemini", "capability": capability, "content": text,
            "model": model, "usage": d.get("usageMetadata", {})}


_PROVIDER_INVOKE_HANDLERS: Dict[str, Any] = {
    "openai": _invoke_openai,
    "claude": _invoke_claude,
    "gemini": _invoke_gemini,
    "nvidia": _invoke_nvidia,
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_extensions(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Marketplace catalog — browsable **without** authentication. Install /
    enable / uninstall / connect remain admin-gated."""
    data = _extensions_store()
    result = [_public_view(ext_id, data) for ext_id in _default_extensions()]
    return {"extensions": result, "total": len(result)}


@router.get("/installed")
async def list_installed(user: Dict[str, Any] = Depends(get_current_user)):
    data = _extensions_store()
    installed = data["installed"]
    result = []
    for ext_id, inst in installed.items():
        ext_data = _sanitize_install_state(inst)
        ext_data["id"] = ext_id
        ext_data["logo"] = _logo(ext_id)
        ext_data["caps"] = _extension_capabilities(ext_id)
        ext_data["connect_type"] = _connect_type(ext_id)
        # Reflect the REAL service / OAuth URL here — never a stale fallback
        # deep-link persisted from an older confirm-gate connect, so /installed
        # agrees with the public catalog (_public_view).
        ext_data["launch_url"] = _launch_url(ext_id)
        ext_data["status"] = inst.get("status", "connected" if inst.get("connected") else "needs_connection")
        if ext_id == "github":
            from ..connectors import oauth as oauth_store

            metadata = oauth_store.connection_metadata("github", str(user.get("id") or ""))
            ext_data["connected"] = metadata.get("connected", False)
            ext_data["status"] = metadata.get("status", "Authorization required")
            ext_data["account"] = metadata.get("account")
            ext_data["caps"] = []
        result.append(ext_data)
    return {"installed": result, "total": len(result)}


@router.get("/capabilities")
async def extension_capabilities(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Effective capability surface for currently enabled extensions. Public so
    the AI-access / developer panel can render without a session."""
    data = _extensions_store()
    installed = data["installed"]
    capabilities: List[str] = []
    for ext_id, ext in installed.items():
        # An extension's capabilities only go live on the platform once the
        # user has actually connected it (installed + enabled + connected) —
        # so pressing Connect is what makes the effect positive platform-wide.
        if ext.get("enabled") and ext.get("connected"):
            capabilities.extend(_extension_capabilities(ext_id))
    return {"capabilities": capabilities}


@router.get("/{extension_id}")
async def get_extension(extension_id: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Single-extension detail — public so the marketplace can deep-link."""
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    ext_data = _public_view(extension_id, data)
    return ext_data


@router.post("/install")
async def install_extension(body: ExtensionInstallIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    available = _default_extensions()
    ext = available.get(body.extension_id)
    if not ext:
        raise HTTPException(status_code=404, detail=f"Extension '{body.extension_id}' not found")

    data = _extensions_store()
    installed = data["installed"]
    installed[body.extension_id] = {
        "id": body.extension_id,
        "name": ext["name"],
        "category": ext["category"],
        "config": body.config,
        "enabled": True,
        "installed_at": now_iso(),
        "version": "1.0.0",
        # Jarvis's own storage holds the connection intent/state:
        "connected": False,
        "connected_at": None,
        "status": "needs_connection",
        "launch_url": _launch_url(body.extension_id),
    }
    get_store("extensions").save()
    return {"success": True, "extension": body.extension_id,
            "message": f"{ext['name']} installed — grant access to activate"}


@router.post("/{extension_id}/launch")
async def launch_extension(extension_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Return the authorize/configure URL so the user can connect the extension
    to its external service (OAuth / settings). The URL is persisted so the
    connection is tracked in Jarvis storage."""
    _require_admin(user)
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    if extension_id == "github":
        app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000").rstrip("/")
        return {
            "launch_url": f"{app_url}/dashboard/connections",
            "authorize_url": None,
            "connect_type": "oauth",
            "connected": False,
            "message": "Authorize GitHub through the user-scoped Connections center.",
        }
    # If an OAuth client is configured for this extension, hand back the
    # provider's authorize URL so the connection is VALIDATED by the service
    # and recorded via the /oauth/callback/<ext> redirect. Otherwise fall back
    # to the service's own app URL (manual confirm-gate on the frontend).
    authorize_url = _oauth_authorize_url(extension_id, user["id"])
    connect_type = _connect_type(extension_id)
    if authorize_url:
        url = authorize_url
        message = (f"Open {url} to grant {available[extension_id]['name']} access — "
                   "JARVIS validates the connection automatically when you return.")
    elif connect_type == "api_key":
        url = _API_KEY_PROVIDERS[extension_id]["console_url"]
        message = (
            f"Open {url} to create an API key for {available[extension_id]['name']}. "
            f"Paste the key (or set {_API_KEY_PROVIDERS[extension_id]['key_env'][0]}) "
            f"to connect JARVIS.")
    else:
        url = _launch_url(extension_id)
        message = f"Open {url} to grant {available[extension_id]['name']} access"
    installed[extension_id]["launch_url"] = url
    get_store("extensions").save()
    return {"launch_url": url, "authorize_url": authorize_url,
            "connect_type": connect_type,
            "key_env": ((_API_KEY_PROVIDERS.get(extension_id, {}) or {}).get("key_env") or [None])[0],
            "connected": installed[extension_id].get("connected", False),
            "message": message}


@router.get("/oauth/callback/{extension_id}")
async def oauth_callback(
    extension_id: str,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """OAuth redirect target (public: hit by the provider after the user grants).

    Verifies the signed ``state`` we issued, exchanges the ``code`` for tokens
    server-side using the provider's ``client_secret`` read from the
    ``JARVIS_OAUTH_CLIENTS`` env (never exposed to the client), and — only on a
    successful exchange — records the connection as validated on the backend.
    Then bounces the user's browser to the front-end callback page.
    """
    if extension_id == "github":
        from urllib.parse import urlencode

        app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000").rstrip("/")
        return RedirectResponse(
            url=f"{app_url}/dashboard/connections?{urlencode({'github_error': 'Use the secure Connections OAuth flow.'})}",
            status_code=303,
        )
    cfg = _oauth_config(extension_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="No OAuth configuration for this extension")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")
    payload, _, sig = state.partition(".")
    expected = hmac.new(
        os.environ.get("JARVIS_SECRET_KEY", "").encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    try:
        pad = "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload + pad))
        uid = decoded.get("uid")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    backend_base = os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000")
    redirect_uri = f"{backend_base}/api/v1/extensions/oauth/callback/{extension_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(cfg["token_url"], data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Token exchange failed ({resp.status_code})")
        token_data = resp.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Token exchange failed")
    # Validate to backend: persist tokens and flip the extension live.
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    inst = installed[extension_id]
    inst["connected"] = True
    inst["connected_at"] = now_iso()
    inst["status"] = "connected"
    inst["launch_url"] = _launch_url(extension_id)
    inst["oauth_token"] = token_data
    inst["connected_by"] = uid
    get_store("extensions").save()
    app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000")
    return RedirectResponse(f"{app_url}/oauth/callback/{extension_id}?connected=1",
                            status_code=303)


@router.post("/{extension_id}/connect")
async def connect_extension(
    extension_id: str,
    body: Optional[ExtensionConnectIn] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Persist the connection in Jarvis storage once the user has authorized the
    extension at the ``launch`` URL.

    - API-key services (OpenAI, Claude, Gemini, Hugging Face ...): accept an
      ``api_key`` (or auto-detect it from the environment), VALIDATE it live
      against the provider, and only then mark the extension connected, so its
      capabilities go live on the platform with no demo state. A validated key
      is also injected into the process env so the cloud provider path can use it
      immediately (no restart).
    - OAuth services: the code-for-token exchange runs at
      ``/oauth/callback/{ext}``; calling ``/connect`` here just acknowledges an
      already-validated OAuth token.
    - Everything else (confirm-gate, e.g. Docker): the frontend confirmed the
      user granted access in the service app, and this records the connection.
    """
    _require_admin(user)
    if extension_id == "github":
        raise HTTPException(
            status_code=409,
            detail="GitHub authorization is user-scoped. Use the Connections center OAuth flow; extension confirmation cannot mark it connected.",
        )
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    inst = installed[extension_id]
    prov = _API_KEY_PROVIDERS.get(extension_id)
    if prov:
        key = body.api_key if (body and body.api_key) else _env_api_key(extension_id)
        if not key:
            env_names = ", ".join(_api_key_env_names(extension_id))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{available[extension_id]['name']} requires an API key. "
                    f"Set one of ({env_names}) in your environment, or POST "
                    f'{{"api_key": "..."}} to this endpoint.'),
            )
        verified, err = _validate_api_key(extension_id, key)
        if err:
            raise HTTPException(status_code=401, detail=err)
        # Inject the validated key into the process env so the model gateway's
        # cloud-provider path can use it immediately (no restart needed).
        os.environ.setdefault(prov["key_env"][0], key)
        inst["connected"] = True
        inst["connected_at"] = now_iso()
        inst["status"] = "connected"
        inst["launch_url"] = _launch_url(extension_id)
        inst["connected_by"] = "api_key"
        inst["validation"] = "verified" if verified else "stored"
        inst["key_env"] = prov["key_env"][0]
    else:
        inst["connected"] = True
        inst["connected_at"] = now_iso()
        inst["status"] = "connected"
        inst["launch_url"] = _launch_url(extension_id)
        inst["connected_by"] = user["id"]
    get_store("extensions").save()
    return {"success": True, "extension": extension_id, "connected": True,
            "connect_type": _connect_type(extension_id),
            "validation": inst.get("validation"),
            "message": f"{available[extension_id]['name']} connected to Jarvis"}


@router.post("/uninstall")
async def uninstall_extension(body: ExtensionUninstallIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    data = _extensions_store()
    installed = data["installed"]
    if body.extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    del installed[body.extension_id]
    get_store("extensions").save()
    return {"success": True, "removed": body.extension_id}


@router.patch("/{extension_id}")
async def update_extension(extension_id: str, body: ExtensionUpdateIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    if body.config:
        installed[extension_id]["config"] = body.config
    if body.enabled is not None:
        installed[extension_id]["enabled"] = body.enabled
        # keep the persisted status in sync with the connection/enabled reality
        if not body.enabled:
            installed[extension_id]["status"] = "disabled"
        elif installed[extension_id].get("connected"):
            installed[extension_id]["status"] = "connected"
        else:
            installed[extension_id]["status"] = "needs_connection"
    get_store("extensions").save()
    return {"success": True, "extension": extension_id}


@router.post("/{extension_id}/invoke")
async def invoke_extension(
    extension_id: str,
    body: ExtensionInvokeIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Ask an installed extension to run one of its capabilities against its REAL
    service (the provider's own API). The credential is resolved, in order, from
    the request body ``api_key`` or the env key that POST /connect injected -- i.e.
    an extension the user has already connected. A bad key is rejected live by the
    provider (401); a valid key returns the provider's real response.

    This is the explicit, opt-in path for 'Jarvis uses an extension's service':
    it does NOT autowire /api/chat routing (that is a separate, user-chosen step).
    """
    _require_admin(user)
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    inst = _installed_state(data, extension_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Extension not installed")
    if not inst.get("enabled", False):
        raise HTTPException(status_code=409, detail="Extension is disabled")
    if _connect_type(extension_id) == "api_key":
        key = body.api_key or _env_api_key(extension_id)
        if not key:
            env_names = ", ".join(_api_key_env_names(extension_id))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{available[extension_id]['name']} requires an API key. "
                    f"Set one of ({env_names}) and POST /connect, or pass "
                    f'{{"api_key": "..."}} with this capability.'
                ),
            )
        handler = _PROVIDER_INVOKE_HANDLERS.get(extension_id)
        if not handler:
            raise HTTPException(status_code=501,
                detail=f"Invocation not implemented for {extension_id} yet")
        result = handler(extension_id, body.capability, body.params, key)
        return {"success": True, "extension": extension_id,
                "capability": body.capability,
                "connected": bool(inst.get("connected")),
                "result": result}
    raise HTTPException(
        status_code=501,
        detail=f"Invocation for {extension_id} (connect_type={_connect_type(extension_id)}) "
               f"is not implemented yet; only API-key services are wired for invocation.",
    )
