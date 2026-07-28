from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class IncomeSource(Base):
    __tablename__ = "income_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    last_detected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_detected_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    next_expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    enforce_current_month: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
