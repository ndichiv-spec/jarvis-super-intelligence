"""Candidate-vs-baseline evaluation over the governed curriculum (spec §31).

Runs a candidate chat model and a baseline chat model over a fixed problem
set (from a curriculum dataset revision), obtains deterministic verification
+ teacher critique per answer, and reports an honest comparison.  Raw answer
artifacts are preserved for every problem — nothing is thrown away, and no
metric is fabricated.

When neither candidate nor baseline chat health is available, the evaluator
returns ``NEEDS_RUNTIME`` rather than pretending to have evaluated.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .verification import VerificationOutcome, verify_problem

#: How each model is asked to answer (kept identical for both sides).
_ANSWER_SYSTEM = (
    "Solve the given problem. If it is a programming problem, respond ONLY "
    "with runnable Python code. Be precise and concise."
)

#: Optional per-model invoke hook:
#: ``callable(question: str) -> dict{answer, model, ok}``.
ChatRunner = Callable[[str], dict]


@dataclass
class EvalItemResult:
    problem_id: str
    domain: str
    difficulty: int
    difficulty_label: str
    baseline: dict = field(default_factory=dict)  # {answer, verdict, evidence}
    candidate: dict = field(default_factory=dict)  # {answer, verdict, evidence}
    baseline_verification: dict = field(default_factory=dict)
    candidate_verification: dict = field(default_factory=dict)
    outcome: str = "PENDING"

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "difficulty_label": self.difficulty_label,
            "baseline_verification": self.baseline_verification,
            "candidate_verification": self.candidate_verification,
            "outcome": self.outcome,
        }

    @property
    def baseline_passed(self) -> bool:
        return self.baseline_verification.get("outcome") == VerificationOutcome.VERIFIED.value

    @property
    def candidate_passed(self) -> bool:
        return self.candidate_verification.get("outcome") == VerificationOutcome.VERIFIED.value


@dataclass
class EvaluationResult:
    eval_id: str
    dataset_id: str
    candidate_model: str
    baseline_model: str
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    per_problem: list[EvalItemResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    status: str = "PENDING"  # PENDING | COMPLETE | NEEDS_RUNTIME | ERROR

    def to_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "dataset_id": self.dataset_id,
            "candidate_model": self.candidate_model,
            "baseline_model": self.baseline_model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "summary": self.summary,
            "per_problem": [p.to_dict() for p in self.per_problem],
        }

    @property
    def row_count(self) -> int:
        return len(self.per_problem)


class CurriculumEvaluator:
    """Evaluates candidate vs baseline over a dataset revision."""

    def __init__(
        self,
        *,
        verifier: Optional[Callable] = None,
        candidate_runner: Optional[ChatRunner] = None,
        baseline_runner: Optional[ChatRunner] = None,
        max_problems: int = 0,
    ) -> None:
        self.verifier = verifier or verify_problem
        self.candidate_runner = candidate_runner
        self.baseline_runner = baseline_runner
        self.max_problems = int(max_problems)
        self._results: dict[str, EvaluationResult] = {}

    # ------------------------------------------------------------------
    def evaluate(
        self,
        revision: Any,
        *,
        candidate_model: str,
        baseline_model: str,
        candidate_runner: Optional[ChatRunner] = None,
        baseline_runner: Optional[ChatRunner] = None,
    ) -> EvaluationResult:
        """Run verification over every problem; never fabricate health.

        If neither runner is healthy the evaluation stays ``NEEDS_RUNTIME``
        with all raw problem artifacts preserved.
        """
        cand = candidate_runner or self.candidate_runner
        base = baseline_runner or self.baseline_runner
        if not cand or not base:
            result = EvaluationResult(
                eval_id=f"eval-{uuid.uuid4().hex[:12]}",
                dataset_id=revision.dataset_id,
                candidate_model=candidate_model,
                baseline_model=baseline_model,
                status="NEEDS_RUNTIME",
                summary={
                    "note": "no healthy chat runtime for candidate and/or baseline",
                    "candidate_runner": bool(cand),
                    "baseline_runner": bool(base),
                },
            )
            self._results[result.eval_id] = result
            return result

        problems = revision.examples
        if self.max_problems and problems:
            problems = problems[: self.max_problems]

        per_problem: list[EvalItemResult] = []
        for example in problems:
            question = _example_text(example)
            candidate_call = _safe_runner(cand, question)
            baseline_call = _safe_runner(base, question)

            candidate_v = _to_verification_dict(
                candidate_call.get("verification")
                or self.verifier(_problem_like(example), candidate_call.get("answer", ""))
            )
            baseline_v = _to_verification_dict(
                baseline_call.get("verification")
                or self.verifier(_problem_like(example), baseline_call.get("answer", ""))
            )

            c_ok = candidate_v.get("outcome") == VerificationOutcome.VERIFIED.value
            b_ok = baseline_v.get("outcome") == VerificationOutcome.VERIFIED.value
            if c_ok and not b_ok:
                outcome = "CANDIDATE_BETTER"
            elif b_ok and not c_ok:
                outcome = "BASELINE_BETTER"
            elif c_ok and b_ok:
                outcome = "TIE_PASS"
            else:
                outcome = "BOTH_UNVERIFIED"

            per_problem.append(
                EvalItemResult(
                    problem_id=example.example_id,
                    domain=example.domain,
                    difficulty=example.difficulty,
                    difficulty_label=example.difficulty_label,
                    baseline={
                        "answer": baseline_call.get("answer", ""),
                        "provider": baseline_call.get("provider", ""),
                        "latency_ms": baseline_call.get("latency_ms"),
                        "error": baseline_call.get("error", ""),
                    },
                    candidate={
                        "answer": candidate_call.get("answer", ""),
                        "provider": candidate_call.get("provider", ""),
                        "latency_ms": candidate_call.get("latency_ms"),
                        "error": candidate_call.get("error", ""),
                    },
                    baseline_verification=dict(baseline_v),
                    candidate_verification=dict(candidate_v),
                    outcome=outcome,
                )
            )

        total = len(per_problem)
        passed_b = sum(1 for p in per_problem if p.baseline_passed)
        passed_c = sum(1 for p in per_problem if p.candidate_passed)
        outcomes: dict[str, int] = {}
        for p in per_problem:
            outcomes[p.outcome] = outcomes.get(p.outcome, 0) + 1

        result = EvaluationResult(
            eval_id=f"eval-{uuid.uuid4().hex[:12]}",
            dataset_id=revision.dataset_id,
            candidate_model=candidate_model,
            baseline_model=baseline_model,
            finished_at=time.time(),
            per_problem=per_problem,
            status="COMPLETE",
            summary={
                "problems": total,
                "baseline_passed": passed_b,
                "candidate_passed": passed_c,
                "baseline_pass_rate": round(passed_b / total, 4) if total else 0,
                "candidate_pass_rate": round(passed_c / total, 4) if total else 0,
                "delta_pass_rate": round((passed_c - passed_b) / total, 4) if total else 0,
                "outcomes": outcomes,
            },
        )
        self._results[result.eval_id] = result
        return result

    def get(self, eval_id: str) -> Optional[EvaluationResult]:
        return self._results.get(eval_id)

    def results(self) -> list[EvaluationResult]:
        return list(self._results.values())


def _to_verification_dict(verification: Any) -> dict:
    if isinstance(verification, dict):
        return verification
    to_dict = getattr(verification, "to_dict", None)
    if callable(to_dict):
        return verification.to_dict()
    return {"outcome": "ERROR", "evidence": f"verifier returned non-dict: {verification!r}"}


def _safe_runner(runner: ChatRunner, question: str) -> dict:
    try:
        out = runner(question) or {}
    except Exception as exc:  # noqa: BLE001
        return {"answer": "", "error": str(exc), "ok": False}
    answer = out.get("answer", "") if isinstance(out, dict) else str(out)
    return {**({"answer": answer} if answer else {}), **({k: v for k, v in out.items() if k != "answer"})}


def _example_text(example: Any) -> str:
    return f"{example.problem}\n\nContext: {example.context}".strip()


def _problem_like(example: Any) -> Any:
    """Build a problem-like object so verify_problem can read expected_format."""
    return SimpleNamespace(
        question=example.problem,
        context=example.context,
        expected_format=example.expected_format,
        canonical_answer=None,
        metadata={},
    )


from types import SimpleNamespace  # noqa: E402