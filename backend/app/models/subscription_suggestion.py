from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class SubscriptionSuggestion(Base):
    __tablename__ = "subscription_suggestions"
    __table_args__ = (
        CheckConstraint(
            "avg_amount > 0 AND avg_amount <= 1000000000000000",
            name="ck_subscription_suggestions_avg_amount",
        ),
        CheckConstraint(
            "frequency IN ('monthly', 'quarterly', 'annual')",
            name="ck_subscription_suggestions_frequency",
        ),
        CheckConstraint(
            "status IN ('pending', 'snoozed', 'ignored', 'confirmed')",
            name="ck_subscription_suggestions_status",
        ),
        CheckConstraint(
            "status != 'snoozed' OR snoozed_until IS NOT NULL",
            name="ck_subscription_suggestions_snooze_date",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    recurring_pattern_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("recurring_patterns.id", ondelete="CASCADE"),
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
        String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )
