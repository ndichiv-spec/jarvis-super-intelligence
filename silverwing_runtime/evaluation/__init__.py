"""Silverwing Evaluation Registry.

A standardized evaluation harness that tests a Silverwing model across
perplexity, math, logic, knowledge, coding, and instruction-following
benchmarks, then persists the structured results as evidence for model
promotion (spec sections 47-48).

Public API::

    from silverwing_runtime.evaluation import EvaluationHarness, EvaluationRegistry

    harness = EvaluationHarness(backend, model_ref)
    result = harness.run_full_evaluation(val_text_path, label="r1-eval")
    registry = EvaluationRegistry()
    registry.record(result)
    report = registry.promotion_evidence("silverwing-120m-base")
"""

from silverwing_runtime.evaluation.results import (
    BenchmarkResult,
    ComparisonReport,
    EvaluationResult,
    GenerationSample,
    HardwareInfo,
    PerplexityResult,
    QuestionResult,
)
from silverwing_runtime.evaluation.harness import (
    EvaluationHarness,
    _extract_python,
    _run_code_check_sandboxed,
)
from silverwing_runtime.evaluation.registry import EvaluationRegistry

__all__ = [
    # Schemas
    "BenchmarkResult",
    "ComparisonReport",
    "EvaluationResult",
    "GenerationSample",
    "HardwareInfo",
    "PerplexityResult",
    "QuestionResult",
    # Harness
    "EvaluationHarness",
    # Registry
    "EvaluationRegistry",
    # Helpers
    "_extract_python",
    "_run_code_check_sandboxed",
]
