from __future__ import annotations

from datetime import date
from decimal import Decimal
import sqlite3

import pytest
from sqlalchemy import func, text

from app.core.startup_migrations import (
    SchemaMigrationError,
    apply_additive_schema_updates,
)
from app.models.account import Account
from app.models.goal import Goal
from app.models.goal_contribution import (
    GoalContribution,
    GoalContributionSuggestion,
)
from app.models.income_source import IncomeSource
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.recurring_pattern import RecurringPattern
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion
from app.models.transaction import Transaction
from app.models.transaction_split import TransactionSplit
from app.models.transfer_match import TransferMatch


def _transaction(account_id: str, suffix: str, amount) -> Transaction:
    return Transaction(
        id=f"exact-{suffix}",
        date=date(2026, 8, 1),
        raw_text=f"Exact money fixture {suffix}",
        merchant_raw="EXACT MONEY",
        merchant_normalized="EXACT MONEY",
        amount=amount,
        type="debit",
        instrument="manual",
        account_id=account_id,
        source="manual",
    )


def test_transaction_money_is_stored_as_integer_minor_units(db_session):
    account = db_session.query(Account).first()
    transaction = _transaction(account.id, "ten-paise", Decimal("0.10"))
    db_session.add(transaction)
    db_session.commit()

    stored = db_session.execute(
        text(
            "SELECT amount, amount_minor, typeof(amount_minor) "
            "FROM transactions WHERE id=:id"
        ),
        {"id": transaction.id},
    ).one()

    assert transaction.amount == Decimal("0.10")
    assert stored.amount_minor == 10
    assert stored[2] == "integer"


def test_transaction_sum_is_exact_decimal(db_session):
    account = db_session.query(Account).first()
    db_session.add_all(
        [
            _transaction(account.id, "point-one", Decimal("0.10")),
            _transaction(account.id, "point-two", Decimal("0.20")),
        ]
    )
    db_session.commit()

    total = db_session.query(func.sum(Transaction.amount)).scalar()

    assert total == Decimal("0.30")
    assert isinstance(total, Decimal)


def test_split_and_transfer_amounts_use_exact_minor_units(db_session):
    account = db_session.query(Account).first()
    debit = _transaction(account.id, "debit", Decimal("100.10"))
    credit = _transaction(account.id, "credit", Decimal("100.10"))
    credit.type = "credit"
    split = TransactionSplit(
        id="exact-split",
        parent_transaction=debit,
        amount=Decimal("40.05"),
        category="SHOPPING",
    )
    match = TransferMatch(
        id="exact-match",
        debit_transaction_id=debit.id,
        credit_transaction_id=credit.id,
        amount=Decimal("100.10"),
        date_gap_days=0,
        confidence=1.0,
        status="confirmed",
    )
    db_session.add_all([debit, credit, split, match])
    db_session.commit()

    rows = db_session.execute(
        text(
            "SELECT "
            "(SELECT amount_minor FROM transaction_splits WHERE id='exact-split'), "
            "(SELECT amount_minor FROM transfer_matches WHERE id='exact-match')"
        )
    ).one()

    assert split.amount == Decimal("40.05")
    assert match.amount == Decimal("100.10")
    assert rows == (4005, 10010)


def test_money_rounds_half_up_once_at_the_storage_boundary(db_session):
    account = db_session.query(Account).first()
    transaction = _transaction(account.id, "half-paise", Decimal("1.005"))
    db_session.add(transaction)
    db_session.commit()

    assert transaction.amount == Decimal("1.01")
    assert db_session.execute(
        text("SELECT amount_minor FROM transactions WHERE id=:id"),
        {"id": transaction.id},
    ).scalar_one() == 101


def test_repeated_cent_aggregation_remains_exact(db_session):
    account = db_session.query(Account).first()
    db_session.add_all(
        [
            _transaction(account.id, f"cent-{index}", Decimal("0.01"))
            for index in range(1000)
        ]
    )
    db_session.commit()

    total = db_session.query(func.sum(Transaction.amount)).scalar()

    assert total == Decimal("10.00")


