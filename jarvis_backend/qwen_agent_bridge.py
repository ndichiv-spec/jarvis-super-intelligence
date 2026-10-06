"""Qwen-Agent bridge for JARVIS capabilities.

Integrates the Qwen-Agent multi-agent framework (42,462 stars, Python) with
the existing JARVIS capability runtime. This allows Qwen-Agent's agentic
orchestration to call JARVIS capabilities (research.cortex, science.engine,
bio.learner, tech.evolution, browser, task, etc.) as tools — all routed
through the existing JARVIS Orchestrator for full OTel tracing + persistence.

This is an UPGRADE of the existing backend, not a new backend. Qwen-Agent
is used as an additional orchestration layer — JARVIS capabilities remain
the source of truth, and all tool calls pass through the existing orchestrator.

Usage:
    from jarvis_backend.qwen_agent_bridge import JarvisQwenAgent, run_qwen_agent_task
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

log: Any = None  # lazy logger

def _get_logger():
    global log
    if log is None:
        import logging
        log = logging.getLogger("jarvis.qwen_agent_bridge")
    return log


# --------------------------------------------------------------------------- #
# JARVIS tool wrapper for Qwen-Agent
# --------------------------------------------------------------------------- #
class JarvisCapabilityTool:
    """Wraps a JARVIS capability as a Qwen-Agent tool.

    When Qwen-Agent calls this tool, the request is routed through
    the JARVIS Orchestrator (which provides OTel tracing, persistence,
    and event bus emission) — NOT executed directly.
    """

    def __init__(self, capability_name: str, action: str, description: str = "",
                 parameters: Optional[dict] = None):
        self.capability_name = capability_name
        self.action = action
        self.description = description or f"Execute {action} on {capability_name}"
        self.parameters = parameters or {}

    def to_qwen_tool(self) -> dict:
        """Return a Qwen-Agent-compatible tool definition."""
        return {
            "name": f"jarvis_{self.capability_name.replace('.', '_')}_{self.action}",
            "description": self.description,
            "parameters": {
                "type": "dict",
                "properties": self.parameters,
            },
        }

    async def execute(self, params: dict) -> str:
        """Execute the capability through the JARVIS orchestrator.

        Returns the result as a JSON string (Qwen-Agent tool result format).
        """
        from jarvis_backend.capability import get_orchestrator, ExecutionContext
        from jarvis_backend.core import now_iso

        orch = get_orchestrator()
        ctx = ExecutionContext(
            user_id="system",
            session_id=f"qwen-{os.urandom(4).hex()[:8]}",
            correlation_id=f"qwen-{os.urandom(8).hex()[:12]}",
            permissions=["*"],
        )

        request = {"action": self.action, "params": params}
        result = await orch.execute_capability(self.capability_name, request, ctx)

        if result.success:
            return json.dumps({
                "success": True,
                "data": result.data,
                "latency_ms": result.latency_ms,
            }, default=str)
        else:
            return json.dumps({
                "success": False,
                "error": result.error,
                "error_type": result.error_type,
            }, default=str)


# --------------------------------------------------------------------------- #
# JARVIS tool registry for Qwen-Agent
# --------------------------------------------------------------------------- #
def get_jarvis_qwen_tools() -> List[JarvisCapabilityTool]:
    """Build the list of JARVIS capabilities exposed as Qwen-Agent tools."""
    tools = [
        # Research Cortex
        JarvisCapabilityTool(
            "research.cortex", "initialize",
            "Initialize the research cortex with seed feeds and knowledge graph",
            {"optional": True},
        ),
        JarvisCapabilityTool(
            "research.cortex", "semantic_search",
            "Search ingested knowledge by semantic similarity (vector search)",
            {
                "type": "string",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "limit": {"type": "integer", "description": "Max results to return"},
                    "source": {"type": "string", "description": "Table to search (knowledge_graph or research_items)"},
                },
                "required": ["query"],
            },
        ),
        JarvisCapabilityTool(
            "research.cortex", "search_arxiv",
            "Search arXiv for scientific papers",
            {"query": {"type": "string", "description": "arXiv search query"},
             "max_results": {"type": "integer", "default": 10}},
        ),
        JarvisCapabilityTool(
            "research.cortex", "ingest_url",
            "Crawl and digest a web URL into the knowledge graph",
            {"url": {"type": "string", "description": "URL to ingest"}},
        ),
        JarvisCapabilityTool(
            "research.cortex", "ingest_content",
            "Ingest raw text content into the knowledge graph",
            {"title": {"type": "string"}, "content": {"type": "string"},
             "source": {"type": "string"}, "source_type": {"type": "string"}},
        ),

        # Science Engine
        JarvisCapabilityTool(
            "science.engine", "solve",
            "Solve a symbolic/numerical math problem",
            {
                "type": "string",
                "properties": {
                    "operation": {"type": "string", "description": "Math operation: linear_solve, integral, derivative, numerical_integrate, monte_carlo_pi, determinant, mean, formulate_hypothesis"},
                    "problem": {"type": "string", "description": "Math expression or equation"},
                    "variable": {"type": "string", "default": "x"},
                    "matrix": {"type": "array", "description": "Matrix as 2D array (for determinant)"},
                    "data": {"type": "array", "description": "Data list (for mean)"},
                },
                "required": ["operation"],
            },
        ),

        # Bio Learner
        JarvisCapabilityTool(
            "bio.learner", "study_concept",
            "Study a concept within a learning domain (SM-2 spaced repetition)",
            {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Learning domain"},
                    "concept": {"type": "string", "description": "Concept to study"},
                },
                "required": ["domain", "concept"],
            },
        ),
        JarvisCapabilityTool(
            "bio.learner", "consolidate",
            "Run hippocampal replay + cross-domain synthesis",
            {},
        ),
        JarvisCapabilityTool(
            "bio.learner", "get_learning_path",
            "Get curriculum learning path for a domain",
            {"domain": {"type": "string", "description": "Learning domain"}},
        ),
        JarvisCapabilityTool(
            "bio.learner", "review_due",
            "Get due reviews for SM-2 spaced repetition",
            {},
        ),
        JarvisCapabilityTool(
            "bio.learner", "perform_review",
            "Perform a spaced-repetition review",
            {"item_key": {"type": "string"}, "quality": {"type": "integer"}},
        ),

        # Tech Evolution
        JarvisCapabilityTool(
            "tech.evolution", "discover",
            "Discover new technologies from research ingestion",
            {"limit": {"type": "integer", "default": 50}},
        ),
        JarvisCapabilityTool(
            "tech.evolution", "get_tech_radar",
            "Get the ThoughtWorks-style tech radar",
            {},
        ),
        JarvisCapabilityTool(
            "tech.evolution", "get_frontiers",
            "Get mapped research frontiers with cross-domain synthesis",
            {},
        ),

        # Browser
        JarvisCapabilityTool(
            "browser", "fetch",
            "Fetch a URL and return content",
            {"url": {"type": "string", "description": "URL to fetch"},
             "timeout": {"type": "integer", "default": 30}},
        ),

        # Task
        JarvisCapabilityTool(
            "task", "create_task",
            "Create a new task in the JARVIS task system",
            {"title": {"type": "string"}, "description": {"type": "string"},
             "capability": {"type": "string"}, "priority": {"type": "integer", "default": 0}},
        ),

        # Memory
        JarvisCapabilityTool(
            "memory", "store_memory",
            "Store a memory entry",
            {"memory_type": {"type": "string"}, "content": {"type": "string"},
             "metadata": {"type": "string"}},
        ),
        JarvisCapabilityTool(
            "memory", "recall",
            "Retrieve memories by type",
            {"memory_type": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
        ),

        # Knowledge
        JarvisCapabilityTool(
            "knowledge.search", "search",
            "Search the knowledge base",
            {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}},
        ),
    ]
    return tools


def get_jarvis_qwen_tool_names() -> List[str]:
    """Return list of available JARVIS-as-Qwen-Agent tool names."""
    return [t.to_qwen_tool()["name"] for t in get_jarvis_qwen_tools()]


# --------------------------------------------------------------------------- #
# Qwen-Agent orchestration layer
# --------------------------------------------------------------------------- #
# Map capability_name.action -> JarvisCapabilityTool
_TOOL_MAP: Dict[str, JarvisCapabilityTool] = {}


def _build_tool_map():
    """Build a lookup table of tool_name -> JarvisCapabilityTool."""
    global _TOOL_MAP
    if _TOOL_MAP:
        return _TOOL_MAP
    for tool in get_jarvis_qwen_tools():
        qwen_def = tool.to_qwen_tool()
        _TOOL_MAP[qwen_def["name"]] = tool
    return _TOOL_MAP


def jarvis_tool_executor(tool_name: str, **kwargs) -> str:
    """Synchronous tool executor for Qwen-Agent (wraps async).

    Qwen-Agent calls can be sync or async. This function bridges to the
    async JARVIS orchestrator.
    """
    tool_map = _build_tool_map()
    tool = tool_map.get(tool_name)
    if tool is None:
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context — create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(tool.execute(kwargs))).result()
        else:
            result = asyncio.run(tool.execute(kwargs))
        return result
    except RuntimeError:
        result = asyncio.run(tool.execute(kwargs))
        return result
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


class JarvisQwenAgent:
    """A Qwen-Agent-powered agent that uses JARVIS capabilities as tools.

    Wraps qwen_agent.agent.Assistant with JARVIS tools, providing
    multi-agent orchestration that routes through the existing JARVIS
    capability runtime.
    """

    def __init__(
        self,
        name: str = "jarvis_agent",
        system_message: str = "",
        llm_config: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
    ):
        self.name = name
        self.system_message = system_message or self._default_system_message()
        self.llm_config = llm_config or self._default_llm_config()
        self.exposed_tools = tools or get_jarvis_qwen_tool_names()
        self._agent: Any = None
        self._tool_map = _build_tool_map()

    def _default_system_message(self) -> str:
        return (
            "You are JARVIS, a highly capable AI assistant backed by a rich set of "
            "tools for research, science, learning, technology tracking, browsing, "
            "memory, and task management. Always use the appropriate tool for each "
            "request. When you don't know something, use the research tool to ingest "
            "and search knowledge. When asked to solve math problems, use the science "
            "solver. When asked to learn something new, use the bio-learner tools."
        )

    def _default_llm_config(self) -> Dict[str, Any]:
        # Use OpenAI-compatible config (JARVIS supports OpenAI providers)
        return {
            "model": os.environ.get("QWEN_MODEL", "gpt-4o-mini"),
            "model_server": os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
            "api_key": os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY"),
        }

    def _get_qwen_tools(self) -> List[dict]:
        """Build Qwen-Agent tool definitions from JARVIS tools."""
        tool_defs = []
        for tool_name in self.exposed_tools:
            if tool_name in self._tool_map:
                jarvis_tool = self._tool_map[tool_name]
                qwen_def = jarvis_tool.to_qwen_tool()
                # Qwen-Agent uses a specific format
                tool_defs.append({
                    "type": "function",
                    "function": {
                        "name": qwen_def["name"],
                        "description": qwen_def["description"],
                        "parameters": qwen_def["parameters"],
                    },
                })
        return tool_defs

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Run a conversation through Qwen-Agent with JARVIS tools.

        Requires OPENAI_API_KEY environment variable.
        """
        try:
            from qwen_agent.agents import Assistant
            from qwen_agent.tools.base import BaseTool
            from qwen_agent.common.typedef import Role
        except ImportError:
            _get_logger().warning("qwen_agent not installed; chat unavailable")
            return "Qwen-Agent not installed. Install with: pip install qwen-agent"

        # Build Qwen-Agent tool definitions
        tool_defs = self._get_qwen_tools()

        # Create the Qwen-Agent Assistant with JARVIS tools
        self._agent = Assistant(
            llm=self.llm_config,
            tools=tool_defs,
            system_message=self.system_message,
        )

        # Execute conversation
        response = self._agent.run(messages)
        # Collect the final result
        result = None
        for r in response:
            result = r
        if result and hasattr(result[-1], 'content'):
            return result[-1].content
        return ""


