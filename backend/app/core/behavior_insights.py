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
            Transaction.status != "deleted",
            Transaction.is_transfer.is_(False),
        )
        .all()
    )
    by_month: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "spend": 0.0, "discretionary": 0.0}
    )
    weekly_counts: dict[tuple[int, int], set[date]] = defaultdict(set)
    total_spend = 0.0
    discretionary = 0.0
    flexible_categories = {
        category for category, elasticity in ELASTICITY.items() if elasticity == "flexible"
    }
    for transaction in transactions:
        month = by_month[_month_key(transaction.date)]
        if transaction.is_income or transaction.type == "credit":
            if transaction.is_income:
                month["income"] += float(transaction.amount)
        elif transaction.type == "debit":
            amount = float(transaction.amount)
            month["spend"] += amount
            total_spend += amount
            if transaction.category in flexible_categories:
                month["discretionary"] += amount
                discretionary += amount
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
            "Savings consistency",
            savings_consistency,
            "%",
            "Share of income months where verified income covered included spending.",
            "months with income − spending ≥ 0 ÷ months with verified income × 100",
            "Monthly verified income and non-transfer debit totals.",
            f"{positive_savings} of {len(income_months)} income months were non-negative.",
            "Missing income or transactions can change this result.",
        ),
        metric(
            "cash_flow_volatility",
            "Cash-flow volatility",
            cash_flow_volatility,
            "%",
            "How widely monthly net cash flow varies around its typical absolute level.",
            "population standard deviation of monthly net ÷ mean absolute monthly net × 100",
            "Monthly verified income minus non-transfer spending.",
            f"{len(monthly_nets)} monthly net values were compared.",
            "A higher value describes variation; it is not a risk score or diagnosis.",
        ),
        metric(
            "discretionary_ratio",
            "Discretionary ratio",
            discretionary_ratio,
            "%",
            "Share of included spending assigned to flexible categories.",
            "flexible-category spending ÷ total non-transfer spending × 100",
            "Confirmed transaction categories and debit amounts.",
            f"{len(transactions)} included transactions were reviewed.",
            "Classification choices determine which purchases count as flexible.",
        ),
        metric(
            "budget_adherence",
            "Budget adherence",
            budget_adherence,
            "%",
            "Share of observed months at or below the monthly spending limit you set.",
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
            "Subscription load",
            subscription_load,
            "%",
            "Monthly-equivalent confirmed subscription cost as a share of average income.",
            "monthly-equivalent confirmed subscriptions ÷ average verified monthly income × 100",
            "Confirmed subscriptions and verified income months.",
            f"{db.query(Subscription).filter(Subscription.is_active.is_(True)).count()} active subscriptions were included.",
            "Unconfirmed suggestions and non-INR currency conversion gaps can affect this ratio.",
        ),
        metric(
            "buffer_coverage",
            "Buffer coverage",
            buffer_coverage,
            "months",
            "Approximate months of average spending covered by active liquid assets.",
            "active liquid asset value ÷ average monthly non-transfer spending",
            "Net-worth cash/liquid assets and average included spending.",
            f"{len(complete_months)} observed months contributed to average spending.",
            "Liquidity and market values can change; this is not emergency-fund advice.",
        ),
        metric(
            "routine_stability",
            "Routine stability",
            routine_stability,
            "score",
            "Consistency of the number of transaction-active days from week to week.",
            "100 − capped coefficient of variation of weekly active-day counts",
            "Transaction dates only; amounts and merchants are not used.",
            f"{len(active_days)} observed weeks were compared.",
            "A stable score is descriptive and does not imply healthy or unhealthy behavior.",
        ),
    ]
    return {
        "window_days": WINDOW_DAYS,
        "period": period,
        "metrics": metrics,
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
