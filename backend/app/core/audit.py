from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY
from app.models.audit_log import AuditLog
from app.models.audit_session import AuditSession
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.transaction import Transaction
from app.core.transaction_semantics import spending_clause, verified_income_clause


class FinalizedPeriodError(ValueError):
    """Raised when a ledger write targets a finalized accounting period."""

    def __init__(self, transaction_date: date):
        self.transaction_date = transaction_date
        self.period = transaction_date.strftime("%Y-%m")
        super().__init__(
            f"{self.period} is finalized. Reopen the month before adding "
            "transactions dated in this period."
        )


def assert_period_writable(db: Session, transaction_date: date) -> None:
    """Enforce the accounting-period write boundary for every ledger ingress.

    Reopening creates a newer draft session while retaining the prior session
    as non-authoritative history, so the latest active session is the
    authoritative period state.
    """
    latest_session = (
        db.query(AuditSession)
        .filter_by(
            period_year=transaction_date.year,
            period_month=transaction_date.month,
        )
        .filter(
            AuditSession.status.in_(["draft", "finalized", "locked"])
        )
        .order_by(AuditSession.created_at.desc(), AuditSession.id.desc())
        .first()
    )
    if latest_session and latest_session.status in {"finalized", "locked"}:
        raise FinalizedPeriodError(transaction_date)


def get_month_status(db: Session, year: int, month: int) -> str:
    """Returns 'finalized', 'draft', or 'no_audit' for a given month."""
    session = (
        db.query(AuditSession)
        .filter_by(period_year=year, period_month=month)
        .filter(AuditSession.status.in_(['draft', 'finalized', 'locked']))
        .order_by(AuditSession.created_at.desc(), AuditSession.id.desc())
        .first()
    )
    if session is None:
        return 'no_audit'
    return 'finalized' if session.status == 'locked' else session.status


def start_audit(db: Session, year: int, month: int) -> AuditSession:
    """Create a draft audit session. Enforces one-draft-at-a-time."""
    # Check for existing active session
    existing = (
        db.query(AuditSession)
        .filter(AuditSession.status == 'draft')
        .first()
    )
    if existing:
        raise ValueError(
            f'A draft audit is already in progress for '
            f'{existing.period_year}-{existing.period_month:02d}. '
            f'Finalize or discard it first.'
        )

    # Check this month isn't already finalized
    finalized = (
        db.query(AuditSession)
        .filter_by(period_year=year, period_month=month, status='finalized')
        .first()
    )
    if finalized:
        raise ValueError(
            f'{year}-{month:02d} is already finalized. Reopen it first.'
        )

    session = AuditSession(
        period_year=year,
        period_month=month,
        status='draft',
    )
    db.add(session)
    db.flush()
    return session


def finalize_audit(db: Session, session_id: str) -> AuditSession:
    """Finalize an audit: lock transactions, compute aggregates."""
    session = db.query(AuditSession).filter_by(id=session_id).first()
    if not session:
        raise ValueError('Audit session not found')
    if session.status != 'draft':
        raise ValueError(f'Cannot finalize a session with status: {session.status}')

    year, month = session.period_year, session.period_month
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Lock all transactions for this month
    txns = db.query(Transaction).filter(
        Transaction.date >= month_start,
        Transaction.date < month_end,
        Transaction.status != 'deleted',
    ).all()

    for txn in txns:
        txn.is_locked = True
        txn.audit_session_id = session_id

    # Compute aggregates
    aggregate = _compute_aggregate(db, year, month, month_start, month_end, session_id)

    # Count changes during this audit
    change_count = db.query(AuditLog).filter(
        AuditLog.created_at >= session.created_at,
    ).count()

    # Feedback loop: user-corrected transactions improve future classification
    _update_merchant_memory_from_corrections(db, txns)

    session.status = 'finalized'
    session.finalized_at = datetime.now(timezone.utc)
    session.change_summary = f'{len(txns)} transactions locked, {change_count} changes recorded'

    db.flush()
    return session


def discard_audit(db: Session, session_id: str) -> AuditSession:
    """Discard a draft audit session."""
    session = db.query(AuditSession).filter_by(id=session_id).first()
    if not session:
        raise ValueError('Audit session not found')
    if session.status != 'draft':
        raise ValueError('Can only discard draft sessions')

    session.status = 'discarded'
    db.flush()
    return session


