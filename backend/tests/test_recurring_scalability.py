from __future__ import annotations

import calendar
import json
import uuid
from datetime import date

from sqlalchemy import event

from app.core.recurring import DETECTION_VERSION, detect_recurring_patterns
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


def _shift_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    source_last = calendar.monthrange(value.year, value.month)[1]
    target_last = calendar.monthrange(year, month)[1]
    day = target_last if value.day == source_last else min(value.day, target_last)
    return date(year, month, day)


def _transaction(db, merchant: str, transaction_date: date, amount: float):
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=transaction_date,
        raw_text=f"Recurring test {merchant}",
        merchant_raw=merchant,
        merchant_normalized=merchant,
        amount=amount,
        type="debit",
        instrument="statement",
        account_id=SAVINGS_ACCOUNT_ID,
        source="statement_upload",
        category="UTILITIES & BILLS",
        semantic_type="expense",
        status="settled",
    )
    db.add(transaction)
    return transaction


def test_full_recurring_scan_batches_selects_and_persists_evidence(db_session):
    expected_ids: dict[str, set[str]] = {}
    latest = date(2026, 7, 31)
    for merchant_index in range(120):
        merchant = f"SERVICE {merchant_index:03d}"
        expected_ids[merchant] = set()
        for occurrence in range(4):
            transaction = _transaction(
                db_session,
                merchant,
                _shift_months(latest, -occurrence),
                500 + merchant_index + occurrence,
            )
            expected_ids[merchant].add(transaction.id)
    db_session.flush()

    statements: list[str] = []
    engine = db_session.get_bind()

    def _count_statement(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        summary = detect_recurring_patterns(
            db_session,
            as_of=date(2026, 8, 9),
        )
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)

    assert summary.created == 120
    assert summary.scanned == 120
    assert statements.count("SELECT") <= 3
    patterns = db_session.query(RecurringPattern).all()
    assert len(patterns) == 120
    for pattern in patterns:
        assert pattern.detection_version == DETECTION_VERSION
        assert set(json.loads(pattern.evidence_transaction_ids_json)) == expected_ids[
            pattern.merchant_normalized
        ]
        assert pattern.evidence_count == 4
        assert pattern.next_expected == date(2026, 8, 31)


def test_full_scan_retires_stale_pattern_without_past_projection(db_session):
    merchant = "OLD MONTHLY SERVICE"
    evidence = [
        _transaction(
            db_session,
            merchant,
            _shift_months(date(2024, 4, 30), -occurrence),
            700,
        )
        for occurrence in range(4)
    ]
    existing = RecurringPattern(
        merchant_normalized=merchant,
        account_id=SAVINGS_ACCOUNT_ID,
        avg_amount=700,
        amount_stddev=0,
        frequency="monthly",
        last_occurrence=date(2024, 4, 30),
        next_expected=date(2024, 5, 31),
        times_detected=4,
        confidence=0.95,
        evidence_count=4,
        detection_status="active",
        is_active=True,
    )
    db_session.add(existing)
    db_session.flush()

    summary = detect_recurring_patterns(
        db_session,
        as_of=date(2026, 8, 9),
    )
    db_session.refresh(existing)

    assert summary.deactivated == 1
    assert existing.is_active is False
    assert existing.detection_status == "retired"
    assert existing.next_expected is None
    assert set(json.loads(existing.evidence_transaction_ids_json)) == {
        transaction.id for transaction in evidence
    }
    assert existing.detection_version == DETECTION_VERSION


def test_projection_keeps_non_month_end_anchor_after_february(db_session):
    merchant = "THIRTIETH DAY SERVICE"
    for transaction_date in (
        date(2025, 10, 30),
        date(2025, 11, 30),
        date(2025, 12, 30),
        date(2026, 1, 30),
    ):
        _transaction(db_session, merchant, transaction_date, 450)
    db_session.flush()

    detect_recurring_patterns(db_session, as_of=date(2026, 3, 1))
    pattern = db_session.query(RecurringPattern).filter_by(
        merchant_normalized=merchant
    ).one()

    assert pattern.next_expected == date(2026, 3, 30)


def test_full_scan_clears_provenance_for_unsupported_pattern(db_session):
    existing = RecurringPattern(
        merchant_normalized="REMOVED SERVICE",
        account_id=SAVINGS_ACCOUNT_ID,
        avg_amount=350,
        amount_stddev=0,
        frequency="monthly",
        last_occurrence=date(2026, 7, 1),
        next_expected=date(2026, 8, 1),
        times_detected=4,
        confidence=0.9,
        evidence_count=4,
        evidence_transaction_ids_json='["one","two","three","four"]',
        detection_status="active",
        is_active=True,
    )
    db_session.add(existing)
    db_session.flush()

    summary = detect_recurring_patterns(db_session, as_of=date(2026, 8, 9))
    db_session.refresh(existing)

    assert summary.deactivated == 1
    assert existing.is_active is False
    assert existing.detection_status == "retired"
    assert existing.next_expected is None
    assert existing.evidence_count == 0
    assert json.loads(existing.evidence_transaction_ids_json) == []
    assert existing.detection_version == DETECTION_VERSION
