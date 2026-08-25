from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.money import (
    MAX_MONEY_MINOR,
    MoneyMinorUnits,
    money_from_minor,
    money_decimal,
    set_money_columns,
)
from app.core.time import utcnow_naive

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    __table_args__ = (
        CheckConstraint(
            f"amount_minor > 0 AND amount_minor <= {MAX_MONEY_MINOR}",
            name="ck_transaction_splits_amount_minor_range",
        ),
        CheckConstraint(
            "amount_minor = CAST(ROUND(amount * 100, 0) AS INTEGER)",
            name="ck_transaction_splits_amount_shadow_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    _legacy_amount: Mapped[float] = mapped_column("amount", Float, nullable=False)
    _exact_amount: Mapped[Decimal] = mapped_column(
        "amount_minor", MoneyMinorUnits(), nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)

    parent_transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="splits")

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
