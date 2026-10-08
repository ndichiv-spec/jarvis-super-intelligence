"""Task Planner for the Silverwing Intelligence Fabric.

The ``TaskPlanner`` decomposes a ``TaskSpec`` into fine-grained,
executable steps.  Each step records its purpose and the data it needs
to read or produce.  Steps are the unit of execution that the
``AgentScheduler`` ultimately dispatches.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fabric_models import TaskSpec


# Canonical step templates keyed by task capability
_STEP_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "research": [
        {"step": "decompose_query", "description": "Break the objective into sub-queries",
         "tool": "builtin", "produces": ["sub_queries"]},
        {"step": "search_sources", "description": "Search research connectors for evidence",
         "tool": "multi", "produces": ["sources"]},
        {"step": "rank_and_dedup", "description": "Rank and deduplicate sources",
         "tool": "builtin", "produces": ["ranked_sources"]},
        {"step": "fetch_content", "description": "Fetch full content from top sources",
         "tool": "multi", "produces": ["full_texts"]},
    ],
    "analysis": [
        {"step": "load_evidence", "description": "Load evidence from prior research steps",
         "tool": "memory_read", "produces": ["evidence"]},
        {"step": "identify_patterns", "description": "Identify patterns and relationships in evidence",
         "tool": "model", "produces": ["patterns"]},
        {"step": "evaluate_conflicts", "description": "Evaluate conflicting information",
         "tool": "model", "produces": ["conflicts"]},
    ],
    "coding": [
        {"step": "plan_implementation", "description": "Plan code structure",
         "tool": "model", "produces": ["plan"]},
        {"step": "generate_code", "description": "Generate code for the planned structure",
         "tool": "model", "produces": ["code"]},
        {"step": "execute_validation", "description": "Execute code and validate output",
         "tool": "python", "produces": ["execution_result"]},
    ],
    "verification": [
        {"step": "gather_claims", "description": "Gather claims from prior analysis",
         "tool": "memory_read", "produces": ["claims"]},
        {"step": "fetch_evidence", "description": "Fetch evidence for each claim",
         "tool": "multi", "produces": ["verification_sources"]},
        {"step": "cross_verify", "description": "Cross-verify claims against evidence",
         "tool": "model", "produces": ["verification_results"]},
        {"step": "resolve_contradictions", "description": "Resolve any contradictions found",
         "tool": "model", "produces": ["resolved_claims"]},
    ],
    "synthesis": [
        {"step": "compile_findings", "description": "Compile all findings into a report",
         "tool": "builtin", "produces": ["findings"]},
        {"step": "generate_conclusions", "description": "Generate final conclusions",
         "tool": "model", "produces": ["conclusions"]},
    ],
    "memory_management": [
        {"step": "consolidate_memory", "description": "Consolidate findings into semantic memory",
         "tool": "memory_write", "produces": ["memories"]},
        {"step": "update_knowledge_graph", "description": "Update knowledge graph with findings",
         "tool": "knowledge_graph", "produces": ["graph_updates"]},
    ],
}


class TaskPlanner:
    """Decomposes ``TaskSpec`` objects into ordered execution steps."""

    def __init__(self) -> None:
        self._templates = _STEP_TEMPLATES

    def decompose(self, task: TaskSpec) -> List[Dict[str, Any]]:
        """Return an ordered list of step dicts for the given task.

        Each step dict has:
            - ``step``: short identifier
            - ``description``: human-readable description
            - ``tool``: the tool category needed (builtin, model, python, etc.)
            - ``produces``: keys that will be available to downstream steps
        """

        capability = task.capability
        template = self._templates.get(capability)

        if template is None:
            # Generic fallback: just an execution step
            return [{
                "step": "execute_generic",
                "description": f"Execute {task.description}",
                "tool": "model",
                "produces": ["result"],
            }]

        # Return a shallow copy so callers can't mutate the template
        return [dict(s) for s in template]

    def estimate_steps(self, capability: str) -> int:
        """Return the number of steps a task of this capability typically has."""

        template = self._templates.get(capability)
        if template is None:
            return 1
        return len(template)

    def merge_subtask_results(self, steps: List[Dict[str, Any]],
                              step_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Merge per-step results into a single task-level result dict."""

        merged: Dict[str, Any] = {}
        for step in steps:
            step_name = step["step"]
            if step_name in step_results:
                merged.update(step_results[step_name])
        return merged
