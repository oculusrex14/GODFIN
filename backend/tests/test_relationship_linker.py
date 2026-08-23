from __future__ import annotations

import uuid
from datetime import date

from app.core.relationship_linker import suggest_transaction_relationships
from app.models.account import Account
from app.models.transaction import Transaction


def _transaction(
    db_session,
    *,
    account_id: str,
    when: date,
    amount: float,
    direction: str,
    merchant: str,
    source: str,
    semantic_detail: str,
    reference: str | None = None,
) -> Transaction:
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=when,
        raw_text=merchant,
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=direction,
        instrument="bank",
        account_id=account_id,
        source=source,
        status="settled",
        semantic_type="unknown",
        semantic_detail=semantic_detail,
        reference_number=reference,
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def test_refund_relationship_is_evidence_only_and_preserves_financial_semantics(
    db_session,
):
    account = db_session.query(Account).first()
    purchase = _transaction(
        db_session,
        account_id=account.id,
        when=date(2026, 8, 1),
        amount=499,
        direction="debit",
        merchant="EXAMPLE STORE",
        source="statement_upload",
        semantic_detail="purchase",
        reference="REF12345678",
    )
    refund = _transaction(
        db_session,
        account_id=account.id,
        when=date(2026, 8, 3),
        amount=499,
        direction="credit",
        merchant="EXAMPLE STORE REFUND",
        source="gmail",
        semantic_detail="refund",
        reference="REF12345678",
    )
    db_session.commit()

    relationships = suggest_transaction_relationships(db_session)
    db_session.commit()

    refund_links = [item for item in relationships if item.relationship_type == "refund_of"]
    assert len(refund_links) == 1
    assert refund_links[0].from_transaction_id == refund.id
    assert refund_links[0].to_transaction_id == purchase.id
    assert refund_links[0].status == "confirmed"
    assert purchase.semantic_detail == "purchase"
    assert refund.semantic_detail == "refund"
    assert purchase.amount == 499
    assert refund.amount == 499


def test_internal_transfer_pair_is_directional_and_not_duplicated(db_session):
    accounts = db_session.query(Account).limit(2).all()
    debit = _transaction(
        db_session,
        account_id=accounts[0].id,
        when=date(2026, 8, 5),
        amount=10_000,
        direction="debit",
        merchant="OWN ACCOUNT TRANSFER",
        source="statement_upload",
        semantic_detail="transfer_out",
        reference="UTR123456789",
    )
    credit = _transaction(
        db_session,
        account_id=accounts[1].id,
        when=date(2026, 8, 5),
        amount=10_000,
        direction="credit",
        merchant="OWN ACCOUNT TRANSFER",
        source="statement_upload",
        semantic_detail="transfer_in",
        reference="UTR123456789",
    )
    db_session.commit()

    first = suggest_transaction_relationships(db_session)
    second = suggest_transaction_relationships(db_session)
    db_session.commit()

    pairs = [item for item in first if item.relationship_type == "internal_transfer_pair"]
    assert len(pairs) == 1
    assert pairs[0].from_transaction_id == debit.id
    assert pairs[0].to_transaction_id == credit.id
    assert second == []


def test_ambiguous_same_amount_rows_abstain_without_reference_or_merchant_evidence(
    db_session,
):
    accounts = db_session.query(Account).limit(2).all()
    _transaction(
        db_session,
        account_id=accounts[0].id,
        when=date(2026, 8, 7),
        amount=2500,
        direction="debit",
        merchant="ALPHA",
        source="statement_upload",
        semantic_detail="unknown",
    )
    _transaction(
        db_session,
        account_id=accounts[1].id,
        when=date(2026, 8, 7),
        amount=2500,
        direction="credit",
        merchant="COMPLETELY DIFFERENT",
        source="statement_upload",
        semantic_detail="unknown",
    )
    db_session.commit()

    assert suggest_transaction_relationships(db_session) == []
