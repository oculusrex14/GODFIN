from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY
from app.core.net_worth import liquid_asset_total
from app.core.transaction_semantics import (
    active_clause,
    is_spending,
    is_verified_income,
)
from app.models.app_setting import AppSetting
from app.models.behavior_insight import BehaviorInsightPreference
from app.models.subscription import Subscription
from app.models.transaction import Transaction

WINDOW_DAYS = 180
BUDGET_KEY = "behavior_monthly_budget"


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _confidence(month_count: int) -> str:
    if month_count >= 6:
        return "high"
    if month_count >= 3:
        return "medium"
    return "low"


def _safe_cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    denominator = statistics.fmean(abs(value) for value in values)
    if denominator <= 0:
        return 0.0
    return statistics.pstdev(values) / denominator * 100


def _monthly_subscription_cost(db: Session) -> float:
    divisors = {"monthly": 1, "quarterly": 3, "annual": 12}
    return sum(
        float(item.amount) / divisors.get(item.frequency, 1)
        for item in db.query(Subscription).filter(Subscription.is_active.is_(True))
    )


def _preference_map(db: Session) -> dict[str, BehaviorInsightPreference]:
    return {
        preference.metric_key: preference
        for preference in db.query(BehaviorInsightPreference).all()
    }


def compute_behavior_insights(
    db: Session,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date <= today,
            active_clause(Transaction),
        )
        .all()
    )
    by_month: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "spend": 0.0, "discretionary": 0.0}
    )
    weekly_counts: dict[tuple[int, int], set[date]] = defaultdict(set)
    debit_transactions: list[Transaction] = []
    total_spend = 0.0
    discretionary = 0.0
    flexible_categories = {
        category for category, elasticity in ELASTICITY.items() if elasticity == "flexible"
    }
    for transaction in transactions:
        month = by_month[_month_key(transaction.date)]
        included_in_behavior = False
        if is_verified_income(transaction):
            month["income"] += float(transaction.amount)
            included_in_behavior = True
        elif is_spending(transaction):
            amount = float(transaction.amount)
            debit_transactions.append(transaction)
            month["spend"] += amount
            total_spend += amount
            included_in_behavior = True
            if transaction.category in flexible_categories:
                month["discretionary"] += amount
                discretionary += amount
        if included_in_behavior:
            iso = transaction.date.isocalendar()
            weekly_counts[(iso.year, iso.week)].add(transaction.date)

    complete_months = sorted(by_month)
    income_months = [
        values for values in by_month.values() if values["income"] > 0
    ]
    confidence = _confidence(len(complete_months))
    preferences = _preference_map(db)
    period = f"{start.isoformat()} through {today.isoformat()}"

    def metric(
        key: str,
        label: str,
        value: float | None,
        unit: str,
        meaning: str,
        formula: str,
        inputs: str,
        evidence: str,
        caveat: str,
    ) -> dict[str, Any]:
        preference = preferences.get(key)
        return {
            "key": key,
            "label": label,
            "value": round(value, 1) if value is not None else None,
            "unit": unit,
            "meaning": meaning,
            "formula": formula,
            "inputs": inputs,
            "period": period,
            "evidence": evidence,
            "confidence": confidence,
            "provenance": "Deterministic local calculation from included GODFIN data.",
            "caveat": caveat,
            "difficulty": {
                "savings_consistency": "easy",
                "budget_adherence": "easy",
                "subscription_load": "easy",
                "discretionary_ratio": "intermediate",
                "buffer_coverage": "intermediate",
                "routine_stability": "advanced",
                "cash_flow_volatility": "advanced",
            }.get(key, "intermediate"),
            "hidden": bool(preference and preference.hidden),
            "correction_note": (
                preference.correction_note if preference else None
            ),
        }

    positive_savings = sum(
        values["income"] - values["spend"] >= 0 for values in income_months
    )
    savings_consistency = (
        positive_savings / len(income_months) * 100 if income_months else None
    )
    monthly_nets = [
        values["income"] - values["spend"] for values in by_month.values()
    ]
    cash_flow_volatility = _safe_cv(monthly_nets) if monthly_nets else None
    discretionary_ratio = (
        discretionary / total_spend * 100 if total_spend > 0 else None
    )

    budget_setting = db.query(AppSetting).filter_by(key=BUDGET_KEY).first()
    try:
        monthly_budget = float(budget_setting.value) if budget_setting else None
    except (TypeError, ValueError):
        monthly_budget = None
    budget_adherence = None
    if monthly_budget and complete_months:
        budget_adherence = (
            sum(values["spend"] <= monthly_budget for values in by_month.values())
            / len(complete_months)
            * 100
        )

    average_income = (
        statistics.fmean(values["income"] for values in income_months)
        if income_months
        else 0
    )
    subscription_cost = _monthly_subscription_cost(db)
    subscription_load = (
        subscription_cost / average_income * 100 if average_income > 0 else None
    )
    average_spend = (
        statistics.fmean(values["spend"] for values in by_month.values())
        if complete_months
        else 0
    )
    buffer_coverage = (
        liquid_asset_total(db) / average_spend if average_spend > 0 else None
    )
    active_days = [float(len(days)) for days in weekly_counts.values()]
    routine_stability = (
        max(0.0, 100.0 - min(100.0, _safe_cv(active_days)))
        if active_days
        else None
    )

    metrics = [
        metric(
            "savings_consistency",
            "Months your income covered spending",
            savings_consistency,
            "%",
            "Out of the months with recorded income, how often you spent no more than came in.",
            "months with income − spending ≥ 0 ÷ months with verified income × 100",
            "Monthly verified income and non-transfer debit totals.",
            f"{positive_savings} of {len(income_months)} income months were non-negative.",
            "Missing income or transactions can change this result.",
        ),
        metric(
            "cash_flow_volatility",
            "How much your monthly balance changes",
            cash_flow_volatility,
            "%",
            "Whether the amount left after spending stays similar each month or moves up and down a lot.",
            "population standard deviation of monthly net ÷ mean absolute monthly net × 100",
            "Monthly verified income minus non-transfer spending.",
            f"{len(monthly_nets)} monthly net values were compared.",
            "A higher value describes variation; it is not a risk score or diagnosis.",
        ),
        metric(
            "discretionary_ratio",
            "Spending you had more choice over",
            discretionary_ratio,
            "%",
            "The share of spending in flexible areas such as eating out, shopping, and entertainment.",
            "flexible-category spending ÷ total non-transfer spending × 100",
            "Confirmed transaction categories and debit amounts.",
            f"{len(transactions)} included transactions were reviewed.",
            "Classification choices determine which purchases count as flexible.",
        ),
        metric(
            "budget_adherence",
            "Months you stayed within your limit",
            budget_adherence,
            "%",
            "How often your total monthly spending stayed at or below the limit you chose.",
            "months within limit ÷ observed months × 100",
            "Your monthly spending limit and non-transfer debit totals.",
            (
                f"Monthly limit: {monthly_budget:.2f}."
                if monthly_budget
                else "No monthly spending limit is configured."
            ),
            "This metric remains unavailable until you set a limit.",
        ),
        metric(
            "subscription_load",
            "Income already promised to subscriptions",
            subscription_load,
            "%",
            "How much of an average income month is already committed to confirmed subscriptions.",
            "monthly-equivalent confirmed subscriptions ÷ average verified monthly income × 100",
            "Confirmed subscriptions and verified income months.",
            f"{db.query(Subscription).filter(Subscription.is_active.is_(True)).count()} active subscriptions were included.",
            "Unconfirmed suggestions and non-INR currency conversion gaps can affect this ratio.",
        ),
        metric(
            "buffer_coverage",
            "How long ready-to-use savings may cover spending",
            buffer_coverage,
            "months",
            "A rough estimate of how many average spending months your ready-to-use savings could cover.",
            "active liquid asset value ÷ average monthly non-transfer spending",
            "Net-worth cash/liquid assets and average included spending.",
            f"{len(complete_months)} observed months contributed to average spending.",
            "Liquidity and market values can change; this is not emergency-fund advice.",
        ),
        metric(
            "routine_stability",
            "How steady your week-to-week activity is",
            routine_stability,
            "score",
            "Whether you tend to spend on a similar number of days each week.",
            "100 − capped coefficient of variation of weekly active-day counts",
            "Transaction dates only; amounts and merchants are not used.",
            f"{len(active_days)} observed weeks were compared.",
            "A stable score is descriptive and does not imply healthy or unhealthy behavior.",
        ),
    ]
    metric_order = {
        "savings_consistency": 1,
        "budget_adherence": 2,
        "subscription_load": 3,
        "discretionary_ratio": 4,
        "buffer_coverage": 5,
        "routine_stability": 6,
        "cash_flow_volatility": 7,
    }
    metrics.sort(key=lambda item: metric_order[item["key"]])

    small_flexible = [
        transaction
        for transaction in debit_transactions
        if float(transaction.amount) <= 500
        and transaction.category in flexible_categories
    ]
    small_flexible_total = sum(float(item.amount) for item in small_flexible)
    small_share = (
        small_flexible_total / total_spend * 100 if total_spend > 0 else None
    )

    weekend_total = sum(
        float(item.amount) for item in debit_transactions if item.date.weekday() >= 5
    )
    weekday_total = total_spend - weekend_total
    day_count = (today - start).days + 1
    weekend_days = sum(
        1
        for offset in range(day_count)
        if (start + timedelta(days=offset)).weekday() >= 5
    )
    weekday_days = max(1, day_count - weekend_days)
    weekend_daily = weekend_total / weekend_days if weekend_days else 0
    weekday_daily = weekday_total / weekday_days
    weekend_shift = (
        (weekend_daily - weekday_daily) / weekday_daily * 100
        if weekday_daily > 0
        else None
    )

    late_month_total = sum(
        float(item.amount) for item in debit_transactions if item.date.day >= 21
    )
    late_month_share = (
        late_month_total / total_spend * 100 if total_spend > 0 else None
    )

    merchant_counts: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "total": 0.0}
    )
    for item in debit_transactions:
        merchant = item.merchant_normalized or item.merchant_raw or "Unknown"
        merchant_counts[merchant]["count"] += 1
        merchant_counts[merchant]["total"] += float(item.amount)
    repeat_merchant = (
        max(
            merchant_counts.items(),
            key=lambda item: (item[1]["count"], item[1]["total"]),
        )
        if merchant_counts
        else None
    )

    reflections = [
        {
            "key": "small_purchases",
            "title": "Are small purchases quietly adding up?",
            "observation": (
                f"{len(small_flexible)} flexible purchases of ₹500 or less added "
                f"up to ₹{small_flexible_total:,.0f}"
                + (
                    f", or {small_share:.1f}% of included spending."
                    if small_share is not None
                    else "."
                )
            ),
            "question": "Do these purchases still feel worth it when you see their combined total?",
            "action": "Pick one week to notice these purchases without trying to ban them.",
            "evidence": f"{len(small_flexible)} included purchases in {period}.",
            "confidence": confidence,
        },
        {
            "key": "weekend_shift",
            "title": "Does your spending change on weekends?",
            "observation": (
                "Average spending per weekend day was "
                f"₹{weekend_daily:,.0f}, compared with ₹{weekday_daily:,.0f} on weekdays."
                + (
                    f" That is {abs(weekend_shift):.0f}% "
                    f"{'higher' if weekend_shift >= 0 else 'lower'} on weekends."
                    if weekend_shift is not None
                    else ""
                )
            ),
            "question": "Is that difference intentional, or does free time make spending easier to overlook?",
            "action": "Before the next weekend, choose one thing you are happy to spend on.",
            "evidence": f"{weekend_days} weekend days and {weekday_days} weekdays in {period}.",
            "confidence": confidence,
        },
        {
            "key": "late_month_spending",
            "title": "What happens near the end of the month?",
            "observation": (
                f"₹{late_month_total:,.0f}"
                + (
                    f", or {late_month_share:.1f}% of included spending,"
                    if late_month_share is not None
                    else ""
                )
                + " happened on or after the 21st."
            ),
            "question": "Do later-month purchases feel planned, necessary, or like a response to earlier restraint?",
            "action": "Compare this with your pay date and bill dates before drawing a conclusion.",
            "evidence": f"Included debit dates in {period}.",
            "confidence": confidence,
        },
        {
            "key": "repeat_merchant",
            "title": "Which place appears most often?",
            "observation": (
                f"{repeat_merchant[0]} appeared {int(repeat_merchant[1]['count'])} times, "
                f"totalling ₹{repeat_merchant[1]['total']:,.0f}."
                if repeat_merchant
                else "There is not enough spending history to identify a repeated place yet."
            ),
            "question": "Does this repeat spending support something you value, or is it happening mostly from habit?",
            "action": "Look at the individual purchases before deciding whether anything should change.",
            "evidence": f"{len(debit_transactions)} included debit transactions in {period}.",
            "confidence": confidence,
        },
    ]

    return {
        "window_days": WINDOW_DAYS,
        "period": period,
        "metrics": metrics,
        "reflections": reflections,
        "monthly_budget": monthly_budget,
        "policy": (
            "These local, descriptive insights are never used for advertising, "
            "pricing, licensing, lending, insurance, or other consequential decisions."
        ),
    }


def export_behavior_insights_csv(db: Session) -> str:
    payload = compute_behavior_insights(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "metric",
            "value",
            "unit",
            "period",
            "confidence",
            "formula",
            "evidence",
            "correction_note",
        ]
    )
    for metric in payload["metrics"]:
        writer.writerow(
            [
                metric["label"],
                metric["value"],
                metric["unit"],
                metric["period"],
                metric["confidence"],
                metric["formula"],
                metric["evidence"],
                metric["correction_note"] or "",
            ]
        )
    return output.getvalue()
