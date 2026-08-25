from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.v1.entitlements import require_entitlement
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import IntegrationUnavailableError
from app.core.encryption import SecretDecryptionError, decrypt, encrypt
from app.core.fx import FxRateUnavailable, get_inr_rates
from app.core.money import (
    FX_RATE_SCALE,
    MAX_EXACT_FX_RATE,
    MAX_UNIT_PRICE,
    UNIT_PRICE_SCALE,
    money_decimal,
    scaled_decimal,
)
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
    NetWorthMoney,
    NetWorthQuantity,
    NetWorthValuationMode,
    SupportedSubscriptionCurrency,
    reject_explicit_nulls,
)

router = APIRouter()
NET_WORTH_ENTITLEMENT = require_entitlement(
    "net_worth",
    "net_worth",
    "Net Worth is not available in this build.",
)
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
    quantity: NetWorthQuantity = Decimal("1")
    currency: CurrencyCode = "INR"
    manual_value: NetWorthMoney | None = None
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
    quantity: NetWorthQuantity | None = None
    currency: CurrencyCode | None = None
    manual_value: NetWorthMoney | None = None
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


class RecoverableNetWorthDeletion(BaseModel):
    id: str
    status: Literal["deleted", "restored"]
    affected_records: int
    deleted_at: str | None
    recovery: str


class MarketDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=200)
    base_currency: SupportedSubscriptionCurrency = "INR"


class ItemConversionResponse(BaseModel):
    status: str
    provider: str
    source_url: str | None
    as_of: str | None
    age_days: int | None
    stale: bool | None
    rate: float | None
    source_currency: str
    base_currency: str
    unavailable_reason: str | None
    privacy: str


class NetWorthQuoteResponse(BaseModel):
    id: str
    unit_price: float
    quote_currency: str
    exchange_rate_to_base: float
    total_value_base: float
    base_currency: str
    source: str
    source_url: str | None
    quoted_at: str
    expires_at: str
    fx_rate_source: str | None
    fx_rate_source_url: str | None
    fx_rate_as_of: str | None
    matches_current_base: bool
    expired: bool


class NetWorthItemResponse(BaseModel):
    id: str
    name: str
    item_type: str
    asset_class: str
    valuation_mode: str
    symbol: str | None
    quantity: float
    currency: str
    manual_value: float | None
    valuation_source: str | None
    source_url: str | None
    valued_at: str | None
    expires_on: str | None
    notes: str | None
    is_active: bool
    value_base: float | None
    native_value: float | None
    exchange_rate_to_base: float | None
    base_currency: str
    source: str
    stale: bool
    available: bool
    unavailable_reason: str | None
    provenance: str
    conversion: ItemConversionResponse | None
    calculation_version: str
    quote_history: list[NetWorthQuoteResponse] | None = None


class FxSummaryResponse(BaseModel):
    status: str
    provider: str
    source_url: str | None
    as_of: str | None
    age_days: int | None
    stale: bool | None
    rate_direction: str
    rates_to_inr: dict[str, float]
    rate_dates: dict[str, str]
    requested_currencies: list[str]
    privacy: str
    unavailable_reason: str | None


class NetWorthSummaryResponse(BaseModel):
    base_currency: str
    valuation_status: str
    total_assets: float | None
    total_liabilities: float | None
    net_worth: float | None
    stale_count: int
    unavailable_item_count: int
    valued_item_count: int
    item_count: int
    items: list[NetWorthItemResponse]
    fx: FxSummaryResponse
    calculation_version: str
    provenance: str


class MarketDataStatusResponse(BaseModel):
    provider: str
    configured: bool
    base_currency: str
    supported_base_currencies: list[str]
    currency_rate_provider: str
    key_storage: str
    privacy: str


class ManualRateRefreshResponse(BaseModel):
    updated_items: int
    total_manual_items: int
    fx: FxSummaryResponse


class MarketDataUpdateResponse(BaseModel):
    provider: str
    configured: bool
    base_currency: str
    supported_base_currencies: list[str]
    key_storage: str
    base_currency_changed: bool
    quotes_requiring_refresh: int
    conversion_refresh: ManualRateRefreshResponse


