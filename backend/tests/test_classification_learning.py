from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.core.classification_learning import build_pattern_key
from app.core.classifier import classify_transaction
from app.models.classification_learning import (
    ClassificationCorrection,
    ClassificationPattern,
)
from app.models.app_setting import AppSetting
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID
from tests.license_helpers import install_test_license


def _transaction(db_session, merchant: str) -> Transaction:
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=date(2025, 2, 1),
        raw_text=merchant,
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=250,
        type="debit",
        instrument="upi",
        account_id=SAVINGS_ACCOUNT_ID,
        source="manual",
    )
    db_session.add(transaction)
    db_session.commit()
    return transaction


def _resolve(auth_client, transaction: Transaction):
    response = auth_client.post(
        f"/api/v1/review/{transaction.id}/resolve",
        json={"category": "FOOD & DINING", "subcategory": "Groceries"},
    )
    assert response.status_code == 200
    assert response.json()["learned"] is True


def test_pattern_key_removes_reference_noise():
    first, display = build_pattern_key("UPI GREEN MART 881234", "upi")
    second, _ = build_pattern_key("GREEN-MART REF 998877", "upi")
    assert first == second
    assert display == "GREEN MART"


def test_two_explicit_corrections_enable_confirmed_pattern(
    auth_client,
    db_session,
):
    first = _transaction(db_session, "GREEN MART 1001")
    second = _transaction(db_session, "GREEN MART 2002")
    _resolve(auth_client, first)
    _resolve(auth_client, second)

    pattern = db_session.query(ClassificationPattern).one()
    assert pattern.confirmations == 2
    assert pattern.category == "FOOD & DINING"

    result = classify_transaction(
        db_session,
        "GREEN MART 3003",
        500,
        "upi",
    )
    assert result.source == "confirmed_pattern"
    assert result.category == "FOOD & DINING"


def test_learning_memory_can_be_inspected_exported_and_undone(
    auth_client,
    db_session,
):
    transaction = _transaction(db_session, "UNDO LEARNING 1234")
    _resolve(auth_client, transaction)

    response = auth_client.get("/api/v1/settings/classification-memory")
    assert response.status_code == 200
    correction = response.json()["corrections"][0]
    assert correction["new_category"] == "FOOD & DINING"

    exported = auth_client.get("/api/v1/settings/classification-memory/export")
    assert exported.status_code == 200
    assert "exact_merchant" in exported.text

    undone = auth_client.post(
        f"/api/v1/settings/classification-memory/{correction['id']}/undo"
    )
    assert undone.status_code == 200
    db_session.refresh(transaction)
    assert transaction.category is None
    event = db_session.query(ClassificationCorrection).filter_by(
        id=correction["id"]
    ).one()
    assert event.undone_at is not None


def test_finalized_transaction_learning_cannot_be_undone(
    auth_client,
    db_session,
):
    transaction = _transaction(db_session, "LOCKED LEARNING 1234")
    _resolve(auth_client, transaction)
    correction = db_session.query(ClassificationCorrection).one()
    transaction.is_locked = True
    db_session.commit()

    response = auth_client.post(
        f"/api/v1/settings/classification-memory/{correction.id}/undo"
    )
    assert response.status_code == 409


def test_personal_classifier_cannot_enable_early(auth_client, db_session):
    install_test_license(db_session, "max")

    response = auth_client.put(
        "/api/v1/settings/classification-memory/personal",
        json={"enabled": True},
    )
    assert response.status_code == 409
    assert "200 confirmed corrections" in response.json()["detail"]
