from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits, exact_money_hybrid
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
        CheckConstraint(
            f"target_amount_minor BETWEEN 1 AND {MAX_MONEY_MINOR}",
            name="ck_goals_target_amount_minor_range",
        ),
        CheckConstraint(
            f"current_saved_minor BETWEEN 0 AND {MAX_MONEY_MINOR}",
            name="ck_goals_current_saved_minor_range",
        ),
        CheckConstraint(
            f"minimum_flexible_floor_minor BETWEEN 0 AND {MAX_MONEY_MINOR}",
            name="ck_goals_flexible_floor_minor_range",
        ),
        CheckConstraint(
            "target_amount_minor = CAST(ROUND(target_amount * 100, 0) AS INTEGER) "
            "AND current_saved_minor = "
            "CAST(ROUND(current_saved * 100, 0) AS INTEGER) "
            "AND minimum_flexible_floor_minor = "
            "CAST(ROUND(minimum_flexible_floor * 100, 0) AS INTEGER)",
            name="ck_goals_money_shadows_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    _legacy_target_amount: Mapped[float] = mapped_column(
        "target_amount", Float, nullable=False
    )
    _exact_target_amount: Mapped[Decimal] = mapped_column(
        "target_amount_minor", MoneyMinorUnits(), nullable=False
    )
    target_amount = exact_money_hybrid(
        "_legacy_target_amount", "_exact_target_amount"
    )
    _legacy_current_saved: Mapped[float] = mapped_column(
        "current_saved", Float, default=0
    )
    _exact_current_saved: Mapped[Decimal] = mapped_column(
        "current_saved_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    current_saved = exact_money_hybrid(
        "_legacy_current_saved", "_exact_current_saved"
    )
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    pressure_level: Mapped[str] = mapped_column(String(20), default="moderate")
    annual_return_rate: Mapped[float] = mapped_column(Float, default=0.0)
    _legacy_minimum_flexible_floor: Mapped[float] = mapped_column(
        "minimum_flexible_floor", Float, default=5000
    )
    _exact_minimum_flexible_floor: Mapped[Decimal] = mapped_column(
        "minimum_flexible_floor_minor",
        MoneyMinorUnits(),
        default=Decimal("5000.00"),
    )
    minimum_flexible_floor = exact_money_hybrid(
        "_legacy_minimum_flexible_floor",
        "_exact_minimum_flexible_floor",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
