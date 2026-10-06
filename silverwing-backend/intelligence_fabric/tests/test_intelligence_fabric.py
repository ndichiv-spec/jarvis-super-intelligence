"""Tests for the Silverwing Intelligence Fabric core components.

These tests verify:
  * MissionPlanner decomposes requests into tasks correctly
  * AgentScheduler assigns tasks to appropriate agents
  * ToolSelector validates tool allowances
  * VerificationCoordinator tracks claim verification
  * IntelligenceFabric can handle requests end-to-end
  * Integration with Model Gateway routing
"""

import asyncio
import sys

import pytest

sys.path.insert(0, '.')
sys.path.insert(0, '..')
sys.path.insert(0, '../..')

from fabric_models import (
    IntelligenceRequest,
    MissionContext,
    TaskSpec,
    TaskStatus,
    TaskPriority,
    RiskLevel,
    AgentSpec,
)
from mission_planner import MissionPlanner
from task_planner import TaskPlanner
from agent_scheduler import AgentScheduler
from tool_selector import ToolSelector
from verification_coordinator import VerificationCoordinator, VerificationStatus
from fabric import IntelligenceFabric


class TestMissionPlanner:
    """Tests for MissionPlanner decomposition logic."""

    def setup_method(self):
        self.planner = MissionPlanner()

    def test_create_context_generates_mission_id(self):
        """Context always has a unique mission ID."""
        req = IntelligenceRequest(query="What is AI?")
        ctx = self.planner.create_context(req)
        assert ctx.mission_id is not None
        assert ctx.mission_id.startswith("mission-")

    def test_create_context_preserves_privacy_and_cost(self):
        """Privacy and cost settings are passed to context."""
        req = IntelligenceRequest(
            query="Research quantum annealing",
            privacy="private",
            cost="low_cost",
        )
        ctx = self.planner.create_context(req)
        assert ctx.privacy == "private"
        assert ctx.cost == "low_cost"

    def test_plan_produces_multiple_tasks(self):
        """A research query produces multiple tasks."""
        req = IntelligenceRequest(
            query="Study transformer architectures",
            privacy="public",
        )
        tasks = self.planner.plan(req)
        assert len(tasks) >= 3  # research, analysis, verification, memory

    def test_plan_registers_task_ids_in_context(self):
        """Task IDs are tracked in the context."""
        req = IntelligenceRequest(query="Analyze stock trends")
        ctx = MissionContext(
            mission_id="test-1", objective=req.query,
            privacy=req.privacy, cost=req.cost
        )
        tasks = self.planner.plan(req, ctx)
        assert len(ctx.task_ids) == len(tasks)
        for task in tasks:
            assert task.task_id in ctx.task_ids

    def test_plan_includes_verification_task(self):
        """Verification task is always appended for evidence work."""
        req = IntelligenceRequest(query="What is quantum computing?")
        tasks = self.planner.plan(req)
        task_caps = [t.capability for t in tasks]
        assert "verification" in task_caps
        # memory_consolidation template uses capability "memory_management"
        assert "memory_management" in task_caps

    def test_plan_respects_constraints(self):
        """Task constraints affect planning."""
        req = IntelligenceRequest(
            query="Code a sorting function",
            constraints={"force_tasks": ["coding", "verification"]},
        )
        tasks = self.planner.plan(req)
        task_caps = [t.capability for t in tasks]
        assert "coding" in task_caps
        assert "verification" in task_caps


class TestTaskPlanner:
    """Tests for TaskPlanner step decomposition."""

    def setup_method(self):
        self.planner = TaskPlanner()

    def test_decompose_research_produces_steps(self):
        """Research tasks decompose into research steps."""
        task = TaskSpec(
            task_id="t1", mission_id="m1", description="Research AI alignment",
            capability="research", priority=TaskPriority.NORMAL,
            risk=RiskLevel.LOW, privacy="public", cost="best_quality",
            required_tools=["web_search"],
            required_model_classes=["REASONING"],
        )
        steps = self.planner.decompose(task)
        assert len(steps) >= 3
        step_names = [s["step"] for s in steps]
        assert "search_sources" in step_names

    def test_decompose_analysis_produces_analysis_steps(self):
        """Analysis tasks have analysis-focused steps."""
        task = TaskSpec(
            task_id="t2", mission_id="m2", description="Analyze the data",
            capability="analysis", priority=TaskPriority.NORMAL,
            risk=RiskLevel.MEDIUM, privacy="public", cost="best_quality",
            required_tools=["python"],
        )
        steps = self.planner.decompose(task)
        step_names = [s["step"] for s in steps]
        assert "identify_patterns" in step_names

    def test_decompose_code_produces_code_steps(self):
        """Coding tasks have code-generation steps."""
        task = TaskSpec(
            task_id="t3", mission_id="m3", description="Generate Python code",
            capability="coding", priority=TaskPriority.NORMAL,
            risk=RiskLevel.HIGH, privacy="public", cost="best_quality",
            required_tools=["python", "filesystem"],
        )
        steps = self.planner.decompose(task)
        step_names = [s["step"] for s in steps]
        assert "generate_code" in step_names

    def test_estimate_steps_returns_positive(self):
        """Step count estimation returns a positive integer."""
        assert self.planner.estimate_steps("research") > 0
        assert self.planner.estimate_steps("analysis") > 0
        assert self.planner.estimate_steps("unknown") == 1


