"""Income sources management endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.transaction_semantics import verified_income_clause
from app.models.income_source import IncomeSource
from app.models.transaction import Transaction
from app.schemas.financial import (
    IncomeFrequency,
    PositiveMoney,
    YearMonth,
    reject_explicit_nulls,
)

router = APIRouter()


class IncomeSourceCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: IncomeFrequency = "monthly"
    next_expected_date: Optional[date] = None
    enforce_current_month: bool = False  # If true, apply to current month income
    is_active: bool = True


class IncomeSourceUpdate(BaseModel):
    source_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: Optional[IncomeFrequency] = None
    next_expected_date: Optional[date] = None
    enforce_current_month: Optional[bool] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        return reject_explicit_nulls(
            self,
            {"source_name", "frequency", "enforce_current_month", "is_active"},
        )


class IncomeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    expected_amount: Optional[float]
    frequency: str
    next_expected_date: Optional[str]
    enforce_current_month: bool
    last_detected_date: Optional[str]
    last_detected_amount: Optional[float]
    is_active: bool
    created_at: str

class IncomeSourceListResponse(BaseModel):
    items: List[IncomeSourceResponse]
    total: int


class IncomeStatsResponse(BaseModel):
    total_expected_monthly: float
    total_detected_this_month: float
    sources_count: int
    active_sources_count: int
    by_frequency: dict


def _calculate_default_next_date(frequency: str) -> Optional[date]:
    """Calculate default next expected date based on frequency."""
    today = date.today()
    if frequency == "monthly":
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        else:
            return date(today.year, today.month + 1, 1)
    elif frequency == "quarterly":
        current_quarter = (today.month - 1) // 3
        next_quarter_month = (current_quarter + 1) * 3 + 1
        if next_quarter_month > 12:
            return date(today.year + 1, 1, 1)
        else:
            return date(today.year, next_quarter_month, 1)
    elif frequency == "annual":
        return date(today.year + 1, 1, 1)
    return None


def _source_to_response(source: IncomeSource) -> IncomeSourceResponse:
    """Convert IncomeSource model to response."""
    return IncomeSourceResponse(
        id=source.id,
        source_name=source.source_name,
        expected_amount=source.expected_amount,
        frequency=source.frequency,
        next_expected_date=source.next_expected_date.isoformat() if source.next_expected_date else None,
        enforce_current_month=source.enforce_current_month or False,
        last_detected_date=source.last_detected_date.isoformat() if source.last_detected_date else None,
        last_detected_amount=source.last_detected_amount,
        is_active=source.is_active,
        created_at=source.created_at.isoformat() if isinstance(source.created_at, datetime) else str(source.created_at),
    )


@router.get("", response_model=IncomeSourceListResponse)
def list_income_sources(
    is_active: Optional[bool] = None,
    frequency: Optional[IncomeFrequency] = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """List all income sources."""
    query = db.query(IncomeSource)

    if is_active is not None:
        query = query.filter(IncomeSource.is_active == is_active)
    if frequency:
        query = query.filter(IncomeSource.frequency == frequency)

    items = query.order_by(IncomeSource.created_at.desc()).all()

    return IncomeSourceListResponse(
        items=[_source_to_response(item) for item in items],
        total=len(items),
    )


@router.post("", response_model=IncomeSourceResponse, status_code=201)
def create_income_source(
    body: IncomeSourceCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Create a new income source."""
    next_expected_date = body.next_expected_date
    if next_expected_date is None and body.frequency in ["monthly", "quarterly", "annual"] and body.expected_amount:
        next_expected_date = _calculate_default_next_date(body.frequency)

    source = IncomeSource(
        id=str(uuid.uuid4()),
        source_name=body.source_name,
        expected_amount=body.expected_amount,
        frequency=body.frequency,
        next_expected_date=next_expected_date,
        enforce_current_month=body.enforce_current_month,
        is_active=body.is_active,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return _source_to_response(source)


@router.get("/stats", response_model=IncomeStatsResponse)
def get_income_stats(
    month: Optional[YearMonth] = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get income statistics for a given month."""
    from sqlalchemy import func

    if not month:
        month = date.today().strftime("%Y-%m")

    sources = db.query(IncomeSource).all()

    year, month_num = map(int, month.split("-"))
    start_date = date(year, month_num, 1)
    if month_num == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month_num + 1, 1)

    total_expected_monthly = 0
    by_frequency = {"monthly": 0, "quarterly": 0, "annual": 0, "one_time": 0}

    for source in sources:
        if not source.is_active:
            continue

        expected = source.expected_amount or 0
        count_for_month = False

        if source.frequency == "monthly":
            count_for_month = True
            by_frequency["monthly"] += expected
        elif source.frequency == "quarterly":
            by_frequency["quarterly"] += expected
            if source.enforce_current_month:
                count_for_month = True
            elif source.next_expected_date:
                if start_date <= source.next_expected_date < end_date:
                    count_for_month = True
        elif source.frequency == "annual":
            by_frequency["annual"] += expected
            if source.enforce_current_month:
                count_for_month = True
            elif source.next_expected_date:
                if start_date <= source.next_expected_date < end_date:
                    count_for_month = True
        else:
            by_frequency["one_time"] += expected
            if source.next_expected_date:
                if start_date <= source.next_expected_date < end_date:
                    count_for_month = True

        if count_for_month:
            total_expected_monthly += expected

    total_detected = (
        db.query(func.sum(Transaction.amount))
        .filter(
            verified_income_clause(Transaction),
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.status != "deleted",
        )
        .scalar() or 0
    )

    # For enforced sources, only add the expected amount if no actual
    # income matching that source was detected (prevents double-counting)
    enforced_shortfall = 0
    for source in sources:
        if not source.is_active or not source.enforce_current_month:
            continue
        expected = source.expected_amount or 0
        if expected <= 0:
            continue
        # Check if a matching income transaction exists this month
        # (within 20% of expected amount to account for variation)
        threshold = expected * 0.2
        matching = (
            db.query(Transaction)
            .filter(
                verified_income_clause(Transaction),
                Transaction.date >= start_date,
                Transaction.date < end_date,
                Transaction.status != "deleted",
                Transaction.amount >= expected - threshold,
                Transaction.amount <= expected + threshold,
            )
            .first()
        )
        if not matching:
            enforced_shortfall += expected

    total_this_month = float(total_detected) + enforced_shortfall

    return IncomeStatsResponse(
        total_expected_monthly=total_expected_monthly,
        total_detected_this_month=total_this_month,
        sources_count=len(sources),
        active_sources_count=sum(1 for s in sources if s.is_active),
        by_frequency=by_frequency,
    )


@router.get("/{source_id}", response_model=IncomeSourceResponse)
def get_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get a specific income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    return _source_to_response(source)


@router.put("/{source_id}", response_model=IncomeSourceResponse)
def update_income_source(
    source_id: str,
    body: IncomeSourceUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Update an income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    update_data = body.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(source, field, value)

    db.commit()
    db.refresh(source)

    return _source_to_response(source)


@router.delete("/{source_id}", status_code=204)
def delete_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Delete an income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    db.delete(source)
    db.commit()
