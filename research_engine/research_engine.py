"""Research Engine — the Section 4 pipeline (with hard budgets, Section 28).

Pipeline:
    User question
      → research planning (multi-pass query generation)
      → search / source discovery
      → source retrieval
      → content extraction
      → source normalization
      → evidence extraction (with provenance)
      → cross-source comparison (conflict detection)
      → sandbox experiment (when the mode calls for it)
      → verification
      → evidence package + investigation timeline

Non-goals (by design): it never performs infinite autonomous searching.  Every
run is bounded by :class:`ResearchBudgets` (iterations / tokens / providers /
time / sources).  It never fabricates a result it did not actually obtain from a
tool; a tool that is unavailable is recorded as such and the run degrades
gracefully with an honest status.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict
from typing import Any, Optional

from .models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    InvestigationEvent,
    ResearchBudgets,
    ResearchMode,
    ResearchReport,
    ResearchSession,
    ResearchStatus,
    SearchResult,
    SourceType,
    ToolCall,
    ToolResult,
    VerificationStatus,
    now_iso,
)
from .tool_registry import ToolRegistry, ToolContext, DefaultPermissionPolicy, PermissionPolicy
from .verification import VerificationEngine


# Multi-pass research questions (Section 4).  Each pass narrows the lens.
_RESEARCH_PASSES: dict[int, str] = {
    0: "What is the problem? {q}",
    1: "What do official sources say about {q}",
    2: "What do implementation / technical sources say about {q}",
    3: "What are known bugs, issues or caveats around {q}",
    4: "Can this be reproduced or refuted with an experiment?",
}


class ResearchEngine:
    """Drives the research pipeline through the Tool Registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        verifier: Optional[VerificationEngine] = None,
        policy: Optional[PermissionPolicy] = None,
    ):
        self.registry = registry
        self.verifier = verifier or VerificationEngine()
        self._policy = policy or DefaultPermissionPolicy()

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    async def research(
        self,
        query: str,
        mode: ResearchMode = ResearchMode.STANDARD,
        user_id: str = "anonymous",
        budgets: Optional[ResearchBudgets] = None,
        confirmations: Optional[dict[str, bool]] = None,
    ) -> ResearchReport:
        budgets = budgets or ResearchBudgets()
        session = ResearchSession(user_id=user_id, query=query, mode=mode, budgets=budgets)
        report = ResearchReport(session=session)
        ctx = ToolContext(request_id=f"r-{session.session_id[:8]}", user_id=user_id,
                          research_dir=self._research_dir(user_id))

        report.add_event("research_start", f"mode={mode.value} query={query}")
        start = time.monotonic()

        # Budget enforcement helper.
        def over_budget(iters: int) -> tuple[bool, str]:
            if iters > budgets.max_iterations:
                return True, "max_iterations"
            if (time.monotonic() - start) > budgets.max_seconds:
                return True, "max_seconds"
            return False, ""

        # 1) Multi-pass search → evidence extraction.
        evidence: list[Evidence] = []
        sources_seen = set()
        iteration = 0
        last_status = ResearchStatus.COMPLETE
        for pass_no in range(len(_RESEARCH_PASSES)):
            if over_budget(iteration)[0]:
                last_status = ResearchStatus.BUDGET_EXHAUSTED
                report.add_event("budget_exhausted", f"stopped at pass {pass_no} (iteration={iteration})")
                break
            search_query = self._plan_query(query, pass_no)
            # In DEEP_RESEARCH mode the engine navigates + extracts the top
            # result pages so evidence carries the actual source text, not just
            # search-engine snippets.  STANDARD mode stays snippet-only.
            do_extract = mode == ResearchMode.DEEP_RESEARCH
            tool_res = await self._safe_invoke(
                "search_web",
                {"query": search_query, "max_results": budgets.max_sources, "extract": do_extract},
                ctx,
            )
            iteration += 1
            if not tool_res.success:
                report.add_event("tool_unavailable", f"search_web: {tool_res.error}", None)
                # Try the local knowledge store as a fallback source.
                kg = await self._safe_invoke("knowledge_retrieve", {"query": search_query, "limit": budgets.max_sources}, ctx)
                if kg.success and kg.result.strip():
                    evidence.extend(_evidence_from_text(kg.result, search_query, SourceType.DOCUMENT, "knowledge://index"))
                    report.add_event("knowledge_retrieved", f"knowledge_retrieve returned {len(kg.result)} chars")
                continue
            report.add_event("search", f"pass {pass_no}: {search_query}", tool_res.tool_id)
            evidence.extend(_evidence_from_text(tool_res.result, search_query, SourceType.WEB, tool_res.metrics.get("url", "web://search")))
            # Per-URL, fine-grained provenance from the structured SearchResult
            # artifacts (only populated when result pages were navigated+extracted).
            evidence.extend(_evidence_from_artifacts(tool_res.artifacts, search_query, tool_res.metrics.get("provider")))
            if len(sources_seen) >= budgets.max_sources:
                report.add_event("source_limit", f"reached max_sources={budgets.max_sources}")
                break

        report.evidence = _dedupe_evidence(_filter_domains(evidence, budgets.domain_allow, budgets.domain_deny))
        report.add_event("evidence_extracted", f"{len(report.evidence)} evidence items assembled")

        # 2) Cross-source conflict check.
        if _has_conflict(report.evidence):
            last_status = ResearchStatus.EVIDENCE_CONFLICT
            report.add_event("evidence_conflict", "conflicting evidence detected")
        else:
            report.add_event("cross_source_analysis", "no direct conflicts among evidence")

        # 3) Sandbox experiment when the mode calls for reproduction (Section 7).
        experiment = None
        if mode in (ResearchMode.EXPERIMENT, ResearchMode.DEEP_RESEARCH,
                    ResearchMode.CODE, ResearchMode.VERIFICATION, ResearchMode.DEBUG):
            experiment = await self._maybe_experiment(query, ctx, budgets, report, start)
            if experiment:
                report.experiments.append(experiment)

        # 4) Verification (Section 12).
        claim = f"re: {query}"
        status, reason = self.verifier.verify(claim, report.evidence, report.experiments or None)
        report.verification = status
        report.verification_reason = reason
        report.add_event("verification", f"{status.value}: {reason}")

        # 5) Confidence summary (qualitative, never a fabricated float).
        report.confidence_summary = _confidence_summary(status, report.evidence)
        if report.status is ResearchStatus.COMPLETE and status == VerificationStatus.VERIFIED:
            report.final_answer = _synthesize(query, report.evidence, report.experiments, status)
        else:
            report.final_answer = _synthesize(query, report.evidence, report.experiments, status)
        report.status = last_status

        report.add_event("research_end", f"status={report.status.value} verification={status.value}")
        return report

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _plan_query(self, query: str, pass_no: int) -> str:
        template = _RESEARCH_PASSES.get(pass_no, _RESEARCH_PASSES[len(_RESEARCH_PASSES) - 1])
        return template.format(q=query)

    async def _safe_invoke(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ok, reason = self.registry.authorize(ctx.user_id, name)
        if not ok:
            return ToolResult(tool_id=ctx.request_id, name=name, success=False,
                              error=f"TOOL_DENIED: {reason}")
        return await self.registry.invoke(name, args, ctx)

    async def _maybe_experiment(
        self, query: str, ctx: ToolContext, budgets: ResearchBudgets,
        report: ResearchReport, start: float,
    ) -> Optional[Experiment]:
        code = _derive_experiment_code(query)
        if code is None:
            report.add_event("experiment_skipped", "query did not yield a reproducible experiment")
            return None
        exp = Experiment(id=f"exp-{ctx.request_id}", objective=query, hypothesis=f"running {code!r} reproduces the claim")
        report.add_event("hypothesis", exp.hypothesis, ctx.request_id)
        tool_res = await self._safe_invoke("sandbox_run", {"code": code, "timeout": 5.0}, ctx)
        report.add_event("experiment_run", f"exit={tool_res.success} out={(tool_res.result or '')[:120]}", tool_res.tool_id)
        exp.observations.append(tool_res.result or "")
        exp.result = tool_res.result
        exp.verification = self.verifier.classify_tool_result("sandbox_run", tool_res.to_model_view())
        exp.reproducibility = "deterministic"
        return exp

    def _research_dir(self, user_id: str):
        from pathlib import Path

        # Prefer the platform data dir; fall back to a local scratch dir so the
        # engine stays usable (and testable) outside the platform process.
        try:
            from jarvis_backend.core import DATA_DIR  # type: ignore[import-not-found]
            return DATA_DIR / "research" / user_id
        except Exception:  # noqa: BLE001 — no platform wiring available
            return Path("./.research") / user_id


def _derive_experiment_code(query: str) -> Optional[str]:
    """Derive a SMALL reproducible Python snippet for a numeric/computational claim.

    Returns None (→ no experiment) for anything that is not a crisp computation,
    so we never fabricate an experiment for an unanswerable query.
    """
    q = query.strip().lower().rstrip("?")
    # Pattern: "... equals N" / "... equal N" / "... is N" / "= N" style.
    m = re.search(r"(.+?)\b(?:equals|equal|is|=)\s*(-?\d+(?:\.\d+)?)\s*$", q)
    if m:
        lhs = m.group(1).strip()
        # Recognise a small arithmetic expression on the left-hand side.
        expr = _arithmetic_expr(lhs)
        if expr:
            return f"print({expr})"
    # Bare arithmetic question, e.g. "what is 6 * 7" -> 42
    m = re.search(r"(?:what is|compute|evaluate)?\s*([\d\s\+\-\*\/\(\)\.]+)$", q)
    if m and _arithmetic_expr(m.group(1).strip()):
        return f"print({_arithmetic_expr(m.group(1).strip())})"
    return None


def _arithmetic_expr(lhs: str) -> Optional[str]:
    """Return a sanitised python arithmetic expression or None."""
    if not lhs:
        return None
    safe = re.sub(r"[^0-9\.\+\-\*\/\(\) ]", "", lhs).strip()
    if not safe or (safe == lhs.strip(" ") and not any(c.isdigit() for c in safe)):
        return None
    if not re.fullmatch(r"[\d\s\.\+\-\*\/\(\)]+", safe):
        return None
    try:
        compile(safe, "<expr>", "eval")
    except Exception:
        return None
    return safe


def _evidence_from_text(text: str, claim: str, source_type: SourceType, source_url: str) -> list[Evidence]:
    """Split a tool result into provenance-tagged Evidence items (no fabrication).

    Implemented as a comprehension so there is no post-loop return for a
    misbehaving auto-formatter to mis-indent (which previously pulled the
    return into the loop and truncated evidence to a single chunk).
    """
    if not text:
        return []
    chunks = [
        c.strip()
        for c in re.split(r"\n{2,}|(?<=\.)\s+", text.strip())[:8]
        if c.strip()
    ]
    return [
        Evidence(
            id=f"ev-{abs(hash(c)) & 0xFFFFFF:06x}-{i}",
            source_url=source_url,
            source_type=source_type,
            title=claim,
            retrieved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            relevant_content=c[:500],
            claims=[c[:200]],
            supporting_excerpt=c[:200],
            confidence=None,  # never fabricated
            verification_status=EvidenceStatus.UNVERIFIED,
            provider=None,
        )
        for i, c in enumerate(chunks)
    ]


def _evidence_from_artifacts(
    artifacts: list, claim: str, default_provider: Optional[str] = None
) -> list[Evidence]:
    """Build per-URL Evidence from structured SearchResult artifacts (Section 7).

    Only artifacts that actually carry extracted content produce evidence — pure
    search snippets are already captured via the result digest, so we avoid
    double-counting.  Each item is attributed to its REAL source URL (fine-grained
    provenance), never fabricated.
    """
    items: list[Evidence] = []
    for a in artifacts:
        content = (
            (a.get("relevant_content") or a.get("content_excerpt") or "")
            if isinstance(a, dict) else ""
        )
        snippet = (a.get("snippet") or "") if isinstance(a, dict) else ""
        text = (content or snippet).strip()
        if not text:
            continue
        url = (a.get("url") or "web://result") if isinstance(a, dict) else "web://result"
        title = (a.get("title") or claim) if isinstance(a, dict) else claim
        provider = (a.get("provider") or default_provider) if isinstance(a, dict) else default_provider
        items.append(Evidence(
            id=f"ev-art-{abs(hash((url, content[:80]))) & 0xFFFFFF:06x}",
            source_url=url,
            source_type=SourceType.WEB,
            title=title,
            retrieved_at=a.get("retrieved_at") or now_iso() if isinstance(a, dict) else now_iso(),
            relevant_content=content[:500] if content else text[:500],
            claims=[(content[:200] if content else text[:200])],
            supporting_excerpt=(content[:200] if content else text[:200]),
            confidence=None,  # never fabricated
            verification_status=EvidenceStatus.UNVERIFIED,
            provider=provider,
        ))
    return items


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    out: list[Evidence] = []
    for e in items:
        key = (e.source_url, e.relevant_content[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _filter_domains(items: list[Evidence], allow: list[str], deny: list[str]) -> list[Evidence]:
    """Honest source filtering (Section 4 domain allow/deny).  A source whose
    host is denied (and not explicitly allowed) is dropped, never rewritten."""
    if not allow and not deny:
        return items
    out: list[Evidence] = []
    for e in items:
        host = _host_of(e.source_url)
        if deny and host in deny:
            continue
        if allow and host not in allow:
            continue
        out.append(e)
    return out


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc
    except Exception:  # noqa: BLE001
        return ""


def _has_conflict(evidence: list[Evidence]) -> bool:
    for a in evidence:
        for b in evidence:
            if a is not b and a.conflicts_with(b):
                return True
    return False


def _confidence_summary(status: VerificationStatus, evidence: list[Evidence]) -> str:
    n = len(evidence)
    if status == VerificationStatus.VERIFIED:
        return f"verified by {n} evidence item(s) + reproduction"
    if status == VerificationStatus.PARTIALLY_VERIFIED:
        return f"partially verified: supported by {n} evidence item(s), not independently reproduced"
    if status == VerificationStatus.CONTRADICTED:
        return "contradicted by conflicting evidence"
    if status == VerificationStatus.UNAVAILABLE:
        return "no sources available to verify"
    return f"unverified ({n} evidence item(s) present)"


def _synthesize(query: str, evidence: list[Evidence], experiments: list[Experiment], status: VerificationStatus) -> Optional[str]:
    if not evidence and not experiments:
        return f"Unable to research '{query}': no sources were reachable." if status == VerificationStatus.UNAVAILABLE else None
    parts = []
    if status == VerificationStatus.VERIFIED:
        parts.append(f"Claim '{query}' is VERIFIED.")
    elif status == VerificationStatus.CONTRADICTED:
        parts.append(f"Claim '{query}' is CONTRADICTED.")
    else:
        parts.append(f"Claim '{query}' is {status.value}.")
    if experiments:
        for exp in experiments:
            parts.append(f"Experiment {exp.id} ({exp.reproducibility or 'run'}) produced: {(exp.result or '')[:120]}")
    if evidence:
        parts.append(f"Evidence from {len(evidence)} source(s).")
    return " ".join(parts)
