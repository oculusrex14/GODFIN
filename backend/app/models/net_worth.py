from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time import utcnow_naive


class NetWorthItem(Base):
    __tablename__ = "net_worth_items"
    __table_args__ = (
        Index("ix_net_worth_items_type", "item_type"),
        Index("ix_net_worth_items_asset_class", "asset_class"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    item_type: Mapped[str] = mapped_column(String(12), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    valuation_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="manual")
    symbol: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    manual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exchange_rate_to_base: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    valuation_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    valued_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )

    quotes: Mapped[list["NetWorthQuote"]] = relationship(
        "NetWorthQuote",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="NetWorthQuote.quoted_at.desc()",
    )


class NetWorthQuote(Base):
    __tablename__ = "net_worth_quotes"
    __table_args__ = (Index("ix_net_worth_quotes_item_quoted", "item_id", "quoted_at"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("net_worth_items.id", ondelete="CASCADE"), nullable=False
    )
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate_to_base: Mapped[float] = mapped_column(Float, nullable=False)
    total_value_base: Mapped[float] = mapped_column(Float, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    quoted_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow_naive)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    item: Mapped["NetWorthItem"] = relationship("NetWorthItem", back_populates="quotes")
