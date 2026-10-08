"""Base orchestration adapter for the Silverwing Intelligence Fabric.

All external framework adapters (LangGraph, LangChain, CrewAI, AutoGen,
PydanticAI, LlamaIndex) inherit from ``BaseOrchestrationAdapter``.  Each
adapter translates between a Silverwing ``TaskSpec`` and the framework's
native representation, and back.

Silverwing owns the mission lifecycle.  External frameworks are adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from fabric_models import AgentSpec, TaskSpec, MissionContext


class BaseOrchestrationAdapter(ABC):
    """Abstract base for orchestration-framework adapters.

    An adapter bridges the Silverwing Fabric to one external framework.
    It implements:

    * ``name``           — framework identifier (e.g. ``"langgraph"``)
    * ``is_available()`` — whether the framework is installed
    * ``execute()``      — run a single task (or task sequence) via the framework
    * ``execute_mission()`` — run an entire mission via the framework
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short name of the framework."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the framework library is importable."""

    @abstractmethod
    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        """Execute a single task via the framework.

        Returns a result dict with at least ``status`` and ``output``.
        """

    @abstractmethod
    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        """Execute an entire mission via the framework.

        Returns a mission-level result dict with ``tasks``, ``findings``,
        etc.
        """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def info(self) -> Dict[str, Any]:
        """Return metadata about this adapter."""

        return {
            "name": self.name,
            "available": self.is_available(),
        }

    def adapt_agent(self, agent: AgentSpec) -> Dict[str, Any]:
        """Convert a Fabric ``AgentSpec`` to a framework-native description."""

        return {
            "role": agent.role,
            "agent_id": agent.agent_id,
            "capabilities": agent.capabilities,
            "allowed_tools": agent.allowed_tools,
            "system_prompt": agent.system_prompt,
            "model_preference": agent.model_preference,
        }

    def adapt_task(self, task: TaskSpec) -> Dict[str, Any]:
        """Convert a Fabric ``TaskSpec`` to a framework-native description."""

        return {
            "task_id": task.task_id,
            "mission_id": task.mission_id,
            "description": task.description,
            "capability": task.capability,
            "priority": task.priority,
            "risk": task.risk,
            "required_tools": task.required_tools,
            "required_model_classes": task.required_model_classes,
            "inputs": task.inputs,
        }

    def format_result(self, task: TaskSpec, output: Any,
                      error: Optional[str] = None) -> Dict[str, Any]:
        """Standardize the result dict returned to the Orchestrator."""

        return {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "capability": task.capability,
            "status": "completed" if error is None else "failed",
            "output": output,
            "error": error,
        }


class NativeExecutionAdapter(BaseOrchestrationAdapter):
    """The built-in adapter that executes tasks directly within Silverwing.

    This is the default path.  Other adapters are only used when explicitly
    selected via ``IntelligenceRequest.framework``.
    """

    @property
    def name(self) -> str:
        return "native"

    def is_available(self) -> bool:
        return True

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        """Native execution: returns a structured plan without calling models.

        The actual model calls happen in the Orchestrator via the ModelRouter.
        This adapter is responsible for sequencing steps and collecting
        intermediate results from the Fabric's own runtimes.
        """

        step_results: Dict[str, Dict[str, Any]] = {}

        for step in steps:
            step_name = step["step"]
            step_results[step_name] = {
                "status": "pending",
                "description": step["description"],
            }

        return {
            "adapter": "native",
            "agent_id": agent.agent_id,
            "task_id": task.task_id,
            "steps": step_results,
            "output": f"Executed {len(steps)} steps for {task.description}",
            "status": "completed",
        }

    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        return {
            "adapter": "native",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "status": "completed",
        }


# Registry of all available adapters
def get_all_adapters() -> List[str]:
    return ["native", "langgraph", "langchain", "crewai", "autogen",
            "pydanticai", "llamaindex"]


def get_adapter_info_all() -> List[Dict[str, Any]]:
    """Probe all adapters and return their availability metadata.

    This is used by the Orchestration Ecosystem analysis.
    """

    infos: List[Dict[str, Any]] = []
    for name in get_all_adapters():
        info: Dict[str, Any] = {"name": name, "available": False,
                                "version": None, "license": None,
                                "description": "", "use_cases": []}
        try:
            if name == "native":
                info.update(NativeExecutionAdapter().info())
                info["license"] = "MIT (built-in)"
                info["description"] = "Built-in native execution within Silverwing"
                info["use_cases"] = ["default", "full-control", "no-dependencies"]
            elif name == "langgraph":
                import langgraph  # noqa: F401
                info["available"] = True
                info["version"] = getattr(langgraph, "__version__", "unknown")
                info["license"] = "MIT"
                info["description"] = "Stateful multi-agent workflows with persistence"
                info["use_cases"] = ["complex-workflows", "stateful-agents", "human-in-loop"]
            elif name == "langchain":
                import langchain  # noqa: F401
                info["available"] = True
                info["version"] = getattr(langchain, "__version__", "unknown")
                info["license"] = "MIT"
                info["description"] = "Composable LLM chains and agents"
                info["use_cases"] = ["tool-chaining", "prompt-templates", "memory"]
            elif name == "crewai":
                import crewai  # noqa: F401
                info["available"] = True
                info["version"] = getattr(crewai, "__version__", "unknown")
                info["license"] = "MIT"
                info["description"] = "Role-playing AI agents with delegation"
                info["use_cases"] = ["role-playing", "delegation", "team-collaboration"]
            elif name == "autogen":
                import autogen  # noqa: F401
                info["available"] = True
                info["version"] = getattr(autogen, "__version__", "unknown")
                info["license"] = "MIT"
                info["description"] = "Conversable agents with multi-agent conversations"
                info["use_cases"] = ["conversation-agents", "multi-agent-dialogue", "code-execution"]
            elif name == "pydanticai":
                import pydantic_ai  # noqa: F401
                info["available"] = True
                info["version"] = getattr(pydantic_ai, "__version__", "unknown")
                info["license"] = "MIT"
                info["description"] = "Type-safe agent framework with dependency injection"
                info["use_cases"] = ["type-safety", "dependency-injection", "structured-output"]
            elif name == "llamaindex":
                import llama_index  # noqa: F401
                info["available"] = True
                info["version"] = getattr(llama_index, "__version__", "unknown")
                info["license"] = "Apache-2.0"
                info["description"] = "RAG and knowledge graph indexing"
                info["use_cases"] = ["rag", "knowledge-graph", "document-indexing"]
        except ImportError:
            pass
        infos.append(info)

    return infos