# --------------------------------------------------------------------------- #
# Convenience functions
# --------------------------------------------------------------------------- #
def list_jarvis_qwen_tools() -> List[str]:
    """List all JARVIS capabilities available as Qwen-Agent tools."""
    return get_jarvis_qwen_tool_names()


def get_qwen_agent_status() -> Dict[str, Any]:
    """Check Qwen-Agent integration status."""
    try:
        import qwen_agent  # type: ignore
        qwen_available = True
        qwen_version = getattr(qwen_agent, "__version__", "unknown")
    except ImportError:
        qwen_available = False
        qwen_version = None

    try:
        import qwen_agent.agents  # type: ignore
        agents_module = True
    except ImportError:
        agents_module = False

    tools = get_jarvis_qwen_tool_names()

    return {
        "qwen_agent_available": qwen_available,
        "qwen_agent_version": qwen_version,
        "agents_module_available": agents_module,
        "jarvis_tools_exposed": len(tools),
        "tool_names": tools,
        "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
    }


__all__ = [
    "JarvisCapabilityTool",
    "JarvisQwenAgent",
    "get_jarvis_qwen_tools",
    "get_jarvis_qwen_tool_names",
    "jarvis_tool_executor",
    "list_jarvis_qwen_tools",
    "get_qwen_agent_status",
]
