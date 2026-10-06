"""Phase 11 — Evaluation suite tests.

Validates the EvaluationSuite dataclass, registry, 12 standard suites,
scoring utilities, and graceful degradation of SuiteWrapper.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend.core import get_store  # noqa: E402
from jarvis_backend.evaluation_suite import (  # noqa: E402
    EvaluationSuite,
    EvaluationSuiteRegistry,
    ScoringMethod,
    ScoringRule,
    EvaluationTask,
    SuiteWrapper,
    score_accuracy,
    score_exact_match,
    score_f1,
)


@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("evaluation_suites").reset()
    EvaluationSuiteRegistry._suites = {}
    EvaluationSuiteRegistry._initialized = False
    yield
    get_store("evaluation_suites").reset()
    EvaluationSuiteRegistry._suites = {}
    EvaluationSuiteRegistry._initialized = False


@pytest.fixture()
def sample_suite():
    return EvaluationSuite(
        suite_id="test_suite",
        name="Test Suite",
        version="1",
        tasks=[
            EvaluationTask(
                task_id="math_arithmetic",
                name="Arithmetic",
                description="Basic math",
                metrics=["accuracy"],
                input_spec={"count": 15},
            ).to_dict()
        ],
        scoring_rules=[
            ScoringRule(
                metric_name="math_accuracy",
                method=ScoringMethod.ACCURACY.value,
                higher_is_better=True,
                unit="ratio",
            ).to_dict()
        ],
        required_capabilities=["compute.evaluation"],
        required_models=["text-generation"],
        resource_requirements={"min_vram_gb": 0, "offline_ok": True},
    )


# --------------------------------------------------------------------------- #
# ScoringMethod enum
# --------------------------------------------------------------------------- #
def test_scoring_method_values():
    assert ScoringMethod.ACCURACY.value == "accuracy"
    assert ScoringMethod.EXACT.value == "exact"
    assert ScoringMethod.F1.value == "f1"
    assert ScoringMethod.PERPLEXITY.value == "perplexity"
    assert ScoringMethod.PASS_AT_1.value == "pass_at_1"


# --------------------------------------------------------------------------- #
# EvaluationSuite dataclass
# --------------------------------------------------------------------------- #
def test_suite_versioned_id(sample_suite):
    assert sample_suite.versioned_id == "test_suite:v1"


def test_suite_to_dict(sample_suite):
    d = sample_suite.to_dict()
    assert d["suite_id"] == "test_suite"
    assert d["version"] == "1"
    assert "tasks" in d
    assert "scoring_rules" in d
    assert d["required_capabilities"] == ["compute.evaluation"]


def test_suite_from_dict_roundtrip(sample_suite):
    d = sample_suite.to_dict()
    loaded = EvaluationSuite.from_dict(d)
    assert loaded.suite_id == "test_suite"
    assert loaded.version == "1"
    assert len(loaded.tasks) == 1
    assert loaded.tasks[0]["task_id"] == "math_arithmetic"


def test_suite_save_and_load(sample_suite):
    sample_suite.save()
    loaded = EvaluationSuite.load(sample_suite.versioned_id)
    assert loaded is not None
    assert loaded.suite_id == "test_suite"


def test_suite_load_nonexistent():
    assert EvaluationSuite.load("nonexistent_suite:v1") is None


def test_suite_list_all(sample_suite):
    sample_suite.save()
    all_suites = EvaluationSuite.list_all()
    assert len(all_suites) >= 1


# --------------------------------------------------------------------------- #
# EvaluationSuiteRegistry
# --------------------------------------------------------------------------- #
def test_registry_has_standard_suites():
    EvaluationSuiteRegistry.initialize()
    suites = EvaluationSuiteRegistry.list_all()
    ids = [s.suite_id for s in suites]
    assert "math_reasoning" in ids
    assert "code_generation" in ids
    assert "general_reasoning" in ids
    assert "document_analysis" in ids
    assert "data_analysis" in ids
    assert "tool_use" in ids
    assert "rag" in ids
    assert "geography" in ids
    assert "security" in ids
    assert "instruction_following" in ids
    assert "generation_quality" in ids
    assert "perplexity" in ids


def test_registry_get_builtin():
    EvaluationSuiteRegistry.initialize()
    suite = EvaluationSuiteRegistry.get("math_reasoning:v1")
    assert suite is not None
    assert suite.versioned_id == "math_reasoning:v1"
    assert len(suite.tasks) > 0


def test_registry_get_builtin_by_suite_id():
    EvaluationSuiteRegistry.initialize()
    suite = EvaluationSuiteRegistry.get_by_id("math_reasoning")
    assert suite is not None


def test_registry_get_nonexistent():
    assert EvaluationSuiteRegistry.get("nonexistent_suite:v1") is None


# --------------------------------------------------------------------------- #
# Scoring utilities
# --------------------------------------------------------------------------- #
def test_score_accuracy_perfect():
    assert score_accuracy(correct=3, total=3) == pytest.approx(1.0)


def test_score_accuracy_none_correct():
    assert score_accuracy(correct=0, total=2) == pytest.approx(0.0)


def test_score_accuracy_partial():
    assert score_accuracy(correct=2, total=3) == pytest.approx(2.0 / 3.0)


def test_score_accuracy_zero_total():
    assert score_accuracy(correct=0, total=0) == pytest.approx(0.0)


def test_score_exact_match():
    assert score_exact_match(matches=5, total=5) == pytest.approx(1.0)
    assert score_exact_match(matches=0, total=5) == pytest.approx(0.0)


def test_score_f1_perfect():
    assert score_f1(correct=3, total=3) == pytest.approx(1.0)


def test_score_f1_zero():
    assert score_f1(correct=0, total=3) == pytest.approx(0.0)


def test_score_f1_partial():
    result = score_f1(correct=2, total=3)
    assert 0.0 < result < 1.0


# --------------------------------------------------------------------------- #
# SuiteWrapper graceful degradation
# --------------------------------------------------------------------------- #
def test_suite_wrapper_math_evaluation_no_model():
    """Without a checkpoint, should return a 0.0 metric with failure provenance."""
    metrics = SuiteWrapper.run_math_evaluation(
        checkpoint_dir="", device="cpu", evaluation_version="math_reasoning:v1")
    assert len(metrics) == 1
    assert metrics[0].value == 0.0
    assert metrics[0].sample_count == 0
    # Must have provenance explaining the 0.0
    assert len(metrics[0].provenance) > 0
    prov_text = " ".join(metrics[0].provenance).lower()
    assert any(w in prov_text for w in ["failure", "unavailable", "not", "error"])


def test_suite_wrapper_coding_evaluation_no_model():
    metrics = SuiteWrapper.run_coding_evaluation(
        checkpoint_dir="", device="cpu", evaluation_version="code_generation:v1")
    assert len(metrics) == 1
    assert metrics[0].value == 0.0
    assert metrics[0].sample_count == 0


def test_suite_wrapper_knowledge_evaluation_no_model():
    metrics = SuiteWrapper.run_knowledge_evaluation(
        checkpoint_dir="", device="cpu", evaluation_version="general_reasoning:v1")
    assert len(metrics) == 1
    assert metrics[0].value == 0.0
    assert metrics[0].sample_count == 0


# --------------------------------------------------------------------------- #
# EvaluationTask
# --------------------------------------------------------------------------- #
def test_evaluation_task_from_dict():
    t = EvaluationTask(
        task_id="test_task", name="Test Task", description="A test",
        metrics=["accuracy"], input_spec={"count": 10},
    )
    d = t.to_dict()
    loaded = EvaluationTask.from_dict(d)
    assert loaded.task_id == "test_task"
    assert loaded.name == "Test Task"
    assert loaded.metrics == ["accuracy"]


def test_scoring_rule_to_from_dict():
    r = ScoringRule(
        metric_name="accuracy",
        method=ScoringMethod.ACCURACY.value,
        higher_is_better=True,
        unit="ratio",
    )
    d = r.to_dict()
    loaded = ScoringRule.from_dict(d)
    assert loaded.metric_name == "accuracy"
    assert loaded.method == ScoringMethod.ACCURACY.value
    assert loaded.higher_is_better is True
