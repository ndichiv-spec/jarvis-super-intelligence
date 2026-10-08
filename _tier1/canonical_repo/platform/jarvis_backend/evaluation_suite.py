"""Phase 11 — Versioned Evaluation Suites for the JARVIS Laboratory.

Evaluation suites are *versioned* collections of evaluation tasks with
scoring rules.  They wrap existing evaluation infrastructure (the
``evaluate_experiment_b.py`` functions) rather than duplicating it.

Each suite defines:
  - suite_id, version
  - tasks (the evaluation questions/problems)
  - scoring_rules (how to score each task)
  - required_capabilities (what compute capabilities the model must have)
  - required_models (what model types this suite applies to)
  - resource_requirements (compute needed to run this suite)

The SuiteWrapper delegates to real evaluation code — it NEVER fabricates
scores.  If the underlying evaluation is unavailable (e.g. torch not
installed, checkpoint not found), the suite reports the limitation truthfully.
"""
from __future__ import annotations

import importlib
import logging
import math
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.experiment import Metric

logger = logging.getLogger("jarvis_backend.evaluation_suite")


# ---------------------------------------------------------------------------
# Scorer types
# ---------------------------------------------------------------------------
class ScoringMethod(str, Enum):
    """How a task is scored."""

    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    F1 = "f1"
    ACCURACY = "accuracy"
    EXACT = "exact"
    PERPLEXITY = "perplexity"
    PASS_AT_1 = "pass_at_1"


@dataclass
class ScoringRule:
    """A rule for scoring a task within a suite."""

    metric_name: str           # e.g. "math_accuracy"
    method: str                # ScoringMethod value
    higher_is_better: bool = True
    unit: str = "ratio"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "method": self.method,
            "higher_is_better": self.higher_is_better,
            "unit": self.unit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoringRule":
        return cls(
            metric_name=data["metric_name"],
            method=data.get("method", ScoringMethod.ACCURACY.value),
            higher_is_better=data.get("higher_is_better", True),
            unit=data.get("unit", "ratio"),
            description=data.get("description", ""),
        )


