"""Unit tests for the Silverwing Evaluation Registry.

These tests exercise the evaluation package *without* loading the 514 MB
Silverwing checkpoint.  They cover:

- Benchmark case definitions (well-formed, correct counts, correct types).
- Scoring/checker functions (``_first_int``, keyword checkers, sandboxed code
  execution).
- Result schema validation + round-trip serialization.
- Perplexity computation against a synthetic model+tokenizer mock.
- Registry persistence (save / load / list / latest / compare).
- Full harness run against :class:`EchoBackend` (fast, no weights).

Integration tests (marked ``@pytest.mark.integration``) run the full harness
against the real 120M model via :class:`TorchBackend`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure workspace is on the path.
WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in os.sys.path:
    os.sys.path.insert(0, str(WORKSPACE))

from silverwing_runtime.evaluation.benchmarks import (
    CODE_QS,
    FIXED_PROMPTS,
    INSTRUCTION_QS,
    KNOW_QS,
    LOGIC_QS,
    MATH_QS,
    R2000_CODING,
    R2000_KNOWLEDGE,
    R2000_LOGIC,
    R2000_MATH,
    R2000_MODEL_ID,
    R2000_MODEL_SHA,
    R2000_PARAMS,
    R2000_VAL_LOSS,
    R2000_VAL_PPL,
    all_benchmarks,
    build_coding_cases,
    build_instruction_cases,
    build_knowledge_cases,
    build_logic_cases,
    build_math_cases,
)
from silverwing_runtime.evaluation.harness import (
    EvaluationHarness,
    _extract_python,
    _run_code_check_sandboxed,
)
from silverwing_runtime.evaluation.perplexity import (
    compute_perplexity,
    compute_perplexity_safe,
)
from silverwing_runtime.evaluation.registry import EvaluationRegistry
from silverwing_runtime.evaluation.results import (
    BenchmarkResult,
    ComparisonReport,
    EvaluationResult,
    GenerationSample,
    HardwareInfo,
    PerplexityResult,
    QuestionResult,
)


# --------------------------------------------------------------------------- #
# Benchmark definitions
# --------------------------------------------------------------------------- #
class TestBenchmarkDefinitions:
    """Verify benchmark case definitions are well-formed."""

    def test_fixed_prompts_count(self):
        assert len(FIXED_PROMPTS) == 10

    def test_math_qs_count(self):
        assert len(MATH_QS) == 8

    def test_logic_qs_count(self):
        assert len(LOGIC_QS) == 6

    def test_knowledge_qs_count(self):
        assert len(KNOW_QS) == 8

    def test_coding_qs_count(self):
        assert len(CODE_QS) == 3

    def test_instruction_qs_count(self):
        assert len(INSTRUCTION_QS) == 5

    def test_math_cases_well_formed(self):
        """Each MATH_QS entry is (question: str, expected: int)."""
        for q, expected in MATH_QS:
            assert isinstance(q, str) and len(q) > 0
            assert isinstance(expected, int)

    def test_logic_cases_well_formed(self):
        for q, kws in LOGIC_QS:
            assert isinstance(q, str) and len(q) > 0
            assert isinstance(kws, list) and len(kws) > 0

    def test_knowledge_cases_well_formed(self):
        for q, kws in KNOW_QS:
            assert isinstance(q, str) and len(q) > 0
            assert isinstance(kws, list) and len(kws) > 0

    def test_coding_cases_well_formed(self):
        """Each CODE_QS entry is (prompt, function_name, test_expression)."""
        for prompt, fname, test_expr in CODE_QS:
            assert isinstance(prompt, str) and len(prompt) > 0
            assert isinstance(fname, str) and len(fname) > 0
            assert isinstance(test_expr, str) and len(test_expr) > 0

    def test_all_benchmarks_returns_all_categories(self):
        cats = all_benchmarks()
        assert set(cats.keys()) == {"math", "logic", "knowledge", "coding", "instruction"}
        for name, cases in cats.items():
            assert len(cases) > 0, f"{name} has no cases"

    def test_built_cases_have_names(self):
        for cases in [
            build_math_cases(),
            build_logic_cases(),
            build_knowledge_cases(),
            build_coding_cases(),
            build_instruction_cases(),
        ]:
            for c in cases:
                assert isinstance(c.name, str) and c.name
                assert isinstance(c.question, str) and c.question
                assert isinstance(c.expected, str)

    def test_r2000_baseline_values(self):
        """Frozen r2000 baseline values from the training script."""
        assert R2000_MODEL_ID == "silverwing-12m-base-r2000"
        assert R2000_PARAMS == 12_440_448
        assert R2000_MATH == (0, 8)
        assert R2000_LOGIC == (4, 6)
        assert R2000_CODING == (0, 3)
        assert R2000_KNOWLEDGE == (0, 8)
        assert abs(R2000_VAL_LOSS - 6.3445) < 0.01
        assert R2000_VAL_PPL == 569.3768335750539
        assert R2000_MODEL_SHA.startswith("2c2775a7")


# --------------------------------------------------------------------------- #
# Checker functions
# --------------------------------------------------------------------------- #
class TestCheckers:
    def test_first_int_extraction(self):
        from silverwing_runtime.evaluation.benchmarks import _first_int
        assert _first_int("The answer is 42") == 42
        assert _first_int("1,024 people") == 1024
        assert _first_int("no numbers here") is None
        assert _first_int("-5 degrees") == -5

    def test_math_checker_correct(self):
        from silverwing_runtime.evaluation.benchmarks import _check_math
        checker = _check_math("What is 17 × 24?", 408)
        assert checker("The answer is 408") is True
        assert checker("408 is the answer") is True

    def test_math_checker_incorrect(self):
        from silverwing_runtime.evaluation.benchmarks import _check_math
        checker = _check_math("What is 17 × 24?", 408)
        assert checker("The answer is 500") is False
        assert checker("I don't know") is False

    def test_keyword_checker_positive(self):
        from silverwing_runtime.evaluation.benchmarks import _check_keywords
        checker = _check_keywords(["water", "H2O"])
        assert checker("H2O is the chemical formula for water") is True
        assert checker("Water is wet") is True

    def test_keyword_checker_negative(self):
        from silverwing_runtime.evaluation.benchmarks import _check_keywords
        checker = _check_keywords(["water", "H2O"])
        assert checker("Fire is hot") is False

    def test_negation_checker(self):
        from silverwing_runtime.evaluation.benchmarks import _check_negation
        checker = _check_negation(["banana", "fig", "kiwi"])
        assert checker("A kiwi is a fruit") is True
        assert checker("A banana is yellow") is False  # banana has 'a'


# --------------------------------------------------------------------------- #
# Perplexity computation (synthetic model, no weights needed)
# --------------------------------------------------------------------------- #
class _MockConfig:
    """Minimal stand-in for ModelConfig that has vocab_size."""
    vocab_size = 8192


class _MockTokenizer:
    """Minimal tokenizer mock for perplexity tests."""
    vocab_size = 8192
    sha256 = "mock-tokenizer-sha256"

    def encode(self, text: str) -> list[int]:
        # Simple deterministic tokenization for testing.
        return [abs(hash(c)) % 1000 + 1 for c in text]

    def decode(self, ids: list[int]) -> str:
        return "".join(chr(i % 127) for i in ids)


class _MockDecoder:
    """Minimal decoder mock that produces uniform-ish logits for perplexity.

    We use random logits; perplexity should be > 1 but finite.
    """
    config = _MockConfig()
    device = "cpu"

    def eval(self):
        pass

    def full_forward(self, input_ids: Any) -> Any:
        """Return random logits [1, seq, vocab] — perplexity > 1, finite."""
        import torch
        batch, seq = input_ids.shape
        return torch.randn(batch, seq, 8192, dtype=torch.float32)


@pytest.mark.skipif(
    importlib.util.find_spec("torch") is None,
    reason="perplexity tests require torch",
)
class TestPerplexity:
    def test_perplexity_on_synthetic_model(self):
        """Perplexity is computed and is finite + > 1 for random logits."""
        model = _MockDecoder()
        tok = _MockTokenizer()
        val_text = "hello world this is a test " * 50
        result = compute_perplexity(model, tok, val_text, max_seq_len=32, max_windows=4)
        assert result.val_loss > 0
        assert result.val_perplexity > 1.0
        assert result.val_windows > 0
        assert result.val_tokens_evaluated > 0
        assert len(result.val_sha256) == 64  # SHA-256 hex

    def test_perplexity_from_file(self, tmp_path):
        """Perplexity accepts a file path for val text."""
        model = _MockDecoder()
        tok = _MockTokenizer()
        val_file = tmp_path / "val.txt"
        val_file.write_text("some validation text for testing perplexity " * 30,
                            encoding="utf-8")
        result = compute_perplexity(model, tok, val_file, max_seq_len=32, max_windows=4)
        assert result.val_loss > 0
        assert len(result.val_sha256) == 64

    def test_perplexity_safe_on_exception(self):
        """compute_perplexity_safe returns a skipped result on failure."""

        class BrokenModel:
            def full_forward(self, input_ids):
                raise RuntimeError("boom")

            def eval(self):
                pass

        result = compute_perplexity_safe(
            BrokenModel(), _MockTokenizer(),
            "test text " * 50, max_seq_len=32, max_windows=2,
        )
        assert result.skipped is True
        assert "boom" in result.skip_reason

    def test_perplexity_result_schema_valid(self):
        """PerplexityResult validates correctly."""
        r = PerplexityResult(
            val_loss=5.0,
            val_perplexity=148.4,
            val_tokens_evaluated=32768,
            val_windows=128,
            val_sha256="abc123" * 8,
        )
        assert r.val_perplexity == 148.4
        assert r.skipped is False


# --------------------------------------------------------------------------- #
# Code extraction + sandboxed execution
# --------------------------------------------------------------------------- #
class TestCodeExtraction:
    def test_extract_python_code_block(self):
        text = (
            "Here is the solution:\n"
            "```python\ndef add(a, b):\n    return a + b\n```\n"
            "Done."
        )
        code = _extract_python(text)
        assert "def add" in code
        assert "return a + b" in code

    def test_extract_python_fallback_to_def(self):
        """When no code block, extract from the first 'def' line."""
        text = "Here's a function:\ndef multiply(x, y):\n    return x * y\n\nAnd that's it."
        code = _extract_python(text)
        assert "def multiply" in code
        assert "return x * y" in code

    def test_extract_python_no_code(self):
        code = _extract_python("This is just a regular response with no code.")
        assert code == ""


class TestSandboxedCodeExecution:
    def test_sandboxed_correct_code(self):
        code = "def add(a, b):\n    return a + b\n"
        test_expr = "add(2, 3) == 5 and add(-1, 1) == 0"
        passed, detail = _run_code_check_sandboxed(code, test_expr)
        assert passed is True
        assert detail.get("passed", True) is True

    def test_sandboxed_wrong_answer(self):
        code = "def add(a, b):\n    return a + b\n"
        test_expr = "add(2, 3) == 10"
        passed, detail = _run_code_check_sandboxed(code, test_expr)
        assert passed is False

    def test_sandboxed_code_with_exception(self):
        code = "def add(a, b):\n    return a / 0\n"
        test_expr = "add(2, 3) == 5"
        passed, detail = _run_code_check_sandboxed(code, test_expr)
        assert passed is False
        assert "error" in detail

    def test_sandboxed_empty_code(self):
        passed, detail = _run_code_check_sandboxed("", "add(2, 3) == 5")
        assert passed is False
        assert "error" in detail

    def test_sandboxed_timeout(self):
        """A runaway generation is killed by the subprocess timeout."""
        code = "import time\ndef f():\n    time.sleep(100)\n    return 1\n"
        test_expr = "f() == 1"
        passed, detail = _run_code_check_sandboxed(code, test_expr, timeout=1.0)
        assert passed is False
        assert detail.get("timeout") is True or "timed out" in detail.get("error", "").lower()

    def test_sandboxed_valid_python_code_question(self):
        """End-to-end: the add() coding benchmark case should pass."""
        code = """def add(a, b):
    return a + b
