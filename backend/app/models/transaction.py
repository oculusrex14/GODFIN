from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
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
            f"amount_minor > 0 AND amount_minor <= {MAX_MONEY_MINOR}",
            name="ck_transactions_amount_minor_range",
        ),
        CheckConstraint(
            "amount_minor = CAST(ROUND(amount * 100, 0) AS INTEGER)",
            name="ck_transactions_amount_shadow_consistent",
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
        CheckConstraint(
            "semantic_detail IN ('purchase', 'transfer_in', 'transfer_out', "
            "'internal_transfer', 'credit_card_payment', 'refund', 'reversal', "
            "'chargeback', 'fee_charge', 'cash_withdrawal', 'cash_deposit', "
            "'interest_credit', 'interest_debit', 'salary', 'other_income', "
            "'cashback_reward', 'wallet_topup', 'wallet_withdrawal', "
            "'investment_buy', 'investment_sell', 'investment_sip', 'dividend', "
            "'loan_disbursement', 'loan_payment', 'emi', 'bill_payment', "
            "'tax_payment', 'tax_refund', 'unknown')",
            name="ck_transactions_semantic_detail",
        ),
        CheckConstraint(
            "currency = UPPER(currency) AND length(currency) = 3",
            name="ck_transactions_currency",
        ),
        CheckConstraint(
            "vpa_role IS NULL OR vpa_role IN ('person', 'merchant', 'unknown')",
            name="ck_transactions_vpa_role",
        ),
        CheckConstraint(
            f"running_balance_minor IS NULL OR "
            f"(running_balance_minor >= {-MAX_MONEY_MINOR} AND "
            f"running_balance_minor <= {MAX_MONEY_MINOR})",
            name="ck_transactions_running_balance_minor_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    merchant_normalized: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    _legacy_amount: Mapped[float] = mapped_column("amount", Float, nullable=False)
    _exact_amount: Mapped[Decimal] = mapped_column(
        "amount_minor", MoneyMinorUnits(), nullable=False
    )
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
    semantic_detail: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_bank: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_format_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    running_balance_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payment_rail: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    processor_candidate: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    counterparty_candidate: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extraction_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vpa_role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
