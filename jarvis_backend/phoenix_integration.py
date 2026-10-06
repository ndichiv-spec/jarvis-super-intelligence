"""Arize Phoenix integration for JARVIS AI evaluation and observability.

Extends the existing OpenTelemetry instrumentation with:
- LLM evaluation (hallucination detection, relevance, toxicity)
- Trace collection via the OpenTelemetry bridge
- In-memory evaluation dataset management

Phoenix runs as a local server (phoenix serve) or can connect to a remote
instance. When no Phoenix server is reachable, evaluations run in-process
and results are stored in an in-memory buffer.

Usage:
    from jarvis_backend.phoenix_integration import get_phoenix_client, run_evaluation
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.phoenix_integration")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
_DEFAULT_PHOENIX_PORT = int(os.environ.get("PHOENIX_PORT", "6006"))
_DEFAULT_PHOENIX_HOST = os.environ.get("PHOENIX_HOST", "localhost")


# --------------------------------------------------------------------------- #
# Evaluation criteria
# --------------------------------------------------------------------------- #
EVAL_CRITERIA = {
    "hallucination": {
        "description": "Detect whether the model's response contains "
                       "information not supported by the input/prompt",
        "scale": 2,  # 0=not hallucinated, 1=hallucinated
    },
    "relevance": {
        "description": "Rate how relevant the response is to the user query (1-5)",
        "scale": 5,
    },
    "toxicity": {
        "description": "Detect toxic, harmful, or unsafe content (1-5)",
        "scale": 5,
    },
    "coherence": {
        "description": "Rate how coherent and well-structured the response is (1-5)",
        "scale": 5,
    },
    "faithfulness": {
        "description": "Rate how faithfully the response adheres to the prompt (1-5)",
        "scale": 5,
    },
}


# --------------------------------------------------------------------------- #
# Phoenix evaluator wrapper
# --------------------------------------------------------------------------- #
class PhoenixEvaluator:
    """Wrapper around Phoenix's evaluation harness.

    When the Phoenix package is installed, uses phoenix.eval for real
    evaluations. When not installed (or evaluation model not configured),
    performs a lightweight heuristic-based evaluation.
    """

    def __init__(self):
        self._px = None
        self._eval_model = None
        self._setup()

    def _setup(self):
        """Try to initialize the Phoenix evaluation framework."""
        try:
            import phoenix as px  # type: ignore
            self._px = px
            logger.info("Phoenix initialized (version: %s)", getattr(px, "__version__", "unknown"))

            # Try to configure an evaluation model
            # Phoenix evals can use OpenAI, Anthropic, or any OpenAI-compatible endpoint
            eval_model_name = os.environ.get("PHOENIX_EVAL_MODEL")
            if eval_model_name:
                try:
                    from phoenix.evals import OpenAIModel
                    self._eval_model = OpenAIModel(model=eval_model_name)
                except ImportError:
                    try:
                        from phoenix.evals import LiteLLMModel
                        self._eval_model = LiteLLMModel(model=eval_model_name)
                    except ImportError:
                        logger.warning(
                            "No evaluation model available; using heuristic evals"
                        )
                        self._eval_model = None
        except ImportError:
            logger.warning(
                "phoenix package not installed; using heuristic evaluation only"
            )
        except Exception as e:
            logger.warning("Phoenix setup failed: %s; using heuristic evaluation", e)

    @property
    def available(self) -> bool:
        """True if the full Phoenix framework is available."""
        return self._px is not None

    def evaluate_hallucination(
        self,
        prompt: str,
        response: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """Detect hallucination in a model response.

        Uses Phoenix's built-in hallucination evaluator if available,
        otherwise falls back to a keyword-based heuristic.
        """
        # Try real Phoenix evaluator first
        if self._eval_model is not None:
            try:
                from phoenix.evals import HallucinationEvaluator
                eval_result = HallucinationEvaluator(self._eval_model).evaluate(
                    input=prompt,
                    output=response,
                    context=context or prompt,
                )
                return {
                    "method": "phoenix.hallucination",
                    "score": eval_result.label,
                    "explanation": eval_result.explanation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                logger.warning("Phoenix hallucination eval failed: %s", e)

        # Heuristic fallback
        return self._heuristic_hallucination(prompt, response, context)

    def evaluate_relevance(
        self,
        query: str,
        response: str,
    ) -> Dict[str, Any]:
        """Rate relevance of a response to a query (1-5)."""
        if self._eval_model is not None:
            try:
                from phoenix.evals import RelevanceEvaluator
                eval_result = RelevanceEvaluator(self._eval_model).evaluate(
                    input=query,
                    output=response,
                )
                return {
                    "method": "phoenix.relevance",
                    "score": eval_result.label,
                    "explanation": eval_result.explanation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                logger.warning("Phoenix relevance eval failed: %s", e)

        return self._heuristic_relevance(query, response)

    def evaluate_toxicity(
        self,
        response: str,
    ) -> Dict[str, Any]:
        """Detect toxic content in a response."""
        if self._eval_model is not None:
            try:
                from phoenix.evals import ToxicityEvaluator
                eval_result = ToxicityEvaluator(self._eval_model).evaluate(
                    input="",
                    output=response,
                )
                return {
                    "method": "phoenix.toxicity",
                    "score": eval_result.label,
                    "explanation": eval_result.explanation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                logger.warning("Phoenix toxicity eval failed: %s", e)

        return self._heuristic_toxicity(response)

    def run_comprehensive_evaluation(
        self,
        prompt: str,
        response: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """Run all evaluation criteria and return a combined report."""
        results = {
            "evaluations": {},
            "overall_score": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        eval_functions = {
            "hallucination": self.evaluate_hallucination,
            "relevance": self.evaluate_relevance,
            "toxicity": self.evaluate_toxicity,
            "coherence": self._heuristic_coherence,
            "faithfulness": self._heuristic_faithfulness,
        }

        total_score = 0.0
        for name, func in eval_functions.items():
            try:
                result = func(prompt, response, context) if name in ("hallucination",) else (
                    func(prompt, response) if name == "relevance" else (
                        func(response) if name == "toxicity" else func(prompt, response)
                    )
                )
                results["evaluations"][name] = result
                total_score += result.get("score", 2)  # default neutral score
            except Exception as e:
                results["evaluations"][name] = {
                    "method": "error",
                    "score": 0,
                    "explanation": str(e),
                }
                total_score += 0

        results["overall_score"] = round(total_score / len(eval_functions), 2)
        return results

    # -- Heuristic fallbacks (when Phoenix eval model unavailable) ---------- #
    def _heuristic_hallucination(
        self, prompt: str, response: str, context: str = ""
    ) -> Dict[str, Any]:
        """Simple heuristic: check for uncertainty markers and specificity."""
        uncertainty_markers = [
            "i'm not sure", "i don't know", "i'm uncertain", "possibly",
            "might be", "could be", "perhaps", "i think", "i believe",
        ]
        specificity = len(response.split())
        has_uncertainty = any(m in response.lower() for m in uncertainty_markers)
        # Lower score = less hallucination
        score = 1 if (has_uncertainty and specificity < 20) else 0
        return {
            "method": "heuristic.hallucination",
            "score": score,
            "explanation": (
                "Response contains uncertainty markers and is short"
                if score == 1 else
                "No strong hallucination indicators detected"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _heuristic_relevance(self, query: str, response: str) -> Dict[str, Any]:
        """Simple keyword overlap heuristic for relevance scoring (1-5)."""
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())
        if not query_words:
            return {
                "method": "heuristic.relevance",
                "score": 3,
                "explanation": "Empty query; neutral score",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        overlap = query_words & response_words
        ratio = len(overlap) / len(query_words) if query_words else 0
        score = max(1, min(5, int(ratio * 5) + 1))
        return {
            "method": "heuristic.relevance",
            "score": score,
            "explanation": f"Keyword overlap ratio: {ratio:.2f} ({len(overlap)}/{len(query_words)})",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _heuristic_toxicity(self, response: str) -> Dict[str, Any]:
        """Simple heuristic toxicity check."""
        toxic_patterns = [
            "hate", "kill", "murder", "violence", "racist", "discriminate",
            "harmful", "dangerous", "violent", "threat",
        ]
        response_lower = response.lower()
        matches = [p for p in toxic_patterns if p in response_lower]
        score = 1 if not matches else min(5, 2 + len(matches))
        return {
            "method": "heuristic.toxicity",
            "score": score,
            "explanation": (
                "No toxic content detected"
                if not matches else
                f"Potential toxic patterns: {', '.join(matches)}"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _heuristic_coherence(self, prompt: str, response: str) -> Dict[str, Any]:
        """Heuristic coherence: checks sentence structure and length."""
        sentences = [s.strip() for s in response.split(".") if s.strip()]
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
        score = max(1, min(5, int(avg_len / 5) + 2)) if avg_len else 2
        return {
            "method": "heuristic.coherence",
            "score": score,
            "explanation": f"Avg sentence length: {avg_len:.1f} words, {len(sentences)} sentences",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _heuristic_faithfulness(self, prompt: str, response: str) -> Dict[str, Any]:
        """Heuristic faithfulness: checks if response stays on topic."""
        query_words = set(prompt.lower().split())
        response_words = set(response.lower().split())
        overlap = query_words & response_words
        ratio = len(overlap) / len(query_words) if query_words else 0
        score = max(1, min(5, int(ratio * 4) + 1)) if ratio else 1
        return {
            "method": "heuristic.faithfulness",
            "score": score,
            "explanation": f"Topic adherence: {ratio:.2f} keyword overlap",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# --------------------------------------------------------------------------- #
# In-memory evaluation store
# --------------------------------------------------------------------------- #
_evaluation_store: List[Dict[str, Any]] = []
_MAX_EVALUATIONS = 1000


def store_evaluation(evaluation: Dict[str, Any]) -> None:
    """Store an evaluation result in the in-memory buffer."""
    _evaluation_store.append(evaluation)
    if len(_evaluation_store) > _MAX_EVALUATIONS:
        del _evaluation_store[:len(_evaluation_store) - _MAX_EVALUATIONS]


def get_recent_evaluations(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent evaluation results."""
    return list(_evaluation_store[-limit:])


