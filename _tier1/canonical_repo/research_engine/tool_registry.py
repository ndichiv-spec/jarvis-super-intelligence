"""Tool Registry — the authorization + credential-resolution boundary (Sections 2, 19, 20, 28).

The Brain agent NEVER receives provider credentials.  It receives only the
**description** of each tool (``name`` + ``description`` + JSON ``schema``),
requests an invocation through the registry, and the registry performs
authorization, credential resolution, execution and **secret scrubbing** of the
result before it is ever handed back.

Every concrete tool is a thin adapter over an EXISTING subsystem (Browser,
Sandbox, Knowledge/RAG, Memory, Model Gateway / brain_runtime).  They are
imported lazily so a missing optional dependency degrades to
``PROVIDER_UNAVAILABLE`` / ``BROWSER_UNAVAILABLE`` rather than crashing the
import graph.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .models import (
    ToolCall,
    ToolResult,
    RiskLevel,
    now_iso,
    SearchResult,
)

# High-entropy token patterns that must NEVER reach the model.  We scrub them
# out of every tool result (Section 19/20 secret leakage).  These regexes match
# the *shape* of a credential, not its value: no secret value is ever logged.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-_]{16,}"),
    # OpenAI-style / HuggingFace-style / JWT-looking long tokens
    re.compile(r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{32,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{32,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
]
_REDACTION = "[REDACTED:credential]"


def scrub_secrets(text: Any) -> tuple[str, bool]:
    """Return ``(scrubbed_text, redacted)`` masking credential-shaped substrings."""
    if text is None:
        return "", False
    s = text if isinstance(text, str) else json.dumps(text, default=str)
    redacted = False
    for pat in _SECRET_PATTERNS:
        if pat.search(s):
            s = pat.sub(_REDACTION, s)
            redacted = True
    return s, redacted


# --------------------------------------------------------------------------- #
# Permissions / authorization (Section 20)
# --------------------------------------------------------------------------- #
@dataclass
class Permission:
    """A grant that allows a caller to use a tool at its risk level."""

    tool: str
    risk: RiskLevel
    granted: bool = True
    reason: str = "default"


class PermissionPolicy(ABC):
    """Decides whether a user may run a tool at a given risk level."""

    @abstractmethod
    def authorize(self, user_id: str, tool_name: str, risk: RiskLevel) -> tuple[bool, str]:
        ...


class DefaultPermissionPolicy(PermissionPolicy):
    """Sane defaults: authenticated users may read + run sandboxed code;
    network/write/admin require explicit confirmation (Section 21)."""

    def __init__(self, confirmations: Optional[dict[str, bool]] = None):
        self._confirmations = confirmations or {}

    def authorize(self, user_id: str, tool_name: str, risk: RiskLevel) -> tuple[bool, str]:
        if risk == RiskLevel.READ or risk == RiskLevel.EXEC or risk == RiskLevel.WRITE:
            # READ / local EXEC / local WRITE are auto-granted to authenticated
            # researchers.  WRITE here is local-isolated (research memory file),
            # not an external mutation — external writes are modeled as NETWORK.
            return True, "granted"
        # NETWORK / ADMIN require an explicit confirmation grant (Section 21).
        granted = bool(self._confirmations.get(f"{user_id}:{tool_name}", False))
        if granted:
            return True, "user confirmation recorded"
        return False, "requires_user_confirmation"


# --------------------------------------------------------------------------- #
# Tool abstraction
# --------------------------------------------------------------------------- #
class Tool(ABC):
    """A callable capability the Brain may invoke (Section 20)."""

    name: str = ""
    description: str = ""
    # JSON schema describing the arguments the model may safely supply.
    schema: dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.READ
    requires_confirmation: bool = False

    @abstractmethod
    async def invoke(self, args: dict[str, Any], ctx: "ToolContext") -> ToolResult:
        ...

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.schema,
            "risk": self.risk.value,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass
class ToolContext:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = "anonymous"
    research_dir: Optional[Path] = None
    budgets: Optional[dict[str, Any]] = None
    # Caller authority for capability permission enforcement. ``permissions`` is
    # an explicit grant set; ``principal`` is the user record resolved against
    # the canonical ``roles`` store. Both are optional so existing callers keep
    # working; when a tool declares ``required_permissions`` and neither can be
    # resolved the call is DENIED (fail closed).
    permissions: Optional[set[str]] = None
    principal: Optional[dict[str, Any]] = None


def resolve_permissions(
    user_id: str,
    permissions: Optional[set[str]] = None,
    principal: Optional[dict[str, Any]] = None,
) -> set[str]:
    """Resolve the caller's granted permission strings.

    Reuses the EXISTING RBAC engine (``identity.rbac.PermissionEngine``) and the
    canonical ``roles`` store. No second permission system is introduced.

    Resolution order:
      1. an explicit ``permissions`` set supplied by the caller
      2. ``principal`` resolved through the roles store
      3. ``user_id`` looked up in the canonical users store

    Returns an empty set when the caller cannot be identified, so callers must
    treat "no permissions" as "deny" for tools that declare requirements.
    """
    if permissions is not None:
        return {str(p) for p in permissions}
    try:
        from identity.rbac import PermissionEngine

        from jarvis_backend.core import get_store

        engine = PermissionEngine(get_store("roles"))
        if principal is not None:
            return {str(p) for p in engine.effective_permissions(principal)}
        if user_id and user_id != "anonymous":
            user = get_store("users").load().get(user_id)
            if isinstance(user, dict):
                return {str(p) for p in engine.effective_permissions(user)}
    except Exception:  # noqa: BLE001 - authorization must fail closed, not raise
        return set()
    return set()


def permission_granted(granted: set[str], required: str) -> bool:
    """Wildcard-aware permission match (``*``, ``resource:*``)."""
    if "*" in granted or required in granted:
        return True
    resource, _, action = required.partition(":")
    if f"{resource}:*" in granted:
        return True
    if f"*:{action}" in granted:
        return True
    return False


# --------------------------------------------------------------------------- #
# Concrete tools — thin adapters over EXISTING subsystems
# --------------------------------------------------------------------------- #
class SandboxRunTool(Tool):
    """Execute Python in the existing sandbox (Section 6).

    Prefers the integrated Silverwing sandbox (``silverwing-backend/sandbox``)
    when available; falls back to an isolated subprocess runner with the same
    honest restrictions (timeout, output cap, no network).  Secrets from the
    host environment are never forwarded to the child process.
    """

    name = "sandbox_run"
    description = (
        "Run a Python snippet in an isolated subprocess sandbox with a wall-clock "
        "timeout, output caps and no network access. Returns stdout/stderr/exit code."
    )
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {"type": "number", "description": "seconds (max 20)", "default": 5.0},
        },
        "required": ["code"],
    }
    risk = RiskLevel.EXEC

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        code = str(args.get("code", ""))
        if not code:
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False, error="code is required")
        timeout = float(args.get("timeout", 5.0))

        # Preferred path: the integrated Silverwing sandbox.
        try:
            sw = _try_import_sandbox_module()
            if sw is not None:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: sw.run_code(code, timeout=timeout, memory_limit_mb=128),  # type: ignore[attr-defined]
                )
                return self._to_result(result, ctx)
        except Exception as exc:  # noqa: BLE001
            # Fall through to the honest fallback runner.
            fallback_err = f"integrated sandbox unavailable ({type(exc).__name__}); using isolated fallback"
        else:
            fallback_err = None

        # Fallback: isolated subprocess with hardened env (no secrets forwarded).
        result = await self._fallback_run(code, timeout)
        result.metrics["sandbox_engine"] = "isolated_subprocess"
        if fallback_err:
            result.metrics["fallback_reason"] = fallback_err
        return result

    @staticmethod
    def _to_result(sw_out: Any, ctx: ToolContext) -> ToolResult:
        if isinstance(sw_out, dict):
            ok = bool(sw_out.get("ok"))
            return ToolResult(
                tool_id=ctx.request_id,
                name="sandbox_run",
                success=ok,
                result=(sw_out.get("stdout") or "")[:5000],
                error=sw_out.get("error", "") if not ok else "",
                duration_ms=float(sw_out.get("time", 0.0)) * 1000,
                metrics={"exit_code": sw_out.get("exit_code"), "memory_enforced": sw_out.get("memory_enforced", False)},
                artifacts=[],
            )
        # Already a ToolResult-like object
        return sw_out  # type: ignore[return-value]

    @staticmethod
    async def _fallback_run(code: str, timeout: float) -> ToolResult:
        start = time.monotonic()
        # Honest AST pre-flight: the isolated fallback must enforce the same
        # "no imports / no dangerous I/O" policy as the integrated sandbox.
        violation = _sandbox_ast_violation(code)
        if violation:
            return ToolResult(tool_id="fallback", name="sandbox_run", success=False,
                              error=f"violation: {violation}", duration_ms=(time.monotonic() - start) * 1000,
                              metrics={"exit_code": None, "signal": "violation"})
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Explicit capability grant: NO provider secrets forwarded.
                env={"PATH": os_env_path(), "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_id="fallback", name="sandbox_run", success=False,
                              error=f"spawn failed: {exc}", duration_ms=(time.monotonic() - start) * 1000)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=min(timeout, 20.0))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(tool_id="fallback", name="sandbox_run", success=False,
                              error=f"timed out after {timeout}s", duration_ms=(time.monotonic() - start) * 1000)
        return ToolResult(
            tool_id="fallback",
            name="sandbox_run",
            success=proc.returncode == 0,
            result=out.decode("utf-8", "replace")[:5000],
            error=(err.decode("utf-8", "replace")[:2000] if proc.returncode != 0 else ""),
            duration_ms=(time.monotonic() - start) * 1000,
            metrics={"exit_code": proc.returncode},
        )


class BrowserSearchTool(Tool):
    """Web search/navigation via the EXISTING BrowserEngine (Section 3).

    Delegates to ``jarvis_backend.browser_engine.HttpBrowserEngine`` (the real
    urllib-based engine) through ``get_engine("default")``.  The Brain never
    touches the network directly: it goes through the Tool Registry, which is
    the authorization + credential-resolution boundary.

    Degrades honestly when live web search is not enabled in the current
    deployment (unit tests run without the flag -> BROWSER_UNAVAILABLE; the
    platform launcher and live_verify.py set JARVIS_BROWSER_SEARCH_ENABLED=1).
    Never fabricates results.
    """

    name = "search_web"
    description = (
        "Search the live web and return source URLs with extracted snippets and "
        "provenance. When 'extract' is true, the top result pages are navigated "
        "and their main text extracted so evidence carries the actual source. "
        "Requires network access and explicit user confirmation."
    )
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "search query"},
            "max_results": {"type": "integer", "description": "max sources (default 5)"},
            "extract": {"type": "boolean", "description": "navigate+extract text of top results (default false)"},
        },
        "required": ["query"],
    }
    risk = RiskLevel.NETWORK
    requires_confirmation = True

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # Deployment gate: live web search is an opt-in capability of the
        # platform.  In the unit-test environment it is off -> honest
        # BROWSER_UNAVAILABLE (no fabricated results, no silent network call).
        if not _web_search_enabled():
            return ToolResult(
                tool_id=ctx.request_id, name=self.name, success=False,
                error="BROWSER_UNAVAILABLE: live web search is not enabled in this "
                      "environment (set JARVIS_BROWSER_SEARCH_ENABLED=1 within the "
                      "JARVIS platform)",
                metrics={"available": False},
            )

        query = str(args.get("query", ""))
        if not query:
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error="query is required")
        max_results = int(args.get("max_results", 5))
        do_extract = bool(args.get("extract", False))

        # Resolve the EXISTING engine (never instantiate the abstract base).
        try:
            from jarvis_backend.browser_engine import get_engine  # type: ignore
            engine = get_engine("default")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error=f"BROWSER_WORKER_UNAVAILABLE: {type(exc).__name__}: "
                                    f"{str(exc)[:160]}",
                              metrics={"available": False})

        loop = asyncio.get_event_loop()
        start = time.monotonic()
        # (1) Discovery: search the live web.
        try:
            raw = await loop.run_in_executor(
                None, lambda: engine.search(query, max_results=max_results)
            )
        except Exception as exc:  # noqa: BLE001
            code, msg = _classify_browser_error(exc)
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error=f"{code}: {msg}", metrics={"available": False})

        if not raw:
            return ToolResult(
                tool_id=ctx.request_id, name=self.name, success=True,
                result="no results for query",
                metrics={"results": 0, "available": True,
                         "provider": "duckduckgo/wikipedia",
                         "latency_ms": round((time.monotonic() - start) * 1000, 2)},
            )

        # (2) Normalise into SearchResult artifacts (Section 3 contract).
        results: list[SearchResult] = []
        for i, r in enumerate(raw[:max_results]):
            sr = SearchResult(
                id=f"sr-{uuid.uuid4().hex[:12]}",
                title=str(r.get("title", "")),
                url=str(r.get("url", "")),
                snippet=str(r.get("snippet", "")),
                source=r.get("source", "web"),
                retrieved_at=now_iso(),
                rank=int(r.get("rank", i + 1)),
                provider=r.get("provider", "duckduckgo"),
                domain=r.get("domain", ""),
                metadata=dict(r.get("metadata", {})),
            )
            # (3) Optional navigate + extract so evidence carries the real source.
            if do_extract:
                try:
                    doc = await loop.run_in_executor(
                        None, lambda url=sr.url: engine.fetch_document(url)  # type: ignore[union-attr]
                    )
                except Exception as exc:  # noqa: BLE001
                    sr.navigation_failure = "BROWSER_ENGINE_FAILURE"
                    sr.metadata["fetch_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                else:
                    if doc.get("success"):
                        sr.relevant_content = doc.get("text", "")[:4000]
                        sr.content_excerpt = doc.get("text", "")[:2000]
                        sr.content_type = doc.get("content_type", "")
                        sr.word_count = int(doc.get("word_count", 0))
                        sr.navigation_context = doc.get("navigation_context")
                        sr.metadata["word_count"] = sr.word_count
                        sr.metadata["content_length"] = doc.get("content_length", 0)
                    else:
                        sr.navigation_failure = doc.get("failure_category") or "NETWORK_FAILURE"
                        sr.metadata["fetch_error"] = doc.get("failure", "")
                        sr.navigation_context = doc.get("navigation_context")
            results.append(sr)

        # (4) Build a provenance-rich digest; the ResearchEngine parses this into
        # Evidence via _evidence_from_text, and also consumes the structured
        # artifacts (per-URL provenance) via _evidence_from_artifacts.
        lines: list[str] = []
        for sr in results:
            lines.append(f"[{sr.rank}] {sr.title} ({sr.url})")
            if sr.snippet:
                lines.append(f"    snippet: {sr.snippet}")
            if sr.relevant_content:
                lines.append(f"    content: {sr.relevant_content[:600]}")
            if sr.navigation_failure:
                lines.append(f"    fetch_failure: {sr.navigation_failure}")
            if sr.navigation_context:
                lines.append(f"    presentation: {sr.navigation_context.get('presentation')}")
        digest = "\n".join(lines)

        return ToolResult(
            tool_id=ctx.request_id, name=self.name, success=True,
            result=digest,
            metrics={
                "results": len(results),
                "available": True,
                "extracted": sum(1 for r in results if r.relevant_content),
                "provider": "duckduckgo+lite/wikipedia",
                "latency_ms": round((time.monotonic() - start) * 1000, 2),
                "query": query,
            },
            artifacts=[sr.to_dict() for sr in results],
        )


class KnowledgeRetrieveTool(Tool):
    """RAG retrieval over the EXISTING Knowledge store (Section 9)."""

    name = "knowledge_retrieve"
    description = "Retrieve relevant passages from the local knowledge/RAG index with provenance."
    schema = {"type": "object", "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "default": 5},
    }, "required": ["query"]}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            from infrastructure.knowledge.rag import RAGPipeline  # type: ignore
            from infrastructure.knowledge.retrieval import KnowledgeRetriever, RetrievalConfig  # type: ignore
        except Exception:  # noqa: BLE001 — optional / not on path in some contexts
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error="RAG_UNAVAILABLE: knowledge index not configured",
                              metrics={"available": False})
        query = str(args.get("query", ""))
        limit = int(args.get("limit", 5))
        try:
            retriever = KnowledgeRetriever()
            cfg = RetrievalConfig()
            cfg.chunk_limit = limit
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(None, lambda: retriever.retrieve(query, cfg))
        except Exception as exc:  # noqa: BLE001 — any config/construction error = not configured
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error=f"RAG_UNAVAILABLE: {type(exc).__name__}", metrics={"available": False})
        passages = [getattr(c, "content", str(c))[:400] for c in chunks]
        return ToolResult(
            tool_id=ctx.request_id, name=self.name, success=bool(passages),
            result="\n---\n".join(passages) if passages else "no passages",
            metrics={"results": len(passages), "available": True},
            artifacts=[{"id": getattr(c, "id", ""), "source": getattr(c, "source", "")} for c in chunks],
        )


class MemoryTool(Tool):
    """Durable research-session memory (Section 10).

    Prefers the existing ``memory`` subsystem; when that is not wired up it
    persists to a JSON file under the research workspace so findings are durable
    within a session (never fabricates a memory service).
    """

    name = "memory_store"
    description = "Persist a verified finding to durable research memory."
    schema = {"type": "object", "properties": {
        "key": {"type": "string"}, "value": {"type": "string"},
    }, "required": ["key", "value"]}
    risk = RiskLevel.WRITE

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        key = str(args.get("key", ""))
        value = str(args.get("value", ""))
        store = await _memory_store(ctx)
        store[key] = value
        await store.save()
        return ToolResult(tool_id=ctx.request_id, name=self.name, success=True,
                          result=f"stored {len(value)} chars under {key}",
                          metrics={"backend": store.backend, "entries": len(store)})


class MemoryRecallTool(Tool):
    name = "memory_recall"
    description = "Recall a previously stored research finding by key."
    schema = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        store = await _memory_store(ctx)
        key = str(args.get("key", ""))
        if key in store:
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=True,
                              result=store[key], metrics={"backend": store.backend})
        return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                          error="RECALL_MISS", metrics={"available": True, "backend": store.backend})


class ModelConsultTool(Tool):
    """Consult another model via the Model Gateway / brain_runtime (Section 11).

    Only consults a provider that passes actual health/auth checks; never
    fabricates availability.  The model only sees the resulting text, never the
    credential used upstream.
    """

    name = "model_consult"
    description = "Ask a healthy specialist model a question (only providers passing health checks)."
    schema = {"type": "object", "properties": {
        "question": {"type": "string"},
        "provider": {"type": "string", "description": "preferred provider hint, e.g. 'nvidia'/'openai'/'silverwing'"},
    }, "required": ["question"]}
    risk = RiskLevel.NETWORK

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            from jarvis_backend.gateway import ProviderGateway  # type: ignore
        except Exception:  # noqa: BLE001
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error="PROVIDER_UNAVAILABLE: ProviderGateway not importable",
                              metrics={"available": False})
        question = str(args.get("question", ""))
        provider_hint = args.get("provider")
        gateway = ProviderGateway()
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None, lambda: _consult_via_gateway(gateway, question, provider_hint)  # type: ignore
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=False,
                              error=f"PROVIDER_UNAVAILABLE: {type(exc).__name__}",
                              metrics={"available": False})
        return ToolResult(tool_id=ctx.request_id, name=self.name, success=bool(text),
                          result=text or "", metrics={"available": True})


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class ToolRegistry:
    """Authorization + dispatch boundary between the Brain and all tools."""

    def __init__(self, policy: Optional[PermissionPolicy] = None):
        self._tools: dict[str, Tool] = {}
        self._policy = policy or DefaultPermissionPolicy()
        self._history: list[ToolCall] = []

    def register(self, tool: Tool) -> "ToolRegistry":
        self._tools[tool.name] = tool
        return self

    def describe(self) -> list[dict[str, Any]]:
        """The ONLY shape the model sees — no credentials, no secrets."""
        return [t.describe() for t in self._tools.values()]

    def available(self) -> list[str]:
        """Names of tools that are currently functional (honest liveness)."""
        # All registered tools are potentially available; liveness is checked
        # per-invocation by the tool itself (no fabrication).
        return list(self._tools.keys())

    def authorize(
        self,
        user_id: str,
        tool_name: str,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Authorize a tool call: risk policy first, then capability permissions.

        Both layers fail closed:

        * risk is decided by the existing :class:`PermissionPolicy`
        * if the tool declares ``required_permissions``, the caller must
          actually hold them. Permissions are resolved from the caller context
          and matched wildcard-aware. A caller whose permissions cannot be
          resolved holds none, so the call is denied.

        Tools that declare no ``required_permissions`` keep their previous
        behaviour exactly (risk-only), so unrelated domains are unaffected.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return False, "TOOL_NOT_REGISTERED"
        ok, reason = self._policy.authorize(user_id, tool_name, tool.risk)
        if not ok:
            return False, reason
        required = tuple(getattr(tool, "required_permissions", ()) or ())
        if not required:
            return True, reason
        granted = resolve_permissions(user_id, permissions, principal)
        missing = [p for p in required if not permission_granted(granted, p)]
        if missing:
            # Report only the missing permission names - never the granted set,
            # never a credential.
            return False, "PERMISSION_DENIED:" + ",".join(missing)
        return True, reason

    async def invoke(self, tool_name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Authorize → invoke → scrub secrets, for one tool call."""
        tool = self._tools.get(tool_name)
        if tool is None:
            res = ToolResult(tool_id=ctx.request_id, name=tool_name, success=False,
                             error="TOOL_NOT_REGISTERED")
        else:
            ok, reason = self.authorize(ctx.user_id, tool_name,
                                        ctx.permissions, ctx.principal)
            if not ok:
                res = ToolResult(tool_id=ctx.request_id, name=tool_name, success=False,
                                 error=f"TOOL_DENIED: {reason}")
            else:
                res = await tool.invoke(args, ctx)
        # Secret scrubbing before anything returns to the model (Section 19/28).
        scrubbed, was_redacted = scrub_secrets(res.result)
        if was_redacted:
            res.result = scrubbed
            res.redacted_secrets = True
        if res.error:
            e_scrubbed, red = scrub_secrets(res.error)
            if red:
                res.error = e_scrubbed
                res.redacted_secrets = True
        call = ToolCall(name=tool_name, arguments=dict(args), tool_id=ctx.request_id)
        self._history.append(call)
        return res

    @property
    def history(self) -> list[ToolCall]:
        return list(self._history)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _try_import_sandbox_module():
    """Import the integrated Silverwing sandbox module if on the path."""
    try:
        import sandbox as sw  # type: ignore  # from silverwing-backend on sys.path
        return sw
    except Exception:  # noqa: BLE001
        return None


def os_env_path() -> str:
    return __import__("os").environ.get("PATH", "/usr/bin:/bin")


def _web_search_enabled() -> bool:
    """Deployment gate for live web search (Section 28).

    Returns True only when the running process has opted into live web access
    (the platform launcher ``.start_unified.py`` and ``live_verify.py`` set
    ``JARVIS_BROWSER_SEARCH_ENABLED=1``).  In the unit-test environment the flag
    is absent, so ``BrowserSearchTool`` honestly reports ``BROWSER_UNAVAILABLE``
    rather than fabricating results or making silent network calls.
    """
    return os.environ.get("JARVIS_BROWSER_SEARCH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Sandbox AST guard for the isolated fallback runner (Section 16 policy honesty).
# --------------------------------------------------------------------------- #
import ast as _ast

_BLOCKED_ATTRS = {"os", "sys", "subprocess", "socket", "urllib", "http",
                  "ftplib", "glob", "shutil", "pathlib", "builtins",
                  "importlib", "ctypes", "platform"}


def _sandbox_ast_violation(code: str) -> Optional[str]:
    """Return a human reason if ``code`` violates the sandbox policy, else None."""
    try:
        tree = _ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg}"
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.Import, _ast.ImportFrom)):
            return "imports are blocked in the sandbox"
        if isinstance(node, _ast.Attribute) and isinstance(node.value, _ast.Name):
            if node.value.id in _BLOCKED_ATTRS and node.attr not in ("__name__",):
                return f"access to {node.value.id}.{node.attr} is blocked"
        if isinstance(node, _ast.Call):
            if isinstance(node.func, _ast.Name) and node.func.id in {"eval", "exec", "compile", "__import__", "open"}:
                return f"call to {node.func.id}() is blocked"
    return None


