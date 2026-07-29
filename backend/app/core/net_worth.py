from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.models.net_worth import NetWorthItem, NetWorthQuote
from app.core.time import utcnow_naive

BASE_CURRENCY_KEY = "net_worth_base_currency"
MARKET_DATA_KEY = "twelve_data_api_key"
LIQUID_CLASSES = {"cash", "stock", "etf", "mutual_fund", "crypto", "bond", "metal"}


def get_base_currency(db: Session) -> str:
    setting = db.query(AppSetting).filter_by(key=BASE_CURRENCY_KEY).first()
    return (setting.value if setting else "INR").upper()


def _latest_quote(item: NetWorthItem) -> NetWorthQuote | None:
    return max(item.quotes, key=lambda quote: quote.quoted_at, default=None)


def item_value(item: NetWorthItem) -> dict[str, Any]:
    latest = _latest_quote(item)
    today = date.today()
    if item.valuation_mode == "market" and latest is not None:
        value = float(latest.total_value_base)
        source = latest.source
        source_url = latest.source_url
        valued_at = latest.quoted_at.date()
        expires_on = latest.expires_at.date()
        stale = latest.expires_at < utcnow_naive()
        provenance = "live_quote"
    else:
        value = float(item.manual_value or 0) * float(item.exchange_rate_to_base or 1)
        source = item.valuation_source or "Manual valuation"
        source_url = item.source_url
        valued_at = item.valued_at
        expires_on = item.expires_on
        stale = expires_on is not None and expires_on < today
        provenance = "manual"
    return {
        "value_base": round(value, 2),
        "source": source,
        "source_url": source_url,
        "valued_at": valued_at.isoformat() if valued_at else None,
        "expires_on": expires_on.isoformat() if expires_on else None,
        "stale": stale,
        "provenance": provenance,
    }


def serialize_item(item: NetWorthItem, *, include_history: bool = False) -> dict[str, Any]:
    value = item_value(item)
    payload = {
        "id": item.id,
        "name": item.name,
        "item_type": item.item_type,
        "asset_class": item.asset_class,
        "valuation_mode": item.valuation_mode,
        "symbol": item.symbol,
        "quantity": item.quantity,
        "currency": item.currency,
        "manual_value": item.manual_value,
        "exchange_rate_to_base": item.exchange_rate_to_base,
        "valuation_source": item.valuation_source,
        "source_url": item.source_url,
        "valued_at": item.valued_at.isoformat() if item.valued_at else None,
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "notes": item.notes,
        "is_active": item.is_active,
        **value,
    }
    if include_history:
        payload["quote_history"] = [
            {
                "id": quote.id,
                "unit_price": quote.unit_price,
                "quote_currency": quote.quote_currency,
                "exchange_rate_to_base": quote.exchange_rate_to_base,
                "total_value_base": quote.total_value_base,
                "base_currency": quote.base_currency,
                "source": quote.source,
                "source_url": quote.source_url,
                "quoted_at": quote.quoted_at.isoformat(),
                "expires_at": quote.expires_at.isoformat(),
            }
            for quote in sorted(item.quotes, key=lambda row: row.quoted_at, reverse=True)[
                :100
            ]
        ]
    return payload


def net_worth_summary(db: Session) -> dict[str, Any]:
    items = (
        db.query(NetWorthItem)
        .filter(NetWorthItem.is_active.is_(True))
        .order_by(NetWorthItem.item_type, NetWorthItem.name)
        .all()
    )
    serialized = [serialize_item(item) for item in items]
    assets = sum(
        item["value_base"] for item in serialized if item["item_type"] == "asset"
    )
    liabilities = sum(
        item["value_base"]
        for item in serialized
        if item["item_type"] == "liability"
    )
    stale_count = sum(bool(item["stale"]) for item in serialized)
    return {
        "base_currency": get_base_currency(db),
        "total_assets": round(assets, 2),
        "total_liabilities": round(liabilities, 2),
        "net_worth": round(assets - liabilities, 2),
        "stale_count": stale_count,
        "item_count": len(serialized),
        "items": serialized,
        "provenance": (
            "Calculated locally as assets minus liabilities from the latest "
            "saved quote or manual valuation for each active item."
        ),
    }


def liquid_asset_total(db: Session) -> float:
    items = (
        db.query(NetWorthItem)
        .filter(
            NetWorthItem.is_active.is_(True),
            NetWorthItem.item_type == "asset",
            NetWorthItem.asset_class.in_(LIQUID_CLASSES),
        )
        .all()
    )
    return sum(item_value(item)["value_base"] for item in items)
