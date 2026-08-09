from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits, exact_money_hybrid
from app.core.time import utcnow_naive


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "amount > 0 AND amount <= 1000000000000000",
            name="ck_subscriptions_amount_range",
        ),
        CheckConstraint(
            "currency IN ('INR', 'USD', 'EUR', 'GBP')",
            name="ck_subscriptions_currency",
        ),
        CheckConstraint(
            "frequency IN ('monthly', 'quarterly', 'annual')",
            name="ck_subscriptions_frequency",
        ),
        CheckConstraint(
            "fx_rate_to_inr IS NULL OR "
            "(fx_rate_to_inr > 0 AND fx_rate_to_inr <= 1000000000)",
            name="ck_subscriptions_fx_rate_range",
        ),
        CheckConstraint(
            "((fx_rate_to_inr IS NULL AND fx_rate_source IS NULL AND "
            "fx_rate_source_url IS NULL AND fx_rate_as_of IS NULL AND "
            "fx_rate_fetched_at IS NULL) OR "
            "(fx_rate_to_inr IS NOT NULL AND fx_rate_source IS NOT NULL AND "
            "fx_rate_source_url IS NOT NULL AND fx_rate_as_of IS NOT NULL AND "
            "fx_rate_fetched_at IS NOT NULL))",
            name="ck_subscriptions_fx_provenance_complete",
        ),
        CheckConstraint(
            f"amount_minor BETWEEN 1 AND {MAX_MONEY_MINOR}",
            name="ck_subscriptions_amount_minor_range",
        ),
        CheckConstraint(
            "amount_minor = CAST(ROUND(amount * 100, 0) AS INTEGER)",
            name="ck_subscriptions_amount_shadow_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    _legacy_amount: Mapped[float] = mapped_column("amount", Float, nullable=False)
    _exact_amount: Mapped[Decimal] = mapped_column(
        "amount_minor", MoneyMinorUnits(), nullable=False
    )
    amount = exact_money_hybrid("_legacy_amount", "_exact_amount")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_payment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fx_rate_to_inr: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 12), nullable=True
    )
    fx_rate_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    fx_rate_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    fx_rate_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fx_rate_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