class TestAgentScheduler:
    """Tests for AgentScheduler agent assignment."""

    def setup_method(self):
        self.scheduler = AgentScheduler()

    def test_agent_ids_contains_all_eight(self):
        """Scheduler knows about all 8 defined agent types."""
        expected = {"orchestrator", "researcher", "analyst", "verifier",
                    "engineer", "coder", "librarian", "planner"}
        actual = set(self.scheduler.agent_ids)
        assert expected == actual

    def test_get_spec_returns_agent_spec(self):
        """Getting an agent spec returns a valid AgentSpec."""
        spec = self.scheduler.get_spec("researcher")
        assert spec is not None
        assert spec.agent_id == "researcher"
        assert "research" in spec.capabilities

    def test_capabilities_returns_all_union(self):
        """Capabilities returns all unique capability strings."""
        caps = self.scheduler.capabilities()
        assert "research" in caps
        assert "analysis" in caps
        assert "verification" in caps
        assert "coding" in caps

    def test_schedule_assigns_correct_agent_for_research(self):
        """Research capability tasks go to researcher agent."""
        task = TaskSpec(
            task_id="t1", mission_id="m1", description="Find papers",
            capability="research", priority=TaskPriority.NORMAL,
            risk=RiskLevel.LOW, privacy="public", cost="best_quality",
            required_tools=["web_search", "openalex"],
            required_model_classes=["RESEARCH"],
        )
        spec = self.scheduler.schedule(task)
        assert spec.agent_id == "researcher"
        assert task.agent_id == "researcher"
        assert task.status == TaskStatus.ASSIGNED

    def test_schedule_assigns_verifier_for_verification(self):
        """Verification capability tasks go to verifier agent."""
        task = TaskSpec(
            task_id="t2", mission_id="m1", description="Verify this claim",
            capability="verification", priority=TaskPriority.HIGH,
            risk=RiskLevel.MEDIUM, privacy="public", cost="best_quality",
            required_tools=["web_fetch"],
        )
        spec = self.scheduler.schedule(task)
        assert spec.verification_policy == "strict"


class TestToolSelector:
    """Tests for ToolSelector tool validation."""

    def setup_method(self):
        self.selector = ToolSelector()

    def test_tool_names_contains_all(self):
        """Tool catalog includes all 24 tools."""
        assert "web_search" in self.selector.tool_names
        assert "openalex" in self.selector.tool_names
        assert "python" in self.selector.tool_names
        assert "knowledge_graph" in self.selector.tool_names

    def test_select_for_step_builtin_no_tools(self):
        """Builtin steps yield empty tool list."""
        step = {"step": "decompose_query", "description": "Break query",
                "tool": "builtin", "produces": ["sub_queries"]}
        agent = AgentSpec(agent_id="test", role="test",
                          capabilities=["test"], allowed_tools=[],
                          verification_policy="standard")
        task = TaskSpec(task_id="t1", mission_id="m1", description="Test task",
                        capability="test", privacy="public", cost="best_quality",
                        required_tools=[])
        selections = self.selector.select_for_step(agent, task, step)
        assert selections == []

    def test_select_for_step_model_uses_model_inference(self):
        """Model steps select model_inference tool."""
        step = {"step": "identify_patterns", "description": "Find patterns",
                "tool": "model", "produces": ["patterns"]}
        agent = AgentSpec(agent_id="test", role="test",
                          capabilities=["test"], allowed_tools=["model_inference"],
                          verification_policy="standard")
        task = TaskSpec(task_id="t1", mission_id="m1", description="Test task",
                        capability="test", privacy="public", cost="best_quality",
                        required_tools=["model_inference"])
        selections = self.selector.select_for_step(agent, task, step)
        assert len(selections) == 1
        assert selections[0].name == "model_inference"


