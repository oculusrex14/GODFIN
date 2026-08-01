from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.core.audit import finalize_audit, start_audit
from app.core.product_depth import decide_transfer_match
from app.core.reconciliation import ReconciliationService
from app.core.reporting import prepare_summary_report
from app.core.statement_parser import ParsedTransaction, _finalize_savings_txn
from app.core.transaction_semantics import (
    TransactionSemantic,
    backfill_transaction_semantics,
    infer_semantic_type,
)
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.transfer_match import TransferMatch


def _transaction(
    db_session,
    *,
    account_id: str,
    transaction_date: date,
    amount: float,
    transaction_type: str,
    merchant: str,
    is_income: bool = False,
) -> Transaction:
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=transaction_date,
        raw_text=f"{merchant} {amount}",
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=transaction_type,
        instrument="bank",
        account_id=account_id,
        source="manual",
        is_income=is_income,
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def test_confirmed_transfer_pair_has_zero_income_spend_and_net_movement(
    auth_client,
    db_session,
):
    accounts = db_session.query(Account).limit(2).all()
    debit = _transaction(
        db_session,
        account_id=accounts[0].id,
        transaction_date=date(2026, 7, 10),
        amount=10_000,
        transaction_type="debit",
        merchant="Own account transfer sent",
    )
    credit = _transaction(
        db_session,
        account_id=accounts[1].id,
        transaction_date=date(2026, 7, 10),
        amount=10_000,
        transaction_type="credit",
        merchant="Own account transfer received",
        is_income=True,
    )
    match = TransferMatch(
        debit_transaction_id=debit.id,
        credit_transaction_id=credit.id,
        amount=10_000,
        date_gap_days=0,
        confidence=1.0,
        status="pending",
    )
    db_session.add(match)
    db_session.flush()

    decide_transfer_match(db_session, match, "confirm")
    db_session.commit()

    assert credit.is_income is False
    response = auth_client.get(
        "/api/v1/dashboard/stats",
        params={"month": "2026-07"},
    )
    assert response.status_code == 200
    assert response.json()["month_income"] == 0
    assert response.json()["month_spend"] == 0
    assert response.json()["account_balance"] == 0


def test_transfer_confirmation_cannot_mutate_a_finalized_period(
    db_session,
):
    accounts = db_session.query(Account).limit(2).all()
    debit = _transaction(
        db_session,
        account_id=accounts[0].id,
        transaction_date=date(2026, 6, 10),
        amount=10_000,
        transaction_type="debit",
        merchant="Own account transfer sent",
    )
    credit = _transaction(
        db_session,
        account_id=accounts[1].id,
        transaction_date=date(2026, 6, 10),
        amount=10_000,
        transaction_type="credit",
        merchant="Own account transfer received",
    )
    match = TransferMatch(
        debit_transaction_id=debit.id,
        credit_transaction_id=credit.id,
        amount=10_000,
        date_gap_days=0,
        confidence=1.0,
        status="pending",
    )
    db_session.add(match)
    audit = start_audit(db_session, 2026, 6)
    finalize_audit(db_session, audit.id)
    db_session.flush()

    with pytest.raises(Exception, match="(?i)finalized.*reopen"):
        decide_transfer_match(db_session, match, "confirm")

    assert match.status == "pending"
    assert debit.is_transfer is False
    assert credit.is_transfer is False


def test_generic_statement_credit_defaults_to_unverified_not_income():
    transaction = ReconciliationService.create_transaction_from_parsed(
        ParsedTransaction(
            date=date(2026, 7, 1),
            description="BANK CREDIT",
            amount=5_000,
            type="credit",
        ),
        account_id="example-account",
    )

    assert transaction.is_income is False


