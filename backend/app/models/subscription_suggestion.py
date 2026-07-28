from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class SubscriptionSuggestion(Base):
    __tablename__ = "subscription_suggestions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    recurring_pattern_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("recurring_patterns.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    avg_amount: Mapped[float] = mapped_column(Float, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_expected: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    snoozed_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confirmed_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("subscriptions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )
