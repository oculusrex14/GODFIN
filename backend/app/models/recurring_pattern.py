from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id"), nullable=True
    )
    avg_amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_stddev: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    avg_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_occurrence: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_expected: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    times_detected: Mapped[int] = mapped_column(Integer, default=2)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
