import sqlite3
from pathlib import Path

import pytest

from app.core.startup_migrations import (
    CURRENT_SCHEMA_REVISION,
    apply_additive_schema_updates,
    backup_before_schema_update,
    read_schema_revision,
    record_schema_revision,
)
from app.models.app_setting import AppSetting


def _create_legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE app_settings ("
            "key VARCHAR(100) PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at DATETIME"
            ")"
        )
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("is_first_run", "false"),
        )
        connection.commit()
    finally:
        connection.close()


def test_legacy_database_is_backed_up_before_schema_update(tmp_path):
    db_path = tmp_path / "godfin.db"
    backup_dir = tmp_path / "backups"
    _create_legacy_database(db_path)

    filename = backup_before_schema_update(str(db_path), str(backup_dir))

    assert filename
    assert (backup_dir / filename).exists()
    assert read_schema_revision(str(db_path)) == 0


def test_current_schema_does_not_create_redundant_backup(
    tmp_path,
    db_session,
):
    record_schema_revision(db_session)
    setting = db_session.query(AppSetting).filter_by(key="schema_revision").one()
    assert setting.value == str(CURRENT_SCHEMA_REVISION)

    # The fixture database is an in-memory URI, so exercise the reader with an
    # equivalent on-disk database carrying the current revision.
    db_path = tmp_path / "godfin.db"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("schema_revision", str(CURRENT_SCHEMA_REVISION)),
        )
        connection.commit()
    finally:
        connection.close()

    assert (
        backup_before_schema_update(
            str(db_path),
            str(tmp_path / "backups"),
        )
        is None
    )


