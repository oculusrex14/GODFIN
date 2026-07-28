from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


def create_backup(db_path: str, backup_dir: str) -> str:
    """Create a safe online backup of the SQLite database."""
    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'godfin_backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    dest.close()
    source.close()

    prune_backups(backup_dir)
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


def restore_backup(backup_path: str, db_path: str) -> bool:
    """Restore a backup by copying it over the live database."""
    if not os.path.exists(backup_path):
        return False

    source = sqlite3.connect(backup_path)
    dest = sqlite3.connect(db_path)
    source.backup(dest)
    dest.close()
    source.close()
    return True


def _backup_timestamp(path: Path) -> datetime:
    prefix = "godfin_backup_"
    try:
        stamp = path.stem.removeprefix(prefix)
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S")
    except ValueError:
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
