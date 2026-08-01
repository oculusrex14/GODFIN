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
CURRENT_SCHEMA_REVISION = 8

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

_FINANCIAL_GUARDS = {
    "subscriptions": (
        {"amount", "currency", "frequency"},
        "typeof(NEW.amount) IN ('integer', 'real') "
        "AND NEW.amount > 0 AND NEW.amount <= 1000000000000000 "
        "AND NEW.currency IN ('INR', 'USD', 'EUR', 'GBP') "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual')"
    ),
    "income_sources": (
        {"expected_amount", "frequency"},
        "(NEW.expected_amount IS NULL OR "
        "(typeof(NEW.expected_amount) IN ('integer', 'real') "
        "AND NEW.expected_amount > 0 "
        "AND NEW.expected_amount <= 1000000000000000)) "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual', "
        "'one_time', 'biweekly', 'irregular')"
    ),
    "goals": (
        {
            "target_amount",
            "current_saved",
            "annual_return_rate",
            "minimum_flexible_floor",
            "pressure_level",
        },
        "typeof(NEW.target_amount) IN ('integer', 'real') "
        "AND NEW.target_amount > 0 "
        "AND NEW.target_amount <= 1000000000000000 "
        "AND typeof(NEW.current_saved) IN ('integer', 'real') "
        "AND NEW.current_saved >= 0 "
        "AND NEW.current_saved <= 1000000000000000 "
        "AND typeof(NEW.annual_return_rate) IN ('integer', 'real') "
        "AND NEW.annual_return_rate >= 0 AND NEW.annual_return_rate <= 0.5 "
        "AND typeof(NEW.minimum_flexible_floor) IN ('integer', 'real') "
        "AND NEW.minimum_flexible_floor >= 0 "
        "AND NEW.minimum_flexible_floor <= 1000000000000000 "
        "AND NEW.pressure_level IN ('minimal', 'moderate', 'aggressive')"
    ),
    "goal_contributions": (
        {"amount", "entry_type"},
        "typeof(NEW.amount) IN ('integer', 'real') "
        "AND NEW.amount >= -1000000000000000 "
        "AND NEW.amount <= 1000000000000000 "
        "AND ((NEW.entry_type = 'deposit' AND NEW.amount > 0) "
        "OR (NEW.entry_type = 'withdrawal' AND NEW.amount < 0))"
    ),
    "net_worth_items": (
        {
            "item_type",
            "asset_class",
            "valuation_mode",
            "quantity",
            "manual_value",
            "exchange_rate_to_base",
            "currency",
        },
        "NEW.item_type IN ('asset', 'liability') "
        "AND NEW.asset_class IN ('cash', 'stock', 'etf', 'mutual_fund', "
        "'crypto', 'bond', 'metal', 'property', 'land', 'gem', "
        "'private_asset', 'debt', 'other') "
        "AND NEW.valuation_mode IN ('manual', 'market') "
        "AND typeof(NEW.quantity) IN ('integer', 'real') "
        "AND NEW.quantity > 0 AND NEW.quantity <= 1000000000000000 "
        "AND (NEW.manual_value IS NULL OR "
        "(typeof(NEW.manual_value) IN ('integer', 'real') "
        "AND NEW.manual_value >= 0 "
        "AND NEW.manual_value <= 1000000000000000)) "
        "AND typeof(NEW.exchange_rate_to_base) IN ('integer', 'real') "
        "AND NEW.exchange_rate_to_base > 0 "
        "AND NEW.exchange_rate_to_base <= 1000000000 "
        "AND length(NEW.currency) = 3 "
        "AND NEW.currency = upper(NEW.currency)"
    ),
    "transactions": (
        {"amount", "type", "confidence", "status", "semantic_type"},
        "typeof(NEW.amount) IN ('integer', 'real') "
        "AND NEW.amount > 0 AND NEW.amount <= 1000000000000000 "
        "AND NEW.type IN ('debit', 'credit') "
        "AND (NEW.confidence IS NULL OR "
        "(typeof(NEW.confidence) IN ('integer', 'real') "
        "AND NEW.confidence >= 0 AND NEW.confidence <= 1)) "
        "AND NEW.status IN ('settled', 'pending', 'deleted', 'reversed', "
        "'reversal', 'voided') "
        "AND NEW.semantic_type IN ('unknown', 'expense', 'income', "
        "'internal_transfer', 'refund', 'reimbursement', 'reversal', "
        "'cashback', 'adjustment', 'excluded')"
    ),
}


def _install_financial_guards(connection: sqlite3.Connection) -> None:
    """Install restart-safe write guards for databases created by old builds."""
    for table, (required_columns, condition) in _FINANCIAL_GUARDS.items():
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            continue
        columns = {
            row[1]
            for row in connection.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
        }
        if not required_columns.issubset(columns):
            continue
        for operation in ("INSERT", "UPDATE"):
            trigger_name = (
                f"trg_{table}_financial_guard_{operation.lower()}"
            )
            connection.execute(
                f'''CREATE TRIGGER IF NOT EXISTS "{trigger_name}"
                    BEFORE {operation} ON "{table}"
                    FOR EACH ROW
                    WHEN NOT ({condition})
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'GODFIN financial invariant failed: {table}'
                        );
                    END'''
            )


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
        _install_financial_guards(connection)
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
