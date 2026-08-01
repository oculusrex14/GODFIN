from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction
from app.core.transaction_semantics import (
    TransactionSemantic,
    semantic_type_for,
    spending_clause,
)

_EXCLUDED_STATUSES = {"deleted", "reversed", "reversal", "voided"}


@dataclass
class DetectionSummary:
    created: int = 0
    updated: int = 0
    deactivated: int = 0
    scanned: int = 0

    @property
    def detected(self) -> int:
        return self.created + self.updated

    def to_dict(self) -> dict[str, int]:
        return {
            "detected": self.detected,
            "created": self.created,
            "updated": self.updated,
            "deactivated": self.deactivated,
            "scanned": self.scanned,
        }


@dataclass
class PatternAnalysis:
    frequency: str
    median_interval_days: int
    avg_amount: float
    amount_stddev: float
    interval_variability: float
    amount_variability: float
    confidence: float
    evidence_count: int
    is_active: bool


def _is_reversal(transaction: Transaction) -> bool:
    return semantic_type_for(transaction) == TransactionSemantic.REVERSAL.value


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    source_last_day = calendar.monthrange(value.year, value.month)[1]
    target_last_day = calendar.monthrange(year, month)[1]
    day = target_last_day if value.day == source_last_day else min(value.day, target_last_day)
    return date(year, month, day)


def _next_expected(last_date: date, frequency: str) -> date:
    return _add_months(
        last_date,
        {"monthly": 1, "quarterly": 3, "annual": 12}[frequency],
    )


def _interval_fit(
    intervals: list[int],
    *,
    base_days: float,
    tolerance_days: float,
    max_skipped_cycles: int,
) -> tuple[bool, list[float]]:
    normalized = []
    for interval in intervals:
        cycles = max(1, round(interval / base_days))
        if cycles > max_skipped_cycles:
            return False, []
        expected = base_days * cycles
        if abs(interval - expected) > tolerance_days * cycles:
            return False, []
        normalized.append(interval / cycles)
    return True, normalized


def _analyze_pattern(txns: list[Transaction]) -> Optional[PatternAnalysis]:
    ordered = sorted(txns, key=lambda transaction: transaction.date)
    intervals = [
        (ordered[index].date - ordered[index - 1].date).days
        for index in range(1, len(ordered))
        if ordered[index].date > ordered[index - 1].date
    ]
    if not intervals:
        return None

    frequency = None
    normalized_intervals: list[float] = []
    monthly_fit, monthly_normalized = _interval_fit(
        intervals,
        base_days=30.4375,
        tolerance_days=7,
        max_skipped_cycles=3,
    )
    if monthly_fit and any(interval <= 45 for interval in intervals):
        frequency = "monthly"
        normalized_intervals = monthly_normalized
    else:
        quarterly_fit, quarterly_normalized = _interval_fit(
            intervals,
            base_days=91.3125,
            tolerance_days=14,
            max_skipped_cycles=2,
        )
        if quarterly_fit:
            frequency = "quarterly"
            normalized_intervals = quarterly_normalized
        else:
            annual_fit, annual_normalized = _interval_fit(
                intervals,
                base_days=365.25,
                tolerance_days=35,
                max_skipped_cycles=1,
            )
            if annual_fit:
                frequency = "annual"
                normalized_intervals = annual_normalized

    if not frequency:
        return None

    amounts = [float(transaction.amount) for transaction in ordered]
    avg_amount = statistics.mean(amounts)
    amount_stddev = statistics.stdev(amounts) if len(amounts) > 1 else 0.0
    amount_variability = amount_stddev / avg_amount if avg_amount > 0 else 1.0
    median_interval = statistics.median(normalized_intervals)
    interval_mad = statistics.median(
        abs(value - median_interval) for value in normalized_intervals
    )
    interval_variability = interval_mad / median_interval if median_interval else 1.0

    evidence_count = len(ordered)
    evidence_score = min(1.0, max(0.0, (evidence_count - 1) / 4))
    regularity_score = max(0.0, 1 - min(1.0, interval_variability / 0.25))
    amount_score = max(0.35, 1 - min(0.65, amount_variability))
    confidence = round(
        0.5 * evidence_score + 0.35 * regularity_score + 0.15 * amount_score,
        3,
    )
    is_active = evidence_count >= 3 and confidence >= 0.65
    return PatternAnalysis(
        frequency=frequency,
        median_interval_days=round(median_interval),
        avg_amount=round(avg_amount, 2),
        amount_stddev=round(amount_stddev, 2),
        interval_variability=round(interval_variability, 4),
        amount_variability=round(amount_variability, 4),
        confidence=confidence,
        evidence_count=evidence_count,
        is_active=is_active,
    )


