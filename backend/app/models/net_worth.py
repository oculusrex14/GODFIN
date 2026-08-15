from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.money import (
    FX_RATE_SCALE,
    MAX_EXACT_FX_RATE,
    MAX_NET_WORTH_MONEY,
    MAX_NET_WORTH_MONEY_MINOR,
    MAX_QUANTITY,
    MAX_UNIT_PRICE,
    MONEY_SCALE,
    QUANTITY_SCALE,
    ScaledIntegerUnits,
    UNIT_PRICE_SCALE,
    exact_scaled_hybrid,
)
from app.core.time import utcnow_naive


class NetWorthItem(Base):
    __tablename__ = "net_worth_items"
    __table_args__ = (
        Index("ix_net_worth_items_type", "item_type"),
        Index("ix_net_worth_items_asset_class", "asset_class"),
        CheckConstraint(
            "item_type IN ('asset', 'liability')",
            name="ck_net_worth_items_type",
        ),
        CheckConstraint(
            "asset_class IN ('cash', 'stock', 'etf', 'mutual_fund', 'crypto', "
            "'bond', 'metal', 'property', 'land', 'gem', 'private_asset', "
            "'debt', 'other')",
            name="ck_net_worth_items_asset_class",
        ),
        CheckConstraint(
            "valuation_mode IN ('manual', 'market')",
            name="ck_net_worth_items_valuation_mode",
        ),
        CheckConstraint(
            f"quantity > 0 AND quantity <= {MAX_QUANTITY}",
            name="ck_net_worth_items_quantity_range",
        ),
        CheckConstraint(
            "manual_value IS NULL OR "
            f"(manual_value >= 0 AND manual_value <= {MAX_NET_WORTH_MONEY})",
            name="ck_net_worth_items_manual_value_range",
        ),
        CheckConstraint(
            "exchange_rate_to_base > 0 AND "
            f"exchange_rate_to_base <= {MAX_EXACT_FX_RATE}",
            name="ck_net_worth_items_exchange_rate",
        ),
        CheckConstraint(
            f"quantity_units BETWEEN 1 AND {int(MAX_QUANTITY * QUANTITY_SCALE)}",
            name="ck_net_worth_items_quantity_units_range",
        ),
        CheckConstraint(
            f"quantity_units = CAST(ROUND(quantity * {QUANTITY_SCALE}, 0) AS INTEGER)",
            name="ck_net_worth_items_quantity_shadow_consistent",
        ),
        CheckConstraint(
            "((manual_value IS NULL AND manual_value_minor IS NULL) OR "
            "(manual_value IS NOT NULL AND manual_value_minor BETWEEN 0 AND "
            f"{MAX_NET_WORTH_MONEY_MINOR} AND manual_value_minor = "
            f"CAST(ROUND(manual_value * {MONEY_SCALE}, 0) AS INTEGER)))",
            name="ck_net_worth_items_manual_value_shadow_consistent",
        ),
        CheckConstraint(
            "exchange_rate_to_base_units BETWEEN 1 AND "
            f"{int(MAX_EXACT_FX_RATE * FX_RATE_SCALE)}",
            name="ck_net_worth_items_exchange_rate_units_range",
        ),
        CheckConstraint(
            "exchange_rate_to_base_units = "
            f"CAST(ROUND(exchange_rate_to_base * {FX_RATE_SCALE}, 0) AS INTEGER)",
            name="ck_net_worth_items_exchange_rate_shadow_consistent",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_net_worth_items_currency_shape",
        ),
        CheckConstraint(
            "((fx_source_currency IS NULL AND fx_base_currency IS NULL "
            "AND fx_rate_source IS NULL AND "
            "fx_rate_source_url IS NULL AND fx_rate_as_of IS NULL AND "
            "fx_rate_fetched_at IS NULL) OR "
            "(length(fx_source_currency) = 3 AND "
            "fx_source_currency = upper(fx_source_currency) AND "
            "length(fx_base_currency) = 3 AND "
            "fx_base_currency = upper(fx_base_currency) AND "
            "length(fx_rate_source) > 0 AND length(fx_rate_source_url) > 0 "
            "AND fx_rate_as_of IS NOT NULL AND fx_rate_fetched_at IS NOT NULL))",
            name="ck_net_worth_items_fx_provenance_complete",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    item_type: Mapped[str] = mapped_column(String(12), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    valuation_mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="manual"
    )
    symbol: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    _legacy_quantity: Mapped[float] = mapped_column(
        "quantity", Float, nullable=False, default=1.0
    )
    _exact_quantity: Mapped[Decimal] = mapped_column(
        "quantity_units",
        ScaledIntegerUnits(
            scale=QUANTITY_SCALE,
            minimum=Decimal("0.00000001"),
            maximum=MAX_QUANTITY,
            field_name="Quantity",
        ),
        nullable=False,
        default=Decimal("1"),
    )
    quantity = exact_scaled_hybrid(
        "_legacy_quantity",
        "_exact_quantity",
        scale=QUANTITY_SCALE,
        minimum=Decimal("0.00000001"),
        maximum=MAX_QUANTITY,
        field_name="Quantity",
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    _legacy_manual_value: Mapped[Optional[float]] = mapped_column(
        "manual_value", Float, nullable=True
    )
    _exact_manual_value: Mapped[Optional[Decimal]] = mapped_column(
        "manual_value_minor",
        ScaledIntegerUnits(
            scale=MONEY_SCALE,
            minimum=Decimal("0"),
            maximum=MAX_NET_WORTH_MONEY,
            field_name="Manual value",
        ),
        nullable=True,
    )
    manual_value = exact_scaled_hybrid(
        "_legacy_manual_value",
        "_exact_manual_value",
        scale=MONEY_SCALE,
        minimum=Decimal("0"),
        maximum=MAX_NET_WORTH_MONEY,
        field_name="Manual value",
    )
    _legacy_exchange_rate_to_base: Mapped[float] = mapped_column(
        "exchange_rate_to_base", Float, nullable=False, default=1.0
    )
    _exact_exchange_rate_to_base: Mapped[Decimal] = mapped_column(
        "exchange_rate_to_base_units",
        ScaledIntegerUnits(
            scale=FX_RATE_SCALE,
            minimum=Decimal("0.000000000001"),
            maximum=MAX_EXACT_FX_RATE,
            field_name="Exchange rate",
        ),
        nullable=False,
        default=Decimal("1"),
    )
    exchange_rate_to_base = exact_scaled_hybrid(
        "_legacy_exchange_rate_to_base",
        "_exact_exchange_rate_to_base",
        scale=FX_RATE_SCALE,
        minimum=Decimal("0.000000000001"),
        maximum=MAX_EXACT_FX_RATE,
        field_name="Exchange rate",
    )
    fx_source_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    fx_base_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    fx_rate_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    fx_rate_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    fx_rate_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fx_rate_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    valuation_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    valued_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
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
    __table_args__ = (
        Index("ix_net_worth_quotes_item_quoted", "item_id", "quoted_at"),
        CheckConstraint(
            "((fx_rate_source IS NULL AND fx_rate_source_url IS NULL AND "
            "fx_rate_as_of IS NULL AND fx_rate_fetched_at IS NULL) OR "
            "(length(fx_rate_source) > 0 AND length(fx_rate_source_url) > 0 "
            "AND fx_rate_as_of IS NOT NULL AND fx_rate_fetched_at IS NOT NULL))",
            name="ck_net_worth_quotes_fx_provenance_complete",
        ),
        CheckConstraint(
            f"unit_price > 0 AND unit_price <= {MAX_UNIT_PRICE}",
            name="ck_net_worth_quotes_unit_price_range",
        ),
        CheckConstraint(
            f"unit_price_units BETWEEN 1 AND {int(MAX_UNIT_PRICE * UNIT_PRICE_SCALE)}",
            name="ck_net_worth_quotes_unit_price_units_range",
        ),
        CheckConstraint(
            f"unit_price_units = CAST(ROUND(unit_price * {UNIT_PRICE_SCALE}, 0) AS INTEGER)",
            name="ck_net_worth_quotes_unit_price_shadow_consistent",
        ),
        CheckConstraint(
            "exchange_rate_to_base > 0 AND "
            f"exchange_rate_to_base <= {MAX_EXACT_FX_RATE}",
            name="ck_net_worth_quotes_exchange_rate_range",
        ),
        CheckConstraint(
            "exchange_rate_to_base_units BETWEEN 1 AND "
            f"{int(MAX_EXACT_FX_RATE * FX_RATE_SCALE)}",
            name="ck_net_worth_quotes_exchange_rate_units_range",
        ),
        CheckConstraint(
            "exchange_rate_to_base_units = "
            f"CAST(ROUND(exchange_rate_to_base * {FX_RATE_SCALE}, 0) AS INTEGER)",
            name="ck_net_worth_quotes_exchange_rate_shadow_consistent",
        ),
        CheckConstraint(
            f"total_value_base >= 0 AND total_value_base <= {MAX_NET_WORTH_MONEY}",
            name="ck_net_worth_quotes_total_value_range",
        ),
        CheckConstraint(
            f"total_value_base_minor BETWEEN 0 AND {MAX_NET_WORTH_MONEY_MINOR}",
            name="ck_net_worth_quotes_total_value_minor_range",
        ),
        CheckConstraint(
            "total_value_base_minor = "
            f"CAST(ROUND(total_value_base * {MONEY_SCALE}, 0) AS INTEGER)",
            name="ck_net_worth_quotes_total_value_shadow_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("net_worth_items.id", ondelete="CASCADE"), nullable=False
    )
    _legacy_unit_price: Mapped[float] = mapped_column(
        "unit_price", Float, nullable=False
    )
    _exact_unit_price: Mapped[Decimal] = mapped_column(
        "unit_price_units",
        ScaledIntegerUnits(
            scale=UNIT_PRICE_SCALE,
            minimum=Decimal("0.00000001"),
            maximum=MAX_UNIT_PRICE,
            field_name="Unit price",
        ),
        nullable=False,
    )
    unit_price = exact_scaled_hybrid(
        "_legacy_unit_price",
        "_exact_unit_price",
        scale=UNIT_PRICE_SCALE,
        minimum=Decimal("0.00000001"),
        maximum=MAX_UNIT_PRICE,
        field_name="Unit price",
    )
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    _legacy_exchange_rate_to_base: Mapped[float] = mapped_column(
        "exchange_rate_to_base", Float, nullable=False
    )
    _exact_exchange_rate_to_base: Mapped[Decimal] = mapped_column(
        "exchange_rate_to_base_units",
        ScaledIntegerUnits(
            scale=FX_RATE_SCALE,
            minimum=Decimal("0.000000000001"),
            maximum=MAX_EXACT_FX_RATE,
            field_name="Exchange rate",
        ),
        nullable=False,
    )
    exchange_rate_to_base = exact_scaled_hybrid(
        "_legacy_exchange_rate_to_base",
        "_exact_exchange_rate_to_base",
        scale=FX_RATE_SCALE,
        minimum=Decimal("0.000000000001"),
        maximum=MAX_EXACT_FX_RATE,
        field_name="Exchange rate",
    )
    _legacy_total_value_base: Mapped[float] = mapped_column(
        "total_value_base", Float, nullable=False
    )
    _exact_total_value_base: Mapped[Decimal] = mapped_column(
        "total_value_base_minor",
        ScaledIntegerUnits(
            scale=MONEY_SCALE,
            minimum=Decimal("0"),
            maximum=MAX_NET_WORTH_MONEY,
            field_name="Total value",
        ),
        nullable=False,
    )
    total_value_base = exact_scaled_hybrid(
        "_legacy_total_value_base",
        "_exact_total_value_base",
        scale=MONEY_SCALE,
        minimum=Decimal("0"),
        maximum=MAX_NET_WORTH_MONEY,
        field_name="Total value",
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    fx_rate_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    fx_rate_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    fx_rate_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fx_rate_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    quoted_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow_naive)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    item: Mapped["NetWorthItem"] = relationship("NetWorthItem", back_populates="quotes")