@dataclass
class EvaluationTask:
    """A single task within an evaluation suite."""

    task_id: str
    name: str
    description: str
    metrics: list[str]        # metric names produced by this task
    input_spec: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "metrics": list(self.metrics),
            "input_spec": dict(self.input_spec),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationTask":
        return cls(
            task_id=data["task_id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            metrics=list(data.get("metrics", [])),
            input_spec=dict(data.get("input_spec", {})),
        )


# ---------------------------------------------------------------------------
# Evaluation Suite
# ---------------------------------------------------------------------------
@dataclass
class EvaluationSuite:
    """A versioned collection of evaluation tasks with scoring rules.

    Persistence via ``get_store("evaluation_suites")``.
    """

    suite_id: str
    name: str
    version: str
    tasks: list[dict[str, Any]] = field(default_factory=list)     # EvaluationTask.to_dict list
    scoring_rules: list[dict[str, Any]] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    required_models: list[str] = field(default_factory=list)
    resource_requirements: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: str = field(default_factory=now_iso)

    @property
    def versioned_id(self) -> str:
        """Suite ID with version, e.g. 'math_reasoning:v1'."""
        return f"{self.suite_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "name": self.name,
            "version": self.version,
            "tasks": list(self.tasks),
            "scoring_rules": list(self.scoring_rules),
            "required_capabilities": list(self.required_capabilities),
            "required_models": list(self.required_models),
            "resource_requirements": dict(self.resource_requirements),
            "description": self.description,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationSuite":
        return cls(
            suite_id=data["suite_id"],
            name=data.get("name", ""),
            version=data.get("version", "1"),
            tasks=list(data.get("tasks", [])),
            scoring_rules=list(data.get("scoring_rules", [])),
            required_capabilities=list(data.get("required_capabilities", [])),
            required_models=list(data.get("required_models", [])),
            resource_requirements=dict(data.get("resource_requirements", {})),
            description=data.get("description", ""),
            created_at=data.get("created_at", now_iso()),
        )

    # -- Persistence --
    def save(self) -> None:
        store = get_store("evaluation_suites")
        suites = store.load()
        suites[self.versioned_id] = self.to_dict()
        store.save()

    @staticmethod
    def load(versioned_id: str) -> Optional["EvaluationSuite"]:
        store = get_store("evaluation_suites")
        suites = store.load()
        raw = suites.get(versioned_id)
        if raw is None:
            return None
        return EvaluationSuite.from_dict(raw)

    @staticmethod
    def load_by_id(suite_id: str) -> Optional["EvaluationSuite"]:
        """Load the latest version of a suite by suite_id."""
        store = get_store("evaluation_suites")
        suites = store.load()
        matches = [
            EvaluationSuite.from_dict(raw)
            for raw in suites.values()
            if raw.get("suite_id") == suite_id
        ]
        if not matches:
            return None
        # Return highest version
        return max(matches, key=lambda s: s.version)

    @staticmethod
    def list_all() -> list["EvaluationSuite"]:
        store = get_store("evaluation_suites")
        suites = store.load()
        return [EvaluationSuite.from_dict(raw) for raw in suites.values()]

    @staticmethod
    def list_by_id() -> dict[str, list["EvaluationSuite"]]:
        """Group suites by suite_id (multiple versions)."""
        by_id: dict[str, list[EvaluationSuite]] = {}
        for s in EvaluationSuite.list_all():
            by_id.setdefault(s.suite_id, []).append(s)
        return by_id


# ---------------------------------------------------------------------------
# Suite Registry
# ---------------------------------------------------------------------------
class EvaluationSuiteRegistry:
    """Registry for standard evaluation suites."""

    _suites: dict[str, EvaluationSuite] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, suite: EvaluationSuite) -> None:
        cls._suites[suite.versioned_id] = suite
        # Also persist to store
        suite.save()

    @classmethod
    def get(cls, versioned_id: str) -> Optional[EvaluationSuite]:
        """Get a suite by versioned id (e.g. 'math_reasoning:v1')."""
        # Check in-memory first
        if versioned_id in cls._suites:
            return cls._suites[versioned_id]
        # Check persistent store
        suite = EvaluationSuite.load(versioned_id)
        if suite is not None:
            cls._suites[versioned_id] = suite
            return suite
        return None

    @classmethod
    def get_by_id(cls, suite_id: str) -> Optional[EvaluationSuite]:
        """Get the latest version of a suite by suite_id."""
        if suite_id in cls._suites:
            # Return highest version from cache
            versions = {k: v for k, v in cls._suites.items() if k.split(":")[0] == suite_id.replace(":v", "").split(":")[0]}
            if versions:
                return max(versions.values(), key=lambda s: s.version)
        return EvaluationSuite.load_by_id(suite_id)

    @classmethod
    def list_all(cls) -> list[EvaluationSuite]:
        return list(cls._suites.values()) + [
            s for s in EvaluationSuite.list_all() if s.versioned_id not in cls._suites
        ]

    @classmethod
    def initialize(cls) -> None:
        """Register all standard suites."""
        if cls._initialized:
            return
        for suite in _standard_suites():
            cls.register(suite)
        cls._initialized = True


