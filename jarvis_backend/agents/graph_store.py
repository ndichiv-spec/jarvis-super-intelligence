"""Redis-backed agent graph store for JARVIS multi-agent orchestration.

Persists agent nodes, edges (communication channels), and message boards
using Redis as the backing store — matching the pattern used by OpenAI
Codex's ``agent-graph-store`` and ``agent-message-board-client``.

Data model (Redis):
    agent:node:<agent_id>        → hash of agent metadata (JSON-encoded)
    agent:edge:<a>:<b>           → hash of edge metadata
    agent:msg:<agent_id>         → list of messages (LPUSH/RPOP)
    agent:msg:pending:<agent_id> → set of pending message IDs awaiting ack

The graph is also mirrored into PostgreSQL (jarvis_kv) for durability and
offline recovery. When Redis is unavailable, the store falls back to
in-process storage (same approach as the Temporal.io in-process fallback).

Usage:
    store = AgentGraphStore()
    await store.start_agent("researcher", role="specialist", config={...})
    await store.send_message(sender_id, receiver_id, {"text": "hello"})
    messages = await store.get_messages(agent_id, limit=100)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger("jarvis.agents.graph")

_LOCAL_EXECUTION_CLAIMS: Dict[str, tuple[str, float]] = {}
_LOCAL_EXECUTION_CLAIMS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AgentNode:
    """A single agent in the graph."""
    agent_id: str
    name: str
    role: str          # "orchestrator", "researcher", "analyst", "engineer", "verifier"
    status: str        # "idle", "running", "paused", "stopped", "error"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    config: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentNode":
        return cls(**data)


@dataclass
class GraphEdge:
    """A directed edge between two agents (communication channel)."""
    source_agent_id: str
    target_agent_id: str
    edge_type: str = "message"   # "message", "delegate", "report"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source_agent_id}:{self.target_agent_id}"


@dataclass
class AgentMessage:
    """A message on an agent's message board."""
    message_id: str
    sender_id: str
    receiver_id: str
    message_type: str       # "task", "result", "query", "response", "event"
    content: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None
    priority: int = 0
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# Redis-backed graph store
# ---------------------------------------------------------------------------

