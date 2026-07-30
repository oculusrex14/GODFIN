from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    current_saved: Mapped[float] = mapped_column(Float, default=0)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    pressure_level: Mapped[str] = mapped_column(String(20), default="moderate")
    annual_return_rate: Mapped[float] = mapped_column(Float, default=0.0)
    minimum_flexible_floor: Mapped[float] = mapped_column(Float, default=5000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