class TestVerificationCoordinator:
    """Tests for VerificationCoordinator claim tracking."""

    def setup_method(self):
        self.coordinator = VerificationCoordinator()

    def test_register_claims_returns_claim_ids(self):
        """Registering claims returns their IDs."""
        claims = [
            {"statement": "AI will reach AGI by 2030", "confidence": 0.7},
            {"statement": "Current LLMs are transformers", "confidence": 0.95},
        ]
        mission_id = "mission-1"
        agent_id = "researcher"
        ids = self.coordinator.register_claims(mission_id, agent_id, claims)
        assert len(ids) == 2
        assert all(cid.startswith("claim-") for cid in ids)

    def test_needs_verification_standard(self):
        """Standard policy requires verification for research."""
        agent = AgentSpec(agent_id="r1", role="researcher",
                          capabilities=["research"],
                          verification_policy="standard")
        assert self.coordinator.needs_verification(agent, "research") is True
        assert self.coordinator.needs_verification(agent, "memory_management") is False

    def test_needs_verification_skip(self):
        """Skip policy skips all verification."""
        agent = AgentSpec(agent_id="m1", role="manager",
                          capabilities=["research"],
                          verification_policy="skip")
        assert self.coordinator.needs_verification(agent, "research") is False

    def test_get_record_returns_correct_data(self):
        """Retrieving a record by ID works."""
        claims = [{"statement": "Test claim", "confidence": 0.5}]
        ids = self.coordinator.register_claims("m1", "a1", claims)
        record = self.coordinator.get_record(ids[0])
        assert record is not None
        assert record["statement"] == "Test claim"

    def test_summary_counts_properly(self):
        """Summary counts claims correctly."""
        claims = [{"statement": f"Claim {i}", "confidence": 0.5} for i in range(5)]
        self.coordinator.register_claims("m1", "a1", claims)

        summary = self.coordinator.summary("m1")
        assert summary["total_claims"] == 5


class TestIntelligenceFabric:
    """End-to-end tests for IntelligenceFabric."""

    def setup_method(self):
        self.fabric = IntelligenceFabric()

    def test_fabric_has_all_components(self):
        """Fabric instantiates all required subsystems."""
        assert self.fabric.planner is not None
        assert self.fabric.task_planner is not None
        assert self.fabric.scheduler is not None
        assert self.fabric.tool_selector is not None
        assert self.fabric.verifier is not None

    def test_list_frameworks_returns_native(self):
        """Fabric can list available framework adapters."""
        frameworks = self.fabric.list_frameworks()
        names = [f.name for f in frameworks]
        assert "native" in names
        assert "langgraph" in names
        assert "crewai" in names

    def test_get_adapter_returns_native_by_default(self):
        """Default adapter is native execution."""
        adapter = self.fabric.get_adapter("native")
        assert adapter.name == "native"
        assert adapter.is_available() is True

    def test_get_routing_decision_without_router_returns_none(self):
        """Without a ModelRouter, routing returns None."""
        decision = self.fabric.get_routing_decision(capability="test")
        assert decision is None

    def test_handle_request_returns_result(self):
        """Request handling produces a FabricResult."""
        req = IntelligenceRequest(
            query="What are transformers?",
            privacy="public",
            cost="best_quality",
            latency="normal",
        )
        result = asyncio.run(self.fabric.handle_request(req))

        assert result.mission_id is not None
        assert result.query == "What are transformers?"
        assert result.success is True
        assert len(result.tasks) >= 3
        assert result.elapsed_ms >= 0

    def test_handle_request_assigns_agents(self):
        """Tasks get assigned to agents."""
        req = IntelligenceRequest(query="Analyze BERT model performance")
        result = asyncio.run(self.fabric.handle_request(req))

        agent_ids = {a["agent_id"] for a in result.agents}
        assert "researcher" in agent_ids or "analyst" in agent_ids

    def test_reset_clears_state(self):
        """Reset clears internal state."""
        req = IntelligenceRequest(query="Test reset")
        asyncio.run(self.fabric.handle_request(req))

        self.fabric.reset()
        assert len(self.fabric._routing_decisions) == 0
        assert len(self.fabric._tool_executions) == 0


class TestIntelligenceFabricWithModelGateway:
    """Tests requiring the Model Gateway integration."""

    def test_fabric_with_router_selects_models(self):
        """With a Router, the Fabric can select models."""

        from model_provider import ModelRouter, ModelManager, ModelConfig

        config = ModelConfig()
        manager = ModelManager(config=config)
        router = ModelRouter(manager=manager)

        fabric = IntelligenceFabric(router=router)

        decision = fabric.get_routing_decision(
            capability="research",
            privacy="public",
            cost="best_quality",
            task="test",
        )

        # Without API keys, falls back to local
        assert decision is not None
        assert decision.selected_model is not None

    def test_fabric_uses_router_decisions_in_result(self):
        """Routing decisions appear in FabricResult."""

        from model_provider import ModelRouter, ModelManager, ModelConfig

        config = ModelConfig()
        manager = ModelManager(config=config)
        router = ModelRouter(manager=manager)

        fabric = IntelligenceFabric(router=router)
        req = IntelligenceRequest(query="Test model selection")
        result = asyncio.run(fabric.handle_request(req))

        # Should have routing decisions recorded
        assert len(result.routing_decisions) > 0
        first = result.routing_decisions[0]
        assert "selected_model" in first
        assert "provider" in first


if __name__ == "__main__":
    pytest.main([__file__, "-v"])