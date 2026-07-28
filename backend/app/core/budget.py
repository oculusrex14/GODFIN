from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
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


# --- Goal Calculator ---

def calculate_required_monthly_saving(
    target_amount: float,
    current_saved: float,
    months_remaining: int,
    annual_return_rate: float = 0.035,
) -> float:
    if months_remaining <= 0:
        return target_amount - current_saved

    remaining = target_amount - current_saved
    if remaining <= 0:
        return 0.0

    monthly_rate = annual_return_rate / 12

    if monthly_rate == 0:
        return remaining / months_remaining

    # Future Value of Annuity: FV = PMT * ((1+r)^n - 1) / r
    # Solve for PMT: PMT = FV * r / ((1+r)^n - 1)
    factor = (1 + monthly_rate) ** months_remaining - 1
    pmt = remaining * monthly_rate / factor

    return round(pmt, 2)


@dataclass
class SimulationResult:
    required_monthly: float
    flexible_spend: float
    max_saveable: float
    is_feasible: bool
    months_remaining: int
    extended_deadline_months: Optional[int] = None
    pressure_savings: dict = None

    def __post_init__(self):
        if self.pressure_savings is None:
            self.pressure_savings = {}


def simulate_goal(
    db: Session,
    target_amount: float,
    current_saved: float,
    deadline: date,
    annual_return_rate: float = 0.035,
    minimum_floor: float = 5000.0,
) -> SimulationResult:
    today = date.today()
    months_remaining = max(1, (deadline.year - today.year) * 12 + deadline.month - today.month)

    required = calculate_required_monthly_saving(
        target_amount, current_saved, months_remaining, annual_return_rate
    )

    # Calculate current flexible spending
    flexible_spend = _get_monthly_flexible_spend(db)
    max_saveable = max(0, flexible_spend - minimum_floor)

    is_feasible = required <= max_saveable

    # Calculate per-pressure-level savings
    pressure_savings = {}
    for level, ratio in PRESSURE_LEVELS.items():
        saveable = flexible_spend * ratio
        actual = min(saveable, max_saveable)
        pressure_savings[level] = round(actual, 2)

    result = SimulationResult(
        required_monthly=required,
        flexible_spend=round(flexible_spend, 2),
        max_saveable=round(max_saveable, 2),
        is_feasible=is_feasible,
        months_remaining=months_remaining,
        pressure_savings=pressure_savings,
    )

    # If not feasible, calculate extended deadline
    if not is_feasible and max_saveable > 0:
        extended = _calculate_extended_months(
            target_amount - current_saved, max_saveable, annual_return_rate
        )
        result.extended_deadline_months = extended

    return result


def _get_monthly_flexible_spend(db: Session) -> float:
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # Look at last 3 months of flexible spending
    three_months_ago = date(today.year, today.month - 3, 1) if today.month > 3 else date(today.year - 1, today.month + 9, 1)

    flexible_categories = [cat for cat, elast in ELASTICITY.items() if elast == 'flexible']

    result = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= three_months_ago,
            Transaction.date < month_start,
            Transaction.status != 'deleted',
            Transaction.type == 'debit',
            Transaction.category.in_(flexible_categories),
        )
        .scalar()
    )

    # Average over 3 months
    return float(result) / 3.0


def _calculate_extended_months(
    remaining: float, monthly_saving: float, annual_return_rate: float
) -> int:
    if monthly_saving <= 0:
        return 999

    monthly_rate = annual_return_rate / 12
    if monthly_rate == 0:
        return math.ceil(remaining / monthly_saving)

    # FV = PMT * ((1+r)^n - 1) / r >= remaining
    # (1+r)^n >= remaining * r / PMT + 1
    # n >= log(remaining * r / PMT + 1) / log(1+r)
    try:
        n = math.log(remaining * monthly_rate / monthly_saving + 1) / math.log(1 + monthly_rate)
        return math.ceil(n)
    except (ValueError, ZeroDivisionError):
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
