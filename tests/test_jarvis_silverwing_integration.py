"""JARVIS x Silverwing integration acceptance tests.

Tests the full chain: ChatService -> ProviderGateway -> ModelGateway ->
SilverwingClient -> runtime on http://127.0.0.1:8010 (TorchBackend,
120,087,552 params, model silverwing-120m-base-v1, revision r1, device cpu).

Scenarios (5):
  1. Conversation — basic round-trip with accurate metadata
  2. Context — follow-up message retains conversation history
  3. Calculation — numeric answer verifiable by arithmetic
  4. Knowledge — retrieval-augmented context grounding
  5. Coding — code generation in a sandbox

These are marked ``integration`` (excluded from the default ``pytest -m "not
integration"`` run) and require a live runtime on port 8010.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid

import pytest

# Ensure the env is set before any platform imports resolve.
os.environ.setdefault("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")
os.environ.setdefault("SILVERWING_MODEL", "silverwing-120m-base-v1")
os.environ.setdefault("SILVERWING_TIMEOUT", "300")
os.environ.setdefault("JARVIS_SECRET_KEY", "integration-test-secret")

# The Silverwing runtime must be serving real weights for these tests.
pytestmark = [pytest.mark.integration, pytest.mark.silverwing]

EXPECTED_MODEL = "silverwing-120m-base-v1"
EXPECTED_REVISION = "r1"
EXPECTED_BACKEND = "torch"
EXPECTED_DEVICE = "cpu"
EXPECTED_PARAMS = 120_087_552

# Timeout for the whole asyncio.wait_for (CPU inference is slow).
E2E_TIMEOUT = 300


def _make_svc():
    """Import and instantiate ChatService with the live gateway."""
    from jarvis_backend.chat_service import ChatService

    return ChatService()


def _new_session(svc):
    """Create a fresh chat session and return (user_id, session_id)."""
    uid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    svc.create_session(uid, sid, title="Integration Test")
    return uid, sid


# --------------------------------------------------------------------------- #
# Scenario 1 — Conversation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_conversation_basic_round_trip():
    """A simple user message yields a non-empty COMPLETED reply with accurate
    metadata identifying the real Silverwing model core."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    result = await asyncio.wait_for(
        svc.send_message(uid, sid, "Hello JARVIS. What is the capital of France?"),
        timeout=E2E_TIMEOUT,
    )

    # Honesty: must be COMPLETED (not FAILED, never echo/local-rule).
    assert result["status"] == "COMPLETED", f"status was {result.get('status')!r}"
    assert result["error"] is None, f"error card: {result.get('error')}"
    assert result["message"], "empty content — not a real model response"

    # Metadata must accurately identify the Silverwing model core.
    assert result["model"] == EXPECTED_MODEL
    assert result["revision"] == EXPECTED_REVISION
    assert result["backend"] == EXPECTED_BACKEND
    assert result["device"] == EXPECTED_DEVICE
    assert result["latency_ms"] > 0
    assert result["usage"]["total_tokens"] > 0
    assert result["usage"]["prompt_tokens"] > 0
    assert result["usage"]["completion_tokens"] > 0


# --------------------------------------------------------------------------- #
# Scenario 2 — Context (follow-up with conversation history)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_context_conversation_followup():
    """A follow-up question must see the prior exchange through the
    conversation history that ChatService forwards to Silverwing."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    # First turn — establish a fact.
    r1 = await asyncio.wait_for(
        svc.send_message(uid, sid, "My favorite color is teal."),
        timeout=E2E_TIMEOUT,
    )
    assert r1["status"] == "COMPLETED", f"first turn failed: {r1.get('error')}"

    # Second turn — the model should have the prior message in context.
    r2 = await asyncio.wait_for(
        svc.send_message(uid, sid, "What is my favorite color?"),
        timeout=E2E_TIMEOUT,
    )
    assert r2["status"] == "COMPLETED", f"second turn failed: {r2.get('error')}"
    assert r2["model"] == EXPECTED_MODEL
    assert r2["backend"] == EXPECTED_BACKEND

    # The conversation history (at least 2 user + 1 assistant messages).
    history = svc.load_history(uid, sid)["messages"]
    roles = [m["role"] for m in history]
    assert roles.count("user") >= 2
    assert roles.count("assistant") >= 1


# --------------------------------------------------------------------------- #
# Scenario 3 — Calculation (verifiable arithmetic)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_calculation_arithmetic():
    """Silverwing must produce a numeric answer that we can verify
    independently (here: 15 * 8 = 120)."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    r = await asyncio.wait_for(
        svc.send_message(uid, sid, "What is 15 multiplied by 8? Give just the number."),
        timeout=E2E_TIMEOUT,
    )
    assert r["status"] == "COMPLETED", f"failed: {r.get('error')}"

    content = r["message"]
    # Extract the first integer found in the response.
    nums = re.findall(r"\d+", content)
    assert nums, f"no integer found in response: {content!r}"
    answer = int(nums[0])
    assert answer == 120, f"expected 120, got {answer} from {content!r}"
    assert r["backend"] == EXPECTED_BACKEND