def test_statement_parser_does_not_promote_every_credit_to_income():
    transactions = []
    _finalize_savings_txn(
        {
            "date": date(2026, 7, 1),
            "narration": "BANK CREDIT",
            "deposit": 5_000,
            "withdrawal": None,
            "balance": 20_000,
        },
        transactions,
    )

    assert len(transactions) == 1
    assert transactions[0].txn_type == "credit"
    assert transactions[0].is_income is False


def test_statement_parser_keeps_deterministic_salary_as_income():
    transactions = []
    _finalize_savings_txn(
        {
            "date": date(2026, 7, 1),
            "narration": "NEFT CR-EMPLOYER-SALARY JULY 2026",
            "deposit": 75_000,
            "withdrawal": None,
            "balance": 95_000,
        },
        transactions,
    )

    assert len(transactions) == 1
    assert transactions[0].is_income is True


def test_refund_credit_is_not_verified_income():
    transactions = []
    _finalize_savings_txn(
        {
            "date": date(2026, 7, 1),
            "narration": "CRV POS-1234XXXX5678-MERCHANT REFUND",
            "deposit": 750,
            "withdrawal": None,
            "balance": 20_750,
        },
        transactions,
    )

    assert len(transactions) == 1
    assert transactions[0].is_income is False
    assert transactions[0].semantic_type == TransactionSemantic.REFUND.value


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("SALARY JULY 2026", TransactionSemantic.INCOME.value),
        ("SAVINGS INTEREST CREDIT", TransactionSemantic.INCOME.value),
        ("INTERESTING STORE CREDIT", TransactionSemantic.UNKNOWN.value),
        ("MERCHANT REFUND", TransactionSemantic.REFUND.value),
        ("CARD REVERSAL", TransactionSemantic.REVERSAL.value),
        ("REWARD CASHBACK", TransactionSemantic.CASHBACK.value),
        ("TRAVEL REIMBURSEMENT", TransactionSemantic.REIMBURSEMENT.value),
        ("GENERIC BANK CREDIT", TransactionSemantic.UNKNOWN.value),
    ],
)
def test_credit_semantics_require_specific_evidence(description, expected):
    assert infer_semantic_type(
        transaction_type="credit",
        text_parts=(description,),
    ) == expected


def test_report_uses_one_verified_income_and_spending_definition(db_session):
    account = db_session.query(Account).first()
    salary = _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 1),
        amount=75_000,
        transaction_type="credit",
        merchant="Salary",
        is_income=True,
    )
    salary.category = "INCOME"
    salary.subcategory = "Salary"

    refund = _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 2),
        amount=1_000,
        transaction_type="credit",
        merchant="Merchant refund",
        is_income=True,
    )
    refund.category = "INCOME"
    refund.subcategory = "Refund"

    _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 3),
        amount=500,
        transaction_type="credit",
        merchant="Unverified credit",
        is_income=True,
    )
    expense = _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 4),
        amount=2_000,
        transaction_type="debit",
        merchant="Groceries",
    )
    expense.category = "FOOD & DINING"
    db_session.flush()

    report = prepare_summary_report(db_session, "2026-07")

    assert report["total_income"] == 75_000
    assert report["total_spend"] == 2_000


def test_semantic_backfill_clears_historic_broad_credit_flags(db_session):
    account = db_session.query(Account).first()
    generic_credit = _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 1),
        amount=5_000,
        transaction_type="credit",
        merchant="Generic bank credit",
        is_income=True,
    )
    salary = _transaction(
        db_session,
        account_id=account.id,
        transaction_date=date(2026, 7, 2),
        amount=75_000,
        transaction_type="credit",
        merchant="Salary",
        is_income=True,
    )
    salary.category = "INCOME"
    salary.subcategory = "Salary"
    salary.source = "manual"

    changed = backfill_transaction_semantics(db_session)

    assert changed >= 2
    assert generic_credit.semantic_type == TransactionSemantic.UNKNOWN.value
    assert generic_credit.is_income is False
    assert salary.semantic_type == TransactionSemantic.INCOME.value
    assert salary.is_income is True
