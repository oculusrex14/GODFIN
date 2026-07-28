from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.product_depth import cash_flow_calendar

router = APIRouter()


@router.get("/calendar")
def get_cash_flow_calendar(
    month: str = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return cash_flow_calendar(db, month)
