"""Silverwing Training Advisor: Gemini-powered, evidence-based ML research advisor.

Public API
----------
* ``AdvisorConfig``           - secure env-based configuration
* ``TrainingAdvisor``         - the advisor orchestrator
* ``AdvisorResult``           - validated structured recommendation output
* ``TrainingMetricsSnapshot`` - a labelled metric point (with provenance)
* ``Provenance``              - OBSERVED / DERIVED / ESTIMATED / UNKNOWN
* ``Recommendation`` / ``RecommendationAction`` / ``RiskLevel`` / ``AdvisorStatus``
* ``GeminiProvider`` / ``LocalProvider`` / ``TrainingAdvisorProvider``

Gemini is an *advisor* only: it never mutates the optimizer, scheduler,
checkpoints, training loop, datasets, or any backend state.  Any
recommendation that could lead to such a mutation is marked
``authorization_required=True`` and only takes effect after explicit human
approval via ``/api/training/advisor/approve``.
"""
from .config import AdvisorConfig
from .schemas import (
    AdvisorResult, AdvisorStatus, Anomaly, AnomalySeverity, MetricValue,
    Provenance, ProvenanceRecord, Recommendation, RecommendationAction,
    RiskLevel, TrainingMetricsSnapshot,
)
from .metrics import MetricsStore
from .analysis import run_all_detectors, classify_status, build_analysis_text
from .lr_advisor import synthesize, recommend_for
from .prompts import PROMPT_VERSION, system_prompt, build_user_prompt, gemini_response_schema
from .providers import (
    TrainingAdvisorProvider, GeminiProvider, LocalProvider,
)
from .provenance import ProvenanceRecorder
from .advisor import TrainingAdvisor

__all__ = [
    "AdvisorConfig", "TrainingAdvisor", "AdvisorResult", "AdvisorStatus",
    "Anomaly", "AnomalySeverity", "MetricValue", "Provenance",
    "ProvenanceRecord", "Recommendation", "RecommendationAction", "RiskLevel",
    "TrainingMetricsSnapshot", "MetricsStore", "run_all_detectors",
    "classify_status", "build_analysis_text", "synthesize", "recommend_for",
    "PROMPT_VERSION", "system_prompt", "build_user_prompt", "gemini_response_schema",
    "TrainingAdvisorProvider", "GeminiProvider", "LocalProvider", "ProvenanceRecorder",
]

__version__ = "1.0.0"
