from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.money import MAX_MONEY_MINOR, MoneyMinorUnits
from app.core.time import utcnow_naive


class AccountBalanceAnchor(Base):
    """An exact, provenance-bearing balance at a precise day boundary."""

    __tablename__ = "account_balance_anchors"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_fingerprint",
            "anchor_type",
            "boundary_date",
            name="uq_account_balance_anchor_source",
        ),
        Index(
            "ix_account_balance_anchors_account_boundary",
            "account_id",
            "boundary_date",
        ),
        CheckConstraint(
            f"balance_minor BETWEEN {-MAX_MONEY_MINOR} AND {MAX_MONEY_MINOR}",
            name="ck_account_balance_anchor_amount",
        ),
        CheckConstraint(
            "anchor_type IN ('statement_opening','statement_closing','manual_verified')",
            name="ck_account_balance_anchor_type",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_account_balance_anchor_currency",
        ),
        CheckConstraint(
            "NOT (verified = 1 AND conflict = 1)",
            name="ck_account_balance_anchor_trust",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    boundary_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        "balance_minor", MoneyMinorUnits(), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    anchor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_profile: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    statement_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    statement_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_method: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow_naive
    )


class AccountStatementCoverage(Base):
    """A statement interval whose rows and arithmetic controls were verified."""

    __tablename__ = "account_statement_coverages"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_fingerprint",
            name="uq_account_statement_coverage_source",
        ),
        Index(
            "ix_account_statement_coverages_account_period",
            "account_id",
            "period_start",
            "period_end",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_account_statement_coverage_period",
        ),
        CheckConstraint(
            "status IN ('verified','conflict')",
            name="ck_account_statement_coverage_status",
        ),
        CheckConstraint(
            "transaction_count >= 0",
            name="ck_account_statement_coverage_transaction_count",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    parser_profile: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_controls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    contains_running_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="verified"
    )
    opening_anchor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("account_balance_anchors.id", ondelete="SET NULL"),
        nullable=True,
    )
    closing_anchor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("account_balance_anchors.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow_naive
    )