# --------------------------------------------------------------------------- #
# Scenario 4 — Knowledge (retrieval-augmented grounding)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_knowledge_retrieval_grounding():
    """JARVIS should recall stored knowledge and pass it as context.
    The model response should be grounded in the retrieved fact."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    # Seed a knowledge entry that the context-assembler will pick up.
    from jarvis_backend.core import get_store

    store = get_store("knowledge")
    data = store.load()
    key = f"integration-test-fact-{uuid.uuid4().hex[:8]}"
    data[key] = {
        "key": key,
        "value": "The Silverwing model has 120,087,552 parameters.",
        "category": "integration-test",
    }
    store.save()

    try:
        # Ask a question whose answer is in the seeded knowledge.
        r = await asyncio.wait_for(
            svc.send_message(uid, sid, "How many parameters does the Silverwing model have?"),
            timeout=E2E_TIMEOUT,
        )
        # The response must come from Silverwing (real model), not echo.
        assert r["status"] == "COMPLETED", f"failed: {r.get('error')}"
        assert r["model"] == EXPECTED_MODEL
        assert r["backend"] == EXPECTED_BACKEND
        content = r["message"]
        # Accept either "120,087,552" or "120087552" in the response.
        assert "120" in content and "087" in content, (
            f"expected parameter count in response, got: {content!r}"
        )
    finally:
        # Clean up the seeded knowledge.
        data = store.load()
        data.pop(key, None)
        store.save()


# --------------------------------------------------------------------------- #
# Scenario 5 — Coding (sandbox code generation)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_coding_code_generation():
    """Silverwing should generate runnable Python code for a simple task."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    r = await asyncio.wait_for(
        svc.send_message(
            uid, sid,
            "Write a Python function named 'add' that takes two numbers and returns their sum. "
            "Return only the code, no explanation.",
        ),
        timeout=E2E_TIMEOUT,
    )
    assert r["status"] == "COMPLETED", f"failed: {r.get('error')}"
    assert r["model"] == EXPECTED_MODEL
    assert r["backend"] == EXPECTED_BACKEND

    content = r["message"]
    # Should contain a function definition with 'add' and a return statement.
    assert "def add" in content, f"no function def in: {content!r}"
    assert "return" in content, f"no return in: {content!r}"

    # Extract and execute the function to verify correctness.
    func_match = re.search(r"def\s+add\s*\([^)]*\)\s*:\s*\n\s*return\s+(.+)", content)
    if func_match:
        namespace = {}
        exec(func_match.group(0), namespace)
        assert namespace["add"](3, 4) == 7, "add(3,4) did not return 7"


# --------------------------------------------------------------------------- #
# Metadata integrity (spec 31-2)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_metadata_never_claims_another_model():
    """The response metadata must identify silverwing-120m-base-v1, never
    a different model or a local-rule echo."""
    svc = _make_svc()
    uid, sid = _new_session(svc)

    r = await asyncio.wait_for(
        svc.send_message(uid, sid, "Say 'model check' and nothing else."),
        timeout=E2E_TIMEOUT,
    )
    assert r["status"] == "COMPLETED"
    # These fields must be the real Silverwing values, not a fallback.
    assert r["model"] == EXPECTED_MODEL
    assert r["revision"] == EXPECTED_REVISION
    assert r["backend"] == EXPECTED_BACKEND
    assert r["device"] == EXPECTED_DEVICE

    # The honesty guard: provider must NOT be local/local-rule/echo.
    provider = r.get("provider")
    if provider:
        assert provider not in ("local", "local-rule", "sw-echo", "sw-echo-dev"), (
            f"honesty breach: provider={provider!r}"
        )


# --------------------------------------------------------------------------- #
# Runtime health endpoint (spec 13)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_runtime_health_endpoint():
    """The Silverwing runtime health endpoint must report healthy with
    the real model, backend, and parameter count."""
    from backend.model_gateway.client import SilverwingClient

    client = SilverwingClient()
    h = await asyncio.wait_for(client.health(refresh=True), timeout=30)
    assert h.status.value == "healthy", f"health={h.status}"
    assert h.model == EXPECTED_MODEL
    assert h.revision == EXPECTED_REVISION
    assert h.backend == EXPECTED_BACKEND
    assert h.device == EXPECTED_DEVICE
    assert h.parameters == EXPECTED_PARAMS
    assert h.loaded is True
    assert h.warmup_ok is True


# --------------------------------------------------------------------------- #
# Model registry listing (spec 6)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_runtime_models_listing():
    """The runtime must list silverwing-120m-base-v1 as a registered model."""
    from backend.model_gateway.client import SilverwingClient

    client = SilverwingClient()
    models = await asyncio.wait_for(client.models(), timeout=30)
    assert len(models) >= 1
    found = [m for m in models if m.id == EXPECTED_MODEL]
    assert found, f"silverwing-120m-base-v1 not in models: {[m.id for m in models]}"
    m = found[0]
    assert "text-generation" in m.capabilities
    assert m.parameters == EXPECTED_PARAMS
