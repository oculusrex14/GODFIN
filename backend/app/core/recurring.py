from __future__ import annotations

import calendar
import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.money import exact_money_statement_values
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction
from app.core.transaction_semantics import (
    TransactionSemantic,
    semantic_type_for,
    spending_clause,
)

_EXCLUDED_STATUSES = {"deleted", "reversed", "reversal", "voided"}
DETECTION_VERSION = "2.0"
_STALE_CYCLES = {"monthly": 3, "quarterly": 2, "annual": 2}


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


def _next_expected(
    last_date: date,
    frequency: str,
    *,
    after: date,
) -> date:
    months = {"monthly": 1, "quarterly": 3, "annual": 12}[frequency]
    cycles = 1
    expected = _add_months(last_date, months)
    while expected <= after:
        cycles += 1
        # Always project from the observed date so a February clamp does not
        # permanently move a 29th/30th billing anchor to month-end.
        expected = _add_months(last_date, months * cycles)
    return expected


def _is_stale(last_date: date, frequency: str, *, as_of: date) -> bool:
    months = {"monthly": 1, "quarterly": 3, "annual": 12}[frequency]
    return as_of > _add_months(
        last_date,
        months * _STALE_CYCLES[frequency],
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


def _insert_pattern_if_absent(
    db: Session,
    *,
    merchant: str,
    account_id: Optional[str],
    values: dict,
) -> str | None:
    """Insert one pattern behind the database uniqueness boundary."""
    insert_values = dict(values)
    money_values = exact_money_statement_values(
        RecurringPattern.__table__,
        {
            "avg_amount": insert_values.pop("avg_amount"),
            "amount_stddev": insert_values.pop("amount_stddev"),
        },
    )
    insert_values.update(money_values)
    insert_values.update(
        {
            "id": str(uuid.uuid4()),
            "merchant_normalized": merchant,
            "account_id": account_id,
        }
    )
    statement = sqlite_insert(RecurringPattern).values(insert_values)
    if account_id is None:
        statement = statement.on_conflict_do_nothing(
            index_elements=[RecurringPattern.merchant_normalized],
            index_where=RecurringPattern.account_id.is_(None),
        )
    else:
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                RecurringPattern.merchant_normalized,
                RecurringPattern.account_id,
            ],
            index_where=RecurringPattern.account_id.is_not(None),
        )
    return db.execute(
        statement.returning(RecurringPattern.id)
    ).scalar_one_or_none()


def detect_recurring_patterns(
    db: Session,
    *,
    merchant_keys: Iterable[tuple[str, str | None]] | None = None,
    as_of: date | None = None,
) -> DetectionSummary:
    requested_keys = set(merchant_keys or [])
    reference_date = as_of or date.today()
    transaction_query = (
        db.query(Transaction)
        .filter(
            Transaction.status.notin_(_EXCLUDED_STATUSES),
            spending_clause(Transaction),
            Transaction.merchant_normalized.isnot(None),
        )
    )
    if requested_keys:
        transaction_query = transaction_query.filter(
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
    transactions = (
        transaction_query.order_by(
            Transaction.merchant_normalized,
            Transaction.account_id,
            Transaction.date,
            Transaction.id,
        )
        .all()
    )
    grouped: dict[tuple[str, str | None], list[Transaction]] = {}
    for transaction in transactions:
        if _is_reversal(transaction):
            continue
        grouped.setdefault(
            (transaction.merchant_normalized, transaction.account_id),
            [],
        ).append(transaction)
    scanned_keys = {
        key for key, values in grouped.items() if len(values) >= 2
    }
    if requested_keys:
        scanned_keys |= requested_keys

    summary = DetectionSummary(scanned=len(scanned_keys))
    supported_pattern_ids: set[str] = set()
    existing_query = db.query(RecurringPattern)
    if requested_keys:
        existing_query = existing_query.filter(
            or_(
                *[
                    and_(
                        RecurringPattern.merchant_normalized == merchant,
                        RecurringPattern.account_id == account_id,
                    )
                    for merchant, account_id in requested_keys
                ]
            )
        )
    existing_by_key = {
        (pattern.merchant_normalized, pattern.account_id): pattern
        for pattern in existing_query.all()
    }

    for merchant, account_id in sorted(
        scanned_keys,
        key=lambda item: (item[0], item[1] or ""),
    ):
        txns = grouped.get((merchant, account_id), [])
        analysis = _analyze_pattern(txns)
        existing = existing_by_key.get((merchant, account_id))
        if analysis is None:
            if existing and existing.detection_status in {"active", "candidate"}:
                was_active = existing.is_active
                existing.is_active = False
                existing.detection_status = "retired"
                existing.next_expected = None
                existing.detection_version = DETECTION_VERSION
                existing.evidence_transaction_ids_json = "[]"
                existing.evidence_count = 0
                if was_active:
                    summary.deactivated += 1
            continue

        last_date = txns[-1].date
        stale = _is_stale(
            last_date,
            analysis.frequency,
            as_of=reference_date,
        )
        if stale and existing is None:
            continue
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
            "next_expected": (
                None
                if stale
                else _next_expected(
                    last_date,
                    analysis.frequency,
                    after=reference_date,
                )
            ),
            "times_detected": len(txns),
            "category": category,
            "confidence": analysis.confidence,
            "evidence_count": analysis.evidence_count,
            "interval_variability": analysis.interval_variability,
            "amount_variability": analysis.amount_variability,
            "detection_status": (
                "retired"
                if stale
                else "active" if analysis.is_active else "candidate"
            ),
            "is_active": analysis.is_active and not stale,
            "evidence_transaction_ids_json": json.dumps(
                [transaction.id for transaction in txns],
                separators=(",", ":"),
            ),
            "detection_version": DETECTION_VERSION,
        }
        if existing:
            was_supported = existing.detection_status in {"active", "candidate"}
            was_active = existing.is_active
            for key, value in values.items():
                setattr(existing, key, value)
            if not stale:
                supported_pattern_ids.add(existing.id)
            if stale:
                if was_active:
                    summary.deactivated += 1
            elif was_supported:
                summary.updated += 1
            else:
                summary.created += 1
            if was_active and not analysis.is_active and not stale:
                summary.deactivated += 1
        else:
            created_id = _insert_pattern_if_absent(
                db,
                merchant=merchant,
                account_id=account_id,
                values=values,
            )
            if created_id is None:
                pattern = (
                    db.query(RecurringPattern)
                    .filter_by(merchant_normalized=merchant, account_id=account_id)
                    .one()
                )
                for key, value in values.items():
                    setattr(pattern, key, value)
                supported_pattern_ids.add(pattern.id)
            else:
                supported_pattern_ids.add(created_id)
            if created_id is not None:
                summary.created += 1
            else:
                summary.updated += 1

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
            stale.next_expected = None
            stale.evidence_count = 0
            stale.evidence_transaction_ids_json = "[]"
            stale.detection_version = DETECTION_VERSION

    db.flush()
    return summary
