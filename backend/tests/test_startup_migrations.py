import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import startup_migrations
from app.core.database import Base
from app.core.startup_migrations import (
    CURRENT_SCHEMA_REVISION,
    SchemaMigrationError,
    apply_additive_schema_updates,
    backup_before_schema_update,
    read_schema_revision,
    record_schema_revision,
    validate_schema_postconditions,
)
from app.models.app_setting import AppSetting


def test_fresh_database_post_create_pass_installs_all_registry_invariants(
    tmp_path,
):
    db_path = tmp_path / "godfin.db"

    # The first pass intentionally has no schema to update on a brand-new
    # installation. This mirrors the production lifespan ordering.
    apply_additive_schema_updates(str(db_path))
    assert not db_path.exists()

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    # The post-create pass must materialize every migration invariant before
    # the schema revision is recorded and startup validation runs.
    apply_additive_schema_updates(str(db_path))
    TestSession = sessionmaker(bind=engine)
    with TestSession() as db:
        record_schema_revision(db)
    engine.dispose()

    validate_schema_postconditions(str(db_path))
    assert read_schema_revision(str(db_path)) == CURRENT_SCHEMA_REVISION

    connection = sqlite3.connect(db_path)
    try:
        installed = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('index', 'trigger')"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "uq_monthly_aggregates_global_month",
        "uq_recurring_patterns_global_merchant",
        "trg_monthly_aggregates_financial_guard_insert",
        "trg_recurring_patterns_financial_guard_insert",
        "trg_net_worth_items_precision_guard_insert",
        "trg_recurring_patterns_provenance_insert",
    }.issubset(installed)


def test_revision_16_adds_guarded_recurring_provenance_idempotently(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE recurring_patterns (
                id TEXT PRIMARY KEY,
                merchant_normalized TEXT NOT NULL,
                account_id TEXT,
                avg_amount REAL NOT NULL,
                amount_stddev REAL,
                frequency TEXT NOT NULL,
                avg_interval_days INTEGER,
                last_occurrence DATE,
                next_expected DATE,
                times_detected INTEGER NOT NULL,
                category TEXT,
                confidence REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                interval_variability REAL,
                amount_variability REAL,
                detection_status TEXT NOT NULL,
                is_active BOOLEAN NOT NULL,
                created_at DATETIME
            );
            INSERT INTO recurring_patterns VALUES (
                'pattern-1', 'SERVICE', NULL, 499.0, 0.0, 'monthly',
                30, '2026-07-01', '2026-08-01', 4, 'UTILITIES & BILLS',
                0.9, 4, 0.0, 0.0, 'active', 1, '2026-07-01T00:00:00'
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
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(recurring_patterns)"
            )
        }
        provenance = connection.execute(
            "SELECT evidence_transaction_ids_json, detection_version "
            "FROM recurring_patterns WHERE id='pattern-1'"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE recurring_patterns "
                "SET evidence_transaction_ids_json='not-json' "
                "WHERE id='pattern-1'"
            )
    finally:
        connection.close()

    assert {
        "evidence_transaction_ids_json",
        "detection_version",
    }.issubset(columns)
    assert provenance == ("[]", "2.0")


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


