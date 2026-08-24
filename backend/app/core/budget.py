from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.core.transaction_semantics import (
    active_clause,
    is_spending,
    is_verified_income,
)
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction


# --- Elasticity Mapping ---

ELASTICITY = {
    'HOUSING': 'fixed',
    'FINANCIAL OBLIGATIONS': 'fixed',
    'TRANSPORTATION': 'semi_flexible',
    'UTILITIES & BILLS': 'semi_flexible',
    'HEALTH & WELLNESS': 'semi_flexible',
    'EDUCATION': 'semi_flexible',
    'FOOD & DINING': 'flexible',
    'SHOPPING': 'flexible',
    'ENTERTAINMENT': 'flexible',
    'MISCELLANEOUS': 'flexible',
    'TRANSFERS': 'none',
    'INCOME': 'none',
}

PRESSURE_LEVELS = {
    'minimal': 0.40,
    'moderate': 0.60,
    'aggressive': 0.80,
}
SIMULATION_CALCULATION_VERSION = "2.1"
SIMULATION_HISTORY_MONTHS = 6
MINIMUM_CAPACITY_MONTHS = 2


# --- Goal Calculator ---

def calculate_required_monthly_saving(
    target_amount: float,
    current_saved: float,
    months_remaining: int,
    annual_return_rate: float = 0.0,
) -> float:
    if months_remaining <= 0:
        return round(max(0.0, target_amount - current_saved), 2)

    target = Decimal(str(target_amount))
    saved = Decimal(str(current_saved))
    monthly_rate = Decimal(str(annual_return_rate)) / Decimal("12")
    compounded_saved = saved * (
        (Decimal("1") + monthly_rate) ** months_remaining
    )
    future_gap = target - compounded_saved
    if future_gap <= 0:
        return 0.0

    if monthly_rate == 0:
        payment = future_gap / Decimal(months_remaining)
    else:
        annuity_factor = (
            (Decimal("1") + monthly_rate) ** months_remaining - Decimal("1")
        ) / monthly_rate
        payment = future_gap / annuity_factor

    return float(payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def scheduled_month_end_contributions(
    as_of: date,
    deadline: date,
) -> list[date]:
    """Return the actual month-end contribution dates through a deadline."""
    if deadline < as_of:
        return []

    year = as_of.year
    month = as_of.month
    scheduled: list[date] = []
    while True:
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        if month_end > deadline:
            break
        if month_end >= as_of:
            scheduled.append(month_end)
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return scheduled


@dataclass
class SimulationResult:
    required_monthly: float
    flexible_spend: float
    max_saveable: float
    is_feasible: Optional[bool]
    months_remaining: int
    extended_deadline_months: Optional[int] = None
    pressure_savings: dict = None
    baseline_surplus: float = 0.0
    reducible_flexible_spend: float = 0.0
    coverage_months: int = 0
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    capacity_status: str = "insufficient_data"
    calculation_version: str = SIMULATION_CALCULATION_VERSION
    assumptions: dict = None
    caveat: str = (
        "This is a planning estimate from incomplete transaction history, "
        "not financial advice or an authoritative forecast."
    )

    def __post_init__(self):
        if self.pressure_savings is None:
            self.pressure_savings = {}
        if self.assumptions is None:
            self.assumptions = {}


@dataclass
class HistoricalCapacity:
    flexible_spend: float
    baseline_surplus: float
    reducible_flexible_spend: float
    max_saveable: float
    coverage_months: int
    coverage_start: Optional[str]
    coverage_end: Optional[str]


def simulate_goal(
    db: Session,
    target_amount: float,
    current_saved: float,
    deadline: date,
    annual_return_rate: float = 0.0,
    minimum_floor: float = 5000.0,
    as_of: date | None = None,
) -> SimulationResult:
    today = as_of or date.today()
    contribution_dates = scheduled_month_end_contributions(today, deadline)
    months_remaining = len(contribution_dates)

    required = calculate_required_monthly_saving(
        target_amount, current_saved, months_remaining, annual_return_rate
    )

    capacity = _get_historical_capacity(db, minimum_floor=minimum_floor)
    has_capacity_data = capacity.coverage_months >= MINIMUM_CAPACITY_MONTHS
    is_feasible = (
        required <= capacity.max_saveable if has_capacity_data else None
    )
    pressure_savings = {}
    if has_capacity_data:
        existing_surplus = max(0.0, capacity.baseline_surplus)
        for level, ratio in PRESSURE_LEVELS.items():
            pressure_savings[level] = round(
                min(
                    capacity.max_saveable,
                    existing_surplus + capacity.reducible_flexible_spend * ratio,
                ),
                2,
            )

    result = SimulationResult(
        required_monthly=required,
        flexible_spend=capacity.flexible_spend,
        max_saveable=capacity.max_saveable,
        is_feasible=is_feasible,
        months_remaining=months_remaining,
        pressure_savings=pressure_savings,
        baseline_surplus=capacity.baseline_surplus,
        reducible_flexible_spend=capacity.reducible_flexible_spend,
        coverage_months=capacity.coverage_months,
        coverage_start=capacity.coverage_start,
        coverage_end=capacity.coverage_end,
        capacity_status="calculated" if has_capacity_data else "insufficient_data",
        assumptions={
            "contribution_timing": "end_of_month",
            "schedule_basis": "actual_calendar_month_ends_on_or_before_deadline",
            "first_contribution_date": (
                contribution_dates[0].isoformat() if contribution_dates else None
            ),
            "last_contribution_date": (
                contribution_dates[-1].isoformat() if contribution_dates else None
            ),
            "scheduled_contribution_count": months_remaining,
            "amount_due_before_first_month_end": months_remaining == 0,
            "annual_return_rate": round(float(annual_return_rate), 6),
            "monthly_return_rate": round(float(annual_return_rate) / 12, 8),
            "minimum_flexible_floor": round(float(minimum_floor), 2),
            "history_window_months": SIMULATION_HISTORY_MONTHS,
            "minimum_complete_months": MINIMUM_CAPACITY_MONTHS,
            "existing_savings_compounded_separately": True,
        },
    )

    if is_feasible is False and capacity.max_saveable > 0:
        extended = _calculate_extended_months(
            target_amount,
            current_saved,
            capacity.max_saveable,
            annual_return_rate,
        )
        result.extended_deadline_months = extended

    return result


def _month_start_offset(start: date, offset: int) -> date:
    month_index = start.year * 12 + start.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _get_historical_capacity(
    db: Session,
    *,
    minimum_floor: float,
) -> HistoricalCapacity:
    today = date.today()
    month_start = date(today.year, today.month, 1)
    history_start = _month_start_offset(month_start, -SIMULATION_HISTORY_MONTHS)
    flexible_categories = [cat for cat, elast in ELASTICITY.items() if elast == 'flexible']
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= history_start,
            Transaction.date < month_start,
            active_clause(Transaction),
        )
        .all()
    )
    by_month: dict[str, dict[str, float | int]] = {}
    for transaction in transactions:
        key = transaction.date.strftime("%Y-%m")
        values = by_month.setdefault(
            key,
            {"income": 0.0, "expenses": 0.0, "flexible": 0.0, "count": 0},
        )
        amount = float(transaction.amount)
        if is_verified_income(transaction):
            values["count"] += 1
            values["income"] += amount
        elif is_spending(transaction):
            values["count"] += 1
            values["expenses"] += amount
            if transaction.category in flexible_categories:
                values["flexible"] += amount

    covered = sorted(
        (month, values)
        for month, values in by_month.items()
        if values["count"] > 0
    )
    if not covered:
        return HistoricalCapacity(0.0, 0.0, 0.0, 0.0, 0, None, None)

    coverage_months = len(covered)
    flexible_spend = (
        sum(float(values["flexible"]) for _, values in covered)
        / coverage_months
    )
    baseline_surplus = (
        sum(
            float(values["income"]) - float(values["expenses"])
            for _, values in covered
        )
        / coverage_months
    )
    reducible = max(0.0, flexible_spend - minimum_floor)
    max_saveable = max(0.0, baseline_surplus + reducible)
    return HistoricalCapacity(
        flexible_spend=round(flexible_spend, 2),
        baseline_surplus=round(baseline_surplus, 2),
        reducible_flexible_spend=round(reducible, 2),
        max_saveable=round(max_saveable, 2),
        coverage_months=coverage_months,
        coverage_start=covered[0][0],
        coverage_end=covered[-1][0],
    )