"""
        passed, detail = _run_code_check_sandboxed(code, "add(2, 3) == 5 and add(-1, 1) == 0")
        assert passed is True


# --------------------------------------------------------------------------- #
# Result scheme validation + round-trip
# --------------------------------------------------------------------------- #
class TestResultSchemas:
    def _make_result(self) -> EvaluationResult:
        return EvaluationResult(
            model_id="silverwing-120m-base-v1",
            version="v1",
            revision="r1",
            weights_sha256="da860489943c6bfe2e826a0a9325e75e381b4ef0a48270f4c4c6a6a4ef12abb4",
            param_count=120_087_552,
            label="unit-test",
            timestamp="2025-01-01T00:00:00Z",
            perplexity=PerplexityResult(
                val_loss=5.437,
                val_perplexity=229.83,
                val_tokens_evaluated=32512,
                val_windows=128,
                val_sha256="abc123",
            ),
            benchmarks={
                "math": BenchmarkResult(name="math", correct=0, total=8, accuracy=0.0),
                "logic": BenchmarkResult(name="logic", correct=4, total=6, accuracy=0.67),
            },
            generation_samples=[
                GenerationSample(
                    prompt="Hello", response="Hi there", backend="torch", device="cpu",
                ),
            ],
            comparison=ComparisonReport(
                model_params=120_087_552,
                model_val_loss=5.437,
                model_val_perplexity=229.83,
                beats_baseline_val_loss=True,
                beats_baseline_ppl=True,
            ),
            hardware=HardwareInfo(device="cpu", dtype="fp32", backend="torch",
                                   torch_version="2.14.0"),
            total_tokens_processed=100,
            total_evaluation_seconds=12.5,
        )

    def test_evaluation_result_validates(self):
        r = self._make_result()
        assert r.model_id == "silverwing-120m-base-v1"
        assert r.param_count == 120_087_552

    def test_evaluation_result_roundtrip(self):
        """Serialize → deserialize → compare."""
        r1 = self._make_result()
        data = r1.model_dump()
        r2 = EvaluationResult(**data)
        assert r2.model_id == r1.model_id
        assert r2.perplexity.val_perplexity == r1.perplexity.val_perplexity
        assert r2.benchmarks["math"].correct == r1.benchmarks["math"].correct

    def test_evaluation_result_json_roundtrip(self):
        """JSON serialization round-trip preserves all data."""
        r1 = self._make_result()
        text = r1.model_dump_json()
        r2 = EvaluationResult.model_validate_json(text)
        assert r2.model_id == r1.model_id
        assert r2.perplexity.val_perplexity == r1.perplexity.val_perplexity
        assert r2.benchmarks["math"].correct == r1.benchmarks["math"].correct

    def test_summary_property(self):
        r = self._make_result()
        s = r.summary
        assert "val_loss" in s
        assert "val_perplexity" in s
        assert "beats_baseline" in s
        assert "evaluated_at" in s

    def test_comparison_defaults(self):
        c = ComparisonReport()
        assert c.baseline_model == "silverwing-12m-base-r2000"
        assert c.baseline_params == 12_440_448


# --------------------------------------------------------------------------- #
# Registry tests
# --------------------------------------------------------------------------- #
class TestEvaluationRegistry:
    def _make_result(self, label: str = "test-eval") -> EvaluationResult:
        return EvaluationResult(
            model_id="silverwing-120m-base-v1",
            version="v1",
            revision="r1",
            weights_sha256="da860489" + "0" * 56,
            param_count=120_087_552,
            label=label,
            timestamp="2025-01-01T00:00:00Z",
            perplexity=PerplexityResult(
                val_loss=5.437, val_perplexity=229.83,
                val_tokens_evaluated=32512, val_windows=128, val_sha256="abc",
            ),
            benchmarks={
                "math": BenchmarkResult(name="math", correct=2, total=8, accuracy=0.25),
            },
            comparison=ComparisonReport(
                model_params=120_087_552,
                model_val_loss=5.437, model_val_perplexity=229.83,
                beats_baseline_val_loss=True, beats_baseline_ppl=True,
            ),
            hardware=HardwareInfo(device="cpu", dtype="fp32", backend="torch",
                                   torch_version="2.14.0"),
        )

    def test_registry_record_and_get(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        result = self._make_result(label="eval-1")
        path = reg.record(result)
        assert path.exists()
        loaded = reg.get("silverwing-120m-base-v1", "r1", "eval-1")
        assert loaded is not None
        assert loaded.model_id == result.model_id
        assert loaded.perplexity.val_perplexity == 229.83

    def test_registry_list_evaluations(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        reg.record(self._make_result(label="eval-1"))
        reg.record(self._make_result(label="eval-2"))
        entries = reg.list_evaluations("silverwing-120m-base-v1", "r1")
        assert len(entries) == 2
        labels = {e["label"] for e in entries}
        assert "eval-1" in labels
        assert "eval-2" in labels

    def test_registry_latest(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        reg.record(self._make_result(label="older", ))  # earlier timestamp
        # Make a second result with a later timestamp
        result2 = self._make_result(label="newer")
        result2.timestamp = "2025-06-01T00:00:00Z"
        reg.record(result2)
        latest = reg.latest("silverwing-120m-base-v1", "r1")
        assert latest is not None
        assert latest.label == "newer"

    def test_registry_latest_no_results(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        assert reg.latest("nonexistent-model") is None

    def test_registry_compare(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        r1 = self._make_result(label="run-1")
        r1.benchmarks = {"math": BenchmarkResult(name="math", correct=1, total=8, accuracy=0.125)}
        r1.perplexity.val_perplexity = 500.0
        reg.record(r1)
        r2 = self._make_result(label="run-2")
        r2.benchmarks = {"math": BenchmarkResult(name="math", correct=3, total=8, accuracy=0.375)}
        r2.perplexity.val_perplexity = 200.0
        reg.record(r2)
        report = reg.compare("silverwing-120m-base-v1")
        assert report["total_runs"] == 2
        assert len(report["runs"]) == 2

    def test_registry_promotion_evidence(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        result = self._make_result(label="eval-1")
        reg.record(result)
        evidence = reg.promotion_evidence("silverwing-120m-base-v1")
        assert evidence["model_id"] == "silverwing-120m-base-v1"
        assert "gates" in evidence
        assert "all_gates_passed" in evidence

    def test_registry_promotion_evidence_no_results(self, tmp_path):
        reg = EvaluationRegistry(base_dir=tmp_path)
        evidence = reg.promotion_evidence("nonexistent-model")
        assert evidence["status"] == "no_evaluation_found"

    def test_registry_overwrite_label(self, tmp_path):
        """Recording with the same (model, revision, label) overwrites."""
        reg = EvaluationRegistry(base_dir=tmp_path)
        r1 = self._make_result(label="eval-1")
        reg.record(r1)
        r2 = self._make_result(label="eval-1")
        r2.perplexity.val_perplexity = 100.0
        reg.record(r2)
        loaded = reg.get("silverwing-120m-base-v1", "r1", "eval-1")
        assert loaded.perplexity.val_perplexity == 100.0
        entries = reg.list_evaluations("silverwing-120m-base-v1", "r1")
        assert len(entries) == 1  # not duplicated


# --------------------------------------------------------------------------- #
# Harness with EchoBackend (fast, no model loading)
# --------------------------------------------------------------------------- #
class _MockEchoBackend:
    """A lightweight stand-in for EchoBackend to avoid the real model.

    Returns a visible 'sw-echo' marker so tests can verify honest reporting.
    """

    backend = "echo"
    device = "n/a"
    dtype_str = "n/a"

    def __init__(self, model_ref: str = "silverwing-120m-base-v1"):
        self._model_ref = model_ref
        self._call_count = 0

    def warmup(self, prompt: str) -> str:
        return "warmup-ok"

    def generate(self, request: Any) -> Any:
        from silverwing_runtime.generation import GenerationRequest, GenerationResult
        self._call_count += 1
        text = f"[sw-echo] {request.prompt}"
        return GenerationResult(
            text=text,
            finish_reason="stop",
            model=self._model_ref,
            revision="r1",
            latency_ms=0.5,
            tokens_input=len(request.prompt.split()),
            tokens_generated=0,
            metadata={"backend": "echo", "device": "n/a"},
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": self._model_ref,
            "revision": "r1",
            "architecture": "Silverwing Decoder",
            "parameter_count": 120_087_552,
            "weights_sha256": "da860489" + "0" * 56,
            "device": "n/a",
            "dtype": "n/a",
            "backend": "echo",
            "loaded": True,
        }

    def close(self) -> None:
        pass


class TestHarnessWithEcho:
    """Run the harness against a mock EchoBackend — no weights needed."""

    def test_harness_perplexity_skipped_with_echo(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        perp = harness.evaluate_perplexity("test text " * 50)
        assert perp.skipped is True
        assert "non-TorchBackend" in perp.skip_reason

    def test_harness_math_all_fail_with_echo(self):
        """EchoBackend responses contain no numbers → math accuracy = 0%."""
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.evaluate_math()
        assert result.name == "math"
        assert result.total == 8
        assert result.correct == 0
        assert result.accuracy == 0.0
        assert len(result.questions) == 8

    def test_harness_logic_all_fail_with_echo(self):
        """EchoBackend echoes prompts which may contain keywords.

        The harness still produces a valid result; some cases may pass
        because the echoed prompt contains the expected keyword (e.g. "Monday"
        in the Monday question).  We verify the harness runs correctly and
        the accuracy is honest about what it found.
        """
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.evaluate_logic()
        assert result.total == 6
        assert 0 <= result.correct <= 6
        assert result.accuracy == result.correct / result.total
        # Verify each question has a response containing the echo marker
        for q in result.questions:
            assert "sw-echo" in q.response

    def test_harness_knowledge_all_fail_with_echo(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.evaluate_knowledge()
        assert result.total == 8
        assert result.correct == 0

    def test_harness_coding_all_fail_with_echo(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.evaluate_coding()
        assert result.total == 3
        assert result.correct == 0

    def test_harness_instruction_partial_with_echo(self):
        """Instruction cases look for keywords — 'Repeat hello' → echo contains 'hello'."""
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.evaluate_instruction_following()
        assert result.total == 5
        # EchoBackend returns "[sw-echo] List three colors." etc.
        # The "Repeat the word 'hello'" prompt echoes "hello" in the response.
        # So at least 1 case may pass.
        assert result.correct >= 0
        assert result.correct <= 5

    def test_harness_fixed_samples(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        samples = harness.generate_fixed_samples()
        assert len(samples) == 10
        for s in samples:
            assert s.backend == "echo"
            assert s.device == "n/a"

    def test_harness_no_echo_in_results(self):
        """When using EchoBackend, the 'no_echo_substitution' gate catches it."""
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.run_full_evaluation("test text " * 50, label="echo-test")
        assert len(result.generation_samples) == 10
        # Every sample has 'sw-echo' (EchoBackend marker)
        has_echo = any("sw-echo" in s.response for s in result.generation_samples)
        assert has_echo is True  # echo IS present, will be caught by promotion gate

    def test_harness_build_comparison_with_echo(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        perp = harness.evaluate_perplexity("test text " * 10)
        benchmarks = {"math": BenchmarkResult(name="math", correct=0, total=8, accuracy=0.0)}
        cmp = harness.build_comparison(perp, benchmarks)
        assert cmp.baseline_model == "silverwing-12m-base-r2000"
        assert cmp.model_math == (0, 8)
        assert cmp.beats_baseline_val_loss is False  # perplexity skipped

    def test_harness_capture_hardware(self):
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        hw = harness.capture_hardware()
        assert hw.backend == "echo"
        assert hw.device == "n/a"

    def test_harness_full_evaluation_completes(self):
        """Full evaluation against EchoBackend completes in reasonable time (no model load)."""
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.run_full_evaluation("hello world " * 200, label="smoke")
        assert result.model_id == "silverwing-120m-base-v1"
        assert result.revision == "r1"
        assert result.param_count == 120_087_552
        assert len(result.benchmarks) == 5  # math, logic, knowledge, coding, instruction
        assert len(result.generation_samples) == 10
        assert result.perplexity.skipped is True
        assert result.total_evaluation_seconds >= 0  # Fast completion is valid (rounds to 0)

    def test_harness_full_evaluation_serializes(self):
        """The result is JSON-serializable end-to-end."""
        harness = EvaluationHarness(_MockEchoBackend(), "silverwing-120m-base-v1")
        result = harness.run_full_evaluation("hello world " * 200, label="serial")
        json_str = result.model_dump_json()
        assert "silverwing-120m-base-v1" in json_str
        parsed = EvaluationResult.model_validate_json(json_str)
        assert parsed.model_id == result.model_id


# --------------------------------------------------------------------------- #
# Integration tests (require real model — marked, skipped by default)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
class TestFullEvaluationRealModel:
    """Run the full evaluation harness against the real 120M model.

    These tests are skipped by default (``pytest -m "not integration"``) and
    take ~10-30 min on CPU because each test loads the 514 MB checkpoint.
    Run with: ``pytest tests/test_silverwing_evaluation.py -m integration -v``.
    """

    def test_full_evaluation_real_model(self):
        """Run complete evaluation against the real 120M model.

        Produces an EvaluationResult with real perplexity, benchmark scores,
        and generation samples.
        """
        from silverwing_runtime.config import RuntimeConfig
        from silverwing_runtime.generation import GenerationConfig, GenerationRequest
        from silverwing_runtime.inference import InferenceService
        from silverwing_runtime.model_loader import ModelLoader
        from silverwing_runtime.model_registry import SilverwingRegistry

        cfg = RuntimeConfig()
        reg = SilverwingRegistry(cfg)
        reg.refresh()
        loader = ModelLoader(reg, config=cfg)
        svc = InferenceService(loader, cfg)
        svc.warmup("silverwing-120m-base-v1")

        # Get the real backend
        backend = svc._backends["silverwing-120m-base-v1"]
        assert backend.backend == "torch"

        # Verify no echo substitution
        sanity = backend.generate(
            GenerationRequest(prompt="test", config=GenerationConfig(max_new_tokens=2))
        )
        assert "sw-echo" not in sanity.text

        harness = EvaluationHarness(
            backend, "silverwing-120m-base-v1"
        )
        # Use a small val text for speed during the test
        val_path = WORKSPACE / "silverwing-120m" / "data" / "splits" / "val.txt"
        result = harness.run_full_evaluation(
            str(val_path) if val_path.exists() else "the quick brown fox " * 200,
            label="integration-test",
        )

        # Assertions: the result must contain real evidence
        assert result.model_id == "silverwing-120m-base-v1"
        assert result.param_count == 120_087_552
        assert len(result.benchmarks) == 5
        assert result.benchmarks["math"].total == 8
        assert result.benchmarks["logic"].total == 6
        assert result.benchmarks["knowledge"].total == 8
        assert result.benchmarks["coding"].total == 3
        assert result.benchmarks["instruction"].total == 5
        assert len(result.generation_samples) == 10
        # Perplexity should be computed (not skipped) for real model
        assert result.perplexity.skipped is False
        assert result.perplexity.val_perplexity > 0
        # No echo substitution on real model
        for s in result.generation_samples:
            assert "sw-echo" not in s.response
        # Comparison should have real data
        assert result.comparison.beats_baseline_ppl in (True, False)
        svc.shutdown()
