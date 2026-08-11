import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import update_recovery
from app.core.update_recovery import (
    UpdateRecoveryError,
    compare_versions,
    prepare_update_transition,
    recover_interrupted_transition,
)


def _database(path: Path, *, revision: int, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE update_fixture (
                id INTEGER PRIMARY KEY,
                marker TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO app_settings(key, value) VALUES ('schema_revision', ?)",
            (str(revision),),
        )
        connection.execute(
            "INSERT INTO update_fixture(id, marker) VALUES (1, ?)",
            (marker,),
        )


def _marker(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT marker FROM update_fixture WHERE id=1"
        ).fetchone()[0]


def _set_database_state(path: Path, *, revision: int, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE app_settings SET value=? WHERE key='schema_revision'",
            (str(revision),),
        )
        connection.execute(
            "UPDATE update_fixture SET marker=? WHERE id=1",
            (marker,),
        )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.2.0", "1.1.9", 1),
        ("1.0.0", "1.0.0", 0),
        ("1.0.0-rc.2", "1.0.0-rc.10", -1),
        ("1.0.0", "1.0.0-rc.10", 1),
        ("1.0.0+build.2", "1.0.0+build.1", 0),
    ],
)
def test_compare_versions_follows_semantic_version_order(left, right, expected):
    assert compare_versions(left, right) == expected


def test_upgrade_snapshot_and_interrupted_rollback_recover_current_data(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=15, marker="before upgrade")

    upgrade = prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
        target_version="1.1.0",
    )
    assert upgrade["direction"] == "upgrade"
    assert upgrade["source_schema_revision"] == 15

    _set_database_state(database, revision=16, marker="new-version activity")
    rollback = prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.1.0",
        target_version="1.0.0",
    )
    assert rollback["direction"] == "downgrade"
    assert _marker(database) == "before upgrade"

    recovery = recover_interrupted_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.1.0",
    )
    assert recovery == {"action": "rollback_aborted_and_current_database_restored"}
    assert _marker(database) == "new-version activity"
    document = json.loads(journal.read_text("utf-8"))
    assert document["entries"][-1]["status"] == "aborted"


def test_successful_rollback_is_completed_by_the_target_version(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=15, marker="compatible snapshot")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="2.0.0",
        target_version="2.1.0",
    )
    _set_database_state(database, revision=16, marker="newer state")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="2.1.0",
        target_version="2.0.0",
    )

    result = recover_interrupted_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="2.0.0",
    )
    assert result == {"action": "rollback_completed"}
    assert _marker(database) == "compatible snapshot"
    document = json.loads(journal.read_text("utf-8"))
    assert document["entries"][-1]["status"] == "completed"


def test_sequential_immediate_rollbacks_preserve_each_release_snapshot(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=14, marker="v1")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
        target_version="1.1.0",
    )
    _set_database_state(database, revision=15, marker="v2")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.1.0",
        target_version="1.2.0",
    )
    _set_database_state(database, revision=16, marker="v3")

    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.2.0",
        target_version="1.1.0",
    )
    recover_interrupted_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.1.0",
    )
    assert _marker(database) == "v2"

    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.1.0",
        target_version="1.0.0",
    )
    recover_interrupted_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
    )
    assert _marker(database) == "v1"


def test_downgrade_requires_the_immediate_predecessor_snapshot(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=15, marker="v1")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
        target_version="1.1.0",
    )
    _set_database_state(database, revision=16, marker="v2")

    with pytest.raises(UpdateRecoveryError, match="immediate predecessor"):
        prepare_update_transition(
            db_path=str(database),
            backup_dir=str(backups),
            journal_path=str(journal),
            current_version="1.2.0",
            target_version="1.0.0",
        )
    assert _marker(database) == "v2"


def test_tampered_snapshot_is_rejected_without_changing_live_database(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=15, marker="v1")
    upgrade = prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
        target_version="1.1.0",
    )
    snapshot = next(
        (backups / "update-recovery" / "snapshots").glob("*/*.db")
    )
    snapshot.write_bytes(snapshot.read_bytes() + b"tamper")
    _set_database_state(database, revision=16, marker="v2 remains active")

    with pytest.raises(UpdateRecoveryError, match="digest"):
        prepare_update_transition(
            db_path=str(database),
            backup_dir=str(backups),
            journal_path=str(journal),
            current_version="1.1.0",
            target_version="1.0.0",
        )
    assert _marker(database) == "v2 remains active"


def test_failed_rollback_restore_recovers_the_newer_database(tmp_path, monkeypatch):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=15, marker="v1")
    prepare_update_transition(
        db_path=str(database),
        backup_dir=str(backups),
        journal_path=str(journal),
        current_version="1.0.0",
        target_version="1.1.0",
    )
    _set_database_state(database, revision=16, marker="v2 must survive")
    real_restore = update_recovery.restore_backup
    calls = 0

    def fail_then_recover(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic restore failure")
        return real_restore(*args, **kwargs)

    monkeypatch.setattr(update_recovery, "restore_backup", fail_then_recover)
    with pytest.raises(UpdateRecoveryError, match="failed safely"):
        prepare_update_transition(
            db_path=str(database),
            backup_dir=str(backups),
            journal_path=str(journal),
            current_version="1.1.0",
            target_version="1.0.0",
        )
    assert _marker(database) == "v2 must survive"
    document = json.loads(journal.read_text("utf-8"))
    assert document["entries"][-1]["status"] == "aborted"


def test_corrupt_journal_fails_closed(tmp_path):
    database = tmp_path / "godfin.db"
    _database(database, revision=16, marker="untouched")
    journal = tmp_path / "update-recovery.json"
    journal.write_text("{not-json", "utf-8")
    with pytest.raises(UpdateRecoveryError, match="journal is unreadable"):
        recover_interrupted_transition(
            db_path=str(database),
            backup_dir=str(tmp_path / "backups"),
            journal_path=str(journal),
            current_version="1.0.0",
        )
    assert _marker(database) == "untouched"


def test_desktop_maintenance_entry_creates_upgrade_recovery_state(tmp_path):
    database = tmp_path / "godfin.db"
    backups = tmp_path / "backups"
    journal = tmp_path / "update-recovery.json"
    _database(database, revision=16, marker="packaged entry fixture")
    environment = {
        **os.environ,
        "DB_PATH": str(database),
        "GODFIN_BACKUP_DIR": str(backups),
        "GODFIN_UPDATE_RECOVERY_JOURNAL": str(journal),
    }
    result = subprocess.run(
        [
            sys.executable,
            "desktop_entry.py",
            "--prepare-update-transition",
            "--current-version",
            "1.0.0",
            "--target-version",
            "1.1.0",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["direction"] == "upgrade"
    assert journal.is_file()
    assert list((backups / "update-recovery" / "snapshots").glob("*/*.db"))