def reopen_audit(db: Session, session_id: str) -> AuditSession:
    """Reopen a finalized month: unlock transactions, create new draft."""
    session = db.query(AuditSession).filter_by(id=session_id).first()
    if not session:
        raise ValueError('Audit session not found')
    if session.status != 'finalized':
        raise ValueError('Can only reopen finalized sessions')

    year, month = session.period_year, session.period_month
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Unlock transactions
    txns = db.query(Transaction).filter(
        Transaction.date >= month_start,
        Transaction.date < month_end,
        Transaction.audit_session_id == session_id,
    ).all()
    for txn in txns:
        txn.is_locked = False
        txn.audit_session_id = None

    # Mark aggregate as not finalized
    agg = db.query(MonthlyAggregate).filter_by(
        audit_session_id=session_id
    ).first()
    if agg:
        agg.is_finalized = False

    # Retain the old session as non-authoritative history. This also releases
    # the partial unique index before the replacement draft is created.
    session.status = 'discarded'
    prior_summary = (session.change_summary or '').strip()
    session.change_summary = (
        f"{prior_summary} Reopened; this audit was superseded by a new draft."
    ).strip()
    db.flush()

    # Create new draft
    new_session = AuditSession(
        period_year=year,
        period_month=month,
        status='draft',
    )
    db.add(new_session)
    db.flush()
    return new_session


def _compute_aggregate(
    db: Session, year: int, month: int,
    month_start: date, month_end: date,
    session_id: str,
) -> MonthlyAggregate:
    """Compute and store monthly aggregate for finalization."""
    base = db.query(Transaction).filter(
        Transaction.date >= month_start,
        Transaction.date < month_end,
        Transaction.status != 'deleted',
    )

    total_spend = float(
        base.filter(spending_clause(Transaction))
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )
    total_income = float(
        base.filter(verified_income_clause(Transaction))
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    savings_rate = None
    if total_income > 0:
        savings_rate = round(((total_income - total_spend) / total_income) * 100, 1)

    transaction_count = base.filter(
        spending_clause(Transaction)
    ).count()

    # Elasticity totals
    fixed_total = 0.0
    semi_flex_total = 0.0
    flex_total = 0.0
    transfer_total = 0.0

    cat_rows = (
        base.filter(spending_clause(Transaction), Transaction.category.isnot(None))
        .with_entities(Transaction.category, func.sum(Transaction.amount).label('total'))
        .group_by(Transaction.category)
        .all()
    )

    cat_breakdown = {}
    for row in cat_rows:
        amt = float(row.total)
        cat_breakdown[row.category] = round(amt, 2)
        elast = ELASTICITY.get(row.category, 'flexible')
        if elast == 'fixed':
            fixed_total += amt
        elif elast == 'semi_flexible':
            semi_flex_total += amt
        elif elast == 'flexible':
            flex_total += amt
        elif elast == 'none':
            transfer_total += amt

    # Recurring total
    recurring_total = float(
        base.filter(Transaction.is_recurring == True, spending_clause(Transaction))
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    # Upsert aggregate
    month_str = f'{year}-{month:02d}'
    agg = db.query(MonthlyAggregate).filter_by(month=month_str, account_id=None).first()
    if agg is None:
        agg = MonthlyAggregate(month=month_str)
        db.add(agg)

    agg.total_spend = round(total_spend, 2)
    agg.total_income = round(total_income, 2)
    agg.savings_rate = savings_rate
    agg.fixed_total = round(fixed_total, 2)
    agg.semi_flexible_total = round(semi_flex_total, 2)
    agg.flexible_total = round(flex_total, 2)
    agg.transfer_total = round(transfer_total, 2)
    agg.recurring_total = round(recurring_total, 2)
    agg.category_breakdown = json.dumps(cat_breakdown)
    agg.transaction_count = transaction_count
    agg.is_finalized = True
    agg.audit_session_id = session_id
    agg.computed_at = datetime.now(timezone.utc)

    db.flush()
    return agg


def _update_merchant_memory_from_corrections(db: Session, txns: list) -> None:
    """
    After audit finalization, scan user-corrected transactions and upsert
    their merchant→category mappings into merchant_memory. This ensures
    manual corrections during audit improve future auto-classification.
    """
    from app.core.merchant_memory_service import upsert_merchant_memory

    for txn in txns:
        if txn.classification_source != 'user':
            continue
        if not txn.merchant_normalized or not txn.category:
            continue

        upsert_merchant_memory(
            db,
            txn.merchant_normalized,
            txn.category,
            txn.subcategory,
            confidence=1.0,
            raw_string=txn.merchant_raw,
        )

    db.flush()
