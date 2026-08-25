"""Crash-safe database recovery contract for desktop application updates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.backup import create_backup, restore_backup, validate_database
from app.core.startup_migrations import read_schema_revision


JOURNAL_SCHEMA_VERSION = 1
MAX_JOURNAL_ENTRIES = 50
_VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class UpdateRecoveryError(RuntimeError):
    """An update could not establish or restore a trusted recovery point."""


def _parsed_version(value: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None]:
    match = _VERSION_PATTERN.fullmatch(str(value).strip())
    if not match:
        raise UpdateRecoveryError(f"Invalid application version: {value!r}")
    core = tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
    prerelease = match.group("prerelease")
    return core, tuple(prerelease.split(".")) if prerelease else None


def compare_versions(left: str, right: str) -> int:
    """Compare strict semantic versions, ignoring build metadata."""
    left_core, left_pre = _parsed_version(left)
    right_core, right_pre = _parsed_version(right)
    if left_core != right_core:
        return 1 if left_core > right_core else -1
    if left_pre is None or right_pre is None:
        if left_pre is right_pre:
            return 0
        return 1 if left_pre is None else -1
    for left_part, right_part in zip(left_pre, right_pre):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_part) > int(right_part) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_part > right_part else -1
    if len(left_pre) == len(right_pre):
        return 0
    return 1 if len(left_pre) > len(right_pre) else -1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_journal() -> dict[str, Any]:
    return {"schema_version": JOURNAL_SCHEMA_VERSION, "entries": []}


def _read_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_journal()
    try:
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("invalid journal file")
        document = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise UpdateRecoveryError("The update recovery journal is unreadable.") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != JOURNAL_SCHEMA_VERSION
        or not isinstance(document.get("entries"), list)
        or not all(isinstance(entry, dict) for entry in document["entries"])
    ):
        raise UpdateRecoveryError("The update recovery journal has an unknown format.")
    return document


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_journal(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document["schema_version"] = JOURNAL_SCHEMA_VERSION
    document["entries"] = document.get("entries", [])[-MAX_JOURNAL_ENTRIES:]
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise UpdateRecoveryError("The update recovery journal could not be saved.") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _append_entry(document: dict[str, Any], entry: dict[str, Any]) -> None:
    document["entries"].append(entry)
    document["entries"] = document["entries"][-MAX_JOURNAL_ENTRIES:]


def _trusted_backup(root: Path, filename: str, expected_sha256: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise UpdateRecoveryError("The update recovery snapshot path is invalid.")
    candidate = (root / filename).resolve()
    if candidate.parent != root.resolve() or not candidate.is_file():
        raise UpdateRecoveryError("The required update recovery snapshot is missing.")
    validate_database(candidate)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or ""):
        raise UpdateRecoveryError("The update recovery snapshot has no trusted digest.")
    if _sha256(candidate) != expected_sha256:
        raise UpdateRecoveryError("The update recovery snapshot failed its digest check.")
    return candidate


def _backup_record(
    *,
    kind: str,
    status: str,
    current_version: str,
    target_version: str,
    backup_path: Path,
    source_schema_revision: int,
) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "kind": kind,
        "status": status,
        "current_version": current_version,
        "target_version": target_version,
        "source_schema_revision": source_schema_revision,
        "backup_filename": backup_path.name,
        "backup_sha256": _sha256(backup_path),
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def prepare_update_transition(
    *,
    db_path: str,
    backup_dir: str,
    journal_path: str,
    current_version: str,
    target_version: str,
) -> dict[str, Any]:
    """Create the exact recovery state required before installing an update."""
    direction = compare_versions(target_version, current_version)
    if direction == 0:
        raise UpdateRecoveryError("The downloaded update is already installed.")

    live_database = Path(db_path).expanduser()
    recovery_root = Path(backup_dir).expanduser() / "update-recovery"
    snapshot_root = recovery_root / "snapshots"
    safety_root = recovery_root / "safety" / "preserved"
    automatic_recovery_root = recovery_root / "safety" / "automatic"
    journal_file = Path(journal_path).expanduser()
    document = _read_journal(journal_file)

    if direction > 0:
        transition_directory = f"{current_version}_to_{target_version}"
        transition_root = snapshot_root / transition_directory
        backup_name = create_backup(str(live_database), str(transition_root))
        backup_path = transition_root / backup_name
        entry = _backup_record(
            kind="upgrade_snapshot",
            status="prepared",
            current_version=current_version,
            target_version=target_version,
            backup_path=backup_path,
            source_schema_revision=read_schema_revision(str(backup_path)),
        )
        entry["backup_directory"] = transition_directory
        _append_entry(document, entry)
        _write_journal(journal_file, document)
        return {
            "direction": "upgrade",
            "snapshot": backup_name,
            "source_schema_revision": entry["source_schema_revision"],
        }

    snapshot_entry = next(
        (
            entry
            for entry in reversed(document["entries"])
            if entry.get("kind") == "upgrade_snapshot"
            and entry.get("current_version") == target_version
            and entry.get("target_version") == current_version
            and entry.get("status") in {"prepared", "completed"}
        ),
        None,
    )
    if snapshot_entry is None:
        raise UpdateRecoveryError(
            "Rollback is allowed only to the immediate predecessor with its verified pre-upgrade snapshot."
        )
    snapshot_directory = str(snapshot_entry.get("backup_directory") or "")
    if not snapshot_directory or Path(snapshot_directory).name != snapshot_directory:
        raise UpdateRecoveryError("The rollback snapshot directory is invalid.")
    snapshot = _trusted_backup(
        snapshot_root / snapshot_directory,
        str(snapshot_entry.get("backup_filename") or ""),
        str(snapshot_entry.get("backup_sha256") or ""),
    )
    snapshot_revision = read_schema_revision(str(snapshot))
    if snapshot_revision != snapshot_entry.get("source_schema_revision"):
        raise UpdateRecoveryError("The rollback snapshot schema evidence does not match.")

    safety_name = create_backup(str(live_database), str(safety_root))
    safety_path = safety_root / safety_name
    rollback_entry = _backup_record(
        kind="rollback_restore",
        status="prepared",
        current_version=current_version,
        target_version=target_version,
        backup_path=safety_path,
        source_schema_revision=read_schema_revision(str(safety_path)),
    )
    rollback_entry["restored_snapshot_filename"] = snapshot.name
    rollback_entry["restored_snapshot_sha256"] = snapshot_entry["backup_sha256"]
    _append_entry(document, rollback_entry)
    _write_journal(journal_file, document)

    try:
        if not restore_backup(
            str(snapshot),
            str(live_database),
            recovery_dir=str(automatic_recovery_root),
            quiesced=True,
        ):
            raise UpdateRecoveryError("The rollback snapshot could not be restored.")
        if read_schema_revision(str(live_database)) != snapshot_revision:
            raise UpdateRecoveryError("The restored rollback schema does not match its evidence.")
        rollback_entry["status"] = "restored"
        rollback_entry["restored_at_utc"] = (
            datetime.now(UTC).replace(microsecond=0).isoformat()
        )
        _write_journal(journal_file, document)
    except Exception as exc:
        try:
            restore_backup(
                str(safety_path),
                str(live_database),
                recovery_dir=str(automatic_recovery_root),
                quiesced=True,
            )
            rollback_entry["status"] = "aborted"
            _write_journal(journal_file, document)
        except Exception as recovery_exc:
            raise UpdateRecoveryError(
                "Rollback preparation failed and the current database could not be recovered automatically."
            ) from recovery_exc
        if isinstance(exc, UpdateRecoveryError):
            raise
        raise UpdateRecoveryError("Rollback preparation failed safely.") from exc

    return {
        "direction": "downgrade",
        "snapshot": snapshot.name,
        "safety_backup": safety_name,
        "source_schema_revision": snapshot_revision,
    }


def recover_interrupted_transition(
    *,
    db_path: str,
    backup_dir: str,
    journal_path: str,
    current_version: str,
) -> dict[str, Any] | None:
    """Resolve an update journal before the normal backend opens SQLite."""
    journal_file = Path(journal_path).expanduser()
    document = _read_journal(journal_file)
    if not document["entries"]:
        return None
    entry = document["entries"][-1]

    if entry.get("kind") == "upgrade_snapshot" and entry.get("status") == "prepared":
        if current_version == entry.get("target_version"):
            entry["status"] = "completed"
            entry["completed_at_utc"] = datetime.now(UTC).replace(microsecond=0).isoformat()
            _write_journal(journal_file, document)
            return {"action": "upgrade_completed"}
        return None

    if (
        entry.get("kind") != "rollback_restore"
        or entry.get("status") not in {"prepared", "restored"}
    ):
        return None
    if current_version == entry.get("target_version") and entry.get("status") == "restored":
        entry["status"] = "completed"
        entry["completed_at_utc"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        _write_journal(journal_file, document)
        return {"action": "rollback_completed"}
    if current_version != entry.get("current_version"):
        raise UpdateRecoveryError(
            "An interrupted rollback journal does not match this application version."
        )

    recovery_root = Path(backup_dir).expanduser() / "update-recovery"
    safety_root = recovery_root / "safety" / "preserved"
    automatic_recovery_root = recovery_root / "safety" / "automatic"
    safety = _trusted_backup(
        safety_root,
        str(entry.get("backup_filename") or ""),
        str(entry.get("backup_sha256") or ""),
    )
    if not restore_backup(
        str(safety),
        str(Path(db_path).expanduser()),
        recovery_dir=str(automatic_recovery_root),
        quiesced=True,
    ):
        raise UpdateRecoveryError("The interrupted rollback safety backup is missing.")
    entry["status"] = "aborted"
    entry["aborted_at_utc"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    _write_journal(journal_file, document)
    return {"action": "rollback_aborted_and_current_database_restored"}
