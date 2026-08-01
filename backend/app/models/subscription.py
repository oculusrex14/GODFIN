from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")  # INR, USD, EUR, etc.
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")  # monthly, quarterly, annual
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_payment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
