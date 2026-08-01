from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class GoalContribution(Base):
    __tablename__ = "goal_contributions"
    __table_args__ = (
        UniqueConstraint(
            "source_transaction_id",
            name="uq_goal_contribution_source_transaction",
        ),
        UniqueConstraint("idempotency_key", name="uq_goal_contribution_idempotency"),
        CheckConstraint(
            "amount >= -1000000000000000 "
            "AND amount <= 1000000000000000 "
            "AND ((entry_type = 'deposit' AND amount > 0) "
            "OR (entry_type = 'withdrawal' AND amount < 0))",
            name="ck_goal_contributions_amount_range",
        ),
        CheckConstraint(
            "entry_type IN ('deposit', 'withdrawal')",
            name="ck_goal_contributions_entry_type",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    goal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("goals.id"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    contribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual"
    )
    source_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transactions.id"), nullable=True, index=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class GoalContributionSuggestion(Base):
    __tablename__ = "goal_contribution_suggestions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    goal_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("goals.id"), nullable=True, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    deposit_type: Mapped[str] = mapped_column(String(10), nullable=False)
    evidence: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )
