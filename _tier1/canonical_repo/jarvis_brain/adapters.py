"""Brain adapters: the model boundary (Phase 8 §2, §8, §17, §19-21).

The control plane never talks to a model directly.  It talks to a
:class:`BrainAdapter` — a small protocol that returns a *structured*
:class:`BrainOutput`.  Two implementations ship:

* :class:`ModelBrainAdapter` — routes through the *existing* honesty-gated
  :class:`BrainClient` (``backend.model_gateway.brain_client``).  It constrains
  the model to emit JSON matching the Brain contract, parses it, and if the
  Brain is unavailable (``gw_brain_unavailable``) or the JSON is unparseable
  it degrades HONESTLY to ``ASK_USER`` / ``INSUFFICIENT_EVIDENCE`` — it never
  fabricates a plan.

* :class:`DeterministicBrainAdapter` — used only when the Brain model is down or
  unreachable.  It produces a minimal, evidence-driven plan from the bounded
  context pack and is explicitly labelled ``provenance.is_offline = True``.
  Completion is never declared here — it only *proposes* evidence-gathering
  steps; the control plane still validates + verifies with real evidence.

Neither adapter touches credentials, shell, DB, or provider SDKs directly.  All
provider/model access flows through :class:`ToolRegistry` tools at execution
time, which is where authorization + secret-scrubbing happens.
"""
from __future__ import annotations

import json
import os
import inspect
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from .contract import (
    BrainInput, BrainOutput, BrainIntent, Plan, PlanStep, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode,
    validate_brain_output, safe_parse_brain_json,
)
from .budget import TaskBudget
from research_engine.tool_registry import scrub_secrets


