from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.budget import calculate_required_monthly_saving, simulate_goal
from app.core.goal_contributions import (
    detect_goal_contribution_suggestions,
    reconcile_goal_source_transactions,
)
from app.core.recurring import detect_recurring_patterns
from app.models.app_setting import AppSetting
from app.models.goal import Goal
from app.models.goal_contribution import (
    GoalContribution,
    GoalContributionSuggestion,
)
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


def _future_goal_payload(**overrides):
    payload = {
        "name": "Emergency reserve",
        "target_amount": 200000,
        "current_saved": 25000,
        "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
        "annual_return_rate": 0,
    }
    payload.update(overrides)
    return payload


def _transaction(
    db,
    *,
    merchant: str,
    txn_date: date,
    amount: float = 499,
    account_id: str = SAVINGS_ACCOUNT_ID,
    txn_type: str = "debit",
    raw_text: str | None = None,
    reconciled: bool = True,
    is_transfer: bool = False,
    status: str = "settled",
    checksum: str | None = None,
):
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=txn_date,
        raw_text=raw_text or f"Statement: {merchant} {amount}",
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=txn_type,
        instrument="statement",
        account_id=account_id,
        source="statement_upload",
        reconciled=reconciled,
        is_transfer=is_transfer,
        status=status,
        checksum_canonical=checksum,
    )
    db.add(transaction)
    return transaction


def _activate_paid(db, tier: str = "pro"):
    now = datetime.now(UTC).isoformat()
    for key, value in (
        ("license_tier", tier),
        ("license_status", "active"),
        ("license_verified_at", now),
    ):
        setting = db.query(AppSetting).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.commit()


def _shift_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    source_last = calendar.monthrange(value.year, value.month)[1]
    target_last = calendar.monthrange(year, month)[1]
    day = target_last if value.day == source_last else min(value.day, target_last)
    return date(year, month, day)


