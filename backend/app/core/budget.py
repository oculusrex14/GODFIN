from __future__ import annotations

import calendar
from dataclasses import dataclass
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
    calculation_version: str = "2.0"
    caveat: str = (
        "These are descriptive money patterns from categorized transactions, "
        "not a diagnosis or a judgment about you."
    )


def compute_financial_profile(
    db: Session,
    *,
    as_of: date | None = None,
) -> FinancialProfile:
    """Calculate plain-language ratios from the latest complete month."""
    today = as_of or date.today()
    current_month_start = date(today.year, today.month, 1)
    period_start = _month_start_offset(current_month_start, -1)
    comparison_start = _month_start_offset(current_month_start, -2)
    profile = FinancialProfile(
        period_start=period_start.isoformat(),
        period_end=(current_month_start - timedelta(days=1)).isoformat(),
        comparison_start=comparison_start.isoformat(),
        comparison_end=(period_start - timedelta(days=1)).isoformat(),
    )

    primary = (
        db.query(Transaction)
        .filter(
            Transaction.date >= period_start,
            Transaction.date < current_month_start,
            active_clause(Transaction),
        )
        .all()
    )
    comparison = (
        db.query(Transaction)
        .filter(
            Transaction.date >= comparison_start,
            Transaction.date < period_start,
            active_clause(Transaction),
        )
        .all()
    )
    profile.transaction_count = len(primary)
    profile.comparison_transaction_count = len(comparison)
    if not primary:
        return profile

    income = sum(float(item.amount) for item in primary if is_verified_income(item))
    spending = [item for item in primary if is_spending(item)]
    total_spend = sum(float(item.amount) for item in spending)
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

    if len(spending) >= 5:
        small_flexible_count = sum(
            1 for item in flexible_spending if float(item.amount) < 500
        )
        profile.impulse_index = round(
            small_flexible_count / len(spending) * 100,
            1,
        )
    if total_spend > 0:
        profile.subscription_dependency = round(
            subscription_spend / total_spend * 100,
            1,
        )

    comparison_spending = [item for item in comparison if is_spending(item)]
    comparison_flexible = [
        item for item in comparison_spending
        if item.category in flexible_categories
    ]
    if len(flexible_spending) >= 3 and len(comparison_flexible) >= 3:
        current_flexible = sum(float(item.amount) for item in flexible_spending)
        previous_flexible = sum(float(item.amount) for item in comparison_flexible)
        if previous_flexible > 0:
            profile.lifestyle_inflation = round(
                (current_flexible - previous_flexible)
                / previous_flexible
                * 100,
                1,
            )

    if income <= 0:
        profile.data_status = "income_unavailable"
        return profile

    profile.savings_rate = round((income - total_spend) / income * 100, 1)
    profile.fixed_expense_ratio = round(fixed_spend / income * 100, 1)
    frequency_divisors = {"monthly": 1, "quarterly": 3, "annual": 12}
    monthly_recurring = sum(
        float(pattern.avg_amount) / frequency_divisors[pattern.frequency]
        for pattern in db.query(RecurringPattern)
        .filter(RecurringPattern.is_active.is_(True))
        .all()
        if pattern.frequency in frequency_divisors
    )
    profile.recurring_burden = round(monthly_recurring / income * 100, 1)
    profile.data_status = "calculated"
    return profile
