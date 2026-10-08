from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from jarvis_backend.runtime import (
    ExecutionState,
    InvalidExecutionTransitionError,
    InvalidPlanStepTransitionError,
    InvalidPlanTransitionError,
    JarvisRuntime,
)


@pytest.fixture
def durable_runtime():
    return JarvisRuntime()


def test_execution_transitions_are_persisted_and_validated(durable_runtime):
    execution = durable_runtime.create_execution(
        command_id=str(uuid.uuid4()),
        user_id="runtime-test-user",
    )

    assert durable_runtime.claim_execution(
        execution["execution_id"], worker_id="test-worker",
    )
    durable_runtime.transition(
        execution["execution_id"], ExecutionState.STARTING,
        worker_id="test-worker",
    )
    running = durable_runtime.transition(
        execution["execution_id"], ExecutionState.RUNNING,
        worker_id="test-worker",
    )
    assert running["status"] == "RUNNING"
    assert running["worker_id"] == "test-worker"
    assert running["heartbeat_at"] is not None
    with pytest.raises(InvalidExecutionTransitionError):
        durable_runtime.transition(
            execution["execution_id"], ExecutionState.SUCCEEDED,
        )


def test_execution_claim_is_exclusive(durable_runtime):
    execution = durable_runtime.create_execution(
        command_id=str(uuid.uuid4()),
        user_id="runtime-test-user",
    )

    assert durable_runtime.claim_execution(
        execution["execution_id"], worker_id="worker-one",
    )
    assert not durable_runtime.claim_execution(
        execution["execution_id"], worker_id="worker-two",
    )


def test_running_work_can_be_quarantined_for_reconciliation(durable_runtime):
    execution = durable_runtime.create_execution(
        command_id=str(uuid.uuid4()),
        user_id="runtime-test-user",
    )
    durable_runtime.claim_execution(
        execution["execution_id"], worker_id="test-worker",
    )
    durable_runtime.transition(
        execution["execution_id"], ExecutionState.STARTING,
        worker_id="test-worker",
    )
    durable_runtime.transition(
        execution["execution_id"], ExecutionState.RUNNING,
        worker_id="test-worker",
    )

    recovered = durable_runtime.transition(
        execution["execution_id"],
        ExecutionState.RECOVERY_REQUIRED,
        error="execution timed out",
    )
    assert recovered["status"] == "RECOVERY_REQUIRED"
    assert recovered["error"] == "execution timed out"


def test_execution_lineage_is_visible_from_another_runtime_instance(durable_runtime):
    command_id = str(uuid.uuid4())
    execution = durable_runtime.create_execution(
        command_id=command_id,
        user_id="lineage-owner",
        plan_id=str(uuid.uuid4()),
    )

    reopened_runtime = JarvisRuntime()
    persisted = reopened_runtime.get_execution(execution["execution_id"])
    owner_records = reopened_runtime.list_executions(user_id="lineage-owner")

    assert persisted["command_id"] == command_id
    assert persisted["plan_id"] == execution["plan_id"]
    assert execution["execution_id"] in {
        item["execution_id"] for item in owner_records
    }
    assert reopened_runtime.list_executions(user_id="different-owner") == []


