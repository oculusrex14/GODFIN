from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.fx import (
    FRANKFURTER_RATES_URL,
    FX_PROVIDER,
    MAX_RATE_AGE_DAYS,
    STALE_AFTER_DAYS,
    SUPPORTED_CURRENCIES,
    FxRateSnapshot,
    FxRateUnavailable,
    get_inr_rates,
    unavailable_fx_metadata,
)
from app.core.money import (
    FX_RATE_SCALE,
    MAX_EXACT_FX_RATE,
    money_decimal,
    scaled_decimal,
)
from app.core.time import utcnow_naive
from app.models.app_setting import AppSetting
from app.models.net_worth import NetWorthItem, NetWorthQuote

BASE_CURRENCY_KEY = "net_worth_base_currency"
MARKET_DATA_KEY = "twelve_data_api_key"
LIQUID_CLASSES = {"cash", "stock", "etf", "mutual_fund", "crypto", "bond", "metal"}
CALCULATION_VERSION = "net_worth_v3"


@dataclass(frozen=True)
class NetWorthValuationContext:
    base_currency: str
    snapshot: FxRateSnapshot | None
    requested_currencies: frozenset[str]
    unavailable_reason: str | None = None

    def metadata(self) -> dict[str, Any]:
        if self.snapshot is not None:
            return self.snapshot.metadata(self.requested_currencies)
        if len(self.requested_currencies) <= 1:
            return {
                "status": "not_required",
                "provider": "No conversion required",
                "source_url": None,
                "as_of": date.today().isoformat(),
                "age_days": 0,
                "stale": False,
                "rate_direction": (
                    f"{self.base_currency} per 1 unit of the source currency"
                ),
                "rates_to_inr": {},
                "rate_dates": {},
                "requested_currencies": sorted(self.requested_currencies),
                "privacy": "No market or personal data left this computer.",
                "unavailable_reason": None,
            }
        return unavailable_fx_metadata(
            self.unavailable_reason or "Verified currency conversion is unavailable.",
            self.requested_currencies,
        )


def get_base_currency(db: Session) -> str:
    setting = db.query(AppSetting).filter_by(key=BASE_CURRENCY_KEY).first()
    return (setting.value if setting else "INR").strip().upper()


def build_valuation_context(
    items: Iterable[NetWorthItem],
    *,
    base_currency: str,
    today: date | None = None,
    force_refresh: bool = False,
) -> NetWorthValuationContext:
    base = base_currency.strip().upper()
    source_currencies = {
        (item.currency or "").strip().upper() for item in items if item.currency
    }
    requested = frozenset({base, *source_currencies})
    needs_conversion = any(currency != base for currency in source_currencies)
    if not needs_conversion:
        return NetWorthValuationContext(base, None, requested or frozenset({base}))

    unsupported = requested - SUPPORTED_CURRENCIES
    if unsupported:
        listed = ", ".join(sorted(unsupported))
        return NetWorthValuationContext(
            base,
            None,
            requested,
            f"Verified conversion is not available for {listed}.",
        )
    try:
        snapshot = get_inr_rates(
            requested,
            today=today,
            force_refresh=force_refresh,
        )
    except FxRateUnavailable as exc:
        return NetWorthValuationContext(base, None, requested, str(exc))
    return NetWorthValuationContext(base, snapshot, requested)


def clear_item_fx(item: NetWorthItem) -> None:
    item.exchange_rate_to_base = 1
    item.fx_source_currency = None
    item.fx_base_currency = None
    item.fx_rate_source = None
    item.fx_rate_source_url = None
    item.fx_rate_as_of = None
    item.fx_rate_fetched_at = None


def apply_snapshot_to_item(
    item: NetWorthItem,
    snapshot: FxRateSnapshot,
    *,
    base_currency: str,
    fetched_at: datetime | None = None,
) -> None:
    source = item.currency.strip().upper()
    base = base_currency.strip().upper()
    if source == base:
        clear_item_fx(item)
        return
    item.exchange_rate_to_base = Decimal(str(snapshot.rate_between(source, base)))
    item.fx_source_currency = source
    item.fx_base_currency = base
    item.fx_rate_source = snapshot.provider
    item.fx_rate_source_url = snapshot.source_url
    item.fx_rate_as_of = snapshot.as_of
    item.fx_rate_fetched_at = fetched_at or utcnow_naive()


