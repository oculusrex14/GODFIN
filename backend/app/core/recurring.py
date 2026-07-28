from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction


def detect_recurring_patterns(db: Session) -> int:
    # Get all non-deleted debits grouped by merchant
    rows = (
        db.query(
            Transaction.merchant_normalized,
            Transaction.account_id,
            Transaction.category,
        )
        .filter(
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
            Transaction.merchant_normalized.isnot(None),
        )
        .group_by(Transaction.merchant_normalized, Transaction.account_id)
        .having(func.count(Transaction.id) >= 2)
        .all()
    )

    detected = 0
    for row in rows:
        merchant = row.merchant_normalized
        account_id = row.account_id
        category = row.category

        txns = (
            db.query(Transaction)
            .filter(
                Transaction.merchant_normalized == merchant,
                Transaction.account_id == account_id,
                Transaction.status != 'deleted',
                Transaction.type == 'debit',
            )
            .order_by(Transaction.date)
            .all()
        )

        if len(txns) < 2:
            continue

        pattern = _analyze_pattern(txns)
        if pattern is None:
            continue

        freq, avg_interval, avg_amount, stddev = pattern

        # Upsert recurring pattern
        existing = db.query(RecurringPattern).filter_by(
            merchant_normalized=merchant,
            account_id=account_id,
        ).first()

        last_date = txns[-1].date
        next_expected = last_date + timedelta(days=avg_interval)

        if existing:
            existing.avg_amount = avg_amount
            existing.amount_stddev = stddev
            existing.frequency = freq
            existing.avg_interval_days = avg_interval
            existing.last_occurrence = last_date
            existing.next_expected = next_expected
            existing.times_detected = len(txns)
            existing.category = category
        else:
            db.add(RecurringPattern(
                merchant_normalized=merchant,
                account_id=account_id,
                avg_amount=avg_amount,
                amount_stddev=stddev,
                frequency=freq,
                avg_interval_days=avg_interval,
                last_occurrence=last_date,
                next_expected=next_expected,
                times_detected=len(txns),
                category=category,
            ))
            detected += 1

    db.flush()
    return detected


def _analyze_pattern(txns: list) -> Optional[tuple]:
    dates = [t.date for t in txns]
    amounts = [t.amount for t in txns]

    intervals = []
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if delta > 0:
            intervals.append(delta)

    if not intervals:
        return None

    avg_interval = statistics.mean(intervals)
    avg_amount = statistics.mean(amounts)
    stddev = statistics.stdev(amounts) if len(amounts) > 1 else 0.0

    # Amount coefficient of variation
    cv = (stddev / avg_amount * 100) if avg_amount > 0 else 0

    # Monthly: 28-31 day interval
    if 25 <= avg_interval <= 35:
        if cv <= 5:
            return ('monthly', round(avg_interval), round(avg_amount, 2), round(stddev, 2))
        elif cv <= 50:
            return ('monthly', round(avg_interval), round(avg_amount, 2), round(stddev, 2))

    # Quarterly: 85-95 days
    if 80 <= avg_interval <= 100:
        return ('quarterly', round(avg_interval), round(avg_amount, 2), round(stddev, 2))

    # Annual: 360-370 days
    if 355 <= avg_interval <= 375:
        return ('annual', round(avg_interval), round(avg_amount, 2), round(stddev, 2))

    return None
