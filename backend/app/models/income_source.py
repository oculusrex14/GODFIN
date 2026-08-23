from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits, exact_money_hybrid
from app.core.time import utcnow_naive


class IncomeSource(Base):
    __tablename__ = "income_sources"
    __table_args__ = (
        CheckConstraint(
            "expected_amount IS NULL OR "
            "(expected_amount > 0 AND expected_amount <= 1000000000000000)",
            name="ck_income_sources_expected_amount_range",
        ),
        CheckConstraint(
            "frequency IN ('monthly', 'quarterly', 'annual', 'one_time', "
            "'biweekly', 'irregular')",
            name="ck_income_sources_frequency",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_income_sources_effective_dates",
        ),
        CheckConstraint(
            "amount_tolerance >= 0 AND amount_tolerance <= 1",
            name="ck_income_sources_amount_tolerance",
        ),
        CheckConstraint(
            f"expected_amount_minor IS NULL OR expected_amount_minor "
            f"BETWEEN 1 AND {MAX_MONEY_MINOR}",
            name="ck_income_sources_expected_amount_minor_range",
        ),
        CheckConstraint(
            f"last_detected_amount_minor IS NULL OR last_detected_amount_minor "
            f"BETWEEN 1 AND {MAX_MONEY_MINOR}",
            name="ck_income_sources_detected_amount_minor_range",
        ),
        CheckConstraint(
            "((expected_amount IS NULL AND expected_amount_minor IS NULL) OR "
            "(expected_amount IS NOT NULL AND expected_amount_minor = "
            "CAST(ROUND(expected_amount * 100, 0) AS INTEGER))) AND "
            "((last_detected_amount IS NULL AND "
            "last_detected_amount_minor IS NULL) OR "
            "(last_detected_amount IS NOT NULL AND "
            "last_detected_amount_minor = "
            "CAST(ROUND(last_detected_amount * 100, 0) AS INTEGER)))",
            name="ck_income_sources_money_shadows_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    _legacy_expected_amount: Mapped[Optional[float]] = mapped_column(
        "expected_amount", Float, nullable=True
    )
    _exact_expected_amount: Mapped[Optional[Decimal]] = mapped_column(
        "expected_amount_minor", MoneyMinorUnits(), nullable=True
    )
    expected_amount = exact_money_hybrid(
        "_legacy_expected_amount", "_exact_expected_amount"
    )
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    effective_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=date.today,
    )
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount_tolerance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.20,
    )
    confirmed_merchant_alias: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_rail: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_detected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    _legacy_last_detected_amount: Mapped[Optional[float]] = mapped_column(
        "last_detected_amount", Float, nullable=True
    )
    _exact_last_detected_amount: Mapped[Optional[Decimal]] = mapped_column(
        "last_detected_amount_minor", MoneyMinorUnits(), nullable=True
    )
    last_detected_amount = exact_money_hybrid(
        "_legacy_last_detected_amount", "_exact_last_detected_amount"
    )
    next_expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    enforce_current_month: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class IncomeMatchSuggestion(Base):
    __tablename__ = "income_match_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "income_source_id",
            "transaction_id",
            name="uq_income_match_source_transaction",
        ),
        Index("ix_income_match_suggestions_source_status", "income_source_id", "status"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_income_match_suggestions_confidence",
        ),
        CheckConstraint(
            "strength IN ('strong', 'uncertain')",
            name="ck_income_match_suggestions_strength",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'dismissed', 'stale')",
            name="ck_income_match_suggestions_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    income_source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("income_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strength: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
