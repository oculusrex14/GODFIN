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
