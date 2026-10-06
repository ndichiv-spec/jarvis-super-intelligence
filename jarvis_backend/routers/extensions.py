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
import httpx
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from ..core import get_current_user, get_optional_user, get_store, now_iso
from ..connectors import oauth as oauth_store

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
    for field in ("client_secret", "authorize_url", "token_url"):
        if not cfg.get(field):
            raise HTTPException(
                status_code=503,
                detail=f"OAuth configuration for '{ext_id}' is missing {field}",
            )
    for field in ("authorize_url", "token_url"):
        parsed = urlparse(str(cfg[field]))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(
                status_code=503,
                detail=f"OAuth configuration for '{ext_id}' requires HTTPS provider URLs",
            )
    return cfg


def _oauth_authorize_url(ext_id: str, user_id: str) -> Optional[str]:
    """OAuth ``authorize`` URL for an extension, or None if it has no config."""
    cfg = _oauth_config(ext_id)
    if not cfg:
        return None
    try:
        state = oauth_store.make_state(ext_id, user_id)
    except oauth_store.OAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
    ``api_key`` (supported provider key) or ``unsupported`` (not wired yet)."""
    if _oauth_config(ext_id):
        return "oauth"
    if ext_id in _API_KEY_PROVIDERS:
        return "api_key" if ext_id in _PROVIDER_INVOKE_HANDLERS else "unsupported"
    return "unsupported"


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


def _stored_api_key(ext_id: str, user_id: str) -> Optional[str]:
    tokens = oauth_store.load_tokens(ext_id, user_id)
    key = tokens.get("access_token") if tokens else None
    return key if isinstance(key, str) and key else None


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
        "github": ["github.read", "github.write", "github.pr"],
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
    migrated = False
    for ext_id, install in data["installed"].items():
        if not isinstance(install, dict):
            continue
        owner_id = install.get("connected_by")
        for field in ("oauth_token", "api_key"):
            legacy = install.pop(field, None)
            if not legacy:
                continue
            if (
                owner_id
                and isinstance(legacy, dict)
                and isinstance(legacy.get("access_token"), str)
                and legacy["access_token"]
            ):
                expires_at = legacy.get("expires_at")
                if expires_at is None and legacy.get("expires_in") is not None:
                    try:
                        expires_at = time.time() + int(legacy["expires_in"])
                    except (TypeError, ValueError):
                        expires_at = None
                oauth_store.save_tokens(
                    ext_id,
                    str(owner_id),
                    {
                        "access_token": legacy.get("access_token"),
                        "refresh_token": legacy.get("refresh_token")
                        if isinstance(legacy.get("refresh_token"), str) else None,
                        "expires_at": expires_at,
                        "scope": legacy.get("scope"),
                        "provider": ext_id,
                    },
                )
            elif owner_id and isinstance(legacy, str):
                oauth_store.save_tokens(
                    ext_id,
                    str(owner_id),
                    {"access_token": legacy, "provider": ext_id},
                )
            migrated = True
    if migrated:
        store.save()
    return data


def _public_view(
    ext_id: str,
    data: Dict[str, Any],
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a catalog entry without exposing another user's connection state."""
    ext_data = dict(_default_extensions()[ext_id])
    inst = _installed_state(data, ext_id)
    ext_data["installed"] = bool(inst)
    ext_data["enabled"] = inst.get("enabled", False)
    connection = (
        oauth_store.connection_metadata(ext_id, user_id)
        if user_id else {"connected": False}
    )
    owner_connection = bool(connection.get("connected"))
    ext_data["connected"] = owner_connection
    ext_data["status"] = (
        "connected" if owner_connection
        else "needs_connection" if inst
        else "available"
    )
    ext_data["config"] = inst.get("config", {})
    ext_data["installed_at"] = inst.get("installed_at")
    ext_data["connected_at"] = inst.get("connected_at") if owner_connection else None
    ext_data["launch_url"] = _launch_url(ext_id)
    ext_data["connect_type"] = _connect_type(ext_id)
    ext_data["key_env"] = ((_API_KEY_PROVIDERS.get(ext_id, {}) or {}).get("key_env") or [None])[0]
    ext_data["caps"] = _extension_capabilities(ext_id)
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
    confirmed: bool = False


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
    user_id = str(user.get("id") or "") if user else None
    result = [_public_view(ext_id, data, user_id) for ext_id in _default_extensions()]
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
        owner_tokens = oauth_store.load_tokens(ext_id, str(user.get("id") or ""))
        if _oauth_config(ext_id):
            ext_data["connected"] = bool(
                oauth_store.connection_metadata(ext_id, str(user.get("id") or "")).get("connected")
            )
            ext_data["connected_at"] = (
                inst.get("connected_at") if ext_data["connected"] else None
            )
            ext_data.pop("connected_by", None)
        result.append(ext_data)
    return {"installed": result, "total": len(result)}


