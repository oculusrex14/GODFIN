from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.core.backup import (
    BackupError,
    create_backup,
    prune_backups,
    validate_backup_manifest,
)
from app.core.restore_request import (
    complete_restore_request,
    prepare_restore_request,
)


def _godfin_database(path, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE accounts (id TEXT PRIMARY KEY);
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                amount_minor INTEGER NOT NULL,
                type TEXT NOT NULL
            );
            """
        )
        connection.execute("INSERT INTO accounts(id) VALUES ('example-account')")
        connection.executemany(
            "INSERT INTO app_settings(key, value) VALUES (?, ?)",
            (("schema_revision", "17"), ("marker", marker)),
        )
        connection.execute(
            "INSERT INTO transactions(id, amount_minor, type) "
            "VALUES ('example-transaction', 12345, 'debit')"
        )


def _marker(path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT value FROM app_settings WHERE key='marker'"
        ).fetchone()[0]


def test_manifest_records_schema_and_financial_controls(tmp_path):
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    _godfin_database(source, "before")

    filename = create_backup(str(source), str(backups))
    manifest = validate_backup_manifest(
        backups / filename,
        require_product=True,
        maximum_schema_revision=17,
    )

    assert manifest["profile"] == {
        "kind": "godfin",
        "schema_revision": 17,
        "accounts": 1,
        "settings": 2,
        "transactions": 1,
        "transaction_amount_control": "12345",
        "transaction_amount_storage": "amount_minor",
        "encrypted_secret_count": 0,
        "unencrypted_secret_count": 0,
        "license_state": "free",
    }


def test_manifest_detects_database_tampering(tmp_path):
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    _godfin_database(source, "before")
    filename = create_backup(str(source), str(backups))
    backup_path = backups / filename

    with sqlite3.connect(backup_path) as connection:
        connection.execute(
            "UPDATE app_settings SET value='tampered' WHERE key='marker'"
        )

    with pytest.raises(BackupError, match="no longer match"):
        validate_backup_manifest(backup_path, require_product=True)


def test_legacy_plaintext_secret_is_backed_up_but_not_offered_for_restore(tmp_path):
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    _godfin_database(source, "before")
    with sqlite3.connect(source) as connection:
        connection.execute(
            "INSERT INTO app_settings(key, value) VALUES ('license_key', 'plaintext')"
        )

    filename = create_backup(str(source), str(backups))

    assert (backups / filename).is_file()
    with pytest.raises(BackupError, match="unprotected credential"):
        validate_backup_manifest(backups / filename, require_product=True)


def test_restore_request_is_one_use_and_preserves_pre_restore_recovery(tmp_path):
    live = tmp_path / "live.db"
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    request = tmp_path / "restore-request.json"
    _godfin_database(live, "current")
    _godfin_database(source, "backup")
    filename = create_backup(str(source), str(backups))

    prepared = prepare_restore_request(
        backup_dir=backups,
        filename=filename,
        request_path=request,
        maximum_schema_revision=17,
    )
    result = complete_restore_request(
        backup_dir=backups,
        database_path=live,
        request_path=request,
        restore_token=prepared["restore_token"],
        maximum_schema_revision=17,
    )

    assert result["status"] == "restored"
    assert _marker(live) == "backup"
    assert not request.exists()
    recovery_backups = [
        path for path in backups.glob("godfin_backup_*.db") if path.name != filename
    ]
    assert len(recovery_backups) == 1
    assert _marker(recovery_backups[0]) == "current"
    with pytest.raises(BackupError, match="missing or invalid"):
        complete_restore_request(
            backup_dir=backups,
            database_path=live,
            request_path=request,
            restore_token=prepared["restore_token"],
            maximum_schema_revision=17,
        )


def test_wrong_or_expired_restore_token_never_changes_live_database(tmp_path):
    live = tmp_path / "live.db"
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    request = tmp_path / "restore-request.json"
    _godfin_database(live, "current")
    _godfin_database(source, "backup")
    filename = create_backup(str(source), str(backups))
    requested_at = datetime(2026, 8, 16, tzinfo=UTC)

    prepared = prepare_restore_request(
        backup_dir=backups,
        filename=filename,
        request_path=request,
        maximum_schema_revision=17,
        now=requested_at,
    )
    with pytest.raises(BackupError, match="authorization is invalid"):
        complete_restore_request(
            backup_dir=backups,
            database_path=live,
            request_path=request,
            restore_token="wrong-token",
            maximum_schema_revision=17,
            now=requested_at,
        )
    assert _marker(live) == "current"

    with pytest.raises(BackupError, match="expired"):
        complete_restore_request(
            backup_dir=backups,
            database_path=live,
            request_path=request,
            restore_token=prepared["restore_token"],
            maximum_schema_revision=17,
            now=requested_at + timedelta(minutes=6),
        )
    assert _marker(live) == "current"


def test_retention_removes_matching_manifest(tmp_path):
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    _godfin_database(source, "snapshot")
    filenames = [create_backup(str(source), str(backups)) for _ in range(3)]

    prune_backups(str(backups), daily_to_keep=1, weekly_to_keep=0)

    existing = [filename for filename in filenames if (backups / filename).exists()]
    assert len(existing) == 1
    for filename in set(filenames) - set(existing):
        assert not (backups / f"{filename}.manifest.json").exists()


def test_prepare_restore_endpoint_requires_current_pin(auth_client, monkeypatch):
    from app.api.v1.endpoints import settings

    captured = {}

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        return {
            "restore_token": "a" * 43,
            "backup_filename": kwargs["filename"],
            "expires_at": "2026-08-16T12:05:00+00:00",
        }

    monkeypatch.setattr(settings, "prepare_restore_request", fake_prepare)
    wrong = auth_client.post(
        "/api/v1/settings/backups/godfin_backup_20260816_120000_test.db/prepare-restore",
        json={"pin": "0000", "confirmation": "RESTORE"},
    )
    accepted = auth_client.post(
        "/api/v1/settings/backups/godfin_backup_20260816_120000_test.db/prepare-restore",
        json={"pin": "4826", "confirmation": "RESTORE"},
    )

    assert wrong.status_code == 403
    assert accepted.status_code == 200
    assert captured["filename"].endswith("_test.db")
