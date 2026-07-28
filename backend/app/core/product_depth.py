from __future__ import annotations

import calendar
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion
from app.models.transaction import Transaction
from app.models.transfer_match import TransferMatch


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = (int(part) for part in month.split("-", 1))
    start = date(year, mon, 1)
    end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
    return start, end


def cash_flow_calendar(db: Session, month: str) -> dict[str, Any]:
    start, end = month_bounds(month)
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.status != "deleted",
            Transaction.is_transfer.is_(False),
        )
        .all()
    )
    by_day: dict[date, dict[str, float | int]] = {}
    for txn in rows:
        day = by_day.setdefault(
            txn.date, {"spend": 0.0, "income": 0.0, "transaction_count": 0}
        )
        day["transaction_count"] += 1
        if txn.type == "debit" and not txn.is_income:
            day["spend"] += float(txn.amount)
        elif txn.is_income:
            day["income"] += float(txn.amount)

    days = []
    total_spend = 0.0
    total_income = 0.0
    for day_number in range(1, calendar.monthrange(start.year, start.month)[1] + 1):
        current = date(start.year, start.month, day_number)
        values = by_day.get(
            current, {"spend": 0.0, "income": 0.0, "transaction_count": 0}
        )
        spend = round(float(values["spend"]), 2)
        income = round(float(values["income"]), 2)
        total_spend += spend
        total_income += income
        days.append(
            {
                "date": current.isoformat(),
                "spend": spend,
                "income": income,
                "net": round(income - spend, 2),
                "transaction_count": int(values["transaction_count"]),
            }
        )

    return {
        "month": month,
        "days": days,
        "total_spend": round(total_spend, 2),
        "total_income": round(total_income, 2),
        "net": round(total_income - total_spend, 2),
        "max_daily_flow": round(
            max((max(day["spend"], day["income"]) for day in days), default=0), 2
        ),
    }


