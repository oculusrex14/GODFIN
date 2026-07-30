from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.taxonomy import TAXONOMY
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
SIMULATION_CALCULATION_VERSION = "2.0"
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
) -> SimulationResult:
    today = date.today()
    days_remaining = max(1, (deadline - today).days)
    months_remaining = max(1, math.ceil(days_remaining / 30.4375))

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
            Transaction.status != 'deleted',
            Transaction.is_transfer.is_(False),
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
        values["count"] += 1
        amount = float(transaction.amount)
        if transaction.is_income or transaction.type == "credit":
            values["income"] += amount
        elif transaction.type == "debit":
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
    impulse_index: float = 0.0
    lifestyle_inflation: float = 0.0
    fixed_expense_ratio: float = 0.0
    recurring_burden: float = 0.0
    subscription_dependency: float = 0.0
    savings_rate: float = 0.0


def compute_financial_profile(db: Session) -> FinancialProfile:
    profile = FinancialProfile()
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # Get current month data
    if today.month == 1:
        prev_month_start = date(today.year - 1, 12, 1)
    else:
        prev_month_start = date(today.year, today.month - 1, 1)

    # Total income this month
    income = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.is_income == True,
        )
        .scalar()
    )

    # Total spend this month (excluding transfers)
    total_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
        )
        .scalar()
    )

    # 1. Savings Rate
    if income > 0:
        profile.savings_rate = round(((income - total_spend) / income) * 100, 1)

    # 2. Fixed Expense Ratio
    fixed_categories = [cat for cat, elast in ELASTICITY.items() if elast == 'fixed']
    fixed_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.category.in_(fixed_categories),
        )
        .scalar()
    )
    if income > 0:
        profile.fixed_expense_ratio = round((fixed_spend / income) * 100, 1)

    # 3. Impulse Index (small discretionary transactions < 500 in flexible categories)
    flexible_categories = [cat for cat, elast in ELASTICITY.items() if elast == 'flexible']
    small_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.amount < 500,
            Transaction.category.in_(flexible_categories),
        )
        .scalar()
    )
    total_txn_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
        )
        .scalar()
    )
    if total_txn_count > 0:
        profile.impulse_index = min(round((small_count / total_txn_count) * 100, 1), 100.0)

    # 4. Lifestyle Inflation (current month flexible vs previous month)
    current_flexible = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.category.in_(flexible_categories),
        )
        .scalar()
    )
    prev_flexible = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= prev_month_start,
            Transaction.date < month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.category.in_(flexible_categories),
        )
        .scalar()
    )
    # Only compute if previous month had meaningful spending (>= 1000)
    # to avoid extreme percentages from tiny denominators
    if prev_flexible >= 1000:
        raw = ((current_flexible - prev_flexible) / prev_flexible) * 100
        profile.lifestyle_inflation = round(max(-100.0, min(raw, 500.0)), 1)
    elif prev_flexible > 0 and current_flexible > 0:
        # Not enough data for reliable %, flag as insufficient
        profile.lifestyle_inflation = 0.0

    # 5. Recurring Burden
    recurring_total = float(
        db.query(func.coalesce(func.sum(RecurringPattern.avg_amount), 0))
        .filter(RecurringPattern.is_active == True, RecurringPattern.frequency == 'monthly')
        .scalar()
    )
    if income > 0:
        profile.recurring_burden = min(round((recurring_total / income) * 100, 1), 100.0)

    # 6. Subscription Dependency (% of total spending, not just flexible)
    sub_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.category == 'ENTERTAINMENT',
            Transaction.subcategory == 'Subscriptions',
        )
        .scalar()
    )
    total_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
        )
        .scalar()
    )
    if total_spend > 0:
        profile.subscription_dependency = min(round((sub_spend / total_spend) * 100, 1), 100.0)

    return profile
