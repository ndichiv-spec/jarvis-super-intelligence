"""JARVIS Multi-Agent System.

Provides persistent agent graph storage, lifecycle management, and
specialist agent roles for complex multi-agent workflows.

Components:
- AgentGraphStore: Redis-backed persistent agent graph (nodes, edges, messages)
- AgentLifecycleManager: Spawn/pause/resume/terminate multi-agent instances
- SpecialistAgent: Role-based agents (orchestrator, researcher, analyst, engineer, verifier)

This matches the multi-agent orchestration pattern used by OpenAI Codex
(``agent-graph-store``, ``agent-message-board-client``) and enables
complex agent collaboration workflows where multiple agents communicate
via message boards and the JARVIS capability registry.

Usage:
    from jarvis_backend.agents import AgentLifecycleManager, create_agent

    manager = AgentLifecycleManager.get_shared()
    agent_id = await manager.spawn(
        name="researcher-1",
        role="researcher",
        config={"model": "gpt-4o-mini"},
        request={"capability": "research_cortex", "action": "search_arxiv", "params": {"query": "Tesla FSD"}},
    )
"""
from __future__ import annotations

from .graph_store import (
    AgentNode,
    GraphEdge,
    AgentMessage,
    AgentGraphStore,
)
from .lifecycle import AgentLifecycleManager
from .specialist import (
    SpecialistAgent,
    create_agent,
    get_role_definitions,
    ROLE_DEFINITIONS,
)

__all__ = [
    "AgentGraphStore",
    "AgentLifecycleManager",
    "SpecialistAgent",
    "AgentNode",
    "GraphEdge",
    "AgentMessage",
    "create_agent",
    "get_role_definitions",
    "ROLE_DEFINITIONS",
]
