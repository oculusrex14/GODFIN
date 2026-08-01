from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(
            "target_amount > 0 AND target_amount <= 1000000000000000",
            name="ck_goals_target_amount_range",
        ),
        CheckConstraint(
            "current_saved >= 0 AND current_saved <= 1000000000000000",
            name="ck_goals_current_saved_range",
        ),
        CheckConstraint(
            "annual_return_rate >= 0 AND annual_return_rate <= 0.5",
            name="ck_goals_annual_return_rate",
        ),
        CheckConstraint(
            "minimum_flexible_floor >= 0 AND "
            "minimum_flexible_floor <= 1000000000000000",
            name="ck_goals_minimum_flexible_floor",
        ),
        CheckConstraint(
            "pressure_level IN ('minimal', 'moderate', 'aggressive')",
            name="ck_goals_pressure_level",
        ),
    )

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
