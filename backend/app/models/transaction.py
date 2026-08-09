from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time import utcnow_naive

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.transaction_split import TransactionSplit


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_category", "category"),
        Index("ix_transactions_email_message_id", "email_message_id"),
        Index("ix_transactions_checksum_source", "checksum_source"),
        Index("ix_transactions_checksum_canonical", "checksum_canonical"),
        Index(
            "uq_transactions_email_message_id",
            "email_message_id",
            unique=True,
            sqlite_where=text("email_message_id IS NOT NULL"),
        ),
        CheckConstraint(
            "amount > 0 AND amount <= 1000000000000000",
            name="ck_transactions_amount_range",
        ),
        CheckConstraint(
            "type IN ('debit', 'credit')",
            name="ck_transactions_type",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_transactions_confidence",
        ),
        CheckConstraint(
            "status IN ('settled', 'pending', 'deleted', 'reversed', "
            "'reversal', 'voided')",
            name="ck_transactions_status",
        ),
        CheckConstraint(
            "semantic_type IN ('unknown', 'expense', 'income', "
            "'internal_transfer', 'refund', 'reimbursement', 'reversal', "
            "'cashback', 'adjustment', 'excluded')",
            name="ck_transactions_semantic_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    merchant_normalized: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    instrument: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    classification_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="settled")
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_split: Mapped[bool] = mapped_column(Boolean, default=False)
    is_income: Mapped[bool] = mapped_column(Boolean, default=False)
    semantic_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown"
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    vpa_handle: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    upi_ref_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    checksum_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    checksum_canonical: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classification_version: Mapped[int] = mapped_column(Integer, default=1)
    audit_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("audit_sessions.id", ondelete="SET NULL"), nullable=True
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow_naive, onupdate=utcnow_naive)

    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship("TransactionSplit", back_populates="parent_transaction")
