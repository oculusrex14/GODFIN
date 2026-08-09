from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import (
    MAX_MONEY_MINOR,
    MoneyMinorUnits,
    money_from_minor,
    money_decimal,
    set_money_columns,
)
from app.core.time import utcnow_naive


class TransferMatch(Base):
    __tablename__ = "transfer_matches"
    __table_args__ = (
        UniqueConstraint(
            "debit_transaction_id",
            "credit_transaction_id",
            name="uq_transfer_match_pair",
        ),
        CheckConstraint(
            f"amount_minor > 0 AND amount_minor <= {MAX_MONEY_MINOR}",
            name="ck_transfer_matches_amount_minor_range",
        ),
        CheckConstraint(
            "amount_minor = CAST(ROUND(amount * 100, 0) AS INTEGER)",
            name="ck_transfer_matches_amount_shadow_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    debit_transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id"), nullable=False, index=True
    )
    credit_transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id"), nullable=False, index=True
    )
    _legacy_amount: Mapped[float] = mapped_column("amount", Float, nullable=False)
    _exact_amount: Mapped[Decimal] = mapped_column(
        "amount_minor", MoneyMinorUnits(), nullable=False
    )
    date_gap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    snoozed_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )

    @hybrid_property
    def amount(self) -> Decimal:
        if self._exact_amount is not None:
            return money_decimal(self._exact_amount)
        return money_from_minor(None, self._legacy_amount)

    @amount.inplace.setter
    def _set_amount(self, value) -> None:
        set_money_columns(
            self,
            value,
            legacy_attr="_legacy_amount",
            exact_attr="_exact_amount",
        )

    @amount.inplace.expression
    @classmethod
    def _amount_expression(cls):
        return cls._exact_amount
