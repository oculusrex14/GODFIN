from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class MonthlyAggregate(Base):
    __tablename__ = "monthly_aggregates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id"), nullable=True
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
        String(36), ForeignKey("audit_sessions.id"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
