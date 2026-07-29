from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.account import Account
from app.models.app_setting import AppSetting
from app.models.recurring_pattern import RecurringPattern
from app.models.subscription import Subscription
from app.models.transaction import Transaction


def _activate_pro(db_session) -> None:
    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    db_session.commit()


def _transaction(
    db_session,
    *,
    account_id: str,
    txn_date: date,
    amount: float,
    txn_type: str,
    merchant: str,
    is_income: bool = False,
) -> Transaction:
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=txn_date,
        raw_text=f"{merchant} {amount}",
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=txn_type,
        instrument="bank",
        account_id=account_id,
        source="manual",
        is_income=is_income,
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def test_cash_flow_calendar_excludes_transfers(auth_client, db_session):
    account = db_session.query(Account).first()
    _transaction(
        db_session,
        account_id=account.id,
        txn_date=date(2026, 7, 2),
        amount=500,
        txn_type="debit",
        merchant="Groceries",
    )
    _transaction(
        db_session,
        account_id=account.id,
        txn_date=date(2026, 7, 2),
        amount=1000,
        txn_type="credit",
        merchant="Salary",
        is_income=True,
    )
    transfer = _transaction(
        db_session,
        account_id=account.id,
        txn_date=date(2026, 7, 2),
        amount=250,
        txn_type="debit",
        merchant="Transfer",
    )
    transfer.is_transfer = True
    db_session.commit()

    response = auth_client.get("/api/v1/cash-flow/calendar?month=2026-07")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["days"]) == 31
    day = next(item for item in payload["days"] if item["date"] == "2026-07-02")
    assert day == {
        "date": "2026-07-02",
        "spend": 500.0,
        "income": 1000.0,
        "net": 500.0,
        "transaction_count": 2,
    }


def test_transfer_scan_and_confirm(auth_client, db_session):
    _activate_pro(db_session)
    accounts = db_session.query(Account).limit(2).all()
    debit = _transaction(
        db_session,
        account_id=accounts[0].id,
        txn_date=date(2026, 7, 10),
        amount=5000,
        txn_type="debit",
        merchant="Card payment",
    )
    credit = _transaction(
        db_session,
        account_id=accounts[1].id,
        txn_date=date(2026, 7, 11),
        amount=5000,
        txn_type="credit",
        merchant="Payment received",
    )
    db_session.commit()

    response = auth_client.post("/api/v1/transfers/scan")
    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["debit"]["id"] == debit.id
    assert candidate["credit"]["id"] == credit.id

    response = auth_client.post(
        f"/api/v1/transfers/{candidate['id']}/decision",
        json={"decision": "confirm"},
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Transaction, debit.id).is_transfer is True
    assert db_session.get(Transaction, credit.id).is_transfer is True


def test_transfer_matching_requires_paid_license(auth_client):
    response = auth_client.get("/api/v1/transfers")
    assert response.status_code == 403


def test_subscription_confirmation_and_reminder(auth_client, db_session):
    account = db_session.query(Account).first()
    pattern = RecurringPattern(
        merchant_normalized="STREAMING SERVICE",
        account_id=account.id,
        avg_amount=499,
        frequency="monthly",
        next_expected=date.today() + timedelta(days=3),
        category="ENTERTAINMENT",
    )
    db_session.add(pattern)
    db_session.commit()

    response = auth_client.post("/api/v1/subscriptions/suggestions/scan")
    assert response.status_code == 200
    response = auth_client.get("/api/v1/subscriptions/suggestions")
    suggestion = response.json()[0]
    response = auth_client.post(
        f"/api/v1/subscriptions/suggestions/{suggestion['id']}/decision",
        json={"decision": "confirm"},
    )
    assert response.status_code == 200
    assert db_session.query(Subscription).filter_by(name="Streaming Service").one()

    response = auth_client.get("/api/v1/subscriptions/reminders?days=7")
    assert response.status_code == 200
    assert response.json()["reminders"][0]["days_until"] == 3


def test_financial_year_export_csv_and_json(auth_client, db_session):
    _activate_pro(db_session)
    account = db_session.query(Account).first()
    _transaction(
        db_session,
        account_id=account.id,
        txn_date=date(2025, 4, 1),
        amount=1250,
        txn_type="debit",
        merchant="Professional expense",
    )
    db_session.commit()

    response = auth_client.get(
        "/api/v1/reports/fy?start_year=2025&format=csv"
    )
    assert response.status_code == 200
    assert "professional expense" in response.text.lower()
    assert "godfin_ca_fy2025-26.csv" in response.headers["content-disposition"]

    response = auth_client.get(
        "/api/v1/reports/fy?start_year=2025&format=json"
    )
    assert response.status_code == 200
    assert response.json()["summary"]["transaction_count"] == 1


def test_weekly_advisor_digest_and_settings(auth_client, db_session):
    _activate_pro(db_session)
    account = db_session.query(Account).first()
    _transaction(
        db_session,
        account_id=account.id,
        txn_date=date.today(),
        amount=2000,
        txn_type="debit",
        merchant="Unusual purchase",
    )
    db_session.commit()

    response = auth_client.get("/api/v1/advisor/digest")
    assert response.status_code == 200
    assert response.json()["current_spend"] == 2000
    assert len(response.json()["anomalies"]) == 1

    response = auth_client.put(
        "/api/v1/advisor/digest/settings",
        json={"enabled": True, "recipient": "user@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_first_pin_starts_onboarding(auth_client):
    response = auth_client.get("/api/v1/onboarding")
    assert response.status_code == 200
    assert response.json()["completed"] is False
    assert response.json()["deferred"] is False
    assert response.json()["step_count"] == 6
    response = auth_client.put(
        "/api/v1/onboarding", json={"step": 6, "completed": True}
    )
    assert response.status_code == 200
    assert response.json()["completed"] is True


def test_finish_later_preserves_setup_and_tutorial_progress(auth_client):
    response = auth_client.put(
        "/api/v1/onboarding",
        json={"step": 4, "deferred": True},
    )
    assert response.status_code == 200
    status = response.json()
    assert status["completed"] is False
    assert status["deferred"] is True
    assert status["step"] == 4

    response = auth_client.put(
        "/api/v1/onboarding",
        json={"tutorial_step": 7},
    )
    status = response.json()
    assert status["tutorial_step"] == 7
    assert status["tutorial_completed"] is False


def test_tutorial_completion_is_versioned_and_restartable(auth_client):
    completed = auth_client.put(
        "/api/v1/onboarding",
        json={"tutorial_step": 10, "tutorial_completed": True},
    ).json()
    assert completed["tutorial_completed"] is True
    assert completed["tutorial_completed_version"] == completed["tutorial_version"]

    restarted = auth_client.put(
        "/api/v1/onboarding",
        json={"restart_tutorial": True},
    ).json()
    assert restarted["tutorial_step"] == 1
    assert restarted["tutorial_completed"] is False
