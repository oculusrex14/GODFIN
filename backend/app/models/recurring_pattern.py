from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
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
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits, exact_money_hybrid
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
        CheckConstraint(
            "json_valid(evidence_transaction_ids_json) "
            "AND json_type(evidence_transaction_ids_json) = 'array'",
            name="ck_recurring_patterns_evidence_json",
        ),
        CheckConstraint(
            "length(trim(detection_version)) BETWEEN 1 AND 20",
            name="ck_recurring_patterns_detection_version",
        ),
        CheckConstraint(
            f"avg_amount_minor BETWEEN 1 AND {MAX_MONEY_MINOR}",
            name="ck_recurring_patterns_avg_amount_minor",
        ),
        CheckConstraint(
            "amount_stddev_minor IS NULL OR "
            f"amount_stddev_minor BETWEEN 0 AND {MAX_MONEY_MINOR}",
            name="ck_recurring_patterns_stddev_minor",
        ),
        CheckConstraint(
            "avg_amount_minor = CAST(ROUND(avg_amount * 100, 0) AS INTEGER) "
            "AND ((amount_stddev IS NULL AND amount_stddev_minor IS NULL) OR "
            "(amount_stddev IS NOT NULL AND amount_stddev_minor = "
            "CAST(ROUND(amount_stddev * 100, 0) AS INTEGER)))",
            name="ck_recurring_patterns_money_shadows_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    _legacy_avg_amount: Mapped[float] = mapped_column(
        "avg_amount", Float, nullable=False
    )
    _exact_avg_amount: Mapped[Decimal] = mapped_column(
        "avg_amount_minor", MoneyMinorUnits(), nullable=False
    )
    avg_amount = exact_money_hybrid("_legacy_avg_amount", "_exact_avg_amount")
    _legacy_amount_stddev: Mapped[Optional[float]] = mapped_column(
        "amount_stddev", Float, nullable=True
    )
    _exact_amount_stddev: Mapped[Optional[Decimal]] = mapped_column(
        "amount_stddev_minor", MoneyMinorUnits(), nullable=True
    )
    amount_stddev = exact_money_hybrid(
        "_legacy_amount_stddev", "_exact_amount_stddev"
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    avg_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_occurrence: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_expected: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    times_detected: Mapped[int] = mapped_column(Integer, default=2)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_transaction_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    detection_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="2.0",
    )
    interval_variability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amount_variability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detection_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
