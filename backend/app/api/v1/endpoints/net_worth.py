from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.v1.endpoints.license import enforce_feature
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.encryption import SecretDecryptionError, decrypt, encrypt
from app.core.feature_flags import FeatureDisabledError, require_feature_flag
from app.core.fx import FxRateUnavailable, get_inr_rates
from app.core.net_worth import (
    BASE_CURRENCY_KEY,
    MARKET_DATA_KEY,
    NetWorthValuationContext,
    apply_snapshot_to_item,
    build_valuation_context,
    clear_item_fx,
    get_base_currency,
    net_worth_summary,
    refresh_manual_item_rates,
    serialize_item,
)
from app.models.app_setting import AppSetting
from app.models.net_worth import NetWorthItem, NetWorthQuote
from app.core.time import utcnow_naive
from app.schemas.financial import (
    CurrencyCode,
    NetWorthAssetClass,
    NetWorthItemType,
    NetWorthValuationMode,
    NonNegativeMoney,
    PositiveFiniteNumber,
    SupportedSubscriptionCurrency,
    require_positive_finite,
    reject_explicit_nulls,
)

router = APIRouter()
TWELVE_DATA_API = "https://api.twelvedata.com"
MARKET_CLASSES = {"stock", "etf", "mutual_fund", "crypto", "bond", "metal"}
ILLQUID_CLASSES = {"property", "land", "gem", "private_asset", "other"}


class NetWorthItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    item_type: NetWorthItemType
    asset_class: NetWorthAssetClass
    valuation_mode: NetWorthValuationMode = "manual"
    symbol: str | None = Field(default=None, max_length=40)
    quantity: PositiveFiniteNumber = 1
    currency: CurrencyCode = "INR"
    manual_value: NonNegativeMoney | None = None
    valuation_source: str | None = Field(default=None, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    valued_at: date | None = None
    expires_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class NetWorthItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    item_type: NetWorthItemType | None = None
    asset_class: NetWorthAssetClass | None = None
    valuation_mode: NetWorthValuationMode | None = None
    symbol: str | None = Field(default=None, max_length=40)
    quantity: PositiveFiniteNumber | None = None
    currency: CurrencyCode | None = None
    manual_value: NonNegativeMoney | None = None
    valuation_source: str | None = Field(default=None, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    valued_at: date | None = None
    expires_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        return reject_explicit_nulls(
            self,
            {
                "name",
                "item_type",
                "asset_class",
                "valuation_mode",
                "quantity",
                "currency",
                "is_active",
            },
        )


class MarketDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=200)
    base_currency: SupportedSubscriptionCurrency = "INR"


def _authorize(db: Session) -> None:
    try:
        require_feature_flag(db, "net_worth")
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    enforce_feature(db, "net_worth")


def _validate_item_payload(
    *,
    valuation_mode: str,
    asset_class: str,
    symbol: str | None,
    manual_value: float | None,
    valuation_source: str | None,
    valued_at: date | None,
    expires_on: date | None,
) -> None:
    if valuation_mode == "market":
        if asset_class not in MARKET_CLASSES:
            raise HTTPException(
                status_code=400,
                detail="Live quotes are limited to supported liquid asset classes.",
            )
        if not symbol:
            raise HTTPException(
                status_code=400, detail="A market symbol is required for live quotes."
            )
    elif manual_value is None:
        raise HTTPException(
            status_code=400, detail="A manual valuation is required for this item."
        )
    elif asset_class in ILLQUID_CLASSES and (
        not valuation_source or not valued_at or not expires_on
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Property, land, gems, private assets, and unsupported items "
                "require a valuation source, valuation date, and review/expiry date."
            ),
        )
    if valued_at and expires_on and expires_on < valued_at:
        raise HTTPException(
            status_code=400,
            detail="The review/expiry date cannot be before the valuation date.",
        )


def _setting(db: Session, key: str) -> AppSetting | None:
    return db.query(AppSetting).filter_by(key=key).first()


