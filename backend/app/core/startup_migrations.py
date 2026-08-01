"""Small, additive migration guard for GODFIN's local SQLite lifecycle."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.backup import create_backup
from app.models.app_setting import AppSetting
from app.models.goal import Goal
from app.models.goal_contribution import GoalContribution

SCHEMA_REVISION_KEY = "schema_revision"
CURRENT_SCHEMA_REVISION = 7

_RECURRING_PATTERN_COLUMNS = {
    "confidence": "REAL NOT NULL DEFAULT 0",
    "evidence_count": "INTEGER NOT NULL DEFAULT 0",
    "interval_variability": "REAL",
    "amount_variability": "REAL",
    "detection_status": "TEXT NOT NULL DEFAULT 'active'",
}

_TRANSACTION_COLUMNS = {
    "semantic_type": "TEXT NOT NULL DEFAULT 'unknown'",
}


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


def apply_additive_schema_updates(db_path: str) -> None:
    """Apply restart-safe column additions before SQLAlchemy maps the schema."""
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return

    connection = sqlite3.connect(path)
    try:
        for table, columns in (
            ("recurring_patterns", _RECURRING_PATTERN_COLUMNS),
            ("transactions", _TRANSACTION_COLUMNS),
        ):
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            existing = {
                row[1]
                for row in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            }
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}'
                    )

        audit_table = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='audit_sessions'"
        ).fetchone()
        if audit_table:
            # Older releases could leave both the previous finalized session
            # and its replacement draft/finalized session active. Keep only
            # the newest row authoritative before installing the invariant.
            active_rows = connection.execute(
                "SELECT id, period_year, period_month "
                "FROM audit_sessions "
                "WHERE status IN ('draft', 'finalized', 'locked') "
                "ORDER BY period_year, period_month, "
                "COALESCE(created_at, '') DESC, rowid DESC"
            ).fetchall()
            seen_periods: set[tuple[int, int]] = set()
            superseded_ids: list[str] = []
            for audit_id, year, month in active_rows:
                period = (year, month)
                if period in seen_periods:
                    superseded_ids.append(audit_id)
                else:
                    seen_periods.add(period)
            for audit_id in superseded_ids:
                connection.execute(
                    "UPDATE audit_sessions SET status='discarded' WHERE id=?",
                    (audit_id,),
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_audit_sessions_active_period "
                "ON audit_sessions(period_year, period_month) "
                "WHERE status IN ('draft', 'finalized', 'locked')"
            )
        connection.commit()
    finally:
        connection.close()


def run_post_create_migrations(db: Session) -> None:
    """Backfill transaction semantics and auditable opening balances."""
    from app.core.transaction_semantics import backfill_transaction_semantics

    backfill_transaction_semantics(db)
    goals = db.query(Goal).filter(Goal.current_saved > 0).all()
    for goal in goals:
        existing = (
            db.query(GoalContribution.id)
            .filter(GoalContribution.goal_id == goal.id)
            .first()
        )
        if existing:
            continue
        db.add(
            GoalContribution(
                goal_id=goal.id,
                amount=round(float(goal.current_saved), 2),
                contribution_date=goal.created_at.date(),
                entry_type="deposit",
                source_type="opening_balance",
                idempotency_key=f"opening:{goal.id}",
                note="Opening balance migrated from the existing goal total.",
            )
        )
    db.commit()


def record_schema_revision(db: Session) -> None:
    setting = db.query(AppSetting).filter_by(key=SCHEMA_REVISION_KEY).first()
    value = str(CURRENT_SCHEMA_REVISION)
    if setting is None:
        db.add(AppSetting(key=SCHEMA_REVISION_KEY, value=value))
    else:
        setting.value = value
    db.commit()
