"""Domain models for the JARVIS research/verification fabric (Sections 2, 4-7, 12, 14, 22).

Pure data classes — no I/O, no network, no provider logic.  These travel between
the Brain agent, the Research Engine, the Tool Registry, the Verification
Engine and the learning surfaces, carrying provenance so confidence is never
fabricated and every claim can be traced to its source.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class EvidenceStatus(str, Enum):
    """Qualitative verification status for a piece of evidence (Section 5)."""

    VERIFIED = "VERIFIED"
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNAVAILABLE = "UNAVAILABLE"


class VerificationStatus(str, Enum):
    """Status produced by the Verification Engine (Section 12)."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"
    CONTRADICTED = "CONTRADICTED"
    UNAVAILABLE = "UNAVAILABLE"


class SourceType(str, Enum):
    """Origin of a piece of evidence (Section 5)."""

    WEB = "web"
    DOCUMENT = "document"
    CODE = "code"
    MEMORY = "memory"
    MODEL = "model"
    USER = "user"
    REPO_ISSUE = "repo_issue"
    EXPERIMENT = "experiment"


class ResearchMode(str, Enum):
    """Brain working modes (Section 13)."""

    STANDARD = "STANDARD"
    RESEARCH = "RESEARCH"
    DEEP_RESEARCH = "DEEP_RESEARCH"
    EXPERIMENT = "EXPERIMENT"
    DEBUG = "DEBUG"
    CODE = "CODE"
    ANALYSIS = "ANALYSIS"
    VERIFICATION = "VERIFICATION"
    LEARNING = "LEARNING"


class ResearchStatus(str, Enum):
    """Terminal status of a research report (Section 28 failure behaviour)."""

    COMPLETE = "COMPLETE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    VERIFICATION_INCOMPLETE = "VERIFICATION_INCOMPLETE"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"


class RiskLevel(str, Enum):
    """Risk tier for a tool (Section 19/20)."""

    READ = "read"          # passive observation, e.g. search / retrieve
    EXEC = "exec"          # local deterministic execution, e.g. sandbox_run
    WRITE = "write"        # external mutation, e.g. publish / email (requires confirmation)
    NETWORK = "network"    # outbound connection to a third party
    ADMIN = "admin"        # privileged host operation


# --------------------------------------------------------------------------- #
# Tool call / result (Section 2 / Section 22 observability)
# --------------------------------------------------------------------------- #
@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    tool_id: str = field(default_factory=lambda: _short_uuid())
    started_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "arguments": dict(self.arguments),
            "started_at": self.started_at,
        }


@dataclass
class ToolResult:
    """Result of invoking a tool.  Secrets are NEVER present in ``result``."""

    tool_id: str
    name: str
    success: bool
    result: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # When True, some secret-shaped substring was detected and scrubbed from
    # ``result`` before the model could see it (Section 19 secret leakage).
    redacted_secrets: bool = False

    def to_model_view(self) -> dict[str, Any]:
        """The ONLY representation the language model is ever allowed to see."""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "metrics": dict(self.metrics),
            "artifacts": [dict(a) for a in self.artifacts],
        }


# --------------------------------------------------------------------------- #
# Evidence (Section 5)
# --------------------------------------------------------------------------- #
@dataclass
class Evidence:
    id: str
    source_url: str
    source_type: SourceType
    title: Optional[str]
    retrieved_at: str  # ISO-8601
    relevant_content: str
    claims: list[str] = field(default_factory=list)
    supporting_excerpt: Optional[str] = None
    # confidence is ONLY set when a deterministic check produced a real number.
    # None means "not numerically justified" — never fabricated.
    confidence: Optional[float] = None
    verification_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    provider: Optional[str] = None  # which tool/provider produced it

    def conflicts_with(self, other: "Evidence") -> bool:
        """Heuristic conflict detection between two evidence snippets.

        Returns True when both snippets make a direct factual claim about the
        same subject and the claims cannot both be true.  This is deliberately
        conservative (substring-level) — it never infers truth.
        """
        if not self.claims or not other.claims:
            return False
        for a in self.claims:
            for b in other.claims:
                if a == b:
                    continue
                # A "X vs not-X / different value" pattern on the same claim text
                # is treated as a conflict; everything else stays UNVERIFIED.
                if _contradicts(a, b):
                    return True
        return False


# --------------------------------------------------------------------------- #
# Experiment (Section 7)
# --------------------------------------------------------------------------- #
@dataclass
class Experiment:
    id: str
    objective: str
    hypothesis: str
    inputs: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    result: Optional[str] = None
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    reproducibility: Optional[str] = None  # e.g. "deterministic", "environment-dependent"
    started_at: str = field(default_factory=now_iso)