def scan_transfer_candidates(
    db: Session,
    *,
    max_date_gap_days: int = 3,
    amount_tolerance_percent: float = 0.005,
) -> int:
    existing_pairs = {
        (row.debit_transaction_id, row.credit_transaction_id)
        for row in db.query(TransferMatch).all()
    }
    debits = (
        db.query(Transaction)
        .filter(
            Transaction.type == "debit",
            Transaction.status != "deleted",
            Transaction.is_transfer.is_(False),
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    credits = (
        db.query(Transaction)
        .filter(
            Transaction.type == "credit",
            Transaction.status != "deleted",
            Transaction.is_transfer.is_(False),
        )
        .order_by(Transaction.date.desc())
        .all()
    )

    created = 0
    credits_by_amount = sorted(
        ((float(credit.amount), credit) for credit in credits),
        key=lambda item: item[0],
    )
    credit_amounts = [item[0] for item in credits_by_amount]
    for debit in debits:
        tolerance = max(1.0, float(debit.amount) * amount_tolerance_percent)
        lower = bisect_left(credit_amounts, float(debit.amount) - tolerance)
        upper = bisect_right(credit_amounts, float(debit.amount) + tolerance)
        for _, credit in credits_by_amount[lower:upper]:
            if debit.account_id == credit.account_id:
                continue
            gap = abs((debit.date - credit.date).days)
            if gap > max_date_gap_days:
                continue
            amount_gap = abs(float(debit.amount) - float(credit.amount))
            if amount_gap > tolerance:
                continue
            pair = (debit.id, credit.id)
            if pair in existing_pairs:
                continue
            amount_score = max(0.0, 1 - amount_gap / max(tolerance, 1.0))
            date_score = max(0.0, 1 - gap / (max_date_gap_days + 1))
            confidence = round(0.7 * amount_score + 0.3 * date_score, 3)
            db.add(
                TransferMatch(
                    debit_transaction_id=debit.id,
                    credit_transaction_id=credit.id,
                    amount=round((float(debit.amount) + float(credit.amount)) / 2, 2),
                    date_gap_days=gap,
                    confidence=confidence,
                )
            )
            existing_pairs.add(pair)
            created += 1
    db.flush()
    return created


def transfer_match_to_dict(
    match: TransferMatch,
    transactions: dict[str, Transaction],
    accounts: dict[str, Account],
) -> dict[str, Any]:
    def txn_payload(txn_id: str) -> dict[str, Any]:
        txn = transactions[txn_id]
        account = accounts.get(txn.account_id)
        return {
            "id": txn.id,
            "date": txn.date.isoformat(),
            "merchant": txn.merchant_normalized or txn.merchant_raw or txn.raw_text[:80],
            "amount": float(txn.amount),
            "type": txn.type,
            "account": (
                account.nickname
                if account and account.nickname
                else f"{account.bank} ••••{account.last_4_digits}"
                if account
                else "Unknown account"
            ),
        }

    return {
        "id": match.id,
        "amount": match.amount,
        "date_gap_days": match.date_gap_days,
        "confidence": match.confidence,
        "status": match.status,
        "snoozed_until": (
            match.snoozed_until.isoformat() if match.snoozed_until else None
        ),
        "decision_note": match.decision_note,
        "debit": txn_payload(match.debit_transaction_id),
        "credit": txn_payload(match.credit_transaction_id),
    }


def list_transfer_matches(
    db: Session, *, include_resolved: bool = False
) -> list[dict[str, Any]]:
    query = db.query(TransferMatch)
    if not include_resolved:
        query = query.filter(
            or_(
                TransferMatch.status == "pending",
                (
                    (TransferMatch.status == "snoozed")
                    & (
                        (TransferMatch.snoozed_until.is_(None))
                        | (TransferMatch.snoozed_until <= date.today())
                    )
                ),
            )
        )
    matches = query.order_by(TransferMatch.confidence.desc()).all()
    transaction_ids = {
        txn_id
        for match in matches
        for txn_id in (match.debit_transaction_id, match.credit_transaction_id)
    }
    transactions = {
        txn.id: txn
        for txn in db.query(Transaction).filter(Transaction.id.in_(transaction_ids)).all()
    }
    accounts = {account.id: account for account in db.query(Account).all()}
    return [
        transfer_match_to_dict(match, transactions, accounts)
        for match in matches
        if match.debit_transaction_id in transactions
        and match.credit_transaction_id in transactions
    ]


def decide_transfer_match(
    db: Session,
    match: TransferMatch,
    decision: str,
    *,
    snooze_days: int = 7,
    note: str | None = None,
) -> None:
    debit = db.query(Transaction).filter_by(id=match.debit_transaction_id).one()
    credit = db.query(Transaction).filter_by(id=match.credit_transaction_id).one()
    match.decision_note = note
    if decision == "confirm":
        match.status = "confirmed"
        match.snoozed_until = None
        for txn in (debit, credit):
            txn.is_transfer = True
            txn.category = "TRANSFERS"
            txn.subcategory = "Matched Transfer"
        db.query(TransferMatch).filter(
            TransferMatch.id != match.id,
            TransferMatch.status.in_(["pending", "snoozed"]),
            or_(
                TransferMatch.debit_transaction_id.in_([debit.id, credit.id]),
                TransferMatch.credit_transaction_id.in_([debit.id, credit.id]),
            ),
        ).update(
            {
                TransferMatch.status: "ignored",
                TransferMatch.decision_note: "Another transfer candidate was confirmed.",
            },
            synchronize_session=False,
        )
    elif decision == "ignore":
        match.status = "ignored"
        match.snoozed_until = None
    elif decision == "snooze":
        match.status = "snoozed"
        match.snoozed_until = date.today() + timedelta(days=snooze_days)
    else:
        raise ValueError("Unsupported decision")


def sync_subscription_suggestions(db: Session) -> int:
    from app.core.recurring import detect_recurring_patterns
    from app.models.recurring_pattern import RecurringPattern

    detect_recurring_patterns(db)
    existing = {
        suggestion.recurring_pattern_id
        for suggestion in db.query(SubscriptionSuggestion).all()
    }
    created = 0
    patterns = db.query(RecurringPattern).filter_by(is_active=True).all()
    for pattern in patterns:
        if pattern.id in existing:
            continue
        db.add(
            SubscriptionSuggestion(
                recurring_pattern_id=pattern.id,
                merchant=pattern.merchant_normalized,
                avg_amount=pattern.avg_amount,
                frequency=pattern.frequency,
                category=pattern.category,
                next_expected=pattern.next_expected,
            )
        )
        created += 1
    db.flush()
    return created


def decide_subscription_suggestion(
    db: Session,
    suggestion: SubscriptionSuggestion,
    decision: str,
    *,
    snooze_days: int = 7,
) -> Subscription | None:
    if decision == "confirm":
        if suggestion.confirmed_subscription_id:
            return (
                db.query(Subscription)
                .filter_by(id=suggestion.confirmed_subscription_id)
                .first()
            )
        frequency = (
            suggestion.frequency
            if suggestion.frequency in {"monthly", "quarterly", "annual"}
            else "monthly"
        )
        subscription = Subscription(
            name=suggestion.merchant.title(),
            amount=suggestion.avg_amount,
            currency="INR",
            frequency=frequency,
            category=suggestion.category,
            next_payment_date=suggestion.next_expected,
            is_active=True,
            notes="Confirmed from GODFIN recurring detection.",
        )
        db.add(subscription)
        db.flush()
        suggestion.status = "confirmed"
        suggestion.snoozed_until = None
        suggestion.confirmed_subscription_id = subscription.id
        return subscription
    if decision == "ignore":
        suggestion.status = "ignored"
        suggestion.snoozed_until = None
        return None
    if decision == "snooze":
        suggestion.status = "snoozed"
        suggestion.snoozed_until = date.today() + timedelta(days=snooze_days)
        return None
    raise ValueError("Unsupported decision")


def upcoming_subscription_reminders(
    db: Session, *, days: int = 7
) -> list[dict[str, Any]]:
    today = date.today()
    horizon = today + timedelta(days=days)
    reminders = []
    for subscription in db.query(Subscription).filter_by(is_active=True).all():
        due = subscription.next_payment_date
        if not due:
            continue
        while due < today:
            if subscription.frequency == "annual":
                next_year = due.year + 1
                due = date(
                    next_year,
                    due.month,
                    min(due.day, calendar.monthrange(next_year, due.month)[1]),
                )
            elif subscription.frequency == "quarterly":
                month_index = due.year * 12 + due.month - 1 + 3
                last_day = calendar.monthrange(
                    month_index // 12, month_index % 12 + 1
                )[1]
                due = date(
                    month_index // 12,
                    month_index % 12 + 1,
                    min(due.day, last_day),
                )
            else:
                month_index = due.year * 12 + due.month
                last_day = calendar.monthrange(
                    month_index // 12, month_index % 12 + 1
                )[1]
                due = date(
                    month_index // 12,
                    month_index % 12 + 1,
                    min(due.day, last_day),
                )
        if due <= horizon:
            reminders.append(
                {
                    "id": subscription.id,
                    "name": subscription.name,
                    "amount": subscription.amount,
                    "currency": subscription.currency or "INR",
                    "frequency": subscription.frequency,
                    "due_date": due.isoformat(),
                    "days_until": (due - today).days,
                }
            )
    return sorted(reminders, key=lambda item: (item["due_date"], item["name"]))
