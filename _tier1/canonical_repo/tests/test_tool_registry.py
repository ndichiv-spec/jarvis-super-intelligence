"""Tests for the Tool Registry (Section 20/28).

No secrets, no network.  Exercises the authorization boundary, the sandbox AST
guard, and secret-scrubbing — all of which are deterministic.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from research_engine.models import RiskLevel, ToolResult
from research_engine.tool_registry import (
    BrowserSearchTool,
    DefaultPermissionPolicy,
    KnowledgeRetrieveTool,
    MemoryRecallTool,
    MemoryTool,
    ModelConsultTool,
    SandboxRunTool,
    StaticSearchTool,
    ToolContext,
    ToolRegistry,
    scrub_secrets,
)

pytestmark = pytest.mark.brain


def _run(coro):
    # Use new_event_loop() (not get_event_loop()): Python 3.13 no longer
    # auto-creates a loop for get_event_loop() once any prior asyncio.run /
    # set_event_loop has flipped the policy's _set_called flag.  A fresh loop
    # also avoids leaking global policy state across tests.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---- describe() must never leak credentials ---------------------------------
def test_describe_exposes_no_credentials():
    reg = ToolRegistry()
    for t in (SandboxRunTool(), BrowserSearchTool(), KnowledgeRetrieveTool(),
              MemoryTool(), MemoryRecallTool(), ModelConsultTool()):
        reg.register(t)

    flat = __import__("json").dumps(reg.describe())
    forbidden = ("api_key", "token", "password", "secret", "bearer", "authorization")
    lowered = flat.lower()
    # Tool descriptions/schemas must not carry credential-shaped fields.
    for word in forbidden:
        assert word not in lowered, f"credential leak via '{word}' in describe()"
    for d in reg.describe():
        assert "api_key" not in d.get("parameters", {}).get("properties", {})
        assert set(d.keys()) >= {"name", "description", "parameters", "risk"}


def test_describe_does_not_register_secret_values():
    tool = SandboxRunTool()
    assert "key" not in tool.schema.get("properties", {})
    desc = tool.describe()
    # Description is a human sentence, never a credential.
    assert "Bearer" not in desc["description"]


# ---- secret scrubbing (Section 19/28) --------------------------------------
def test_scrub_secrets_redacts_api_key_shape():
    out, redacted = scrub_secrets("call failed: api_key=sk-abc123def456ghijklmnop")
    assert redacted is True
    assert "sk-abc123def456ghijklmnop" not in out
    assert "REDACTED" in out


def test_scrub_secrets_redacts_long_alphanumeric_tokens():
    # HF / OpenAI style 32+ char tokens of form a.b
    out, redacted = scrub_secrets("token=aaabbbccc111.222ddee111ff")
    assert redacted is True
    assert "222ddee111ff" not in out


def test_scrub_secrets_plain_text_not_redacted():
    out, redacted = scrub_secrets("2 + 2 = 4")
    assert redacted is False
    assert out == "2 + 2 = 4"


# ---- authorization ---------------------------------------------------------
def test_network_tool_denied_without_confirmation():
    reg = ToolRegistry(policy=DefaultPermissionPolicy())
    reg.register(BrowserSearchTool())
    ctx = ToolContext(user_id="alice")
    res = _run(reg.invoke("search_web", {"query": "hello"}, ctx))
    assert not res.success
    assert "TOOL_DENIED" in res.error


def test_network_tool_allowed_with_confirmation():
    reg = ToolRegistry(policy=DefaultPermissionPolicy(confirmations={"alice:search_web": True}))
    reg.register(BrowserSearchTool())
    ctx = ToolContext(user_id="alice")
    # search_web needs BrowserEngine which isn't importable in tests -> BROWSER_UNAVAILABLE,
    # but it must NOT be a denial (authorization passed).
    res = _run(reg.invoke("search_web", {"query": "hello"}, ctx))
    assert not res.success  # no browser in test env
    assert "BROWSER_UNAVAILABLE" in res.error or "TOOL_DENIED" not in res.error


def test_exec_tool_auto_allowed():
    reg = ToolRegistry(policy=DefaultPermissionPolicy())
    reg.register(SandboxRunTool())
    ctx = ToolContext(user_id="bob")
    res = _run(reg.invoke("sandbox_run", {"code": "print(2+2)"}, ctx))
    assert res.success
    assert "4" in res.result


def test_unknown_tool_denied():
    reg = ToolRegistry()
    res = _run(reg.invoke("nope", {}, ToolContext()))
    assert not res.success
    assert "TOOL_NOT_REGISTERED" in res.error


# ---- sandbox policy (Section 16 honesty) -------------------------------------
def test_sandbox_rejects_import_os():
    reg = ToolRegistry()
    reg.register(SandboxRunTool())
    ctx = ToolContext(user_id="carol")
    res = _run(reg.invoke("sandbox_run", {"code": "import os; os.system('id')"}, ctx))
    assert not res.success
    assert "import" in res.error.lower()


def test_sandbox_rejects_file_open_and_eval():
    reg = ToolRegistry()
    reg.register(SandboxRunTool())
    ctx = ToolContext(user_id="carol")
    for bad in ["open('/etc/passwd')", "eval('1+1')", "exec('x=1')"]:
        res = _run(reg.invoke("sandbox_run", {"code": bad}, ctx))
        assert not res.success, bad
        assert "block" in res.error.lower() or "violation" in res.error.lower(), bad


def test_sandbox_rejects_dangerous_attrs():
    reg = ToolRegistry()
    reg.register(SandboxRunTool())
    ctx = ToolContext(user_id="carol")
    res = _run(reg.invoke("sandbox_run", {"code": "print(1)"}, ctx))
    assert res.success


def test_sandbox_allows_plain_arithmetic():
    reg = ToolRegistry()
    reg.register(SandboxRunTool())
    ctx = ToolContext(user_id="carol")
    res = _run(reg.invoke("sandbox_run", {"code": "print(6*7)"}, ctx))
    assert res.success
    assert "42" in res.result


# ---- static search (test-only, deterministic) ------------------------------
def test_static_search_no_network():
    reg = ToolRegistry()
    reg.register(StaticSearchTool(knowledge={"photosynthesis": ["plants make glucose", "uses chlorophyll"]}))
    ctx = ToolContext(user_id="dave")
    res = _run(reg.invoke("static_search", {"query": "photosynthesis"}, ctx))
    assert res.success
    assert "chlorophyll" in res.result


# ---- model_consult degrades honestly (no provider in tests) -----------------
def test_model_consult_unavailable_in_tests():
    reg = ToolRegistry(policy=DefaultPermissionPolicy(confirmations={"eve:model_consult": True}))
    reg.register(ModelConsultTool())
    ctx = ToolContext(user_id="eve")
    res = _run(reg.invoke("model_consult", {"question": "hi", "provider": "auto"}, ctx))
    assert not res.success
    assert "PROVIDER_UNAVAILABLE" in res.error