def _scrub_model_payload(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_secrets(value)[0]
    if isinstance(value, dict):
        return {str(key): _scrub_model_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_model_payload(item) for item in value]
    return value

# System prompt fragment instructing the model to emit the contract schema.
_SCHEMA_FRAGMENT = (
    "You are JARVIS Brain, the reasoning+planning layer. You PROPOSE plans; "
    "you never execute, never see credentials, and never declare task complete "
    "on your own. Output STRICT JSON matching this schema. Do not include prose "
    "outside the JSON. Confidence_state must be one of: "
    "SUFFICIENT_INFORMATION, MISSING_INFORMATION, AMBIGUOUS_REQUEST, "
    "CONFLICTING_EVIDENCE, INSUFFICIENT_EVIDENCE, ASK_USER.\n"
    "If you cannot determine the plan, return confidence_state=ASK_USER with "
    "questions_for_user and an empty capability_requests list.\n"
    "JSON schema:\n"
    + json.dumps({
        "intent": {"domain": "str", "task": "str", "confidence_state": "str"},
        "plan": {"summary": "str", "steps": [{"id": "str", "capability": "str",
            "summary": "str", "args": "obj", "depends_on": ["str"]}]},
        "capability_requests": [{"capability": "str", "args": "obj",
            "reason": "str", "depends_on": ["str"]}],
        "questions_for_user": ["str"],
        "completion_conditions": [{"type": "str", "target": "str",
            "expected": "any"}],
        "confidence_state": "str",
        "model_ref": "str",
        "summary": "str",
    })
)


@runtime_checkable
class BrainAdapter(Protocol):
    """The model-independent interface the control plane depends on."""

    async def propose(self, brain_input: BrainInput, budget: Optional[TaskBudget]) -> BrainOutput:
        ...


@dataclass
class BrainAvailability:
    """Honest runtime view of the Brain model backend (spec §1)."""

    available: bool = False
    stub: bool = True
    production_health: bool = False
    backend: str = "stub"
    reason: str = "not probed"
    endpoint: str = ""
    model: str = ""
    provider: str = ""

    @property
    def reachable(self) -> bool:
        return self.available and not self.stub


def _probe_brain() -> BrainAvailability:
    """Honest probe — never claims active just because files exist."""
    endpoint = os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    backend = os.environ.get("JARVIS_BRAIN_BACKEND", "stub")
    model = os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")
    if not endpoint:
        return BrainAvailability(
            available=False, stub=True, backend=backend,
            reason="JARVIS_BRAIN_ENDPOINT not configured",
            model=model,
        )
    # Probe the runtime's /health for an honest availability signal.
    health = _brain_health(endpoint)
    avail = bool(health)
    return BrainAvailability(
        available=avail, stub=bool(health.get("stub")) if health else backend == "stub",
        production_health=avail,
        backend=(health.get("backend") or backend) if health else backend,
        endpoint=endpoint,
        model=(health.get("model") or model) if health else model,
        provider=(health.get("provider") or "") if health else "",
        reason="ok" if avail else "runtime /health reported unavailable",
    )


def _brain_health(endpoint: str) -> dict[str, Any] | None:
    # Lazy, isolated import of the runtime health client to avoid pulling the
    # brain_runtime server into every test process.
    root = endpoint.rstrip("/")
    root = root.removesuffix("/v1")
    import urllib.request
    try:
        with urllib.request.urlopen(root + "/health", timeout=3) as r:
            import json as _j
            data = _j.loads(r.read().decode("utf-8", "ignore"))
            if data.get("available") and not data.get("stub"):
                return data
    except Exception:
        pass
    return None


def _health_available(endpoint: str) -> bool:
    return _brain_health(endpoint) is not None


class ModelBrainAdapter:
    """Brains through the honest-gated :class:`BrainClient`.

    The BrainClient already refuses to proceed when the runtime reports
    available=false/stub=true (gw_brain_unavailable).  Here we additionally
    constrain the model to JSON and degrade on parse failure.
    """

    def __init__(self, brain_client: Any):
        self.client = brain_client
        self.availability = _probe_brain()

    async def propose(self, brain_input: BrainInput,
                      budget: Optional[TaskBudget]) -> BrainOutput:
        # Honest gate 1: Brain runtime not reachable -> degrade, do NOT fabricate.
        if not self.availability.reachable:
            self.availability = _probe_brain()
            return self._degrade_unavailable(brain_input)

        # Build the messages: system prompt (schema) + user request + context.
        messages = self._build_messages(brain_input)
        try:
            resp = self.client.chat(
                messages,
                timeout=60,
                temperature=0.0,
                max_tokens=2048,
            )
            if inspect.isawaitable(resp):
                resp = await resp
        except Exception as e:
            # Honest gate 2: any model error -> degrade.
            name = type(e).__name__
            if "gw_brain_unavailable" in name or "GatewayError" in name:
                self.availability = _probe_brain()
                return self._degrade_unavailable(brain_input)
            return self._degrade_parse_failure(brain_input, str(e))

        content = getattr(resp, "content", "") or ""
        # Honest gate 3: stub content must be rejected (never fabricate).
        if content.strip().startswith("[brain-stub]") or not content.strip():
            return self._degrade_unavailable(brain_input)

        parsed = safe_parse_brain_json(content)
        if parsed is None:
            return self._degrade_parse_failure(brain_input, "non-JSON model output")

        # Honest gate 4: the contract schema is the hard structural gate.
        try:
            output = validate_brain_output(parsed)
        except Exception as e:
            return self._degrade_parse_failure(brain_input, f"schema violation: {e}")

        usage = getattr(resp, "usage", None)
        if usage is not None and budget is not None:
            try:
                budget.spend_tokens(getattr(usage, "total_tokens", 0) or 0)
            except Exception:
                pass
        output.model_ref = self.availability.model
        output.provenance["adapter"] = "ModelBrainAdapter"
        output.provenance["backend"] = self.availability.backend
        output.provenance["provider"] = self.availability.provider
        return output

    # ------------------------------------------------------------------ #
    def _build_messages(self, brain_input: BrainInput) -> list[dict[str, str]]:
        user_payload = {
            "request": brain_input.request,
            "execution_mode": brain_input.execution_mode,
            "available_capabilities": brain_input.available_capabilities,
            "context": brain_input.context,
            "task_state": brain_input.task_state,
            "relevant_artifacts": brain_input.relevant_artifacts,
            "autonomy": brain_input.autonomy,
        }
        return [
            {"role": "system", "content": _SCHEMA_FRAGMENT},
            {"role": "user", "content": json.dumps(_scrub_model_payload(user_payload))},
        ]

    @staticmethod
    def _degrade_unavailable(brain_input: BrainInput) -> BrainOutput:
        return BrainOutput(
            intent=BrainIntent(domain=brain_input.execution_mode,
                               task=brain_input.request,
                               confidence=ConfidenceState.ASK_USER),
            plan=Plan(summary="Brain model unavailable — cannot propose a plan."),
            capability_requests=[],
            questions_for_user=["The JARVIS Brain model is not available. "
                                "Would you like me to proceed with the offline "
                                "evidence-gathering path, or provide more detail?"],
            completion_conditions=[],
            confidence_state=ConfidenceState.ASK_USER,
            model_ref="unavailable",
            provenance={"adapter": "ModelBrainAdapter", "offline": True,
                        "reason": "brain_unavailable"},
            summary="I cannot reach the Brain model right now; routing through the "
                    "offline evidence path.",
        )

    @staticmethod
    def _degrade_parse_failure(brain_input: BrainInput, err: str) -> BrainOutput:
        return BrainOutput(
            intent=BrainIntent(domain=brain_input.execution_mode,
                               task=brain_input.request,
                               confidence=ConfidenceState.INSUFFICIENT_EVIDENCE),
            plan=Plan(summary="Model produced unusable output."),
            capability_requests=[],
            questions_for_user=[],
            completion_conditions=[],
            confidence_state=ConfidenceState.INSUFFICIENT_EVIDENCE,
            model_ref="unavailable",
            provenance={"adapter": "ModelBrainAdapter", "offline": True,
                        "reason": "model_output_unparseable"},
            summary="The Brain returned an answer I could not interpret; asking "
                    "the control plane to verify before trusting anything.",
        )


class DeterministicBrainAdapter:
    """Offline, no-fabrication planner (Phase 8 §17, §8 honesty).

    Only proposes capabilities that are:
      * registered in the context pack's available_capabilities, AND
      * offline-capable (supports_offline=True) when execution_mode=OFFLINE, AND
      * read/local-exec risk (never pure NETWORK/ADMIN without approval).

    It NEVER claims completion — completion is decided solely by the control
    plane verifying evidence against completion_conditions.
    """

    # Capability families this offline planner is willing to propose evidence
    # gathering from.
    _OFFLINE_READ = {
        "static_search", "knowledge_retrieve", "memory_recall",
        "files.read", "files.search", "project.inspect", "project.search",
        "project.test_status", "capability.discover", "capability.catalogue",
        "brain.status", "silverwing.status", "provider.status",
    }

    def __init__(self, offline_mode: bool = True):
        self.offline_mode = offline_mode

    async def propose(self, brain_input: BrainInput,
                      budget: Optional[TaskBudget]) -> BrainOutput:
        available = {
            c.get("id"): c for c in brain_input.available_capabilities
            if isinstance(c, dict)
        }
        chosen: list[CapabilityRequest] = []
        for cap_id in self._OFFLINE_READ:
            info = available.get(cap_id)
            if info is None:
                continue
            if self.offline_mode and not info.get("offline", False):
                continue
            risk = info.get("risk", "read")
            if risk in ("network", "admin"):
                # Offline path never proposes network/admin without approval.
                continue
            chosen.append(CapabilityRequest(
                capability=cap_id, args={}, reason="offline evidence gathering",
            ))

        summary = ("Offline evidence-gathering plan derived from bounded context "
                   "pack. No inference provider available; completion will be "
                   "decided by the control plane verifying evidence only.")
        steps = [
            PlanStep(id=f"s{i+1}", capability=c.capability,
                     summary=f"retrieve evidence via {c.capability}",
                     args=dict(c.args), depends_on=[])
            for i, c in enumerate(chosen[:6])
        ]
        return BrainOutput(
            intent=BrainIntent(
                domain=brain_input.execution_mode,
                task=brain_input.request,
                confidence=ConfidenceState.INSUFFICIENT_EVIDENCE,
            ),
            plan=Plan(summary=summary, steps=steps),
            capability_requests=chosen[:6],
            questions_for_user=[] if not self.offline_mode else [
                "No inference provider is available. Proceeding in OFFLINE mode: "
                "I will gather evidence only and cannot synthesize new answers."
            ],
            completion_conditions=[
                CompletionCondition(type="evidence_sufficient",
                                    target=brain_input.request, expected=True),
            ],
            confidence_state=ConfidenceState.INSUFFICIENT_EVIDENCE,
            model_ref="deterministic-offline",
            provenance={"adapter": "DeterministicBrainAdapter", "offline": True,
                        "is_offline_fallback": True},
            summary=summary,
        )
def build_brain_adapter(brain_client: Optional[Any] = None) -> BrainAdapter:
    """Production factory: picks ModelBrainAdapter when the Brain is reachable,
    else falls back to the deterministic offline adapter.

    Honest: when the Brain runtime is unreachable this is reported, never
    hidden.
    """
    avail = _probe_brain()
    if avail.reachable:
        return ModelBrainAdapter(brain_client or _default_brain_client())
    return DeterministicBrainAdapter(offline_mode=True)


def _default_brain_client() -> Any:
    """Lazy import of the honesty-gated BrainClient (existing code)."""
    from backend.model_gateway.brain_client import BrainClient
    return BrainClient()


__all__ = ["BrainAdapter", "ModelBrainAdapter", "DeterministicBrainAdapter",
           "BrainAvailability", "build_brain_adapter"]
