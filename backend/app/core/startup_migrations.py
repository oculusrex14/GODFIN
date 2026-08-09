"""Small, additive migration guard for GODFIN's local SQLite lifecycle."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.backup import create_backup
from app.models.app_setting import AppSetting
from app.models.goal import Goal
from app.models.goal_contribution import GoalContribution

SCHEMA_REVISION_KEY = "schema_revision"
CURRENT_SCHEMA_REVISION = 14


class SchemaMigrationError(RuntimeError):
    """Raised when the local schema cannot be upgraded or trusted safely."""


@dataclass(frozen=True)
class SchemaMigration:
    """One ordered, restart-safe compatibility revision."""

    revision: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    validate: Callable[[sqlite3.Connection], None]

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

_EXACT_MONEY_SHADOWS = {
    "transactions": {"amount", "raw_text", "account_id"},
    "transaction_splits": {"amount", "parent_transaction_id", "category"},
    "transfer_matches": {
        "amount",
        "debit_transaction_id",
        "credit_transaction_id",
    },
}
_MAX_MONEY_MINOR = 100000000000000000

# Each field definition is (minimum minor units, maximum minor units, nullable).
# Table signatures keep the migration from acting on intentionally minimal test
# or third-party tables that happen to share a generic column name.
_PRODUCT_EXACT_MONEY_SHADOWS = {
    "goals": (
        {"id", "name", "deadline_date", "target_amount", "current_saved"},
        {
            "target_amount": (1, _MAX_MONEY_MINOR, False),
            "current_saved": (0, _MAX_MONEY_MINOR, False),
            "minimum_flexible_floor": (0, _MAX_MONEY_MINOR, False),
        },
    ),
    "goal_contributions": (
        {"id", "goal_id", "amount", "entry_type", "source_type"},
        {"amount": (-_MAX_MONEY_MINOR, _MAX_MONEY_MINOR, False)},
    ),
    "goal_contribution_suggestions": (
        {"id", "transaction_id", "amount", "deposit_type", "evidence"},
        {"amount": (1, _MAX_MONEY_MINOR, False)},
    ),
    "income_sources": (
        {"id", "source_name", "expected_amount", "frequency"},
        {
            "expected_amount": (1, _MAX_MONEY_MINOR, True),
            "last_detected_amount": (1, _MAX_MONEY_MINOR, True),
        },
    ),
    "subscriptions": (
        {"id", "name", "amount", "currency", "frequency"},
        {"amount": (1, _MAX_MONEY_MINOR, False)},
    ),
    "recurring_patterns": (
        {"id", "merchant_normalized", "avg_amount", "frequency"},
        {
            "avg_amount": (1, _MAX_MONEY_MINOR, False),
            "amount_stddev": (0, _MAX_MONEY_MINOR, True),
        },
    ),
    "subscription_suggestions": (
        {"id", "recurring_pattern_id", "merchant", "avg_amount", "frequency"},
        {"avg_amount": (1, _MAX_MONEY_MINOR, False)},
    ),
    "monthly_aggregates": (
        {
            "id",
            "month",
            "total_spend",
            "total_income",
            "fixed_total",
            "semi_flexible_total",
            "flexible_total",
            "transfer_total",
            "recurring_total",
        },
        {
            "total_spend": (0, _MAX_MONEY_MINOR, False),
            "total_income": (0, _MAX_MONEY_MINOR, False),
            "fixed_total": (0, _MAX_MONEY_MINOR, False),
            "semi_flexible_total": (0, _MAX_MONEY_MINOR, False),
            "flexible_total": (0, _MAX_MONEY_MINOR, False),
            "transfer_total": (0, _MAX_MONEY_MINOR, False),
            "recurring_total": (0, _MAX_MONEY_MINOR, False),
        },
    ),
}

_INCOME_SOURCE_COLUMNS = {
    "next_expected_date": "DATE",
    "enforce_current_month": "BOOLEAN NOT NULL DEFAULT 0",
}

_SUBSCRIPTION_BASE_COLUMNS = {
    "currency": "VARCHAR(3) NOT NULL DEFAULT 'INR'",
}

_SUBSCRIPTION_FX_COLUMNS = {
    "fx_rate_to_inr": "NUMERIC",
    "fx_rate_source": "TEXT",
    "fx_rate_source_url": "TEXT",
    "fx_rate_as_of": "DATE",
    "fx_rate_fetched_at": "DATETIME",
}

_NET_WORTH_ITEM_FX_COLUMNS = {
    "fx_source_currency": "TEXT",
    "fx_base_currency": "TEXT",
    "fx_rate_source": "TEXT",
    "fx_rate_source_url": "TEXT",
    "fx_rate_as_of": "DATE",
    "fx_rate_fetched_at": "DATETIME",
}

_NET_WORTH_QUOTE_FX_COLUMNS = {
    "fx_rate_source": "TEXT",
    "fx_rate_source_url": "TEXT",
    "fx_rate_as_of": "DATE",
    "fx_rate_fetched_at": "DATETIME",
}

_FINANCIAL_GUARDS = {
    "monthly_aggregates": (
        {
            "month",
            "total_spend",
            "total_income",
            "savings_rate",
            "fixed_total",
            "semi_flexible_total",
            "flexible_total",
            "transfer_total",
            "recurring_total",
            "transaction_count",
            "is_finalized",
        },
        "length(NEW.month) = 7 "
        "AND NEW.month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' "
        "AND CAST(substr(NEW.month, 1, 4) AS INTEGER) BETWEEN 2000 AND 9999 "
        "AND CAST(substr(NEW.month, 6, 2) AS INTEGER) BETWEEN 1 AND 12 "
        "AND typeof(NEW.total_spend) IN ('integer', 'real') "
        "AND NEW.total_spend >= 0 AND NEW.total_spend <= 1000000000000000 "
        "AND typeof(NEW.total_income) IN ('integer', 'real') "
        "AND NEW.total_income >= 0 AND NEW.total_income <= 1000000000000000 "
        "AND typeof(NEW.fixed_total) IN ('integer', 'real') "
        "AND NEW.fixed_total >= 0 AND NEW.fixed_total <= 1000000000000000 "
        "AND typeof(NEW.semi_flexible_total) IN ('integer', 'real') "
        "AND NEW.semi_flexible_total >= 0 "
        "AND NEW.semi_flexible_total <= 1000000000000000 "
        "AND typeof(NEW.flexible_total) IN ('integer', 'real') "
        "AND NEW.flexible_total >= 0 "
        "AND NEW.flexible_total <= 1000000000000000 "
        "AND typeof(NEW.transfer_total) IN ('integer', 'real') "
        "AND NEW.transfer_total >= 0 "
        "AND NEW.transfer_total <= 1000000000000000 "
        "AND typeof(NEW.recurring_total) IN ('integer', 'real') "
        "AND NEW.recurring_total >= 0 "
        "AND NEW.recurring_total <= 1000000000000000 "
        "AND (NEW.savings_rate IS NULL OR "
        "(typeof(NEW.savings_rate) IN ('integer', 'real') "
        "AND NEW.savings_rate >= -1000000 AND NEW.savings_rate <= 100)) "
        "AND typeof(NEW.transaction_count) = 'integer' "
        "AND NEW.transaction_count >= 0 "
        "AND NEW.is_finalized IN (0, 1)",
    ),
    "recurring_patterns": (
        {
            "avg_amount",
            "amount_stddev",
            "frequency",
            "avg_interval_days",
            "times_detected",
            "confidence",
            "evidence_count",
            "interval_variability",
            "amount_variability",
            "detection_status",
            "is_active",
        },
        "typeof(NEW.avg_amount) IN ('integer', 'real') "
        "AND NEW.avg_amount > 0 AND NEW.avg_amount <= 1000000000000000 "
        "AND (NEW.amount_stddev IS NULL OR "
        "(typeof(NEW.amount_stddev) IN ('integer', 'real') "
        "AND NEW.amount_stddev >= 0)) "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual') "
        "AND (NEW.avg_interval_days IS NULL OR "
        "(typeof(NEW.avg_interval_days) = 'integer' "
        "AND NEW.avg_interval_days > 0)) "
        "AND typeof(NEW.times_detected) = 'integer' "
        "AND NEW.times_detected >= 2 "
        "AND typeof(NEW.confidence) IN ('integer', 'real') "
        "AND NEW.confidence >= 0 AND NEW.confidence <= 1 "
        "AND typeof(NEW.evidence_count) = 'integer' "
        "AND NEW.evidence_count >= 0 "
        "AND (NEW.interval_variability IS NULL OR "
        "(typeof(NEW.interval_variability) IN ('integer', 'real') "
        "AND NEW.interval_variability >= 0)) "
        "AND (NEW.amount_variability IS NULL OR "
        "(typeof(NEW.amount_variability) IN ('integer', 'real') "
        "AND NEW.amount_variability >= 0)) "
        "AND NEW.detection_status IN ('active', 'candidate', 'retired') "
        "AND NEW.is_active IN (0, 1) "
        "AND ((NEW.detection_status = 'active' AND NEW.is_active = 1) OR "
        "(NEW.detection_status IN ('candidate', 'retired') "
        "AND NEW.is_active = 0))",
    ),
    "subscription_suggestions": (
        {
            "avg_amount",
            "frequency",
            "status",
            "snoozed_until",
            "confirmed_subscription_id",
        },
        "typeof(NEW.avg_amount) IN ('integer', 'real') "
        "AND NEW.avg_amount > 0 AND NEW.avg_amount <= 1000000000000000 "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual') "
        "AND NEW.status IN ('pending', 'snoozed', 'ignored', 'confirmed') "
        "AND (NEW.status != 'snoozed' OR NEW.snoozed_until IS NOT NULL)",
    ),
    "subscriptions": (
        {
            "amount",
            "currency",
            "frequency",
            "fx_rate_to_inr",
            "fx_rate_source",
            "fx_rate_source_url",
            "fx_rate_as_of",
            "fx_rate_fetched_at",
        },
        "typeof(NEW.amount) IN ('integer', 'real') "
        "AND NEW.amount > 0 AND NEW.amount <= 1000000000000000 "
        "AND NEW.currency IN ('INR', 'USD', 'EUR', 'GBP') "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual') "
        "AND ((NEW.fx_rate_to_inr IS NULL "
        "AND NEW.fx_rate_source IS NULL "
        "AND NEW.fx_rate_source_url IS NULL "
        "AND NEW.fx_rate_as_of IS NULL "
        "AND NEW.fx_rate_fetched_at IS NULL) OR "
        "(typeof(NEW.fx_rate_to_inr) IN ('integer', 'real') "
        "AND NEW.fx_rate_to_inr > 0 "
        "AND NEW.fx_rate_to_inr <= 1000000000 "
        "AND length(NEW.fx_rate_source) > 0 "
        "AND length(NEW.fx_rate_source_url) > 0 "
        "AND NEW.fx_rate_as_of IS NOT NULL "
        "AND NEW.fx_rate_fetched_at IS NOT NULL))",
    ),
    "income_sources": (
        {"expected_amount", "frequency"},
        "(NEW.expected_amount IS NULL OR "
        "(typeof(NEW.expected_amount) IN ('integer', 'real') "
        "AND NEW.expected_amount > 0 "
        "AND NEW.expected_amount <= 1000000000000000)) "
        "AND NEW.frequency IN ('monthly', 'quarterly', 'annual', "
        "'one_time', 'biweekly', 'irregular')",
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
        "AND NEW.pressure_level IN ('minimal', 'moderate', 'aggressive')",
    ),
    "goal_contributions": (
        {"amount", "entry_type"},
        "typeof(NEW.amount) IN ('integer', 'real') "
        "AND NEW.amount >= -1000000000000000 "
        "AND NEW.amount <= 1000000000000000 "
        "AND ((NEW.entry_type = 'deposit' AND NEW.amount > 0) "
        "OR (NEW.entry_type = 'withdrawal' AND NEW.amount < 0))",
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
            "fx_source_currency",
            "fx_base_currency",
            "fx_rate_source",
            "fx_rate_source_url",
            "fx_rate_as_of",
            "fx_rate_fetched_at",
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
        "AND NEW.currency = upper(NEW.currency) "
        "AND ((NEW.fx_source_currency IS NULL "
        "AND NEW.fx_base_currency IS NULL "
        "AND NEW.fx_rate_source IS NULL "
        "AND NEW.fx_rate_source_url IS NULL "
        "AND NEW.fx_rate_as_of IS NULL "
        "AND NEW.fx_rate_fetched_at IS NULL) OR "
        "(length(NEW.fx_source_currency) = 3 "
        "AND NEW.fx_source_currency = upper(NEW.fx_source_currency) "
        "AND length(NEW.fx_base_currency) = 3 "
        "AND NEW.fx_base_currency = upper(NEW.fx_base_currency) "
        "AND length(NEW.fx_rate_source) > 0 "
        "AND length(NEW.fx_rate_source_url) > 0 "
        "AND NEW.fx_rate_as_of IS NOT NULL "
        "AND NEW.fx_rate_fetched_at IS NOT NULL))",
    ),
    "net_worth_quotes": (
        {
            "unit_price",
            "quote_currency",
            "exchange_rate_to_base",
            "total_value_base",
            "base_currency",
            "fx_rate_source",
            "fx_rate_source_url",
            "fx_rate_as_of",
            "fx_rate_fetched_at",
        },
        "typeof(NEW.unit_price) IN ('integer', 'real') "
        "AND NEW.unit_price > 0 AND NEW.unit_price <= 1000000000000000 "
        "AND typeof(NEW.exchange_rate_to_base) IN ('integer', 'real') "
        "AND NEW.exchange_rate_to_base > 0 "
        "AND NEW.exchange_rate_to_base <= 1000000000 "
        "AND typeof(NEW.total_value_base) IN ('integer', 'real') "
        "AND NEW.total_value_base >= 0 "
        "AND NEW.total_value_base <= 1000000000000000 "
        "AND length(NEW.quote_currency) = 3 "
        "AND NEW.quote_currency = upper(NEW.quote_currency) "
        "AND length(NEW.base_currency) = 3 "
        "AND NEW.base_currency = upper(NEW.base_currency) "
        "AND ((NEW.fx_rate_source IS NULL "
        "AND NEW.fx_rate_source_url IS NULL "
        "AND NEW.fx_rate_as_of IS NULL "
        "AND NEW.fx_rate_fetched_at IS NULL) OR "
        "(length(NEW.fx_rate_source) > 0 "
        "AND length(NEW.fx_rate_source_url) > 0 "
        "AND NEW.fx_rate_as_of IS NOT NULL "
        "AND NEW.fx_rate_fetched_at IS NOT NULL))",
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
        "'cashback', 'adjustment', 'excluded')",
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
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        }
        if not required_columns.issubset(columns):
            continue
        for operation in ("INSERT", "UPDATE"):
            trigger_name = f"trg_{table}_financial_guard_{operation.lower()}"
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


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> dict[str, tuple]:
    return {
        row[1]: row
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _add_missing_columns(
    connection: sqlite3.Connection,
    table: str,
    definitions: dict[str, str],
) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return
    existing = _table_columns(connection, table)
    for column, definition in definitions.items():
        if column not in existing:
            connection.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}'
            )


def _apply_revision_11(connection: sqlite3.Connection) -> None:
    """Consolidate every compatibility repair from pre-registry builds."""
    for table, columns in (
        ("income_sources", _INCOME_SOURCE_COLUMNS),
        ("recurring_patterns", _RECURRING_PATTERN_COLUMNS),
        ("transactions", _TRANSACTION_COLUMNS),
        ("subscriptions", _SUBSCRIPTION_BASE_COLUMNS),
        ("subscriptions", _SUBSCRIPTION_FX_COLUMNS),
        ("net_worth_items", _NET_WORTH_ITEM_FX_COLUMNS),
        ("net_worth_quotes", _NET_WORTH_QUOTE_FX_COLUMNS),
    ):
        _add_missing_columns(connection, table, columns)

    audit_columns = _table_columns(connection, "audit_sessions")
    if audit_columns:
        required = {"id", "period_year", "period_month", "status", "created_at"}
        missing = required.difference(audit_columns)
        if missing:
            raise SchemaMigrationError(
                "The audit schema is incomplete and cannot be upgraded safely."
            )
        # Older releases could leave both the previous finalized session and
        # its replacement draft/finalized session active. Keep only the newest
        # row authoritative before installing the invariant.
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


def _validate_revision_11(connection: sqlite3.Connection) -> None:
    for table, columns in (
        ("income_sources", _INCOME_SOURCE_COLUMNS),
        ("recurring_patterns", _RECURRING_PATTERN_COLUMNS),
        ("transactions", _TRANSACTION_COLUMNS),
        ("subscriptions", _SUBSCRIPTION_BASE_COLUMNS),
        ("subscriptions", _SUBSCRIPTION_FX_COLUMNS),
        ("net_worth_items", _NET_WORTH_ITEM_FX_COLUMNS),
        ("net_worth_quotes", _NET_WORTH_QUOTE_FX_COLUMNS),
    ):
        existing = _table_columns(connection, table)
        if existing and not set(columns).issubset(existing):
            raise SchemaMigrationError(
                f"The {table} schema did not satisfy revision 11 postconditions."
            )

    audit_columns = _table_columns(connection, "audit_sessions")
    if audit_columns:
        index = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='uq_audit_sessions_active_period'"
        ).fetchone()
        if not index:
            raise SchemaMigrationError(
                "The audit-period uniqueness invariant was not installed."
            )


def _delete_duplicate_monthly_aggregates(
    connection: sqlite3.Connection,
) -> None:
    if not _table_columns(connection, "monthly_aggregates"):
        return
    rows = connection.execute(
        "SELECT id, month, account_id FROM monthly_aggregates "
        "ORDER BY month, account_id, is_finalized DESC, "
        "COALESCE(computed_at, '') DESC, rowid DESC"
    ).fetchall()
    seen: set[tuple[str, Optional[str]]] = set()
    duplicate_ids: list[str] = []
    for aggregate_id, month, account_id in rows:
        key = (month, account_id)
        if key in seen:
            duplicate_ids.append(aggregate_id)
        else:
            seen.add(key)
    for aggregate_id in duplicate_ids:
        connection.execute(
            "DELETE FROM monthly_aggregates WHERE id=?",
            (aggregate_id,),
        )


def _suggestion_priority(row: tuple) -> tuple:
    status_priority = {
        "confirmed": 0,
        "pending": 1,
        "snoozed": 2,
        "ignored": 3,
    }
    return (
        -status_priority.get(row[2], 4),
        1 if row[3] else 0,
        row[4] or "",
        row[5] or "",
        row[6],
    )


def _merge_recurring_pattern_suggestions(
    connection: sqlite3.Connection,
    keeper_id: str,
    duplicate_ids: list[str],
) -> None:
    if not duplicate_ids or not _table_columns(connection, "subscription_suggestions"):
        return
    pattern_ids = [keeper_id, *duplicate_ids]
    placeholders = ", ".join("?" for _ in pattern_ids)
    suggestions = connection.execute(
        "SELECT id, recurring_pattern_id, status, confirmed_subscription_id, "
        "updated_at, created_at, rowid FROM subscription_suggestions "
        f"WHERE recurring_pattern_id IN ({placeholders})",
        pattern_ids,
    ).fetchall()
    if not suggestions:
        return
    winner = max(suggestions, key=_suggestion_priority)
    for suggestion in suggestions:
        if suggestion[0] != winner[0]:
            connection.execute(
                "DELETE FROM subscription_suggestions WHERE id=?",
                (suggestion[0],),
            )
    if winner[1] != keeper_id:
        connection.execute(
            "UPDATE subscription_suggestions SET recurring_pattern_id=? WHERE id=?",
            (keeper_id, winner[0]),
        )


def _delete_duplicate_recurring_patterns(
    connection: sqlite3.Connection,
) -> None:
    if not _table_columns(connection, "recurring_patterns"):
        return
    rows = connection.execute(
        "SELECT id, merchant_normalized, account_id FROM recurring_patterns "
        "ORDER BY merchant_normalized, account_id, is_active DESC, "
        "CASE detection_status "
        "WHEN 'active' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END, "
        "evidence_count DESC, COALESCE(last_occurrence, '') DESC, "
        "COALESCE(created_at, '') DESC, rowid DESC"
    ).fetchall()
    grouped: dict[tuple[str, Optional[str]], list[str]] = {}
    for pattern_id, merchant, account_id in rows:
        grouped.setdefault((merchant, account_id), []).append(pattern_id)
    for pattern_ids in grouped.values():
        keeper_id, *duplicate_ids = pattern_ids
        if not duplicate_ids:
            continue
        _merge_recurring_pattern_suggestions(
            connection,
            keeper_id,
            duplicate_ids,
        )
        placeholders = ", ".join("?" for _ in duplicate_ids)
        connection.execute(
            f"DELETE FROM recurring_patterns WHERE id IN ({placeholders})",
            duplicate_ids,
        )


def _reject_duplicate_gmail_message_ids(
    connection: sqlite3.Connection,
) -> None:
    columns = _table_columns(connection, "transactions")
    if not columns or "email_message_id" not in columns:
        return
    duplicate = connection.execute(
        "SELECT email_message_id FROM transactions "
        "WHERE email_message_id IS NOT NULL "
        "GROUP BY email_message_id HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone()
    if duplicate:
        raise SchemaMigrationError(
            "Duplicate Gmail message identities require review before GODFIN "
            "can enforce ingestion idempotency."
        )


def _apply_revision_12(connection: sqlite3.Connection) -> None:
    """Install race-safe identities for derived and Gmail-ingested rows."""
    _delete_duplicate_monthly_aggregates(connection)
    _delete_duplicate_recurring_patterns(connection)
    _reject_duplicate_gmail_message_ids(connection)

    if _table_columns(connection, "monthly_aggregates"):
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_monthly_aggregates_global_month "
            "ON monthly_aggregates(month) WHERE account_id IS NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_monthly_aggregates_account_month "
            "ON monthly_aggregates(month, account_id) "
            "WHERE account_id IS NOT NULL"
        )
    if _table_columns(connection, "recurring_patterns"):
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_recurring_patterns_global_merchant "
            "ON recurring_patterns(merchant_normalized) "
            "WHERE account_id IS NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_recurring_patterns_account_merchant "
            "ON recurring_patterns(merchant_normalized, account_id) "
            "WHERE account_id IS NOT NULL"
        )
    transaction_columns = _table_columns(connection, "transactions")
    if "email_message_id" in transaction_columns:
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_transactions_email_message_id "
            "ON transactions(email_message_id) "
            "WHERE email_message_id IS NOT NULL"
        )
    _install_financial_guards(connection)


def _validate_revision_12(connection: sqlite3.Connection) -> None:
    expected_indexes = {
        "monthly_aggregates": {
            "uq_monthly_aggregates_global_month",
            "uq_monthly_aggregates_account_month",
        },
        "recurring_patterns": {
            "uq_recurring_patterns_global_merchant",
            "uq_recurring_patterns_account_merchant",
        },
    }
    transaction_columns = _table_columns(connection, "transactions")
    if "email_message_id" in transaction_columns:
        expected_indexes["transactions"] = {
            "uq_transactions_email_message_id"
        }
    for table, names in expected_indexes.items():
        if not _table_columns(connection, table):
            continue
        installed = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name=?",
                (table,),
            ).fetchall()
        }
        missing = names.difference(installed)
        if missing:
            raise SchemaMigrationError(
                f"The {table} identity indexes were not installed: "
                f"{', '.join(sorted(missing))}."
            )

    _reject_duplicate_gmail_message_ids(connection)
    for table in (
        "monthly_aggregates",
        "recurring_patterns",
        "subscription_suggestions",
    ):
        if not _table_columns(connection, table):
            continue
        for operation in ("insert", "update"):
            trigger_name = f"trg_{table}_financial_guard_{operation}"
            trigger = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger_name,),
            ).fetchone()
            if not trigger:
                raise SchemaMigrationError(
                    f"The {table} write guard was not installed."
                )


def _exact_money_table_is_supported(
    connection: sqlite3.Connection,
    table: str,
    required_columns: set[str],
) -> bool:
    columns = _table_columns(connection, table)
    return bool(columns) and required_columns.issubset(columns)


def _install_exact_money_guard(
    connection: sqlite3.Connection,
    table: str,
) -> None:
    invalid = (
        "NEW.amount_minor IS NULL "
        "OR typeof(NEW.amount_minor) <> 'integer' "
        "OR NEW.amount_minor <= 0 "
        f"OR NEW.amount_minor > {_MAX_MONEY_MINOR} "
        "OR CAST(ROUND(NEW.amount * 100, 0) AS INTEGER) "
        "<> NEW.amount_minor"
    )
    for operation in ("insert", "update"):
        trigger = f"trg_{table}_exact_money_{operation}"
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute(
            f"CREATE TRIGGER {trigger} "
            f"BEFORE {operation.upper()} ON {table} "
            f"FOR EACH ROW WHEN {invalid} BEGIN "
            f"SELECT RAISE(ABORT, 'GODFIN exact-money invariant failed: {table}'); "
            "END"
        )


def _apply_revision_13(connection: sqlite3.Connection) -> None:
    for table, required_columns in _EXACT_MONEY_SHADOWS.items():
        if not _exact_money_table_is_supported(
            connection,
            table,
            required_columns,
        ):
            continue
        columns = _table_columns(connection, table)
        invalid = connection.execute(
            f"SELECT COUNT(*) FROM {table} "
            "WHERE amount IS NULL "
            "OR typeof(amount) NOT IN ('integer', 'real') "
            "OR amount <= 0 OR amount > 1000000000000000 "
            "OR ABS(amount * 100 - ROUND(amount * 100, 0)) > 0.000001"
        ).fetchone()[0]
        if invalid:
            raise SchemaMigrationError(
                f"The {table} table contains {invalid} amount value(s) "
                "that cannot be converted to exact minor units safely."
            )
        if "amount_minor" not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN amount_minor INTEGER"
            )
        connection.execute(
            f"UPDATE {table} SET amount_minor = "
            "CAST(ROUND(amount * 100, 0) AS INTEGER) "
            "WHERE amount_minor IS NULL"
        )
        _install_exact_money_guard(connection, table)


def _validate_revision_13(connection: sqlite3.Connection) -> None:
    for table, required_columns in _EXACT_MONEY_SHADOWS.items():
        if not _exact_money_table_is_supported(
            connection,
            table,
            required_columns,
        ):
            continue
        if "amount_minor" not in _table_columns(connection, table):
            raise SchemaMigrationError(
                f"The {table} exact-money column was not installed."
            )
        invalid = connection.execute(
            f"SELECT COUNT(*) FROM {table} "
            "WHERE amount_minor IS NULL "
            "OR typeof(amount_minor) <> 'integer' "
            "OR amount_minor <= 0 "
            f"OR amount_minor > {_MAX_MONEY_MINOR} "
            "OR CAST(ROUND(amount * 100, 0) AS INTEGER) <> amount_minor"
        ).fetchone()[0]
        if invalid:
            raise SchemaMigrationError(
                f"The {table} table contains {invalid} invalid exact-money row(s)."
            )
        for operation in ("insert", "update"):
            trigger = f"trg_{table}_exact_money_{operation}"
            installed = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger,),
            ).fetchone()
            if not installed:
                raise SchemaMigrationError(
                    f"The {table} exact-money guard was not installed."
                )


def _product_exact_money_table_is_supported(
    connection: sqlite3.Connection,
    table: str,
    signature: set[str],
    fields: dict[str, tuple[int, int, bool]],
) -> bool:
    columns = _table_columns(connection, table)
    required = signature.union(fields)
    return bool(columns) and required.issubset(columns)


def _legacy_money_invalid_sql(
    field: str,
    minimum_minor: int,
    maximum_minor: int,
    nullable: bool,
    *,
    prefix: str = "",
) -> str:
    legacy = f'{prefix}"{field}"'
    invalid_value = (
        f"typeof({legacy}) NOT IN ('integer', 'real') "
        f"OR ({legacy} * 100) < {minimum_minor} "
        f"OR ({legacy} * 100) > {maximum_minor} "
        f"OR ABS(({legacy} * 100) - ROUND({legacy} * 100, 0)) > 0.000001"
    )
    if nullable:
        return f"({legacy} IS NOT NULL AND ({invalid_value}))"
    return f"({legacy} IS NULL OR {invalid_value})"


def _exact_money_invalid_sql(
    field: str,
    minimum_minor: int,
    maximum_minor: int,
    nullable: bool,
    *,
    prefix: str = "",
) -> str:
    legacy = f'{prefix}"{field}"'
    exact = f'{prefix}"{field}_minor"'
    populated_invalid = (
        f"{_legacy_money_invalid_sql(field, minimum_minor, maximum_minor, False, prefix=prefix)} "
        f"OR {exact} IS NULL "
        f"OR typeof({exact}) <> 'integer' "
        f"OR {exact} < {minimum_minor} "
        f"OR {exact} > {maximum_minor} "
        f"OR CAST(ROUND({legacy} * 100, 0) AS INTEGER) <> {exact}"
    )
    if nullable:
        return (
            f"(({legacy} IS NULL AND {exact} IS NOT NULL) OR "
            f"({legacy} IS NOT NULL AND ({populated_invalid})))"
        )
    return f"({populated_invalid})"


def _install_product_exact_money_guard(
    connection: sqlite3.Connection,
    table: str,
    fields: dict[str, tuple[int, int, bool]],
) -> None:
    invalid_conditions = [
        _exact_money_invalid_sql(
            field,
            minimum_minor,
            maximum_minor,
            nullable,
            prefix="NEW.",
        )
        for field, (minimum_minor, maximum_minor, nullable) in fields.items()
    ]
    if table == "goal_contributions":
        invalid_conditions.append(
            "((NEW.entry_type = 'deposit' AND NEW.amount_minor <= 0) OR "
            "(NEW.entry_type = 'withdrawal' AND NEW.amount_minor >= 0))"
        )
    invalid = " OR ".join(invalid_conditions)
    for operation in ("insert", "update"):
        trigger = f"trg_{table}_product_exact_money_{operation}"
        connection.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
        connection.execute(
            f'CREATE TRIGGER "{trigger}" '
            f'BEFORE {operation.upper()} ON "{table}" '
            f"FOR EACH ROW WHEN {invalid} BEGIN "
            f"SELECT RAISE(ABORT, "
            f"'GODFIN exact-money invariant failed: {table}'); "
            "END"
        )


def _apply_revision_14(connection: sqlite3.Connection) -> None:
    """Extend authoritative minor-unit storage to remaining product totals."""
    supported: list[tuple[str, dict[str, tuple[int, int, bool]]]] = []
    for table, (signature, fields) in _PRODUCT_EXACT_MONEY_SHADOWS.items():
        if not _product_exact_money_table_is_supported(
            connection,
            table,
            signature,
            fields,
        ):
            continue
        supported.append((table, fields))
        for field, (minimum_minor, maximum_minor, nullable) in fields.items():
            invalid = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE '
                f"{_legacy_money_invalid_sql(field, minimum_minor, maximum_minor, nullable)}"
            ).fetchone()[0]
            if invalid:
                raise SchemaMigrationError(
                    f"The {table}.{field} field contains {invalid} value(s) "
                    "that cannot be converted to exact minor units safely."
                )

    for table, fields in supported:
        columns = _table_columns(connection, table)
        for field, (minimum_minor, maximum_minor, nullable) in fields.items():
            exact = f"{field}_minor"
            if exact in columns:
                existing_invalid = connection.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{exact}" IS NOT NULL '
                    f"AND ({_exact_money_invalid_sql(field, minimum_minor, maximum_minor, nullable)})"
                ).fetchone()[0]
                if existing_invalid:
                    raise SchemaMigrationError(
                        f"The {table}.{exact} field contains {existing_invalid} "
                        "invalid exact-money value(s)."
                    )
            else:
                connection.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "{exact}" INTEGER'
                )
            connection.execute(
                f'UPDATE "{table}" SET "{exact}" = '
                f'CAST(ROUND("{field}" * 100, 0) AS INTEGER) '
                f'WHERE "{field}" IS NOT NULL AND "{exact}" IS NULL'
            )
        _install_product_exact_money_guard(connection, table, fields)


def _validate_revision_14(connection: sqlite3.Connection) -> None:
    for table, (signature, fields) in _PRODUCT_EXACT_MONEY_SHADOWS.items():
        if not _product_exact_money_table_is_supported(
            connection,
            table,
            signature,
            fields,
        ):
            continue
        columns = _table_columns(connection, table)
        for field, (minimum_minor, maximum_minor, nullable) in fields.items():
            exact = f"{field}_minor"
            if exact not in columns:
                raise SchemaMigrationError(
                    f"The {table}.{exact} exact-money column was not installed."
                )
            invalid = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE '
                f"{_exact_money_invalid_sql(field, minimum_minor, maximum_minor, nullable)}"
            ).fetchone()[0]
            if invalid:
                raise SchemaMigrationError(
                    f"The {table}.{field} field contains {invalid} invalid "
                    "exact-money row(s)."
                )
        for operation in ("insert", "update"):
            trigger = f"trg_{table}_product_exact_money_{operation}"
            installed = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger,),
            ).fetchone()
            if not installed:
                raise SchemaMigrationError(
                    f"The {table} product exact-money guard was not installed."
                )


MIGRATION_REGISTRY = (
    SchemaMigration(
        revision=11,
        name="consolidate_pre_registry_compatibility_repairs",
        apply=_apply_revision_11,
        validate=_validate_revision_11,
    ),
    SchemaMigration(
        revision=12,
        name="enforce_derived_and_ingestion_identities",
        apply=_apply_revision_12,
        validate=_validate_revision_12,
    ),
    SchemaMigration(
        revision=13,
        name="introduce_exact_ledger_minor_units",
        apply=_apply_revision_13,
        validate=_validate_revision_13,
    ),
    SchemaMigration(
        revision=14,
        name="extend_exact_product_minor_units",
        apply=_apply_revision_14,
        validate=_validate_revision_14,
    ),
)


def read_schema_revision(db_path: str) -> int:
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return 0

    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            has_settings = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
            ).fetchone()
            if not has_settings:
                return 0
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key=?",
                (SCHEMA_REVISION_KEY,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise SchemaMigrationError(
            "The local database schema revision could not be read safely."
        ) from exc

    if not row:
        return 0
    try:
        revision = int(row[0])
    except (TypeError, ValueError) as exc:
        raise SchemaMigrationError(
            "The local database contains an invalid schema revision."
        ) from exc
    if revision < 0:
        raise SchemaMigrationError(
            "The local database contains an invalid schema revision."
        )
    return revision


def backup_before_schema_update(db_path: str, backup_dir: str) -> Optional[str]:
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return None
    revision = read_schema_revision(str(path))
    if revision > CURRENT_SCHEMA_REVISION:
        raise SchemaMigrationError(
            "This database was created by a newer GODFIN version. "
            "Install that version instead of opening it here."
        )
    if revision == CURRENT_SCHEMA_REVISION:
        return None
    return create_backup(str(path), backup_dir)


def apply_additive_schema_updates(db_path: str) -> None:
    """Apply the ordered compatibility registry in one SQLite transaction."""
    path = Path(db_path).expanduser()
    if not path.exists() or path.stat().st_size == 0:
        return

    revision = read_schema_revision(str(path))
    if revision > CURRENT_SCHEMA_REVISION:
        raise SchemaMigrationError(
            "This database was created by a newer GODFIN version. "
            "Install that version instead of opening it here."
        )

    connection = sqlite3.connect(path, timeout=1.0)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        for migration in MIGRATION_REGISTRY:
            if revision < migration.revision:
                migration.apply(connection)
            migration.validate(connection)

        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if quick_check != ("ok",):
            raise SchemaMigrationError(
                "The local database failed its migration integrity check."
            )
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchone()
        if foreign_key_errors is not None:
            raise SchemaMigrationError(
                "The local database contains broken relationships after migration."
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def validate_schema_postconditions(db_path: str) -> None:
    """Verify the recorded revision and database integrity after startup."""
    revision = read_schema_revision(db_path)
    if revision != CURRENT_SCHEMA_REVISION:
        raise SchemaMigrationError(
            "GODFIN did not finish updating the local database schema."
        )
    connection = sqlite3.connect(
        f"file:{Path(db_path).expanduser().resolve()}?mode=ro",
        uri=True,
    )
    try:
        for migration in MIGRATION_REGISTRY:
            migration.validate(connection)
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise SchemaMigrationError(
                "The local database failed its post-migration integrity check."
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise SchemaMigrationError(
                "The local database contains broken relationships."
            )
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
    if setting is not None:
        try:
            existing_revision = int(setting.value)
        except (TypeError, ValueError) as exc:
            raise SchemaMigrationError(
                "The local database contains an invalid schema revision."
            ) from exc
        if existing_revision > CURRENT_SCHEMA_REVISION:
            raise SchemaMigrationError(
                "This database was created by a newer GODFIN version."
            )
    value = str(CURRENT_SCHEMA_REVISION)
    if setting is None:
        db.add(AppSetting(key=SCHEMA_REVISION_KEY, value=value))
    else:
        setting.value = value
    db.commit()