def refresh_manual_item_rates(
    db: Session,
    *,
    base_currency: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = (
        db.query(NetWorthItem)
        .filter(
            NetWorthItem.is_active.is_(True),
            NetWorthItem.valuation_mode == "manual",
        )
        .all()
    )
    context = build_valuation_context(
        items,
        base_currency=base_currency,
        force_refresh=force_refresh,
    )
    updated = 0
    for item in items:
        if item.currency == context.base_currency:
            clear_item_fx(item)
    if context.snapshot is not None:
        for item in items:
            if item.currency != context.base_currency:
                apply_snapshot_to_item(
                    item,
                    context.snapshot,
                    base_currency=context.base_currency,
                )
                updated += 1
    return {
        "updated_items": updated,
        "total_manual_items": len(items),
        "fx": context.metadata(),
    }


def _latest_quote_subquery():
    return (
        select(NetWorthQuote.id)
        .where(NetWorthQuote.item_id == NetWorthItem.id)
        .order_by(NetWorthQuote.quoted_at.desc(), NetWorthQuote.id.desc())
        .limit(1)
        .correlate(NetWorthItem)
        .scalar_subquery()
    )


def _items_with_latest_quote(
    db: Session,
    *,
    liquid_only: bool = False,
) -> list[tuple[NetWorthItem, NetWorthQuote | None]]:
    query = (
        db.query(NetWorthItem, NetWorthQuote)
        .outerjoin(NetWorthQuote, NetWorthQuote.id == _latest_quote_subquery())
        .filter(NetWorthItem.is_active.is_(True))
    )
    if liquid_only:
        query = query.filter(
            NetWorthItem.item_type == "asset",
            NetWorthItem.asset_class.in_(LIQUID_CLASSES),
        )
    return query.order_by(NetWorthItem.item_type, NetWorthItem.name).all()


def _stored_rate(
    record,
    *,
    source_currency: str,
    base_currency: str,
    stored_source_currency: str | None,
    stored_base_currency: str | None,
    today: date,
) -> tuple[Decimal, dict[str, Any]] | None:
    rate = getattr(record, "exchange_rate_to_base", None)
    as_of = getattr(record, "fx_rate_as_of", None)
    source = getattr(record, "fx_rate_source", None)
    source_url = getattr(record, "fx_rate_source_url", None)
    fetched_at = getattr(record, "fx_rate_fetched_at", None)
    try:
        numeric_rate = scaled_decimal(
            rate,
            scale=FX_RATE_SCALE,
            minimum=Decimal("0.000000000001"),
            maximum=MAX_EXACT_FX_RATE,
            field_name="Exchange rate",
        )
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        stored_source_currency != source_currency
        or stored_base_currency != base_currency
        or source_currency == base_currency
        or numeric_rate <= 0
        or source != FX_PROVIDER
        or source_url != FRANKFURTER_RATES_URL
        or not isinstance(as_of, date)
        or not isinstance(fetched_at, datetime)
        or fetched_at.date() < as_of
    ):
        return None
    age_days = (today - as_of).days
    fetched_age_days = (today - fetched_at.date()).days
    if (
        age_days < 0
        or age_days > MAX_RATE_AGE_DAYS
        or fetched_age_days < 0
        or fetched_age_days > MAX_RATE_AGE_DAYS
    ):
        return None
    return numeric_rate, {
        "status": "stored",
        "provider": source,
        "source_url": source_url,
        "as_of": as_of.isoformat(),
        "age_days": age_days,
        "stale": age_days > STALE_AFTER_DAYS,
        "rate": numeric_rate,
        "source_currency": source_currency,
        "base_currency": base_currency,
        "unavailable_reason": None,
        "privacy": "Only currency codes were sent when this rate was obtained.",
    }


def _conversion(
    record,
    *,
    source_currency: str,
    stored_source_currency: str | None,
    stored_base_currency: str | None,
    context: NetWorthValuationContext,
    today: date,
) -> tuple[Decimal | None, dict[str, Any]]:
    source = source_currency.strip().upper()
    base = context.base_currency
    if source == base:
        return Decimal("1"), {
            "status": "not_required",
            "provider": "No conversion required",
            "source_url": None,
            "as_of": today.isoformat(),
            "age_days": 0,
            "stale": False,
            "rate": Decimal("1"),
            "source_currency": source,
            "base_currency": base,
            "unavailable_reason": None,
            "privacy": "No data left this computer.",
        }
    if context.snapshot is not None:
        try:
            rate = context.snapshot.rate_between(source, base)
        except FxRateUnavailable:
            rate = None
        if rate is not None:
            normalized_rate = scaled_decimal(
                rate,
                scale=FX_RATE_SCALE,
                minimum=Decimal("0.000000000001"),
                maximum=MAX_EXACT_FX_RATE,
                field_name="Exchange rate",
            )
            return normalized_rate, {
                "status": context.snapshot.status,
                "provider": context.snapshot.provider,
                "source_url": context.snapshot.source_url,
                "as_of": context.snapshot.as_of.isoformat(),
                "age_days": context.snapshot.age_days,
                "stale": context.snapshot.stale,
                "rate": normalized_rate,
                "source_currency": source,
                "base_currency": base,
                "unavailable_reason": None,
                "privacy": "Only currency codes were sent; values and holdings stayed local.",
            }
    saved = _stored_rate(
        record,
        source_currency=source,
        base_currency=base,
        stored_source_currency=stored_source_currency,
        stored_base_currency=stored_base_currency,
        today=today,
    )
    if saved is not None:
        return saved
    reason = context.unavailable_reason or (
        f"No recent verified {source} to {base} exchange rate is available."
    )
    return None, {
        "status": "unavailable",
        "provider": FX_PROVIDER,
        "source_url": FRANKFURTER_RATES_URL,
        "as_of": None,
        "age_days": None,
        "stale": None,
        "rate": None,
        "source_currency": source,
        "base_currency": base,
        "unavailable_reason": reason,
        "privacy": "Only currency codes are sent; values and holdings stay local.",
    }