def _calculate_extended_months(
    target_amount: float,
    current_saved: float,
    monthly_saving: float,
    annual_return_rate: float,
) -> int:
    if monthly_saving <= 0:
        return 999

    balance = max(0.0, float(current_saved))
    monthly_rate = max(0.0, float(annual_return_rate)) / 12
    for month in range(1, 601):
        balance = balance * (1 + monthly_rate) + monthly_saving
        if balance + 0.005 >= target_amount:
            return month
    return 999


# --- Financial Profile Metrics ---

@dataclass
class FinancialProfile:
    impulse_index: Optional[float] = None
    lifestyle_inflation: Optional[float] = None
    fixed_expense_ratio: Optional[float] = None
    recurring_burden: Optional[float] = None
    subscription_dependency: Optional[float] = None
    savings_rate: Optional[float] = None
    data_status: str = "insufficient_history"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    comparison_start: Optional[str] = None
    comparison_end: Optional[str] = None
    transaction_count: int = 0
    comparison_transaction_count: int = 0
    verified_income_count: int = 0
    verified_income_total: float = 0
    spending_transaction_count: int = 0
    spending_total: float = 0
    complete_month_count: int = 0
    recurring_sample_count: int = 0
    metrics: dict[str, dict[str, object]] = field(default_factory=dict)
    calculation_version: str = "3.0"
    caveat: str = (
        "These are descriptive money patterns from categorized transactions, "
        "not a diagnosis or a judgment about you."
    )


