from __future__ import annotations

from app.seed import SAVINGS_ACCOUNT_ID, CC_ACCOUNT_ID


def _make_txn(account_id=None, **overrides):
    data = {
        "date": "2026-02-15",
        "merchant_raw": "Swiggy Food",
        "amount": 350.00,
        "type": "debit",
        "instrument": "upi",
        "account_id": account_id or SAVINGS_ACCOUNT_ID,
        "category": "FOOD & DINING",
        "subcategory": "Food Delivery",
    }
    data.update(overrides)
    return data


def test_create_transaction(auth_client):
    resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 350.00
    assert data["source"] == "manual"
    assert data["classification_source"] == "user"
    assert data["confidence"] == 1.0
    assert data["merchant_normalized"] == "SWIGGY FOOD"


def test_create_transaction_no_category(auth_client):
    resp = auth_client.post(
        "/api/v1/transactions",
        json=_make_txn(category=None, subcategory=None),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] is None
    assert data["confidence"] is None
    assert data["classification_source"] is None


def test_create_transaction_invalid_category(auth_client):
    resp = auth_client.post(
        "/api/v1/transactions",
        json=_make_txn(category="FAKE_CATEGORY"),
    )
    assert resp.status_code == 422


def test_create_transaction_missing_fields(auth_client):
    resp = auth_client.post("/api/v1/transactions", json={"amount": 100})
    assert resp.status_code == 422


def test_list_transactions_empty(auth_client):
    resp = auth_client.get("/api/v1/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_transactions_with_data(auth_client):
    for i in range(3):
        auth_client.post(
            "/api/v1/transactions",
            json=_make_txn(merchant_raw=f"Merchant {i}", amount=100 + i),
        )
    resp = auth_client.get("/api/v1/transactions")
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_list_transactions_filter_date(auth_client):
    auth_client.post("/api/v1/transactions", json=_make_txn(date="2026-01-10"))
    auth_client.post("/api/v1/transactions", json=_make_txn(date="2026-02-15"))
    auth_client.post("/api/v1/transactions", json=_make_txn(date="2026-03-20"))

    resp = auth_client.get(
        "/api/v1/transactions",
        params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
    )
    assert resp.json()["total"] == 1


def test_list_transactions_filter_category(auth_client):
    auth_client.post("/api/v1/transactions", json=_make_txn(category="FOOD & DINING"))
    auth_client.post("/api/v1/transactions", json=_make_txn(category="SHOPPING"))

    resp = auth_client.get(
        "/api/v1/transactions", params={"category": "SHOPPING"}
    )
    assert resp.json()["total"] == 1


def test_list_transactions_search(auth_client):
    auth_client.post("/api/v1/transactions", json=_make_txn(merchant_raw="Amazon"))
    auth_client.post("/api/v1/transactions", json=_make_txn(merchant_raw="Netflix"))

    resp = auth_client.get("/api/v1/transactions", params={"search": "amazon"})
    assert resp.json()["total"] == 1


def test_list_transactions_pagination(auth_client):
    for i in range(5):
        auth_client.post(
            "/api/v1/transactions",
            json=_make_txn(merchant_raw=f"M{i}", amount=100 + i),
        )
    resp = auth_client.get("/api/v1/transactions", params={"page": 1, "page_size": 2})
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1


def test_get_transaction_detail(auth_client):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    resp = auth_client.get(f"/api/v1/transactions/{txn_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == txn_id


def test_get_transaction_not_found(auth_client):
    resp = auth_client.get("/api/v1/transactions/nonexistent-id")
    assert resp.status_code == 404


def test_update_transaction(auth_client):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    resp = auth_client.put(
        f"/api/v1/transactions/{txn_id}",
        json={"category": "SHOPPING", "notes": "Updated"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "SHOPPING"
    assert data["notes"] == "Updated"
    assert data["classification_source"] == "user"


def test_update_locked_transaction(auth_client, db_session):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    from app.models.transaction import Transaction
    txn = db_session.query(Transaction).filter_by(id=txn_id).first()
    txn.is_locked = True
    db_session.commit()

    resp = auth_client.put(
        f"/api/v1/transactions/{txn_id}",
        json={"category": "SHOPPING"},
    )
    assert resp.status_code == 403


def test_delete_transaction(auth_client):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    resp = auth_client.delete(f"/api/v1/transactions/{txn_id}")
    assert resp.status_code == 204

    resp = auth_client.get(f"/api/v1/transactions/{txn_id}")
    assert resp.status_code == 404


def test_delete_locked_transaction(auth_client, db_session):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    from app.models.transaction import Transaction
    txn = db_session.query(Transaction).filter_by(id=txn_id).first()
    txn.is_locked = True
    db_session.commit()

    resp = auth_client.delete(f"/api/v1/transactions/{txn_id}")
    assert resp.status_code == 403


def test_deleted_not_in_list(auth_client):
    create_resp = auth_client.post("/api/v1/transactions", json=_make_txn())
    txn_id = create_resp.json()["id"]

    auth_client.delete(f"/api/v1/transactions/{txn_id}")
    resp = auth_client.get("/api/v1/transactions")
    assert resp.json()["total"] == 0
