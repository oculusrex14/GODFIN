from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.product_depth import cash_flow_calendar
from app.schemas.financial import YearMonth

router = APIRouter()


class CashFlowDayResponse(BaseModel):
    date: str
    spend: float
    income: float
    net: float
    transaction_count: int


class CashFlowCalendarResponse(BaseModel):
    month: str
    days: list[CashFlowDayResponse]
    total_spend: float
    total_income: float
    net: float
    max_daily_flow: float


@router.get("/calendar", response_model=CashFlowCalendarResponse)
def get_cash_flow_calendar(
    month: YearMonth | None = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return cash_flow_calendar(db, month)