def compute_financial_profile(
    db: Session,
    *,
    as_of: date | None = None,
) -> FinancialProfile:
    """Calculate explainable ratios from the latest complete months with data."""
    today = as_of or date.today()
    current_month_start = date(today.year, today.month, 1)
    fallback_period = _month_start_offset(current_month_start, -1)
    profile = FinancialProfile(
        period_start=fallback_period.isoformat(),
        period_end=(current_month_start - timedelta(days=1)).isoformat(),
    )

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date < current_month_start,
            active_clause(Transaction),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    by_month: dict[date, list[Transaction]] = {}
    for transaction in transactions:
        month_start = date(transaction.date.year, transaction.date.month, 1)
        by_month.setdefault(month_start, []).append(transaction)
    complete_months = sorted(by_month, reverse=True)
    profile.complete_month_count = len(complete_months)
    if not complete_months:
        unavailable = "No completed month contains recorded transactions yet."
        profile.metrics = {
            name: {
                "available": False,
                "unavailable_reason": unavailable,
                "period_start": None,
                "period_end": None,
                "sample_count": 0,
            }
            for name in (
                "savings_rate",
                "impulse_index",
                "fixed_expense_ratio",
                "recurring_burden",
                "subscription_dependency",
                "lifestyle_inflation",
            )
        }
        return profile

    period_start = complete_months[0]
    period_end = _month_start_offset(period_start, 1) - timedelta(days=1)
    primary = by_month[period_start]
    comparison_start = complete_months[1] if len(complete_months) > 1 else None
    comparison = by_month.get(comparison_start, []) if comparison_start else []
    profile.period_start = period_start.isoformat()
    profile.period_end = period_end.isoformat()
    profile.comparison_start = comparison_start.isoformat() if comparison_start else None
    profile.comparison_end = (
        (_month_start_offset(comparison_start, 1) - timedelta(days=1)).isoformat()
        if comparison_start
        else None
    )
    profile.transaction_count = len(primary)
    profile.comparison_transaction_count = len(comparison)

    income_rows = [item for item in primary if is_verified_income(item)]
    income = sum(float(item.amount) for item in income_rows)
    spending = [item for item in primary if is_spending(item)]
    total_spend = sum(float(item.amount) for item in spending)
    profile.verified_income_count = len(income_rows)
    profile.verified_income_total = round(income, 2)
    profile.spending_transaction_count = len(spending)
    profile.spending_total = round(total_spend, 2)
    fixed_categories = {
        category for category, elasticity in ELASTICITY.items()
        if elasticity == "fixed"
    }
    flexible_categories = {
        category for category, elasticity in ELASTICITY.items()
        if elasticity == "flexible"
    }
    fixed_spend = sum(
        float(item.amount) for item in spending
        if item.category in fixed_categories
    )
    flexible_spending = [
        item for item in spending if item.category in flexible_categories
    ]
    subscription_spend = sum(
        float(item.amount) for item in spending
        if (item.subcategory or "").strip().lower() == "subscriptions"
    )

    def metric(
        name: str,
        *,
        available: bool,
        unavailable_reason: str | None,
        sample_count: int,
        metric_start: date | None = period_start,
        metric_end: date | None = period_end,
    ) -> None:
        profile.metrics[name] = {
            "available": available,
            "unavailable_reason": unavailable_reason,
            "period_start": metric_start.isoformat() if metric_start else None,
            "period_end": metric_end.isoformat() if metric_end else None,
            "sample_count": sample_count,
        }

    if len(spending) >= 5:
        small_flexible_count = sum(
            1 for item in flexible_spending if float(item.amount) < 500
        )
        profile.impulse_index = round(
            small_flexible_count / len(spending) * 100,
            1,
        )
        metric(
            "impulse_index",
            available=True,
            unavailable_reason=None,
            sample_count=len(spending),
        )
    else:
        metric(
            "impulse_index",
            available=False,
            unavailable_reason=(
                f"At least 5 purchases are needed; this month has {len(spending)}."
            ),
            sample_count=len(spending),
        )
    if total_spend > 0:
        profile.subscription_dependency = round(
            subscription_spend / total_spend * 100,
            1,
        )
        metric(
            "subscription_dependency",
            available=True,
            unavailable_reason=None,
            sample_count=len(spending),
        )
    else:
        metric(
            "subscription_dependency",
            available=False,
            unavailable_reason="No included purchases were recorded in this month.",
            sample_count=0,
        )

    lifestyle_pair: tuple[date, list[Transaction], date, list[Transaction]] | None = None
    for position, candidate_start in enumerate(complete_months):
        candidate = [
            item
            for item in by_month[candidate_start]
            if is_spending(item) and item.category in flexible_categories
        ]
        if len(candidate) < 3:
            continue
        for older_start in complete_months[position + 1 :]:
            older = [
                item
                for item in by_month[older_start]
                if is_spending(item) and item.category in flexible_categories
            ]
            if len(older) >= 3:
                lifestyle_pair = (candidate_start, candidate, older_start, older)
                break
        if lifestyle_pair:
            break
    if lifestyle_pair:
        current_start, current_flexible_rows, older_start, older_flexible_rows = lifestyle_pair
        current_flexible = sum(float(item.amount) for item in current_flexible_rows)
        previous_flexible = sum(float(item.amount) for item in older_flexible_rows)
        profile.lifestyle_inflation = round(
            (current_flexible - previous_flexible) / previous_flexible * 100,
            1,
        )
        metric(
            "lifestyle_inflation",
            available=True,
            unavailable_reason=None,
            sample_count=len(current_flexible_rows) + len(older_flexible_rows),
            metric_start=older_start,
            metric_end=_month_start_offset(current_start, 1) - timedelta(days=1),
        )
    else:
        flexible_samples = sum(
            1
            for rows in by_month.values()
            for item in rows
            if is_spending(item) and item.category in flexible_categories
        )
        metric(
            "lifestyle_inflation",
            available=False,
            unavailable_reason=(
                "Two completed months with at least 3 optional purchases each are needed."
            ),
            sample_count=flexible_samples,
        )

    if income > 0:
        profile.savings_rate = round((income - total_spend) / income * 100, 1)
        profile.fixed_expense_ratio = round(fixed_spend / income * 100, 1)
        metric(
            "savings_rate",
            available=True,
            unavailable_reason=None,
            sample_count=len(income_rows) + len(spending),
        )
        metric(
            "fixed_expense_ratio",
            available=True,
            unavailable_reason=None,
            sample_count=len(income_rows) + len(spending),
        )
    else:
        income_reason = (
            "No verified income was recorded in the selected completed month. "
            "Record actual income or confirm a matching credit."
        )
        metric(
            "savings_rate",
            available=False,
            unavailable_reason=income_reason,
            sample_count=len(spending),
        )
        metric(
            "fixed_expense_ratio",
            available=False,
            unavailable_reason=income_reason,
            sample_count=len(spending),
        )

    frequency_divisors = {"monthly": 1, "quarterly": 3, "annual": 12}
    recurring_patterns = [
        pattern
        for pattern in db.query(RecurringPattern)
        .filter(RecurringPattern.is_active.is_(True))
        .all()
        if pattern.frequency in frequency_divisors
    ]
    profile.recurring_sample_count = len(recurring_patterns)
    if income > 0 and recurring_patterns:
        monthly_recurring = sum(
            float(pattern.avg_amount) / frequency_divisors[pattern.frequency]
            for pattern in recurring_patterns
        )
        profile.recurring_burden = round(monthly_recurring / income * 100, 1)
        metric(
            "recurring_burden",
            available=True,
            unavailable_reason=None,
            sample_count=len(recurring_patterns),
        )
    else:
        reason = (
            "No verified income was recorded in the selected completed month."
            if income <= 0
            else "No confirmed repeat-payment pattern is available yet."
        )
        metric(
            "recurring_burden",
            available=False,
            unavailable_reason=reason,
            sample_count=len(recurring_patterns),
        )

    available_count = sum(
        bool(item["available"]) for item in profile.metrics.values()
    )
    if available_count == len(profile.metrics):
        profile.data_status = "calculated"
    elif available_count > 0:
        profile.data_status = "partial"
    elif income <= 0:
        profile.data_status = "income_unavailable"
    return profile
