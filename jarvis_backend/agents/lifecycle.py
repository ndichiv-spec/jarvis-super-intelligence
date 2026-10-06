"""Agent lifecycle manager for JARVIS multi-agent orchestration.

Manages the spawn/pause/resume/terminate lifecycle of agent instances,
integrating with the AgentGraphStore for persistent state and the
JARVIS capability registry for agent execution.

Lifecycle states:
  inactive → spawned → running → paused → running → terminated
                     ↘ error → terminated

Each agent runs as an asyncio task. When paused, the task is cancelled but
its state (message board, config, partial results) persists in the graph
store for later resumption — similar to Codex's agent lifecycle.

Usage:
    manager = AgentLifecycleManager()
    await manager.spawn("researcher", role="specialist", request={...})
    # ... later ...
    await manager.pause(agent_id)
    await manager.resume(agent_id)
    await manager.terminate(agent_id)
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.agents.lifecycle")

_SECRET_REQUEST_SUFFIXES = (
    "password", "passwd", "secret", "token", "credential", "credentials",
    "authorization", "cookie", "apikey", "privatekey", "accesskey",
)


def _persistable_request(value: Any) -> Any:
    """Strip credentials from request data before it enters durable graph state."""
    if isinstance(value, dict):
        def is_secret_key(key: Any) -> bool:
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            return any(normalized.endswith(suffix) for suffix in _SECRET_REQUEST_SUFFIXES)

        return {
            key: _persistable_request(item)
            for key, item in value.items()
            if not is_secret_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_persistable_request(item) for item in value]
    return value


class AgentLifecycleManager:
    """Manages the full lifecycle of multi-agent instances."""

    _instance: Optional["AgentLifecycleManager"] = None

    def __init__(self):
        self._store: Optional[Any] = None
        self._tasks: Dict[str, asyncio.Task] = {}
        self._agent_configs: Dict[str, Dict[str, Any]] = {}
        self._shutdown = False
        self._resume_lock = asyncio.Lock()

    # -- singleton ----------------------------------------------------------

    @classmethod
    def get_shared(cls) -> "AgentLifecycleManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_store(self):
        if self._store is None:
            from jarvis_backend.agents.graph_store import AgentGraphStore
            self._store = AgentGraphStore.get_shared()
        return self._store

    async def ensure_store(self) -> bool:
        store = self._get_store()
        if not store._connected:
            await store.connect()
        return store._connected

    # -- lifecycle operations ----------------------------------------------

    async def _initialize_lifecycle_checkpoint(
        self, agent_id: str, request: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        safe_request = _persistable_request(request or {})
        node = await self._get_store().get_agent(agent_id)
        if node is None:
            return safe_request
        node.metadata["lifecycle"] = {
            "version": 1,
            "initial_request": safe_request,
            "initial_request_status": "pending" if safe_request else "completed",
            "initial_request_attempts": 0,
            "message_progress": {},
            "created_at": time.time(),
        }
        await self._get_store().save_agent(node)
        return safe_request

    async def spawn(
        self,
        name: str,
        role: str = "specialist",
        config: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Spawn a new agent instance.

        Args:
            name: Human-readable agent name.
            role: Agent role (orchestrator, researcher, analyst, engineer, verifier).
            config: Agent-specific configuration.
            capabilities: List of capability names this agent can use.
            request: Initial task/request to start the agent with.

        Returns:
            The agent_id of the spawned agent.
        """
        await self.ensure_store()
        store = self._get_store()

        agent_id = await store.create_agent(
            name=name,
            role=role,
            config=config or {},
            capabilities=capabilities or [],
        )

        safe_request = await self._initialize_lifecycle_checkpoint(agent_id, request)

        # Cache only; the node remains the source of truth after a restart.
        self._agent_configs[agent_id] = {
            "name": name,
            "role": role,
            "config": config or {},
            "capabilities": capabilities or [],
            "request": safe_request,
            "spawned_at": time.time(),
        }

        await store.update_agent_status(agent_id, "spawned")

        # Start the agent's execution loop
        await self._launch_agent(agent_id)

        log.info("Agent spawned: %s (id=%s, role=%s)", name, agent_id, role)
        return agent_id

    async def _launch_agent(self, agent_id: str) -> bool:
        """Acquire the shared execution claim before starting a worker task."""
        store = self._get_store()
        token = uuid.uuid4().hex
        claim = getattr(store, "claim_agent_execution", None)
        if claim is None or not await claim(agent_id, token):
            return False
        try:
            task = asyncio.create_task(self._run_agent(agent_id, token))
        except BaseException:
            await self._release_execution_claim(agent_id, token)
            raise
        self._tasks[agent_id] = task
        return True

    async def _renew_execution_claim(
        self,
        agent_id: str,
        token: str,
        parent_task: asyncio.Task,
        claim_lost: asyncio.Event,
    ) -> None:
        store = self._get_store()
        renew = getattr(store, "renew_agent_execution", None)
        if renew is None:
            return
        while True:
            await asyncio.sleep(60)
            if not await renew(agent_id, token):
                log.error("Agent execution claim lost: %s", agent_id)
                claim_lost.set()
                if not parent_task.done():
                    parent_task.cancel()
                return

    async def _release_execution_claim(self, agent_id: str, token: str) -> None:
        release = getattr(self._get_store(), "release_agent_execution", None)
        if release is not None:
            await release(agent_id, token)

    def _runtime_config(self, node: Any) -> Dict[str, Any]:
        config = self._agent_configs.get(node.agent_id)
        if config is not None:
            return config
        lifecycle = node.metadata.get("lifecycle", {})
        config = {
            "name": node.name,
            "role": node.role,
            "config": node.config,
            "capabilities": node.capabilities,
            "request": lifecycle.get("initial_request", {}),
            "spawned_at": node.created_at,
        }
        self._agent_configs[node.agent_id] = config
        return config

    async def _save_lifecycle(self, node: Any, lifecycle: Dict[str, Any]) -> None:
        node.metadata["lifecycle"] = lifecycle
        node.last_active = time.time()
        await self._get_store().save_agent(node)

    async def _deliver_initial_result(self, agent_id: str, config: Dict[str, Any]) -> None:
        store = self._get_store()
        node = await store.get_agent(agent_id)
        lifecycle = node.metadata.get("lifecycle", {})
        if (
            lifecycle.get("initial_request_status") != "completed"
            or not lifecycle.get("initial_request")
        ):
            return
        if lifecycle.get("initial_result_delivery") == "delivered":
            return

        result = lifecycle.get("initial_result")
        request = lifecycle.get("initial_request", {})
        await store.send_message(
            sender_id=agent_id,
            receiver_id=request.get("sender_id", "orchestrator"),
            content={"result": result, "agent_id": agent_id},
            message_type="result",
            correlation_id=f"agent-initial-{agent_id}",
            message_id=f"agent-initial-result-{agent_id}",
        )
        lifecycle["initial_result_delivery"] = "delivered"
        lifecycle.pop("initial_request", None)
        lifecycle.pop("initial_result", None)
        await self._save_lifecycle(node, lifecycle)
        owner_id = config.get("config", {}).get("_owner_id")
        if owner_id:
            from jarvis_backend.notifications import record_notification
            record_notification(
                str(owner_id),
                "Agent task completed",
                f"{config.get('name', config.get('role', 'Agent'))} finished its submitted task.",
                "agents",
            )

    async def _deliver_indeterminate_initial(self, agent_id: str) -> None:
        store = self._get_store()
        node = await store.get_agent(agent_id)
        lifecycle = node.metadata.get("lifecycle", {})
        if lifecycle.get("initial_request_status") != "indeterminate":
            return
        if lifecycle.get("initial_result_delivery") == "indeterminate_delivered":
            return
        request = lifecycle.get("initial_request", {})
        result = {
            "success": False,
            "status": "indeterminate",
            "error": "Execution was interrupted; its outcome is unknown and was not replayed.",
            "agent_id": agent_id,
        }
        await store.send_message(
            sender_id=agent_id,
            receiver_id=request.get(
                "sender_id", lifecycle.get("initial_request_sender", "orchestrator")
            ),
            content={"result": result, "agent_id": agent_id, "status": "indeterminate"},
            message_type="result",
            correlation_id=f"agent-initial-{agent_id}",
            message_id=f"agent-initial-result-{agent_id}",
        )
        lifecycle["initial_result_delivery"] = "indeterminate_delivered"
        lifecycle["initial_request_sender"] = request.get(
            "sender_id", lifecycle.get("initial_request_sender", "orchestrator")
        )
        lifecycle.pop("initial_request", None)
        await self._save_lifecycle(node, lifecycle)

    async def _run_agent(self, agent_id: str, claim_token: Optional[str] = None) -> None:
        """Main execution loop for a single agent."""
        claim_heartbeat = None
        claim_lost = asyncio.Event()
        try:
            if claim_token is None:
                # Keep direct/internal callers safe too; production spawn/resume
                # acquire before creating the task.
                claim_token = uuid.uuid4().hex
                claim = getattr(self._get_store(), "claim_agent_execution", None)
                if claim is None or not await claim(agent_id, claim_token):
                    return
            parent_task = asyncio.current_task()
            claim_heartbeat = asyncio.create_task(
                self._renew_execution_claim(
                    agent_id, claim_token, parent_task, claim_lost
                )
            )
            store = self._get_store()
            node = await store.get_agent(agent_id)
            if node is None:
                return
            config = self._runtime_config(node)
            lifecycle = node.metadata.get("lifecycle", {})
            node.status = "running"
            node.last_active = time.time()
            await store.save_agent(node)

            request = lifecycle.get("initial_request", {})
            role = config.get("role", "specialist")

            # Get the specialist agent class for this role
            from jarvis_backend.agents.specialist import SpecialistAgent

            agent = SpecialistAgent(
                agent_id=agent_id,
                role=role,
                config=config.get("config", {}),
                capabilities=config.get("capabilities", []),
            )

            initial_status = lifecycle.get("initial_request_status", "completed")
            if initial_status == "pending" and request:
                # Persist intent before invoking an operation that may have side effects.
                lifecycle["initial_request_status"] = "running"
                lifecycle["initial_request_attempts"] = lifecycle.get("initial_request_attempts", 0) + 1
                lifecycle["initial_started_at"] = time.time()
                await self._save_lifecycle(node, lifecycle)
                result = await agent.execute(request)
                lifecycle["initial_result"] = result
                lifecycle["initial_request_status"] = "completed"
                lifecycle["initial_completed_at"] = time.time()
                lifecycle["initial_result_delivery"] = "pending"
                await self._save_lifecycle(node, lifecycle)
                await self._deliver_initial_result(agent_id, config)
            elif initial_status == "running":
                # The previous process may have completed the side effect before it
                # died. Never replay an uncheckpointed operation automatically.
                lifecycle["initial_request_status"] = "indeterminate"
                lifecycle["initial_interrupted_at"] = time.time()
                await self._save_lifecycle(node, lifecycle)
                await self._deliver_indeterminate_initial(agent_id)
            elif initial_status == "indeterminate":
                await self._deliver_indeterminate_initial(agent_id)
            elif initial_status == "completed":
                # Delivery is separately checkpointed and uses a stable message id.
                await self._deliver_initial_result(agent_id, config)

            # Main loop: process incoming messages
            while not self._shutdown:
                # Check if we've been paused/terminated
                node = await self._get_store().get_agent(agent_id)
                if node is None:
                    break
                if node.status in ("paused", "stopped"):
                    await asyncio.sleep(1.0)
                    continue
                if node.status == "error":
                    break

                messages = await self._get_store().get_messages(agent_id, limit=10, unread_only=True)
                if not messages:
                    await asyncio.sleep(0.5)
                    continue

                for msg in messages:
                    if msg.message_type == "terminate":
                        await self._get_store().update_agent_status(agent_id, "terminated")
                        return
                    if msg.message_type == "pause":
                        await self._get_store().update_agent_status(agent_id, "paused")
                        await self._get_store().ack_message(agent_id, msg.message_id)
                        # Wait to be resumed
                        while not self._shutdown:
                            node = await self._get_store().get_agent(agent_id)
                            if node and node.status == "running":
                                break
                            await asyncio.sleep(1.0)
                        await self._get_store().ack_message(agent_id, msg.message_id)
                        continue

                    node = await store.get_agent(agent_id)
                    lifecycle = node.metadata.get("lifecycle", {})
                    progress = lifecycle.setdefault("message_progress", {})
                    state = progress.get(msg.message_id, {}).get("status")
                    if state == "indeterminate_delivered":
                        await store.ack_message(agent_id, msg.message_id)
                        continue
                    if state == "completed":
                        result = progress[msg.message_id].get("result")
                    elif state in ("running", "indeterminate"):
                        # Ambiguous completion is checkpointed, never blindly replayed.
                        if state == "running":
                            progress[msg.message_id]["status"] = "indeterminate"
                            progress[msg.message_id]["interrupted_at"] = time.time()
                            await self._save_lifecycle(node, lifecycle)
                        result = {
                            "success": False,
                            "status": "indeterminate",
                            "error": "Execution was interrupted; its outcome is unknown and was not replayed.",
                            "agent_id": agent_id,
                        }
                        await store.send_message(
                            sender_id=agent_id,
                            receiver_id=msg.sender_id,
                            content={
                                "result": result,
                                "in_reply_to": msg.message_id,
                                "status": "indeterminate",
                            },
                            message_type="response",
                            correlation_id=msg.correlation_id,
                            message_id=f"agent-response-{msg.message_id}",
                        )
                        await store.ack_message(agent_id, msg.message_id)
                        progress[msg.message_id]["status"] = "indeterminate_delivered"
                        progress[msg.message_id].pop("result", None)
                        self._trim_message_progress(progress, store)
                        await self._save_lifecycle(node, lifecycle)
                        continue
                    else:
                        progress[msg.message_id] = {
                            "status": "running",
                            "started_at": time.time(),
                        }
                        await self._save_lifecycle(node, lifecycle)
                        result = await agent.execute(msg.content)
                        progress[msg.message_id].update({
                            "status": "completed",
                            "result": result,
                            "completed_at": time.time(),
                        })
                        await self._save_lifecycle(node, lifecycle)

                    await store.send_message(
                        sender_id=agent_id,
                        receiver_id=msg.sender_id,
                        content={"result": result, "in_reply_to": msg.message_id},
                        message_type="response",
                        correlation_id=msg.correlation_id,
                        message_id=f"agent-response-{msg.message_id}",
                    )
                    await store.ack_message(agent_id, msg.message_id)
                    progress[msg.message_id].pop("result", None)
                    self._trim_message_progress(progress, store)
                    await self._save_lifecycle(node, lifecycle)

        except asyncio.CancelledError:
            log.info("Agent %s cancelled", agent_id)
            if not claim_lost.is_set():
                await self._get_store().update_agent_status(agent_id, "stopped")
        except Exception as e:
            log.error("Agent %s error: %s", agent_id, e, exc_info=True)
            await self._get_store().update_agent_status(agent_id, "error")
        finally:
            if claim_heartbeat:
                claim_heartbeat.cancel()
                try:
                    await claim_heartbeat
                except asyncio.CancelledError:
                    pass
            if claim_token is not None:
                await self._release_execution_claim(agent_id, claim_token)
            node = await self._get_store().get_agent(agent_id)
            if not claim_lost.is_set() and node and node.status in ("spawned", "running"):
                await self._get_store().update_agent_status(agent_id, "idle")

    async def pause(self, agent_id: str) -> bool:
        """Pause an agent's execution (state persists)."""
        task = self._tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._get_store().update_agent_status(agent_id, "paused")
        log.info("Agent paused: %s", agent_id)
        return True

    @staticmethod
    def _trim_message_progress(progress: Dict[str, Any], store: Any) -> None:
        """Keep checkpoint history within the graph message board's retention bound."""
        limit = max(1, int(getattr(store, "_max_messages", 10000)))
        excess = len(progress) - limit
        if excess <= 0:
            return
        completed = sorted(
            (
                (entry.get("completed_at", entry.get("interrupted_at", 0)), message_id)
                for message_id, entry in progress.items()
                if entry.get("status") in (
                    "completed", "indeterminate", "indeterminate_delivered"
                )
            )
        )
        for _, message_id in completed[:excess]:
            progress.pop(message_id, None)

    async def resume(self, agent_id: str, owner_id: Optional[str] = None) -> bool:
        """Resume a paused or interrupted agent from its durable graph checkpoint."""
        async with self._resume_lock:
            store = self._get_store()
            node = await store.get_agent(agent_id)
            if node is None:
                return False
            if owner_id is not None and node.config.get("_owner_id") != str(owner_id):
                return False
            if node.status not in ("paused", "stopped", "spawned", "running", "error"):
                return False
            task = self._tasks.get(agent_id)
            if task is not None and not task.done():
                return False

            if not await self._launch_agent(agent_id):
                return False
            await store.update_agent_status(agent_id, "running")

        log.info("Agent resumed: %s", agent_id)
        return True

    async def terminate(self, agent_id: str) -> bool:
        """Terminate an agent permanently (state preserved for audit)."""
        task = self._tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._get_store().update_agent_status(agent_id, "terminated")
        self._agent_configs.pop(agent_id, None)
        self._tasks.pop(agent_id, None)
        log.info("Agent terminated: %s", agent_id)
        return True

    async def get_status(self) -> Dict[str, Any]:
        """Get the status of all managed agents."""
        store = self._get_store()
        graph_status = await store.graph_status()

        managed = {}
        for agent_id, config in self._agent_configs.items():
            task = self._tasks.get(agent_id)
            managed[agent_id] = {
                "name": config["name"],
                "role": config["role"],
                "status": "running" if (task and not task.done()) else "idle",
                "task_done": task.done() if task else None,
            }

        return {
            "graph": graph_status,
            "managed_agents": managed,
            "total_managed": len(managed),
        }

    async def shutdown(self) -> None:
        """Shut down all managed agents."""
        self._shutdown = True
        for agent_id in list(self._tasks.keys()):
            await self.terminate(agent_id)
        await self._get_store().disconnect()

    # -- inter-agent messaging ---------------------------------------------

    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: Dict[str, Any],
        message_type: str = "message",
        priority: int = 0,
    ) -> str:
        """Send a message between agents via the graph store's message board."""
        store = self._get_store()
        correlation_id = f"msg-{uuid.uuid4().hex[:8]}"
        return await store.send_message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            message_type=message_type,
            priority=priority,
            correlation_id=correlation_id,
        )

    async def get_messages(
        self,
        agent_id: str,
        limit: int = 100,
        unread_only: bool = False,
    ):
        store = self._get_store()
        return await store.get_messages(agent_id, limit, unread_only)


__all__ = ["AgentLifecycleManager"]
