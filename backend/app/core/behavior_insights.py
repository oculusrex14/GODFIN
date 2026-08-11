from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY
from app.core.csv_security import spreadsheet_safe_row
from app.core.fx import (
    FxRateSnapshot,
    FxRateUnavailable,
    get_inr_rates,
    saved_subscription_snapshot,
    unavailable_fx_metadata,
)
from app.core.net_worth import get_base_currency, liquid_asset_total
from app.core.transaction_semantics import (
    active_clause,
    is_spending,
    is_verified_income,
)
from app.models.app_setting import AppSetting
from app.models.behavior_insight import BehaviorInsightPreference
from app.models.subscription import Subscription
from app.models.transaction import Transaction

WINDOW_MONTHS = 6
WINDOW_DAYS = 180  # Compatibility constant; payload window_days is calendar-derived.
BUDGET_KEY = "behavior_monthly_budget"
CALCULATION_VERSION = "behavior-insights-v2.0"
MIN_INCOME_MONTHS = 2
MIN_CASH_FLOW_MONTHS = 3
MIN_SPENDING_MONTHS = 2
MIN_DISCRETIONARY_TRANSACTIONS = 5
MIN_ROUTINE_WEEKS = 8


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _complete_period(today: date) -> tuple[date, date, date]:
    end_exclusive = today.replace(day=1)
    start = _shift_month(end_exclusive, -WINDOW_MONTHS)
    return start, end_exclusive - timedelta(days=1), end_exclusive


def _confidence(
    sample_size: int,
    *,
    minimum: int,
    medium: int,
    high: int,
) -> str:
    if sample_size < minimum:
        return "insufficient"
    if sample_size >= high:
        return "high"
    if sample_size >= medium:
        return "medium"
    return "low"


def _safe_cv(values: list[float]) -> float:
    denominator = statistics.fmean(abs(value) for value in values)
    if denominator <= 0:
        return 0.0
    return statistics.pstdev(values) / denominator * 100


