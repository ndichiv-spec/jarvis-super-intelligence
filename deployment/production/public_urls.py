#!/usr/bin/env python3
"""Derive public JARVIS URLs from the deployment environment file."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def normalize_path(value: str, name: str) -> str:
    if not value:
        value = "/"
    if "?" in value or "#" in value or "\\" in value:
        raise ValueError(f"{name} must be a URL path without query, fragment, or backslash.")
    segments = [segment for segment in value.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError(f"{name} cannot contain dot segments.")
    encoded = "/".join(quote(segment, safe="-._~!$&'()*+,;=:@%") for segment in segments)
    return f"/{encoded}" if encoded else "/"


def join_path(*paths: str) -> str:
    segments: list[str] = []
    for path in paths:
        segments.extend(part for part in path.split("/") if part)
    return "/" + "/".join(segments) if segments else "/"


def derive_public_urls(
    values: dict[str, str], *, production: bool = False
) -> dict[str, str]:
    domain = values.get("JARVIS_DOMAIN", "").strip()
    if not domain or any(character in domain for character in "/@?#"):
        raise ValueError("Set JARVIS_DOMAIN to a DNS hostname without scheme, port, or path.")

    scheme = values.get("JARVIS_SCHEME", "https").strip().lower()
    if scheme not in {"http", "https"}:
        raise ValueError("JARVIS_SCHEME must be http or https.")

    parsed_domain = urlsplit(f"{scheme}://{domain}")
    if (
        parsed_domain.hostname is None
        or parsed_domain.username is not None
        or parsed_domain.password is not None
        or parsed_domain.port is not None
        or parsed_domain.path
    ):
        raise ValueError("JARVIS_DOMAIN must contain only a hostname; configure port separately.")
    hostname = parsed_domain.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if (
        len(hostname) > 253
        or "." not in hostname
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in hostname.split(".")
        )
    ):
        raise ValueError("JARVIS_DOMAIN must be a valid fully-qualified DNS hostname.")
    port_text = values.get("JARVIS_PUBLIC_PORT", "").strip()
    port = int(port_text) if port_text else 443
    if not 1 <= port <= 65535:
        raise ValueError("JARVIS_PUBLIC_PORT must be between 1 and 65535.")
    http_port_text = values.get("JARVIS_HTTP_PORT", "").strip()
    http_port = int(http_port_text) if http_port_text else 80
    if not 1 <= http_port <= 65535:
        raise ValueError("JARVIS_HTTP_PORT must be between 1 and 65535.")
    if production and (scheme != "https" or port != 443 or http_port != 80):
        raise ValueError(
            "Automatic public TLS requires JARVIS_SCHEME=https and "
            "JARVIS_PUBLIC_PORT=443 with JARVIS_HTTP_PORT=80."
        )

    base_path = normalize_path(values.get("JARVIS_BASE_PATH", "/"), "JARVIS_BASE_PATH")
    api_path = normalize_path(values.get("JARVIS_API_PATH", "/api"), "JARVIS_API_PATH")
    ws_path = normalize_path(values.get("JARVIS_WS_PATH", "/ws"), "JARVIS_WS_PATH")
    if production and (api_path != "/api" or ws_path != "/ws"):
        raise ValueError(
            "This application currently requires JARVIS_API_PATH=/api and "
            "JARVIS_WS_PATH=/ws."
        )
    default_port = 443 if scheme == "https" else 80
    authority = hostname if port == default_port else f"{hostname}:{port}"
    origin = urlunsplit((scheme, authority, "", "", "")).rstrip("/")
    public_path = "" if base_path == "/" else base_path
    public_base_url = f"{origin}{public_path}/"
    api_base_url = f"{origin}{join_path(base_path, api_path)}"
    ws_scheme = "wss" if scheme == "https" else "ws"
    ws_base_url = urlunsplit((ws_scheme, authority, join_path(base_path, ws_path), "", ""))

    return {
        "JARVIS_PUBLIC_ORIGIN": origin,
        "PUBLIC_BASE_URL": public_base_url,
        "API_BASE_URL": api_base_url,
        "WS_BASE_URL": ws_base_url,
        "JARVIS_CADDY_BASE_PATH": "" if base_path == "/" else base_path,
        "JARVIS_CADDY_BASE_PATH_REGEX": re.escape(
            "" if base_path == "/" else base_path
        ),
        "JARVIS_FRONTEND_BASE_PATH": base_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--shell", action="store_true", help="Print safely quoted shell exports.")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    values = read_env_file(args.env_file)
    if not values.get("JARVIS_DOMAIN", "").strip():
        print("DOMAIN_REQUIRED: Set JARVIS_DOMAIN to a hostname you control.", file=sys.stderr)
        raise SystemExit(2)
    try:
        derived = derive_public_urls(values, production=args.production)
    except ValueError as error:
        print(f"INVALID_PUBLIC_URL_CONFIGURATION: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    if args.shell:
        for key, value in derived.items():
            print(f"export {key}={shlex.quote(value)}")
    else:
        for key, value in derived.items():
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
