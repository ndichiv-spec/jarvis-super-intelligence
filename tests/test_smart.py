"""Opt-in integration check for the historical standalone chat service."""

import pytest
import requests


pytestmark = pytest.mark.integration


def test_legacy_chat_service_returns_response(legacy_service_base_url):
    response = requests.post(
        f"{legacy_service_base_url}/api/chat",
        json={"message": "hello"},
        timeout=10,
    )

    assert response.status_code == 200
    assert isinstance(response.json().get("response"), str)
