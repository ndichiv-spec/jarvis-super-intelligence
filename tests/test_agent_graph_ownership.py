import asyncio

import pytest
from fastapi import HTTPException

from jarvis_backend.agents.graph_store import AgentNode
from jarvis_backend.routers import agents


class FakeGraphStore:
    def __init__(self, nodes):
        self.nodes = {node.agent_id: node for node in nodes}

    async def list_agents(self):
        return list(self.nodes.values())

    async def get_agent(self, agent_id):
        return self.nodes.get(agent_id)


class FakeLifecycleManager:
    def __init__(self):
        self.spawned = None

    async def spawn(self, **kwargs):
        self.spawned = kwargs
        return "researcher-test-agent"


def test_graph_agent_list_is_scoped_to_authenticated_owner(monkeypatch):
    store = FakeGraphStore([
        AgentNode("researcher-own", "Mine", "researcher", "running", config={"_owner_id": "user-1"}),
        AgentNode("researcher-other", "Not mine", "researcher", "running", config={"_owner_id": "user-2"}),
        AgentNode("researcher-legacy", "Legacy", "researcher", "running"),
    ])

    async def get_store():
        return store

    monkeypatch.setattr(agents, "_get_graph_store", get_store)
    result = asyncio.run(agents.list_graph_agents({"id": "user-1"}))

    assert result["count"] == 1
    assert [item["agent_id"] for item in result["agents"]] == ["researcher-own"]


def test_other_users_cannot_read_or_control_graph_agent(monkeypatch):
    store = FakeGraphStore([
        AgentNode("researcher-other", "Not mine", "researcher", "running", config={"_owner_id": "user-2"}),
    ])

    async def get_store():
        return store

    monkeypatch.setattr(agents, "_get_graph_store", get_store)

    with pytest.raises(HTTPException) as error:
        asyncio.run(agents.get_graph_agent("researcher-other", {"id": "user-1"}))

    assert error.value.status_code == 404


def test_spawn_binds_owner_and_routes_results_to_private_inbox(monkeypatch):
    manager = FakeLifecycleManager()

    async def get_manager():
        return manager

    monkeypatch.setattr(agents, "_get_lifecycle_manager", get_manager)
    body = agents.SpawnAgentIn(
        name="Research task",
        role="researcher",
        config={"_owner_id": "attacker-controlled"},
        request={"query": "Find recent research", "sender_id": "another-user-inbox"},
    )

    result = asyncio.run(agents.spawn_graph_agent(body, {"id": "user-1"}))

    assert result["agent_id"] == "researcher-test-agent"
    assert manager.spawned["config"]["_owner_id"] == "user-1"
    assert manager.spawned["request"]["sender_id"] == "orchestrator:user-1"

