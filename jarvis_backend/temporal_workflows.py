"""Temporal.io workflow integration for JARVIS durable execution.

Defines Temporal Workflows and Activities for the three bio-growth operations
that benefit from durable, retryable, and observable execution:

1. **Research Ingestion Workflow** — periodically ingests RSS feeds, arXiv
   queries, and web URLs with checkpointing between each source.
2. **Bio-Learner Consolidation Workflow** — runs the SM-2 spaced repetition
   consolidation cycle, with retryable study sessions.
3. **Science Computation Workflow** — executes mathematical operations with
   automatic retry and intermediate result persistence.

When no Temporal server is running (default: localhost:7223), these workflows
fall back to a synchronous in-process executor so the existing backend keeps
working unchanged.  This is an UPGRADE of the existing backend — Temporal
is an additional orchestration layer, not a new backend.

Usage:
    from jarvis_backend.temporal_workflows import (
        run_research_workflow, run_consolidation_workflow,
        run_science_workflow, get_temporal_client, temporal_available
    )
"""
from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.temporal_workflows")

# --------------------------------------------------------------------------- #
# Activity functions (plain async — work both in Temporal workers and in-process)
# --------------------------------------------------------------------------- #
async def ingest_feed_activity(feed_url: str, source_type: str) -> Dict[str, Any]:
    """Activity: ingest a single RSS/Atom feed into the research cortex."""
    from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
    cortex = AutonomousResearchCortex()
    cortex.initialize()
    result = await cortex.ingest_feed(feed_url)
    return {"feed_url": feed_url, "source_type": source_type, "result": result}


async def search_arxiv_activity(query: str, max_results: int) -> Dict[str, Any]:
    """Activity: search arXiv for papers."""
    from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
    cortex = AutonomousResearchCortex()
    items = await cortex.search_arxiv(query, max_results)
    return {"query": query, "results": [i.to_dict() for i in items], "count": len(items)}


async def ingest_url_activity(url: str, title: str, source_type: str) -> Dict[str, Any]:
    """Activity: crawl and ingest a URL."""
    from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
    cortex = AutonomousResearchCortex()
    item = await cortex.ingest_url(url)
    return {"url": url, "item": item.to_dict() if item else None}


async def study_concept_activity(domain: str, concept: str) -> Dict[str, Any]:
    """Activity: study a concept in a learning domain (SM-2)."""
    from jarvis_backend.capabilities.bio_learner import BioLearnerCapability
    from jarvis_backend.capability import ExecutionContext
    cap = BioLearnerCapability()
    ctx = ExecutionContext(user_id="system", session_id="temporal")
    result = await cap.execute(
        {"action": "study_concept", "domain": domain, "concept": concept},
        ctx,
    )
    return {"domain": domain, "concept": concept, "result": result.data}


async def consolidate_activity() -> Dict[str, Any]:
    """Activity: run bio-learner consolidation."""
    from jarvis_backend.capabilities.bio_learner import BioLearnerCapability
    from jarvis_backend.capability import ExecutionContext
    cap = BioLearnerCapability()
    ctx = ExecutionContext(user_id="system", session_id="temporal")
    result = await cap.execute({"action": "consolidate"}, ctx)
    return {"consolidation": result.data}


async def solve_math_activity(operation: str, problem: str, variable: str = "x") -> Dict[str, Any]:
    """Activity: solve a math problem via the Science Engine."""
    from jarvis_backend.capabilities.science import ScienceCapability
    cap = ScienceCapability()
    result = await cap.execute({
        "operation": operation,
        "problem": problem,
        "variable": variable,
    })
    return {"operation": operation, "result": result.data}


_ALL_ACTIVITIES = {
    "ingest_feed_activity": ingest_feed_activity,
    "search_arxiv_activity": search_arxiv_activity,
    "ingest_url_activity": ingest_url_activity,
    "study_concept_activity": study_concept_activity,
    "consolidate_activity": consolidate_activity,
    "solve_math_activity": solve_math_activity,
}


# --------------------------------------------------------------------------- #
# Temporal workflow classes (only defined when temporalio is installed)
# --------------------------------------------------------------------------- #
_WorkflowClasses: Dict[str, type] = {}

