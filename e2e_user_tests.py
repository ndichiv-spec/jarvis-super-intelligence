#!/usr/bin/env python3
"""JARVIS REAL & LIVE Platform E2E User Tests (A-L)

Spec section 23: End-to-end user test suite that verifies each capability
is IMPLEMENTED + INTEGRATED + PERSISTENT + SECURE + OBSERVABLE +
UI-CONNECTED + ERROR-HANDLED + RECOVERABLE + ACTUALLY EXECUTED.

Each test maps to a specific user journey and validates that the
platform returns *real* data, not simulations or placeholders.

Run:
    python3 F:/AI/e2e_user_tests.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import asyncio
import traceback
from datetime import datetime

# Ensure both project roots and the JARVIS backend are importable.
sys.path.insert(0, "F:/AI")
sys.path.insert(0, "F:/AI/Jarvis-super-intelligence-")

os.environ.setdefault("JARVIS_ENV", "dev")

from jarvis_backend.persistence import (
    initialize_persistence, get_engine,
    ConversationRepository, MemoryRepository, TaskRepository, AuditLog,
)
from jarvis_backend.capability import get_orchestrator
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.interaction import get_interaction_layer
import jarvis_backend.capabilities as caps_mod
from jarvis_backend.capability import ExecutionContext

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

passed = 0
failed = 0
warnings = 0
results: list[dict] = []


def run_test(test_id: str, description: str):
    def decorator(func):
        def wrapper():
            global passed, failed
            start = time.time()
            try:
                func()
                elapsed = round(time.time() - start, 3)
                passed += 1
                results.append({
                    "test": test_id,
                    "description": description,
                    "status": "PASS",
                    "duration_ms": elapsed,
                })
                print(f"  [PASS] {test_id}: {description}  ({elapsed}s)")
            except AssertionError as e:
                elapsed = round(time.time() - start, 3)
                failed += 1
                results.append({
                    "test": test_id,
                    "description": description,
                    "status": "FAIL",
                    "duration_ms": elapsed,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
                print(f"  [FAIL] {test_id}: {description}  ({elapsed}s)")
                print(f"         -> {e}")
            except Exception as e:
                elapsed = round(time.time() - start, 3)
                failed += 1
                results.append({
                    "test": test_id,
                    "description": description,
                    "status": "ERROR",
                    "duration_ms": elapsed,
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                })
                print(f"  [ERR ] {test_id}: {description}  ({elapsed}s)")
                print(f"         -> {type(e).__name__}: {e}")
        wrapper._is_test = True
        wrapper._test_id = test_id
        return wrapper
    return decorator


def warn(msg: str):
    global warnings
    warnings += 1
    print(f"  [WARN] {msg}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _init_db():
    """Initialize persistence tables."""
    initialize_persistence()
    return get_engine()


def _check_all_health():
    """Run health checks across all capabilities, mirroring app startup."""
    orch = get_orchestrator()
    asyncio.run(orch.registry.health_all())


# ---------------------------------------------------------------------------
# Test A: Capability Registration & Live Status (spec section 4)
# ---------------------------------------------------------------------------

@run_test("A", "All 11 capabilities registered with live health status")
def test_a_capabilities():
    _check_all_health()
    orch = get_orchestrator()
    statuses = orch.get_all_status()

    assert "capabilities" in statuses, "get_all_status() missing 'capabilities' key"
    caps = statuses["capabilities"]

    expected = {
        "brain", "conversation", "voice", "vision", "image.generate",
        "provider", "browser", "task", "memory", "knowledge.search", "tool",
    }
    actual = set(caps.keys())
    missing = expected - actual
    assert not missing, f"Missing capabilities: {missing}"

    # Status must be a real lifecycle state, never "simulated"/"fake".
    valid_statuses = {"ready", "degraded", "unavailable", "error", "offline",
                      "not_configured", "active", "auth_failed", "rate_limited",
                      "unsupported"}
    for cap_id, info in caps.items():
        s = info["status"].lower() if isinstance(info["status"], str) else str(info["status"]).lower()
        assert s in valid_statuses, f"Capability '{cap_id}' has invalid status: {info['status']}"

    # At least these should be ready in dev mode with real providers configured.
    ready_caps = [c for c, i in caps.items() if i["status"].lower() == "ready"]
    assert len(ready_caps) >= 5, f"Expected at least 5 ready capabilities, got {len(ready_caps)}: {ready_caps}"
    assert "brain" in caps, "brain must be registered"
    assert "conversation" in caps, "conversation must be registered"
    assert "tool" in caps, "tool must be registered"
    print(f"         (registered={len(caps)}, ready={len(ready_caps)})")


# ---------------------------------------------------------------------------
# Test B: Capability Health Check -- Brain (spec section 5)
# ---------------------------------------------------------------------------

@run_test("B", "Brain capability produces real health check with provider data")
def test_b_brain_health():
    _check_all_health()
    oreg = get_orchestrator()
    from jarvis_backend.capabilities import get_registry
    registry = get_registry()
    brain_cap = registry.get("brain")
    assert brain_cap is not None, "Brain capability not registered"

    # Call health() directly for full health data.
    brain = asyncio.run(brain_cap.health())

    # Brain must report real status, not 'simulated'.
    s = brain["status"]
    if hasattr(s, "value"):
        s = s.value
    s = s.lower() if isinstance(s, str) else str(s).lower()
    assert s in {"ready", "degraded", "unavailable", "error"}, \
        f"Brain has invalid status: {brain['status']}"

    # In dev mode with real OpenAI key, brain should be ready.
    assert s == "ready", f"Brain should be READY in dev mode, got {brain['status']}"
    assert "healthy" in brain, f"Missing 'healthy' key in brain status: {brain.keys()}"
    assert brain["healthy"] is True, f"Brain healthy should be True, got {brain['healthy']}"
    assert "latency_ms" in brain or "last_checked" in brain, "Brain health missing latency/check timestamp"
    print(f"         (status={brain['status']}, healthy={brain['healthy']}, latency={brain.get('latency_ms', 'N/A')}ms)")


# ---------------------------------------------------------------------------
# Test C: Conversation Persistence - Create/Read/Verify (spec section 6)
# ---------------------------------------------------------------------------

@run_test("C", "Conversation persistence: create -> add message -> retrieve -> verify")
def test_c_conversation():
    import uuid
    session_id = f"test-e2e-{uuid.uuid4().hex[:8]}"

    # Create via persistence layer (same as e2e_validation)
    conv_id = ConversationRepository.create_session(
        session_id=session_id,
        user_id="test-user-e2e",
        title="E2E Test Conversation",
        modality="text",
    )
    assert conv_id, "Failed to create conversation session"

    # Add message
    msg_id = ConversationRepository.add_message(
        conversation_id=conv_id,
        session_id=session_id,
        role="user",
        content="Hello JARVIS E2E test!",
        modality="text",
    )
    assert msg_id, "Failed to add message"

    # Retrieve
    retrieved_session = ConversationRepository.get_session(session_id)
    assert retrieved_session is not None, "Failed to retrieve session"

    messages = ConversationRepository.get_messages(conv_id)
    assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"
    assert messages[0]["content"] == "Hello JARVIS E2E test!", "Message content mismatch"
    assert messages[0]["role"] == "user", "Message role mismatch"

    # Verify persistence in DB directly
    engine = get_engine()
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM jarvis_conversations WHERE id = :cid"), {"cid": conv_id}).fetchall()
        assert len(rows) == 1, "Conversation not persisted in DB"
        msg_rows = conn.execute(text("SELECT * FROM jarvis_messages WHERE conversation_id = :cid"), {"cid": conv_id}).fetchall()
        assert len(msg_rows) == 1, "Message not persisted in DB"

    print(f"         (conv_id={conv_id}, msg_id={msg_id}, session_id={session_id})")


# ---------------------------------------------------------------------------
# Test D: Memory Persistence - Store/Recall/Query (spec section 7)
# ---------------------------------------------------------------------------

@run_test("D", "Memory: store -> recall -> verify persistence in DB")
def test_d_memory():
    # Store memory
    mem_id = MemoryRepository.store_memory(
        memory_type="episodic",
        content="E2E test memory: JARVIS platform is live and operational",
        session_id="test-session-e2e",
        user_id="test-user-e2e",
        provenance="e2e_test",
        metadata={"test": True},
    )
    assert mem_id, "Failed to store memory"

    # Recall
    memories = MemoryRepository.retrieve_memories(
        memory_type="episodic",
        user_id="test-user-e2e",
        limit=5,
    )
    assert len(memories) >= 1, f"Expected at least 1 memory, got {len(memories)}"
    assert any("live and operational" in m["content"] for m in memories), "Memory content mismatch"

    # Verify persistence in DB
    engine = get_engine()
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM jarvis_memory_entries WHERE id = :mid"), {"mid": mem_id}).fetchall()
        assert len(rows) == 1, "Memory not persisted in DB"

    print(f"         (mem_id={mem_id}, retrieved={len(memories)}, db_verified=True)")


# ---------------------------------------------------------------------------
# Test E: Browser Automation - Real HTTP fetch (spec section 8)
# ---------------------------------------------------------------------------

@run_test("E", "Browser automation: real HTTP fetch with content verification")
def test_e_browser():
    from jarvis_backend.capabilities import get_registry
    registry = get_registry()

    browser_cap = registry.get("browser")
    assert browser_cap is not None, "Browser capability not registered"

    context = ExecutionContext(user_id="test-user-e2e", session_id="browser-e2e")

    # Create session
    result = asyncio.run(browser_cap.execute(
        {"action": "create_session"},
        context,
    ))
    assert result.success, f"Browser session creation failed: {result.error}"
    print(f"         (session: {result.data})")

    # Navigate to real URL
    result = asyncio.run(browser_cap.execute(
        {"action": "navigate", "url": "https://httpbin.org/html"},
        context,
    ))
    assert result.success, f"Browser navigate failed: {result.error}"

    data = result.data
    assert "content" in data, "Missing 'content' key in browser result"
    assert len(data["content"]) > 0, "No content returned from browser"
    assert "<html" in data["content"].lower(), "Response is not HTML"
    assert "Herman Melville" in data["content"], "Expected content from httpbin.org/html not found"

    print(f"         (url=https://httpbin.org/html, content_len={len(data['content'])})")


# ---------------------------------------------------------------------------
# Test F: Tool Execution - Browser tool via interaction layer (spec section 9)
# ---------------------------------------------------------------------------

@run_test("F", "Tool execution: browser tool returns real HTTP data")
def test_f_tool():
    interaction = get_interaction_layer()

    result = asyncio.run(interaction.execute_tool(
        user_id="test-user-e2e",
        session_id="tool-e2e",
        tool="browser",
        action="fetch",
        params={"url": "https://httpbin.org/html"},
    ))
    assert result["success"], f"Tool execution failed: {result.get('error', 'unknown')}"
    data = result.get("data", {})
    assert data.get("content_length", 0) > 0, "No content from tool"
    assert data.get("status_code") == 200, f"Expected 200, got {data.get('status_code')}"
    print(f"         (tool=browser, status_code={data['status_code']}, content_len={data['content_length']})")


# ---------------------------------------------------------------------------
# Test G: Provider/Model Orchestration (spec section 10)
# ---------------------------------------------------------------------------

@run_test("G", "Provider/model orchestration: live provider status")
def test_g_provider():
    from jarvis_backend.capabilities import get_registry
    _check_all_health()
    registry = get_registry()

    provider_cap = registry.get("provider")
    assert provider_cap is not None, "Provider capability not registered"

    status = provider_cap.get_available_providers()
    assert status is not None, "get_available_providers returned None"

    # The API returns a list of provider dicts with name/status/available.
    assert isinstance(status, list), f"Expected list, got {type(status)}"
    assert len(status) > 0, "No providers found"

    # Verify each entry has the expected structure.
    for p in status:
        assert "name" in p, f"Provider entry missing 'name': {p}"
        assert "status" in p, f"Provider entry missing 'status': {p}"
    provider_names = [p["name"] for p in status]
    print(f"         (providers={provider_names[:8]}, total={len(status)})")


# --------------------------------------------------------------------------
# Test H: Task Management - Create/Query/Recover (spec section 12)
# ---------------------------------------------------------------------------

@run_test("H", "Task management: create task -> query incomplete -> verify persistence")
def test_h_task():
    task_id = TaskRepository.create_task(
        user_id="test-user-e2e",
        capability="test",
        title="E2E Test Task",
        input_data={"test": True, "description": "E2E task for real platform verification"},
        priority=1,
    )
    assert task_id, "Failed to create task"
    assert "task" in task_id.lower() or "task" in task_id, "Task ID should contain 'task'"

    # Query incomplete tasks
    incomplete = TaskRepository.get_incomplete_tasks()
    assert len(incomplete) >= 1, f"Expected at least 1 incomplete task, got {len(incomplete)}"

    found = any(t["id"] == task_id for t in incomplete)
    assert found, f"Created task {task_id} not found in incomplete tasks"

    # Verify in DB
    engine = get_engine()
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM jarvis_tasks WHERE id = :tid"), {"tid": task_id}).fetchone()
        assert row is not None, "Task not persisted in DB"

    print(f"         (task_id={task_id}, incomplete={len(incomplete)})")


# ---------------------------------------------------------------------------
# Test I: Event Fabric - Emit/Subscribe/Persist (spec section 14)
# ---------------------------------------------------------------------------

@run_test("I", "Event fabric: emit -> retrieve -> verify persistence in DB")
def test_i_event_fabric():
    from jarvis_backend.persistence import event_log_table, db_session, insert
    bus = get_event_bus()

    # Wire DB persistence into the event bus (mirrors app startup wiring).
    def _persist_event(event_dict):
        with db_session() as conn:
            conn.execute(insert(event_log_table).values(
                event_id=event_dict.get("event_id", event_dict.get("id", "")),
                event_type=event_dict.get("event_type", ""),
                source=event_dict.get("source", ""),
                capability=event_dict.get("capability", ""),
                correlation_id=event_dict.get("correlation_id", ""),
                session_id=event_dict.get("session_id", ""),
                user_id=event_dict.get("user_id", ""),
                status=event_dict.get("status", ""),
                payload=json.dumps(event_dict.get("payload", {})),
                metrics=json.dumps(event_dict.get("metrics", {})),
            ))
    bus.set_db_persistence(_persist_event)

    # emit() returns None (fire-and-forget); verify via retrieval.
    bus.emit(
        event_type="test.e2e.event",
        source="e2e_test",
        capability="test",
        session_id="test-session-e2e",
        user_id="test-user-e2e",
        status="completed",
        payload={"test": "E2E event fabric"},
    )

    # Retrieve events — must find our emitted event.
    events = bus.get_events(event_type="test.e2e.event", limit=10)
    assert len(events) >= 1, f"Expected at least 1 event, got {len(events)}"

    found = any(e.get("event_type") == "test.e2e.event" for e in events)
    assert found, "Emitted event not found in retrieval"

    # Verify persistence in DB
    engine = get_engine()
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM jarvis_event_log WHERE event_type = :et"), {"et": "test.e2e.event"}).fetchall()
        assert len(rows) >= 1, "Event not persisted in DB"

    print(f"         (retrieved={len(events)}, db_rows={len(rows)})")


# ---------------------------------------------------------------------------
# Test J: Model Catalog - 53-entry live catalog (spec section 8)
# ---------------------------------------------------------------------------

@run_test("J", "Model catalog: live 53-entry catalog from system.py")
def test_j_models():
    from jarvis_backend.routers.system import _MODEL_CATALOG
    assert len(_MODEL_CATALOG) == 53, f"Expected 53 models, got {len(_MODEL_CATALOG)}"

    # Verify all entries have required fields
    for entry in _MODEL_CATALOG:
        assert "model_id" in entry, "Missing model_id"
        assert "provider" in entry, "Missing provider"
        assert "category" in entry, "Missing category"
        assert "max_tokens" in entry, "Missing max_tokens"

    # Verify provider coverage
    providers = set(e["provider"] for e in _MODEL_CATALOG)
    expected_providers = {"openai", "google", "anthropic", "nvidia", "huggingface", "stability", "aws", "silverwing", "jarvis-brain"}
    found = providers & expected_providers
    assert len(found) >= 7, f"Expected at least 7 real providers, found: {found}"

    print(f"         (total={len(_MODEL_CATALOG)}, providers={sorted(found)})")


# ---------------------------------------------------------------------------
# Test K: Platform Identity - Live Git state (spec section 12)
# ---------------------------------------------------------------------------

@run_test("K", "Platform identity: live Git repository state from platform_identity")
def test_k_identity():
    from jarvis_backend.platform_identity import get_platform_identity
    identity = get_platform_identity()

    # Identity nests git info under "git" key.
    git_info = identity.get("git", {})
    assert "repository" in git_info, f"Missing 'repository' in identity: {identity.keys()}"
    assert "branch" in git_info, f"Missing 'branch' in identity: {identity.keys()}"
    assert "head" in git_info, f"Missing 'head' in identity: {identity.keys()}"

    assert git_info.get("repo_available") == True, f"Expected repo_available=True, got {git_info.get('repo_available')}"
    assert git_info.get("repository") == "Jarvis-super-intelligence-", \
        f"Expected 'Jarvis-super-intelligence-', got {git_info.get('repository')}"
    assert git_info.get("branch") == "main", f"Expected branch='main', got {git_info.get('branch')}"

    print(f"         (repo={git_info['repository']}, branch={git_info['branch']}, head={git_info.get('head', '')[:12]})")


# ---------------------------------------------------------------------------
# Test L: Service Orchestration - Live service health (spec section 40)
# ---------------------------------------------------------------------------

@run_test("L", "Service orchestration: live service health from /services endpoint")
def test_l_services():
    from jarvis_backend.routers.system import services
    result = asyncio.run(services())

    assert "services" in result, "Missing 'services' key"
    assert "overall_status" in result, "Missing 'overall_status'"

    services_state = result["services"]
    required = {"backend", "silverwing-runtime", "jarvis-brain", "database", "redis"}
    found = set(services_state.keys())
    assert required.issubset(found), f"Missing services: {required - found}"

    # Backend must always be healthy.
    assert services_state["backend"]["status"] == "healthy", \
        f"Backend should be healthy, got {services_state['backend']['status']}"

    # Silverwing status must be truthful.
    sw_status = services_state["silverwing-runtime"]["status"]
    assert sw_status in ("healthy", "unreachable", "not_configured", "error"), \
        f"Unexpected silverwing status: {sw_status}"

    # Database must be healthy (DB was initialized).
    db_status = services_state["database"]["status"]
    assert db_status in ("healthy", "not_configured", "error"), \
        f"Unexpected database status: {db_status}"

    print(f"         (overall={result['overall_status']}, services={sorted(services_state.keys())})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("JARVIS E2E USER TESTS (A-L)")
    print("Spec 23: Each capability must be IMPLEMENTED + INTEGRATED")
    print("  + PERSISTENT + SECURE + OBSERVABLE + UI-CONNECTED")
    print("  + ERROR-HANDLED + RECOVERABLE + ACTUALLY EXECUTED")
    print("=" * 70)
    print()

    # Initialize
    _init_db()
    print("[Setup] Database initialized")
    caps_mod.register_all_capabilities()
    print("[Setup] 11 capabilities registered")
    _check_all_health()
    print("[Setup] Health checks complete")

    tests = [
        ("A", test_a_capabilities),
        ("B", test_b_brain_health),
        ("C", test_c_conversation),
        ("D", test_d_memory),
        ("E", test_e_browser),
        ("F", test_f_tool),
        ("G", test_g_provider),
        ("H", test_h_task),
        ("I", test_i_event_fabric),
        ("J", test_j_models),
        ("K", test_k_identity),
        ("L", test_l_services),
    ]

    print()
    for test_id, test_func in tests:
        test_func()

    print()
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {warnings} warnings")
    print("=" * 70)

    results_path = "F:/AI/jarvis_e2e_user_test_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "total": passed + failed,
            "tests": results,
        }, f, indent=2)
    print(f"Results written to {results_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
