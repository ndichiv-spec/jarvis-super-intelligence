"""Teacher Mesh (spec §24, §27).

Composes the configured healthy external providers, the live NVIDIA Brain, the
local Jarvis brain, and Silverwing into a *panel of teachers*.  Teaching
capabilities map one-to-one onto discreet, purpose-built calls:

- propose / generate problem          (governed curriculum generator + review)
- solve                               (produce a solution)
- critique                            (assess a solution)
- generate counterexample             (attack a solution)
- verification criteria               (what "correct" means here)
- explain failure                     (diagnose why a learner failed)
- create lesson                       (turn an episode into a lesson draft)

Lesson quality is gated separately (``learning_arena.lesson_gate``); the mesh
only *drafts*.  Teacher selection is health-gated — a teacher that is not
healthy is never consulted and every real call is routed through the provider
fabric.  On disagreement, the mesh does not guess: it converges, verifies via
sandbox when the task is verifiable, or returns an honest ``UNVERIFIED``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from providers.base import Message, ProviderRequest
from providers.health import HealthStatus

#: Verifier hook signature: ``callable(problem, solution) -> dict`` returning at
#: least ``{"outcome": "VERIFIED"|"REFUTED"|"UNVERIFIABLE", "evidence": str}``.
Verifier = Callable[[Any, str], dict]

SOLUTION_ROLE = (
    "You are a rigorous teacher. Give ONLY the final answer, concise and precise. "
    "For programming problems, give runnable Python code. No commentary."
)

CRITIQUE_ROLE = (
    "You are a skeptical peer reviewer. Judge this solution against the problem. "
    "Return JSON: {\"verdict\":\"CONVINCING\"|\"WEAK\"|\"FLAWED\","
    " \"issues\":[<issue strings>], \"fix\":\"<if needed>\"}."
)

COUNTEREXAMPLE_ROLE = (
    "You are an adversary. Find one concrete counterexample to this solution, "
    "or state 'NONE FOUND'. Reply with the counterexample and why it breaks the solution."
)

CRITERIA_ROLE = (
    "You are an evaluation designer. List the concrete, checkable criteria that "
    "determine whether a solution is correct. Be minimal and complete."
)

EXPLAIN_ROLE = (
    "You are a diagnostic teacher. Explain the learner's failure vs the correct "
    "approach. Return JSON: {\"root_cause\":\"...\", \"hint\":\"...\"}."
)

LESSON_ROLE = (
    "You are a curriculum designer. Draft ONE focused lesson from this "
    "problem/solution/verification episode. Return JSON: {\"title\":\"..\","
    " \"concept\":\"..\", \"worked_example\":\"..\", "
    " \"misconceptions\":[\"..\"], \"exercises\":[\"..\"]}."
)


class TeacherUnavailable(RuntimeError):
    """No healthy teacher could serve the requested capability."""


class TeacherCallError(RuntimeError):
    """A teacher's underlying provider call failed."""


@dataclass
class Teacher:
    """One selectable teacher (a provider+model pair)."""

    key: str  # "nvidia/metadata-instruct-3q", ...
    provider: str
    model_id: str
    display_name: str
    capabilities: frozenset[str] = frozenset()
    adapter_kind: str = "external"  # external | jarvis | silverwing | local
    status: str = "unknown"
    detail: str = ""
    latency_ms: Optional[float] = None
    last_checked: Optional[float] = None

    def ready(self) -> bool:
        return self.status == HealthStatus.HEALTHY.value

    def satisfies(self, caps: set[str]) -> bool:
        return not caps or caps.issubset(set(self.capabilities))

    def snapshot(self) -> dict:
        return {
            "key": self.key,
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": sorted(self.capabilities),
            "adapter_kind": self.adapter_kind,
            "status": self.status,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
            "ready": self.ready(),
        }


def _normalize(solution: str) -> str:
    return re.sub(r"\s+", " ", solution or "").strip().lower()


