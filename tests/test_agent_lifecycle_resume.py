import asyncio
import time

from jarvis_backend.agents.graph_store import AgentGraphStore, AgentMessage, AgentNode
from jarvis_backend.agents.lifecycle import AgentLifecycleManager, _persistable_request


class PersistentFakeGraphStore:
    """A graph store whose node/message state survives new manager instances."""

    def __init__(self):
        self.nodes = {}
        self.messages = {}
        self.claims = {}

    async def get_agent(self, agent_id):
        value = self.nodes.get(agent_id)
        return AgentNode.from_dict(value) if value else None

    async def save_agent(self, node):
        self.nodes[node.agent_id] = node.to_dict()
        return True

    async def update_agent_status(self, agent_id, status):
        node = await self.get_agent(agent_id)
        if node is None:
            return False
        node.status = status
        node.last_active = time.time()
        return await self.save_agent(node)

    async def send_message(
        self, sender_id, receiver_id, content, message_type="message",
        priority=0, correlation_id=None, message_id=None,
    ):
        messages = self.messages.setdefault(receiver_id, [])
        if message_id and any(msg.message_id == message_id for msg in messages):
            return message_id
        message_id = message_id or f"msg-{len(messages)}"
        messages.insert(0, AgentMessage(
            message_id=message_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content,
            correlation_id=correlation_id,
        ))
        return message_id

    async def get_messages(self, agent_id, limit=100, unread_only=False):
        messages = self.messages.get(agent_id, [])[:limit]
        return [msg for msg in messages if not unread_only or not msg.acknowledged]

    async def ack_message(self, agent_id, message_id):
        for msg in self.messages.get(agent_id, []):
            if msg.message_id == message_id:
                msg.acknowledged = True
                return True
        return False

    async def claim_agent_execution(self, agent_id, token, ttl=300):
        current = self.claims.get(agent_id)
        if current and current[1] > time.monotonic():
            return False
        self.claims[agent_id] = (token, time.monotonic() + ttl)
        return True

    async def renew_agent_execution(self, agent_id, token, ttl=300):
        current = self.claims.get(agent_id)
        if not current or current[0] != token:
            return False
        self.claims[agent_id] = (token, time.monotonic() + ttl)
        return True

    async def release_agent_execution(self, agent_id, token):
        current = self.claims.get(agent_id)
        if not current or current[0] != token:
            return False
        del self.claims[agent_id]
        return True


class FakeRedisClaims:
    def __init__(self):
        self.values = {}

    async def set(self, key, token, nx=False, ex=None):
        current = self.values.get(key)
        if current and current[1] > time.monotonic() and nx:
            return False
        self.values[key] = (token, time.monotonic() + ex)
        return True

    async def eval(self, script, key_count, key, token, *args):
        current = self.values.get(key)
        if not current or current[0] != token or current[1] <= time.monotonic():
            return 0
        if "expire" in script:
            self.values[key] = (token, time.monotonic() + int(args[0]))
            return 1
        del self.values[key]
        return 1


def _node(agent_id, owner_id, status, request_status, request):
    return AgentNode(
        agent_id=agent_id,
        name="Persisted agent",
        role="researcher",
        status=status,
        config={"_owner_id": owner_id},
        metadata={
            "lifecycle": {
                "version": 1,
                "initial_request": request,
                "initial_request_status": request_status,
                "initial_request_attempts": 0,
                "message_progress": {},
            }
        },
    )


def test_fresh_manager_resumes_interrupted_owned_agent_and_rejects_other_owner(monkeypatch):
    store = PersistentFakeGraphStore()
    own = _node("researcher-owned", "user-1", "running", "pending", {"query": "resume"})
    other = _node("researcher-other", "user-2", "running", "pending", {"query": "private"})
    store.nodes[own.agent_id] = own.to_dict()
    store.nodes[other.agent_id] = other.to_dict()
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(own.agent_id, owner_id="user-1")
        for _ in range(100):
            saved = await store.get_agent(own.agent_id)
            if saved.metadata["lifecycle"]["initial_request_status"] == "completed":
                break
            await asyncio.sleep(0.01)
        assert saved.metadata["lifecycle"]["initial_request_status"] == "completed"
        assert calls == [{"query": "resume"}]
        assert not await manager.resume(other.agent_id, owner_id="user-1")
        assert len(calls) == 1
        await manager.pause(own.agent_id)

    asyncio.run(scenario())


