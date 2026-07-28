from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core.budget import (
    ELASTICITY,
    FinancialProfile,
    calculate_required_monthly_saving,
    compute_financial_profile,
    simulate_goal,
)
from app.core.recurring import detect_recurring_patterns
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


def _add_txn(db, merchant, amount, txn_date, category=None, txn_type='debit'):
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=txn_date,
        raw_text=f'Test: {merchant} {amount}',
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=txn_type,
        instrument='upi',
        account_id=SAVINGS_ACCOUNT_ID,
        source='manual',
        category=category,
        is_income=txn_type == 'credit',
    )
    db.add(txn)
    return txn


# --- Goal Calculator ---

def test_calculate_monthly_saving_basic():
    # Need 12000 in 12 months at 0% return
    pmt = calculate_required_monthly_saving(12000, 0, 12, 0.0)
    assert abs(pmt - 1000.0) < 1


def test_calculate_monthly_saving_with_interest():
    pmt = calculate_required_monthly_saving(100000, 0, 24, 0.06)
    assert pmt > 0
    assert pmt < 100000 / 24  # Should be less than simple division due to returns


def test_calculate_monthly_saving_already_saved():
    pmt = calculate_required_monthly_saving(10000, 10000, 12, 0.0)
    assert pmt == 0.0


def test_calculate_monthly_saving_zero_months():
    pmt = calculate_required_monthly_saving(10000, 0, 0, 0.0)
    assert pmt == 10000


# --- Simulation ---

def test_simulate_goal(db_session):
    future = date.today() + timedelta(days=365)
    result = simulate_goal(
        db_session,
        target_amount=100000,
        current_saved=0,
        deadline=future,
    )
    assert result.required_monthly > 0
    assert result.months_remaining > 0
    assert 'minimal' in result.pressure_savings
    assert 'moderate' in result.pressure_savings
    assert 'aggressive' in result.pressure_savings


# --- Recurring Detection ---

def test_detect_monthly_recurring(db_session):
    today = date.today()
    for i in range(4):
        _add_txn(
            db_session, 'NETFLIX', 199.0,
            today - timedelta(days=30 * i),
            category='ENTERTAINMENT',
        )
    db_session.flush()

    detected = detect_recurring_patterns(db_session)
    assert detected >= 1


def test_no_recurring_single_txn(db_session):
    _add_txn(db_session, 'ONE TIME SHOP', 500.0, date.today())
    db_session.flush()

    detected = detect_recurring_patterns(db_session)
    assert detected == 0


# --- Financial Profile ---

def test_financial_profile_empty(db_session):
    profile = compute_financial_profile(db_session)
    assert profile.savings_rate == 0.0
    assert profile.impulse_index == 0.0


def test_financial_profile_with_data(db_session):
    today = date.today()
    _add_txn(db_session, 'SALARY', 75000, today, category='INCOME', txn_type='credit')
    _add_txn(db_session, 'RENT', 20000, today, category='HOUSING')
    _add_txn(db_session, 'SWIGGY', 200, today, category='FOOD & DINING')
    _add_txn(db_session, 'COFFEE', 100, today, category='FOOD & DINING')
    db_session.flush()

    profile = compute_financial_profile(db_session)
    assert profile.savings_rate > 0
    assert profile.fixed_expense_ratio > 0


# --- Elasticity ---

def test_elasticity_mapping():
    assert ELASTICITY['HOUSING'] == 'fixed'
    assert ELASTICITY['FOOD & DINING'] == 'flexible'
    assert ELASTICITY['TRANSFERS'] == 'none'


# --- API endpoints ---

def test_create_goal(auth_client):
    future = (date.today() + timedelta(days=365)).isoformat()
    resp = auth_client.post("/api/v1/goals", json={
        "name": "Emergency Fund",
        "target_amount": 100000,
        "deadline_date": future,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Emergency Fund"
    assert data["id"]


def test_list_goals(auth_client):
    future = (date.today() + timedelta(days=365)).isoformat()
    auth_client.post("/api/v1/goals", json={
        "name": "Vacation",
        "target_amount": 50000,
        "deadline_date": future,
    })

    resp = auth_client.get("/api/v1/goals")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_update_goal(auth_client):
    future = (date.today() + timedelta(days=365)).isoformat()
    resp = auth_client.post("/api/v1/goals", json={
        "name": "Update Test",
        "target_amount": 30000,
        "deadline_date": future,
    })
    goal_id = resp.json()["id"]

    resp = auth_client.put(f"/api/v1/goals/{goal_id}", json={
        "current_saved": 5000,
    })
    assert resp.status_code == 200


def test_delete_goal(auth_client):
    future = (date.today() + timedelta(days=365)).isoformat()
    resp = auth_client.post("/api/v1/goals", json={
        "name": "Delete Test",
        "target_amount": 10000,
        "deadline_date": future,
    })
    goal_id = resp.json()["id"]

    resp = auth_client.delete(f"/api/v1/goals/{goal_id}")
    assert resp.status_code == 204


def test_simulate_goal_api(auth_client):
    future = (date.today() + timedelta(days=365)).isoformat()
    resp = auth_client.post("/api/v1/goals", json={
        "name": "Simulate Test",
        "target_amount": 100000,
        "deadline_date": future,
    })
    goal_id = resp.json()["id"]

    resp = auth_client.post(f"/api/v1/goals/{goal_id}/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert "required_monthly" in data
    assert "is_feasible" in data
    assert "pressure_savings" in data


def test_recurring_list(auth_client):
    resp = auth_client.get("/api/v1/recurring")
    assert resp.status_code == 200


def test_recurring_detect(auth_client):
    resp = auth_client.post("/api/v1/recurring/detect")
    assert resp.status_code == 200
    assert "detected" in resp.json()


def test_financial_profile_api(auth_client):
    resp = auth_client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "savings_rate" in data
    assert "impulse_index" in data
    assert "fixed_expense_ratio" in data


def test_elasticity_api(auth_client):
    resp = auth_client.get("/api/v1/elasticity")
    assert resp.status_code == 200
    data = resp.json()
    assert data["HOUSING"] == "fixed"


def test_goal_past_deadline(auth_client):
    past = (date.today() - timedelta(days=1)).isoformat()
    resp = auth_client.post("/api/v1/goals", json={
        "name": "Past Goal",
        "target_amount": 10000,
        "deadline_date": past,
    })
    assert resp.status_code == 400