def _monthly_subscription_cost(
    subscriptions: Iterable[Subscription], snapshot: FxRateSnapshot
) -> float:
    divisors = {"monthly": 1, "quarterly": 3, "annual": 12}
    return sum(
        snapshot.convert_to_inr(float(item.amount), item.currency)
        / divisors[item.frequency]
        for item in subscriptions
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
    reference_day = today or date.today()
    start, end, end_exclusive = _complete_period(reference_day)
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date < end_exclusive,
            active_clause(Transaction),
        )
        .all()
    )
    by_month: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "spend": 0.0, "discretionary": 0.0}
    )
    weekly_active_dates: dict[date, set[date]] = defaultdict(set)
    debit_transactions: list[Transaction] = []
    included_transactions: list[Transaction] = []
    total_spend = 0.0
    discretionary = 0.0
    flexible_categories = {
        category
        for category, elasticity in ELASTICITY.items()
        if elasticity == "flexible"
    }

    for transaction in transactions:
        if is_verified_income(transaction):
            month = by_month[_month_key(transaction.date)]
            month["income"] += float(transaction.amount)
        elif is_spending(transaction):
            month = by_month[_month_key(transaction.date)]
            amount = float(transaction.amount)
            debit_transactions.append(transaction)
            month["spend"] += amount
            total_spend += amount
            if transaction.category in flexible_categories:
                month["discretionary"] += amount
                discretionary += amount
        else:
            continue
        included_transactions.append(transaction)
        week_start = transaction.date - timedelta(days=transaction.date.weekday())
        week_end = week_start + timedelta(days=6)
        if week_start >= start and week_end <= end:
            weekly_active_dates[week_start].add(transaction.date)

    observed_months = sorted(by_month)
    income_months = [values for values in by_month.values() if values["income"] > 0]
    spending_months = [values for values in by_month.values() if values["spend"] > 0]
    cash_flow_months = [
        values
        for values in by_month.values()
        if values["income"] > 0 and values["spend"] > 0
    ]
    active_days = [float(len(days)) for days in weekly_active_dates.values()]
    preferences = _preference_map(db)
    period = f"{start.isoformat()} through {end.isoformat()}"

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
        *,
        sample_size: int,
        minimum_sample: int,
        medium_sample: int,
        high_sample: int,
        unavailable_reason: str | None = None,
        provenance: str = "Deterministic local calculation from included GODFIN data.",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        available = value is not None and unavailable_reason is None
        confidence = _confidence(
            sample_size,
            minimum=minimum_sample,
            medium=medium_sample,
            high=high_sample,
        )
        if not available:
            value = None
            confidence = "insufficient"
        preference = preferences.get(key)
        payload = {
            "key": key,
            "label": label,
            "value": round(value, 1) if value is not None else None,
            "unit": unit,
            "meaning": meaning,
            "formula": formula,
            "inputs": inputs,
            "period": period,
            "evidence": evidence,
            "available": available,
            "unavailable_reason": unavailable_reason,
            "sample_size": sample_size,
            "minimum_sample": minimum_sample,
            "confidence": confidence,
            "confidence_explanation": (
                f"Based on {sample_size} comparable observations; at least "
                f"{minimum_sample} are required and {high_sample} are needed for high confidence."
            ),
            "provenance": provenance,
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
            "correction_note": preference.correction_note if preference else None,
        }
        if extra:
            payload.update(extra)
        return payload

    positive_savings = sum(
        values["income"] - values["spend"] >= 0 for values in income_months
    )
    savings_reason = None
    if len(income_months) < MIN_INCOME_MONTHS:
        savings_reason = (
            f"Add verified income and spending for at least {MIN_INCOME_MONTHS} "
            "complete calendar months."
        )
    savings_consistency = (
        positive_savings / len(income_months) * 100 if income_months else None
    )

    monthly_nets = [values["income"] - values["spend"] for values in cash_flow_months]
    cash_flow_reason = None
    if len(cash_flow_months) < MIN_CASH_FLOW_MONTHS:
        cash_flow_reason = (
            f"At least {MIN_CASH_FLOW_MONTHS} complete months with both verified "
            "income and spending are needed."
        )
    cash_flow_volatility = (
        _safe_cv(monthly_nets)
        if len(cash_flow_months) >= MIN_CASH_FLOW_MONTHS
        else None
    )

    discretionary_reason = None
    if len(debit_transactions) < MIN_DISCRETIONARY_TRANSACTIONS:
        discretionary_reason = (
            f"At least {MIN_DISCRETIONARY_TRANSACTIONS} spending transactions "
            "are needed before showing a share."
        )
    elif len(spending_months) < MIN_SPENDING_MONTHS:
        discretionary_reason = (
            f"Spending across at least {MIN_SPENDING_MONTHS} complete months is needed."
        )
    discretionary_ratio = discretionary / total_spend * 100 if total_spend > 0 else None

    budget_setting = db.query(AppSetting).filter_by(key=BUDGET_KEY).first()
    try:
        monthly_budget = (
            float(budget_setting.value)
            if budget_setting and budget_setting.value
            else None
        )
    except (TypeError, ValueError):
        monthly_budget = None
    budget_reason = None
    if not monthly_budget:
        budget_reason = "Set a monthly spending limit to use this comparison."
    elif len(spending_months) < MIN_SPENDING_MONTHS:
        budget_reason = (
            f"At least {MIN_SPENDING_MONTHS} complete spending months are needed."
        )
    budget_adherence = (
        sum(values["spend"] <= monthly_budget for values in spending_months)
        / len(spending_months)
        * 100
        if monthly_budget and spending_months
        else None
    )

    average_income = (
        statistics.fmean(values["income"] for values in income_months)
        if income_months
        else 0
    )
    active_subscriptions = (
        db.query(Subscription).filter(Subscription.is_active.is_(True)).all()
    )
    subscription_currencies = {
        (item.currency or "INR").upper() for item in active_subscriptions
    } or {"INR"}
    subscription_cost = None
    subscription_reason = None
    subscription_fx: dict[str, Any] | None = None
    subscription_provenance = "Deterministic local calculation from confirmed subscriptions and verified income."
    if len(income_months) < MIN_INCOME_MONTHS:
        subscription_reason = f"At least {MIN_INCOME_MONTHS} complete months with verified income are needed."
    else:
        fx_snapshot = None
        try:
            fx_snapshot = get_inr_rates(
                subscription_currencies,
                today=reference_day,
            )
        except FxRateUnavailable:
            fx_snapshot = saved_subscription_snapshot(
                active_subscriptions,
                today=reference_day,
            )
            if fx_snapshot is None:
                subscription_reason = (
                    "A verified currency rate is unavailable, so GODFIN will not "
                    "estimate the subscription share."
                )
                subscription_fx = unavailable_fx_metadata(
                    "Verified currency rates are temporarily unavailable.",
                    subscription_currencies,
                )
        if fx_snapshot is not None:
            subscription_cost = _monthly_subscription_cost(
                active_subscriptions, fx_snapshot
            )
            subscription_fx = fx_snapshot.metadata(subscription_currencies)
            if subscription_currencies - {"INR"}:
                source_wording = (
                    "saved verified currency rates"
                    if fx_snapshot.status == "stored"
                    else "verified currency rates"
                )
                subscription_provenance += (
                    f" Currency conversion uses {source_wording} from "
                    f"{fx_snapshot.provider}; the oldest included rate is dated "
                    f"{fx_snapshot.as_of.isoformat()}."
                )
    subscription_load = (
        subscription_cost / average_income * 100
        if subscription_cost is not None and average_income > 0
        else None
    )

    average_spend = (
        statistics.fmean(values["spend"] for values in spending_months)
        if spending_months
        else 0
    )
    net_worth_base = get_base_currency(db)
    buffer_reason = None
    buffer_coverage = None
    if len(spending_months) < MIN_SPENDING_MONTHS:
        buffer_reason = (
            f"At least {MIN_SPENDING_MONTHS} complete spending months are needed."
        )
    elif net_worth_base != "INR":
        buffer_reason = (
            "Set Net Worth to INR before comparing it with INR spending; GODFIN "
            "will not assume a 1:1 exchange rate."
        )
    else:
        liquid_total = liquid_asset_total(db)
        if liquid_total is None:
            buffer_reason = (
                "One or more ready-to-use assets cannot be converted with a fresh, "
                "verified rate. Refresh those Net Worth valuations first."
            )
        elif liquid_total <= 0:
            buffer_reason = "Add cash or other ready-to-use savings in Net Worth before showing coverage."
        elif average_spend > 0:
            buffer_coverage = liquid_total / average_spend

    routine_reason = None
    if len(active_days) < MIN_ROUTINE_WEEKS:
        routine_reason = (
            f"At least {MIN_ROUTINE_WEEKS} full calendar weeks with recorded activity "
            "are needed before showing a routine score."
        )
    routine_stability = (
        max(0.0, 100.0 - min(100.0, _safe_cv(active_days)))
        if len(active_days) >= MIN_ROUTINE_WEEKS
        else None
    )

    metrics = [
        metric(
            "savings_consistency",
            "Months when income covered spending",
            savings_consistency,
            "%",
            "How often the money recorded as income was enough for the spending recorded that month.",
            "complete income months where income − spending ≥ 0 ÷ complete months with verified income × 100",
            "Verified income and non-transfer spending grouped into complete calendar months.",
            f"{positive_savings} of {len(income_months)} complete income months were non-negative.",
            "Missing income or purchases can change this result, so check that each month is fully imported.",
            sample_size=len(income_months),
            minimum_sample=MIN_INCOME_MONTHS,
            medium_sample=3,
            high_sample=6,
            unavailable_reason=savings_reason,
        ),
        metric(
            "cash_flow_volatility",
            "How much the amount left over changes",
            cash_flow_volatility,
            "%",
            "Whether the money left after spending is fairly similar each month or changes a lot.",
            "standard deviation of monthly money left ÷ average absolute monthly money left × 100",
            "Complete months containing both verified income and non-transfer spending.",
            f"{len(cash_flow_months)} complete income-and-spending months were compared.",
            "A higher number only means more month-to-month change; it is not a danger score or diagnosis.",
            sample_size=len(cash_flow_months),
            minimum_sample=MIN_CASH_FLOW_MONTHS,
            medium_sample=4,
            high_sample=6,
            unavailable_reason=cash_flow_reason,
        ),
        metric(
            "discretionary_ratio",
            "Spending where you had more choice",
            discretionary_ratio,
            "%",
            "The share of recorded spending in flexible areas such as eating out, shopping, and entertainment.",
            "flexible-category spending ÷ all non-transfer spending × 100",
            "Confirmed transaction categories and spending amounts in complete months.",
            f"{len(debit_transactions)} spending transactions across {len(spending_months)} complete months were reviewed.",
            "Your category choices decide which purchases count as flexible.",
            sample_size=len(debit_transactions),
            minimum_sample=MIN_DISCRETIONARY_TRANSACTIONS,
            medium_sample=15,
            high_sample=30,
            unavailable_reason=discretionary_reason,
        ),
        metric(
            "budget_adherence",
            "Months you stayed within your chosen limit",
            budget_adherence,
            "%",
            "How often your recorded monthly spending stayed at or below the limit you set.",
            "complete spending months within limit ÷ complete spending months × 100",
            "Your chosen monthly limit and non-transfer spending totals.",
            (
                f"Monthly limit: ₹{monthly_budget:,.2f}; {len(spending_months)} complete spending months compared."
                if monthly_budget
                else "No monthly spending limit is configured."
            ),
            "This is only as complete as the spending imported for each month.",
            sample_size=len(spending_months),
            minimum_sample=MIN_SPENDING_MONTHS,
            medium_sample=3,
            high_sample=6,
            unavailable_reason=budget_reason,
        ),
        metric(
            "subscription_load",
            "Income already set aside for subscriptions",
            subscription_load,
            "%",
            "How much of an average recorded income month would be used by confirmed subscriptions.",
            "monthly INR value of confirmed subscriptions ÷ average verified monthly INR income × 100",
            "Confirmed subscriptions, their billing frequency, verified income months, and verified currency rates when needed.",
            f"{len(active_subscriptions)} active subscriptions and {len(income_months)} complete income months were included.",
            "Unconfirmed suggestions are excluded. Currency totals disappear if a verified rate is unavailable.",
            sample_size=len(income_months),
            minimum_sample=MIN_INCOME_MONTHS,
            medium_sample=3,
            high_sample=6,
            unavailable_reason=subscription_reason,
            provenance=subscription_provenance,
            extra={"currency_conversion": subscription_fx},
        ),
        metric(
            "buffer_coverage",
            "How many months ready-to-use savings may cover",
            buffer_coverage,
            "months",
            "A rough comparison between saved cash or easy-to-sell assets and your average recorded monthly spending.",
            "active liquid assets valued in INR ÷ average spending across complete months",
            "Net Worth cash/liquid assets and non-transfer spending in complete months.",
            f"{len(spending_months)} complete spending months were used; Net Worth base currency is {net_worth_base}.",
            "Asset values and how quickly they can be used may change; this is not emergency-fund advice.",
            sample_size=len(spending_months),
            minimum_sample=MIN_SPENDING_MONTHS,
            medium_sample=3,
            high_sample=6,
            unavailable_reason=buffer_reason,
        ),
        metric(
            "routine_stability",
            "How similar your active money days are each week",
            routine_stability,
            "score",
            "Whether you tend to have transactions on a similar number of days from one full week to the next.",
            "100 − the capped variation in active-day counts across observed full Monday-to-Sunday weeks",
            "Transaction dates only; amounts and merchants are not used.",
            f"{len(active_days)} full calendar weeks with recorded activity were compared.",
            "A steady routine is not automatically good or bad, and missing imports can change the score.",
            sample_size=len(active_days),
            minimum_sample=MIN_ROUTINE_WEEKS,
            medium_sample=12,
            high_sample=20,
            unavailable_reason=routine_reason,
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

    reflection_ready = (
        len(debit_transactions) >= MIN_DISCRETIONARY_TRANSACTIONS
        and len(spending_months) >= MIN_SPENDING_MONTHS
    )
    reflection_confidence = _confidence(
        len(debit_transactions), minimum=5, medium=15, high=30
    )
    reflection_reason = (
        None
        if reflection_ready
        else "Add at least 5 spending transactions across 2 complete months before GODFIN suggests a pattern to reflect on."
    )

    small_flexible = [
        transaction
        for transaction in debit_transactions
        if float(transaction.amount) <= 500
        and transaction.category in flexible_categories
    ]
    small_flexible_total = sum(float(item.amount) for item in small_flexible)
    small_share = small_flexible_total / total_spend * 100 if total_spend > 0 else None
    weekend_total = sum(
        float(item.amount) for item in debit_transactions if item.date.weekday() >= 5
    )
    weekday_total = total_spend - weekend_total
    day_count = (end - start).days + 1
    weekend_days = sum(
        1
        for offset in range(day_count)
        if (start + timedelta(days=offset)).weekday() >= 5
    )
    weekday_days = day_count - weekend_days
    weekend_daily = weekend_total / weekend_days if weekend_days else 0
    weekday_daily = weekday_total / weekday_days if weekday_days else 0
    weekend_shift = (
        (weekend_daily - weekday_daily) / weekday_daily * 100
        if weekday_daily > 0
        else None
    )
    late_month_total = sum(
        float(item.amount) for item in debit_transactions if item.date.day >= 21
    )
    late_month_share = late_month_total / total_spend * 100 if total_spend > 0 else None
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

    def reflection(
        key: str,
        title: str,
        observation: str,
        question: str,
        action: str,
        evidence: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "observation": observation if reflection_ready else reflection_reason,
            "question": question,
            "action": action,
            "evidence": evidence,
            "available": reflection_ready,
            "unavailable_reason": reflection_reason,
            "confidence": reflection_confidence if reflection_ready else "insufficient",
        }

    reflections = [
        reflection(
            "small_purchases",
            "Are small purchases quietly adding up?",
            (
                f"{len(small_flexible)} flexible purchases of ₹500 or less added up to "
                f"₹{small_flexible_total:,.0f}"
                + (
                    f", or {small_share:.1f}% of included spending."
                    if small_share is not None
                    else "."
                )
            ),
            "Do these purchases still feel worth it when you see their combined total?",
            "Pick one week to notice these purchases without trying to ban them.",
            f"{len(small_flexible)} included purchases in {period}.",
        ),
        reflection(
            "weekend_shift",
            "Does your spending change on weekends?",
            (
                f"Average recorded spending per weekend day was ₹{weekend_daily:,.0f}, "
                f"compared with ₹{weekday_daily:,.0f} on weekdays."
                + (
                    f" That is {abs(weekend_shift):.0f}% "
                    f"{'higher' if weekend_shift >= 0 else 'lower'} on weekends."
                    if weekend_shift is not None
                    else ""
                )
            ),
            "Is that difference intentional, or does free time make spending easier to overlook?",
            "Before the next weekend, choose one thing you are happy to spend on.",
            f"{weekend_days} weekend days and {weekday_days} weekdays in {period}.",
        ),
        reflection(
            "late_month_spending",
            "What happens near the end of the month?",
            (
                f"₹{late_month_total:,.0f}"
                + (
                    f", or {late_month_share:.1f}% of included spending,"
                    if late_month_share is not None
                    else ""
                )
                + " happened on or after the 21st."
            ),
            "Do later-month purchases feel planned, necessary, or like a response to earlier restraint?",
            "Compare this with your pay date and bill dates before drawing a conclusion.",
            f"Included spending dates in {period}.",
        ),
        reflection(
            "repeat_merchant",
            "Which place appears most often?",
            (
                f"{repeat_merchant[0]} appeared {int(repeat_merchant[1]['count'])} times, "
                f"totalling ₹{repeat_merchant[1]['total']:,.0f}."
                if repeat_merchant
                else "There is not enough spending history to identify a repeated place yet."
            ),
            "Does this repeat spending support something you value, or is it happening mostly from habit?",
            "Look at the individual purchases before deciding whether anything should change.",
            f"{len(debit_transactions)} included spending transactions in {period}.",
        ),
    ]

    calendar_months = [
        _month_key(_shift_month(start, offset)) for offset in range(WINDOW_MONTHS)
    ]
    return {
        "calculation_version": CALCULATION_VERSION,
        "window_days": day_count,
        "window_months": WINDOW_MONTHS,
        "period": period,
        "coverage": {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "calendar_months": WINDOW_MONTHS,
            "calendar_month_keys": calendar_months,
            "observed_months": len(observed_months),
            "observed_month_keys": observed_months,
            "income_months": len(income_months),
            "spending_months": len(spending_months),
            "cash_flow_months": len(cash_flow_months),
            "observed_full_weeks": len(active_days),
            "included_transactions": len(included_transactions),
            "current_month_excluded": True,
            "note": (
                "Only the previous six finished calendar months are considered. "
                "GODFIN cannot know whether every statement or email for those months was imported."
            ),
        },
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
            "available",
            "value",
            "unit",
            "period",
            "confidence",
            "sample_size",
            "minimum_sample",
            "unavailable_reason",
            "formula",
            "evidence",
            "provenance",
            "correction_note",
        ]
    )
    for item in payload["metrics"]:
        writer.writerow(
            spreadsheet_safe_row(
                [
                    item["label"],
                    item["available"],
                    item["value"],
                    item["unit"],
                    item["period"],
                    item["confidence"],
                    item["sample_size"],
                    item["minimum_sample"],
                    item["unavailable_reason"] or "",
                    item["formula"],
                    item["evidence"],
                    item["provenance"],
                    item["correction_note"] or "",
                ]
            )
        )
    return output.getvalue()