def _validate_item_payload(
    *,
    valuation_mode: str,
    asset_class: str,
    symbol: str | None,
    manual_value: Decimal | None,
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


@router.get(
    "",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=NetWorthSummaryResponse,
)
def summary(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return net_worth_summary(db)


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=NetWorthItemResponse,
    response_model_exclude_unset=True,
)
def create_item(
    body: NetWorthItemCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
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


@router.get(
    "/{item_id}",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=NetWorthItemResponse,
    response_model_exclude_unset=True,
)
def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    item = db.query(NetWorthItem).filter_by(id=item_id, deleted_at=None).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    context = build_valuation_context(
        [item],
        base_currency=get_base_currency(db),
    )
    return serialize_item(item, db=db, context=context, include_history=True)


@router.put(
    "/{item_id}",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=NetWorthItemResponse,
    response_model_exclude_unset=True,
)
def update_item(
    item_id: str,
    body: NetWorthItemUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    item = db.query(NetWorthItem).filter_by(id=item_id, deleted_at=None).first()
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


@router.delete(
    "/{item_id}",
    response_model=RecoverableNetWorthDeletion,
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    item = db.query(NetWorthItem).filter_by(id=item_id, deleted_at=None).first()
    if not item:
        raise HTTPException(status_code=404, detail="Net-worth item not found.")
    affected_records = 1 + len(item.quotes)
    item.deleted_at = utcnow_naive()
    db.commit()
    return RecoverableNetWorthDeletion(
        id=item.id,
        status="deleted",
        affected_records=affected_records,
        deleted_at=item.deleted_at.isoformat(),
        recovery="Use Undo to restore this item and its quote history.",
    )


@router.post(
    "/{item_id}/restore",
    response_model=RecoverableNetWorthDeletion,
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
)
def restore_item(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    item = db.query(NetWorthItem).filter(
        NetWorthItem.id == item_id,
        NetWorthItem.deleted_at.is_not(None),
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Deleted net-worth item not found.")
    affected_records = 1 + len(item.quotes)
    item.deleted_at = None
    db.commit()
    return RecoverableNetWorthDeletion(
        id=item.id,
        status="restored",
        affected_records=affected_records,
        deleted_at=None,
        recovery="The item and its quote history are visible again.",
    )


@router.get(
    "/market-data/config/status",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=MarketDataStatusResponse,
)
def market_data_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
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


@router.put(
    "/market-data/config",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=MarketDataUpdateResponse,
)
def configure_market_data(
    body: MarketDataConfig,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
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
                NetWorthItem.deleted_at.is_(None),
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


@router.post(
    "/{item_id}/refresh",
    dependencies=[Depends(NET_WORTH_ENTITLEMENT)],
    response_model=NetWorthItemResponse,
    response_model_exclude_unset=True,
)
def refresh_quote(
    item_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    item = db.query(NetWorthItem).filter_by(id=item_id, deleted_at=None).first()
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
            unit_price = scaled_decimal(
                unit_price_value,
                scale=UNIT_PRICE_SCALE,
                minimum=Decimal("0.00000001"),
                maximum=MAX_UNIT_PRICE,
                field_name="Quote price",
            )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise IntegrationUnavailableError(
            code="MARKET_QUOTE_UNAVAILABLE",
            message="A verified market quote is temporarily unavailable.",
            hint="Check the symbol and market-data key, then try again.",
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
        rate = scaled_decimal(
            snapshot.rate_between(quote_currency, base_currency),
            scale=FX_RATE_SCALE,
            minimum=Decimal("0.000000000001"),
            maximum=MAX_EXACT_FX_RATE,
            field_name="Exchange rate",
        )
    except (FxRateUnavailable, ValueError) as exc:
        raise IntegrationUnavailableError(
            code="MARKET_FX_UNAVAILABLE",
            message="The verified currency conversion is temporarily unavailable.",
            hint="The quote was not saved. Try again later.",
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
        total_value_base=money_decimal(unit_price * item.quantity * rate),
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
