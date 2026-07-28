from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.transaction import Transaction
from app.schemas.dashboard import DashboardStats

router = APIRouter()


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    return absolute // 12, absolute % 12 + 1


@router.get("/months")
def dashboard_months(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Return up to 24 transaction-backed months, with a 24-month fallback."""
    rows = (
        db.query(func.strftime("%Y-%m", Transaction.date).label("month"))
        .filter(Transaction.status != "deleted")
        .group_by(func.strftime("%Y-%m", Transaction.date))
        .order_by(func.strftime("%Y-%m", Transaction.date).desc())
        .limit(24)
        .all()
    )
    months = [row.month for row in rows if row.month]
    has_data = bool(months)

    if not months:
        today = date.today()
        months = [
            f"{year:04d}-{month:02d}"
            for year, month in (
                _shift_month(today.year, today.month, -offset)
                for offset in range(24)
            )
        ]

    return {"months": months, "has_data": has_data}


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    period: str = Query("full", pattern=r"^(full|week_1|week_2|week_3|week_4|first_half|second_half)$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    year, mon = month.split("-")
    year, mon = int(year), int(mon)

    # Determine date range for the month
    month_start = date(year, mon, 1)
    if mon == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, mon + 1, 1)

    # Apply period filter
    start_date, end_date = _get_period_dates(month_start, month_end, period)

    base_query = db.query(Transaction).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.status != "deleted",
    )

    # Month spend: sum of debits excluding transfers
    spend_result = base_query.filter(
        Transaction.type == "debit",
        Transaction.is_transfer == False,
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    month_spend = float(spend_result)

    # Month income: sum where is_income is True
    income_result = base_query.filter(
        Transaction.is_income == True,
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    month_income = float(income_result)

    # Savings rate
    savings_rate = None
    if month_income > 0:
        savings_rate = round(((month_income - month_spend) / month_income) * 100, 1)

    # Review queue: transactions with no category
    review_count = base_query.filter(
        Transaction.category == None,
    ).count()

    # Account balance: all-time credits minus debits up to end of selected month
    balance_query = db.query(Transaction).filter(
        Transaction.date < end_date,
        Transaction.status != "deleted",
    )

    credits_total = balance_query.filter(
        (Transaction.is_income == True) | (Transaction.type == 'credit'),
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()

    debits_total = balance_query.filter(
        Transaction.type == 'debit',
        Transaction.is_transfer == False,
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()

    account_balance = round(float(credits_total) - float(debits_total), 2)

    return DashboardStats(
        month_spend=round(month_spend, 2),
        month_income=round(month_income, 2),
        savings_rate=savings_rate,
        review_queue_count=review_count,
        account_balance=account_balance,
    )


@router.get("/category-breakdown")
def category_breakdown(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    period: str = Query("full", pattern=r"^(full|week_1|week_2|week_3|week_4|first_half|second_half)$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    year, mon = month.split("-")
    year, mon = int(year), int(mon)
    month_start = date(year, mon, 1)
    month_end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)

    # Apply period filter
    start_date, end_date = _get_period_dates(month_start, month_end, period)

    rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.status != "deleted",
            Transaction.type == "debit",
            Transaction.is_transfer == False,
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    return [
        {"category": row.category or "Uncategorized", "amount": round(float(row.total), 2)}
        for row in rows
    ]


def _get_period_dates(month_start: date, month_end: date, period: str) -> tuple[date, date]:
    """Calculate start and end dates based on period selection."""
    if period == "full":
        return month_start, month_end
    elif period == "week_1":
        return month_start, min(date(month_start.year, month_start.month, 8), month_end)
    elif period == "week_2":
        start = date(month_start.year, month_start.month, 8)
        return start, min(date(month_start.year, month_start.month, 15), month_end)
    elif period == "week_3":
        start = date(month_start.year, month_start.month, 15)
        return start, min(date(month_start.year, month_start.month, 22), month_end)
    elif period == "week_4":
        start = date(month_start.year, month_start.month, 22)
        return start, month_end
    elif period == "first_half":
        return month_start, min(date(month_start.year, month_start.month, 16), month_end)
    elif period == "second_half":
        start = date(month_start.year, month_start.month, 16)
        return start, month_end
    return month_start, month_end


@router.get("/spending-trend")
def spending_trend(
    months: int = Query(6, ge=1, le=12),
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    # If a specific month is provided, anchor the window to that month
    if month:
        anchor_year, anchor_mon = map(int, month.split("-"))
    else:
        today = date.today()
        anchor_year, anchor_mon = today.year, today.month

    # Calculate date range for all months at once
    month_ranges = []
    for i in range(months - 1, -1, -1):
        mon = anchor_mon - i
        yr = anchor_year
        while mon <= 0:
            mon += 12
            yr -= 1

        month_start = date(yr, mon, 1)
        if mon == 12:
            month_end = date(yr + 1, 1, 1)
        else:
            month_end = date(yr, mon + 1, 1)

        month_ranges.append((yr, mon, month_start, month_end))

    # Get min and max dates for the query
    min_date = min(r[2] for r in month_ranges)
    max_date = max(r[3] for r in month_ranges)

    # Single query to get all spend data grouped by month
    spend_data = (
        db.query(
            func.strftime('%Y-%m', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total')
        )
        .filter(
            Transaction.date >= min_date,
            Transaction.date < max_date,
            Transaction.status != "deleted",
            Transaction.type == "debit",
            Transaction.is_transfer == False,
        )
        .group_by(func.strftime('%Y-%m', Transaction.date))
        .all()
    )

    # Single query to get all income data grouped by month
    income_data = (
        db.query(
            func.strftime('%Y-%m', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total')
        )
        .filter(
            Transaction.date >= min_date,
            Transaction.date < max_date,
            Transaction.status != "deleted",
            Transaction.is_income == True,
        )
        .group_by(func.strftime('%Y-%m', Transaction.date))
        .all()
    )

    # Convert to lookup dictionaries
    spend_by_month = {row.month: float(row.total or 0) for row in spend_data}
    income_by_month = {row.month: float(row.total or 0) for row in income_data}

    # Build result in chronological order
    result = []
    for yr, mon, month_start, _ in month_ranges:
        month_key = f"{yr}-{mon:02d}"
        result.append({
            "month": month_key,
            "label": month_start.strftime("%b"),
            "spend": round(spend_by_month.get(month_key, 0), 2),
            "income": round(income_by_month.get(month_key, 0), 2),
        })

    return result
