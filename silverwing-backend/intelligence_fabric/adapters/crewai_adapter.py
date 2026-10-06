"""CrewAI adapter for the Silverwing Intelligence Fabric."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import BaseOrchestrationAdapter
from fabric_models import AgentSpec, MissionContext, TaskSpec


class CrewAIAdapter(BaseOrchestrationAdapter):
    """Runs missions through CrewAI's crew/agent/task model.

    Best use-cases:
      * Role-playing agent teams
      * Delegation and back-and-forth conversation
      * Human-in-the-loop review
    """

    @property
    def name(self) -> str:
        return "crewai"

    def is_available(self) -> bool:
        try:
            import crewai  # noqa: F401
            return True
        except ImportError:
            return False

    async def execute(self, agent: AgentSpec, task: TaskSpec,
                      steps: List[Dict[str, Any]],
                      context: MissionContext) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "crewai not installed"}

        from crewai import Agent, Task, Crew

        crew_agent = Agent(
            role=agent.role,
            goal=f"Execute {task.description}",
            backstory=agent.system_prompt,
            verbose=False,
            allow_delegation=False,
        )

        crew_task = Task(
            description=task.description,
            agent=crew_agent,
            expected_output=f"Result for {task.description}",
        )

        crew = Crew(agents=[crew_agent], tasks=[crew_task], verbose=False)
        result = await crew.kickoff_async()

        return {
            "adapter": "crewai",
            "task_id": task.task_id,
            "agent_id": agent.agent_id,
            "output": str(result),
            "status": "completed",
        }

    async def execute_mission(self, context: MissionContext,
                              tasks: List[TaskSpec],
                              steps_map: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "error": "crewai not installed"}

        from crewai import Agent, Task, Crew

        agents: List[Any] = []
        crew_tasks: List[Any] = []

        for task, agent in [(t, self._make_agent_for_task(t)) for t in tasks]:
            crew_tasks.append(Task(
                description=task.description,
                agent=agent,
                expected_output=f"Result for {task.description}",
            ))
            agents.append(agent)

        crew = Crew(agents=agents, tasks=crew_tasks, verbose=False)
        result = await crew.kickoff_async()

        return {
            "adapter": "crewai",
            "mission_id": context.mission_id,
            "tasks_executed": len(tasks),
            "output": str(result),
            "status": "completed",
        }

    def _make_agent_for_task(self, task: TaskSpec) -> Any:
        from crewai import Agent

        # Look up the agent spec from the scheduler
        from agent_scheduler import AgentScheduler
        scheduler = AgentScheduler()
        spec = scheduler.get_spec(task.agent_id or "researcher")
        return Agent(
            role=spec.role if spec else "agent",
            goal=f"Execute {task.description}",
            backstory=spec.system_prompt if spec else "",
            verbose=False,
        )