@router.get("/capabilities")
async def extension_capabilities(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Effective invocation surface for the authenticated extension owner."""
    if not user:
        return {"capabilities": []}
    data = _extensions_store()
    installed = data["installed"]
    capabilities: List[str] = []
    user_id = str(user.get("id") or "")
    for ext_id, ext in installed.items():
        # An extension's capabilities only go live on the platform once the
        # signed-in owner has connected it and a matching invoker exists.
        if (
            ext.get("enabled")
            and ext.get("connected")
            and (
                ext_id in _PROVIDER_INVOKE_HANDLERS
                or ext_id == "github"
            )
            and (
                ext.get("connected_by") == user_id
                or (
                    ext_id == "github"
                    and oauth_store.connection_metadata(ext_id, user_id).get("connected")
                )
                or _env_api_key(ext_id)
            )
        ):
            capabilities.extend(_extension_capabilities(ext_id))
    return {"capabilities": capabilities}


@router.get("/connections")
async def list_user_connections(user: Dict[str, Any] = Depends(get_current_user)):
    """Return safe, account-scoped connection metadata; credentials never leave the server."""
    user_id = str(user.get("id") or "")
    installed = _extensions_store()["installed"]
    connections = []
    for ext_id in _default_extensions():
        install = installed.get(ext_id, {})
        tokens = oauth_store.load_tokens(ext_id, user_id)
        metadata = oauth_store.connection_metadata(ext_id, user_id)
        has_credentials = bool(metadata.get("connected"))
        config = _oauth_config(ext_id)
        if not has_credentials and not config and ext_id != "github":
            continue
        status = (
            metadata.get("status") if tokens else
            "OAuth client not configured" if ext_id == "github" and not config else
            "Authorization required"
        )
        connections.append({
            "id": ext_id,
            "provider": _default_extensions().get(ext_id, {}).get("name", ext_id),
            "authorization_type": "oauth2" if config or ext_id == "github" else "api_key",
            "connected": has_credentials,
            "status": status,
            "account": tokens.get("account") if tokens else None,
            "scopes": tokens.get("scope") if tokens else (config or {}).get("scope"),
            "expires_at": tokens.get("access_expires_at") if tokens else None,
            "refresh_supported": bool(tokens and tokens.get("refresh_token")),
            "capabilities": [
                "github.repositories.list",
                "github.repository.read",
                "github.issues.read",
                "github.commits.read",
                "github.issues.create",
                "github.files.write",
            ] if ext_id == "github" else [],
            "installed": bool(install),
            "enabled": install.get("enabled", False),
            "authorization_configured": bool(config),
            "health": "not_verified",
            "last_used": None,
        })
    return {"connections": connections}


@router.get("/{extension_id}")
async def get_extension(extension_id: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Single-extension detail — public so the marketplace can deep-link."""
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    user_id = str(user.get("id") or "") if user else None
    ext_data = _public_view(extension_id, data, user_id)
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
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    if _connect_type(extension_id) != "oauth":
        _require_admin(user)
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
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
        message = (
            f"{available[extension_id]['name']} is not connected to an implemented JARVIS action yet. "
            "Opening its website does not authorize JARVIS."
        )
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
    cfg = _oauth_config(extension_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="No OAuth configuration for this extension")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")
    try:
        state_kind, uid = oauth_store.verify_state(state)
    except oauth_store.OAuthError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter") from exc
    if state_kind != extension_id:
        raise HTTPException(status_code=400, detail="OAuth state does not match this extension")
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
    if not isinstance(token_data, dict) or not isinstance(token_data.get("access_token"), str):
        raise HTTPException(status_code=502, detail="Token provider returned an invalid response")
    account = None
    granted_scope = token_data.get("scope")
    if extension_id == "github":
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                profile = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": "Bearer " + token_data["access_token"],
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            if profile.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"GitHub rejected the authorized connection ({profile.status_code})",
                )
            profile_data = profile.json()
            account = profile_data.get("login") if isinstance(profile_data, dict) else None
            if not isinstance(account, str) or not account:
                raise HTTPException(status_code=502, detail="GitHub did not return an account identity")
            granted_scope = profile.headers.get("X-OAuth-Scopes", granted_scope)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not verify the GitHub connection") from exc
    try:
        expires_at = (
            time.time() + int(token_data["expires_in"])
            if token_data.get("expires_in") is not None
            else None
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Token provider returned an invalid expiry") from exc
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
    oauth_store.save_tokens(
        extension_id,
        uid,
        {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at,
            "scope": granted_scope,
            "account": account,
            "provider": extension_id,
        },
    )
    get_store("extensions").save()
    from ..notifications import record_notification
    record_notification(
        uid,
        f"{_default_extensions()[extension_id]['name']} connected",
        "The OAuth token was encrypted and stored for this account.",
        "extensions",
    )
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
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    installed = data["installed"]
    if extension_id not in installed:
        raise HTTPException(status_code=404, detail="Extension not installed")
    inst = installed[extension_id]
    connect_type = _connect_type(extension_id)
    if connect_type == "unsupported":
        raise HTTPException(
            status_code=501,
            detail="This extension has no implemented, verifiable JARVIS connection yet",
        )
    if connect_type == "api_key":
        prov = _API_KEY_PROVIDERS[extension_id]
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
        user_id = str(user.get("id") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Authenticated identity is missing")
        oauth_store.save_tokens(
            extension_id,
            user_id,
            {"access_token": key, "provider": extension_id},
        )
        inst["connected"] = True
        inst["connected_at"] = now_iso()
        inst["status"] = "connected"
        inst["launch_url"] = _launch_url(extension_id)
        inst["connected_by"] = user_id
        inst["validation"] = "verified" if verified else "stored"
        inst["key_env"] = prov["key_env"][0]
    else:
        user_id = str(user.get("id") or "")
        tokens = oauth_store.load_tokens(extension_id, user_id) if user_id else None
        if not tokens or not (tokens.get("access_token") or tokens.get("refresh_token")):
            raise HTTPException(status_code=409, detail="Complete provider OAuth consent before connecting")
        inst["connected"] = True
        inst["connected_at"] = now_iso()
        inst["status"] = "connected"
        inst["launch_url"] = _launch_url(extension_id)
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
    token_store = get_store("oauth_tokens").load()
    if isinstance(token_store, dict):
        prefix = f"{body.extension_id}:"
        token_keys = [key for key in token_store if key.startswith(prefix)]
        for key in token_keys:
            token_store.pop(key, None)
        if token_keys:
            get_store("oauth_tokens").save()
    return {"success": True, "removed": body.extension_id}


@router.post("/{extension_id}/verify")
async def verify_extension_connection(
    extension_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Verify a user's OAuth grant against the provider, never by trusting saved UI state."""
    if extension_id != "github":
        raise HTTPException(
            status_code=501,
            detail=f"Live verification is not implemented for {extension_id}",
        )
    user_id = str(user.get("id") or "")
    token = oauth_store.access_token(extension_id, user_id)
    if not token:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "authorization_required",
                "service": "GitHub",
                "resource": "account",
                "required_permission": "Valid GitHub OAuth grant",
                "current_permission": "No usable grant",
                "remediation": "Authorize or reconnect GitHub.",
            },
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="GitHub verification request failed") from exc
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "access_denied",
                "service": "GitHub",
                "resource": "account",
                "required_permission": "Valid GitHub account authorization",
                "current_permission": f"GitHub returned HTTP {response.status_code}",
                "remediation": "Reauthorize GitHub or ask the organization owner to review its policy.",
            },
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub verification failed ({response.status_code})")
    profile = response.json()
    if not isinstance(profile, dict) or not isinstance(profile.get("login"), str):
        raise HTTPException(status_code=502, detail="GitHub returned an invalid account profile")
    tokens = oauth_store.load_tokens(extension_id, user_id) or {}
    return {
        "connected": True,
        "authenticated": True,
        "reachable": True,
        "account": profile["login"],
        "scopes": response.headers.get("X-OAuth-Scopes") or tokens.get("scope"),
        "capabilities": [
            "github.repositories.list",
            "github.repository.read",
            "github.issues.read",
            "github.commits.read",
            "github.issues.create",
            "github.files.write",
        ],
        "verified_at": now_iso(),
    }


