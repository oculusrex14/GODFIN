from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"
    __table_args__ = (
        Index(
            "uq_recurring_patterns_global_merchant",
            "merchant_normalized",
            unique=True,
            sqlite_where=text("account_id IS NULL"),
        ),
        Index(
            "uq_recurring_patterns_account_merchant",
            "merchant_normalized",
            "account_id",
            unique=True,
            sqlite_where=text("account_id IS NOT NULL"),
        ),
        CheckConstraint(
            "avg_amount > 0 AND avg_amount <= 1000000000000000",
            name="ck_recurring_patterns_avg_amount",
        ),
        CheckConstraint(
            "amount_stddev IS NULL OR amount_stddev >= 0",
            name="ck_recurring_patterns_amount_stddev",
        ),
        CheckConstraint(
            "frequency IN ('monthly', 'quarterly', 'annual')",
            name="ck_recurring_patterns_frequency",
        ),
        CheckConstraint(
            "avg_interval_days IS NULL OR avg_interval_days > 0",
            name="ck_recurring_patterns_avg_interval",
        ),
        CheckConstraint(
            "times_detected >= 2 AND evidence_count >= 0",
            name="ck_recurring_patterns_evidence",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_recurring_patterns_confidence",
        ),
        CheckConstraint(
            "interval_variability IS NULL OR interval_variability >= 0",
            name="ck_recurring_patterns_interval_variability",
        ),
        CheckConstraint(
            "amount_variability IS NULL OR amount_variability >= 0",
            name="ck_recurring_patterns_amount_variability",
        ),
        CheckConstraint(
            "detection_status IN ('active', 'candidate', 'retired')",
            name="ck_recurring_patterns_detection_status",
        ),
        CheckConstraint(
            "is_active IN (0, 1) AND "
            "((detection_status = 'active' AND is_active = 1) OR "
            "(detection_status IN ('candidate', 'retired') AND is_active = 0))",
            name="ck_recurring_patterns_active_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    avg_amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_stddev: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    avg_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_occurrence: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_expected: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    times_detected: Mapped[int] = mapped_column(Integer, default=2)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interval_variability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amount_variability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detection_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
