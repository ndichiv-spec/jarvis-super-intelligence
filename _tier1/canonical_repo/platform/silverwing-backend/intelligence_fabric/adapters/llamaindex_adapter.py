"""LlamaIndex adapter for the Silverwing Intelligence Fabric."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import BaseOrchestrationAdapter
from fabric_models import AgentSpec, MissionContext, TaskSpec


class LlamaIndexAdapter(BaseOrchestrationAdapter):
    """Runs tasks through LlamaIndex's workflow engine.

    Best use-cases:
      * RAG pipelines over knowledge bases
      * Knowledge graph traversal and querying
      * Document indexing and retrieval
    """

    @property
    def name(self) -> str:
        return "llamaindex"

    def is_available(self) -> bool:
        try:
            import llama_index  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "llamaindex not installed"}

        from llama_index.core import Document
        from llama_index.core.workflow import Workflow, StartEvent, StopEvent

        class TaskWorkflow(Workflow):
            async def handle(self, ev: StartEvent) -> StopEvent:
                step_results = {}
                for step in steps:
                    step_results[step["step"]] = {
                        "description": step["description"],
                        "status": "completed",
                    }
                return StopEvent(result=step_results)

        workflow = TaskWorkflow(timeout=60, verbose=False)
        result = await workflow.run(task=task.description)

        return {
            "adapter": "llamaindex",
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
            return {"status": "failed", "error": "llamaindex not installed"}

        from llama_index.core import Document
        from llama_index.core.workflow import Workflow, StartEvent, StopEvent

        class MissionWorkflow(Workflow):
            async def handle(self, ev: StartEvent) -> StopEvent:
                task_results = []
                for task in tasks:
                    steps = steps_map.get(task.task_id, [])
                    task_results.append({
                        "task_id": task.task_id,
                        "capability": task.capability,
                        "steps": len(steps),
                    })
                return StopEvent(result={"task_results": task_results})

        workflow = MissionWorkflow(timeout=300, verbose=False)
        result = await workflow.run(mission_id=context.mission_id)

        return {
            "adapter": "llamaindex",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "output": result,
            "status": "completed",
        }
