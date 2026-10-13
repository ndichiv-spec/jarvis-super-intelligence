"""Opt-in single-request smoke test for a deployed JARVIS image path.

Required environment:
  JARVIS_LIVE_IMAGE_OPT_IN=1
  JARVIS_LIVE_IMAGE_PROVIDER=openai|replicate|stability
  JARVIS_LIVE_BASE_URL=https://the-configured-staging-host
  JARVIS_LIVE_AUTH_TOKEN=<short-lived token for a dedicated test user>
  JARVIS_LIVE_SMOKE_RESULT_FILE=<new path outside the repository>

The selected provider must also be configured server-side as
JARVIS_IMAGE_PROVIDER. This script makes one chat request and performs an
idempotent replay with the same request id; it never retries a failed request.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

SUPPORTED_PROVIDERS = {"openai", "replicate", "stability"}
PROMPT = "A small blue geometric cube on a plain white background."


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Required environment variable is missing: {name}")
    return value


def _check_response(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise SystemExit(f"{label} failed with HTTP {response.status_code}; no retry attempted")


def _verify_image(content_type: str, content: bytes) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def main() -> int:
    if os.environ.get("JARVIS_LIVE_IMAGE_OPT_IN") != "1":
        raise SystemExit(
            "Live test is disabled. Set JARVIS_LIVE_IMAGE_OPT_IN=1 only "
            "after approving one paid provider request."
        )
    provider = _required("JARVIS_LIVE_IMAGE_PROVIDER").lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise SystemExit("JARVIS_LIVE_IMAGE_PROVIDER must be openai, replicate, or stability")

    base_url = _required("JARVIS_LIVE_BASE_URL").rstrip("/")
    parsed_base = urlsplit(base_url)
    if (
        parsed_base.scheme != "https"
        and parsed_base.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise SystemExit("Live smoke tests require HTTPS except on loopback.")
    if not parsed_base.netloc or parsed_base.username or parsed_base.password:
        raise SystemExit("JARVIS_LIVE_BASE_URL must be an origin without embedded credentials.")

    token = _required("JARVIS_LIVE_AUTH_TOKEN")
    result_path = Path(_required("JARVIS_LIVE_SMOKE_RESULT_FILE")).expanduser()
    result_path = result_path.resolve()
    repository = Path(__file__).resolve().parents[1]
    if result_path.is_relative_to(repository):
        raise SystemExit("Smoke result must be written outside the repository.")
    if result_path.exists():
        raise SystemExit("Result file already exists; choose a new path to avoid overwriting data.")
    if not result_path.parent.is_dir():
        raise SystemExit("Result file parent directory must already exist.")

    request_id = str(uuid4())
    conversation_id = str(uuid4())
    request = {
        "session_id": conversation_id,
        "client_message_id": request_id,
        "message": f"Generate an image: {PROMPT}",
    }
    headers = {"Authorization": f"Bearer {token}"}
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "status": "failed",
        "correlation": {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "command_id": None,
            "execution_id": None,
        },
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0), follow_redirects=False) as client:
            status_response = client.get(
                f"{base_url}/api/v1/image/providers",
                headers=headers,
            )
            _check_response(status_response, 200, "Provider readiness check")
            status = status_response.json()
            provider_status = (status.get("providers") or {}).get(provider) or {}
            if (
                status.get("selection_mode") != "explicit"
                or status.get("selected_provider") != provider
                or not provider_status.get("selected")
                or not provider_status.get("configured")
                or provider_status.get("availability") != "configured_unverified"
            ):
                raise SystemExit(
                    "Selected provider is not explicitly configured and ready for a smoke attempt."
                )
            record["server_credential_configured"] = True

            chat_response = client.post(
                f"{base_url}/api/chat",
                headers=headers,
                json=request,
            )
            _check_response(chat_response, 200, "Authenticated conversation request")
            reply = chat_response.json()
            command_id = reply.get("runtime_command_id")
            presentation = reply.get("presentation") or {}
            correlation = presentation.get("correlation") or {}
            record["correlation"].update({
                "command_id": command_id,
                "execution_id": correlation.get("execution_id"),
            })
            if (
                reply.get("status") != "COMPLETED"
                or not command_id
                or correlation.get("request_id") != request_id
                or correlation.get("conversation_id") != conversation_id
                or correlation.get("command_id") != command_id
                or not correlation.get("execution_id")
                or presentation.get("contract_version") != "1.1"
                or presentation.get("task_state", {}).get("status") != "completed"
            ):
                raise SystemExit("Conversation did not present a correlated completed result.")

            command_response = client.get(
                f"{base_url}/api/v1/commands/{command_id}",
                headers=headers,
            )
            _check_response(command_response, 200, "Owner-scoped command read")
            command = command_response.json()
            if command.get("selected_capability_id") != "image.generate":
                raise SystemExit("Conversation did not execute image.generate.")
            events_response = client.get(
                f"{base_url}/api/v1/commands/{command_id}/events",
                headers=headers,
            )
            _check_response(events_response, 200, "Owner-scoped execution event read")
            events = events_response.json().get("events") or []
            event_names = [
                event.get("type") or event.get("event") or event.get("event_type")
                for event in events
            ]
            if (
                "world.execution.selected" not in event_names
                or "world.execution.completed" not in event_names
                or "world.result.observed" not in event_names
            ):
                raise SystemExit("Durable execution lifecycle evidence is incomplete.")
            record["durable_execution_events"] = True

            image_items = [
                item
                for component in presentation.get("components", [])
                if component.get("type") == "media.image_gallery"
                for item in component.get("items", [])
            ]
            media_refs = presentation.get("media_refs") or []
            if not image_items or not media_refs or image_items[0].get("provider") != provider:
                raise SystemExit("Presentation did not contain the requested provider's image.")
            media_ref = media_refs[0]
            media_url = media_ref.get("url")
            media_path = urlsplit(media_url or "")
            if not media_path.path.startswith("/api/v1/media/") or media_path.netloc:
                raise SystemExit("Presentation contained an invalid media reference URL.")
            media_response = client.get(f"{base_url}{media_url}")
            _check_response(media_response, 200, "Authorized media retrieval")
            content_type = media_response.headers.get("content-type", "").split(";", 1)[0].lower()
            if (
                content_type != media_ref.get("content_type")
                or not _verify_image(content_type, media_response.content)
            ):
                raise SystemExit("Stored media failed content type or image signature validation.")

            revisions_response = client.get(
                f"{base_url}/api/v1/presentations/{command_id}/revisions",
                headers=headers,
            )
            _check_response(revisions_response, 200, "Owner-scoped presentation revision read")
            revisions = revisions_response.json().get("revisions") or []
            if not any(
                item.get("presentation", {}).get("presentation_id")
                == presentation.get("presentation_id")
                for item in revisions
            ):
                raise SystemExit("Presented result was not persisted as a conversation revision.")

            replay_response = client.post(
                f"{base_url}/api/chat",
                headers=headers,
                json=request,
            )
            _check_response(replay_response, 200, "Idempotent conversation replay")
            replay = replay_response.json()
            if (
                replay.get("resumed") is not True
                or replay.get("runtime_command_id") != command_id
            ):
                raise SystemExit("Conversation replay did not resume the original execution.")

            record.update({
                "status": "passed",
                "presentation_contract": "1.1",
                "media": {
                    "validated": True,
                    "content_type": content_type,
                    "bytes": len(media_response.content),
                },
                "revision_persisted": True,
                "idempotent_replay": True,
            })
    except httpx.RequestError:
        record["failure"] = "network_request_failed"
        raise SystemExit("Live smoke request failed at the network layer; no retry attempted.")
    finally:
        if not result_path.exists():
            with result_path.open("x", encoding="utf-8") as result_file:
                result_file.write(json.dumps(record, indent=2, sort_keys=True) + "\n")

    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