def test_additive_migration_adds_net_worth_fx_provenance_columns(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE net_worth_items (
                id TEXT PRIMARY KEY, exchange_rate_to_base REAL NOT NULL
            );
            CREATE TABLE net_worth_quotes (
                id TEXT PRIMARY KEY, exchange_rate_to_base REAL NOT NULL
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
        item_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(net_worth_items)")
        }
        quote_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(net_worth_quotes)")
        }
    finally:
        connection.close()

    assert {
        "fx_source_currency",
        "fx_base_currency",
        "fx_rate_source",
        "fx_rate_source_url",
        "fx_rate_as_of",
        "fx_rate_fetched_at",
    }.issubset(item_columns)
    assert {
        "fx_rate_source",
        "fx_rate_source_url",
        "fx_rate_as_of",
        "fx_rate_fetched_at",
    }.issubset(quote_columns)


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
                CREATE TABLE net_worth_quotes (
                    id TEXT PRIMARY KEY, unit_price REAL NOT NULL,
                    quote_currency TEXT NOT NULL,
                    exchange_rate_to_base REAL NOT NULL,
                    total_value_base REAL NOT NULL,
                    base_currency TEXT NOT NULL
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
        assert len(trigger_names) == 14

        connection.execute(
            "INSERT INTO subscriptions "
            "(id, amount, currency, frequency) VALUES (?, ?, ?, ?)",
            ("valid-sub", 499, "INR", "monthly"),
        )
        connection.execute(
            "INSERT INTO income_sources "
            "(id, expected_amount, frequency) VALUES (?, ?, ?)",
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
            "INSERT INTO net_worth_items "
            "(id, item_type, asset_class, valuation_mode, quantity, "
            "manual_value, exchange_rate_to_base, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("valid-item", "asset", "cash", "manual", 1, 1000, 1, "INR"),
        )
        connection.execute(
            "INSERT INTO net_worth_quotes "
            "(id, unit_price, quote_currency, exchange_rate_to_base, "
            "total_value_base, base_currency) VALUES (?, ?, ?, ?, ?, ?)",
            ("valid-quote", 100, "USD", 80, 8000, "INR"),
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
                "INSERT INTO income_sources "
                "(id, expected_amount, frequency) VALUES (?, ?, ?)",
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
                "INSERT INTO net_worth_items "
                "(id, item_type, asset_class, valuation_mode, quantity, "
                "manual_value, exchange_rate_to_base, currency) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad-item", "asset", "invented", "manual", 1, 1000, 1, "INR"),
            ),
            (
                "INSERT INTO net_worth_quotes "
                "(id, unit_price, quote_currency, exchange_rate_to_base, "
                "total_value_base, base_currency, fx_rate_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("bad-quote", 100, "USD", 80, 8000, "INR", "partial"),
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
        "ck_net_worth_items_fx_provenance_complete",
        "ck_net_worth_quotes_fx_provenance_complete",
    }
    with db_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
    schema = "\n".join(row[0] or "" for row in rows)

    assert expected.issubset({name for name in expected if name in schema})


def test_revision_11_absorbs_former_seed_schema_changes(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE income_sources (
                id TEXT PRIMARY KEY,
                expected_amount REAL,
                frequency TEXT NOT NULL
            );
            CREATE TABLE subscriptions (
                id TEXT PRIMARY KEY,
                amount REAL NOT NULL,
                frequency TEXT NOT NULL
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
        income_columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(income_sources)")
        }
        subscription_columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(subscriptions)")
        }
    finally:
        connection.close()

    assert {"next_expected_date", "enforce_current_month"}.issubset(income_columns)
    assert income_columns["enforce_current_month"][3] == 1
    assert income_columns["enforce_current_month"][4] == "0"
    assert subscription_columns["currency"][3] == 1
    assert subscription_columns["currency"][4] == "'INR'"


def test_future_schema_revision_fails_closed_before_backup_or_migration(tmp_path):
    db_path = tmp_path / "godfin.db"
    backup_dir = tmp_path / "backups"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("schema_revision", str(CURRENT_SCHEMA_REVISION + 1)),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(SchemaMigrationError, match="newer GODFIN version"):
        backup_before_schema_update(str(db_path), str(backup_dir))
    with pytest.raises(SchemaMigrationError, match="newer GODFIN version"):
        apply_additive_schema_updates(str(db_path))

    assert not backup_dir.exists()


@pytest.mark.parametrize("revision", ["not-a-number", "-1"])
def test_invalid_schema_revision_fails_closed(tmp_path, revision):
    db_path = tmp_path / "godfin.db"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("schema_revision", revision),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(SchemaMigrationError, match="invalid schema revision"):
        read_schema_revision(str(db_path))
    with pytest.raises(SchemaMigrationError, match="invalid schema revision"):
        apply_additive_schema_updates(str(db_path))