def _money_value(*values: Any) -> Decimal:
    total = Decimal("1")
    for value in values:
        total *= Decimal(str(value))
    return money_decimal(total)


def _unavailable_value(
    *,
    source: str,
    source_url: str | None,
    valued_at: date | None,
    expires_on: date | None,
    stale: bool,
    provenance: str,
    reason: str,
    base_currency: str,
    native_value: float | None,
    conversion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "value_base": None,
        "native_value": native_value,
        "exchange_rate_to_base": None,
        "base_currency": base_currency,
        "source": source,
        "source_url": source_url,
        "valued_at": valued_at.isoformat() if valued_at else None,
        "expires_on": expires_on.isoformat() if expires_on else None,
        "stale": stale,
        "available": False,
        "unavailable_reason": reason,
        "provenance": provenance,
        "conversion": conversion,
        "calculation_version": CALCULATION_VERSION,
    }


def item_value(
    item: NetWorthItem,
    *,
    context: NetWorthValuationContext,
    latest_quote: NetWorthQuote | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    reference_day = today or date.today()
    now = utcnow_naive()
    if item.valuation_mode == "market":
        quote = latest_quote
        if quote is None:
            return _unavailable_value(
                source="No saved market quote",
                source_url=None,
                valued_at=None,
                expires_on=None,
                stale=True,
                provenance="market_quote",
                reason="Refresh this item to obtain a verified market quote.",
                base_currency=context.base_currency,
                native_value=None,
            )
        native_value = _money_value(quote.unit_price, item.quantity)
        common = {
            "source": quote.source,
            "source_url": quote.source_url,
            "valued_at": quote.quoted_at.date(),
            "expires_on": quote.expires_at.date(),
            "provenance": "market_quote",
            "base_currency": context.base_currency,
            "native_value": native_value,
        }
        if quote.quote_currency != item.currency:
            return _unavailable_value(
                **common,
                stale=True,
                reason=(
                    f"The saved quote is in {quote.quote_currency}, but this item is "
                    f"configured as {item.currency}. Refresh after correcting the currency."
                ),
            )
        if quote.expires_at < now:
            return _unavailable_value(
                **common,
                stale=True,
                reason="The saved market quote has expired. Refresh it before using totals.",
            )
        if quote.base_currency != context.base_currency:
            return _unavailable_value(
                **common,
                stale=True,
                reason=(
                    f"This quote was saved for {quote.base_currency}. Refresh it after "
                    f"the base-currency change to {context.base_currency}."
                ),
            )
        rate, conversion = _conversion(
            quote,
            source_currency=quote.quote_currency,
            stored_source_currency=quote.quote_currency,
            stored_base_currency=quote.base_currency,
            context=context,
            today=reference_day,
        )
        if rate is None:
            return _unavailable_value(
                **common,
                stale=True,
                reason=conversion["unavailable_reason"],
                conversion=conversion,
            )
        value = _money_value(
            quote.unit_price,
            item.quantity,
            rate,
        )
        return {
            "value_base": value,
            "native_value": native_value,
            "exchange_rate_to_base": rate,
            "base_currency": context.base_currency,
            "source": quote.source,
            "source_url": quote.source_url,
            "valued_at": quote.quoted_at.date().isoformat(),
            "expires_on": quote.expires_at.date().isoformat(),
            "stale": bool(conversion["stale"]),
            "available": True,
            "unavailable_reason": None,
            "provenance": "market_quote",
            "conversion": conversion,
            "calculation_version": CALCULATION_VERSION,
        }

    native_value = item.manual_value
    source = item.valuation_source or "Manual valuation"
    stale = item.expires_on is not None and item.expires_on < reference_day
    if native_value is None:
        return _unavailable_value(
            source=source,
            source_url=item.source_url,
            valued_at=item.valued_at,
            expires_on=item.expires_on,
            stale=stale,
            provenance="manual",
            reason="Add a manual value before using this item in totals.",
            base_currency=context.base_currency,
            native_value=None,
        )
    rate, conversion = _conversion(
        item,
        source_currency=item.currency,
        stored_source_currency=item.fx_source_currency,
        stored_base_currency=item.fx_base_currency,
        context=context,
        today=reference_day,
    )
    if rate is None:
        return _unavailable_value(
            source=source,
            source_url=item.source_url,
            valued_at=item.valued_at,
            expires_on=item.expires_on,
            stale=stale,
            provenance="manual",
            reason=conversion["unavailable_reason"],
            base_currency=context.base_currency,
            native_value=native_value,
            conversion=conversion,
        )
    return {
        "value_base": _money_value(native_value, rate),
        "native_value": native_value,
        "exchange_rate_to_base": rate,
        "base_currency": context.base_currency,
        "source": source,
        "source_url": item.source_url,
        "valued_at": item.valued_at.isoformat() if item.valued_at else None,
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "stale": stale or bool(conversion["stale"]),
        "available": True,
        "unavailable_reason": None,
        "provenance": "manual",
        "conversion": conversion,
        "calculation_version": CALCULATION_VERSION,
    }


def serialize_item(
    item: NetWorthItem,
    *,
    db: Session,
    context: NetWorthValuationContext,
    latest_quote: NetWorthQuote | None = None,
    include_history: bool = False,
) -> dict[str, Any]:
    if latest_quote is None and item.valuation_mode == "market":
        latest_quote = (
            db.query(NetWorthQuote)
            .filter(NetWorthQuote.item_id == item.id)
            .order_by(NetWorthQuote.quoted_at.desc(), NetWorthQuote.id.desc())
            .first()
        )
    value = item_value(item, context=context, latest_quote=latest_quote)
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
        "valuation_source": item.valuation_source,
        "source_url": item.source_url,
        "valued_at": item.valued_at.isoformat() if item.valued_at else None,
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "notes": item.notes,
        "is_active": item.is_active,
        **value,
    }
    if include_history:
        history = (
            db.query(NetWorthQuote)
            .filter(NetWorthQuote.item_id == item.id)
            .order_by(NetWorthQuote.quoted_at.desc(), NetWorthQuote.id.desc())
            .limit(100)
            .all()
        )
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
                "fx_rate_source": quote.fx_rate_source,
                "fx_rate_source_url": quote.fx_rate_source_url,
                "fx_rate_as_of": (
                    quote.fx_rate_as_of.isoformat() if quote.fx_rate_as_of else None
                ),
                "matches_current_base": quote.base_currency == context.base_currency,
                "expired": quote.expires_at < utcnow_naive(),
            }
            for quote in history
        ]
    return payload


