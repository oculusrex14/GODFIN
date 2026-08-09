from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from app.core.time import utcnow_naive


class MonthlyAggregate(Base):
    __tablename__ = "monthly_aggregates"
    __table_args__ = (
        Index(
            "uq_monthly_aggregates_global_month",
            "month",
            unique=True,
            sqlite_where=text("account_id IS NULL"),
        ),
        Index(
            "uq_monthly_aggregates_account_month",
            "month",
            "account_id",
            unique=True,
            sqlite_where=text("account_id IS NOT NULL"),
        ),
        CheckConstraint(
            "length(month) = 7 AND substr(month, 5, 1) = '-' "
            "AND CAST(substr(month, 1, 4) AS INTEGER) BETWEEN 2000 AND 9999 "
            "AND CAST(substr(month, 6, 2) AS INTEGER) BETWEEN 1 AND 12",
            name="ck_monthly_aggregates_month",
        ),
        CheckConstraint(
            "total_spend BETWEEN 0 AND 1000000000000000 "
            "AND total_income BETWEEN 0 AND 1000000000000000 "
            "AND fixed_total BETWEEN 0 AND 1000000000000000 "
            "AND semi_flexible_total BETWEEN 0 AND 1000000000000000 "
            "AND flexible_total BETWEEN 0 AND 1000000000000000 "
            "AND transfer_total BETWEEN 0 AND 1000000000000000 "
            "AND recurring_total BETWEEN 0 AND 1000000000000000",
            name="ck_monthly_aggregates_nonnegative_totals",
        ),
        CheckConstraint(
            "savings_rate IS NULL OR "
            "(savings_rate >= -1000000 AND savings_rate <= 100)",
            name="ck_monthly_aggregates_savings_rate",
        ),
        CheckConstraint(
            "transaction_count >= 0",
            name="ck_monthly_aggregates_transaction_count",
        ),
        CheckConstraint(
            "is_finalized IN (0, 1)",
            name="ck_monthly_aggregates_is_finalized",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    total_spend: Mapped[float] = mapped_column(Float, default=0)
    total_income: Mapped[float] = mapped_column(Float, default=0)
    savings_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fixed_total: Mapped[float] = mapped_column(Float, default=0)
    semi_flexible_total: Mapped[float] = mapped_column(Float, default=0)
    flexible_total: Mapped[float] = mapped_column(Float, default=0)
    transfer_total: Mapped[float] = mapped_column(Float, default=0)
    recurring_total: Mapped[float] = mapped_column(Float, default=0)
    category_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("audit_sessions.id", ondelete="SET NULL"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
