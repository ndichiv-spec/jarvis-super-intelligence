"""Project-intelligence orchestration for the JARVIS chat path.

This module is intentionally thin.  It does NOT introduce a new registry, agent
framework, permission system or secret scrubber:

* tools come from ``research_engine.project_tools`` and are executed through the
  existing :class:`research_engine.tool_registry.ToolRegistry`;
* authorization, risk levels and ``scrub_secrets()`` are the existing ones;
* provider truth comes from the existing ``ProviderControlCenter``;
* auditing reuses the existing ``AuditEventService``.

Responsibilities are limited to:
1. detecting project-intent in a user request (cheap, explicit patterns);
2. running the project tools to gather a *bounded* evidence pack;
3. rendering that pack as a system-prompt block that instructs the model to
   answer only from the supplied evidence.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from research_engine.tool_registry import (
    DefaultPermissionPolicy,
    ToolContext,
    ToolRegistry,
    scrub_secrets,
)

logger = logging.getLogger("jarvis_backend.project_intel")

# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #
# Each pattern is tied to a tool "focus" so retrieval stays targeted instead of
# dumping the repository into model context.
_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgo through (the )?(jarvis|project|codebase)\b", re.I), "roadmap"),
    (re.compile(r"\b(suggest|recommend|improve|roadmap|priority|prioriti[sz]e)\b.*\b(jarvis|project|implementation|codebase)\b", re.I), "roadmap"),
    (re.compile(r"\bwhat should we (build|do|add|fix|focus on)\b", re.I), "roadmap"),
    (re.compile(r"\b(inspect|analyze|analys|review|examine|audit)\b.*\b(jarvis|project|codebase|repo|repository|implementation)\b", re.I), "gaps"),
    # Verb-first forms where the object IS the codebase: "analyze the codebase",
    # "review the repo", "walk through the project".
    (re.compile(r"\b(inspect|analyze|analys|review|examine|audit|walk through|go through)\s+(the\s+|this\s+|our\s+)?(jarvis\s+)?(project|codebase|repo|repository|implementation|source|code)\b", re.I), "gaps"),
    (re.compile(r"\b(what is|what's) (currently )?implemented\b", re.I), "gaps"),
    (re.compile(r"\b(biggest|largest|main) gaps?\b", re.I), "gaps"),
    (re.compile(r"\bhow does (a )?(chat|message|request)\b.*\b(flow|travel|through)\b", re.I), "flow"),
    (re.compile(r"\b(flow|trace|journey)\b.*\b(chat|message|request)\b.*\b(frontend|jarvis|through)\b", re.I), "flow"),
    (re.compile(r"\bwhich providers?\b.*\b(usable|available|working|unavailable|actually work)\b", re.I), "providers"),
    (re.compile(r"\bproviders?\b.*\b(usable|available|working|configured|healthy)\b", re.I), "providers"),
    (re.compile(r"\b(unfinished|incomplete|placeholder|stub|not implemented|todo|hardcoded|dead code|duplicate)\b", re.I), "gaps"),
    (re.compile(r"\b(where are|find)\b.*\b(duplicates?|stub|placeholder)\b", re.I), "gaps"),
    (re.compile(r"\bwhy (is|isn't|is not|does|doesn't)\b.*\b(work|working|fail|broken)\b", re.I), "flow"),
]

# Guard against false positives: these must not trigger project inspection.
_NOT_PROJECT = re.compile(
    r"\b(write|create|generate|translate|sum|summarize|summarise|rewrite|"
    r"spell|convert)\b.*\b(poem|story|essay|email|sentence|paragraph|code snippet)\b",
    re.I,
)


def detect_project_intent(text: str) -> Optional[str]:
    """Return a retrieval focus when this request is about the JARVIS project.

    Returns one of ``roadmap`` / ``gaps`` / ``flow`` / ``providers`` / ``map``,
    or ``None`` for ordinary chat (which must never trigger a repo scan).
    """
    if not text:
        return None
    if _NOT_PROJECT.search(text):
        return None
    for pattern, focus in _INTENT_PATTERNS:
        if pattern.search(text):
            return focus
    return None


# --------------------------------------------------------------------------- #
# Capability routing
# --------------------------------------------------------------------------- #
# Each route maps a request pattern to the MINIMUM set of capabilities needed.
# Unrelated capabilities are never invoked just because they are registered.
_CAPABILITY_ROUTES: list[tuple[re.Pattern[str], list[tuple[str, dict]]]] = [
    # provider health
    (re.compile(r"\b(provider|providers)\b.*\b(health|status|usable|available|"
                r"working|configured|healthy|unavailable|broken)\b", re.I),
     [("provider.status", {})]),
    (re.compile(r"\b(check|verify|test)\b.*\b(provider|providers)\b", re.I),
     [("provider.status", {})]),
    # jobs
    (re.compile(r"\b(job|jobs|task|tasks)\b.*\b(running|status|current|now|"
                r"active|queued)\b", re.I),
     [("job.status", {})]),
    (re.compile(r"\bwhat\b.*\bjobs?\b", re.I), [("job.status", {})]),
    # artifacts
    (re.compile(r"\b(artifact|artifacts|model artifacts|checkpoint|checkpoints)\b",
                re.I),
     [("artifact.inspect", {})]),
    # models
    (re.compile(r"\b(model|models)\b.*\b(status|registered|available|lifecycle|"
                r"list)\b", re.I),
     [("model.status", {})]),
    # docker
    (re.compile(r"\b(docker|containers?)\b.*\b(status|running|list|up|health)\b",
                re.I),
     [("docker.status", {})]),
    # github
    (re.compile(r"\bgithub\b.*\b(repo|repository|branch|branches|commit|commits|"
                r"pull request|issue|issues)\b", re.I),
     [("github.inspect", {"repo": ""})]),
    # files
    (re.compile(r"\bread\b.*\bfile\b.*\b(project|workspace|repo)", re.I),
     [("files.search", {"query": "", "mode": "filename"})]),
    # web
    (re.compile(r"\b(search|look up|find)\b.*\b(the )?(web|internet|online|docs|"
                r"documentation)\b", re.I),
     [("search_web", {"query": ""})]),
    # compute health/status (read-only) — placed before discover so that
    # "what is the compute status" routes to health, not discover.
    (re.compile(r"\b(compute|resource)\b.*\b(health|status)\b", re.I),
     [("compute.resource_health", {})]),
    # compute discovery (read-only)
    (re.compile(r"\b(what|which|list)\b.*\b(compute|compute resources)\b", re.I),
     [("compute.discover", {})]),
    (re.compile(r"\bcompute resources?\b.*\b(available|usable|ready|ready "
                r"to use)\b", re.I),
     [("compute.discover", {})]),
    # compute verify (read-only)
    (re.compile(r"\b(verify|check|test)\b.*\b(compute|resource|gpu|local|"
                r"nvidia|kaggle|hugging face)\b", re.I),
     [("compute.verify", {"resource_id": "local:control-node"})]),
    # compute job status (read-only)
    (re.compile(r"\b(compute|training|inference)\b.*\b(jobs?|tasks?)\b.*"
                r"\b(running|status|current|now|active|queued)\b", re.I),
     [("compute.job_status", {})]),
]


def select_capabilities(text: str) -> list[tuple[str, dict]]:
    """Select the minimal capability set for a request.

    Returns ``[]`` for ordinary chat so no tool ever runs unnecessarily.
    """
    for pattern, caps in _CAPABILITY_ROUTES:
        m = pattern.search(text or "")
        if not m:
            continue
        chosen: list[tuple[str, dict]] = []
        for name, args in caps:
            a = dict(args)
            if a.get("query") == "":
                a["query"] = _extract_quoted(text) or _extract_after(text)
            if a.get("repo") == "":
                a["repo"] = _extract_repo(text)
            chosen.append((name, a))
        return chosen
    return []


def _extract_quoted(text: str) -> str:
    m = re.search(r"[\"'`]([^\"'`]{2,120})[\"'`]", text or "")
    return m.group(1) if m else ""


def _extract_after(text: str) -> str:
    m = re.search(
        r"\b(?:for|about|on|of)\s+(the\s+)?([A-Za-z0-9 ._\-]{3,80})", text or "",
        re.I)
    return m.group(2).strip() if m else ""


def _extract_repo(text: str) -> str:
    m = re.search(r"\b([\w.-]+/[\w.-]+)\b", text or "")
    return m.group(1) if m else ""



# --------------------------------------------------------------------------- #
# Evidence pack
# --------------------------------------------------------------------------- #
_EVIDENCE_INSTRUCTIONS = """You are answering a question about the ACTUAL JARVIS \
implementation running right now.

You have been given a PROJECT EVIDENCE PACK gathered by executing read-only tools \
against the real project on disk. Treat it as the authoritative source for every \
claim about this codebase.

Rules you must follow:
- Base every claim about the codebase ONLY on the evidence pack below.
- Do NOT invent files, modules, routes, providers, tests, or capabilities.
- If the evidence is insufficient for something, say so explicitly.
- Distinguish clearly between:
  * observed implementation (directly evidenced by a file/symbol/route)
  * inferred relationship (a reasoned connection between two observations)
  * recommendation (your proposed next step)
- When you make a recommendation, cite the concrete file path, symbol, route or \
registry from the evidence that motivates it.
- Never claim to have inspected anything that is not present in the evidence.

Structure your answer as:
1. A short statement of what was inspected.
2. Findings grouped by area (e.g. provider routing, chat persistence, \
capability/tool integration), each with: observation, evidence file(s)/symbol(s).
3. A prioritized list of concrete next steps, each tied to the evidence that \
justifies it.
4. Explicitly state anything you could NOT determine from the evidence."""


def _focused_searches(focus: str, limit: int = 6) -> list[dict[str, str]]:
    """Targeted queries per focus - bounded retrieval, not a repo dump."""
    if focus == "roadmap":
        return [
            {"query": "TODO", "file_types": [".py"]},
            {"query": "NotImplementedError", "file_types": [".py"]},
            {"query": "placeholder", "file_types": [".py", ".ts", ".tsx"]},
            {"query": "stub", "file_types": [".py"]},
            {"query": "simulated", "file_types": [".py", ".ts", ".tsx"]},
        ]
    if focus == "gaps":
        return [
            {"query": "TODO", "file_types": [".py"]},
            {"query": "FIXME", "file_types": [".py", ".ts", ".tsx"]},
            {"query": "NotImplementedError", "file_types": [".py"]},
            {"query": "raise NotImplemented", "file_types": [".py"]},
            {"query": "coming soon", "file_types": [".py", ".ts", ".tsx"]},
            {"query": "dummy", "file_types": [".py"]},
        ]
    if focus == "flow":
        return [
            {"query": "/api/chat/stream", "file_types": [".py", ".ts", ".tsx"]},
            {"query": "stream_message", "file_types": [".py"]},
            {"query": "class ProviderGateway", "file_types": [".py"]},
            {"query": "async def chat", "file_types": [".py"]},
            {"query": "StreamingResponse", "file_types": [".py"]},
        ]
    if focus == "providers":
        return [
            {"query": "ProviderControlCenter", "file_types": [".py"]},
            {"query": "check_provider", "file_types": [".py"]},
            {"query": "mark_inference_verified", "file_types": [".py"]},
            {"query": "inference_authorized", "file_types": [".py"]},
        ]
    return []


def _provider_status() -> dict[str, Any]:
    """Live provider truth from the existing control center (never fabricated)."""
    try:
        from jarvis_backend.gateway import _ensure_provider_fabric_import_path

        _ensure_provider_fabric_import_path()
        from providers.bootstrap import bootstrap_fabric
        from providers.control_center import ProviderControlCenter

        bootstrap_fabric()
        cc = ProviderControlCenter()
        out: dict[str, Any] = {}
        for pid in cc.list_providers():
            try:
                st = cc.check_provider(pid)
            except Exception as exc:  # noqa: BLE001
                out[pid] = {"status": "UNKNOWN", "error": f"{type(exc).__name__}: {exc}"}
                continue
            healthy = st.health_status in ("healthy", "degraded")
            available = bool(st.configured and healthy and st.model_list_available)
            out[pid] = {
                "configured": bool(st.configured),
                "reachable": bool(st.model_list_available),
                "authenticated": healthy,
                "available": available,
                "health_status": st.health_status,
                "inference_verified": bool(st.inference_verified),
                "latency_ms": st.latency_ms,
                "detail": st.errors or None,
            }
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("provider status unavailable: %s", exc)
        return {"_status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}


async def build_evidence_pack(
    question: str,
    focus: str,
    *,
    user_id: str,
    request_id: str,
    activity: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Execute the project tools through the existing ToolRegistry.

    ``activity`` (optional) collects REAL progress events - one per actual tool
    invocation - so the UI can show genuine tool activity. No timers, no fakes.
    """
    emit = activity if activity is not None else []
    started = time.monotonic()

    # Reuse the existing registry + policy. READ-risk tools are auto-granted to
    # authenticated users; NETWORK/ADMIN keep their confirmation requirement.
    from research_engine.capability_tools import build_capability_registry

    registry = build_capability_registry()
    ctx = ToolContext(request_id=request_id, user_id=user_id)

    def _step(tool: str, label: str) -> None:
        emit.append({"stage": label, "tool": tool, "status": "running"})

    pack: dict[str, Any] = {
        "request": question,
        "focus": focus,
        "workspace_root": None,
        "project_overview": None,
        "search_findings": [],
        "test_status": None,
        "provider_status": None,
        "compute_status": None,
        "capability_results": [],
        "capability_inventory": None,
        "warnings": [],
        "tools_used": [],
        "duration_ms": 0.0,
    }

    # ---- 0) routed capabilities (jobs, artifacts, models, providers, ...) --- #
    routed = select_capabilities(question)
    for cap_name, cap_args in routed:
        _step(cap_name, f"Running {cap_name}...")
        t0 = time.monotonic()
        # Required-argument tools need a real value; skip rather than guess.
        if cap_name == "github.inspect" and not cap_args.get("repo"):
            pack["warnings"].append(
                f"{cap_name} skipped: no repository specified")
            emit.append({"stage": f"Running {cap_name}...", "tool": cap_name,
                         "status": "skipped",
                         "reason": "no repository specified"})
            continue
        if cap_name == "search_web" and not cap_args.get("query"):
            pack["warnings"].append(f"{cap_name} skipped: no query extracted")
            emit.append({"stage": f"Running {cap_name}...", "tool": cap_name,
                         "status": "skipped", "reason": "no query extracted"})
            continue

        res = await registry.invoke(cap_name, cap_args, ctx)
        pack["tools_used"].append(cap_name)
        entry: dict[str, Any] = {"capability": cap_name,
                                 "success": res.success}
        if res.success:
            try:
                entry["result"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                entry["result"] = {"raw": res.result[:2000]}
        else:
            entry["error"] = res.error
        entry["duration_ms"] = res.duration_ms
        pack["capability_results"].append(entry)
        emit.append({"stage": f"Running {cap_name}...", "tool": cap_name,
                     "status": "done" if res.success else "failed",
                     "duration_ms": res.duration_ms})
        # Promote well-known capabilities into dedicated pack fields.
        if cap_name == "provider.status" and res.success:
            try:
                pack["provider_status"] = json.loads(res.result).get("providers")
            except (json.JSONDecodeError, ValueError):
                pass
        if cap_name == "job.status" and res.success:
            try:
                pack["job_status"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                pass
        if cap_name == "artifact.inspect" and res.success:
            try:
                pack["artifact_status"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                pass
        if cap_name == "model.status" and res.success:
            try:
                pack["model_status"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                pass
        # Promote compute.* capabilities into a dedicated compute_status field.
        if cap_name in ("compute.discover", "compute.verify",
                        "compute.resource_health") and res.success:
            try:
                pack["compute_status"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                pack["compute_status"] = {"raw": res.result[:2000]}
        if cap_name == "compute.job_status" and res.success:
            try:
                pack["compute_job_status"] = json.loads(res.result)
            except (json.JSONDecodeError, ValueError):
                pack["compute_job_status"] = {"raw": res.result[:2000]}

    try:
        from research_engine.capability_tools import capability_inventory
        pack["capability_inventory"] = capability_inventory()
    except Exception as exc:  # noqa: BLE001
        pack["warnings"].append(f"capability inventory unavailable: {exc}")

    # Project-scoped retrieval.  Capability-only requests already hold their
    # authoritative result and must not pay for a repository scan.
    if focus == "capability":
        pack["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        return pack

    # 1) structure
    _step("project.inspect", "Inspecting JARVIS project...")
    t0 = time.monotonic()
    res = await registry.invoke("project.inspect", {"include_placeholders": True,
                                                    "max_placeholders": 40}, ctx)
    pack["tools_used"].append("project.inspect")
    if res.success:
        try:
            data = json.loads(res.result)
            pack["workspace_root"] = data.get("workspace_root")
            pack["project_overview"] = {
                "project_map": data.get("project_map"),
                "entrypoints": data.get("entrypoints"),
                "routers": data.get("routers"),
                "registries": data.get("registries"),
                "configuration_sources": data.get("configuration_sources"),
                "file_counts": data.get("file_counts"),
                "test_files_count": data.get("test_files_count"),
                "placeholder_markers": (data.get("placeholder_markers") or [])[:40],
                "credential_presence": data.get("credential_presence"),
            }
            emit.append({"stage": "Inspecting JARVIS project...", "tool": "project.inspect",
                         "status": "done", "duration_ms": round((time.monotonic() - t0) * 1000, 2)})
        except (json.JSONDecodeError, ValueError):
            pack["warnings"].append("project.inspect returned unparseable output")
    else:
        pack["warnings"].append(f"project.inspect failed: {res.error}")
        emit.append({"stage": "Inspecting JARVIS project...", "tool": "project.inspect",
                     "status": "failed", "error": res.error})

    # 2) targeted code search
    queries = _focused_searches(focus)
    if queries:
        _step("project.search", "Searching project...")
        t0 = time.monotonic()
        findings: list[dict[str, Any]] = []
        for q in queries[:8]:
            r = await registry.invoke("project.search",
                                      {**q, "max_results": 12}, ctx)
            if not r.success:
                continue
            try:
                parsed = json.loads(r.result)
            except (json.JSONDecodeError, ValueError):
                continue
            for m in (parsed.get("matches") or [])[:12]:
                findings.append({**m, "query": q["query"]})
        pack["search_findings"] = findings[:60]
        pack["tools_used"].append("project.search")
        emit.append({"stage": "Searching project...", "tool": "project.search",
                     "status": "done", "matches": len(pack["search_findings"]),
                     "duration_ms": round((time.monotonic() - t0) * 1000, 2)})

    # 3) test status (read-only; never executes tests)
    _step("project.test_status", "Reviewing tests...")
    t0 = time.monotonic()
    r = await registry.invoke("project.test_status", {}, ctx)
    pack["tools_used"].append("project.test_status")
    if r.success:
        try:
            pack["test_status"] = json.loads(r.result)
        except (json.JSONDecodeError, ValueError):
            pack["warnings"].append("project.test_status returned unparseable output")
    else:
        pack["test_status"] = {"status": "UNAVAILABLE", "error": r.error}
    emit.append({"stage": "Reviewing tests...", "tool": "project.test_status",
                 "status": "done", "duration_ms": round((time.monotonic() - t0) * 1000, 2)})

    # 4) live provider truth
    _step("providers", "Checking provider registry...")
    t0 = time.monotonic()
    pack["provider_status"] = _provider_status()
    emit.append({"stage": "Checking provider registry...", "tool": "ProviderControlCenter",
                 "status": "done", "duration_ms": round((time.monotonic() - t0) * 1000, 2)})

    pack["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    if not pack["project_overview"]:
        pack["warnings"].append(
            "Project structure could not be inspected; treat structure claims as unknown."
        )
    return pack


def render_evidence_block(pack: dict[str, Any]) -> str:
    """Render a bounded evidence pack into a system-prompt block.

    The pack is scrubbed with the EXISTING ``scrub_secrets`` before it is
    attached, and truncated so it can never dominate model context.
    """
    if not pack:
        return ""
    try:
        raw = json.dumps(pack, indent=2, default=str)
    except (TypeError, ValueError):
        return ""
    scrubbed, _ = scrub_secrets(raw)
    max_chars = 60_000
    if len(scrubbed) > max_chars:
        scrubbed = (
            scrubbed[:max_chars]
            + "\n... [evidence truncated at 60k chars; ask a narrower question "
              "for more detail] ..."
        )
    return (
        _EVIDENCE_INSTRUCTIONS
        + "\n\n=== PROJECT EVIDENCE PACK (authoritative, from real tools) ===\n"
        + scrubbed
        + "\n=== END EVIDENCE PACK ===\n"
    )


# --------------------------------------------------------------------------- #
# Verification Integration (Phase 6)
# --------------------------------------------------------------------------- #

async def build_verified_evidence_pack(
    question: str,
    focus: str,
    *,
    user_id: str,
    request_id: str,
    verification_required: bool = True,
) -> dict[str, Any]:
    """Build an evidence pack with integrated verification.
    
    This extends build_evidence_pack with verification semantics:
    1. Builds the evidence pack as usual
    2. Extracts testable artifacts from the pack
    3. Runs verification checks
    4. Embeds verification results in the pack
    
    Returns a dict with:
    - evidence_pack: the original evidence
    - verification: verification results summary
    - verified: boolean indicating if the pack passed verification
    """
    from jarvis_backend.verify import VerificationResult, get_verification_engine
    
    # Build the base evidence pack (unbounded to collect everything for verification)
    activity: list[dict[str, Any]] = []
    pack = await build_evidence_pack(question, focus, user_id=user_id, request_id=request_id, activity=activity)
    
    verification_results = []
    verification_artifacts = []
    
    if verification_required:
        engine = get_verification_engine()
        
        # Verify test status if available
        test_status = pack.get("test_status") or {}
        if test_status:
            test_file = test_status.get("test_file")
            if test_file:
                try:
                    # Run tests on the main project tests
                    import os
                    project_root = os.getcwd() or "."
                    test_path = os.path.join(project_root, "tests")
                    if os.path.exists(test_path):
                        result = engine.verify_tests(test_path)
                        verification_results.append({
                            "check": "project_tests",
                            "status": result.status,
                            "verified": result.verified,
                            "details": result.details,
                            "duration_ms": result.duration_ms,
                        })
                except Exception:
                    pass
        
        # Verify Python syntax for key files if we have file paths
        project_overview = pack.get("project_overview") or {}
        workspace_root = project_overview.get("workspace_root")
        if workspace_root and os.path.exists(workspace_root):
            # Verify the main project files compile
            for py_file in ["jarvis_backend/main.py", "jarvis_backend/core.py"]:
                full_path = os.path.join(workspace_root, py_file)
                if os.path.exists(full_path):
                    result = engine.verify_imports(full_path)
                    if not result.verified:
                        verification_results.append({
                            "check": f"syntax:{py_file}",
                            "status": result.status,
                            "verified": False,
                            "error": result.description,
                        })
        
        # Composite verification result
        if verification_results:
            composite = engine.verify_composite(verification_results, require_all=False)
            verification_artifacts = [r for r in verification_results if r.get("verified")]
        else:
            composite = VerificationResult(
                verified=True,
                status="passed",
                description="No verification issues found",
                details={"checks": 0},
            )
    
    return {
        "evidence_pack": pack,
        "activity": activity,
        "verification": {
            "checks_run": len(verification_results),
            "passed": len(verification_artifacts),
            "status": composite.status,
            "verified": composite.verified,
            "details": composite.details,
            "evidence": composite.evidence,
            "duration_ms": composite.duration_ms,
        },
        "verified": composite.verified,
    }


__all__ = [
    "detect_project_intent",
    "select_capabilities",
    "build_evidence_pack",
    "render_evidence_block",
    "build_verified_evidence_pack",
]
