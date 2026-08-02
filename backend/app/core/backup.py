from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4


logger = logging.getLogger(__name__)


class BackupError(RuntimeError):
    """A backup or restore operation could not be completed safely."""


class BackupValidationError(BackupError):
    """A SQLite snapshot failed integrity or foreign-key validation."""


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _temporary_database_path(directory: Path, prefix: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{prefix}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    path = Path(name)
    path.chmod(0o600)
    return path


def _copy_database(source_path: Path, destination_path: Path) -> None:
    with closing(
        sqlite3.connect(_read_only_uri(source_path), uri=True, timeout=10)
    ) as source, closing(
        sqlite3.connect(str(destination_path), timeout=10)
    ) as destination:
        source.backup(destination)
        destination.commit()


def validate_database(database_path: str | Path) -> None:
    """Reject unreadable, corrupt, or referentially inconsistent snapshots."""
    path = Path(database_path).expanduser()
    if not path.is_file() or path.stat().st_size == 0:
        raise BackupValidationError("Backup validation failed: database file is missing or empty.")

    try:
        with closing(
            sqlite3.connect(_read_only_uri(path), uri=True, timeout=10)
        ) as connection:
            integrity_rows = connection.execute("PRAGMA quick_check").fetchall()
            if integrity_rows != [("ok",)]:
                raise BackupValidationError(
                    "Backup validation failed: SQLite integrity check did not pass."
                )
            foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_rows:
                raise BackupValidationError(
                    "Backup validation failed: foreign key violations were found."
                )
    except sqlite3.Error as exc:
        raise BackupValidationError(
            "Backup validation failed: database could not be read safely."
        ) from exc


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def create_backup(db_path: str, backup_dir: str) -> str:
    """Create, validate, and atomically publish an online SQLite backup."""
    source_path = Path(db_path).expanduser()
    if not source_path.is_file():
        raise BackupError("Backup could not be created because the local database is missing.")

    backup_root = Path(backup_dir).expanduser()
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"godfin_backup_{timestamp}_{uuid4().hex[:12]}.db"
    backup_path = backup_root / backup_name
    temporary_path = _temporary_database_path(backup_root, backup_name)

    try:
        _copy_database(source_path, temporary_path)
        validate_database(temporary_path)
        _fsync_file(temporary_path)
        os.replace(temporary_path, backup_path)
        backup_path.chmod(0o600)
        _fsync_directory(backup_root)
    except BackupError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("Backup could not be created safely.") from exc
    finally:
        temporary_path.unlink(missing_ok=True)

    try:
        prune_backups(str(backup_root))
    except OSError as exc:
        logger.warning("Backup retention cleanup failed: %s", exc)
    return backup_name


def list_backups(backup_dir: str) -> list:
    """List available backup files sorted by date (newest first)."""
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return []

    files = []
    for f in backup_path.glob('godfin_backup_*.db'):
        stat = f.stat()
        files.append({
            'filename': f.name,
            'size_bytes': stat.st_size,
            'created_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    files.sort(key=lambda x: x['created_at'], reverse=True)
    return files


def _remove_sqlite_sidecars(database_path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def restore_backup(
    backup_path: str,
    db_path: str,
    *,
    recovery_dir: str | None = None,
    quiesced: bool = False,
) -> bool:
    """Atomically restore a validated snapshot after the database is quiesced.

    ``quiesced=True`` is an explicit contract from the desktop lifecycle owner:
    all application sessions and background jobs must be stopped before restore.
    """
    source_path = Path(backup_path).expanduser()
    live_path = Path(db_path).expanduser()
    if not source_path.is_file():
        return False
    if not quiesced:
        raise BackupError("Database restore requires a quiesced application database.")
    if source_path.resolve() == live_path.resolve():
        raise BackupError("Backup source and live database must be different files.")

    validate_database(source_path)
    live_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path = _temporary_database_path(live_path.parent, "godfin_restore")
    rollback_path: Path | None = None
    recovery_path: Path | None = None
    replaced_live = False

    try:
        _copy_database(source_path, staged_path)
        validate_database(staged_path)
        _fsync_file(staged_path)

        if live_path.is_file():
            recovery_root = (
                Path(recovery_dir).expanduser()
                if recovery_dir
                else live_path.parent / "backups"
            )
            recovery_name = create_backup(str(live_path), str(recovery_root))
            recovery_path = recovery_root / recovery_name

        _remove_sqlite_sidecars(live_path)
        os.replace(staged_path, live_path)
        replaced_live = True
        live_path.chmod(0o600)
        _fsync_directory(live_path.parent)
        validate_database(live_path)
        return True
    except BackupError:
        if replaced_live and recovery_path and recovery_path.is_file():
            rollback_path = _temporary_database_path(live_path.parent, "godfin_rollback")
            try:
                _copy_database(recovery_path, rollback_path)
                validate_database(rollback_path)
                _remove_sqlite_sidecars(live_path)
                os.replace(rollback_path, live_path)
                _fsync_directory(live_path.parent)
            except Exception as rollback_exc:
                raise BackupError(
                    "Restore validation failed and the automatic recovery point could not be restored."
                ) from rollback_exc
        raise
    except (OSError, sqlite3.Error) as exc:
        if replaced_live and recovery_path and recovery_path.is_file():
            rollback_path = _temporary_database_path(live_path.parent, "godfin_rollback")
            try:
                _copy_database(recovery_path, rollback_path)
                validate_database(rollback_path)
                _remove_sqlite_sidecars(live_path)
                os.replace(rollback_path, live_path)
                _fsync_directory(live_path.parent)
            except Exception as rollback_exc:
                raise BackupError(
                    "Restore failed and the automatic recovery point could not be restored."
                ) from rollback_exc
        raise BackupError("Database restore could not be completed safely.") from exc
    finally:
        staged_path.unlink(missing_ok=True)
        if rollback_path is not None:
            rollback_path.unlink(missing_ok=True)


_BACKUP_NAME_PATTERN = re.compile(
    r"^godfin_backup_(?P<second>\d{8}_\d{6})"
    r"(?:_(?P<microsecond>\d{6}))?(?:_[^.]+)?$"
)


def _backup_timestamp(path: Path) -> datetime:
    match = _BACKUP_NAME_PATTERN.fullmatch(path.stem)
    if match:
        timestamp = datetime.strptime(match.group("second"), "%Y%m%d_%H%M%S")
        microsecond = match.group("microsecond")
        if microsecond:
            timestamp = timestamp.replace(microsecond=int(microsecond))
        return timestamp
    return datetime.fromtimestamp(path.stat().st_mtime)


def prune_backups(
    backup_dir: str,
    *,
    daily_to_keep: int = 7,
    weekly_to_keep: int = 4,
) -> list[str]:
    """Keep one backup for each of the newest daily and weekly buckets.

    Weekly retention is selected from backups older than the daily window, so
    the two policies do not accidentally collapse into the same files.
    """
    root = Path(backup_dir)
    if not root.exists():
        return []

    records = sorted(
        (
            (_backup_timestamp(path), path)
            for path in root.glob("godfin_backup_*.db")
            if path.is_file()
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    keep: set[Path] = set()
    daily_dates = []
    for timestamp, path in records:
        date_key = timestamp.date()
        if date_key not in daily_dates and len(daily_dates) < daily_to_keep:
            daily_dates.append(date_key)
            keep.add(path)

    daily_cutoff = min(daily_dates) if daily_dates else None
    weekly_buckets = []
    for timestamp, path in records:
        if path in keep:
            continue
        if daily_cutoff is not None and timestamp.date() >= daily_cutoff:
            continue
        week_key = timestamp.isocalendar()[:2]
        if week_key not in weekly_buckets and len(weekly_buckets) < weekly_to_keep:
            weekly_buckets.append(week_key)
            keep.add(path)

    removed = []
    for _, path in records:
        if path not in keep:
            path.unlink()
            removed.append(path.name)
    return removed
