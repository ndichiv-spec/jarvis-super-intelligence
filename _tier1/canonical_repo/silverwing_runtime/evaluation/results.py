"""Evaluation result schemas for the Silverwing Evaluation Registry.

Structured, immutable evidence that models can use for promotion decisions
(spec section 48).  Every field is populated from actual runtime activity —
nothing is fabricated (section 23).

The :class:`EvaluationResult` is the top-level container: it bundles
perplexity, per-category benchmark scores, fixed-prompt generation samples,
and an honest comparison against the r2000 baseline into a single document
that can be persisted and audited.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuestionResult(BaseModel):
    """Result of a single benchmark question.

    ``detail`` carries whatever extra information the evaluator produced —
    e.g. the extracted integer for a math answer, the matched keywords for a
    knowledge question, or the extracted code length for a coding question.
    """

    question: str
    prompt: str = ""
    response: str = ""
    passed: bool
    expected: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResult(BaseModel):
    """Aggregated score for one benchmark category."""

    name: str
    correct: int
    total: int
    accuracy: float
    questions: list[QuestionResult] = Field(default_factory=list)


class PerplexityResult(BaseModel):
    """Validation perplexity + loss for a model checkpoint."""

    val_loss: float
    val_perplexity: float
    val_tokens_evaluated: int
    val_windows: int
    val_sha256: str
    skipped: bool = False
    skip_reason: str = ""


class GenerationSample(BaseModel):
    """One fixed-prompt generation captured for quality inspection."""

    prompt: str
    response: str
    finish_reason: str = "stop"
    tokens_input: int = 0
    tokens_generated: int = 0
    latency_ms: float = 0.0
    backend: str = ""
    device: str = ""


class ComparisonReport(BaseModel):
    """Honest comparison of a model against the r2000 baseline.

    The r2000 (12M) baseline is frozen at the values recorded during the
    Silverwing-12M training run.  Deltas are computed from real measurements,
    never from estimates.
    """

    baseline_model: str = "silverwing-12m-base-r2000"
    baseline_params: int = 12_440_448
    baseline_val_loss: float = 6.3445424883384405
    baseline_val_perplexity: float = 569.3768335750539
    baseline_math: tuple[int, int] = (0, 8)
    baseline_logic: tuple[int, int] = (4, 6)
    baseline_coding: tuple[int, int] = (0, 3)
    baseline_knowledge: tuple[int, int] = (0, 8)

    model_val_loss: float = 0.0
    model_val_perplexity: float = 0.0
    model_math: tuple[int, int] = (0, 8)
    model_logic: tuple[int, int] = (0, 6)
    model_coding: tuple[int, int] = (0, 3)
    model_knowledge: tuple[int, int] = (0, 8)
    model_params: int = 0

    beats_baseline_val_loss: bool = False
    beats_baseline_ppl: bool = False
    math_improvement: float = 0.0
    logic_improvement: float = 0.0
    knowledge_improvement: float = 0.0
    coding_improvement: float = 0.0
    param_efficiency: float = 0.0  # val_ppl per million params


class HardwareInfo(BaseModel):
    """Hardware/runtime context captured during evaluation (honest reporting)."""

    device: str = ""
    dtype: str = ""
    backend: str = ""
    torch_version: str = ""
    cpu_ram_gb: float | None = None
    gpu_name: str | None = None
    gpu_vram_gb: float | None = None


class EvaluationResult(BaseModel):
    """Complete evaluation of one model checkpoint.

    This is the single document that provides evidence for model promotion
    (spec section 48).  It is self-contained: given a result, an auditor can
    verify the model's measured capabilities without re-running anything.
    """

    # --- identity ---
    model_id: str
    version: str
    revision: str
    weights_sha256: str
    param_count: int
    label: str
    timestamp: str

    # --- measurements ---
    perplexity: PerplexityResult
    benchmarks: dict[str, BenchmarkResult] = Field(default_factory=dict)
    generation_samples: list[GenerationSample] = Field(default_factory=list)
    comparison: ComparisonReport = Field(default_factory=ComparisonReport)
    hardware: HardwareInfo = Field(default_factory=HardwareInfo)
    total_tokens_processed: int = 0
    total_evaluation_seconds: float = 0.0

    @property
    def summary(self) -> dict[str, Any]:
        """Compact summary suitable for the model manifest's ``evaluation`` field."""
        return {
            "val_loss": self.perplexity.val_loss,
            "val_perplexity": self.perplexity.val_perplexity,
            "benchmarks": {
                name: {"correct": br.correct, "total": br.total, "accuracy": br.accuracy}
                for name, br in self.benchmarks.items()
            },
            "beats_baseline": {
                "val_loss": self.comparison.beats_baseline_val_loss,
                "ppl": self.comparison.beats_baseline_ppl,
            },
            "evaluated_at": self.timestamp,
            "elapsed_seconds": self.total_evaluation_seconds,
        }
