"""Tests for the maintained authenticated voice API surface."""


def test_voice_status_reports_unconfigured_provider(client):
    response = client.get("/api/v1/voice/status")

    assert response.status_code == 200
    body = response.json()
    assert body["asr_status"] == "NOT_CONFIGURED"
    assert body["streaming_available"] is False