def net_worth_summary(db: Session) -> dict[str, Any]:
    rows = _items_with_latest_quote(db)
    items = [item for item, _quote in rows]
    base_currency = get_base_currency(db)
    context = build_valuation_context(items, base_currency=base_currency)
    serialized = [
        serialize_item(
            item,
            db=db,
            context=context,
            latest_quote=quote,
        )
        for item, quote in rows
    ]
    unavailable = [item for item in serialized if not item["available"]]
    complete = not unavailable
    assets = sum(
        (
            item["value_base"]
            for item in serialized
            if item["item_type"] == "asset" and item["value_base"] is not None
        ),
        Decimal("0"),
    )
    liabilities = sum(
        (
            item["value_base"]
            for item in serialized
            if item["item_type"] == "liability" and item["value_base"] is not None
        ),
        Decimal("0"),
    )
    return {
        "base_currency": base_currency,
        "valuation_status": "complete" if complete else "incomplete",
        "total_assets": money_decimal(assets) if complete else None,
        "total_liabilities": money_decimal(liabilities) if complete else None,
        "net_worth": money_decimal(assets - liabilities) if complete else None,
        "stale_count": sum(bool(item["stale"]) for item in serialized),
        "unavailable_item_count": len(unavailable),
        "valued_item_count": len(serialized) - len(unavailable),
        "item_count": len(serialized),
        "items": serialized,
        "fx": context.metadata(),
        "calculation_version": CALCULATION_VERSION,
        "provenance": (
            "Calculated locally as assets minus liabilities from native values, "
            "fresh market quotes, and verified currency rates. If any active item "
            "cannot be valued safely, all headline totals are hidden."
        ),
    }


def liquid_asset_total(db: Session) -> float | None:
    rows = _items_with_latest_quote(db, liquid_only=True)
    items = [item for item, _quote in rows]
    context = build_valuation_context(items, base_currency=get_base_currency(db))
    values = [
        item_value(item, context=context, latest_quote=quote) for item, quote in rows
    ]
    if any(not value["available"] for value in values):
        return None
    total = sum((value["value_base"] for value in values), Decimal("0"))
    return float(money_decimal(total))
