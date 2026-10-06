from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "deployment"
    / "production"
    / "public_urls.py"
)
SPEC = importlib.util.spec_from_file_location("production_public_urls", MODULE_PATH)
assert SPEC and SPEC.loader
public_urls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public_urls)


def test_public_urls_derive_https_origin_and_standard_routes():
    urls = public_urls.derive_public_urls({"JARVIS_DOMAIN": "jarvis.example.com"})

    assert urls == {
        "JARVIS_PUBLIC_ORIGIN": "https://jarvis.example.com",
        "PUBLIC_BASE_URL": "https://jarvis.example.com/",
        "API_BASE_URL": "https://jarvis.example.com/api",
        "WS_BASE_URL": "wss://jarvis.example.com/ws",
        "JARVIS_CADDY_BASE_PATH": "",
        "JARVIS_CADDY_BASE_PATH_REGEX": "",
        "JARVIS_FRONTEND_BASE_PATH": "/",
    }


def test_public_urls_preserve_domain_port_and_path_configuration():
    urls = public_urls.derive_public_urls(
        {
            "JARVIS_DOMAIN": "jarvis.example.com",
            "JARVIS_PUBLIC_PORT": "8443",
            "JARVIS_BASE_PATH": "/app/",
            "JARVIS_API_PATH": "/v2/api",
            "JARVIS_WS_PATH": "/realtime",
        }
    )

    assert urls["PUBLIC_BASE_URL"] == "https://jarvis.example.com:8443/app/"
    assert urls["API_BASE_URL"] == "https://jarvis.example.com:8443/app/v2/api"
    assert urls["WS_BASE_URL"] == "wss://jarvis.example.com:8443/app/realtime"
    assert urls["JARVIS_CADDY_BASE_PATH"] == "/app"
    assert urls["JARVIS_CADDY_BASE_PATH_REGEX"] == "/app"
    assert urls["JARVIS_FRONTEND_BASE_PATH"] == "/app"


def test_caddy_base_path_regex_is_escaped():
    urls = public_urls.derive_public_urls(
        {"JARVIS_DOMAIN": "jarvis.example.com", "JARVIS_BASE_PATH": "/app.v1"}
    )

    assert urls["JARVIS_CADDY_BASE_PATH_REGEX"] == r"/app\.v1"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({}, "JARVIS_DOMAIN"),
        ({"JARVIS_DOMAIN": "https://jarvis.example.com"}, "JARVIS_DOMAIN"),
        (
            {"JARVIS_DOMAIN": "jarvis.example.com", "JARVIS_SCHEME": "http"},
            "https",
        ),
        (
            {
                "JARVIS_DOMAIN": "jarvis.example.com",
                "JARVIS_PUBLIC_PORT": "8443",
                "JARVIS_SCHEME": "https",
            },
            "443",
        ),
        (
            {
                "JARVIS_DOMAIN": "jarvis.example.com",
                "JARVIS_HTTP_PORT": "8080",
            },
            "HTTP_PORT=80",
        ),
        (
            {"JARVIS_DOMAIN": "jarvis.example.com", "JARVIS_BASE_PATH": "/../app"},
            "dot segments",
        ),
    ],
)
def test_public_urls_reject_invalid_production_configuration(values, message):
    with pytest.raises(ValueError, match=message):
        public_urls.derive_public_urls(values, production=True)


def test_cli_reports_missing_domain_without_emitting_shell_exports(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_SCHEME=https\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--env-file",
            str(env_file),
            "--shell",
            "--production",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "DOMAIN_REQUIRED" in result.stderr
