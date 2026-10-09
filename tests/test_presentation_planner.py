from datetime import UTC, datetime

from jarvis_backend.presentation.planner import PresentationPlanner


class StubContextService:
    def __init__(self, client):
        self.client = client

    def build(self, user_id, session_id, *, recent_events=None):
        return {
            "user": {"id": user_id, "profile": {}},
            "session": {"id": session_id, "message_count": 4},
            "conversation": {"recent_messages": [], "last_user_message": ""},
            "device": self.client,
            "active_capabilities": ["tool", "browser", "web.search"],
            "active_tasks": [],
            "recent_events": recent_events or [],
            "environment": "conversation",
            "selected": [],
            "accessibility": {},
            "preferences": {
                "density": "balanced",
                "visual_preference": "normal",
                "voice_preference": "minimal",
                "avatar_preference": "minimal",
                "technical_detail": "standard",
            },
        }


def _client():
    return {
        "clientId": "web-instance",
        "surfaces": ["web"],
        "environments": ["conversation", "research", "observability"],
        "primitives": ["text", "timeline", "avatar", "status"],
        "media": [],
        "spatial": [],
        "input": ["text"],
        "output": ["text"],
    }


def test_planner_uses_completed_runtime_evidence_for_environment_and_composition():
    planner = PresentationPlanner(context_service=StubContextService(_client()))
    result = planner.plan(
        "user-1",
        "session-1",
        "Search for current guidance.",
        "I found two relevant sources.",
        request_id="request-1",
        status="COMPLETED",
        runtime_events=[{
            "event_id": "event-1",
            "event_type": "capability_action_completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "capability_id": "web.search",
            "action": "search",
            "status": "completed",
            "message": "Search completed.",
        }],
        tool_calls=[{
            "name": "browser.search",
            "status": "completed",
            "result": {"source_count": 2},
        }],
    )

    intent = result["envelope"]["intent"]
    assert intent["environment"]["type"] == "research"
    assert intent["environment"]["state"]["source"] == "observed_runtime"
    assert result["plan"]["primaryEnvironment"] == "research"
    assert [event["type"] for event in result["events"]] == ["created", "updated"]


def test_planner_does_not_infer_location_environment_without_authorized_execution_evidence():
    planner = PresentationPlanner(context_service=StubContextService(_client()))
    result = planner.plan(
        "user-2",
        "session-2",
        "Where am I?",
        "I cannot access your location yet.",
        request_id="request-2",
        status="COMPLETED",
        runtime_events=[{
            "event_type": "location.failed",
            "status": "failed",
            "message": "Location permission was not granted.",
        }],
    )

    assert result["envelope"]["intent"]["environment"]["type"] == "conversation"
    assert "location" not in result["envelope"]["security"]["capabilities"]


def test_planner_keeps_failed_chat_in_conversation_and_reports_alert_state():
    planner = PresentationPlanner(context_service=StubContextService(_client()))
    result = planner.plan(
        "user-3",
        "session-3",
        "Search for current guidance.",
        "",
        request_id="request-3",
        status="FAILED",
        runtime_events=[{
            "event_type": "capability_action_completed",
            "capability_id": "web.search",
            "status": "completed",
        }],
    )

    assert result["envelope"]["intent"]["environment"]["type"] == "conversation"
    assert result["envelope"]["intent"]["assistant"]["state"] == "alert"
