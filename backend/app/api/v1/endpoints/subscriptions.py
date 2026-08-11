"""Subscriptions / Autopayment management endpoints."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.fx import (
    FxRateSnapshot,
    FxRateUnavailable,
    SUPPORTED_CURRENCIES,
    apply_snapshot_to_subscription,
    clear_subscription_fx,
    get_inr_rates,
    saved_subscription_snapshot,
    unavailable_fx_metadata,
)
from app.core.product_depth import (
    decide_subscription_suggestion,
    sync_subscription_suggestions,
    upcoming_subscription_reminders,
)
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion
from app.schemas.financial import (
    PositiveMoney,
    SubscriptionDecision,
    SubscriptionFrequency,
    SupportedSubscriptionCurrency,
    reject_explicit_nulls,
)

router = APIRouter()

_FX_UNAVAILABLE_MESSAGE = "Verified exchange rates are temporarily unavailable."


async def _fetch_exchange_rates(
    currencies: set[str], *, force_refresh: bool = False
) -> FxRateSnapshot:
    """Fetch verified rates off the event loop; only currency codes are sent."""

    return await asyncio.to_thread(
        get_inr_rates,
        currencies,
        force_refresh=force_refresh,
    )


async def _resolve_exchange_rates(
    currencies: set[str],
    subscriptions: list[Subscription] | None = None,
) -> tuple[FxRateSnapshot | None, dict[str, Any]]:
    try:
        snapshot = await _fetch_exchange_rates(currencies)
    except FxRateUnavailable:
        stored = saved_subscription_snapshot(subscriptions or [])
        if stored is not None:
            return stored, stored.metadata(currencies)
        return None, unavailable_fx_metadata(_FX_UNAVAILABLE_MESSAGE, currencies)
    return snapshot, snapshot.metadata(currencies)


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: PositiveMoney
    currency: SupportedSubscriptionCurrency = "INR"
    frequency: SubscriptionFrequency = "monthly"
    category: Optional[str] = Field(default=None, max_length=50)
    subcategory: Optional[str] = Field(default=None, max_length=50)
    next_payment_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    amount: Optional[PositiveMoney] = None
    currency: Optional[SupportedSubscriptionCurrency] = None
    frequency: Optional[SubscriptionFrequency] = None
    category: Optional[str] = Field(default=None, max_length=50)
    subcategory: Optional[str] = Field(default=None, max_length=50)
    next_payment_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        return reject_explicit_nulls(
            self,
            {"name", "amount", "currency", "frequency", "is_active"},
        )


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    amount: float
    currency: str
    amount_inr: Optional[float]
    conversion_status: str
    conversion_as_of: Optional[str]
    conversion_provider: Optional[str]
    conversion_stale: Optional[bool]
    conversion_unavailable_reason: Optional[str]
    frequency: str
    category: Optional[str]
    subcategory: Optional[str]
    next_payment_date: Optional[str]
    is_active: bool
    notes: Optional[str]
    created_at: str


class SubscriptionStatsResponse(BaseModel):
    total_monthly_cost: Optional[float]
    total_annual_projection: Optional[float]
    active_count: int
    inactive_count: int
    by_category: Optional[dict]
    exchange_rates: dict[str, float]
    fx: dict[str, Any]


class SubscriptionSuggestionDecision(BaseModel):
    decision: SubscriptionDecision
    snooze_days: int = Field(default=7, ge=1, le=90)


def _suggestion_response(suggestion: SubscriptionSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "recurring_pattern_id": suggestion.recurring_pattern_id,
        "merchant": suggestion.merchant,
        "avg_amount": suggestion.avg_amount,
        "frequency": suggestion.frequency,
        "category": suggestion.category,
        "next_expected": (
            suggestion.next_expected.isoformat() if suggestion.next_expected else None
        ),
        "status": suggestion.status,
        "snoozed_until": (
            suggestion.snoozed_until.isoformat() if suggestion.snoozed_until else None
        ),
        "confirmed_subscription_id": suggestion.confirmed_subscription_id,
    }


def _to_response(
    sub: Subscription,
    snapshot: FxRateSnapshot | None,
    fx_metadata: dict[str, Any],
) -> SubscriptionResponse:
    currency = (getattr(sub, "currency", None) or "INR").upper()
    amount_inr = None
    if currency != "INR" and snapshot is not None:
        amount_inr = snapshot.convert_to_inr(float(sub.amount), currency)
    conversion_status = "not_required" if currency == "INR" else fx_metadata["status"]
    conversion_as_of = fx_metadata.get("rate_dates", {}).get(
        currency, fx_metadata.get("as_of")
    )
    return SubscriptionResponse(
        id=sub.id,
        name=sub.name,
        amount=sub.amount,
        currency=currency,
        amount_inr=round(amount_inr, 2) if amount_inr is not None else None,
        conversion_status=conversion_status,
        conversion_as_of=(conversion_as_of if currency != "INR" else None),
        conversion_provider=(
            fx_metadata.get("provider") if currency != "INR" else None
        ),
        conversion_stale=(fx_metadata.get("stale") if currency != "INR" else None),
        conversion_unavailable_reason=(
            fx_metadata.get("unavailable_reason") if currency != "INR" else None
        ),
        frequency=sub.frequency,
        category=sub.category,
        subcategory=sub.subcategory,
        next_payment_date=sub.next_payment_date.isoformat()
        if sub.next_payment_date
        else None,
        is_active=sub.is_active,
        notes=sub.notes,
        created_at=sub.created_at.isoformat() if sub.created_at else "",
    )


def _monthly_equivalent(amount: float, frequency: str) -> float:
    if frequency == "monthly":
        return amount
    elif frequency == "quarterly":
        return amount / 3
    elif frequency == "annual":
        return amount / 12
    return amount


@router.get("", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(Subscription)
    if is_active is not None:
        query = query.filter(Subscription.is_active == is_active)
    items = query.order_by(Subscription.created_at.desc()).all()
    currencies = {(item.currency or "INR").upper() for item in items} or {"INR"}
    snapshot, fx_metadata = await _resolve_exchange_rates(currencies, items)
    return [_to_response(item, snapshot, fx_metadata) for item in items]


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sub = Subscription(
        id=str(uuid.uuid4()),
        name=body.name,
        amount=body.amount,
        currency=body.currency,
        frequency=body.frequency,
        category=body.category,
        subcategory=body.subcategory,
        next_payment_date=body.next_payment_date,
        notes=body.notes,
        is_active=body.is_active,
    )
    currencies = {(sub.currency or "INR").upper()}
    snapshot, fx_metadata = await _resolve_exchange_rates(currencies, [sub])
    if snapshot is not None and snapshot.status in {
        "available",
        "stale",
        "not_required",
    }:
        apply_snapshot_to_subscription(sub, snapshot)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _to_response(sub, snapshot, fx_metadata)


@router.get("/stats", response_model=SubscriptionStatsResponse)
async def get_subscription_stats(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    subs = db.query(Subscription).all()
    active = [s for s in subs if s.is_active]
    inactive = [s for s in subs if not s.is_active]
    currencies = {(item.currency or "INR").upper() for item in active} or {"INR"}
    snapshot, fx_metadata = await _resolve_exchange_rates(currencies, active)

    total_monthly = None
    by_category = None
    if snapshot is not None:
        total_monthly = sum(
            _monthly_equivalent(
                snapshot.convert_to_inr(float(item.amount), item.currency),
                item.frequency,
            )
            for item in active
        )
        category_totals: dict[str, float] = {}
        for item in active:
            category = item.category or "Uncategorized"
            amount_inr = snapshot.convert_to_inr(float(item.amount), item.currency)
            category_totals[category] = category_totals.get(
                category, 0
            ) + _monthly_equivalent(amount_inr, item.frequency)
        by_category = {
            category: round(value, 2) for category, value in category_totals.items()
        }

    return SubscriptionStatsResponse(
        total_monthly_cost=(
            round(total_monthly, 2) if total_monthly is not None else None
        ),
        total_annual_projection=(
            round(total_monthly * 12, 2) if total_monthly is not None else None
        ),
        active_count=len(active),
        inactive_count=len(inactive),
        by_category=by_category,
        exchange_rates=(
            {
                currency: round(rate, 6)
                for currency, rate in snapshot.rates_to_inr.items()
            }
            if snapshot is not None
            else {}
        ),
        fx=fx_metadata,
    )


@router.get("/exchange-rates")
async def get_exchange_rates(
    _user: bool = Depends(get_current_user),
):
    """Return verified current exchange rates and their provenance."""
    snapshot, fx_metadata = await _resolve_exchange_rates(set(SUPPORTED_CURRENCIES))
    return {
        "rates": (
            {
                currency: round(rate, 6)
                for currency, rate in snapshot.rates_to_inr.items()
            }
            if snapshot is not None
            else {}
        ),
        "fx": fx_metadata,
    }


@router.post("/exchange-rates/refresh")
async def refresh_exchange_rates(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    subscriptions = (
        db.query(Subscription)
        .filter(
            Subscription.is_active.is_(True),
            Subscription.currency != "INR",
        )
        .all()
    )
    currencies = {(item.currency or "INR").upper() for item in subscriptions}
    if not currencies:
        snapshot = get_inr_rates({"INR"})
        return {"updated": 0, "fx": snapshot.metadata({"INR"})}
    try:
        snapshot = await _fetch_exchange_rates(currencies, force_refresh=True)
    except FxRateUnavailable:
        return {
            "updated": 0,
            "fx": unavailable_fx_metadata(_FX_UNAVAILABLE_MESSAGE, currencies),
        }
    for item in subscriptions:
        apply_snapshot_to_subscription(item, snapshot)
    db.commit()
    return {
        "updated": len(subscriptions),
        "fx": snapshot.metadata(currencies),
    }


@router.post("/suggestions/scan")
def scan_subscription_suggestions(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    created = sync_subscription_suggestions(db)
    db.commit()
    return {"created": created}


@router.get("/suggestions")
def list_subscription_suggestions(
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(SubscriptionSuggestion)
    if not include_resolved:
        query = query.filter(SubscriptionSuggestion.status.in_(["pending", "snoozed"]))
    suggestions = query.order_by(SubscriptionSuggestion.created_at.desc()).all()
    today = date.today()
    return [
        _suggestion_response(suggestion)
        for suggestion in suggestions
        if include_resolved
        or suggestion.status == "pending"
        or not suggestion.snoozed_until
        or suggestion.snoozed_until <= today
    ]


@router.post("/suggestions/{suggestion_id}/decision")
def update_subscription_suggestion(
    suggestion_id: str,
    body: SubscriptionSuggestionDecision,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    suggestion = db.query(SubscriptionSuggestion).filter_by(id=suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    subscription = decide_subscription_suggestion(
        db,
        suggestion,
        body.decision,
        snooze_days=body.snooze_days,
    )
    db.commit()
    return {
        "suggestion": _suggestion_response(suggestion),
        "subscription_id": subscription.id if subscription else None,
    }


@router.get("/reminders")
def get_subscription_reminders(
    days: int = 7,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if not 1 <= days <= 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return {
        "days": days,
        "reminders": upcoming_subscription_reminders(db, days=days),
    }


@router.get("/{sub_id}", response_model=SubscriptionResponse)
async def get_subscription(
    sub_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sub = db.query(Subscription).filter_by(id=sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    currencies = {(sub.currency or "INR").upper()}
    snapshot, fx_metadata = await _resolve_exchange_rates(currencies, [sub])
    return _to_response(sub, snapshot, fx_metadata)


@router.put("/{sub_id}", response_model=SubscriptionResponse)
async def update_subscription(
    sub_id: str,
    body: SubscriptionUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sub = db.query(Subscription).filter_by(id=sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    previous_currency = (sub.currency or "INR").upper()
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(sub, field, value)

    current_currency = (sub.currency or "INR").upper()
    if current_currency != previous_currency:
        clear_subscription_fx(sub)
    currencies = {current_currency}
    snapshot, fx_metadata = await _resolve_exchange_rates(currencies, [sub])
    if snapshot is not None and snapshot.status in {
        "available",
        "stale",
        "not_required",
    }:
        apply_snapshot_to_subscription(sub, snapshot)
    db.commit()
    db.refresh(sub)
    return _to_response(sub, snapshot, fx_metadata)


@router.delete("/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sub = db.query(Subscription).filter_by(id=sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(sub)
    db.commit()