def test_additive_migration_adds_transaction_semantic_column(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE transactions ("
            "id VARCHAR(36) PRIMARY KEY, "
            "is_income BOOLEAN NOT NULL DEFAULT 0, "
            "is_transfer BOOLEAN NOT NULL DEFAULT 0"
            ")"
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(transactions)")
        }
    finally:
        connection.close()

    assert columns["semantic_type"][3] == 1
    assert columns["semantic_type"][4] == "'unknown'"


def test_additive_migration_adds_subscription_fx_provenance_columns(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE subscriptions ("
            "id TEXT PRIMARY KEY, amount REAL NOT NULL, "
            "currency TEXT NOT NULL, frequency TEXT NOT NULL"
            ")"
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(subscriptions)")
        }
    finally:
        connection.close()

    assert {
        "fx_rate_to_inr",
        "fx_rate_source",
        "fx_rate_source_url",
        "fx_rate_as_of",
        "fx_rate_fetched_at",
    }.issubset(columns)
    assert columns["fx_rate_to_inr"][3] == 0


def test_additive_migration_enforces_one_active_audit_per_period(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE audit_sessions ("
            "id TEXT PRIMARY KEY, period_year INTEGER NOT NULL, "
            "period_month INTEGER NOT NULL, status TEXT NOT NULL, "
            "created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO audit_sessions VALUES "
            "('old', 2026, 1, 'finalized', '2026-02-01T00:00:00'), "
            "('new', 2026, 1, 'draft', '2026-02-02T00:00:00')"
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT id, status FROM audit_sessions ORDER BY id"
        ).fetchall()
        index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='uq_audit_sessions_active_period'"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO audit_sessions VALUES "
                "('another', 2026, 1, 'finalized', '2026-02-03T00:00:00')"
            )
    finally:
        connection.close()

    assert rows == [("new", "draft"), ("old", "discarded")]
    assert index == ("uq_audit_sessions_active_period",)


def test_additive_migration_installs_restart_safe_financial_guards(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE subscriptions (
                id TEXT PRIMARY KEY, amount REAL NOT NULL,
                currency TEXT NOT NULL, frequency TEXT NOT NULL
            );
            CREATE TABLE income_sources (
                id TEXT PRIMARY KEY, expected_amount REAL,
                frequency TEXT NOT NULL
            );
            CREATE TABLE goals (
                id TEXT PRIMARY KEY, target_amount REAL NOT NULL,
                current_saved REAL NOT NULL, annual_return_rate REAL NOT NULL,
                minimum_flexible_floor REAL NOT NULL,
                pressure_level TEXT NOT NULL
            );
            CREATE TABLE goal_contributions (
                id TEXT PRIMARY KEY, amount REAL NOT NULL,
                entry_type TEXT NOT NULL
            );
            CREATE TABLE net_worth_items (
                id TEXT PRIMARY KEY, item_type TEXT NOT NULL,
                asset_class TEXT NOT NULL, valuation_mode TEXT NOT NULL,
                quantity REAL NOT NULL, manual_value REAL,
                exchange_rate_to_base REAL NOT NULL, currency TEXT NOT NULL
            );
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, amount REAL NOT NULL,
                type TEXT NOT NULL, confidence REAL, status TEXT NOT NULL,
                semantic_type TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        trigger_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'trg_%_financial_guard_%'"
            )
        }
        assert len(trigger_names) == 12

        connection.execute(
            "INSERT INTO subscriptions "
            "(id, amount, currency, frequency) VALUES (?, ?, ?, ?)",
            ("valid-sub", 499, "INR", "monthly"),
        )
        connection.execute(
            "INSERT INTO income_sources VALUES (?, ?, ?)",
            ("valid-income", 75000, "monthly"),
        )
        connection.execute(
            "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
            ("valid-goal", 100000, 0, 0.05, 5000, "moderate"),
        )
        connection.execute(
            "INSERT INTO goal_contributions VALUES (?, ?, ?)",
            ("valid-contribution", 1000, "deposit"),
        )
        connection.execute(
            "INSERT INTO goal_contributions VALUES (?, ?, ?)",
            ("valid-withdrawal", -250, "withdrawal"),
        )
        connection.execute(
            "INSERT INTO net_worth_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("valid-item", "asset", "cash", "manual", 1, 1000, 1, "INR"),
        )
        connection.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
            ("valid-transaction", 100, "debit", 0.9, "settled", "expense"),
        )

        invalid_inserts = [
            (
                "INSERT INTO subscriptions "
                "(id, amount, currency, frequency) VALUES (?, ?, ?, ?)",
                ("bad-sub", float("inf"), "INR", "monthly"),
            ),
            (
                "INSERT INTO subscriptions "
                "(id, amount, currency, frequency, fx_rate_to_inr) "
                "VALUES (?, ?, ?, ?, ?)",
                ("bad-fx-provenance", 499, "USD", "monthly", 80),
            ),
            (
                "INSERT INTO income_sources VALUES (?, ?, ?)",
                ("bad-income", -1, "monthly"),
            ),
            (
                "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-goal", 100000, -1, 0.05, 5000, "moderate"),
            ),
            (
                "INSERT INTO goal_contributions VALUES (?, ?, ?)",
                ("bad-contribution", 0, "deposit"),
            ),
            (
                "INSERT INTO goal_contributions VALUES (?, ?, ?)",
                ("bad-deposit-sign", -100, "deposit"),
            ),
            (
                "INSERT INTO goal_contributions VALUES (?, ?, ?)",
                ("bad-withdrawal-sign", 100, "withdrawal"),
            ),
            (
                "INSERT INTO net_worth_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad-item", "asset", "invented", "manual", 1, 1000, 1, "INR"),
            ),
            (
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-transaction", 100, "sideways", 0.9, "settled", "expense"),
            ),
        ]
        for statement, parameters in invalid_inserts:
            with pytest.raises(
                sqlite3.IntegrityError,
                match="GODFIN financial invariant failed",
            ):
                connection.execute(statement, parameters)

        with pytest.raises(
            sqlite3.IntegrityError,
            match="GODFIN financial invariant failed: transactions",
        ):
            connection.execute(
                "UPDATE transactions SET confidence=2 WHERE id=?",
                ("valid-transaction",),
            )
    finally:
        connection.close()


def test_fresh_schema_declares_financial_check_constraints(db_engine):
    expected = {
        "ck_transactions_amount_range",
        "ck_subscriptions_amount_range",
        "ck_subscriptions_fx_provenance_complete",
        "ck_income_sources_expected_amount_range",
        "ck_goals_target_amount_range",
        "ck_goal_contributions_amount_range",
        "ck_net_worth_items_manual_value_range",
    }
    with db_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
    schema = "\n".join(row[0] or "" for row in rows)

    assert expected.issubset({name for name in expected if name in schema})
