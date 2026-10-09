from sqlalchemy import create_engine, inspect, insert, select

from jarvis_backend import db
from jarvis_backend.schema_migrations import MIGRATIONS
from scripts import migrate_persistence


def test_persistence_schema_records_the_explicit_initial_revision(capsys):
    migrate_persistence.create_schema()

    assert db.LATEST_SCHEMA_REVISION in db.applied_migrations()
    assert migrate_persistence.check_schema() == 0
    assert f"revision {db.LATEST_SCHEMA_REVISION}" in capsys.readouterr().out


def test_fresh_database_applies_revisions_in_order(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_ready", False)

    migrate_persistence.upgrade_schema()

    assert db.applied_migrations() == [migration.revision for migration in MIGRATIONS]
    assert set(db.metadata.tables).issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_existing_key_value_schema_is_adopted_and_data_preserved(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_ready", False)
    db.kv_store.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(db.kv_store).values(
                store_name="commands",
                key="command-existing",
                value='{"command_id":"command-existing","events":[{"event":"created","timestamp":"2026-10-01T00:00:00Z"}]}',
            )
        )

    migrate_persistence.upgrade_schema()

    with engine.connect() as connection:
        stored = connection.execute(
            select(db.kv_store.c.value).where(
                db.kv_store.c.store_name == "commands",
                db.kv_store.c.key == "command-existing",
            )
        ).scalar_one()
    assert "command-existing" in stored
    assert db.applied_migrations() == [migration.revision for migration in MIGRATIONS]
    events = db.load_command_events("command-existing")
    assert len(events) == 1
    assert events[0]["sequence"] == 1
    engine.dispose()


def test_command_event_downgrade_refuses_to_discard_history(tmp_path, monkeypatch):
    from scripts.migrate_persistence import downgrade

    engine = create_engine(f"sqlite:///{tmp_path / 'downgrade.db'}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_ready", False)
    migrate_persistence.upgrade_schema()
    with engine.begin() as connection:
        connection.execute(
            insert(db.kv_store).values(
                store_name="commands",
                key="command-one",
                value='{"command_id":"command-one","events":[]}',
            )
        )
    db.append_command_event(
        "command-one",
        {
            "event_id": "event-one",
            "timestamp": "2026-10-01T00:00:00Z",
            "event": "created",
        },
    )

    try:
        downgrade("003_durable_runtime_event_journal")
        downgrade("002_durable_command_events")
    except RuntimeError as exc:
        assert "event history exists" in str(exc)
    else:
        raise AssertionError("Downgrade must preserve persisted command history.")
    engine.dispose()
