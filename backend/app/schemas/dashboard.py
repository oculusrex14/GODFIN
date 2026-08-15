from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DashboardStats(BaseModel):
    month_spend: float
    month_income: float
    savings_rate: Optional[float] = None
    review_queue_count: int
    account_balance: Optional[float] = None


class DashboardMonthsResponse(BaseModel):
    months: list[str]
    has_data: bool


class CategoryBreakdownItem(BaseModel):
    category: str
    amount: float


class SpendingTrendItem(BaseModel):
    month: str
    label: str
    spend: float
    income: float