# ---------------------------------------------------------------------------
# Standard Suites
# ---------------------------------------------------------------------------
_standard_suite_defs = {
    "math_reasoning": {
        "name": "Mathematical Reasoning",
        "tasks": [
            {
                "task_id": "math_arithmetic",
                "name": "Arithmetic",
                "description": "Basic arithmetic problems",
                "metrics": ["accuracy"],
                "input_spec": {"problem_types": ["arithmetic"], "count": 15},
            },
            {
                "task_id": "math_algebra",
                "name": "Algebra",
                "description": "Basic algebra problems",
                "metrics": ["accuracy"],
                "input_spec": {"problem_types": ["algebra"], "count": 15},
            },
        ],
        "scoring_rules": [
            {"metric_name": "math_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Mathematical reasoning evaluation suite covering arithmetic and algebra.",
    },
    "code_generation": {
        "name": "Code Generation",
        "tasks": [
            {
                "task_id": "code_python",
                "name": "Python Function Generation",
                "description": "Generate Python functions from natural language descriptions",
                "metrics": ["pass_at_1"],
                "input_spec": {"language": "python", "count": 5},
            },
        ],
        "scoring_rules": [
            {"metric_name": "code_pass_at_1", "method": "pass_at_1", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["code-generation", "text-generation"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Code generation evaluation suite for Python function writing.",
    },
    "code_repair": {
        "name": "Code Repair",
        "tasks": [
            {
                "task_id": "code_repair_python",
                "name": "Python Bug Repair",
                "description": "Fix bugs in Python code",
                "metrics": ["pass_at_1"],
                "input_spec": {"language": "python", "count": 10},
            },
        ],
        "scoring_rules": [
            {"metric_name": "code_repair_pass_at_1", "method": "pass_at_1", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["code-generation", "text-generation"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Code repair evaluation suite for fixing bugs in Python code.",
    },
    "general_reasoning": {
        "name": "General Reasoning",
        "tasks": [
            {
                "task_id": "reasoning_deduction",
                "name": "Deductive Reasoning",
                "description": "Deductive logic problems",
                "metrics": ["accuracy"],
                "input_spec": {"count": 8},
            },
            {
                "task_id": "reasoning_causal",
                "name": "Causal Reasoning",
                "description": "Causal inference problems",
                "metrics": ["accuracy"],
                "input_spec": {"count": 8},
            },
        ],
        "scoring_rules": [
            {"metric_name": "reasoning_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "General reasoning evaluation suite covering deductive and causal reasoning.",
    },
    "document_analysis": {
        "name": "Document Analysis",
        "tasks": [
            {
                "task_id": "doc_qa",
                "name": "Document QA",
                "description": "Question answering over documents",
                "metrics": ["f1", "exact_match"],
                "input_spec": {"count": 100},
            },
        ],
        "scoring_rules": [
            {"metric_name": "doc_f1", "method": "f1", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "doc_exact_match", "method": "exact_match", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "embed", "rerank"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Document analysis evaluation suite for question answering over documents.",
    },
    "data_analysis": {
        "name": "Data Analysis",
        "tasks": [
            {
                "task_id": "data_interpretation",
                "name": "Data Interpretation",
                "description": "Interpret data tables and charts",
                "metrics": ["accuracy"],
                "input_spec": {"count": 50},
            },
        ],
        "scoring_rules": [
            {"metric_name": "data_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Data analysis evaluation suite for data interpretation tasks.",
    },
    "tool_use": {
        "name": "Tool Use",
        "tasks": [
            {
                "task_id": "tool_selection",
                "name": "Tool Selection",
                "description": "Select and use tools to solve problems",
                "metrics": ["accuracy"],
                "input_spec": {"count": 50},
            },
        ],
        "scoring_rules": [
            {"metric_name": "tool_use_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation", "compute.tool_use"],
        "required_models": ["text-generation", "agentic"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Tool use evaluation suite for agentic tool selection and execution.",
    },
    "rag": {
        "name": "RAG",
        "tasks": [
            {
                "task_id": "rag_qa",
                "name": "RAG Question Answering",
                "description": "Question answering with retrieved context",
                "metrics": ["f1", "exact_match", "accuracy"],
                "input_spec": {"count": 100, "retrieval_k": 5},
            },
        ],
        "scoring_rules": [
            {"metric_name": "rag_f1", "method": "f1", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "rag_exact_match", "method": "exact_match", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "rag_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation", "compute.embedding"],
        "required_models": ["text-generation", "embed", "rerank"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "RAG evaluation suite for retrieval-augmented generation question answering.",
    },
    "geography": {
        "name": "Geography Knowledge",
        "tasks": [
            {
                "task_id": "geo_facts",
                "name": "Geography Facts",
                "description": "Geographical knowledge questions",
                "metrics": ["accuracy"],
                "input_spec": {"count": 50},
            },
        ],
        "scoring_rules": [
            {"metric_name": "geography_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Geography knowledge evaluation suite.",
    },
    "security": {
        "name": "Security Reasoning",
        "tasks": [
            {
                "task_id": "sec_vulns",
                "name": "Vulnerability Detection",
                "description": "Identify security vulnerabilities in code",
                "metrics": ["accuracy", "f1"],
                "input_spec": {"count": 50},
            },
        ],
        "scoring_rules": [
            {"metric_name": "security_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "security_f1", "method": "f1", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Security reasoning evaluation suite for vulnerability detection.",
    },
    "instruction_following": {
        "name": "Instruction Following",
        "tasks": [
            {
                "task_id": "inst_follow",
                "name": "Instruction Following",
                "description": "Follow multi-step instructions with constraints",
                "metrics": ["accuracy", "f1"],
                "input_spec": {"count": 50},
            },
        ],
        "scoring_rules": [
            {"metric_name": "instruction_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "instruction_f1", "method": "f1", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Instruction following evaluation suite for multi-step instruction compliance.",
    },
    "generation_quality": {
        "name": "Generation Quality",
        "tasks": [
            {
                "task_id": "gen_8prompt",
                "name": "8-Prompt Generation Quality",
                "description": "Generation quality on 8 fixed prompts",
                "metrics": ["accuracy", "prompts_passed"],
                "input_spec": {"count": 8},
            },
        ],
        "scoring_rules": [
            {"metric_name": "generation_accuracy", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
            {"metric_name": "generation_prompts_passed", "method": "accuracy", "higher_is_better": True, "unit": "ratio"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Generation quality evaluation suite on fixed prompts.",
    },
    "perplexity": {
        "name": "Perplexity",
        "tasks": [
            {
                "task_id": "perplexity_eval",
                "name": "Language Model Perplexity",
                "description": "Per-token perplexity on validation data",
                "metrics": ["val_loss", "val_ppl"],
                "input_spec": {"max_len": 1024},
            },
        ],
        "scoring_rules": [
            {"metric_name": "val_loss", "method": "perplexity", "higher_is_better": False, "unit": "loss"},
            {"metric_name": "val_ppl", "method": "perplexity", "higher_is_better": False, "unit": "perplexity"},
        ],
        "required_capabilities": ["compute.evaluation"],
        "required_models": ["text-generation", "causal-lm"],
        "resource_requirements": {"min_vram_gb": 0, "offline_ok": True},
        "description": "Perplexity evaluation suite for language model per-token loss.",
    },
}


def _standard_suites() -> list[EvaluationSuite]:
    """Build standard evaluation suites (version 1)."""
    suites = []
    for suite_id, spec in _standard_suite_defs.items():
        suite = EvaluationSuite(
            suite_id=suite_id,
            name=spec["name"],
            version="1",
            description=spec["description"],
            tasks=[t if isinstance(t, dict) else t.to_dict() for t in [
                EvaluationTask(
                    task_id=td["task_id"],
                    name=td["name"],
                    description=td["description"],
                    metrics=td["metrics"],
                    input_spec=td.get("input_spec", {}),
                ) for td in spec["tasks"]
            ]],
            scoring_rules=[sr for sr in spec["scoring_rules"]],
            required_capabilities=spec["required_capabilities"],
            required_models=spec["required_models"],
            resource_requirements=spec["resource_requirements"],
        )
        suites.append(suite)
    return suites


def initialize_standard_suites() -> list[EvaluationSuite]:
    """Register all standard suites. Call once at startup."""
    EvaluationSuiteRegistry.initialize()
    return EvaluationSuiteRegistry.list_all()


# ---------------------------------------------------------------------------
# SuiteWrapper — delegates to existing evaluation code
# ---------------------------------------------------------------------------
class SuiteWrapper:
    """Wraps existing evaluation functions as typed Metric producers.

    The wrapper delegates to real evaluation code (evaluate_experiment_b.py).
    It NEVER fabricates metrics.  If the underlying evaluation is unavailable
    (missing torch, missing checkpoint, etc.), it returns a Metric with
    value=0.0 and provenance noting the failure — truthfully.
    """

    @staticmethod
    def _try_import_eval_module():
        """Attempt to import the evaluate_experiment_b module.

        Returns the module or None if unavailable.
        """
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if root not in __import__("sys").path:
                __import__("sys").path.insert(0, root)
            mod = importlib.import_module("evaluate_experiment_b")
            return mod
        except Exception as exc:
            logger.debug("evaluate_experiment_b not available: %s", exc)
            return None

    @staticmethod
    def run_math_evaluation(
        checkpoint_dir: str,
        device: str = "cpu",
        val_file: Optional[str] = None,
        evaluation_version: str = "math_reasoning:v1",
    ) -> list[Metric]:
        """Run math reasoning evaluation, returning typed Metrics.

        If evaluation cannot run (no torch, no checkpoint), returns a single
        Metric with value=0.0 and provenance noting the failure.
        Never fabricates.
        """
        mod = SuiteWrapper._try_import_eval_module()
        if mod is None:
            return [Metric(
                name="math_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_unavailable:module_not_found"],
            )]
        try:
            model, tokenizer, config = mod.load_checkpoint(checkpoint_dir, device)
            result = mod.evaluate_math(model, tokenizer, device)
            return [Metric(
                name="math_accuracy",
                value=float(result.get("accuracy", 0.0)),
                unit="ratio",
                higher_is_better=True,
                sample_count=int(result.get("total", 0)),
                evaluation_version=evaluation_version,
                provenance=[f"checkpoint:{checkpoint_dir}", f"device:{device}"],
            )]
        except Exception as exc:
            logger.debug("Math evaluation failed: %s", exc)
            return [Metric(
                name="math_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_failed:{type(exc).__name__}"],
            )]

    @staticmethod
    def run_coding_evaluation(
        checkpoint_dir: str,
        device: str = "cpu",
        evaluation_version: str = "code_generation:v1",
    ) -> list[Metric]:
        """Run coding evaluation, returning typed Metrics."""
        mod = SuiteWrapper._try_import_eval_module()
        if mod is None:
            return [Metric(
                name="code_pass_at_1",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=["evaluation_unavailable:module_not_found"],
            )]
        try:
            model, tokenizer, config = mod.load_checkpoint(checkpoint_dir, device)
            result = mod.evaluate_coding(model, tokenizer, device)
            return [Metric(
                name="code_pass_at_1",
                value=float(result.get("accuracy", 0.0)),
                unit="ratio",
                higher_is_better=True,
                sample_count=int(result.get("total", 0)),
                evaluation_version=evaluation_version,
                provenance=[f"checkpoint:{checkpoint_dir}", f"device:{device}"],
            )]
        except Exception as exc:
            return [Metric(
                name="code_pass_at_1",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_failed:{type(exc).__name__}"],
            )]

    @staticmethod
    def run_knowledge_evaluation(
        checkpoint_dir: str,
        device: str = "cpu",
        evaluation_version: str = "general_reasoning:v1",
    ) -> list[Metric]:
        """Run knowledge evaluation, returning typed Metrics."""
        mod = SuiteWrapper._try_import_eval_module()
        if mod is None:
            return [Metric(
                name="reasoning_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=["evaluation_unavailable:module_not_found"],
            )]
        try:
            model, tokenizer, config = mod.load_checkpoint(checkpoint_dir, device)
            result = mod.evaluate_knowledge(model, tokenizer, device)
            return [Metric(
                name="reasoning_accuracy",
                value=float(result.get("accuracy", 0.0)),
                unit="ratio",
                higher_is_better=True,
                sample_count=int(result.get("total", 0)),
                evaluation_version=evaluation_version,
                provenance=[f"checkpoint:{checkpoint_dir}", f"device:{device}"],
            )]
        except Exception as exc:
            return [Metric(
                name="reasoning_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_failed:{type(exc).__name__}"],
            )]

    @staticmethod
    def run_logic_evaluation(
        checkpoint_dir: str,
        device: str = "cpu",
        evaluation_version: str = "general_reasoning:v1",
    ) -> list[Metric]:
        """Run logic evaluation, returning typed Metrics."""
        mod = SuiteWrapper._try_import_eval_module()
        if mod is None:
            return [Metric(
                name="reasoning_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=["evaluation_unavailable:module_not_found"],
            )]
        try:
            model, tokenizer, config = mod.load_checkpoint(checkpoint_dir, device)
            result = mod.evaluate_logic(model, tokenizer, device)
            return [Metric(
                name="reasoning_accuracy",
                value=float(result.get("accuracy", 0.0)),
                unit="ratio",
                higher_is_better=True,
                sample_count=int(result.get("total", 0)),
                evaluation_version=evaluation_version,
                provenance=[f"checkpoint:{checkpoint_dir}", f"device:{device}"],
            )]
        except Exception as exc:
            return [Metric(
                name="reasoning_accuracy",
                value=0.0,
                unit="ratio",
                higher_is_better=True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_failed:{type(exc).__name__}"],
            )]

    @staticmethod
    def run_full_checkpoint_evaluation(
        checkpoint_dir: str,
        val_file: str,
        work_dir: str,
        tag: Optional[str] = None,
        evaluation_version: str = "full:v1",
    ) -> list[Metric]:
        """Run full checkpoint evaluation across all dimensions.

        Delegates to evaluate_experiment_b.evaluate_checkpoint().
        Returns a list of Metric objects for each dimension.
        """
        mod = SuiteWrapper._try_import_eval_module()
        if mod is None:
            # Return metrics noting unavailability — never fabricate values
            dims = ["math_accuracy", "logic_accuracy", "coding_accuracy",
                    "knowledge_accuracy", "generation_accuracy", "val_ppl"]
            return [Metric(
                name=d,
                value=0.0,
                unit="ratio" if "ppl" not in d else "perplexity",
                higher_is_better=False if "ppl" in d else True,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=["evaluation_unavailable:module_not_found"],
            ) for d in dims]
        try:
            results = mod.evaluate_checkpoint(checkpoint_dir, val_file, work_dir, tag=tag)
            metrics = []
            # Map result keys to metric names
            dim_map = {
                "perplexity": ("val_ppl", False, "perplexity"),
                "math": ("math_accuracy", True, "ratio"),
                "logic": ("logic_accuracy", True, "ratio"),
                "coding": ("coding_accuracy", True, "ratio"),
                "knowledge": ("knowledge_accuracy", True, "ratio"),
            }
            for key, (name, higher_better, unit) in dim_map.items():
                dim = results.get(key, {})
                if isinstance(dim, dict):
                    value = dim.get("accuracy") or dim.get("val_ppl")
                    count = dim.get("total", dim.get("correct", 0))
                    metrics.append(Metric(
                        name=name,
                        value=float(value) if value is not None else 0.0,
                        unit=unit,
                        higher_is_better=higher_better,
                        sample_count=int(count or 0),
                        evaluation_version=evaluation_version,
                        provenance=[f"checkpoint:{checkpoint_dir}", f"tag:{tag or results.get('tag', '')}"],
                    ))
            # Generation
            gen = results.get("generation", {})
            if isinstance(gen, dict):
                passed = gen.get("prompts_passed", 0)
                total = gen.get("prompts_total", 0)
                acc = passed / total if total > 0 else 0.0
                metrics.append(Metric(
                    name="generation_accuracy",
                    value=acc,
                    unit="ratio",
                    higher_is_better=True,
                    sample_count=total,
                    evaluation_version=evaluation_version,
                    provenance=[f"checkpoint:{checkpoint_dir}"],
                ))
            return metrics
        except Exception as exc:
            logger.warning("Full checkpoint evaluation failed: %s", exc)
            return [Metric(
                name="val_ppl",
                value=0.0,
                unit="perplexity",
                higher_is_better=False,
                sample_count=0,
                evaluation_version=evaluation_version,
                provenance=[f"evaluation_failed:{type(exc).__name__}"],
            )]


# ---------------------------------------------------------------------------
# Standalone metric scoring utilities (no model required)
# ---------------------------------------------------------------------------
def score_accuracy(correct: int, total: int) -> float:
    """Compute accuracy = correct / total. Never fabricates."""
    if total <= 0:
        return 0.0
    return correct / total


def score_f1(correct: int, total: int, false_positives: int = 0) -> float:
    """Compute F1 from counts. Never fabricates."""
    tp = correct
    fp = false_positives
    fn = total - correct
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def score_exact_match(matches: int, total: int) -> float:
    """Compute exact match score. Never fabricates."""
    if total <= 0:
        return 0.0
    return matches / total


__all__ = [
    "ScoringMethod",
    "ScoringRule",
    "EvaluationTask",
    "EvaluationSuite",
    "EvaluationSuiteRegistry",
    "SuiteWrapper",
    "initialize_standard_suites",
    "score_accuracy",
    "score_f1",
    "score_exact_match",
]
