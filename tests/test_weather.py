"""Opt-in integration check for the historical standalone weather service."""

import pytest
import requests


pytestmark = pytest.mark.integration


def test_legacy_weather_service_returns_json(legacy_service_base_url):
    response = requests.get(
        f"{legacy_service_base_url}/api/web/weather",
        timeout=30,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
