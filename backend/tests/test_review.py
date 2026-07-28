from __future__ import annotations

import uuid
from datetime import date

from app.models.audit_log import AuditLog
from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


def _create_unclassified_txn(db_session, merchant='TEST MERCHANT', amount=100.0):
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2025, 1, 15),
        raw_text=f'Manual: {merchant} {amount}',
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type='debit',
        instrument='upi',
        account_id=SAVINGS_ACCOUNT_ID,
        source='manual',
    )
    db_session.add(txn)
    db_session.flush()
    return txn


def test_review_queue_list(auth_client, db_session):
    _create_unclassified_txn(db_session, 'UNKNOWN SHOP')
    _create_unclassified_txn(db_session, 'RANDOM STORE')
    db_session.commit()

    resp = auth_client.get("/api/v1/review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


def test_review_queue_empty(auth_client):
    resp = auth_client.get("/api/v1/review")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_resolve_review(auth_client, db_session):
    txn = _create_unclassified_txn(db_session, 'MYSTERY VENDOR')
    db_session.commit()

    resp = auth_client.post(
        f"/api/v1/review/{txn.id}/resolve",
        json={"category": "SHOPPING", "subcategory": "General"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    # Verify transaction updated
    db_session.refresh(txn)
    assert txn.category == 'SHOPPING'
    assert txn.subcategory == 'General'
    assert txn.confidence == 1.0
    assert txn.classification_source == 'user'


def test_resolve_creates_audit_log(auth_client, db_session):
    txn = _create_unclassified_txn(db_session, 'AUDIT TEST')
    db_session.commit()

    auth_client.post(
        f"/api/v1/review/{txn.id}/resolve",
        json={"category": "ENTERTAINMENT", "subcategory": "Subscriptions"},
    )

    logs = db_session.query(AuditLog).filter_by(transaction_id=txn.id).all()
    assert len(logs) >= 1
    cat_log = [l for l in logs if l.field_changed == 'category'][0]
    assert cat_log.old_value is None
    assert cat_log.new_value == 'ENTERTAINMENT'
    assert cat_log.change_source == 'user_review'


def test_resolve_updates_merchant_memory(auth_client, db_session):
    txn = _create_unclassified_txn(db_session, 'NEW MERCHANT ABC')
    db_session.commit()

    auth_client.post(
        f"/api/v1/review/{txn.id}/resolve",
        json={"category": "FOOD & DINING", "subcategory": "Restaurants"},
    )

    memory = db_session.query(MerchantMemory).filter_by(
        normalized_name='NEW MERCHANT ABC'
    ).first()
    assert memory is not None
    assert memory.category == 'FOOD & DINING'
    assert memory.subcategory == 'Restaurants'


def test_resolve_invalid_category(auth_client, db_session):
    txn = _create_unclassified_txn(db_session, 'BAD CAT TEST')
    db_session.commit()

    resp = auth_client.post(
        f"/api/v1/review/{txn.id}/resolve",
        json={"category": "NONEXISTENT"},
    )
    assert resp.status_code == 400


def test_resolve_not_found(auth_client):
    resp = auth_client.post(
        "/api/v1/review/nonexistent-id/resolve",
        json={"category": "SHOPPING"},
    )
    assert resp.status_code == 404


def test_batch_resolve(auth_client, db_session):
    txn1 = _create_unclassified_txn(db_session, 'BATCH ONE')
    txn2 = _create_unclassified_txn(db_session, 'BATCH TWO')
    db_session.commit()

    resp = auth_client.post("/api/v1/review/batch-resolve", json={
        "items": [
            {"id": txn1.id, "category": "SHOPPING", "subcategory": "General"},
            {"id": txn2.id, "category": "FOOD & DINING", "subcategory": "Groceries"},
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] == 2
    assert len(data["errors"]) == 0


def test_review_stats(auth_client, db_session):
    _create_unclassified_txn(db_session, 'STATS TEST')
    db_session.commit()

    resp = auth_client.get("/api/v1/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queue_size"] >= 1
    assert "auto_accepted" in data
    assert "soft_flagged" in data


def test_resolve_remembers_for_next(auth_client, db_session):
    """After resolving, the same merchant should be classified by exact match."""
    txn1 = _create_unclassified_txn(db_session, 'REMEMBER ME SHOP')
    db_session.commit()

    auth_client.post(
        f"/api/v1/review/{txn1.id}/resolve",
        json={"category": "SHOPPING", "subcategory": "Electronics"},
    )

    # Now classify a new transaction with the same merchant
    from app.core.classifier import classify_transaction
    result = classify_transaction(db_session, 'REMEMBER ME SHOP', 500.0, 'upi')
    assert result.category == 'SHOPPING'
    assert result.source == 'exact_match'
    assert result.confidence == 1.0