@router.delete("/{extension_id}/connection")
async def disconnect_extension_connection(
    extension_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Disconnect only the current user's grant, without disturbing other accounts."""
    if extension_id not in _default_extensions():
        raise HTTPException(status_code=404, detail="Extension not found")
    user_id = str(user.get("id") or "")
    removed = oauth_store.delete_tokens(extension_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No connection exists for this account")
    remaining = get_store("oauth_tokens").load()
    still_connected = any(
        key.startswith(f"{extension_id}:")
        for key in remaining
    )
    install = _extensions_store()["installed"].get(extension_id)
    if install and not still_connected:
        install["connected"] = False
        install["connected_at"] = None
        install["status"] = "needs_connection"
        install.pop("connected_by", None)
        get_store("extensions").save()
    return {"success": True, "connection": extension_id, "connected": False}


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
    available = _default_extensions()
    if extension_id not in available:
        raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
    data = _extensions_store()
    inst = _installed_state(data, extension_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Extension not installed")
    if not inst.get("enabled", False):
        raise HTTPException(status_code=409, detail="Extension is disabled")
    if extension_id == "github":
        user_id = str(user.get("id") or "")
        token = oauth_store.access_token(extension_id, user_id)
        if not token:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "authorization_required",
                    "service": "GitHub",
                    "resource": "repository",
                    "required_permission": "Authorize GitHub for this account",
                    "current_permission": "No account-scoped GitHub grant",
                    "remediation": "Connect GitHub from the Connections center.",
                },
            )
        actions = {
            "github.repositories.list": "list_repos",
            "github.repository.read": "get_repo",
            "github.issues.read": "list_issues",
            "github.commits.read": "list_commits",
            "github.issues.create": "create_issue",
            "github.files.write": "update_file",
        }
        action = actions.get(body.capability)
        if not action:
            raise HTTPException(status_code=400, detail="Unsupported GitHub capability")
        if action in {"create_issue", "update_file"} and not body.confirmed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "confirmation_required",
                    "service": "GitHub",
                    "operation": body.capability,
                    "target": f"{body.params.get('owner', '')}/{body.params.get('repo', '')}",
                    "consequence": "This request writes to the authorized GitHub repository.",
                },
            )
        from ..capability import ExecutionContext
        from ..capabilities.tools.github import GitHubTool

        tool_result = await GitHubTool().execute(
            action,
            body.params,
            ExecutionContext(
                user_id=user_id,
                session_id=str(body.params.get("session_id") or "extension-invoke"),
                metadata={"confirmed": body.confirmed},
            ),
        )
        if not tool_result.get("success"):
            status_code = 403 if tool_result.get("status_code") == 403 else 502
            raise HTTPException(
                status_code=status_code,
                detail={
                    "code": tool_result.get("error_type", "github_execution_failed"),
                    "service": "GitHub",
                    "operation": body.capability,
                    "resource": f"{body.params.get('owner', '')}/{body.params.get('repo', '')}",
                    "required_permission": (
                        "contents:write (OAuth App scope: repo)"
                        if body.capability == "github.files.write"
                        else "issues:write (OAuth App scope: repo)"
                        if body.capability == "github.issues.create"
                        else "Read access to the requested repository"
                    ),
                    "current_permission": tool_result.get("error", "GitHub denied the request"),
                    "reason": tool_result.get("error", "GitHub operation failed"),
                    "remediation": (
                        "Reauthorize with the required scope, confirm repository access, and check organization SSO or GitHub App policy."
                    ),
                },
            )
        return {
            "success": True,
            "extension": extension_id,
            "capability": body.capability,
            "result": tool_result.get("data", {}),
        }
    _require_admin(user)
    if _connect_type(extension_id) == "api_key":
        user_id = str(user.get("id") or "")
        key = body.api_key or _stored_api_key(extension_id, user_id) or _env_api_key(extension_id)
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
