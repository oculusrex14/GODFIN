from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from app.core import backup as backup_module


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 8, 2, 10, 15, 30, 123456)
        return value if tz is None else value.replace(tzinfo=tz)


def _database(path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES (?)", (value,))


def _value(path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM sample").fetchone()[0]


def test_two_backups_in_the_same_second_are_unique(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"
    _database(source, "first")
    monkeypatch.setattr(backup_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(backup_module, "prune_backups", lambda *_args, **_kwargs: [])

    first_name = backup_module.create_backup(str(source), str(backup_dir))
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE sample SET value = 'second'")
    second_name = backup_module.create_backup(str(source), str(backup_dir))

    assert first_name != second_name
    assert _value(backup_dir / first_name) == "first"
    assert _value(backup_dir / second_name) == "second"


def test_failed_backup_leaves_no_final_or_temporary_file(tmp_path):
    source = tmp_path / "corrupt.db"
    backup_dir = tmp_path / "backups"
    source.write_bytes(b"not a sqlite database")

    with pytest.raises(RuntimeError):
        backup_module.create_backup(str(source), str(backup_dir))

    assert list(backup_dir.glob("godfin_backup_*.db")) == []
    assert list(backup_dir.glob(".*.tmp")) == []


def test_backup_rejects_foreign_key_corruption(tmp_path):
    source = tmp_path / "foreign-key-corrupt.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
        )
        connection.execute("INSERT INTO child(parent_id) VALUES (999)")

    with pytest.raises(RuntimeError, match="foreign key"):
        backup_module.create_backup(str(source), str(backup_dir))

    assert list(backup_dir.glob("godfin_backup_*.db")) == []


def test_restore_requires_quiescence_and_creates_recovery_point(tmp_path):
    live = tmp_path / "live.db"
    source = tmp_path / "restore-source.db"
    recovery_dir = tmp_path / "recovery"
    _database(live, "before")
    _database(source, "after")

    with pytest.raises(RuntimeError, match="quiesced"):
        backup_module.restore_backup(str(source), str(live))

    assert backup_module.restore_backup(
        str(source),
        str(live),
        recovery_dir=str(recovery_dir),
        quiesced=True,
    ) is True
    assert _value(live) == "after"
    recovery_files = list(recovery_dir.glob("godfin_backup_*.db"))
    assert len(recovery_files) == 1
    assert _value(recovery_files[0]) == "before"


def test_corrupt_restore_never_changes_live_database(tmp_path):
    live = tmp_path / "live.db"
    corrupt = tmp_path / "corrupt.db"
    _database(live, "preserved")
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(RuntimeError):
        backup_module.restore_backup(
            str(corrupt),
            str(live),
            recovery_dir=str(tmp_path / "recovery"),
            quiesced=True,
        )

    assert _value(live) == "preserved"
