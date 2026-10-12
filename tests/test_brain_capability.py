"""Regression tests for JARVIS Brain capability context propagation."""

import json

import pytest

from jarvis_backend.capabilities.brain import (
    BrainCapability,
    ConversationRepository,
    MemoryRepository,
)
from jarvis_backend.capability import ExecutionContext


def _empty_records(*_args, **_kwargs):
    return []


@pytest.mark.asyncio
async def test_reason_preserves_execution_correlation_id(monkeypatch):
    monkeypatch.setattr(ConversationRepository, "get_messages", _empty_records)
    monkeypatch.setattr(MemoryRepository, "get_working_memory", _empty_records)
    monkeypatch.setattr(MemoryRepository, "retrieve_memories", _empty_records)
    brain = BrainCapability()

    async def fake_provider(prompt, context):
        assert prompt
        assert context.correlation_id == "corr-brain-test"
        return {
            "success": True,
            "data": {
                "response": json.dumps(
                    {
                        "capabilities_needed": [],
                        "reasoning": "direct response",
                        "confidence": 1,
                        "security_flags": [],
                    }
                )
            },
        }

    monkeypatch.setattr(brain, "_call_provider", fake_provider)
    context = ExecutionContext(
        user_id="test-user",
        session_id="test-session",
        correlation_id="corr-brain-test",
    )

    result = await brain._reason({"input": "hello"}, context)

    assert result.success is True
    assert result.correlation_id == "corr-brain-test"


@pytest.mark.asyncio
async def test_plan_prompt_keeps_json_field_names_literal(monkeypatch):
    brain = BrainCapability()
    prompts = []

    async def fake_provider(prompt, context):
        prompts.append(prompt)
        assert context.session_id == "test-session"
        return {"success": True, "data": {"response": '{"steps": []}'}}

    monkeypatch.setattr(brain, "_call_provider", fake_provider)
    context = ExecutionContext(user_id="test-user", session_id="test-session")

    result = await brain._plan({"task": "test"}, context)

    assert result.success is True
    assert brain.status.value == "ready"
    assert "{step_number, capability, action, description, reason}" in prompts[0]