# --------------------------------------------------------------------------- #
# Budgets (Section 4 — hard limits, no infinite autonomous searching)
# --------------------------------------------------------------------------- #
@dataclass
class ResearchBudgets:
    max_iterations: int = 5
    max_tokens: int = 8000
    max_providers: int = 3
    max_seconds: int = 120
    max_sources: int = 8
    domain_allow: list[str] = field(default_factory=list)
    domain_deny: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Research session + report (Section 22 observability)
# --------------------------------------------------------------------------- #
@dataclass
class ResearchSession:
    session_id: str = field(default_factory=lambda: _short_uuid())
    user_id: str = "anonymous"
    query: str = ""
    mode: ResearchMode = ResearchMode.STANDARD
    started_at: str = field(default_factory=now_iso)
    budgets: ResearchBudgets = field(default_factory=ResearchBudgets)


@dataclass
class InvestigationEvent:
    """One line on the investigation timeline (Section 22)."""

    at: str
    kind: str
    detail: str
    tool_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "kind": self.kind, "detail": self.detail, "tool_id": self.tool_id}


@dataclass
class ResearchReport:
    session: ResearchSession
    report_id: str = field(default_factory=lambda: _short_uuid())
    generated_at: str = field(default_factory=now_iso)
    # The Brain agent's final synthesized answer (may contain unverified claims).
    final_answer: Optional[str] = None
    evidence: list[Evidence] = field(default_factory=list)
    experiments: list[Experiment] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    timeline: list[InvestigationEvent] = field(default_factory=list)
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_reason: str = ""
    status: ResearchStatus = ResearchStatus.COMPLETE
    confidence_summary: str = ""  # qualitative, never a fabricated float

    def add_event(self, kind: str, detail: str, tool_id: Optional[str] = None) -> None:
        self.timeline.append(InvestigationEvent(at=now_iso(), kind=kind, detail=detail, tool_id=tool_id))

    def to_summary(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "session_id": self.session.session_id,
            "query": self.session.query,
            "mode": self.session.mode.value,
            "status": self.status.value,
            "verification": self.verification.value,
            "verification_reason": self.verification_reason,
            "evidence_count": len(self.evidence),
            "experiments": len(self.experiments),
            "tool_calls": len(self.tool_calls),
            "verification_statuses": sorted({e.verification_status.value for e in self.evidence}),
            "final_answer": self.final_answer,
            "confidence_summary": self.confidence_summary,
            "timeline": [dataclasses.asdict(e) for e in self.timeline],
        }


# --------------------------------------------------------------------------- #
# Normalized search contract (Section 3 — web search discovery data)
# --------------------------------------------------------------------------- #
@dataclass
class SearchResult:
    """A single normalised web-search result (Section 3).

    ``retrieved_at``, ``rank`` and ``provider`` are *descriptive* provenance,
    NOT claims of factual accuracy — a search result is discovery data only.
    ``confidence`` is None ("not numerically justified") unless a deterministic
    check produced a real number; it is never fabricated.
    """

    id: str = field(default_factory=lambda: _short_uuid())
    title: str = ""
    url: str = ""
    # Snippet returned by the search engine (NOT verified content).
    snippet: str = ""
    # Origin of this result: "web" | "document" | etc.
    source: str = "web"
    retrieved_at: str = field(default_factory=now_iso)
    rank: int = 0
    provider: str = ""          # which search backend (e.g. "duckduckgo", "wikipedia")
    domain: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # Populated when the result page was actually navigated + extracted.
    content_type: str = ""
    relevant_content: str = ""  # main text of the page (<= N chars)
    content_excerpt: str = ""  # shorter excerpt for model context
    word_count: int = 0
    navigation_context: Optional[dict[str, Any]] = None   # from classify_navigation_context
    navigation_failure: Optional[str] = None              # NavigationFailureClass value if fetch failed
    # confidence is ONLY set when a deterministic check produced a real number.
    confidence: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class SearchResponse:
    """Normalized response envelope for a web search (Section 3)."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    provider: str = ""        # overall provider ("duckduckgo+lite/wikipedia")
    latency_ms: float = 0.0
    status: str = "ok"        # "ok" | "partial" | "no_results" | "unavailable"
    total: int = 0
    artifact_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 2),
            "status": self.status,
            "total": self.total,
            "artifact_count": self.artifact_count,
            "metadata": dict(self.metadata),
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _short_uuid() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def _contradicts(a: str, b: str) -> bool:
    """Return True if claim strings ``a`` and ``b`` look like direct contradictions.

    This is intentionally narrow: only exact "X" vs "not X" / negation patterns
    on the same textual claim are flagged.  It never performs semantic inference.
    """
    if not a or not b:
        return False
    la, lb = a.strip().lower(), b.strip().lower()
    if la == lb:
        return False
    # Direct negation markers on the same residual claim.
    for neg in ("not ", "no ", "never ", "false", "incorrect"):
        if la.startswith(neg) and lb.removeprefix(neg) == la.removeprefix(neg):
            return True
        if lb.startswith(neg) and la.removeprefix(neg) == lb.removeprefix(neg):
            return True
    return False