try:
    from temporalio import workflow as _wf
    from temporalio import activity as _act

    # Decorate activities for Temporal
    _temporal_activities = {
        name: _act.defn(fn) for name, fn in _ALL_ACTIVITIES.items()
    }

    @_wf.defn
    class ResearchIngestionWorkflow:
        """Durable workflow: ingest research from multiple feeds and URLs."""

        @_wf.run
        async def run(
            self,
            feed_urls: List[str],
            arxiv_queries: List[str],
            web_urls: List[str],
            max_results_per_source: int = 10,
        ) -> Dict[str, Any]:
            _wf.logger.info("Starting ResearchIngestionWorkflow")
            results: Dict[str, Any] = {
                "feeds_ingested": 0,
                "arxiv_results": 0,
                "urls_ingested": 0,
                "per_source": [],
            }
            for feed_url in feed_urls:
                try:
                    r = await _wf.execute_activity(
                        _temporal_activities["ingest_feed_activity"],
                        feed_url, "rss",
                        start_to_close_timeout=timedelta(minutes=5),
                    )
                    results["feeds_ingested"] += r.get("result", {}).get("items_ingested", 0)
                    results["per_source"].append(r)
                except Exception as e:
                    _wf.logger.warning("Feed failed %s: %s", feed_url, e)
                    results["per_source"].append({"feed_url": feed_url, "error": str(e)})
            for query in arxiv_queries:
                try:
                    r = await _wf.execute_activity(
                        _temporal_activities["search_arxiv_activity"],
                        query, max_results_per_source,
                        start_to_close_timeout=timedelta(minutes=5),
                    )
                    results["arxiv_results"] += r.get("count", 0)
                    results["per_source"].append(r)
                except Exception as e:
                    _wf.logger.warning("ArXiv failed %s: %s", query, e)
                    results["per_source"].append({"query": query, "error": str(e)})
            for url in web_urls:
                try:
                    title = url.split("/")[-1] if "/" in url else url
                    r = await _wf.execute_activity(
                        _temporal_activities["ingest_url_activity"],
                        url, title, "web_crawl",
                        start_to_close_timeout=timedelta(minutes=5),
                    )
                    results["urls_ingested"] += 1 if r.get("item") else 0
                    results["per_source"].append(r)
                except Exception as e:
                    _wf.logger.warning("URL failed %s: %s", url, e)
                    results["per_source"].append({"url": url, "error": str(e)})
            _wf.logger.info("ResearchIngestionWorkflow complete")
            return results

    @_wf.defn
    class BioLearnerConsolidationWorkflow:
        """Durable workflow: run bio-learner study + consolidation cycle."""

        @_wf.run
        async def run(
            self,
            study_pairs: List[Dict[str, str]],
            run_consolidation: bool = True,
        ) -> Dict[str, Any]:
            _wf.logger.info("Starting BioLearnerConsolidationWorkflow")
            results: Dict[str, Any] = {"studied": 0, "consolidated": False, "study_results": []}
            for pair in study_pairs:
                domain = pair.get("domain", "mathematics")
                concept = pair.get("concept", "arithmetic")
                try:
                    r = await _wf.execute_activity(
                        _temporal_activities["study_concept_activity"],
                        domain, concept,
                        start_to_close_timeout=timedelta(minutes=2),
                    )
                    results["studied"] += 1
                    results["study_results"].append(r)
                except Exception as e:
                    _wf.logger.warning("Study failed %s/%s: %s", domain, concept, e)
                    results["study_results"].append({"domain": domain, "concept": concept, "error": str(e)})
            if run_consolidation:
                try:
                    r = await _wf.execute_activity(
                        _temporal_activities["consolidate_activity"],
                        start_to_close_timeout=timedelta(minutes=3),
                    )
                    results["consolidated"] = True
                    results["consolidation_result"] = r
                except Exception as e:
                    _wf.logger.warning("Consolidation failed: %s", e)
                    results["consolidation_error"] = str(e)
            return results

    @_wf.defn
    class ScienceComputationWorkflow:
        """Durable workflow: solve a batch of mathematical operations."""

        @_wf.run
        async def run(
            self,
            problems: List[Dict[str, Any]],
        ) -> Dict[str, Any]:
            _wf.logger.info("Starting ScienceComputationWorkflow")
            results: Dict[str, Any] = {"solved": 0, "results": []}
            for prob in problems:
                operation = prob.get("operation", "")
                problem = prob.get("problem", "")
                variable = prob.get("variable", "x")
                try:
                    r = await _wf.execute_activity(
                        _temporal_activities["solve_math_activity"],
                        operation, problem, variable,
                        start_to_close_timeout=timedelta(minutes=2),
                    )
                    results["solved"] += 1
                    results["results"].append(r)
                except Exception as e:
                    _wf.logger.warning("Math failed %s: %s", problem, e)
                    results["results"].append({"operation": operation, "problem": problem, "error": str(e)})
            return results

    _WorkflowClasses["ResearchIngestionWorkflow"] = ResearchIngestionWorkflow
    _WorkflowClasses["BioLearnerConsolidationWorkflow"] = BioLearnerConsolidationWorkflow
    _WorkflowClasses["ScienceComputationWorkflow"] = ScienceComputationWorkflow