def _classify_browser_error(exc: BaseException) -> tuple[str, str]:
    msg = str(exc)
    if "CERTIFICATE" in msg.upper() or "SSL" in msg.upper() or "TLS" in msg.upper():
        return "TLS_FAILURE", msg
    if "Name or service not known" in msg or "NameResolution" in msg or "getaddrinfo" in msg:
        return "DNS_FAILURE", msg
    if "Connection refused" in msg or "ConnectionError" in type(exc).__name__:
        return "CONNECTION_FAILURE", msg
    if "timed out" in msg.lower():
        return "REQUEST_TIMEOUT", msg
    if "HTTP Error 40" in msg:
        return "HTTP_FAILURE", msg
    if "403" in msg or "401" in msg:
        return "AUTH_REQUIRED", msg
    return "BROWSER_UNAVAILABLE", msg


def _browser_search_fallback(engine: Any, query: str, max_results: int) -> list[dict]:
    # If the engine exposes a higher-level search, it is used above; this is a
    # last-resort single-URL fetch that still yields provenance.
    fetched = getattr(engine, "open_url", None)
    if fetched is None:
        return []
    page = fetched(f"https://html.duckduckgo.com/html/?q={query}")  # type: ignore[operator]
    return [{"url": page, "title": query, "snippet": str(page)[:200]}]


