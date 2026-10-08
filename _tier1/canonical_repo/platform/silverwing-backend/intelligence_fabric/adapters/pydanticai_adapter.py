"""PydanticAI adapter for the Silverwing Intelligence Fabric."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import BaseOrchestrationAdapter
from fabric_models import AgentSpec, MissionContext, TaskSpec


class PydanticAIAdapter(BaseOrchestrationAdapter):
    """Runs tasks through PydanticAI's type-safe agent framework.

    Best use-cases:
      * Structured JSON output from models
      * Dependency injection for tools
      * Type-safe agent pipelines
    """

    @property
    def name(self) -> str:
        return "pydanticai"

    def is_available(self) -> bool:
        try:
            import pydantic_ai  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "pydanticai not installed"}

        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIModel

        # Build the agent using the Silverwing-selected model
        model_name = agent.model_preference or "gpt-4o"
        model = OpenAIModel(model_name)

        ag = Agent(model, system_prompt=agent.system_prompt)

        result = await ag.run(
            f"Execute the following task: {task.description}\n"
            f"Steps: {', '.join(s['step'] for s in steps)}"
        )

        return {
            "adapter": "pydanticai",
            "task_id": task.task_id,
            "agent_id": agent.agent_id,
            "output": result.output,
            "status": "completed",
        }

    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "pydanticai not installed"}

        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIModel

        model = OpenAIModel("gpt-4o")
        ag = Agent(model, system_prompt=(
            f"You are a mission orchestrator for: {context.objective}. "
            "Coordinate sub-tasks and report results."
        ))

        task_descs = [f"Task: {t.description}" for t in tasks]
        result = await ag.run(
            "Execute the following mission:\n" + "\n".join(task_descs)
        )

        return {
            "adapter": "pydanticai",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "output": result.output,
            "status": "completed",
        }
