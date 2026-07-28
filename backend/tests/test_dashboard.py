from __future__ import annotations

from datetime import date

from app.seed import SAVINGS_ACCOUNT_ID


def test_dashboard_months_falls_back_to_last_24(auth_client):
    resp = auth_client.get("/api/v1/dashboard/months")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is False
    assert len(data["months"]) == 24
    assert data["months"][0] == date.today().strftime("%Y-%m")


def test_dashboard_months_uses_actual_transaction_months(auth_client):
    for transaction_date in ("2024-03-10", "2025-11-05", "2024-03-20"):
        auth_client.post("/api/v1/transactions", json={
            "date": transaction_date,
            "merchant_raw": "Month Test",
            "amount": 100,
            "type": "debit",
            "account_id": SAVINGS_ACCOUNT_ID,
            "category": "SHOPPING",
        })

    resp = auth_client.get("/api/v1/dashboard/months")
    assert resp.status_code == 200
    assert resp.json() == {
        "months": ["2025-11", "2024-03"],
        "has_data": True,
    }


def test_dashboard_stats_empty_month(auth_client):
    resp = auth_client.get("/api/v1/dashboard/stats", params={"month": "2026-02"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["month_spend"] == 0
    assert data["month_income"] == 0
    assert data["savings_rate"] is None
    assert data["review_queue_count"] == 0


def test_dashboard_stats_with_data(auth_client):
    # Create debits
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-10",
        "merchant_raw": "Swiggy",
        "amount": 500.00,
        "type": "debit",
        "account_id": SAVINGS_ACCOUNT_ID,
        "category": "FOOD & DINING",
    })
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-15",
        "merchant_raw": "Amazon",
        "amount": 2000.00,
        "type": "debit",
        "account_id": SAVINGS_ACCOUNT_ID,
        "category": "SHOPPING",
    })
    # Create income
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-01",
        "merchant_raw": "Salary",
        "amount": 85000.00,
        "type": "credit",
        "account_id": SAVINGS_ACCOUNT_ID,
        "category": "INCOME",
    })
    # Create transfer (should NOT count in spend)
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-05",
        "merchant_raw": "CC Payment",
        "amount": 10000.00,
        "type": "debit",
        "account_id": SAVINGS_ACCOUNT_ID,
        "category": "TRANSFERS",
    })

    resp = auth_client.get("/api/v1/dashboard/stats", params={"month": "2026-02"})
    data = resp.json()
    assert data["month_spend"] == 2500.00  # 500 + 2000, not including transfer
    assert data["month_income"] == 85000.00
    assert data["savings_rate"] is not None
    assert data["savings_rate"] > 0


def test_dashboard_review_queue_count(auth_client):
    # Transaction without category = needs review
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-10",
        "merchant_raw": "Unknown Merchant",
        "amount": 100.00,
        "type": "debit",
        "account_id": SAVINGS_ACCOUNT_ID,
    })
    # Transaction with category = does NOT need review
    auth_client.post("/api/v1/transactions", json={
        "date": "2026-02-10",
        "merchant_raw": "Swiggy",
        "amount": 200.00,
        "type": "debit",
        "account_id": SAVINGS_ACCOUNT_ID,
        "category": "FOOD & DINING",
    })

    resp = auth_client.get("/api/v1/dashboard/stats", params={"month": "2026-02"})
    assert resp.json()["review_queue_count"] == 1
