"""Hugging Face Hub client — registry / dataset / artifact role (spec §9, §21).

Real, credentialed operations against ``https://huggingface.co/api``:

* ``whoami`` authentication probe mapped onto the canonical
  :class:`~providers.health.HealthStatus` vocabulary (``unconfigured`` /
  ``authentication_failed`` / ``forbidden`` / ``rate_limited`` / ``timeout`` /
  ``unavailable`` / ``healthy``) — never an assumed status.
* ``discover_models`` — a real :class:`HfModelInfo` view of the live Hub search
  API.  Entries carry the exact repo ``sha`` (revision), pipeline tag and
  downloads/likes, so catalogs are never a hardcoded popularity list.

Only the *registry* role lives here.  Inference (chat/stream/embeddings) stays
in ``client.py`` and requires ``JARVIS_HF_INFERENCE_ENDPOINT`` — a Hub *repo*
is never treated as an inference endpoint (spec §9).
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from ..capabilities import Capability, serialize, validate_capabilities
from ..health import HealthStatus, ProviderHealth
from ..models import (
    CostClass,
    DeploymentKind,
    PrivacyClass,
    ProviderModel,
)

#: Default API root for the public Hub.
DEFAULT_API_BASE = "https://huggingface.co"

#: Per-call socket/user-agent timeouts for hub probes (never infinite).
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "jarvis-provider-fabric/1.0"

#: pipeline tag -> honest capability set (registry-role only; a pipeline tag
#: proves *published* intent, not that an endpoint serves it).
_PIPELINE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "text-generation": frozenset({Capability.CHAT, Capability.REASONING, Capability.STRUCTURED_OUTPUT}),
    "text2text-generation": frozenset({Capability.CHAT}),
    "image-text-to-text": frozenset({Capability.CHAT, Capability.VISION}),
    "text-embeddings-inference": frozenset({Capability.EMBEDDINGS}),
    "feature-extraction": frozenset({Capability.EMBEDDINGS}),
    "sentence-similarity": frozenset({Capability.EMBEDDINGS}),
    "text-classification": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "token-classification": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "zero-shot-classification": frozenset({Capability.CHAT}),
    "question-answering": frozenset({Capability.CHAT}),
    "summarization": frozenset({Capability.CHAT}),
    "fill-mask": frozenset({Capability.CHAT}),
    "translation": frozenset({Capability.CHAT}),
    "image-classification": frozenset({Capability.CHAT, Capability.VISION}),
    "automatic-speech-recognition": frozenset({Capability.AUDIO}),
    "text-to-audio": frozenset({Capability.AUDIO}),
    "audio-classification": frozenset({Capability.AUDIO}),
    "text-to-image": frozenset({Capability.CHAT}),
    "sentence-pair-classification": frozenset({Capability.CHAT}),
}


class HubError(Exception):
    """Base error for the Hub registry role."""


class HubAuthError(HubError):
    """401 — the configured token is rejected by the Hub."""


class HubForbiddenError(HubError):
    """403 — token is valid but lacks permission for the requested resource."""


class HubRateLimitedError(HubError):
    """429 — rate limited or the account is over quota."""


class HubTimeoutError(HubError):
    """The Hub did not answer within the probe timeout."""


class HubUnavailableError(HubError):
    """Transport-level failure (offline/unreachable) or 5xx."""


@dataclass(frozen=True)
class HfModelInfo:
    """One model row discovered from the live Hub search API (spec §2).

    Honest by construction: ``architecture`` and ``context_length`` are omitted
    unless the Hub actually reports them; ``capabilities`` derive from the
    published pipeline tag (an intent, never a served guarantee).
    """

    model_id: str
    author: str = ""
    sha: str = ""
    pipeline_tag: str = ""
    downloads: int = 0
    likes: int = 0
    gated: bool = False
    private: bool = False
    tags: frozenset[str] = frozenset()
    capabilities: frozenset[Capability] = frozenset()
    architecture: str = "unknown"
    context_length: Optional[int] = None
    source: str = "huggingface-hub"
    discovered_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", validate_capabilities(self.capabilities))

    def to_provider_model(self, provider: str = "hf") -> ProviderModel:
        """Convert into a fabric :class:`ProviderModel`.

        Cost stays unknown (no invented pricing); capability set is the
        pipeline-derived intent; deployment is ``REMOTE_ENDPOINT`` so a repo is
        never confused with a served model.
        """
        meta = {
            "hub_sha": self.sha,
            "pipeline_tag": self.pipeline_tag,
            "downloads": self.downloads,
            "likes": self.likes,
            "gated": self.gated,
            "architecture": self.architecture,
            "source": self.source,
            "discovered_at": self.discovered_at,
        }
        return ProviderModel(
            provider=provider,
            model_id=self.model_id,
            name=self.model_id.split("/")[-1],
            deployment=DeploymentKind.REMOTE_ENDPOINT,
            context_length=self.context_length or 0,
            capabilities=self.capabilities,
            pricing_per_1k=(None, None),
            cost_class=CostClass.MEDIUM,
            privacy_class=PrivacyClass.PUBLIC if not self.gated else PrivacyClass.INTERNAL,
            latency_class="high",
            metadata=meta,
        )


def capabilities_for_pipeline(pipeline_tag: str | None) -> frozenset[Capability]:
    """Map a Hub ``pipeline_tag`` to the honest capability set, or empty."""
    if not pipeline_tag:
        return frozenset()
    return _PIPELINE_CAPABILITIES.get(pipeline_tag, frozenset())


def _request_json(url: str, headers: dict | None = None, timeout: float = DEFAULT_TIMEOUT):
    """GET ``url`` and return the decoded JSON on 2xx.

    Raises the classified :class:`HubError` subclasses otherwise.
    """
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0))
        if code == 401:
            raise HubAuthError(f"hf hub: 401 authentication failed ({url})") from exc
        if code == 403:
            raise HubForbiddenError(f"hf hub: 403 forbidden ({url})") from exc
        if code == 429:
            raise HubRateLimitedError(f"hf hub: 429 rate limited ({url})") from exc
        raise HubUnavailableError(f"hf hub: HTTP {code} ({url})") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise HubTimeoutError(
            f"hf hub: no response within {timeout}s ({url})"
        ) from exc
    except TypeError as exc:  # pragma: no cover - guard for py3.7 builds
        raise HubTimeoutError(f"hf hub: timeout probe ({url})") from exc
    except urllib.error.URLError as exc:
        raise HubUnavailableError(f"hf hub: unreachable ({exc.reason})") from exc
    except OSError as exc:
        raise HubUnavailableError(f"hf hub: transport error ({exc})") from exc


def whoami_token(
    token: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict]:
    """Probe ``/api/whoami-v2`` with ``token``; return ``(status, payload)``.

    Raises one of the :class:`HubError` subclasses on failure, or returns
    ``(status, payload_dict)`` on success.
    """
    url = f"{api_base.rstrip('/')}/api/whoami-v2"
    status, payload = _request_json(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        payload = {}
    return status, payload


def hf_auth_probe(
    token: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    timeout: float = DEFAULT_TIMEOUT,
) -> ProviderHealth:
    """Real authentication/availability probe for the Hub registry role.

    Uses the canonical :class:`HealthStatus` status vocabulary; the *only*
    truth sources are the live Hub response codes and the configured token.
    """
    if not token:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.UNCONFIGURED,
            detail="no token configured (set JARVIS_HF_TOKEN or HF_TOKEN)",
        )
    try:
        whoami_token(token, api_base=api_base, timeout=timeout)
    except HubAuthError as exc:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.AUTHENTICATION_FAILED,
            detail=str(exc),
        )
    except HubForbiddenError as exc:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.FORBIDDEN,
            detail=str(exc),
        )
    except HubRateLimitedError as exc:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.RATE_LIMITED,
            detail=str(exc),
        )
    except HubTimeoutError as exc:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.TIMEOUT,
            detail=str(exc),
        )
    except HubUnavailableError as exc:
        return ProviderHealth(
            provider="hf",
            status=HealthStatus.UNAVAILABLE,
            detail=str(exc),
        )
    return ProviderHealth(
        provider="hf",
        status=HealthStatus.HEALTHY,
        detail="hf hub: authenticated",
    )


def _identity_name(username: str, model_id: str) -> str:
    author = username or (model_id.split("/", 1)[0] if "/" in model_id else "")
    repo = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    return f"{author}/{repo}".strip("/")


def discover_models(
    token: str | None = None,
    *,
    search: str | None = None,
    author: str | None = None,
    limit: int = 20,
    pipeline_tag: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HfModelInfo]:
    """Discover models from the live Hub search API (spec §2).

    ``limit`` is clamped to ``1..200``.  The optional token lifts the public
    rate limit and reveals gated/private rows; results otherwise reflect real
    Hub telemetry (downloads/likes), the exact revision ``sha`` and the
    published pipeline tag.
    """
    params: dict[str, str | int] = {
        "limit": max(1, min(int(limit), 200)),
        "sort": "downloads",
        "direction": "-1",
    }
    if search:
        params["search"] = search
    if author:
        params["author"] = author
    if pipeline_tag:
        params["pipeline_tag"] = pipeline_tag
    url = f"{api_base.rstrip('/')}/api/models?{urllib.parse.urlencode(params)}"

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, data = _request_json(url, headers=headers, timeout=timeout)
    if status != 200 or not isinstance(data, list):
        return []

    results: list[HfModelInfo] = []
    seen: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id", "")).strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        pipeline = str(row.get("pipeline_tag") or "") or ""
        gated = bool(row.get("gated") or False)
        private = bool(row.get("private") or False)
        tags = frozenset(str(t) for t in row.get("tags") or [] if t)
        downloads = int(row.get("downloads") or 0)
        likes = int(row.get("likes") or 0)
        sha = str(row.get("sha") or row.get("lastModified") or "") or ""
        results.append(
            HfModelInfo(
                model_id=model_id,
                author=_identity_name("", model_id).split("/", 1)[0],
                sha=sha,
                pipeline_tag=pipeline,
                downloads=downloads,
                likes=likes,
                gated=gated,
                private=private,
                tags=tags,
                capabilities=capabilities_for_pipeline(pipeline),
            )
        )
    results.sort(key=lambda info: (info.downloads, info.likes), reverse=True)
    return results[:limit]