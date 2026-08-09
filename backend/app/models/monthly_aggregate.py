from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
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
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits, exact_money_hybrid
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
        CheckConstraint(
            "total_spend_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND total_income_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND fixed_total_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND semi_flexible_total_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND flexible_total_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND transfer_total_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR} AND recurring_total_minor BETWEEN 0 AND "
            f"{MAX_MONEY_MINOR}",
            name="ck_monthly_aggregates_exact_totals_range",
        ),
        CheckConstraint(
            "total_spend_minor = CAST(ROUND(total_spend * 100, 0) AS INTEGER) "
            "AND total_income_minor = "
            "CAST(ROUND(total_income * 100, 0) AS INTEGER) "
            "AND fixed_total_minor = "
            "CAST(ROUND(fixed_total * 100, 0) AS INTEGER) "
            "AND semi_flexible_total_minor = "
            "CAST(ROUND(semi_flexible_total * 100, 0) AS INTEGER) "
            "AND flexible_total_minor = "
            "CAST(ROUND(flexible_total * 100, 0) AS INTEGER) "
            "AND transfer_total_minor = "
            "CAST(ROUND(transfer_total * 100, 0) AS INTEGER) "
            "AND recurring_total_minor = "
            "CAST(ROUND(recurring_total * 100, 0) AS INTEGER)",
            name="ck_monthly_aggregates_money_shadows_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    _legacy_total_spend: Mapped[float] = mapped_column(
        "total_spend", Float, default=0
    )
    _exact_total_spend: Mapped[Decimal] = mapped_column(
        "total_spend_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    total_spend = exact_money_hybrid("_legacy_total_spend", "_exact_total_spend")
    _legacy_total_income: Mapped[float] = mapped_column(
        "total_income", Float, default=0
    )
    _exact_total_income: Mapped[Decimal] = mapped_column(
        "total_income_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    total_income = exact_money_hybrid(
        "_legacy_total_income", "_exact_total_income"
    )
    savings_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    _legacy_fixed_total: Mapped[float] = mapped_column(
        "fixed_total", Float, default=0
    )
    _exact_fixed_total: Mapped[Decimal] = mapped_column(
        "fixed_total_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    fixed_total = exact_money_hybrid("_legacy_fixed_total", "_exact_fixed_total")
    _legacy_semi_flexible_total: Mapped[float] = mapped_column(
        "semi_flexible_total", Float, default=0
    )
    _exact_semi_flexible_total: Mapped[Decimal] = mapped_column(
        "semi_flexible_total_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    semi_flexible_total = exact_money_hybrid(
        "_legacy_semi_flexible_total", "_exact_semi_flexible_total"
    )
    _legacy_flexible_total: Mapped[float] = mapped_column(
        "flexible_total", Float, default=0
    )
    _exact_flexible_total: Mapped[Decimal] = mapped_column(
        "flexible_total_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    flexible_total = exact_money_hybrid(
        "_legacy_flexible_total", "_exact_flexible_total"
    )
    _legacy_transfer_total: Mapped[float] = mapped_column(
        "transfer_total", Float, default=0
    )
    _exact_transfer_total: Mapped[Decimal] = mapped_column(
        "transfer_total_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    transfer_total = exact_money_hybrid(
        "_legacy_transfer_total", "_exact_transfer_total"
    )
    _legacy_recurring_total: Mapped[float] = mapped_column(
        "recurring_total", Float, default=0
    )
    _exact_recurring_total: Mapped[Decimal] = mapped_column(
        "recurring_total_minor", MoneyMinorUnits(), default=Decimal("0.00")
    )
    recurring_total = exact_money_hybrid(
        "_legacy_recurring_total", "_exact_recurring_total"
    )
    category_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("audit_sessions.id", ondelete="SET NULL"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