def test_failed_revision_rolls_back_prior_schema_changes(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            f"""
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                    INSERT INTO app_settings VALUES (
                    'schema_revision', '10'
                );
            CREATE TABLE subscriptions (
                id TEXT PRIMARY KEY,
                amount REAL NOT NULL,
                frequency TEXT NOT NULL
            );
            CREATE TABLE audit_sessions (
                id TEXT PRIMARY KEY,
                period_year INTEGER NOT NULL,
                period_month INTEGER NOT NULL,
                created_at TEXT
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(SchemaMigrationError, match="audit schema is incomplete"):
        apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        subscription_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(subscriptions)")
        }
    finally:
        connection.close()
    assert "currency" not in subscription_columns


def test_schema_postconditions_require_current_recorded_revision(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_legacy_database(db_path)

    with pytest.raises(SchemaMigrationError, match="did not finish updating"):
        validate_schema_postconditions(str(db_path))


def test_locked_database_fails_without_partial_schema_changes(tmp_path, monkeypatch):
    db_path = tmp_path / "godfin.db"
    _create_legacy_database(db_path)
    real_connect = sqlite3.connect
    lock_connection = real_connect(db_path)
    lock_connection.execute("BEGIN EXCLUSIVE")

    def connect_without_waiting(*args, **kwargs):
        kwargs.setdefault("timeout", 0.05)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(startup_migrations.sqlite3, "connect", connect_without_waiting)
    try:
        with pytest.raises(SchemaMigrationError, match="could not be read safely"):
            apply_additive_schema_updates(str(db_path))
    finally:
        lock_connection.rollback()
        lock_connection.close()

    connection = real_connect(db_path)
    try:
        assert read_schema_revision(str(db_path)) == 0
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()

    assert tables == {"app_settings"}


def _create_revision_11_identity_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO app_settings VALUES ('schema_revision', '11');

            CREATE TABLE monthly_aggregates (
                id TEXT PRIMARY KEY,
                month TEXT NOT NULL,
                account_id TEXT,
                total_spend REAL NOT NULL DEFAULT 0,
                total_income REAL NOT NULL DEFAULT 0,
                savings_rate REAL,
                fixed_total REAL NOT NULL DEFAULT 0,
                semi_flexible_total REAL NOT NULL DEFAULT 0,
                flexible_total REAL NOT NULL DEFAULT 0,
                transfer_total REAL NOT NULL DEFAULT 0,
                recurring_total REAL NOT NULL DEFAULT 0,
                transaction_count INTEGER NOT NULL DEFAULT 0,
                is_finalized INTEGER NOT NULL DEFAULT 0,
                computed_at TEXT
            );

            CREATE TABLE recurring_patterns (
                id TEXT PRIMARY KEY,
                merchant_normalized TEXT NOT NULL,
                account_id TEXT,
                avg_amount REAL NOT NULL,
                amount_stddev REAL,
                frequency TEXT NOT NULL,
                avg_interval_days INTEGER,
                last_occurrence TEXT,
                next_expected TEXT,
                times_detected INTEGER NOT NULL DEFAULT 2,
                confidence REAL NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                interval_variability REAL,
                amount_variability REAL,
                detection_status TEXT NOT NULL DEFAULT 'active',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE subscription_suggestions (
                id TEXT PRIMARY KEY,
                recurring_pattern_id TEXT NOT NULL UNIQUE,
                avg_amount REAL NOT NULL,
                frequency TEXT NOT NULL,
                status TEXT NOT NULL,
                snoozed_until TEXT,
                confirmed_subscription_id TEXT,
                updated_at TEXT,
                created_at TEXT
            );

            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                email_message_id TEXT,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                confidence REAL,
                status TEXT NOT NULL,
                semantic_type TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_revision_12_cleans_derived_duplicates_and_installs_identities(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_revision_11_identity_fixture(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            INSERT INTO monthly_aggregates (
                id, month, account_id, is_finalized, computed_at
            ) VALUES
                ('ma-old', '2026-07', NULL, 0, '2026-08-01'),
                ('ma-new', '2026-07', NULL, 1, '2026-08-02');

            INSERT INTO recurring_patterns (
                id, merchant_normalized, account_id, avg_amount, frequency,
                times_detected, confidence, evidence_count, detection_status,
                is_active, created_at
            ) VALUES
                ('rp-old', 'NETFLIX', NULL, 499, 'monthly', 2, 0.4, 2,
                 'retired', 0, '2026-07-01'),
                ('rp-new', 'NETFLIX', NULL, 499, 'monthly', 4, 0.9, 4,
                 'active', 1, '2026-08-01');

            INSERT INTO subscription_suggestions (
                id, recurring_pattern_id, avg_amount, frequency, status,
                confirmed_subscription_id, updated_at, created_at
            ) VALUES
                ('ss-old', 'rp-old', 499, 'monthly', 'ignored', NULL,
                 '2026-07-01', '2026-07-01'),
                ('ss-new', 'rp-new', 499, 'monthly', 'confirmed', 'sub-1',
                 '2026-08-01', '2026-08-01');

            INSERT INTO transactions (
                id, email_message_id, amount, type, status, semantic_type
            ) VALUES ('tx-1', 'gmail-message-1', 499, 'debit', 'settled',
                      'expense');
            """
        )
        connection.commit()
    finally:
        connection.close()

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        aggregate_ids = connection.execute(
            "SELECT id FROM monthly_aggregates"
        ).fetchall()
        pattern_ids = connection.execute(
            "SELECT id FROM recurring_patterns"
        ).fetchall()
        suggestion = connection.execute(
            "SELECT id, recurring_pattern_id FROM subscription_suggestions"
        ).fetchone()
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert aggregate_ids == [("ma-new",)]
    assert pattern_ids == [("rp-new",)]
    assert suggestion == ("ss-new", "rp-new")
    assert {
        "uq_monthly_aggregates_global_month",
        "uq_monthly_aggregates_account_month",
        "uq_recurring_patterns_global_merchant",
        "uq_recurring_patterns_account_merchant",
        "uq_transactions_email_message_id",
    }.issubset(indexes)
    assert {
        "trg_monthly_aggregates_financial_guard_insert",
        "trg_recurring_patterns_financial_guard_insert",
        "trg_subscription_suggestions_financial_guard_insert",
    }.issubset(triggers)