def test_concurrent_managers_share_execution_claim(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node(
        "researcher-concurrent", "user-1", "paused", "pending", {"query": "once"}
    )
    store.nodes[node.agent_id] = node.to_dict()
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            await asyncio.sleep(0.05)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        first = AgentLifecycleManager()
        second = AgentLifecycleManager()
        first._store = store
        second._store = store
        outcomes = await asyncio.gather(
            first.resume(node.agent_id, owner_id="user-1"),
            second.resume(node.agent_id, owner_id="user-1"),
        )
        assert sum(outcomes) == 1
        for _ in range(100):
            saved = await store.get_agent(node.agent_id)
            if saved.metadata["lifecycle"]["initial_request_status"] == "completed":
                break
            await asyncio.sleep(0.01)
        assert calls == [{"query": "once"}]
        winner = first if outcomes[0] else second
        await winner.pause(node.agent_id)

    asyncio.run(scenario())


def test_fresh_manager_does_not_replay_completed_initial_request(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node(
        "researcher-complete", "user-1", "paused", "completed", {"query": "already done"}
    )
    node.metadata["lifecycle"].update({
        "initial_result": {"success": True},
        "initial_result_delivery": "delivered",
    })
    store.nodes[node.agent_id] = node.to_dict()
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(node.agent_id, owner_id="user-1")
        await asyncio.sleep(0.05)
        assert calls == []
        await manager.pause(node.agent_id)

    asyncio.run(scenario())


def test_running_checkpoint_is_marked_indeterminate_instead_of_replayed(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node(
        "researcher-uncertain", "user-1", "running", "running", {"query": "possibly done"}
    )
    store.nodes[node.agent_id] = node.to_dict()
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(node.agent_id, owner_id="user-1")
        for _ in range(100):
            saved = await store.get_agent(node.agent_id)
            if saved.metadata["lifecycle"]["initial_request_status"] == "indeterminate":
                break
            await asyncio.sleep(0.01)
        assert saved.metadata["lifecycle"]["initial_request_status"] == "indeterminate"
        assert calls == []
        await manager.pause(node.agent_id)

    asyncio.run(scenario())


def test_indeterminate_initial_request_delivers_stable_result(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node(
        "researcher-initial-uncertain",
        "user-1",
        "running",
        "running",
        {"query": "possibly completed", "sender_id": "orchestrator:user-1"},
    )
    store.nodes[node.agent_id] = node.to_dict()
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(node.agent_id, owner_id="user-1")
        for _ in range(100):
            saved = await store.get_agent(node.agent_id)
            if saved.metadata["lifecycle"].get("initial_result_delivery") == "indeterminate_delivered":
                break
            await asyncio.sleep(0.01)
        inbox = await store.get_messages("orchestrator:user-1")
        assert len(inbox) == 1
        assert inbox[0].message_id == f"agent-initial-result-{node.agent_id}"
        assert inbox[0].content["status"] == "indeterminate"
        assert saved.metadata["lifecycle"].get("initial_request") is None
        assert calls == []
        await manager._deliver_indeterminate_initial(node.agent_id)
        assert len(await store.get_messages("orchestrator:user-1")) == 1
        await manager.pause(node.agent_id)

    asyncio.run(scenario())


def test_interrupted_message_delivers_indeterminate_response_before_ack(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node(
        "researcher-message-uncertain",
        "user-1",
        "running",
        "completed",
        {},
    )
    node.metadata["lifecycle"]["message_progress"]["msg-inflight"] = {
        "status": "running",
        "started_at": time.time(),
    }
    store.nodes[node.agent_id] = node.to_dict()
    incoming = AgentMessage(
        message_id="msg-inflight",
        sender_id="orchestrator:user-1",
        receiver_id=node.agent_id,
        message_type="task",
        content={"query": "possibly completed"},
        correlation_id="corr-inflight",
    )
    store.messages[node.agent_id] = [incoming]
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": True}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(node.agent_id, owner_id="user-1")
        for _ in range(100):
            responses = await store.get_messages("orchestrator:user-1")
            if responses:
                break
            await asyncio.sleep(0.01)
        assert len(responses) == 1
        assert responses[0].message_id == "agent-response-msg-inflight"
        assert responses[0].content["status"] == "indeterminate"
        assert incoming.acknowledged
        assert calls == []
        await manager.pause(node.agent_id)

    asyncio.run(scenario())


def test_completed_message_checkpoint_is_delivered_without_replay(monkeypatch):
    store = PersistentFakeGraphStore()
    node = _node("researcher-message-done", "user-1", "running", "completed", {})
    node.metadata["lifecycle"]["message_progress"]["msg-done"] = {
        "status": "completed",
        "result": {"success": True, "data": "cached"},
    }
    store.nodes[node.agent_id] = node.to_dict()
    incoming = AgentMessage(
        message_id="msg-done",
        sender_id="orchestrator:user-1",
        receiver_id=node.agent_id,
        message_type="task",
        content={"query": "already executed"},
        correlation_id="corr-done",
    )
    store.messages[node.agent_id] = [incoming]
    calls = []

    class FakeSpecialist:
        def __init__(self, **kwargs):
            pass

        async def execute(self, request):
            calls.append(request)
            return {"success": False}

    monkeypatch.setattr(
        "jarvis_backend.agents.specialist.SpecialistAgent", FakeSpecialist
    )

    async def scenario():
        manager = AgentLifecycleManager()
        manager._store = store
        assert await manager.resume(node.agent_id, owner_id="user-1")
        for _ in range(100):
            responses = await store.get_messages("orchestrator:user-1")
            if responses:
                break
            await asyncio.sleep(0.01)
        assert len(responses) == 1
        assert responses[0].message_id == "agent-response-msg-done"
        assert responses[0].content["result"] == {"success": True, "data": "cached"}
        assert incoming.acknowledged
        assert calls == []
        await manager.pause(node.agent_id)

    asyncio.run(scenario())


def test_request_credentials_are_not_saved_in_lifecycle_state():
    request = _persistable_request({
        "query": "research",
        "apiKey": "secret-value",
        "nested": {"refresh_token": "refresh-secret", "limit": 3},
    })

    assert request == {"query": "research", "nested": {"limit": 3}}


def test_graph_node_is_recovered_from_existing_kv_store(monkeypatch):
    class FakeKvStore:
        def __init__(self):
            self.data = {}

        def load(self):
            return self.data

        def save(self):
            pass

    persisted = FakeKvStore()
    monkeypatch.setattr(
        "jarvis_backend.core.get_store", lambda name: persisted
    )

    async def scenario():
        first_store = AgentGraphStore()
        agent_id = await first_store.create_agent(
            "Durable", "researcher", config={"_owner_id": "user-1"}
        )
        await first_store.save_agent(AgentNode(
            agent_id=agent_id,
            name="Durable",
            role="researcher",
            status="paused",
            config={"_owner_id": "user-1"},
            metadata={"lifecycle": {"initial_request_status": "pending"}},
        ))

        restarted_store = AgentGraphStore()
        node = await restarted_store.get_agent(agent_id)
        assert node.status == "paused"
        assert node.config["_owner_id"] == "user-1"
        assert node.metadata["lifecycle"]["initial_request_status"] == "pending"

    asyncio.run(scenario())


def test_redis_execution_claim_renews_and_releases_only_for_owner_token():
    async def scenario():
        store = AgentGraphStore()
        store._redis = FakeRedisClaims()
        assert await store.claim_agent_execution("agent-1", "owner-token", ttl=5)
        assert not await store.claim_agent_execution("agent-1", "other-token", ttl=5)
        assert not await store.renew_agent_execution("agent-1", "other-token", ttl=5)
        assert not await store.release_agent_execution("agent-1", "other-token")
        assert await store.renew_agent_execution("agent-1", "owner-token", ttl=5)
        assert await store.release_agent_execution("agent-1", "owner-token")
        assert await store.claim_agent_execution("agent-1", "next-token", ttl=5)
        key = store._key("agent:execution", "agent-1")
        store._redis.values[key] = ("expired-token", time.monotonic() - 1)
        assert await store.claim_agent_execution("agent-1", "after-expiry", ttl=5)

    asyncio.run(scenario())
