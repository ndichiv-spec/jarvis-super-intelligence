"""AutoGen adapter for the Silverwing Intelligence Fabric."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import BaseOrchestrationAdapter
from fabric_models import AgentSpec, MissionContext, TaskSpec


class AutoGenAdapter(BaseOrchestrationAdapter):
    """Runs tasks through Microsoft AutoGen's conversable-agent model.

    Best use-cases:
      * Multi-agent conversations and debate
      * Code execution via code executors
      * Tool-calling agents
    """

    @property
    def name(self) -> str:
        return "autogen"

    def is_available(self) -> bool:
        try:
            import autogen  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "autogen not installed"}

        import autogen

        ag = autogen.AssistantAgent(
            name=agent.agent_id,
            system_message=agent.system_prompt,
            llm_config={"config_list": []},  # Silverwing routes through its own gateway
        )

        user_proxy = autogen.UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            code_execution_module=None,  # Silverwing handles code exec via tools
        )

        result = user_proxy.initiate_chat(
            recipient=ag,
            message=f"Execute: {task.description}",
            summary_method="reflection",
        )

        return {
            "adapter": "autogen",
            "task_id": task.task_id,
            "agent_id": agent.agent_id,
            "output": str(result.summary),
            "status": "completed",
        }

    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "autogen not installed"}

        import autogen

        agents: List[Any] = []
        for task in tasks:
            from agent_scheduler import AgentScheduler
            scheduler = AgentScheduler()
            spec = scheduler.get_spec(task.agent_id or "researcher")
            ag = autogen.AssistantAgent(
                name=spec.agent_id,
                system_message=spec.system_prompt,
                llm_config={"config_list": []},
            )
            agents.append(ag)

        user_proxy = autogen.UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=len(agents),
        )

        result = user_proxy.initiate_chats(
            recipients=agents,
            messages=[f"Execute mission: {context.objective}"],
            summary_method="reflection",
        )

        return {
            "adapter": "autogen",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "output": str(result[-1].summary) if result else "",
            "status": "completed",
        }
