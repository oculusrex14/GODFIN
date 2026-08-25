from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DashboardStats(BaseModel):
    month_spend: float
    month_income: float
    savings_rate: Optional[float] = None
    review_queue_count: int
    account_balance: Optional[float] = None
    account_balance_status: str
    account_balance_as_of: str
    account_balance_anchor_as_of: Optional[str] = None
    account_balance_coverage_complete: bool
    account_balance_missing_ranges: list[str]
    account_balance_account_count: int
    account_balance_verified_account_count: int


class DashboardMonthsResponse(BaseModel):
    months: list[str]
    has_data: bool
    data_months: list[str]
    audit_months: list[str]
    calendar_months: list[str]


class CategoryBreakdownItem(BaseModel):
    category: str
    amount: float


class SpendingTrendItem(BaseModel):
    month: str
    label: str
    spend: float
    income: float
