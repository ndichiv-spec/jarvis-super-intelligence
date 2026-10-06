import json

import pytest

from config.settings import Settings
from core import MissionRequest
from core.engine import JarvisEngine, create_engine
from services import LLMReply, LLMService, data_hub


class _FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _RecordingLLMService(LLMService):
    backend_name = "recording"
    model_name = "recording-test-model"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_reply(self, messages, system_prompt, draft_answer) -> LLMReply:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "draft_answer": draft_answer,
            }
        )
        return LLMReply(
            content=f"recorded::{draft_answer}",
            metadata={"backend": self.backend_name, "model": self.model_name},
        )


def _build_settings(tmp_path) -> Settings:
    return Settings.from_env().with_overrides(
        feedback_store_path=str(tmp_path / "feedback.jsonl"),
        audit_log_path=str(tmp_path / "audit.jsonl"),
        llm_backend="heuristic",
        llm_model="nexus-heuristic",
    )


def test_system_module_handles_status(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path))

    response = engine.ask("status")

    assert response.source == "system"
    assert "nominal" in response.content.lower()
    assert response.history_size == 2
    assert response.synthesis is not None
    assert response.synthesis.backend == "module"


def test_general_request_routes_through_nexus_mission_engine(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path))

    response = engine.ask("explain quantum foam")

    assert response.source == "general"
    assert response.mission_type == "general"
    assert "nexus general intelligence" in response.content.lower()
    assert response.synthesis is not None
    assert response.synthesis.backend == "heuristic"
    assert response.synthesis.profile == "general"


def test_engine_retrieves_relevant_history_for_synthesis(tmp_path) -> None:
    llm_service = _RecordingLLMService()
    engine = JarvisEngine(
        settings=_build_settings(tmp_path).with_overrides(llm_backend="ollama"),
        llm_service=llm_service,
    )

    engine.ask("We are tracking Nairobi climate indicators for a dashboard", session_id="mission")
    engine.ask("Keep the Nairobi air-quality focus in the plan", session_id="mission")

    mission = engine.execute_mission(
        MissionRequest(
            objective="Summarize the Nairobi climate mission",
            session_id="mission",
            use_live_data=False,
        )
    )

    assert mission.answer.startswith("recorded::")
    assert mission.synthesis.backend == "recording"
    assert mission.synthesis.profile == "geospatial"
    assert mission.synthesis.retrieved_turns >= 1
    memory_message = next(
        (
            message.content
            for message in llm_service.calls[-1]["messages"]
            if "Relevant recent memory:" in message.content
        ),
        "",
    )
    assert "Nairobi" in memory_message


def test_earth_observation_mission_extracts_location_context(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path))

    mission = engine.execute_mission(
        MissionRequest(
            objective="Analyze satellite imagery options for climate monitoring over Nairobi",
            use_live_data=False,
        )
    )

    provider_names = {provider.name for provider in mission.provider_statuses}
    assert mission.mission_type == "earth_observation"
    assert mission.context.location is not None
    assert mission.context.location.query == "Nairobi"
    assert "open-meteo" in provider_names
    assert "nasa-epic" in provider_names
    assert "sentinel-hub" in provider_names


def test_earth_observation_mission_fetches_live_climate_context(monkeypatch, tmp_path) -> None:
    def fake_urlopen(url: str, timeout: int = 8) -> _FakeHttpResponse:
        _ = timeout
        if "geocoding-api.open-meteo.com" in url:
            payload = {
                "results": [
                    {
                        "name": "Nairobi",
                        "country": "Kenya",
                        "latitude": -1.286389,
                        "longitude": 36.817223,
                        "timezone": "Africa/Nairobi",
                    }
                ]
            }
            return _FakeHttpResponse(json.dumps(payload).encode("utf-8"))
        if "api.open-meteo.com/v1/forecast" in url:
            payload = {
                "current": {
                    "temperature_2m": 24.1,
                    "relative_humidity_2m": 62,
                    "cloud_cover": 48,
                    "wind_speed_10m": 11.4,
                }
            }
            return _FakeHttpResponse(json.dumps(payload).encode("utf-8"))
        if "air-quality-api.open-meteo.com" in url:
            payload = {
                "current": {
                    "european_aqi": 37,
                    "pm2_5": 11.2,
                    "pm10": 19.4,
                    "carbon_monoxide": 240.0,
                    "nitrogen_dioxide": 12.1,
                    "ozone": 81.4,
                }
            }
            return _FakeHttpResponse(json.dumps(payload).encode("utf-8"))
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(data_hub, "urlopen", fake_urlopen)
    settings = _build_settings(tmp_path).with_overrides(allow_nasa_demo_key=False)
    engine = create_engine(settings)

    mission = engine.execute_mission(
        MissionRequest(
            objective="What are the current climate conditions over Nairobi?",
            use_live_data=True,
        )
    )

    open_meteo_usage = next(
        usage for usage in mission.provider_usages if usage.provider_name == "open-meteo"
    )

    assert mission.context.location is not None
    assert mission.context.location.label == "Nairobi, Kenya"
    assert open_meteo_usage.live_data_used is True
    assert "live weather and air-quality context" in open_meteo_usage.summary.lower()
    assert any("AQI" in finding for finding in open_meteo_usage.findings)


def test_engine_falls_back_to_heuristic_when_backend_is_misconfigured(tmp_path) -> None:
    settings = _build_settings(tmp_path).with_overrides(llm_backend="openai-compatible")

    engine = create_engine(settings)
    mission = engine.execute_mission(MissionRequest(objective="Explain the architecture"))

    assert mission.synthesis.backend == "heuristic"
    assert mission.synthesis.fallback_used is True
    assert mission.synthesis.warnings
    assert any("OPENAI_API_KEY" in warning for warning in mission.synthesis.warnings)


def test_engine_allows_profile_override(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path).with_overrides(llm_backend="ollama"))

    mission = engine.execute_mission(
        MissionRequest(
            objective="Design an interactive systems programming tutorial",
            mission_type="education",
            model_profile="coding",
        )
    )

    assert mission.synthesis.profile == "coding"


def test_engine_exposes_session_snapshot_and_summary(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path))

    engine.ask("status", session_id="jarvis-chat")
    engine.ask("Design a lesson plan for Python fundamentals", session_id="jarvis-chat")

    snapshot = engine.session_snapshot("jarvis-chat")
    summary = engine.summarize_session("jarvis-chat")

    assert snapshot.session_id == "jarvis-chat"
    assert snapshot.turn_count == 4
    assert snapshot.last_user_message == "Design a lesson plan for Python fundamentals"
    assert "system" in snapshot.sources
    assert "education" in snapshot.mission_types
    assert summary.turn_count == 4
    assert summary.suggested_profile == "education"
    assert "lesson" in summary.summary.lower()
    assert summary.key_topics


def test_engine_can_clear_a_session(tmp_path) -> None:
    engine = create_engine(_build_settings(tmp_path))

    engine.ask("status", session_id="volatile")
    cleared = engine.clear_session("volatile")

    assert cleared.turn_count == 2
    assert not engine.list_sessions()
    with pytest.raises(KeyError):
        engine.session_snapshot("volatile")