except ImportError:
    pass  # temporalio not installed — in-process fallback only


# --------------------------------------------------------------------------- #
# In-process workflow equivalents (no Temporal runtime required)
# --------------------------------------------------------------------------- #
async def _run_research_in_process(
    feed_urls: List[str],
    arxiv_queries: List[str],
    web_urls: List[str],
    max_results_per_source: int = 10,
) -> Dict[str, Any]:
    """In-process equivalent of ResearchIngestionWorkflow."""
    logger.info("Starting ResearchIngestionWorkflow (in-process)")
    results: Dict[str, Any] = {"feeds_ingested": 0, "arxiv_results": 0, "urls_ingested": 0, "per_source": []}

    for feed_url in feed_urls:
        try:
            r = await ingest_feed_activity(feed_url, "rss")
            results["feeds_ingested"] += r.get("result", {}).get("items_ingested", 0)
            results["per_source"].append(r)
            logger.info("Ingested feed: %s", feed_url)
        except Exception as e:
            logger.warning("Feed ingestion failed for %s: %s", feed_url, e)
            results["per_source"].append({"feed_url": feed_url, "error": str(e)})

    for query in arxiv_queries:
        try:
            r = await search_arxiv_activity(query, max_results_per_source)
            results["arxiv_results"] += r.get("count", 0)
            results["per_source"].append(r)
        except Exception as e:
            logger.warning("ArXiv search failed for %s: %s", query, e)
            results["per_source"].append({"query": query, "error": str(e)})

    for url in web_urls:
        try:
            title = url.split("/")[-1] if "/" in url else url
            r = await ingest_url_activity(url, title, "web_crawl")
            results["urls_ingested"] += 1 if r.get("item") else 0
            results["per_source"].append(r)
        except Exception as e:
            logger.warning("URL ingestion failed for %s: %s", url, e)
            results["per_source"].append({"url": url, "error": str(e)})

    logger.info("ResearchIngestionWorkflow complete (in-process)")
    return results


async def _run_consolidation_in_process(
    study_pairs: List[Dict[str, str]],
    run_consolidation: bool = True,
) -> Dict[str, Any]:
    """In-Process equivalent of BioLearnerConsolidationWorkflow."""
    logger.info("Starting BioLearnerConsolidationWorkflow (in-process)")
    results: Dict[str, Any] = {"studied": 0, "consolidated": False, "study_results": []}

    for pair in study_pairs:
        domain = pair.get("domain", "mathematics")
        concept = pair.get("concept", "arithmetic")
        try:
            r = await study_concept_activity(domain, concept)
            results["studied"] += 1
            results["study_results"].append(r)
        except Exception as e:
            logger.warning("Study failed for %s/%s: %s", domain, concept, e)
            results["study_results"].append({"domain": domain, "concept": concept, "error": str(e)})

    if run_consolidation:
        try:
            r = await consolidate_activity()
            results["consolidated"] = True
            results["consolidation_result"] = r
        except Exception as e:
            logger.warning("Consolidation failed: %s", e)
            results["consolidation_error"] = str(e)

    return results