def test_revision_12_duplicate_gmail_identity_rolls_back_cleanup(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_revision_11_identity_fixture(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            INSERT INTO monthly_aggregates (id, month, account_id)
            VALUES ('ma-1', '2026-07', NULL), ('ma-2', '2026-07', NULL);
            INSERT INTO transactions (
                id, email_message_id, amount, type, status, semantic_type
            ) VALUES
                ('tx-1', 'duplicate-message', 100, 'debit', 'settled',
                 'expense'),
                ('tx-2', 'duplicate-message', 100, 'debit', 'settled',
                 'expense');
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(SchemaMigrationError, match="Duplicate Gmail message"):
        apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM monthly_aggregates"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='uq_transactions_email_message_id'"
        ).fetchone() is None
    finally:
        connection.close()


def test_revision_12_legacy_guards_reject_invalid_derived_rows(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_revision_11_identity_fixture(db_path)
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="monthly_aggregates"):
            connection.execute(
                "INSERT INTO monthly_aggregates "
                "(id, month, total_spend) VALUES ('bad-month', '2026-13', -1)"
            )
        with pytest.raises(sqlite3.IntegrityError, match="recurring_patterns"):
            connection.execute(
                "INSERT INTO recurring_patterns "
                "(id, merchant_normalized, avg_amount, frequency, "
                "times_detected, confidence, evidence_count, "
                "detection_status, is_active) VALUES "
                "('bad-pattern', 'INVALID', -1, 'weekly', 1, 2, -1, "
                "'unknown', 1)"
            )
        with pytest.raises(sqlite3.IntegrityError, match="subscription_suggestions"):
            connection.execute(
                "INSERT INTO subscription_suggestions "
                "(id, recurring_pattern_id, avg_amount, frequency, status) "
                "VALUES ('bad-suggestion', 'missing', 0, 'weekly', 'unknown')"
            )
    finally:
        connection.rollback()
        connection.close()
