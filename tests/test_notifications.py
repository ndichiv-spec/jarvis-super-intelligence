from __future__ import annotations

import pytest

from jarvis_backend.notifications import record_notification
from jarvis_backend.routers import notifications


class FakeStore:
    def __init__(self):
        self.value = {}

    def load(self):
        return self.value

    def save(self):
        pass


@pytest.mark.asyncio
async def test_notifications_are_user_scoped_and_read_state_persists(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("jarvis_backend.notifications.get_store", lambda name: store)
    monkeypatch.setattr("jarvis_backend.routers.notifications.get_store", lambda name: store)

    entry = record_notification("alice", "Task completed", "Research task completed.", "agents")
    record_notification("bob", "Connected", "Mailbox connected.", "connections")

    alice = await notifications.list_notifications(limit=50, user={"id": "alice"})
    assert [item["id"] for item in alice["notifications"]] == [entry["id"]]
    assert alice["notifications"][0]["read"] is False

    marked = await notifications.mark_notification_read(entry["id"], user={"id": "alice"})
    assert marked["success"] is True
    refreshed = await notifications.list_notifications(limit=50, user={"id": "alice"})
    assert refreshed["notifications"][0]["read"] is True

    bob = await notifications.list_notifications(limit=50, user={"id": "bob"})
    assert len(bob["notifications"]) == 1
    assert bob["notifications"][0]["id"] != entry["id"]


@pytest.mark.asyncio
async def test_mark_all_notifications_read_is_user_scoped(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("jarvis_backend.notifications.get_store", lambda name: store)
    monkeypatch.setattr("jarvis_backend.routers.notifications.get_store", lambda name: store)
    record_notification("alice", "One", "First.", "agents")
    record_notification("alice", "Two", "Second.", "agents")
    record_notification("bob", "Other", "Private.", "connections")

    result = await notifications.mark_all_notifications_read(user={"id": "alice"})

    assert result == {"success": True, "count": 2}
    assert all(item["read"] for item in store.value["alice"])
    assert all(not item["read"] for item in store.value["bob"])