def test_execution_survives_database_engine_restart(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    from jarvis_backend import db
    from jarvis_backend import runtime as runtime_module

    database_file = tmp_path / "durable-runtime.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    first_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    db.metadata.create_all(first_engine)
    monkeypatch.setattr(runtime_module, "get_engine", lambda: first_engine)
    command_id = str(uuid.uuid4())
    execution = JarvisRuntime().create_execution(
        command_id=command_id,
        user_id="restart-owner",
    )
    first_engine.dispose()

    restarted_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(runtime_module, "get_engine", lambda: restarted_engine)
    persisted = JarvisRuntime().get_execution(execution["execution_id"])

    assert persisted["command_id"] == command_id
    assert persisted["status"] == "QUEUED"
    restarted_engine.dispose()


def test_event_replay_uses_monotonic_sequences(durable_runtime):
    command_id = str(uuid.uuid4())
    first = durable_runtime.append_event(
        command_id=command_id,
        event_type="command.created",
        payload={
            "safe": True,
            "event_id": "forged",
            "sequence": 0,
            "timestamp": 0,
            "type": "forged",
        },
    )
    assert first["event_id"] != "forged"
    assert first["sequence"] == 1
    assert first["timestamp"] > 0
    assert first["type"] == "command.created"
    assert first["payload"]["type"] == "forged"
    durable_runtime.append_event(
        command_id=command_id,
        event_type="execution.started",
        execution_id=str(uuid.uuid4()),
    )

    replay = durable_runtime.replay_events(command_id, after_sequence=first["sequence"])
    assert len(replay) == 1
    assert replay[0]["sequence"] == first["sequence"] + 1
    assert replay[0]["type"] == "execution.started"


def test_structured_plan_and_step_lifecycle_are_persisted(durable_runtime):
    plan_id = str(uuid.uuid4())
    plan = durable_runtime.create_plan(
        plan_id=plan_id,
        command_id=str(uuid.uuid4()),
        user_id="plan-owner",
        objective="Inspect the repository",
        steps=[{
            "step_id": "inspect",
            "capability": "project.inspect",
            "summary": "Inspect tracked files",
            "input": {"path": "src"},
            "depends_on": [],
        }],
    )
    assert plan["status"] == "PROPOSED"
    assert plan["required_permissions"] is None
    assert plan["steps"][0]["input"] == {"path": "src"}

    assert durable_runtime.update_plan_status(plan_id, "VALIDATED")
    assert durable_runtime.update_plan_status(plan_id, "EXECUTING")
    assert durable_runtime.update_plan_step(
        plan_id, "inspect", status="RUNNING",
    )
    assert durable_runtime.update_plan_step(
        plan_id, "inspect", status="SUCCEEDED",
        result={"success": True},
    )
    final_plan = durable_runtime.get_plan(plan_id)
    assert final_plan["status"] == "EXECUTING"
    assert final_plan["steps"][0]["status"] == "SUCCEEDED"
    assert final_plan["steps"][0]["result"] == {"success": True}
    with pytest.raises(InvalidPlanStepTransitionError):
        durable_runtime.update_plan_step(
            plan_id, "inspect", status="PENDING",
        )
    with pytest.raises(InvalidPlanTransitionError):
        durable_runtime.update_plan_status(plan_id, "PROPOSED")


def test_orchestrator_audit_persists_validated_plan_and_step_lineage(monkeypatch):
    from jarvis_backend.routers import commands

    command_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    command = {
        "command_id": command_id,
        "user_id": "plan-audit-owner",
        "plan_id": plan_id,
        "plan_ids": [],
        "plan": [],
        "models": [],
        "capabilities": [],
        "events": [],
        "errors": [],
        "started_at": None,
        "completed_at": None,
    }

    class CommandStore:
        def load(self):
            return {command_id: command}

        def save(self):
            return None

    monkeypatch.setattr(commands, "get_store", lambda _name: CommandStore())
    record = commands._audit_callback(command_id)
    record(SimpleNamespace(
        event="BRAIN_PLAN_PROPOSED",
        provenance={
            "capabilities": [{
                "step_id": "inspect",
                "capability": "project.inspect",
                "summary": "Inspect repository",
                "input": {"path": "."},
                "depends_on": [],
            }],
            "model": "test-planner",
        },
        detail="Inspect the repository",
        capability="",
        success=None,
        cost={},
    ))
    record(SimpleNamespace(
        event="BRAIN_PLAN_VALIDATED",
        provenance={"decision": "ACCEPTED"},
        detail="accepted",
        capability="",
        success=None,
        cost={},
    ))
    record(SimpleNamespace(
        event="PLAN_AUTHORIZED",
        provenance={"authorized": ["project.inspect"]},
        detail="authorized",
        capability="",
        success=None,
        cost={},
    ))
    record(SimpleNamespace(
        event="CAPABILITY_STARTED",
        provenance={},
        detail="started",
        capability="project.inspect",
        success=None,
        cost={},
    ))
    record(SimpleNamespace(
        event="CAPABILITY_COMPLETED",
        provenance={},
        detail="completed",
        capability="project.inspect",
        success=True,
        cost={},
    ))
    record(SimpleNamespace(
        event="TASK_COMPLETED",
        provenance={},
        detail="verified",
        capability="",
        success=True,
        cost={},
    ))

    plan = JarvisRuntime().get_plan(plan_id)
    assert plan["status"] == "COMPLETED"
    assert plan["steps"][0]["status"] == "SUCCEEDED"
    assert command["plan_ids"] == [plan_id]
    assert command["active_step_id"] is None
    capability_started = next(
        event for event in JarvisRuntime().replay_events(command_id)
        if event["type"] == "capability_started"
    )
    assert capability_started["step_id"] == "inspect"
    assert capability_started["payload"]["plan_id"] == plan_id


def test_worker_recovery_never_requeues_possible_side_effects(durable_runtime):
    before_start = durable_runtime.create_execution(
        command_id=str(uuid.uuid4()),
        user_id="runtime-test-user",
    )
    durable_runtime.claim_execution(
        before_start["execution_id"], worker_id="old-worker",
        lease_seconds=0,
    )

    executing = durable_runtime.create_execution(
        command_id=str(uuid.uuid4()),
        user_id="runtime-test-user",
    )
    durable_runtime.claim_execution(
        executing["execution_id"], worker_id="old-worker",
    )
    durable_runtime.transition(
        executing["execution_id"], ExecutionState.STARTING,
        worker_id="old-worker", lease_seconds=0,
    )
    durable_runtime.transition(
        executing["execution_id"], ExecutionState.RUNNING,
        worker_id="old-worker", lease_seconds=0,
    )

    recovered = durable_runtime.recover_orphaned(worker_id="new-worker")
    results = {item["execution_id"]: item["status"] for item in recovered}
    assert results[before_start["execution_id"]] == "QUEUED"
    assert results[executing["execution_id"]] == "RECOVERY_REQUIRED"
