from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.account_balances import aggregate_balance_at_date
from app.core.database import get_db
from app.core.transaction_semantics import (
    spending_clause,
    verified_income_clause,
)
from app.models.transaction import Transaction
from app.models.audit_session import AuditSession
from app.schemas.dashboard import (
    CategoryBreakdownItem,
    DashboardMonthsResponse,
    DashboardStats,
    SpendingTrendItem,
)
from app.schemas.financial import YearMonth

router = APIRouter()


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    return absolute // 12, absolute % 12 + 1


@router.get("/months", response_model=DashboardMonthsResponse)
def dashboard_months(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Return recent calendar months plus every locally recorded older month."""
    rows = (
        db.query(func.strftime("%Y-%m", Transaction.date).label("month"))
        .filter(Transaction.status != "deleted")
        .group_by(func.strftime("%Y-%m", Transaction.date))
        .order_by(func.strftime("%Y-%m", Transaction.date).desc())
        .all()
    )
    data_months = [row.month for row in rows if row.month]
    audit_rows = (
        db.query(AuditSession.period_year, AuditSession.period_month)
        .distinct()
        .all()
    )
    audit_months = sorted(
        {
            f"{int(row.period_year):04d}-{int(row.period_month):02d}"
            for row in audit_rows
            if row.period_year and row.period_month
        },
        reverse=True,
    )
    today = date.today()
    calendar_months = [
        f"{year:04d}-{month:02d}"
        for year, month in (
            _shift_month(today.year, today.month, -offset)
            for offset in range(24)
        )
    ]
    months = sorted(
        set(calendar_months) | set(data_months) | set(audit_months),
        reverse=True,
    )

    return {
        "months": months,
        "has_data": bool(data_months),
        "data_months": data_months,
        "audit_months": audit_months,
        "calendar_months": calendar_months,
    }


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    month: YearMonth,
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

    # Month spend uses the shared economic-semantic definition.
    spend_result = base_query.filter(
        spending_clause(Transaction),
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    month_spend = float(spend_result)

    # Only explicit/deterministic verified income is counted.
    income_result = base_query.filter(
        verified_income_clause(Transaction),
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

    balance = aggregate_balance_at_date(db, end_date - date.resolution)

    return DashboardStats(
        month_spend=round(month_spend, 2),
        month_income=round(month_income, 2),
        savings_rate=savings_rate,
        review_queue_count=review_count,
        account_balance=(
            round(float(balance.balance), 2)
            if balance.balance is not None
            else None
        ),
        account_balance_status=balance.status,
        account_balance_as_of=balance.as_of.isoformat(),
        account_balance_anchor_as_of=(
            balance.anchor_as_of.isoformat() if balance.anchor_as_of else None
        ),
        account_balance_coverage_complete=balance.coverage_complete,
        account_balance_missing_ranges=list(balance.missing_ranges),
        account_balance_account_count=balance.account_count,
        account_balance_verified_account_count=balance.verified_account_count,
    )


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
def category_breakdown(
    month: YearMonth,
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
            spending_clause(Transaction),
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


@router.get("/spending-trend", response_model=list[SpendingTrendItem])
def spending_trend(
    months: int = Query(6, ge=1, le=12),
    month: Optional[YearMonth] = None,
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
            spending_clause(Transaction),
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
            verified_income_clause(Transaction),
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
