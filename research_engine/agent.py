"""Tool-aware Brain agent (Section 2).

Turns the Brain from a flat ``prompt -> LLM -> answer`` pass into a tool-aware
orchestrator:

    request
      → understand        (classify the task / pick a ResearchMode)
      → plan              (generate bounded search queries / experiment plan)
      → choose tools      (via ToolRegistry.describe() — the model only sees
                           tool name + schema, never credentials)
      → retrieve          (search / knowledge / memory)
      → execute           (sandbox / model_consult)
      → observe           (capture ToolResults, scrub secrets)
      → verify            (VerificationEngine)
      → answer            (synthesize, tagging unverified claims)

The agent reuses :class:`ResearchEngine` for the actual pipeline and an optional
language model for planning/synthesis.  When no model is healthy/available the
agent falls back to evidence-driven synthesis and labels the limitation
honestly (Section 28) — it never fabricates a model answer.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from .models import (
    InvestigationEvent,
    ResearchBudgets,
    ResearchMode,
    ResearchReport,
    ResearchSession,
    ResearchStatus,
    ToolCall,
    VerificationStatus,
    now_iso,
)
from .research_engine import ResearchEngine
from .tool_registry import ToolContext, ToolRegistry
from .verification import VerificationEngine


class BrainAgent:
    """The Brain's tool-aware orchestration layer."""

    def __init__(
        self,
        registry: ToolRegistry,
        verifier: Optional[VerificationEngine] = None,
    ):
        self.registry = registry
        self.verifier = verifier or VerificationEngine()
        self.engine = ResearchEngine(registry=registry, verifier=self.verifier)

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #
    async def investigate(
        self,
        query: str,
        mode: Optional[ResearchMode] = None,
        user_id: str = "anonymous",
        budgets: Optional[ResearchBudgets] = None,
        confirmations: Optional[dict[str, bool]] = None,
    ) -> ResearchReport:
        mode = mode or self._understand(query)
        budgets = budgets or ResearchBudgets()
        report = await self.engine.research(query, mode, user_id, budgets, confirmations)
        # Optional model-driven synthesis if a healthy provider is available.
        plan = self._plan(query, mode, budgets)
        report.add_event("understand", f"mode={mode.value}")
        report.add_event("plan", plan)
        synthesized = await self._maybe_synthesize_with_model(query, report, user_id)
        if synthesized:
            report.final_answer = synthesized
            report.add_event("answer", "model-assisted synthesis (healthy provider)")
        else:
            report.add_event("answer", "evidence-driven synthesis (no healthy model provider)")
        return report

    # ------------------------------------------------------------------ #
    # Internal — all deterministic, honest
    # ------------------------------------------------------------------ #
    def _understand(self, query: str) -> ResearchMode:
        """Classify the task intent into a Brain mode (Section 13)."""
        q = query.lower()
        if any(w in q for w in ("prove", "show that", "equals", "compute", "calculate", "verify", "why does")):
            return ResearchMode.VERIFICATION
        if "implement" in q or "code" in q or "algorithm" in q:
            return ResearchMode.CODE
        if any(w in q for w in ("research", "what is", "latest", "vs", "compare")):
            return ResearchMode.DEEP_RESEARCH
        if "debug" in q or "fails" in q or "error" in q:
            return ResearchMode.DEBUG
        return ResearchMode.STANDARD

    def _plan(self, query: str, mode: ResearchMode, budgets: ResearchBudgets) -> str:
        """Generate bounded planning notes (no live inference required)."""
        steps = [
            "understand question",
            f"generate up to {min(budgets.max_iterations, 5)} research pass queries",
            "search/retrieve sources",
            "extract evidence with provenance",
            "cross-source compare (conflict detection)",
        ]
        if mode in (ResearchMode.EXPERIMENT, ResearchMode.DEEP_RESEARCH,
                    ResearchMode.CODE, ResearchMode.VERIFICATION, ResearchMode.DEBUG):
            steps.append("reproduce claim in sandbox experiment")
        steps += ["verify claim", "synthesize answer, tagging unverified claims"]
        return "; ".join(steps)

    async def _maybe_synthesize_with_model(
        self, query: str, report: ResearchReport, user_id: str
    ) -> Optional[str]:
        """If a healthy model provider is available, ask it to synthesize.
        Otherwise returns None (caller uses evidence-driven synthesis)."""
        # A deterministic experiment already settled the claim (VERIFIED or
        # CONTRADICTED) — the evidence-driven synthesis is authoritative here, so
        # we do not spend a model-consultation call (Section 28 honesty + cost
        # discipline: never pay to summarise a claim already proven by
        # reproduction).
        if report.verification in (VerificationStatus.VERIFIED, VerificationStatus.CONTRADICTED):
            return None
        ctx = ToolContext(request_id=f"synth-{report.session.session_id[:8]}", user_id=user_id)
        ok, _ = self.registry.authorize(user_id, "model_consult")
        if not ok:
            # model_consult is NETWORK-gated; not confirmed → no model assistance.
            return None
        # Build a compact evidence + experiment context (no secrets).
        evidence_text = "; ".join(e.relevant_content for e in report.evidence)[:2000]
        experiment_text = "; ".join(e.result or "" for e in report.experiments)[:1000]
        prompt = (
            f"You are a careful research assistant. Given the evidence and "
            f"experiment observations below, answer the user's question. "
            f"NEVER fabricate. Tag any claim as unverified if the evidence does "
            f"not support it.\n\nQuestion: {query}\n\nEvidence: {evidence_text}\n\n"
            f"Experiments: {experiment_text}\n"
        )
        try:
            result = await self.registry.invoke(
                "model_consult",
                {"question": prompt, "provider": "auto"},
                ctx,
            )
        except Exception:  # noqa: BLE001
            return None
        if result.success and result.result:
            # If the model answer conflicts with verified CONTRADICTED evidence,
            # downgrade rather than trust (Section 28/31 — never assume correctness).
            if VerificationStatus.CONTRADICTED == report.verification and _looks_confident(result.result):
                report.add_event("verification", "model answer discounted: evidence contradicted")
                return None
            return result.result
        return None


def _looks_confident(text: str) -> bool:
    """Tiny heuristic: does the model hedge or assert confidently?"""
    if not text:
        return False
    t = text.lower()
    hedges = ("i'm not sure", "i cannot", "i do not know", "uncertain", "may be", "might be")
    return not any(h in t for h in hedges)
