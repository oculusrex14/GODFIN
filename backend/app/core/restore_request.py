"""One-use, desktop-mediated restore authorization for local backups."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.backup import (
    BackupError,
    restore_backup,
    validate_backup_manifest,
)
from app.core.encryption import SecretDecryptionError, decrypt
from app.core.license import get_machine_id
from app.core.license_entitlement import (
    EntitlementValidationError,
    verify_entitlement_envelope,
)


RESTORE_REQUEST_LIFETIME = timedelta(minutes=5)
_BACKUP_FILENAME = re.compile(
    r"^godfin_backup_\d{8}_\d{6}(?:_\d{6})?(?:_[A-Za-z0-9]+)?\.db$"
)


def default_restore_request_path(database_path: str | Path) -> Path:
    configured = os.environ.get("GODFIN_RESTORE_REQUEST_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path(database_path).expanduser().parent / "restore-request.json"


def _token_digest(token: str) -> str:
    return hashlib.sha256(f"godfin-restore:v1:{token}".encode()).hexdigest()


def _safe_backup_path(backup_dir: str | Path, filename: str) -> Path:
    if not _BACKUP_FILENAME.fullmatch(filename):
        raise BackupError("The selected backup name is invalid.")
    root = Path(backup_dir).expanduser().resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise BackupError("The selected backup is not available.")
    return candidate


def _write_request(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".restore-request.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _encrypted_values(connection: sqlite3.Connection) -> list[str]:
    values: list[str] = []
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "app_settings" in tables:
        rows = connection.execute(
            "SELECT value FROM app_settings "
            "WHERE key IN ('license_key', 'twelve_data_api_key') AND value <> ''"
        ).fetchall()
        values.extend(str(row[0]) for row in rows)
    if "llm_configurations" in tables:
        columns = {
            row[1]
            for row in connection.execute(
                'PRAGMA table_info("llm_configurations")'
            ).fetchall()
        }
        selected = [
            column
            for column in ("api_key", "oauth_token", "oauth_refresh_token")
            if column in columns
        ]
        if selected:
            projection = ", ".join(f'"{column}"' for column in selected)
            for row in connection.execute(
                f"SELECT {projection} FROM llm_configurations"
            ).fetchall():
                values.extend(str(value) for value in row if value)
    return values


def _validate_protected_state(database_path: Path) -> None:
    with closing(
        sqlite3.connect(
            f"{database_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=10,
        )
    ) as connection:
        for encrypted_value in _encrypted_values(connection):
            try:
                decrypt(encrypted_value)
            except SecretDecryptionError as exc:
                raise BackupError(
                    "The backup uses a different or unavailable encryption key."
                ) from exc

        row = connection.execute(
            "SELECT value FROM app_settings WHERE key='license_entitlement'"
        ).fetchone()
        if not row or not row[0]:
            return
        try:
            envelope = json.loads(row[0])
            verify_entitlement_envelope(envelope, machine_id=get_machine_id())
        except EntitlementValidationError as exc:
            if exc.code != "LICENSE_ENTITLEMENT_EXPIRED":
                raise BackupError(
                    "The backup contains license state for a different installation."
                ) from exc
        except (TypeError, json.JSONDecodeError) as exc:
            raise BackupError("The backup license state is invalid.") from exc


def prepare_restore_request(
    *,
    backup_dir: str | Path,
    filename: str,
    request_path: str | Path,
    maximum_schema_revision: int,
    now: datetime | None = None,
) -> dict[str, object]:
    backup_path = _safe_backup_path(backup_dir, filename)
    manifest = validate_backup_manifest(
        backup_path,
        require_product=True,
        maximum_schema_revision=maximum_schema_revision,
    )
    _validate_protected_state(backup_path)
    requested_at = (now or datetime.now(UTC)).astimezone(UTC)
    token = secrets.token_urlsafe(32)
    payload = {
        "schema_version": 1,
        "token_sha256": _token_digest(token),
        "backup_filename": backup_path.name,
        "backup_sha256": manifest["database_sha256"],
        "requested_at": requested_at.isoformat(),
        "expires_at": (requested_at + RESTORE_REQUEST_LIFETIME).isoformat(),
    }
    _write_request(Path(request_path).expanduser(), payload)
    return {
        "restore_token": token,
        "backup_filename": backup_path.name,
        "expires_at": payload["expires_at"],
    }


def complete_restore_request(
    *,
    backup_dir: str | Path,
    database_path: str | Path,
    request_path: str | Path,
    restore_token: str,
    maximum_schema_revision: int,
    now: datetime | None = None,
) -> dict[str, object]:
    request = Path(request_path).expanduser()
    try:
        if request.stat().st_size > 16 * 1024:
            raise ValueError("restore request is too large")
        payload = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise BackupError("The restore authorization is missing or invalid.") from exc

    required = {
        "schema_version",
        "token_sha256",
        "backup_filename",
        "backup_sha256",
        "requested_at",
        "expires_at",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise BackupError("The restore authorization is incomplete.")
    if payload.get("schema_version") != 1 or not secrets.compare_digest(
        str(payload.get("token_sha256")),
        _token_digest(restore_token),
    ):
        raise BackupError("The restore authorization is invalid.")
    try:
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
    except ValueError as exc:
        raise BackupError("The restore authorization expiry is invalid.") from exc
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if current_time > expires_at.astimezone(UTC):
        request.unlink(missing_ok=True)
        raise BackupError("The restore authorization expired. Prepare it again.")

    backup_path = _safe_backup_path(backup_dir, str(payload["backup_filename"]))
    manifest = validate_backup_manifest(
        backup_path,
        require_product=True,
        maximum_schema_revision=maximum_schema_revision,
    )
    if not secrets.compare_digest(
        str(manifest["database_sha256"]),
        str(payload["backup_sha256"]),
    ):
        raise BackupError("The selected backup changed after approval.")
    _validate_protected_state(backup_path)

    consumed = request.with_name(f".{request.name}.consuming-{secrets.token_hex(8)}")
    os.replace(request, consumed)
    try:
        restore_backup(
            str(backup_path),
            str(database_path),
            recovery_dir=str(Path(backup_dir).expanduser()),
            quiesced=True,
        )
    finally:
        consumed.unlink(missing_ok=True)
    return {
        "status": "restored",
        "backup_filename": backup_path.name,
        "recovery_backup_created": True,
    }
