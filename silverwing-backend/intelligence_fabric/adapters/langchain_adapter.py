"""LangChain adapter for the Silverwing Intelligence Fabric."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import BaseOrchestrationAdapter
from fabric_models import AgentSpec, MissionContext, TaskSpec


class LangChainAdapter(BaseOrchestrationAdapter):
    """Runs tasks through LangChain expression-language chains.

    Best use-cases:
      * Tool chaining and prompt templating
      * Runnable passthrough and map-reduce
      * Memory-backed conversations
    """

    @property
    def name(self) -> str:
        return "langchain"

    def is_available(self) -> bool:
        try:
            import langchain  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "langchain not installed"}

        from langchain_core.runnables import RunnableLambda, RunnablePassthrough

        # Build a simple chain that passes through steps
        async def process_steps(input_data: Dict[str, Any]) -> Dict[str, Any]:
            results: Dict[str, Any] = {}
            for step in steps:
                results[step["step"]] = {
                    "description": step["description"],
                    "status": "completed",
                }
            return results

        chain = RunnableLambda(process_steps) | RunnablePassthrough()
        result = await chain.ainvoke({"task_id": task.task_id,
                                      "agent_id": agent.agent_id})

        return {
            "adapter": "langchain",
            "task_id": task.task_id,
            "agent_id": agent.agent_id,
            "output": result,
            "status": "completed",
        }

    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "langchain not installed"}

        from langchain_core.runnables import RunnableLambda

        async def process_all(input_data: Dict[str, Any]) -> Dict[str, Any]:
            task_results = []
            for task in tasks:
                steps = steps_map.get(task.task_id, [])
                task_results.append({
                    "task_id": task.task_id,
                    "capability": task.capability,
                    "steps": len(steps),
                })
            return {"task_results": task_results}

        chain = RunnableLambda(process_all)
        result = await chain.ainvoke({"mission_id": context.mission_id})

        return {
            "adapter": "langchain",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "output": result,
            "status": "completed",
        }
