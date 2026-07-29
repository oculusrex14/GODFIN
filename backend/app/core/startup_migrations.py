"""Small, additive migration guard for GODFIN's local SQLite lifecycle."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.backup import create_backup
from app.models.app_setting import AppSetting

SCHEMA_REVISION_KEY = "schema_revision"
CURRENT_SCHEMA_REVISION = 3


def read_schema_revision(db_path: str) -> int:
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return 0

    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            has_settings = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='app_settings'"
            ).fetchone()
            if not has_settings:
                return 0
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key=?",
                (SCHEMA_REVISION_KEY,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return 0

    if not row:
        return 0
    try:
        return max(0, int(row[0]))
    except (TypeError, ValueError):
        return 0


def backup_before_schema_update(db_path: str, backup_dir: str) -> Optional[str]:
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return None
    if read_schema_revision(str(path)) >= CURRENT_SCHEMA_REVISION:
        return None
    return create_backup(str(path), backup_dir)


def record_schema_revision(db: Session) -> None:
    setting = db.query(AppSetting).filter_by(key=SCHEMA_REVISION_KEY).first()
    value = str(CURRENT_SCHEMA_REVISION)
    if setting is None:
        db.add(AppSetting(key=SCHEMA_REVISION_KEY, value=value))
    else:
        setting.value = value
    db.commit()