async def _run_science_in_process(
    problems: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """In-Process equivalent of ScienceComputationWorkflow."""
    logger.info("Starting ScienceComputationWorkflow (in-process)")
    results: Dict[str, Any] = {"solved": 0, "results": []}

    for prob in problems:
        operation = prob.get("operation", "")
        problem = prob.get("problem", "")
        variable = prob.get("variable", "x")
        try:
            r = await solve_math_activity(operation, problem, variable)
            results["solved"] += 1
            results["results"].append(r)
        except Exception as e:
            logger.warning("Math solve failed for %s: %s", problem, e)
            results["results"].append({"operation": operation, "problem": problem, "error": str(e)})

    return results


# --------------------------------------------------------------------------- #
# Client wrapper (with in-process fallback)
# --------------------------------------------------------------------------- #
_TEMPORAL_CLIENT: Optional[Any] = None
_TEMPORAL_AVAILABLE: bool = False


def _check_temporal() -> bool:
    """Check if temporalio is importable."""
    global _TEMPORAL_AVAILABLE
    if not _TEMPORAL_AVAILABLE:
        try:
            import temporalio  # noqa: F401
            _TEMPORAL_AVAILABLE = True
        except ImportError:
            _TEMPORAL_AVAILABLE = False
    return _TEMPORAL_AVAILABLE


async def get_temporal_client() -> Optional[Any]:
    """Get or create a Temporal client.

    Returns None if no Temporal server is reachable (graceful degradation).
    """
    global _TEMPORAL_CLIENT
    if _TEMPORAL_CLIENT is not None:
        return _TEMPORAL_CLIENT

    if not _check_temporal() or not _WorkflowClasses:
        return None

    host = os.environ.get("TEMPORAL_HOST", "localhost:7223")
    try:
        from temporalio import client as temporal_client
        _TEMPORAL_CLIENT = await temporal_client.Client.connect(
            host,
            connection_timeout=timedelta(seconds=5),
        )
        logger.info("Connected to Temporal server at %s", host)
        return _TEMPORAL_CLIENT
    except Exception as e:
        logger.info("Temporal server not available at %s: %s; using in-process fallback", host, e)
        _TEMPORAL_CLIENT = None
        return None


async def run_workflow(
    workflow_cls_name: str,
    workflow_id: str,
    task_queue: str,
    *args: Any,
) -> Dict[str, Any]:
    """Run a Temporal workflow by name.

    If no Temporal server is available, falls back to direct in-process
    execution of the equivalent in-process function.
    """
    temporal_client = await get_temporal_client()

    if temporal_client is not None:
        # Real Temporal execution — look up the workflow class
        workflow_cls = _WorkflowClasses.get(workflow_cls_name)
        if workflow_cls is None:
            raise ValueError(f"Unknown workflow: {workflow_cls_name}")
        handle = await temporal_client.start_workflow(
            workflow_cls.run,
            *args,
            id=workflow_id,
            task_queue=task_queue,
        )
        result = await handle.result()
        return {"execution": "temporal", "workflow_id": workflow_id, "result": result}
    else:
        # In-process fallback
        fallback_map = {
            "ResearchIngestionWorkflow": _run_research_in_process,
            "BioLearnerConsolidationWorkflow": _run_consolidation_in_process,
            "ScienceComputationWorkflow": _run_science_in_process,
        }
        if workflow_cls_name not in fallback_map:
            raise ValueError(f"Unknown workflow: {workflow_cls_name}")
        result = await fallback_map[workflow_cls_name](*args)
        return {"execution": "in_process", "workflow_id": workflow_id, "result": result}


# --------------------------------------------------------------------------- #
# Convenience functions for JARVIS capabilities
# --------------------------------------------------------------------------- #
async def run_research_workflow(
    feed_urls: List[str],
    arxiv_queries: List[str],
    web_urls: List[str],
    max_results: int = 10,
) -> Dict[str, Any]:
    """Run the research ingestion workflow."""
    return await run_workflow(
        "ResearchIngestionWorkflow",
        f"research-ingestion-{int(time.time())}",
        "jarvis-research",
        feed_urls,
        arxiv_queries,
        web_urls,
        max_results,
    )


async def run_consolidation_workflow(
    study_pairs: List[Dict[str, str]],
    run_consolidation: bool = True,
) -> Dict[str, Any]:
    """Run the bio-learner consolidation workflow."""
    return await run_workflow(
        "BioLearnerConsolidationWorkflow",
        f"bio-consolidation-{int(time.time())}",
        "jarvis-bio",
        study_pairs,
        run_consolidation,
    )


async def run_science_workflow(
    problems: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run the science computation workflow."""
    return await run_workflow(
        "ScienceComputationWorkflow",
        f"science-computation-{int(time.time())}",
        "jarvis-science",
        problems,
    )


def temporal_available() -> bool:
    """Check if temporalio is installed (server availability checked separately)."""
    return _check_temporal()


def get_temporal_status() -> Dict[str, Any]:
    """Check Temporal integration status."""
    installed = _check_temporal()
    host = os.environ.get("TEMPORAL_HOST", "localhost:7223")
    return {
        "temporalio_installed": installed,
        "server_host": host,
        "server_reachable": _TEMPORAL_CLIENT is not None,
        "workflows": [
            "ResearchIngestionWorkflow",
            "BioLearnerConsolidationWorkflow",
            "ScienceComputationWorkflow",
        ],
        "activities": list(_ALL_ACTIVITIES.keys()),
    }


__all__ = [
    "run_research_workflow",
    "run_consolidation_workflow",
    "run_science_workflow",
    "get_temporal_client",
    "get_temporal_status",
    "temporal_available",
    # Activities
    "ingest_feed_activity",
    "search_arxiv_activity",
    "ingest_url_activity",
    "study_concept_activity",
    "consolidate_activity",
    "solve_math_activity",
]