def _set_setting(db: Session, key: str, value: str) -> None:
    setting = _setting(db, key)
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _prepare_item_conversion(
    item: NetWorthItem,
    *,
    base_currency: str,
    invalidate_existing: bool = False,
):
    if (
        invalidate_existing
        or item.valuation_mode != "manual"
        or item.currency == base_currency
    ):
        clear_item_fx(item)
    context = build_valuation_context([item], base_currency=base_currency)
    if (
        item.valuation_mode == "manual"
        and item.currency != base_currency
        and context.snapshot is not None
    ):
        apply_snapshot_to_item(
            item,
            context.snapshot,
            base_currency=base_currency,
        )
    return context


@router.get("")
def summary(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    return net_worth_summary(db)


@router.post("", status_code=201)
def create_item(
    body: NetWorthItemCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    _validate_item_payload(
        valuation_mode=body.valuation_mode,
        asset_class=body.asset_class,
        symbol=body.symbol,
        manual_value=body.manual_value,
        valuation_source=body.valuation_source,
        valued_at=body.valued_at,
        expires_on=body.expires_on,
    )
    values = body.model_dump()
    values["currency"] = body.currency.upper()
    values["symbol"] = body.symbol.upper().strip() if body.symbol else None
    values["asset_class"] = body.asset_class.lower().strip()
    item = NetWorthItem(**values)
    context = _prepare_item_conversion(
        item,
        base_currency=get_base_currency(db),
        invalidate_existing=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_item(item, db=db, context=context)


@router.get("/{item_id}")
def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    item = db.query(NetWorthItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    context = build_valuation_context(
        [item],
        base_currency=get_base_currency(db),
    )
    return serialize_item(item, db=db, context=context, include_history=True)


@router.put("/{item_id}")
def update_item(
    item_id: str,
    body: NetWorthItemUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    item = db.query(NetWorthItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    updates = body.model_dump(exclude_unset=True)
    previous_currency = item.currency
    previous_mode = item.valuation_mode
    projected = {
        "valuation_mode": updates.get("valuation_mode", item.valuation_mode),
        "asset_class": updates.get("asset_class", item.asset_class),
        "symbol": updates.get("symbol", item.symbol),
        "manual_value": updates.get("manual_value", item.manual_value),
        "valuation_source": updates.get("valuation_source", item.valuation_source),
        "valued_at": updates.get("valued_at", item.valued_at),
        "expires_on": updates.get("expires_on", item.expires_on),
    }
    _validate_item_payload(**projected)
    for key, value in updates.items():
        if key in {"currency", "symbol"} and value:
            value = value.upper().strip()
        if key == "asset_class" and value:
            value = value.lower().strip()
        setattr(item, key, value)
    context = _prepare_item_conversion(
        item,
        base_currency=get_base_currency(db),
        invalidate_existing=(
            item.currency != previous_currency or item.valuation_mode != previous_mode
        ),
    )
    db.commit()
    db.refresh(item)
    return serialize_item(item, db=db, context=context, include_history=True)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    item = db.query(NetWorthItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    db.delete(item)
    db.commit()


@router.get("/market-data/config/status")
def market_data_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    encrypted_key = _setting(db, MARKET_DATA_KEY)
    return {
        "provider": "Twelve Data",
        "configured": bool(encrypted_key and encrypted_key.value),
        "base_currency": get_base_currency(db),
        "supported_base_currencies": ["INR", "USD", "EUR", "GBP"],
        "currency_rate_provider": "European Central Bank reference rates via Frankfurter",
        "key_storage": "encrypted_local",
        "privacy": (
            "The key is sent only to Twelve Data when you request a quote. "
            "Currency conversion sends currency codes only to Frankfurter."
        ),
    }


@router.put("/market-data/config")
def configure_market_data(
    body: MarketDataConfig,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    previous_base = get_base_currency(db)
    new_base = body.base_currency.upper()
    _set_setting(db, BASE_CURRENCY_KEY, new_base)
    if body.api_key is not None:
        _set_setting(
            db, MARKET_DATA_KEY, encrypt(body.api_key.strip()) if body.api_key else ""
        )
    conversion_refresh = refresh_manual_item_rates(
        db,
        base_currency=new_base,
        force_refresh=previous_base != new_base,
    )
    quotes_requiring_refresh = 0
    if previous_base != new_base:
        quotes_requiring_refresh = (
            db.query(NetWorthItem)
            .filter(
                NetWorthItem.is_active.is_(True),
                NetWorthItem.valuation_mode == "market",
            )
            .count()
        )
    db.commit()
    saved_key = _setting(db, MARKET_DATA_KEY)
    return {
        "provider": "Twelve Data",
        "configured": bool(saved_key and saved_key.value),
        "base_currency": new_base,
        "supported_base_currencies": ["INR", "USD", "EUR", "GBP"],
        "key_storage": "encrypted_local",
        "base_currency_changed": previous_base != new_base,
        "quotes_requiring_refresh": quotes_requiring_refresh,
        "conversion_refresh": conversion_refresh,
    }


@router.post("/{item_id}/refresh")
def refresh_quote(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _authorize(db)
    item = db.query(NetWorthItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    _validate_item_payload(
        valuation_mode=item.valuation_mode,
        asset_class=item.asset_class,
        symbol=item.symbol,
        manual_value=item.manual_value,
        valuation_source=item.valuation_source,
        valued_at=item.valued_at,
        expires_on=item.expires_on,
    )
    if item.valuation_mode != "market":
        raise HTTPException(
            status_code=409, detail="Manual valuations do not request live quotes."
        )
    key_setting = _setting(db, MARKET_DATA_KEY)
    if not key_setting or not key_setting.value:
        raise HTTPException(
            status_code=409,
            detail="Add your Twelve Data API key before refreshing live quotes.",
        )
    try:
        api_key = decrypt(key_setting.value)
    except SecretDecryptionError as exc:
        raise HTTPException(
            status_code=409, detail="Re-enter the Twelve Data API key."
        ) from exc

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            quote_response = client.get(
                f"{TWELVE_DATA_API}/quote",
                params={"symbol": item.symbol},
                headers={"Authorization": f"apikey {api_key}"},
            )
            quote_payload = quote_response.json()
            unit_price_value = quote_payload.get("close") or quote_payload.get("price")
            quote_currency = str(quote_payload.get("currency") or "").upper().strip()
            if quote_response.status_code >= 400 or unit_price_value is None:
                raise ValueError(
                    str(quote_payload.get("message") or "Quote was unavailable.")
                )
            unit_price = require_positive_finite(
                float(unit_price_value),
                field_name="Quote price",
            )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Twelve Data quote failed: {exc}",
        ) from exc

    if not quote_currency:
        raise HTTPException(
            status_code=502,
            detail=(
                "Twelve Data did not identify the quote currency. "
                "The quote was not saved."
            ),
        )
    if quote_currency != item.currency:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Twelve Data reports {item.symbol} in {quote_currency}, but this "
                f"item is configured as {item.currency}. Correct the item currency "
                "before refreshing."
            ),
        )

    base_currency = get_base_currency(db)
    try:
        snapshot = get_inr_rates(
            {quote_currency, base_currency},
            force_refresh=quote_currency != base_currency,
        )
        rate = snapshot.rate_between(quote_currency, base_currency)
    except FxRateUnavailable as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Verified {quote_currency} to {base_currency} conversion failed: {exc}"
            ),
        ) from exc

    now = utcnow_naive()
    ttl = timedelta(hours=1 if item.asset_class == "crypto" else 24)
    if item.asset_class == "bond":
        ttl = timedelta(days=7)
    quote = NetWorthQuote(
        item_id=item.id,
        unit_price=unit_price,
        quote_currency=quote_currency,
        exchange_rate_to_base=rate,
        total_value_base=float(
            (
                Decimal(str(unit_price))
                * Decimal(str(item.quantity))
                * Decimal(str(rate))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ),
        base_currency=base_currency,
        source="Twelve Data",
        source_url="https://twelvedata.com/docs/advanced",
        fx_rate_source=snapshot.provider if quote_currency != base_currency else None,
        fx_rate_source_url=(
            snapshot.source_url if quote_currency != base_currency else None
        ),
        fx_rate_as_of=snapshot.as_of if quote_currency != base_currency else None,
        fx_rate_fetched_at=now if quote_currency != base_currency else None,
        quoted_at=now,
        expires_at=now + ttl,
    )
    db.add(quote)
    db.commit()
    db.refresh(item)
    context = NetWorthValuationContext(
        base_currency=base_currency,
        snapshot=snapshot,
        requested_currencies=frozenset({quote_currency, base_currency}),
    )
    return serialize_item(
        item,
        db=db,
        context=context,
        latest_quote=quote,
        include_history=True,
    )
