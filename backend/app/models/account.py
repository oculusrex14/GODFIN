from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time import utcnow_naive

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank: Mapped[str] = mapped_column(String(50), nullable=False, default="HDFC")
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    last_4_digits: Mapped[str] = mapped_column(String(4), nullable=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)

    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="account")
