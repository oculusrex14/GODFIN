from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.account import Account
from app.models.audit_session import AuditSession
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.recurring_pattern import RecurringPattern
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion
from app.models.transaction import Transaction


def _transaction(account_id: str, *, transaction_id: str, message_id: str) -> Transaction:
    return Transaction(
        id=transaction_id,
        date=date(2026, 8, 1),
        raw_text=f"Gmail message {message_id}",
        amount=499,
        type="debit",
        instrument="upi",
        account_id=account_id,
        source="gmail",
        email_message_id=message_id,
        checksum_canonical="same-legitimate-canonical-checksum",
        semantic_type="expense",
    )


def test_monthly_aggregate_identity_is_enforced_for_global_and_account_rows(
    db_session,
):
    account = db_session.query(Account).first()
    db_session.add(MonthlyAggregate(month="2026-08"))
    db_session.commit()

    db_session.add(MonthlyAggregate(month="2026-08"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(MonthlyAggregate(month="2026-08", account_id=account.id))
    db_session.commit()
    db_session.add(MonthlyAggregate(month="2026-08", account_id=account.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_recurring_identity_is_enforced_for_global_and_account_rows(db_session):
    account = db_session.query(Account).first()
    base = {
        "merchant_normalized": "NETFLIX",
        "avg_amount": 499,
        "frequency": "monthly",
        "times_detected": 3,
        "confidence": 0.9,
        "evidence_count": 3,
        "detection_status": "active",
    }
    db_session.add(RecurringPattern(**base))
    db_session.commit()
    db_session.add(RecurringPattern(**base))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(RecurringPattern(account_id=account.id, **base))
    db_session.commit()
    db_session.add(RecurringPattern(account_id=account.id, **base))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_gmail_message_identity_is_unique_but_canonical_hash_is_not(db_session):
    account = db_session.query(Account).first()
    db_session.add_all(
        [
            _transaction(account.id, transaction_id="tx-1", message_id="message-1"),
            _transaction(account.id, transaction_id="tx-2", message_id="message-2"),
        ]
    )
    db_session.commit()

    db_session.add(
        _transaction(account.id, transaction_id="tx-3", message_id="message-1")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    "record",
    [
        MonthlyAggregate(month="2026-13"),
        MonthlyAggregate(month="2026-08", total_spend=-1),
        RecurringPattern(
            merchant_normalized="INVALID FREQUENCY",
            avg_amount=100,
            frequency="weekly",
            times_detected=3,
            confidence=0.8,
            evidence_count=3,
            detection_status="active",
        ),
    ],
)
def test_invalid_derived_financial_rows_are_rejected(db_session, record):
    db_session.add(record)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_subscription_suggestion_status_is_rejected(db_session):
    pattern = RecurringPattern(
        merchant_normalized="SPOTIFY",
        avg_amount=119,
        frequency="monthly",
        times_detected=3,
        confidence=0.9,
        evidence_count=3,
        detection_status="active",
    )
    db_session.add(pattern)
    db_session.commit()

    db_session.add(
        SubscriptionSuggestion(
            recurring_pattern_id=pattern.id,
            merchant="Spotify",
            avg_amount=119,
            frequency="monthly",
            status="mystery",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_account_delete_cascades_only_rebuildable_projections(db_session):
    account = Account(
        bank="Example Bank",
        account_type="savings",
        last_4_digits="7788",
        nickname="Constraint fixture",
    )
    db_session.add(account)
    db_session.flush()
    aggregate = MonthlyAggregate(month="2026-06", account_id=account.id)
    pattern = RecurringPattern(
        merchant_normalized="CASCADE SERVICE",
        account_id=account.id,
        avg_amount=100,
        frequency="monthly",
        times_detected=3,
        confidence=0.8,
        evidence_count=3,
        detection_status="active",
    )
    db_session.add_all([aggregate, pattern])
    db_session.commit()
    aggregate_id = aggregate.id
    pattern_id = pattern.id

    db_session.delete(account)
    db_session.commit()

    assert db_session.get(MonthlyAggregate, aggregate_id) is None
    assert db_session.get(RecurringPattern, pattern_id) is None


def test_account_delete_is_restricted_when_ledger_rows_exist(db_session):
    account = Account(
        bank="Example Bank",
        account_type="savings",
        last_4_digits="8899",
        nickname="Restricted fixture",
    )
    db_session.add(account)
    db_session.flush()
    transaction = _transaction(
        account.id,
        transaction_id="restricted-transaction",
        message_id="restricted-message",
    )
    db_session.add(transaction)
    db_session.commit()

    db_session.delete(account)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(Account, account.id) is not None
    assert db_session.get(Transaction, transaction.id) is not None


def test_audit_delete_preserves_ledger_and_nulls_optional_links(db_session):
    account = db_session.query(Account).first()
    audit = AuditSession(
        period_year=2026,
        period_month=5,
        status="discarded",
    )
    db_session.add(audit)
    db_session.flush()
    transaction = _transaction(
        account.id,
        transaction_id="audit-linked-transaction",
        message_id="audit-linked-message",
    )
    transaction.audit_session_id = audit.id
    aggregate = MonthlyAggregate(
        month="2026-05",
        audit_session_id=audit.id,
    )
    db_session.add_all([transaction, aggregate])
    db_session.commit()

    db_session.delete(audit)
    db_session.commit()

    db_session.refresh(transaction)
    db_session.refresh(aggregate)
    assert transaction.audit_session_id is None
    assert aggregate.audit_session_id is None


def test_recurring_delete_cascades_suggestion_and_subscription_delete_unlinks(db_session):
    pattern = RecurringPattern(
        merchant_normalized="CONFIRMED SERVICE",
        avg_amount=199,
        frequency="monthly",
        times_detected=3,
        confidence=0.9,
        evidence_count=3,
        detection_status="active",
    )
    subscription = Subscription(
        name="Confirmed service",
        amount=199,
        currency="INR",
        frequency="monthly",
    )
    db_session.add_all([pattern, subscription])
    db_session.flush()
    suggestion = SubscriptionSuggestion(
        recurring_pattern_id=pattern.id,
        merchant="Confirmed service",
        avg_amount=199,
        frequency="monthly",
        status="confirmed",
        confirmed_subscription_id=subscription.id,
    )
    db_session.add(suggestion)
    db_session.commit()
    suggestion_id = suggestion.id

    db_session.delete(subscription)
    db_session.commit()
    db_session.refresh(suggestion)
    assert suggestion.confirmed_subscription_id is None

    db_session.delete(pattern)
    db_session.commit()
    assert db_session.get(SubscriptionSuggestion, suggestion_id) is None