def test_product_money_models_store_authoritative_minor_units(db_session):
    account = db_session.query(Account).first()
    source = _transaction(account.id, "goal-suggestion", Decimal("30.30"))
    goal = Goal(
        id="exact-goal",
        name="Exact goal",
        target_amount=Decimal("1000.10"),
        current_saved=Decimal("50.05"),
        deadline_date=date(2027, 8, 1),
        minimum_flexible_floor=Decimal("5000.20"),
    )
    contribution = GoalContribution(
        id="exact-contribution",
        goal_id=goal.id,
        amount=Decimal("-10.01"),
        contribution_date=date(2026, 8, 2),
        entry_type="withdrawal",
    )
    contribution_suggestion = GoalContributionSuggestion(
        id="exact-contribution-suggestion",
        transaction_id=source.id,
        goal_id=goal.id,
        amount=Decimal("30.30"),
        deposit_type="FD",
        evidence="Exact-money test",
        confidence=0.9,
    )
    income = IncomeSource(
        id="exact-income",
        source_name="Exact income",
        expected_amount=None,
        last_detected_amount=Decimal("700.07"),
        frequency="monthly",
    )
    subscription = Subscription(
        id="exact-subscription",
        name="Exact subscription",
        amount=Decimal("99.99"),
    )
    pattern = RecurringPattern(
        id="exact-pattern",
        merchant_normalized="EXACT RECURRING",
        account_id=account.id,
        avg_amount=Decimal("199.99"),
        amount_stddev=Decimal("10.01"),
        frequency="monthly",
        avg_interval_days=30,
        times_detected=3,
        confidence=0.9,
        evidence_count=3,
    )
    subscription_suggestion = SubscriptionSuggestion(
        id="exact-subscription-suggestion",
        recurring_pattern_id=pattern.id,
        merchant="EXACT RECURRING",
        avg_amount=Decimal("199.99"),
        frequency="monthly",
    )
    aggregate = MonthlyAggregate(
        id="exact-aggregate",
        month="2098-01",
        account_id=account.id,
        total_spend=Decimal("0.10"),
        total_income=Decimal("0.20"),
        fixed_total=Decimal("0.30"),
        semi_flexible_total=Decimal("0.40"),
        flexible_total=Decimal("0.50"),
        transfer_total=Decimal("0.60"),
        recurring_total=Decimal("0.70"),
    )
    db_session.add_all([source, goal, income, subscription, pattern, aggregate])
    db_session.flush()
    db_session.add_all(
        [contribution, contribution_suggestion, subscription_suggestion]
    )
    db_session.commit()

    goal_row = db_session.execute(
        text(
            "SELECT target_amount_minor, current_saved_minor, "
            "minimum_flexible_floor_minor FROM goals WHERE id='exact-goal'"
        )
    ).one()
    contribution_rows = db_session.execute(
        text(
            "SELECT "
            "(SELECT amount_minor FROM goal_contributions "
            "WHERE id='exact-contribution'), "
            "(SELECT amount_minor FROM goal_contribution_suggestions "
            "WHERE id='exact-contribution-suggestion')"
        )
    ).one()
    product_row = db_session.execute(
        text(
            "SELECT "
            "(SELECT last_detected_amount_minor FROM income_sources "
            "WHERE id='exact-income'), "
            "(SELECT amount_minor FROM subscriptions "
            "WHERE id='exact-subscription'), "
            "(SELECT avg_amount_minor FROM recurring_patterns "
            "WHERE id='exact-pattern'), "
            "(SELECT amount_stddev_minor FROM recurring_patterns "
            "WHERE id='exact-pattern'), "
            "(SELECT avg_amount_minor FROM subscription_suggestions "
            "WHERE id='exact-subscription-suggestion')"
        )
    ).one()
    aggregate_row = db_session.execute(
        text(
            "SELECT total_spend_minor, total_income_minor, fixed_total_minor, "
            "semi_flexible_total_minor, flexible_total_minor, "
            "transfer_total_minor, recurring_total_minor "
            "FROM monthly_aggregates WHERE id='exact-aggregate'"
        )
    ).one()

    assert goal.target_amount == Decimal("1000.10")
    assert goal_row == (100010, 5005, 500020)
    assert contribution_rows == (-1001, 3030)
    assert income.expected_amount is None
    assert product_row == (70007, 9999, 19999, 1001, 19999)
    assert aggregate_row == (10, 20, 30, 40, 50, 60, 70)
    assert db_session.query(func.sum(MonthlyAggregate.total_spend)).scalar() == Decimal(
        "0.10"
    )