class TeacherMesh:
    """Health-gated panel of teachers backed by the provider fabric."""

    def __init__(
        self,
        adapters: Optional[dict[str, Any]] = None,
        *,
        include_local_jarvis: bool = True,
        health_refresh_ms: float = 60_000.0,
        chat_model_preference: Optional[list[str]] = None,
    ) -> None:
        if adapters is None:
            from providers.bootstrap import build_adapters
            from providers.secrets import get_secret_manager

            adapters = build_adapters(secrets=get_secret_manager())
        self.adapters = adapters
        self.include_local_jarvis = include_local_jarvis
        self.health_refresh_ms = health_refresh_ms
        self._teachers: list[Teacher] = []
        self._teacher_map: dict[str, Teacher] = {}
        self._last_probe = 0.0
        self._discover()

    # ------------------------------------------------------------------
    # Discovery / health
    # ------------------------------------------------------------------
    def _discover(self) -> None:
        teachers: list[Teacher] = []
        for pid, adapter in self.adapters.items():
            if not getattr(adapter, "configured", False):
                continue
            if pid == "hf" and not getattr(adapter, "inference_ready", False):
                # HF inference role requires an endpoint; without it, a HF repo
                # is not a chat teacher (registry role only).
                continue
            models = getattr(adapter, "models", None) or []
            if not models:
                continue
            default = getattr(adapter, "default_model", None)
            candidates = [m for m in models if "chat" in {c.value for c in m.capabilities}]
            if not candidates and default:
                # fall back to the adapter default for an untyped catalog
                candidates = []
                for m in models:
                    if m.model_id == default:
                        candidates.append(m)
                        break
            for m in candidates[:3]:
                caps = sorted(c.value for c in m.capabilities) or ["chat"]
                key = f"{pid}/{m.model_id}"
                teachers.append(
                    Teacher(
                        key=key,
                        provider=pid,
                        model_id=m.model_id,
                        display_name=f"{adapter.display_name} · {m.name or m.model_id}",
                        capabilities={"chat", *(c for c in caps)},
                        status=HealthStatus.UNKNOWN.value,
                        latency_ms=None,
                    )
                )
        if not teachers:
            return
        # Deterministic order: provider-priority then model id.
        order = {pid: i for i, pid in enumerate(self.adapters)}
        teachers.sort(key=lambda t: (order.get(t.provider, 99), t.model_id))
        self._teachers = teachers
        self._teacher_map = {t.key: t for t in teachers}

    def refresh(self, *, force: bool = False) -> list[Teacher]:
        """Health-probe all candidate teachers and refresh statuses."""
        now = time.time() * 1000
        if not force and (now - self._last_probe) < self.health_refresh_ms:
            return self._teachers
        self._last_probe = now
        for teacher in self._teachers:
            adapter = self.adapters.get(teacher.provider)
            if adapter is None:
                continue
            try:
                health = adapter.health(force=False)
                teacher.status = health.status.value
                teacher.detail = health.detail or ""
                teacher.latency_ms = health.latency_ms
            except Exception as exc:  # a dead provider must not kill the mesh
                teacher.status = HealthStatus.ERROR.value
                teacher.detail = f"probe failed: {type(exc).__name__}"
                teacher.latency_ms = None
            teacher.last_checked = time.time()
        return self._teachers

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def teachers(self) -> list[Teacher]:
        return list(self._teachers)

    def teacher(self, key: str) -> Teacher:
        return self._teacher_map[key]

    def available(self, capabilities: Optional[set[str]] = None) -> list[Teacher]:
        caps = set(capabilities or {"chat"})
        return [t for t in self.refresh() if t.ready() and t.satisfies(caps)]

    def select(self, capabilities: Optional[set[str]] = None) -> Teacher:
        """Pick one healthy teacher (provider priority within the fabric)."""
        available = self.available(capabilities)
        if not available:
            raise TeacherUnavailable(
                "no healthy teacher available for "
                f"{sorted(capabilities or {'chat'})}"
            )
        return available[0]

    def _chat(self, teacher: Teacher, system: str, user: str, *, temperature: float = 0.2) -> str:
        adapter = self.adapters[teacher.provider]
        try:
            resp = adapter.chat(
                ProviderRequest(
                    messages=[Message.system(system), Message.user(user)],
                    model=teacher.model_id,
                    temperature=temperature,
                    max_tokens=2048,
                )
            )
        except Exception as exc:
            raise TeacherCallError(
                f"teacher {teacher.key} failed: {type(exc).__name__}: {exc}"
            ) from exc
        text = (resp.text or "").strip()
        if not text:
            raise TeacherCallError(f"teacher {teacher.key} returned empty output")
        return text

    # ------------------------------------------------------------------
    # Teaching capabilities
    # ------------------------------------------------------------------
    def solve(
        self,
        problem_like: Any,
        *,
        teacher_key: Optional[str] = None,
    ) -> dict:
        """Solve with the requested teacher, falling back to other healthy ones.

        Real providers can be healthy on a model-list probe yet fail an actual
        chat call (e.g. exhausted credits -> HTTP 429).  Honest fallback: try
        other *currently available* teachers and NEVER fabricate an answer; if
        every candidate fails, raise :class:`TeacherCallError` listing the real
        failures.  ``teacher_failures`` in the result documents what happened.
        """
        question = _problem_text(problem_like)
        candidates: list[tuple[str, Teacher]] = []
        seen: set[str] = set()
        if teacher_key:
            candidates.append((teacher_key, self._teacher(teacher_key)))
            seen.add(teacher_key)
        for t in self.available():
            if t.key not in seen:
                candidates.append((t.key, t))
                seen.add(t.key)
        if not candidates:
            raise TeacherUnavailable("no healthy teachers available")

        failures: list[str] = []
        tried: list[str] = []
        for _key, teacher in candidates:
            tried.append(teacher.key)
            try:
                answer = self._chat(teacher, SOLUTION_ROLE, question)
            except TeacherCallError as exc:
                failures.append(str(exc))
                continue
            return {
                "teacher": teacher.key,
                "solution": answer,
                "teachers_tried": tried,
                "teacher_failures": failures,
            }
        raise TeacherCallError(
            "all healthy teachers failed: " + (" | ".join(failures))
        )

    def critique(
        self,
        problem_like: Any,
        solution: str,
        *,
        teacher_key: Optional[str] = None,
    ) -> dict:
        teacher = self._teacher(teacher_key)
        prompt = (
            f"PROBLEM: {_problem_text(problem_like)}\n\n"
            f"SOLUTION TO REVIEW:\n{solution}"
        )
        raw = self._chat(teacher, CRITIQUE_ROLE, prompt)
        return {"teacher": teacher.key, "verdict": raw}

    def counterexamples(
        self,
        problem_like: Any,
        solution: str,
        *,
        teacher_key: Optional[str] = None,
    ) -> dict:
        teacher = self._teacher(teacher_key)
        prompt = (
            f"PROBLEM: {_problem_text(problem_like)}\n\n"
            f"PROPOSED SOLUTION:\n{solution}"
        )
        raw = self._chat(teacher, COUNTEREXAMPLE_ROLE, prompt)
        return {"teacher": teacher.key, "counterexample_critique": raw}

    def verification_criteria(
        self,
        problem_like: Any,
        *,
        teacher_key: Optional[str] = None,
    ) -> dict:
        teacher = self._teacher(teacher_key)
        raw = self._chat(teacher, CRITERIA_ROLE, _problem_text(problem_like))
        return {"teacher": teacher.key, "criteria": raw}

    def explain_failure(
        self,
        problem_like: Any,
        attempt: str,
        *,
        teacher_key: Optional[str] = None,
    ) -> dict:
        teacher = self._teacher(teacher_key)
        prompt = f"PROBLEM: {_problem_text(problem_like)}\n\nLEARNER ATTEMPT:\n{attempt}"
        raw = self._chat(teacher, EXPLAIN_ROLE, prompt)
        return {"teacher": teacher.key, "explanation": raw}

    def create_lesson(
        self,
        problem_like: Any,
        solution: str,
        *,
        evidence: Optional[list[str]] = None,
        teacher_key: Optional[str] = None,
    ) -> dict:
        teacher = self._teacher(teacher_key)
        prompt = (
            f"PROBLEM: {_problem_text(problem_like)}\n\n"
            f"CORRECT SOLUTION:\n{solution}\n\n"
            f"EVIDENCE IDs: {', '.join(evidence or []) or 'none'}"
        )
        raw = self._chat(teacher, LESSON_ROLE, prompt)
        return {"teacher": teacher.key, "lesson_draft": raw}

    # ------------------------------------------------------------------
    # Disagreement resolution (never guesses)
    # ------------------------------------------------------------------
    def compare_solutions(
        self,
        problem_like: Any,
        solution_a: str,
        teacher_a: str,
        solution_b: str,
        teacher_b: str,
        *,
        verifier: Optional[Verifier] = None,
        sandbox: Optional[Any] = None,
    ) -> dict:
        """Resolve a teacher disagreement.

        * identical normalized answers -> ``CONVERGED``;
        * a sandbox verifier is available and the task is verifiable -> the
          passing solution wins (``RESOLVED_VERIFICATION``);
        * otherwise -> ``UNVERIFIED`` with both answers preserved (no guess).
        """
        if _normalize(solution_a) == _normalize(solution_b):
            return {
                "outcome": "CONVERGED",
                "consensus": True,
                "solution": solution_a,
                "teachers": [teacher_a, teacher_b],
                "method": "identical",
            }

        if verifier is not None:
            try:
                verdict_a = verifier(_problem_text(problem_like), solution_a)
                verdict_b = verifier(_problem_text(problem_like), solution_b)
            except Exception as exc:
                return {
                    "outcome": "UNVERIFIED",
                    "consensus": False,
                    "teachers": [teacher_a, teacher_b],
                    "verification_error": str(exc),
                    "solutions": {"a": solution_a, "b": solution_b},
                }
            a_ok = verdict_a.get("outcome") == "VERIFIED"
            b_ok = verdict_b.get("outcome") == "VERIFIED"
            if a_ok and b_ok:
                return {
                    "outcome": "CONVERGED",
                    "consensus": True,
                    "solution": solution_a,
                    "teachers": [teacher_a, teacher_b],
                    "method": "sandbox_verification",
                    "verification": {"a": verdict_a, "b": verdict_b},
                }
            if a_ok and not b_ok:
                return {
                    "outcome": "RESOLVED_VERIFICATION",
                    "consensus": True,
                    "solution": solution_a,
                    "teachers": [teacher_a],
                    "method": "sandbox_verification",
                    "verification": {"a": verdict_a, "b": verdict_b},
                }
            if b_ok and not a_ok:
                return {
                    "outcome": "RESOLVED_VERIFICATION",
                    "consensus": True,
                    "solution": solution_b,
                    "teachers": [teacher_b],
                    "method": "sandbox_verification",
                    "verification": {"a": verdict_a, "b": verdict_b},
                }

        return {
            "outcome": "UNVERIFIED",
            "consensus": False,
            "teachers": [teacher_a, teacher_b],
            "note": "teachers disagree and the task was not verifiable; both "
            "answers preserved for human/evidence review",
            "solutions": {"a": solution_a, "b": solution_b},
            "sandbox_available": sandbox is not None,
        }

    def _teacher(self, teacher_key: Optional[str]) -> Teacher:
        if teacher_key is None:
            return self.select()
        teacher = self._teacher_map.get(teacher_key)
        if teacher is None:
            raise TeacherUnavailable(f"unknown teacher key {teacher_key!r}")
        return teacher

    def mesh_status(self) -> dict:
        teachers = sorted(
            (t.snapshot() for t in self._teachers), key=lambda s: s["provider"]
        )
        healthy = sum(1 for t in self._teachers if t.ready())
        return {
            "status": "HEALTHY" if healthy else "UNAVAILABLE",
            "healthy": healthy,
            "total": len(self._teachers),
            "teachers": teachers,
        }


def _problem_text(problem_like: Any) -> str:
    if isinstance(problem_like, str):
        return problem_like
    question = getattr(problem_like, "question", None)
    if question:
        context = getattr(problem_like, "context", "") or ""
        return f"{question}\n\nContext: {context}".strip()
    return str(problem_like)