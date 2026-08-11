from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.startup_migrations import CURRENT_SCHEMA_REVISION, read_schema_revision
from app.models.account import Account
from app.models.app_setting import AppSetting


def test_real_lifespan_runs_migrations_seeds_services_and_shutdown(
    monkeypatch,
    tmp_path,
):
    """Exercise the production lifespan instead of the test-only bypass."""

    from app import main
    from app.core import (
        auth,
        database as database_module,
        encryption,
        llm_runtime,
        scheduler,
        startup_migrations,
    )
    from app import seed

    db_path = tmp_path / "lifespan.db"
    backup_dir = tmp_path / "backups"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    events: list[str] = []

    monkeypatch.delenv("GODFIN_TESTING", raising=False)
    monkeypatch.setenv("GODFIN_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", Session)
    monkeypatch.setattr(database_module, "SessionLocal", Session)
    monkeypatch.setattr(main, "setup_logging", lambda: events.append("logging"))

    real_initialize = encryption.initialize_encryption
    real_backup = startup_migrations.backup_before_schema_update
    real_apply = startup_migrations.apply_additive_schema_updates
    real_run_post = startup_migrations.run_post_create_migrations
    real_record = startup_migrations.record_schema_revision
    real_validate = startup_migrations.validate_schema_postconditions
    real_seed = seed.run_seeds
    real_load_token = auth.load_token_from_db

    def initialize_encryption():
        events.append("encryption")
        return real_initialize()

    def backup_before_schema_update(path: str, directory: str):
        events.append("backup_check")
        return real_backup(path, directory)

    def apply_additive_schema_updates(path: str):
        events.append("migration")
        return real_apply(path)

    def run_seeds(db):
        events.append("seeds")
        return real_seed(db)

    def run_post_create_migrations(db):
        events.append("post_create")
        return real_run_post(db)

    def record_schema_revision(db):
        events.append("record_revision")
        return real_record(db)

    def validate_schema_postconditions(path: str):
        events.append("validate_schema")
        return real_validate(path)

    def load_token_from_db(db):
        events.append("auth_state")
        return real_load_token(db)

    monkeypatch.setattr(encryption, "initialize_encryption", initialize_encryption)
    monkeypatch.setattr(
        startup_migrations,
        "backup_before_schema_update",
        backup_before_schema_update,
    )
    monkeypatch.setattr(
        startup_migrations,
        "apply_additive_schema_updates",
        apply_additive_schema_updates,
    )
    monkeypatch.setattr(
        startup_migrations,
        "run_post_create_migrations",
        run_post_create_migrations,
    )
    monkeypatch.setattr(
        startup_migrations,
        "record_schema_revision",
        record_schema_revision,
    )
    monkeypatch.setattr(
        startup_migrations,
        "validate_schema_postconditions",
        validate_schema_postconditions,
    )
    monkeypatch.setattr(main, "run_seeds", run_seeds)
    monkeypatch.setattr(auth, "load_token_from_db", load_token_from_db)
    monkeypatch.setattr(
        llm_runtime,
        "initialize_active_llm",
        lambda _db: events.append("llm"),
    )
    monkeypatch.setattr(
        scheduler,
        "start_scheduler",
        lambda _db_path, _backup_dir: events.append("scheduler_start") or True,
    )
    monkeypatch.setattr(
        scheduler,
        "stop_scheduler",
        lambda: events.append("scheduler_stop"),
    )

    async def exercise_lifespan():
        async with main.lifespan(main.app):
            assert main.app.state.lifecycle_status == "ready"
            assert main.app.state.scheduler_status == "ready"
            assert main.app.state.job_worker_status == "ready"
            with Session() as db:
                assert db.query(Account).count() == 2
                assert db.query(AppSetting).filter_by(key="is_first_run").one()

    try:
        asyncio.run(exercise_lifespan())
        assert main.app.state.lifecycle_status == "stopped"
        assert main.app.state.scheduler_status == "stopped"
        assert read_schema_revision(str(db_path)) == CURRENT_SCHEMA_REVISION
        assert events.count("migration") == 2
        assert events.index("encryption") < events.index("backup_check")
        assert events.index("backup_check") < events.index("seeds")
        assert events.index("seeds") < events.index("auth_state")
        assert events.index("auth_state") < events.index("llm")
        assert events.index("llm") < events.index("scheduler_start")
        assert events[-1] == "scheduler_stop"
    finally:
        engine.dispose()
