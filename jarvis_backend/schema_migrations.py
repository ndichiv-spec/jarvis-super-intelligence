"""The ordered, explicit schema migrations used by the existing SQL store."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
import uuid

from sqlalchemy import Engine, inspect, insert, select, update

from . import db


@dataclass(frozen=True)
class Migration:
    revision: str
    upgrade: Callable[[Engine], None]
    downgrade: Callable[[Engine], None] | None = None


def _upgrade_initial_store(engine: Engine) -> None:
    db.kv_store.create(engine, checkfirst=True)
    db.schema_migrations.create(engine, checkfirst=True)


def _upgrade_command_events(engine: Engine) -> None:
    db.command_events.create(engine, checkfirst=True)
    with engine.begin() as connection:
        command_rows = connection.execute(
            select(db.kv_store.c.key, db.kv_store.c.value).where(
                db.kv_store.c.store_name == "commands"
            )
        )
        for command_id, raw_value in command_rows:
            command = json.loads(raw_value)
            events = command.get("events", [])
            if not isinstance(events, list):
                continue
            ordered = sorted(
                events,
                key=lambda item: (str(item.get("timestamp", "")), str(item.get("event_id", ""))),
            )
            for sequence, event in enumerate(ordered, start=1):
                event = dict(event)
                event_id = str(
                    event.get("event_id")
                    or uuid.uuid5(uuid.NAMESPACE_URL, f"jarvis:{command_id}:event:{sequence}")
                )
                event.update(sequence=sequence, command_id=command_id, event_id=event_id)
                existing = connection.execute(
                    select(db.command_events.c.event_id).where(
                        db.command_events.c.command_id == command_id,
                        db.command_events.c.sequence == sequence,
                    )
                ).first()
                if existing is None:
                    connection.execute(
                        insert(db.command_events).values(
                            command_id=command_id,
                            sequence=sequence,
                            event_id=event_id,
                            created_at=str(event.get("timestamp", "")),
                            payload=json.dumps(event, ensure_ascii=False, default=str),
                        )
                    )
            command["event_seq"] = max(int(command.get("event_seq", 0)), len(ordered))
            connection.execute(
                update(db.kv_store)
                .where(db.kv_store.c.store_name == "commands", db.kv_store.c.key == command_id)
                .values(value=json.dumps(command, ensure_ascii=False, default=str))
            )


def _downgrade_command_events(engine: Engine) -> None:
    if "jarvis_command_events" not in inspect(engine).get_table_names():
        return
    with engine.begin() as connection:
        if connection.execute(select(db.command_events.c.command_id).limit(1)).first():
            raise RuntimeError(
                "Cannot downgrade 002_durable_command_events while command event history exists."
            )
    db.command_events.drop(engine, checkfirst=True)


def _upgrade_runtime_event_journal(engine: Engine) -> None:
    db.runtime_streams.create(engine, checkfirst=True)
    db.runtime_events.create(engine, checkfirst=True)


def _downgrade_runtime_event_journal(engine: Engine) -> None:
    if "jarvis_runtime_events" not in inspect(engine).get_table_names():
        return
    with engine.begin() as connection:
        if connection.execute(select(db.runtime_events.c.event_id).limit(1)).first():
            raise RuntimeError(
                "Cannot downgrade 003_durable_runtime_event_journal while runtime history exists."
            )
    db.runtime_events.drop(engine, checkfirst=True)
    db.runtime_streams.drop(engine, checkfirst=True)


MIGRATIONS = (
    Migration("001_initial_kv_store", _upgrade_initial_store),
    Migration(
        "002_durable_command_events",
        _upgrade_command_events,
        _downgrade_command_events,
    ),
    Migration(
        "003_durable_runtime_event_journal",
        _upgrade_runtime_event_journal,
        _downgrade_runtime_event_journal,
    ),
)

MIGRATION_BY_REVISION = {migration.revision: migration for migration in MIGRATIONS}
