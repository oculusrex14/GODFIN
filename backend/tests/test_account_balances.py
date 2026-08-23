from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.account_balances import (
    balance_at_date,
    record_verified_statement_controls,
)
from app.core.statement_parser import StatementParseResult, StatementTransaction
from app.models.account_balance import (
    AccountBalanceAnchor,
    AccountStatementCoverage,
)
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


def _statement(
    *,
    fingerprint: str,
    period_start: date,
    period_end: date,
    opening: str,
    closing: str,
    rows: list[tuple[date, str, str]],
) -> StatementParseResult:
    running = Decimal(opening)
    transactions: list[StatementTransaction] = []
    for transaction_date, transaction_type, raw_amount in rows:
        amount = Decimal(raw_amount)
        running += amount if transaction_type == "credit" else -amount
        transactions.append(
            StatementTransaction(
                date=transaction_date,
                description=f"{transaction_type} {raw_amount}",
                amount=float(amount),
                txn_type=transaction_type,
                closing_balance=float(running),
            )
        )
    assert running == Decimal(closing)
    return StatementParseResult(
        transactions=transactions,
        statement_type="hdfc_savings",
        parser_profile="hdfc_savings",
        recognized=True,
        reconciliation_status="passed",
        reconciliation_method="explicit_columns_and_running_balance",
        source_digest=fingerprint,
        period_start=period_start,
        period_end=period_end,
        opening_balance=float(Decimal(opening)),
        closing_balance=float(Decimal(closing)),
        total_debits=float(
            sum(Decimal(amount) for _, kind, amount in rows if kind == "debit")
        ),
        total_credits=float(
            sum(Decimal(amount) for _, kind, amount in rows if kind == "credit")
        ),
    )


def _ledger_transaction(
    db_session,
    *,
    transaction_date: date,
    transaction_type: str,
    amount: str,
) -> Transaction:
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=transaction_date,
        raw_text="Synthetic balance test row",
        merchant_raw="Synthetic balance test row",
        merchant_normalized="SYNTHETIC BALANCE TEST ROW",
        amount=Decimal(amount),
        type=transaction_type,
        instrument="statement",
        account_id=SAVINGS_ACCOUNT_ID,
        source="statement_upload",
        status="settled",
    )
    db_session.add(transaction)
    return transaction


def test_verified_statement_creates_idempotent_exact_anchors(db_session):
    statement = _statement(
        fingerprint="a" * 64,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        opening="1000.00",
        closing="950.00",
        rows=[
            (date(2026, 1, 2), "debit", "100.00"),
            (date(2026, 1, 3), "credit", "50.00"),
        ],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 1, 2),
        transaction_type="debit",
        amount="100.00",
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 1, 3),
        transaction_type="credit",
        amount="50.00",
    )

    first = record_verified_statement_controls(
        db_session, SAVINGS_ACCOUNT_ID, statement
    )
    second = record_verified_statement_controls(
        db_session, SAVINGS_ACCOUNT_ID, statement
    )
    db_session.commit()

    assert first is not None and second is not None
    assert first.id == second.id
    assert db_session.query(AccountBalanceAnchor).count() == 2
    assert db_session.query(AccountStatementCoverage).count() == 1
    january_2 = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 1, 2))
    january_31 = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 1, 31))
    assert january_2.status == "verified"
    assert january_2.balance == Decimal("900.00")
    assert january_31.status == "verified"
    assert january_31.balance == Decimal("950.00")


def test_balance_without_anchor_or_with_a_gap_is_not_claimed(db_session):
    missing = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 1, 31))
    assert missing.balance is None
    assert missing.status == "unverified_no_anchor"

    statement = _statement(
        fingerprint="b" * 64,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        opening="1000.00",
        closing="900.00",
        rows=[(date(2026, 1, 2), "debit", "100.00")],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 1, 2),
        transaction_type="debit",
        amount="100.00",
    )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, statement)
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 2, 1),
        transaction_type="debit",
        amount="20.00",
    )
    db_session.commit()

    strict = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 2, 1))
    estimate = balance_at_date(
        db_session,
        SAVINGS_ACCOUNT_ID,
        date(2026, 2, 1),
        allow_estimate=True,
    )
    assert strict.balance is None
    assert strict.status == "unverified_gap"
    assert strict.missing_ranges == ("2026-02-01/2026-02-01",)
    assert estimate.status == "estimated_partial"
    assert estimate.balance == Decimal("880.00")


def test_out_of_order_adjacent_statements_preserve_balance(db_session):
    march = _statement(
        fingerprint="c" * 64,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        opening="2000.00",
        closing="1900.00",
        rows=[(date(2026, 3, 3), "debit", "100.00")],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 3, 3),
        transaction_type="debit",
        amount="100.00",
    )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, march)

    january_february = _statement(
        fingerprint="d" * 64,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 28),
        opening="1500.00",
        closing="2000.00",
        rows=[(date(2026, 2, 1), "credit", "500.00")],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 2, 1),
        transaction_type="credit",
        amount="500.00",
    )
    record_verified_statement_controls(
        db_session, SAVINGS_ACCOUNT_ID, january_february
    )
    db_session.commit()

    february = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 2, 28))
    march_result = balance_at_date(
        db_session, SAVINGS_ACCOUNT_ID, date(2026, 3, 31)
    )
    assert february.status == "verified"
    assert february.balance == Decimal("2000.00")
    assert march_result.status == "verified"
    assert march_result.balance == Decimal("1900.00")


def test_conflicting_overlap_invalidates_both_statement_sources(db_session):
    first = _statement(
        fingerprint="e" * 64,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        opening="2000.00",
        closing="1900.00",
        rows=[(date(2026, 3, 3), "debit", "100.00")],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 3, 3),
        transaction_type="debit",
        amount="100.00",
    )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, first)
    conflicting = _statement(
        fingerprint="f" * 64,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        opening="1499.00",
        closing="1999.00",
        rows=[(date(2026, 2, 1), "credit", "500.00")],
    )
    _ledger_transaction(
        db_session,
        transaction_date=date(2026, 2, 1),
        transaction_type="credit",
        amount="500.00",
    )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, conflicting)
    db_session.commit()

    assert (
        db_session.query(AccountStatementCoverage)
        .filter(AccountStatementCoverage.status == "conflict")
        .count()
        == 2
    )
    result = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 3, 31))
    assert result.balance is None
    assert result.status == "conflict"


def test_account_balance_endpoint_exposes_provenance(auth_client):
    response = auth_client.get(
        f"/api/v1/accounts/{SAVINGS_ACCOUNT_ID}/balance",
        params={"as_of": "2026-01-31"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "balance": None,
        "currency": "INR",
        "as_of": "2026-01-31",
        "status": "unverified_no_anchor",
        "anchor_as_of": None,
        "coverage_complete": False,
        "source": None,
        "missing_ranges": [],
        "account_count": 1,
        "verified_account_count": 0,
    }


def test_exact_cents_are_preserved_across_one_thousand_rows(db_session):
    rows = [(date(2026, 4, 1), "credit", "0.01") for _ in range(1_000)]
    statement = _statement(
        fingerprint="1" * 64,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        opening="0.00",
        closing="10.00",
        rows=rows,
    )
    for _ in rows:
        _ledger_transaction(
            db_session,
            transaction_date=date(2026, 4, 1),
            transaction_type="credit",
            amount="0.01",
        )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, statement)
    db_session.commit()

    result = balance_at_date(db_session, SAVINGS_ACCOUNT_ID, date(2026, 4, 1))
    assert result.status == "verified"
    assert result.balance == Decimal("10.00")