class AgentGraphStore:
    """Persistent agent graph with Redis backing and in-memory fallback."""

    REDIS_PREFIX = "jarvis:agent:"
    NODE_PREFIX = "agent:node:"
    EDGE_PREFIX = "agent:edge:"
    MSG_PREFIX = "agent:msg:"
    MSG_PENDING_PREFIX = "agent:msg:pending:"
    EXECUTION_CLAIM_TTL = 300

    _instance: Optional["AgentGraphStore"] = None

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_messages: int = 10000,
    ):
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._max_messages = max_messages
        self._redis: Optional[Any] = None
        self._fallback: Dict[str, Any] = {"nodes": {}, "edges": {}, "messages": {}}
        self._connected = False

    # -- singleton pattern --------------------------------------------------

    @classmethod
    def get_shared(cls) -> "AgentGraphStore":
        """Get or create the shared graph store instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- connection management ---------------------------------------------

    async def connect(self) -> bool:
        """Connect to Redis. Falls back to in-memory if unavailable."""
        if self._connected:
            return True

        try:
            import redis.asyncio as redis_async

            self._redis = redis_async.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._connected = True
            log.info("AgentGraphStore connected to Redis at %s", self._redis_url)
            return True
        except Exception as e:
            log.warning("Redis unavailable (%s); using in-memory fallback for agent graph", e)
            self._redis = None
            self._connected = True  # still "connected" to fallback
            return False

    async def disconnect(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None
        self._connected = False

    def _key(self, prefix: str, *parts: str) -> str:
        return f"{self.REDIS_PREFIX}{prefix}:{':'.join(parts)}"

    async def claim_agent_execution(self, agent_id: str, token: str, ttl: int = EXECUTION_CLAIM_TTL) -> bool:
        """Claim one agent execution using Redis, or process-local fallback only.

        The local fallback coordinates this Python process only; it is not safe
        for multi-worker deployments without Redis.
        """
        key = self._key("agent:execution", agent_id)
        if self._redis is not None:
            try:
                return bool(await self._redis.set(key, token, nx=True, ex=ttl))
            except Exception:
                # Do not fall back locally: another worker may still hold Redis.
                log.exception("Unable to claim agent execution in Redis")
                return False
        log.warning("Agent execution claim for %s is process-local (Redis unavailable)", agent_id)
        now = time.monotonic()
        with _LOCAL_EXECUTION_CLAIMS_LOCK:
            current = _LOCAL_EXECUTION_CLAIMS.get(agent_id)
            if current and current[1] > now:
                return False
            _LOCAL_EXECUTION_CLAIMS[agent_id] = (token, now + ttl)
            return True

    async def renew_agent_execution(self, agent_id: str, token: str, ttl: int = EXECUTION_CLAIM_TTL) -> bool:
        """Renew an execution lease only while its token still owns the claim."""
        key = self._key("agent:execution", agent_id)
        if self._redis is not None:
            try:
                return bool(await self._redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                    1, key, token, ttl,
                ))
            except Exception:
                log.exception("Unable to renew agent execution claim in Redis")
                return False
        now = time.monotonic()
        with _LOCAL_EXECUTION_CLAIMS_LOCK:
            current = _LOCAL_EXECUTION_CLAIMS.get(agent_id)
            if not current or current[0] != token or current[1] <= now:
                return False
            _LOCAL_EXECUTION_CLAIMS[agent_id] = (token, now + ttl)
            return True

    async def release_agent_execution(self, agent_id: str, token: str) -> bool:
        """Release an execution lease only if the caller still owns its token."""
        key = self._key("agent:execution", agent_id)
        if self._redis is not None:
            try:
                return bool(await self._redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    1, key, token,
                ))
            except Exception:
                log.exception("Unable to release agent execution claim in Redis")
                return False
        with _LOCAL_EXECUTION_CLAIMS_LOCK:
            current = _LOCAL_EXECUTION_CLAIMS.get(agent_id)
            if not current or current[0] != token:
                return False
            _LOCAL_EXECUTION_CLAIMS.pop(agent_id, None)
            return True

    # -- node management ----------------------------------------------------

    async def create_agent(
        self,
        name: str,
        role: str,
        config: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        """Register a new agent node in the graph. Returns agent_id."""
        agent_id = f"{role}-{uuid.uuid4().hex[:12]}"
        node = AgentNode(
            agent_id=agent_id,
            name=name,
            role=role,
            status="idle",
            config=config or {},
            capabilities=capabilities or [],
            parent_id=parent_id,
        )

        data = node.to_dict()
        serialized = json.dumps(data, default=str)

        if self._redis is not None:
            await self._redis.hset(
                self._key(self.NODE_PREFIX, agent_id),
                mapping={"data": serialized, "status": node.status}
            )
        self._fallback["nodes"][agent_id] = data
        self._mirror_node(node)

        # Link to parent
        if parent_id:
            await self.add_edge(parent_id, agent_id, edge_type="spawn")

        log.info("Agent created: %s (role=%s, id=%s)", name, role, agent_id)
        return agent_id

    async def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Fetch an agent node by ID."""
        if self._redis is not None:
            raw = await self._redis.hget(self._key(self.NODE_PREFIX, agent_id), "data")
            if raw:
                data = json.loads(raw)
                return AgentNode.from_dict(data)
        # Fallback / mirror
        node_data = self._fallback.get("nodes", {}).get(agent_id)
        if node_data:
            return AgentNode.from_dict(node_data)

        # Also check PostgreSQL mirror
        try:
            from jarvis_backend.core import get_store
            data = get_store("agent_graph").load().get(agent_id)
            if data:
                return AgentNode.from_dict(data)
        except Exception:
            pass

        return None

    def _mirror_node(self, node: AgentNode) -> None:
        """Persist the complete node through JARVIS's existing KV store."""
        try:
            from jarvis_backend.core import get_store
            store = get_store("agent_graph")
            store.load()[node.agent_id] = node.to_dict()
            store.save()
        except Exception:
            # Redis remains the primary store when the SQL mirror is unavailable.
            pass

    async def save_agent(self, node: AgentNode) -> bool:
        """Persist an updated node without dropping its config or metadata."""
        serialized = json.dumps(node.to_dict(), default=str)
        if self._redis is not None:
            await self._redis.hset(
                self._key(self.NODE_PREFIX, node.agent_id),
                mapping={"data": serialized, "status": node.status},
            )
        self._fallback["nodes"][node.agent_id] = node.to_dict()
        self._mirror_node(node)
        return True

    async def update_agent_status(self, agent_id: str, status: str) -> bool:
        """Update an agent's status (idle, running, paused, stopped, error)."""
        node = await self.get_agent(agent_id)
        if node is None:
            return False
        node.status = status
        node.last_active = time.time()
        return await self.save_agent(node)

    async def list_agents(self, role: Optional[str] = None) -> List[AgentNode]:
        """List all agents, optionally filtered by role."""
        nodes = []
        if self._redis is not None:
            pattern = f"{self.REDIS_PREFIX}{self.NODE_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    raw = await self._redis.hget(key, "data")
                    if raw:
                        data = json.loads(raw)
                        node = AgentNode.from_dict(data)
                        if role is None or node.role == role:
                            nodes.append(node)
                if cursor == 0:
                    break
        else:
            for data in self._fallback.get("nodes", {}).values():
                node = AgentNode.from_dict(data)
                if role is None or node.role == role:
                    nodes.append(node)
            # Recover graph nodes when a process restarts without Redis.
            try:
                from jarvis_backend.core import get_store
                persisted = get_store("agent_graph").load()
                known_ids = {node.agent_id for node in nodes}
                for data in persisted.values():
                    node = AgentNode.from_dict(data)
                    if node.agent_id not in known_ids and (role is None or node.role == role):
                        nodes.append(node)
            except Exception:
                pass
        return nodes

    async def delete_agent(self, agent_id: str) -> bool:
        """Remove an agent node and its edges."""
        if self._redis is not None:
            await self._redis.delete(self._key(self.NODE_PREFIX, agent_id))
        self._fallback["nodes"].pop(agent_id, None)
        return True

    # -- edge management ----------------------------------------------------

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "message",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a directed edge between two agents."""
        edge = GraphEdge(
            source_agent_id=source_id,
            target_agent_id=target_id,
            edge_type=edge_type,
            metadata=metadata or {},
        )
        edge_key = self._key(self.EDGE_PREFIX, edge.key)
        serialized = json.dumps(asdict(edge))

        if self._redis is not None:
            await self._redis.hset(edge_key, mapping={"data": serialized})
        else:
            self._fallback.setdefault("edges", {})[edge.key] = asdict(edge)

        # Update parent/child relationships
        source = await self.get_agent(source_id)
        if source:
            if target_id not in source.children_ids:
                source.children_ids.append(target_id)
            await self.update_agent_status(source_id, source.status)

    async def get_edges(self, agent_id: str, direction: str = "both") -> List[GraphEdge]:
        """Get edges for an agent. direction: 'out', 'in', or 'both'."""
        edges = []
        if self._redis is not None:
            pattern = f"{self.REDIS_PREFIX}{self.EDGE_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    raw = await self._redis.hget(key, "data")
                    if raw:
                        edge = GraphEdge(**json.loads(raw))
                        if direction == "out" and edge.source_agent_id == agent_id:
                            edges.append(edge)
                        elif direction == "in" and edge.target_agent_id == agent_id:
                            edges.append(edge)
                        elif direction == "both":
                            edges.append(edge)
                if cursor == 0:
                    break
        else:
            for raw in self._fallback.get("edges", {}).values():
                edge = GraphEdge(**raw) if isinstance(raw, dict) else GraphEdge(**json.loads(raw))
                if direction == "out" and edge.source_agent_id == agent_id:
                    edges.append(edge)
                elif direction == "in" and edge.target_agent_id == agent_id:
                    edges.append(edge)
                elif direction == "both":
                    edges.append(edge)
        return edges

    # -- message board ------------------------------------------------------

    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: Dict[str, Any],
        message_type: str = "message",
        priority: int = 0,
        correlation_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> str:
        """Send a message to an agent's message board."""
        if message_id:
            existing = await self.get_messages(receiver_id, limit=self._max_messages)
            if any(item.message_id == message_id for item in existing):
                return message_id
        msg = AgentMessage(
            message_id=message_id or f"msg-{uuid.uuid4().hex[:16]}",
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content,
            priority=priority,
            correlation_id=correlation_id or f"corr-{uuid.uuid4().hex[:8]}",
        )
        serialized = json.dumps(msg.to_dict() if hasattr(msg, "to_dict") else asdict(msg), default=str)

        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.lpush(self._key(self.MSG_PREFIX, receiver_id), serialized)
            pipe.lpush(self._key(self.MSG_PENDING_PREFIX, receiver_id), msg.message_id)
            pipe.ltrim(self._key(self.MSG_PREFIX, receiver_id), 0, self._max_messages - 1)
            await pipe.execute()
        else:
            self._fallback.setdefault("messages", {}).setdefault(receiver_id, []).insert(0, asdict(msg))

        return msg.message_id

    async def get_messages(
        self,
        agent_id: str,
        limit: int = 100,
        unread_only: bool = False,
    ) -> List[AgentMessage]:
        """Retrieve messages for an agent (newest first)."""
        messages: List[AgentMessage] = []
        if self._redis is not None:
            raw_msgs = await self._redis.lrange(
                self._key(self.MSG_PREFIX, agent_id), 0, limit - 1
            )
            for raw in raw_msgs:
                data = json.loads(raw)
                msg = AgentMessage(**data)
                if unread_only and msg.acknowledged:
                    continue
                messages.append(msg)
        else:
            all_msgs = self._fallback.get("messages", {}).get(agent_id, [])
            for data in all_msgs[:limit]:
                msg = AgentMessage(**data)
                if unread_only and msg.acknowledged:
                    continue
                messages.append(msg)
        return messages

    async def ack_message(self, agent_id: str, message_id: str) -> bool:
        """Mark a message as acknowledged/read."""
        if self._redis is not None:
            # Mark as acknowledged in each message
            raw_msgs = await self._redis.lrange(self._key(self.MSG_PREFIX, agent_id), 0, -1)
            for i, raw in enumerate(raw_msgs):
                data = json.loads(raw)
                if data.get("message_id") == message_id:
                    data["acknowledged"] = True
                    await self._redis.lset(self._key(self.MSG_PREFIX, agent_id), i, json.dumps(data))
                    await self._redis.srem(self._key(self.MSG_PENDING_PREFIX, agent_id), message_id)
                    return True
        else:
            msgs = self._fallback.get("messages", {}).get(agent_id, [])
            for data in msgs:
                if data.get("message_id") == message_id:
                    data["acknowledged"] = True
                    return True
        return False

    async def get_pending_count(self, agent_id: str) -> int:
        """Get the number of unread messages for an agent."""
        if self._redis is not None:
            return await self._redis.scard(self._key(self.MSG_PENDING_PREFIX, agent_id))
        msgs = self._fallback.get("messages", {}).get(agent_id, [])
        return sum(1 for m in msgs if not m.get("acknowledged", False))

    # -- graph status -------------------------------------------------------

    async def graph_status(self) -> Dict[str, Any]:
        """Return a summary of the agent graph state."""
        agents = await self.list_agents()
        status_by_role: Dict[str, int] = {}
        status_by_state: Dict[str, int] = {}
        for agent in agents:
            status_by_role[agent.role] = status_by_role.get(agent.role, 0) + 1
            status_by_state[agent.status] = status_by_state.get(agent.status, 0) + 1

        pending_counts = {}
        for agent in agents:
            pending_counts[agent.name] = await self.get_pending_count(agent.agent_id)

        return {
            "total_agents": len(agents),
            "by_role": status_by_role,
            "by_status": status_by_state,
            "pending_messages": pending_counts,
            "redis_connected": self._redis is not None,
        }


__all__ = [
    "AgentNode",
    "GraphEdge",
    "AgentMessage",
    "AgentGraphStore",
]