def clear_evaluations() -> int:
    """Clear the evaluation store. Returns count of cleared items."""
    global _evaluation_store
    count = len(_evaluation_store)
    _evaluation_store = []
    return count


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_evaluator: Optional[PhoenixEvaluator] = None


def get_phoenix_client() -> PhoenixEvaluator:
    """Return the singleton PhoenixEvaluator instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = PhoenixEvaluator()
    return _evaluator


def run_evaluation(
    prompt: str,
    response: str,
    context: str = "",
    criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run Phoenix evaluations on a model response.

    Args:
        prompt: The user prompt/input.
        response: The model's response.
        context: Optional retrieval context (for hallucination checks).
        criteria: List of criteria to evaluate. Defaults to all.

    Returns:
        Evaluation result dict with per-criterion scores.
    """
    evaluator = get_phoenix_client()
    if criteria:
        # Filter to requested criteria only
        all_results = evaluator.run_comprehensive_evaluation(prompt, response, context)
        filtered = {
            "evaluations": {k: v for k, v in all_results["evaluations"].items() if k in criteria},
            "overall_score": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        scores = [v.get("score", 0) for v in filtered["evaluations"].values()]
        filtered["overall_score"] = round(sum(scores) / len(scores), 2) if scores else 0.0
        result = filtered
    else:
        result = evaluator.run_comprehensive_evaluation(prompt, response, context)

    result["inputs"] = {
        "prompt": prompt[:2000],
        "response": response[:2000],
        "context": context[:2000] if context else "",
    }
    store_evaluation(result)
    return result


def get_phoenix_status() -> Dict[str, Any]:
    """Check Phoenix integration status."""
    evaluator = get_phoenix_client()
    return {
        "phoenix_available": evaluator.available,
        "evaluation_model_configured": evaluator._eval_model is not None,
        "evaluations_stored": len(_evaluation_store),
        "criteria_available": list(EVAL_CRITERIA.keys()),
    }


__all__ = [
    "PhoenixEvaluator",
    "get_phoenix_client",
    "run_evaluation",
    "get_phoenix_status",
    "get_recent_evaluations",
    "clear_evaluations",
    "EVAL_CRITERIA",
]
