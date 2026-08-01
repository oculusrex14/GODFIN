import sqlite3
from pathlib import Path

from app.core.startup_migrations import (
    CURRENT_SCHEMA_REVISION,
    apply_additive_schema_updates,
    backup_before_schema_update,
    read_schema_revision,
    record_schema_revision,
)
from app.models.app_setting import AppSetting


def _create_legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE app_settings ("
            "key VARCHAR(100) PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at DATETIME"
            ")"
        )
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("is_first_run", "false"),
        )
        connection.commit()
    finally:
        connection.close()


def test_legacy_database_is_backed_up_before_schema_update(tmp_path):
    db_path = tmp_path / "godfin.db"
    backup_dir = tmp_path / "backups"
    _create_legacy_database(db_path)

    filename = backup_before_schema_update(str(db_path), str(backup_dir))

    assert filename
    assert (backup_dir / filename).exists()
    assert read_schema_revision(str(db_path)) == 0


def test_current_schema_does_not_create_redundant_backup(
    tmp_path,
    db_session,
):
    record_schema_revision(db_session)
    setting = db_session.query(AppSetting).filter_by(key="schema_revision").one()
    assert setting.value == str(CURRENT_SCHEMA_REVISION)

    # The fixture database is an in-memory URI, so exercise the reader with an
    # equivalent on-disk database carrying the current revision.
    db_path = tmp_path / "godfin.db"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("schema_revision", str(CURRENT_SCHEMA_REVISION)),
        )
        connection.commit()
    finally:
        connection.close()

    assert backup_before_schema_update(
        str(db_path),
        str(tmp_path / "backups"),
    ) is None


def test_additive_migration_adds_transaction_semantic_column(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE transactions ("
            "id VARCHAR(36) PRIMARY KEY, "
            "is_income BOOLEAN NOT NULL DEFAULT 0, "
            "is_transfer BOOLEAN NOT NULL DEFAULT 0"
            ")"
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(transactions)")
        }
    finally:
        connection.close()

    assert columns["semantic_type"][3] == 1
    assert columns["semantic_type"][4] == "'unknown'"