def test_goal_opening_balance_deposit_withdrawal_and_void(auth_client):
    created = auth_client.post(
        "/api/v1/goals", json=_future_goal_payload()
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]
    assert created.json()["current_saved"] == 25000

    entries = auth_client.get(
        f"/api/v1/goals/{goal_id}/contributions"
    ).json()
    assert len(entries) == 1
    assert entries[0]["source_type"] == "opening_balance"

    deposit = auth_client.post(
        f"/api/v1/goals/{goal_id}/contributions",
        json={
            "amount": 5000,
            "entry_type": "deposit",
            "idempotency_key": "deposit-1",
        },
    )
    assert deposit.status_code == 201
    assert deposit.json()["current_saved"] == 30000

    duplicate = auth_client.post(
        f"/api/v1/goals/{goal_id}/contributions",
        json={
            "amount": 5000,
            "entry_type": "deposit",
            "idempotency_key": "deposit-1",
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["current_saved"] == 30000

    withdrawal = auth_client.post(
        f"/api/v1/goals/{goal_id}/contributions",
        json={"amount": 1000, "entry_type": "withdrawal"},
    )
    assert withdrawal.status_code == 201
    assert withdrawal.json()["current_saved"] == 29000

    entry_id = withdrawal.json()["contribution"]["id"]
    voided = auth_client.post(
        f"/api/v1/goals/{goal_id}/contributions/{entry_id}/void",
        json={"reason": "Entered against the wrong goal"},
    )
    assert voided.status_code == 200
    assert voided.json()["current_saved"] == 30000

    too_large = auth_client.post(
        f"/api/v1/goals/{goal_id}/contributions",
        json={"amount": 999999, "entry_type": "withdrawal"},
    )
    assert too_large.status_code == 400


def test_fd_rd_suggestion_gate_assignment_none_and_source_reversal(
    auth_client,
    db_session,
):
    goal = auth_client.post(
        "/api/v1/goals",
        json=_future_goal_payload(current_saved=0),
    ).json()
    transaction = _transaction(
        db_session,
        merchant="HDFC FIXED DEPOSIT BOOKING",
        txn_date=date.today(),
        amount=10000,
    )
    db_session.commit()

    assert detect_goal_contribution_suggestions(db_session) == 1
    db_session.commit()
    disabled = auth_client.get("/api/v1/goal-contribution-suggestions")
    assert disabled.json() == {"enabled": False, "items": []}

    _activate_paid(db_session)
    suggestions = auth_client.get(
        "/api/v1/goal-contribution-suggestions"
    ).json()
    assert suggestions["enabled"] is True
    suggestion = suggestions["items"][0]
    assert suggestion["goal_id"] == goal["id"]

    assigned = auth_client.post(
        f"/api/v1/goal-contribution-suggestions/{suggestion['id']}/decision",
        json={"goal_id": goal["id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["current_saved"] == 10000

    transaction.status = "reversed"
    assert reconcile_goal_source_transactions(db_session) == 1
    db_session.commit()
    contribution = db_session.query(GoalContribution).filter_by(
        source_transaction_id=transaction.id
    ).one()
    assert contribution.is_voided is True

    second = _transaction(
        db_session,
        merchant="BANK RD INSTALLMENT",
        txn_date=date.today() - timedelta(days=1),
        amount=1500,
    )
    db_session.commit()
    assert detect_goal_contribution_suggestions(
        db_session, transactions=[second]
    ) == 1
    db_session.commit()
    suggestion2 = db_session.query(GoalContributionSuggestion).filter_by(
        transaction_id=second.id
    ).one()
    dismissed = auth_client.post(
        f"/api/v1/goal-contribution-suggestions/{suggestion2.id}/decision",
        json={"goal_id": None},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["contribution"] is None


def test_fd_rd_detection_requires_reconciliation_and_deduplicates(db_session):
    eligible = _transaction(
        db_session,
        merchant="TERM DEPOSIT OPENED",
        txn_date=date.today(),
        checksum="same-canonical",
    )
    duplicate = _transaction(
        db_session,
        merchant="TERM DEPOSIT OPENED",
        txn_date=date.today(),
        checksum="same-canonical",
    )
    _transaction(
        db_session,
        merchant="FD MATURITY CREDIT",
        txn_date=date.today(),
        raw_text="FD MATURITY CREDIT",
    )
    _transaction(
        db_session,
        merchant="RD INSTALLMENT",
        txn_date=date.today(),
        reconciled=False,
    )
    db_session.flush()
    assert detect_goal_contribution_suggestions(
        db_session, transactions=[eligible, duplicate]
    ) == 1


def test_simulation_reference_zero_return_existing_savings_and_rounding():
    assert calculate_required_monthly_saving(12000, 0, 12, 0) == 1000
    assert calculate_required_monthly_saving(
        100000, 20000, 12, 0.12
    ) == 6107.90
    assert calculate_required_monthly_saving(100, 0, 3, 0) == 33.33
    assert calculate_required_monthly_saving(10000, 10000, 12, 0) == 0


def test_simulation_capacity_uses_complete_historical_months(db_session):
    today = date.today()
    first = _shift_months(date(today.year, today.month, 15), -1)
    second = _shift_months(first, -1)
    for month_date in (first, second):
        _transaction(
            db_session,
            merchant="SALARY",
            txn_date=month_date,
            amount=50000,
            txn_type="credit",
        ).is_income = True
        _transaction(
            db_session,
            merchant="RENT",
            txn_date=month_date,
            amount=20000,
        ).category = "HOUSING"
        _transaction(
            db_session,
            merchant="DINING",
            txn_date=month_date,
            amount=10000,
        ).category = "FOOD & DINING"
    db_session.flush()
    result = simulate_goal(
        db_session,
        target_amount=100000,
        current_saved=0,
        deadline=date.today() + timedelta(days=93),
        minimum_floor=5000,
    )
    assert result.coverage_months == 2
    assert result.capacity_status == "calculated"
    assert result.baseline_surplus == 20000
    assert result.reducible_flexible_spend == 5000
    assert result.max_saveable == 25000
    assert result.calculation_version == "2.0"


@pytest.mark.parametrize(
    ("frequency", "months"),
    [("monthly", 1), ("quarterly", 3), ("annual", 12)],
)
def test_recurring_calendar_patterns(db_session, frequency, months):
    target = date(2026, 8, 31)
    for index in range(4):
        _transaction(
            db_session,
            merchant=f"{frequency} SERVICE",
            txn_date=_shift_months(target, -months * index),
            amount=500 + index * 5,
        )
    db_session.flush()
    summary = detect_recurring_patterns(db_session)
    pattern = db_session.query(RecurringPattern).filter_by(
        merchant_normalized=f"{frequency.upper()} SERVICE"
    ).one()
    assert summary.created >= 1
    assert pattern.frequency == frequency
    assert pattern.is_active is True
    assert pattern.confidence >= 0.65
    assert pattern.next_expected == _shift_months(target, months)


def test_recurring_candidate_exclusions_and_stale_deactivation(db_session):
    target = date(2026, 7, 31)
    for index in range(2):
        _transaction(
            db_session,
            merchant="TWO POINT CANDIDATE",
            txn_date=_shift_months(target, -index),
        )
    for index in range(4):
        _transaction(
            db_session,
            merchant="TRANSFER LOOKALIKE",
            txn_date=_shift_months(target, -index),
            is_transfer=True,
        )
        _transaction(
            db_session,
            merchant="REVERSED SERVICE",
            txn_date=_shift_months(target, -index),
            status="reversed",
        )
    db_session.flush()
    detect_recurring_patterns(db_session)
    candidate = db_session.query(RecurringPattern).filter_by(
        merchant_normalized="TWO POINT CANDIDATE"
    ).one()
    assert candidate.detection_status == "candidate"
    assert candidate.is_active is False
    assert db_session.query(RecurringPattern).filter_by(
        merchant_normalized="TRANSFER LOOKALIKE"
    ).first() is None

    for transaction in db_session.query(Transaction).filter_by(
        merchant_normalized="TWO POINT CANDIDATE"
    ):
        transaction.status = "deleted"
    summary = detect_recurring_patterns(db_session)
    assert summary.deactivated == 0
    db_session.refresh(candidate)
    assert candidate.detection_status == "retired"


def test_recurring_redetect_api_returns_counts(auth_client):
    response = auth_client.post("/api/v1/recurring/detect")
    assert response.status_code == 200
    assert set(
        ("created", "updated", "deactivated", "scanned")
    ).issubset(response.json())
