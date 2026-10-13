from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


PLATFORM_ROOT = Path(__file__).resolve().parents[1]


def test_backend_runs_and_reports_health_without_node_or_next(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    env = {
        key: value
        for key, value in os.environ.items()
        if not re.search(r"(?:API_KEY|API_TOKEN|_TOKEN|_ENDPOINT)$", key)
    }
    env.update({
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'runtime.db').as_posix()}",
        "JARVIS_SECRET_KEY": "runtime-independent-test-secret-0123456789",
        "JARVIS_ADMIN_PASSWORD": "runtime-independent-test-password",
        "JARVIS_TEST_MODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
    })
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "jarvis_backend.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--workers", "1",
        ],
        cwd=PLATFORM_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        health_status = None
        health_body = None
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(
                    f"{base_url}/health/live", timeout=1,
                ) as health:
                    health_status = health.status
                    health_body = health.read()
                    break
            except (OSError, TimeoutError):
                time.sleep(0.1)

        assert process.poll() is None, "standalone backend exited before health became available"
        assert health_status is not None, "standalone backend did not serve its health endpoint"
        assert health_status == 200
        assert b'"status":"alive"' in health_body
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_versioned_chat_requires_authentication(client):
    response = client.post(
        "/api/v1/chat",
        json={"message": "Find a public resource."},
    )

    assert response.status_code == 401


def test_world_research_finishes_after_stream_consumer_disconnects(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend.chat_service import chat_service
    from jarvis_backend.core import get_store
    from jarvis_backend.presentation_contract import build_conversation_presentation
    from jarvis_backend.runtime import ExecutionState, runtime

    async def exercise_disconnect():
        started = asyncio.Event()
        release = asyncio.Event()
        user = get_store("users").load()["testuser"]
        session_id = "disconnect-proof-conversation"
        client_message_id = "disconnect-proof-request"
        message = (
            "Research recent battery advances, consult the configured AI systems "
            "independently, compare their conclusions, and prepare a sourced report."
        )
        chat_service.create_session(user["id"], session_id)

        async def execute_fixture(
            content, model, user_id, current_session_id, *, request_id, principal,
        ):
            assert content == message
            assert principal["id"] == user_id
            command_id = "disconnect-proof-command"
            execution = runtime.create_execution(
                command_id=command_id,
                user_id=user_id,
            )
            assert runtime.claim_execution(
                execution["execution_id"], worker_id="fixture-worker",
            )
            runtime.transition(
                execution["execution_id"], ExecutionState.STARTING,
                worker_id="fixture-worker",
            )
            runtime.transition(
                execution["execution_id"], ExecutionState.RUNNING,
                worker_id="fixture-worker",
            )
            commands_store = get_store("commands")
            commands = commands_store.load()
            commands[command_id] = {
                "command_id": command_id,
                "user_id": user_id,
                "conversation_id": current_session_id,
                "request_id": request_id,
                "status": "EXECUTING",
            }
            commands_store.save()
            started.set()
            await release.wait()
            runtime.transition(
                execution["execution_id"], ExecutionState.VERIFYING,
                worker_id="fixture-worker",
                result={"verified": True},
            )
            runtime.transition(
                execution["execution_id"], ExecutionState.SUCCEEDED,
                worker_id="fixture-worker",
                result={"verified": True},
            )
            commands = commands_store.load()
            commands[command_id]["status"] = "COMPLETED"
            commands_store.save()
            return {
                "message": "I found one observed public report.",
                "status": "COMPLETED",
                "sources": ["https://example.org/report"],
                "runtime_command_id": command_id,
                "presentation": build_conversation_presentation(
                    "I found one observed public report.",
                    request_id=request_id,
                    session_id=current_session_id,
                    conversation_id=current_session_id,
                ),
            }

        monkeypatch.setattr(chat_service, "_generate", execute_fixture)
        stream = chat_service.stream_message(
            user["id"], session_id, message,
            client_message_id=client_message_id,
            principal=user,
        )
        metadata = await anext(stream)
        assert metadata["type"] == "meta"
        consumer = asyncio.create_task(anext(stream))
        await asyncio.wait_for(started.wait(), timeout=5)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

        session = chat_service.get_session(user["id"], session_id)
        assistant = session["messages"][-1]
        background_job = chat_service._world_turn_jobs.get(assistant["id"])
        assert background_job is not None
        assert not background_job.cancelled()
        assert assistant["status"] == "STREAMING"
        assert get_store("commands").load()["disconnect-proof-command"]["status"] == (
            "EXECUTING"
        )

        release.set()
        await asyncio.wait_for(asyncio.shield(background_job), timeout=20)
        finished = chat_service.get_session(user["id"], session_id)["messages"][-1]
        assert finished["status"] == "COMPLETED"
        assert finished["runtime_command_id"] == "disconnect-proof-command"
        assert get_store("commands").load()["disconnect-proof-command"]["status"] == (
            "COMPLETED"
        )
        executions = runtime.list_executions(user_id=user["id"])
        assert next(
            record for record in executions
            if record["command_id"] == "disconnect-proof-command"
        )["status"] == "SUCCEEDED"

        resumed = chat_service.stream_message(
            user["id"], session_id, message,
            client_message_id=client_message_id,
            principal=user,
        )
        replay = await anext(resumed)
        assert replay["type"] == "complete"
        assert replay["resumed"] is True
        assert replay["runtime_command_id"] == "disconnect-proof-command"
        await resumed.aclose()

    asyncio.run(exercise_disconnect())
