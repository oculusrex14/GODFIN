from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.core.audit import (
    discard_audit,
    finalize_audit,
    get_month_status,
    reopen_audit,
    start_audit,
)
from app.models.audit_session import AuditSession
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
    db.flush()
    return txn


# --- Month Status ---

def test_month_status_no_audit(db_session):
    assert get_month_status(db_session, 2025, 3) == 'no_audit'


def test_month_status_draft(db_session):
    start_audit(db_session, 2025, 3)
    db_session.flush()
    assert get_month_status(db_session, 2025, 3) == 'draft'


def test_month_status_finalized(db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 3, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 3)
    db_session.flush()
    finalize_audit(db_session, session.id)
    db_session.flush()
    assert get_month_status(db_session, 2025, 3) == 'finalized'


# --- Start Audit ---

def test_start_audit(db_session):
    session = start_audit(db_session, 2025, 1)
    db_session.flush()
    assert session.status == 'draft'
    assert session.period_year == 2025
    assert session.period_month == 1


def test_start_audit_one_draft_at_a_time(db_session):
    start_audit(db_session, 2025, 1)
    db_session.flush()
    with pytest.raises(ValueError, match='draft audit is already in progress'):
        start_audit(db_session, 2025, 2)


def test_start_audit_already_finalized(db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 1)
    db_session.flush()
    finalize_audit(db_session, session.id)
    db_session.flush()
    with pytest.raises(ValueError, match='already finalized'):
        start_audit(db_session, 2025, 1)


# --- Finalize Audit ---

def test_finalize_audit_locks_transactions(db_session):
    txn = _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 1)
    db_session.flush()

    finalize_audit(db_session, session.id)
    db_session.flush()

    db_session.refresh(txn)
    assert txn.is_locked is True
    assert txn.audit_session_id == session.id


def test_finalize_audit_computes_aggregate(db_session):
    from app.models.monthly_aggregate import MonthlyAggregate

    _add_txn(db_session, 'SALARY', 75000, date(2025, 1, 1), category='INCOME', txn_type='credit')
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    _add_txn(db_session, 'RENT', 20000, date(2025, 1, 3), category='HOUSING')
    session = start_audit(db_session, 2025, 1)
    db_session.flush()

    finalize_audit(db_session, session.id)
    db_session.flush()

    agg = db_session.query(MonthlyAggregate).filter_by(month='2025-01').first()
    assert agg is not None
    assert agg.is_finalized is True
    assert agg.total_income == 75000.0
    assert agg.total_spend == 20500.0


def test_finalize_audit_session_status(db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 1)
    db_session.flush()

    result = finalize_audit(db_session, session.id)
    db_session.flush()

    assert result.status == 'finalized'
    assert result.finalized_at is not None
    assert result.change_summary is not None


def test_cannot_finalize_non_draft(db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 1)
    db_session.flush()
    finalize_audit(db_session, session.id)
    db_session.flush()

    with pytest.raises(ValueError, match='Cannot finalize'):
        finalize_audit(db_session, session.id)


# --- Discard Audit ---

def test_discard_audit(db_session):
    session = start_audit(db_session, 2025, 2)
    db_session.flush()

    result = discard_audit(db_session, session.id)
    db_session.flush()

    assert result.status == 'discarded'


def test_cannot_discard_finalized(db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 2, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 2)
    db_session.flush()
    finalize_audit(db_session, session.id)
    db_session.flush()

    with pytest.raises(ValueError, match='only discard draft'):
        discard_audit(db_session, session.id)


# --- Reopen Audit ---

def test_reopen_audit(db_session):
    txn = _add_txn(db_session, 'SWIGGY', 500, date(2025, 4, 5), category='FOOD & DINING')
    session = start_audit(db_session, 2025, 4)
    db_session.flush()
    finalize_audit(db_session, session.id)
    db_session.flush()

    new_session = reopen_audit(db_session, session.id)
    db_session.flush()

    assert new_session.status == 'draft'
    assert new_session.period_year == 2025
    assert new_session.period_month == 4

    db_session.refresh(txn)
    assert txn.is_locked is False
    assert txn.audit_session_id is None


def test_cannot_reopen_non_finalized(db_session):
    session = start_audit(db_session, 2025, 5)
    db_session.flush()

    with pytest.raises(ValueError, match='only reopen finalized'):
        reopen_audit(db_session, session.id)


# --- API Endpoints ---

def test_audit_start_endpoint(auth_client):
    resp = auth_client.post('/api/v1/audit/start', json={'year': 2025, 'month': 6})
    assert resp.status_code == 201
    data = resp.json()
    assert data['status'] == 'draft'
    assert data['period_year'] == 2025
    assert data['period_month'] == 6


def test_audit_sessions_list(auth_client):
    auth_client.post('/api/v1/audit/start', json={'year': 2025, 'month': 7})
    resp = auth_client.get('/api/v1/audit/sessions')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_audit_month_status_endpoint(auth_client):
    resp = auth_client.get('/api/v1/audit/month-status?year=2025&month=8')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'no_audit'