def _create_revision_12_ledger_fixture(path, *, amount="0.10"):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            f"""
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO app_settings VALUES ('schema_revision', '12');

            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                raw_text TEXT NOT NULL,
                account_id TEXT NOT NULL,
                amount REAL NOT NULL,
                semantic_type TEXT NOT NULL DEFAULT 'unknown'
            );
            CREATE TABLE transaction_splits (
                id TEXT PRIMARY KEY,
                parent_transaction_id TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL
            );
            CREATE TABLE transfer_matches (
                id TEXT PRIMARY KEY,
                debit_transaction_id TEXT NOT NULL,
                credit_transaction_id TEXT NOT NULL,
                amount REAL NOT NULL
            );

            INSERT INTO transactions (id, raw_text, account_id, amount)
            VALUES ('tx', 'fixture', 'account', {amount});
            INSERT INTO transaction_splits VALUES ('split', 'tx', 'OTHER', 40.05);
            INSERT INTO transfer_matches VALUES ('match', 'tx', 'credit', 100.10);
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_revision_13_backfills_exact_ledger_minor_units_idempotently(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_revision_12_ledger_fixture(db_path)

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT amount_minor, typeof(amount_minor) FROM transactions"
        ).fetchone() == (10, "integer")
        assert connection.execute(
            "SELECT amount_minor FROM transaction_splits"
        ).fetchone() == (4005,)
        assert connection.execute(
            "SELECT amount_minor FROM transfer_matches"
        ).fetchone() == (10010,)
        with pytest.raises(
            sqlite3.IntegrityError,
            match="GODFIN exact-money invariant failed: transactions",
        ):
            connection.execute(
                "INSERT INTO transactions "
                "(id, raw_text, account_id, amount, amount_minor) "
                "VALUES ('bad', 'bad', 'account', 1.00, 99)"
            )
    finally:
        connection.close()


def test_revision_13_rejects_ambiguous_sub_cent_legacy_amount(tmp_path):
    db_path = tmp_path / "godfin.db"
    _create_revision_12_ledger_fixture(db_path, amount="1.005")

    with pytest.raises(
        SchemaMigrationError,
        match="cannot be converted to exact minor units safely",
    ):
        apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(transactions)")
        }
        assert "amount_minor" not in columns
    finally:
        connection.close()


def _create_revision_11_product_money_fixture(path):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO app_settings VALUES ('schema_revision', '11');

            CREATE TABLE goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_saved REAL NOT NULL,
                deadline_date DATE NOT NULL,
                annual_return_rate REAL NOT NULL,
                minimum_flexible_floor REAL NOT NULL,
                pressure_level TEXT NOT NULL
            );
            INSERT INTO goals VALUES (
                'goal', 'Fixture', 1000.10, 50.05, '2027-08-01',
                0, 5000.20, 'moderate'
            );

            CREATE TABLE goal_contributions (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                amount REAL NOT NULL,
                entry_type TEXT NOT NULL,
                source_type TEXT NOT NULL
            );
            INSERT INTO goal_contributions VALUES (
                'contribution', 'goal', -10.01, 'withdrawal', 'manual'
            );

            CREATE TABLE goal_contribution_suggestions (
                id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                amount REAL NOT NULL,
                deposit_type TEXT NOT NULL,
                evidence TEXT NOT NULL
            );
            INSERT INTO goal_contribution_suggestions VALUES (
                'goal-suggestion', 'transaction', 30.30, 'FD', 'fixture'
            );

            CREATE TABLE income_sources (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                expected_amount REAL,
                last_detected_amount REAL,
                frequency TEXT NOT NULL,
                next_expected_date DATE,
                enforce_current_month INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO income_sources VALUES (
                'income', 'Fixture income', NULL, 700.07, 'monthly', NULL, 0
            );

            CREATE TABLE subscriptions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                frequency TEXT NOT NULL,
                fx_rate_to_inr NUMERIC,
                fx_rate_source TEXT,
                fx_rate_source_url TEXT,
                fx_rate_as_of DATE,
                fx_rate_fetched_at DATETIME
            );
            INSERT INTO subscriptions VALUES (
                'subscription', 'Fixture subscription', 99.99, 'INR',
                'monthly', NULL, NULL, NULL, NULL, NULL
            );

            CREATE TABLE recurring_patterns (
                id TEXT PRIMARY KEY,
                merchant_normalized TEXT NOT NULL,
                account_id TEXT,
                avg_amount REAL NOT NULL,
                amount_stddev REAL,
                frequency TEXT NOT NULL,
                avg_interval_days INTEGER,
                last_occurrence DATE,
                times_detected INTEGER NOT NULL,
                confidence REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                interval_variability REAL,
                amount_variability REAL,
                detection_status TEXT NOT NULL,
                is_active INTEGER NOT NULL,
                created_at DATETIME
            );
            INSERT INTO recurring_patterns VALUES (
                'pattern', 'FIXTURE', NULL, 199.99, 10.01, 'monthly', 30,
                '2026-08-01', 3, 0.9, 3, 1, 0.1, 'active', 1,
                '2026-08-01 00:00:00'
            );

            CREATE TABLE subscription_suggestions (
                id TEXT PRIMARY KEY,
                recurring_pattern_id TEXT NOT NULL,
                merchant TEXT NOT NULL,
                avg_amount REAL NOT NULL,
                frequency TEXT NOT NULL,
                status TEXT NOT NULL,
                snoozed_until DATE,
                confirmed_subscription_id TEXT,
                updated_at DATETIME,
                created_at DATETIME
            );
            INSERT INTO subscription_suggestions VALUES (
                'subscription-suggestion', 'pattern', 'FIXTURE', 199.99,
                'monthly', 'pending', NULL, NULL,
                '2026-08-01 00:00:00', '2026-08-01 00:00:00'
            );

            CREATE TABLE monthly_aggregates (
                id TEXT PRIMARY KEY,
                month TEXT NOT NULL,
                account_id TEXT,
                total_spend REAL NOT NULL,
                total_income REAL NOT NULL,
                savings_rate REAL,
                fixed_total REAL NOT NULL,
                semi_flexible_total REAL NOT NULL,
                flexible_total REAL NOT NULL,
                transfer_total REAL NOT NULL,
                recurring_total REAL NOT NULL,
                transaction_count INTEGER NOT NULL,
                is_finalized INTEGER NOT NULL,
                computed_at DATETIME
            );
            INSERT INTO monthly_aggregates VALUES (
                'aggregate', '2026-08', NULL, 0.10, 0.20, 50,
                0.30, 0.40, 0.50, 0.60, 0.70, 2, 0,
                '2026-08-01 00:00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_revision_14_backfills_product_minor_units_and_guards_idempotently(
    tmp_path,
):
    db_path = tmp_path / "godfin.db"
    _create_revision_11_product_money_fixture(db_path)

    apply_additive_schema_updates(str(db_path))
    apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT target_amount_minor, current_saved_minor, "
            "minimum_flexible_floor_minor FROM goals"
        ).fetchone() == (100010, 5005, 500020)
        assert connection.execute(
            "SELECT amount_minor FROM goal_contributions"
        ).fetchone() == (-1001,)
        assert connection.execute(
            "SELECT amount_minor FROM goal_contribution_suggestions"
        ).fetchone() == (3030,)
        assert connection.execute(
            "SELECT expected_amount_minor, last_detected_amount_minor "
            "FROM income_sources"
        ).fetchone() == (None, 70007)
        assert connection.execute(
            "SELECT amount_minor FROM subscriptions"
        ).fetchone() == (9999,)
        assert connection.execute(
            "SELECT avg_amount_minor, amount_stddev_minor "
            "FROM recurring_patterns"
        ).fetchone() == (19999, 1001)
        assert connection.execute(
            "SELECT avg_amount_minor FROM subscription_suggestions"
        ).fetchone() == (19999,)
        assert connection.execute(
            "SELECT total_spend_minor, total_income_minor, fixed_total_minor, "
            "semi_flexible_total_minor, flexible_total_minor, "
            "transfer_total_minor, recurring_total_minor "
            "FROM monthly_aggregates"
        ).fetchone() == (10, 20, 30, 40, 50, 60, 70)

        with pytest.raises(
            sqlite3.IntegrityError,
            match="GODFIN exact-money invariant failed: monthly_aggregates",
        ):
            connection.execute(
                "UPDATE monthly_aggregates SET total_spend=1.00 "
                "WHERE id='aggregate'"
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="GODFIN exact-money invariant failed: income_sources",
        ):
            connection.execute(
                "UPDATE income_sources SET expected_amount_minor=100 "
                "WHERE id='income'"
            )
    finally:
        connection.close()


def test_revision_14_rejects_ambiguous_product_sub_cent_history(tmp_path):
    db_path = tmp_path / "godfin.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO app_settings VALUES ('schema_revision', '13');
            CREATE TABLE goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_saved REAL NOT NULL,
                deadline_date DATE NOT NULL,
                minimum_flexible_floor REAL NOT NULL
            );
            INSERT INTO goals VALUES (
                'goal', 'Ambiguous', 1.005, 0, '2027-08-01', 0
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SchemaMigrationError,
        match="cannot be converted to exact minor units safely",
    ):
        apply_additive_schema_updates(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(goals)")
        }
        assert "target_amount_minor" not in columns
    finally:
        connection.close()
