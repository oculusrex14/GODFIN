from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from statistics import median
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction
from app.core.transaction_semantics import is_spending, spending_clause


def build_weekly_digest(
    db: Session, *, today: date | None = None
) -> dict[str, Any]:
    today = today or date.today()
    week_start = today - timedelta(days=6)
    previous_start = week_start - timedelta(days=7)

    current_transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= week_start,
            Transaction.date <= today,
            Transaction.status != "deleted",
        )
        .order_by(Transaction.amount.desc())
        .all()
    )
    current_debits = [
        transaction
        for transaction in current_transactions
        if is_spending(transaction)
    ]
    current_spend = round(
        sum(float(transaction.amount) for transaction in current_debits), 2
    )
    previous_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= previous_start,
            Transaction.date < week_start,
            Transaction.status != "deleted",
            spending_clause(Transaction),
        )
        .scalar()
    )
    velocity_percent = (
        round(((current_spend - previous_spend) / previous_spend) * 100, 1)
        if previous_spend
        else None
    )

    amounts = [float(transaction.amount) for transaction in current_debits]
    typical = median(amounts) if amounts else 0
    anomaly_rows = current_debits[:3]
    anomalies = [
        {
            "transaction_id": transaction.id,
            "merchant": (
                transaction.merchant_normalized
                or transaction.merchant_raw
                or "Unknown merchant"
            ),
            "amount": round(float(transaction.amount), 2),
            "date": transaction.date.isoformat(),
            "reason": (
                f"{float(transaction.amount) / typical:.1f}× this week's median"
                if typical and float(transaction.amount) >= typical * 1.5
                else "One of the three largest debits this week"
                if typical
                else "Largest transaction this week"
            ),
        }
        for transaction in anomaly_rows
    ]

    goal_alerts = []
    for goal in (
        db.query(Goal)
        .filter(Goal.is_active.is_(True), Goal.deadline_date >= today)
        .all()
    ):
        start = goal.created_at.date() if goal.created_at else today
        duration = max(1, (goal.deadline_date - start).days)
        elapsed = min(duration, max(0, (today - start).days))
        expected = float(goal.target_amount) * elapsed / duration
        if float(goal.current_saved) + 0.01 < expected:
            goal_alerts.append(
                {
                    "goal_id": goal.id,
                    "name": goal.name,
                    "current_saved": round(float(goal.current_saved), 2),
                    "expected_saved": round(expected, 2),
                    "shortfall": round(expected - float(goal.current_saved), 2),
                }
            )

    new_merchants = [
        {
            "name": merchant.display_name or merchant.normalized_name,
            "category": merchant.category,
            "first_seen": merchant.last_updated.date().isoformat(),
        }
        for merchant in (
            db.query(MerchantMemory)
            .filter(MerchantMemory.last_updated >= datetime.combine(week_start, datetime.min.time()))
            .order_by(MerchantMemory.last_updated.desc())
            .limit(10)
            .all()
        )
    ]

    if velocity_percent is None:
        velocity_message = "No prior-week baseline is available yet."
    elif velocity_percent > 0:
        velocity_message = f"Spending is {velocity_percent:.1f}% higher than last week."
    elif velocity_percent < 0:
        velocity_message = f"Spending is {abs(velocity_percent):.1f}% lower than last week."
    else:
        velocity_message = "Spending is unchanged from last week."

    return {
        "period": {
            "start": week_start.isoformat(),
            "end": today.isoformat(),
        },
        "generated_at": datetime.now().isoformat(),
        "current_spend": current_spend,
        "previous_spend": round(previous_spend, 2),
        "spending_velocity_percent": velocity_percent,
        "spending_velocity_message": velocity_message,
        "anomalies": anomalies,
        "budget_breaches": goal_alerts,
        "new_merchants": new_merchants,
    }


def digest_to_html(digest: dict[str, Any]) -> str:
    def money(value: float) -> str:
        return f"₹{value:,.0f}"

    anomaly_items = "".join(
        (
            f"<li><strong>{escape(item['merchant'])}</strong> — "
            f"{money(item['amount'])} on {escape(item['date'])}"
            f"<br><small>{escape(item['reason'])}</small></li>"
        )
        for item in digest["anomalies"]
    ) or "<li>No unusual transactions this week.</li>"
    goal_items = "".join(
        (
            f"<li><strong>{escape(item['name'])}</strong> is "
            f"{money(item['shortfall'])} behind its current pace.</li>"
        )
        for item in digest["budget_breaches"]
    ) or "<li>No goal pacing alerts.</li>"
    merchant_items = "".join(
        f"<li>{escape(item['name'])} — {escape(item['category'])}</li>"
        for item in digest["new_merchants"]
    ) or "<li>No new merchants detected.</li>"
    return f"""<!doctype html>
<html><body style="font-family:system-ui,sans-serif;color:#172033">
<h1>GODFIN weekly digest</h1>
<p>{escape(digest['period']['start'])} to {escape(digest['period']['end'])}</p>
<p><strong>Spent this week:</strong> {money(digest['current_spend'])}<br>
{escape(digest['spending_velocity_message'])}</p>
<h2>Top anomalies</h2><ul>{anomaly_items}</ul>
<h2>Goal pacing</h2><ul>{goal_items}</ul>
<h2>New merchants</h2><ul>{merchant_items}</ul>
<p><small>Generated locally by GODFIN. Your financial database never left your device.</small></p>
</body></html>"""
