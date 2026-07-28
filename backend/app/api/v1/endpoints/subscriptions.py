"""Subscriptions / Autopayment management endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.product_depth import (
    decide_subscription_suggestion,
    sync_subscription_suggestions,
    upcoming_subscription_reminders,
)
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Exchange rate cache (in-memory, refreshes every 6 hours) ---
_rate_cache: dict = {"rates": {}, "timestamp": 0}
CACHE_TTL = 6 * 3600  # 6 hours


async def _fetch_exchange_rates() -> dict:
    """Fetch live exchange rates with INR as base. Returns {currency: rate_to_inr}."""
    now = time.time()
    if _rate_cache["rates"] and (now - _rate_cache["timestamp"]) < CACHE_TTL:
        return _rate_cache["rates"]

    # Try multiple free APIs in order of reliability
    apis = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d.get("rates", {})),
        ("https://api.exchangerate-api.com/v4/latest/USD", lambda d: d.get("rates", {})),
    ]

    for url, extractor in apis:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    usd_rates = extractor(data)
                    if "INR" in usd_rates:
                        usd_to_inr = float(usd_rates["INR"])
                        rates = {"INR": 1.0, "USD": usd_to_inr}
                        # Add EUR if available
                        if "EUR" in usd_rates and usd_rates["EUR"] > 0:
                            rates["EUR"] = usd_to_inr / float(usd_rates["EUR"])
                        if "GBP" in usd_rates and usd_rates["GBP"] > 0:
                            rates["GBP"] = usd_to_inr / float(usd_rates["GBP"])
                        _rate_cache["rates"] = rates
                        _rate_cache["timestamp"] = now
                        logger.info(f"Exchange rates updated: USD→INR = {usd_to_inr:.2f}")
                        return rates
        except Exception as e:
            logger.warning(f"Exchange rate fetch failed from {url}: {e}")
            continue

    # Fallback to hardcoded approximate rates if all APIs fail
    if not _rate_cache["rates"]:
        _rate_cache["rates"] = {"INR": 1.0, "USD": 85.0, "EUR": 92.0, "GBP": 107.0}
        _rate_cache["timestamp"] = now - CACHE_TTL + 300  # retry in 5 min
        logger.warning("Using fallback exchange rates")
    return _rate_cache["rates"]


def _to_inr(amount: float, currency: str, rates: dict) -> float:
    """Convert amount to INR using exchange rates."""
    if currency == "INR" or currency not in rates:
        return amount
    return amount * rates[currency]


class SubscriptionCreate(BaseModel):
    name: str
    amount: float
    currency: str = "INR"
    frequency: str = "monthly"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    next_payment_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    frequency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    next_payment_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    amount: float
    currency: str
    amount_inr: Optional[float]
    frequency: str
    category: Optional[str]
    subcategory: Optional[str]
    next_payment_date: Optional[str]
    is_active: bool
    notes: Optional[str]
    created_at: str

class SubscriptionStatsResponse(BaseModel):
    total_monthly_cost: float
    total_annual_projection: float
    active_count: int
    inactive_count: int
    by_category: dict
    exchange_rates: dict


class SubscriptionSuggestionDecision(BaseModel):
    decision: str
    snooze_days: int = 7


def _suggestion_response(suggestion: SubscriptionSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "recurring_pattern_id": suggestion.recurring_pattern_id,
        "merchant": suggestion.merchant,
        "avg_amount": suggestion.avg_amount,
        "frequency": suggestion.frequency,
        "category": suggestion.category,
        "next_expected": (
            suggestion.next_expected.isoformat()
            if suggestion.next_expected
            else None
        ),
        "status": suggestion.status,
        "snoozed_until": (
            suggestion.snoozed_until.isoformat()
            if suggestion.snoozed_until
            else None
        ),
        "confirmed_subscription_id": suggestion.confirmed_subscription_id,
    }


def _to_response(sub: Subscription, rates: dict) -> SubscriptionResponse:
    currency = getattr(sub, 'currency', None) or 'INR'
    amount_inr = _to_inr(sub.amount, currency, rates) if currency != 'INR' else None
    return SubscriptionResponse(
        id=sub.id,
        name=sub.name,
        amount=sub.amount,
        currency=currency,
        amount_inr=round(amount_inr, 2) if amount_inr is not None else None,
        frequency=sub.frequency,
        category=sub.category,
        subcategory=sub.subcategory,
        next_payment_date=sub.next_payment_date.isoformat() if sub.next_payment_date else None,
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
    rates = await _fetch_exchange_rates()
    query = db.query(Subscription)
    if is_active is not None:
        query = query.filter(Subscription.is_active == is_active)
    items = query.order_by(Subscription.created_at.desc()).all()
    return [_to_response(s, rates) for s in items]


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    valid_frequencies = ["monthly", "quarterly", "annual"]
    if body.frequency not in valid_frequencies:
        raise HTTPException(status_code=400, detail=f"Frequency must be one of: {', '.join(valid_frequencies)}")

    valid_currencies = ["INR", "USD", "EUR", "GBP"]
    currency = (body.currency or "INR").upper()
    if currency not in valid_currencies:
        raise HTTPException(status_code=400, detail=f"Currency must be one of: {', '.join(valid_currencies)}")

    next_date = None
    if body.next_payment_date:
        next_date = date.fromisoformat(body.next_payment_date)

    sub = Subscription(
        id=str(uuid.uuid4()),
        name=body.name,
        amount=body.amount,
        currency=currency,
        frequency=body.frequency,
        category=body.category,
        subcategory=body.subcategory,
        next_payment_date=next_date,
        notes=body.notes,
        is_active=body.is_active,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    rates = await _fetch_exchange_rates()
    return _to_response(sub, rates)


@router.get("/stats", response_model=SubscriptionStatsResponse)
async def get_subscription_stats(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    rates = await _fetch_exchange_rates()
    subs = db.query(Subscription).all()
    active = [s for s in subs if s.is_active]
    inactive = [s for s in subs if not s.is_active]

    # Convert all amounts to INR for stats
    total_monthly = sum(
        _monthly_equivalent(_to_inr(s.amount, getattr(s, 'currency', 'INR') or 'INR', rates), s.frequency)
        for s in active
    )

    by_category = {}
    for s in active:
        cat = s.category or "Uncategorized"
        amt_inr = _to_inr(s.amount, getattr(s, 'currency', 'INR') or 'INR', rates)
        by_category[cat] = by_category.get(cat, 0) + _monthly_equivalent(amt_inr, s.frequency)
    by_category = {k: round(v, 2) for k, v in by_category.items()}

    return SubscriptionStatsResponse(
        total_monthly_cost=round(total_monthly, 2),
        total_annual_projection=round(total_monthly * 12, 2),
        active_count=len(active),
        inactive_count=len(inactive),
        by_category=by_category,
        exchange_rates={k: round(v, 2) for k, v in rates.items()},
    )


@router.get("/exchange-rates")
async def get_exchange_rates(
    _user: bool = Depends(get_current_user),
):
    """Return current exchange rates (all → INR)."""
    rates = await _fetch_exchange_rates()
    return {"rates": {k: round(v, 2) for k, v in rates.items()}}


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
        query = query.filter(
            SubscriptionSuggestion.status.in_(["pending", "snoozed"])
        )
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
    if body.decision not in {"confirm", "ignore", "snooze"}:
        raise HTTPException(
            status_code=400, detail="Decision must be confirm, ignore, or snooze"
        )
    if not 1 <= body.snooze_days <= 90:
        raise HTTPException(status_code=400, detail="Snooze must be 1–90 days")
    suggestion = (
        db.query(SubscriptionSuggestion).filter_by(id=suggestion_id).first()
    )
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
    rates = await _fetch_exchange_rates()
    return _to_response(sub, rates)


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

    data = body.model_dump(exclude_unset=True)
    if "next_payment_date" in data and data["next_payment_date"]:
        data["next_payment_date"] = date.fromisoformat(data["next_payment_date"])

    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].upper()
        if data["currency"] not in ["INR", "USD", "EUR", "GBP"]:
            raise HTTPException(status_code=400, detail="Currency must be one of: INR, USD, EUR, GBP")

    if "frequency" in data:
        valid = ["monthly", "quarterly", "annual"]
        if data["frequency"] not in valid:
            raise HTTPException(status_code=400, detail=f"Frequency must be one of: {', '.join(valid)}")

    for field, value in data.items():
        setattr(sub, field, value)

    db.commit()
    db.refresh(sub)
    rates = await _fetch_exchange_rates()
    return _to_response(sub, rates)


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