def detect_recurring_patterns(
    db: Session,
    *,
    merchant_keys: Iterable[tuple[str, str | None]] | None = None,
) -> DetectionSummary:
    requested_keys = set(merchant_keys or [])
    query = (
        db.query(Transaction.merchant_normalized, Transaction.account_id)
        .filter(
            Transaction.status.notin_(_EXCLUDED_STATUSES),
            spending_clause(Transaction),
            Transaction.merchant_normalized.isnot(None),
        )
    )
    if requested_keys:
        query = query.filter(
            or_(
                *[
                    and_(
                        Transaction.merchant_normalized == merchant,
                        Transaction.account_id == account_id,
                    )
                    for merchant, account_id in requested_keys
                ]
            )
        )
    rows = (
        query.group_by(Transaction.merchant_normalized, Transaction.account_id)
        .having(func.count(Transaction.id) >= 2)
        .all()
    )
    scanned_keys = {(row.merchant_normalized, row.account_id) for row in rows}
    if requested_keys:
        scanned_keys |= requested_keys

    summary = DetectionSummary(scanned=len(scanned_keys))
    supported_pattern_ids: set[str] = set()
    for merchant, account_id in sorted(scanned_keys, key=lambda item: (item[0], item[1] or "")):
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.merchant_normalized == merchant,
                Transaction.account_id == account_id,
                Transaction.status.notin_(_EXCLUDED_STATUSES),
                spending_clause(Transaction),
            )
            .order_by(Transaction.date)
            .all()
        )
        txns = [transaction for transaction in txns if not _is_reversal(transaction)]
        analysis = _analyze_pattern(txns)
        existing = (
            db.query(RecurringPattern)
            .filter_by(merchant_normalized=merchant, account_id=account_id)
            .first()
        )
        if analysis is None:
            if existing and existing.is_active:
                existing.is_active = False
                existing.detection_status = "retired"
                summary.deactivated += 1
            continue

        last_date = txns[-1].date
        category = next(
            (transaction.category for transaction in reversed(txns) if transaction.category),
            None,
        )
        values = {
            "avg_amount": analysis.avg_amount,
            "amount_stddev": analysis.amount_stddev,
            "frequency": analysis.frequency,
            "avg_interval_days": analysis.median_interval_days,
            "last_occurrence": last_date,
            "next_expected": _next_expected(last_date, analysis.frequency),
            "times_detected": len(txns),
            "category": category,
            "confidence": analysis.confidence,
            "evidence_count": analysis.evidence_count,
            "interval_variability": analysis.interval_variability,
            "amount_variability": analysis.amount_variability,
            "detection_status": "active" if analysis.is_active else "candidate",
            "is_active": analysis.is_active,
        }
        if existing:
            was_supported = existing.detection_status in {"active", "candidate"}
            was_active = existing.is_active
            for key, value in values.items():
                setattr(existing, key, value)
            supported_pattern_ids.add(existing.id)
            if was_supported:
                summary.updated += 1
            else:
                summary.created += 1
            if was_active and not analysis.is_active:
                summary.deactivated += 1
        else:
            pattern = RecurringPattern(
                merchant_normalized=merchant,
                account_id=account_id,
                **values,
            )
            db.add(pattern)
            db.flush()
            supported_pattern_ids.add(pattern.id)
            summary.created += 1

    if merchant_keys is None:
        stale_query = db.query(RecurringPattern).filter(
            RecurringPattern.detection_status.in_(["active", "candidate"])
        )
        if supported_pattern_ids:
            stale_query = stale_query.filter(
                RecurringPattern.id.notin_(supported_pattern_ids)
            )
        for stale in stale_query.all():
            if stale.is_active:
                summary.deactivated += 1
            stale.is_active = False
            stale.detection_status = "retired"

    db.flush()
    return summary