def _consult_via_gateway(gateway: Any, question: str, provider_hint: Optional[str]) -> str:
    """Ask the gateway a question, restricted to a HEALTHY provider only."""
    # The gateway probes provider health; if none are healthy it raises / returns
    # empty.  We never fabricate an answer.
    providers = getattr(gateway, "healthy_providers", None)
    if callable(providers):
        healthy = providers()
    else:
        healthy = getattr(gateway, "list_healthy_providers", lambda: [])()
    if not healthy:
        raise RuntimeError("no healthy provider")
    fn = getattr(gateway, "generate", None) or getattr(gateway, "chat", None)
    if fn is None:
        raise RuntimeError("gateway has no generate/chat method")
    result = fn(question)
    text = result if isinstance(result, str) else getattr(result, "content", getattr(result, "text", str(result)))
    return text or ""


class _JsonMemoryStore:
    """Minimal durable JSON memory for research sessions (Section 10 fallback)."""

    backend = "json"

    def __init__(self, path: Path):
        self._path = path
        self._data: dict[str, str] = {}

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key] = value

    def __len__(self) -> int:
        return len(self._data)

    async def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")


@dataclasses.dataclass
class _MemoryCtx:
    store: _JsonMemoryStore


async def _memory_store(ctx: ToolContext) -> _JsonMemoryStore:
    # Prefer the existing memory subsystem; fall back to a JSON file store.
    try:
        from memory.memory_manager import MemoryManager  # type: ignore  # noqa: F401
        # ... would return a real adapter; the module is a stub here, so fall through.
    except Exception:  # noqa: BLE001
        pass
    path = (ctx.research_dir or Path(".")) / "memory.json"
    store = _JsonMemoryStore(path)
    if path.exists():
        try:
            store._data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            store._data = {}
    return store


# A test-only tool that returns static, well-provenanced evidence without the
# network.  Used to keep the research pipeline deterministic in tests (the live
# path always uses BrowserSearchTool above).  Clearly marked.
class StaticSearchTool(Tool):
    name = "static_search"
    description = "Deterministic, network-free search used only by tests (clearly marked)."
    schema = {"type": "object", "properties": {
        "query": {"type": "string"},
        "max_results": {"type": "integer", "default": 5},
    }, "required": ["query"]}
    risk = RiskLevel.READ

    def __init__(self, knowledge: Optional[dict[str, list[str]]] = None):
        self._knowledge = knowledge or {}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query", "")).lower()
        max_results = int(args.get("max_results", 5))
        results: list[str] = []
        for kw, answers in self._knowledge.items():
            if kw.lower() in query:
                results.extend(answers)
        if not results:
            return ToolResult(tool_id=ctx.request_id, name=self.name, success=True,
                              result="", metrics={"results": 0, "available": True, "url": "static://test"})
        text = "\n\n".join(results[:max_results])
        return ToolResult(tool_id=ctx.request_id, name=self.name, success=True,
                          result=text, metrics={"results": len(results), "available": True, "url": "static://test"})
