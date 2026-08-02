from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import httpx

from app.core.time import utcnow_naive

FRANKFURTER_RATES_URL = "https://api.frankfurter.dev/v2/rates"
FX_PROVIDER = "European Central Bank reference rates via Frankfurter"
SUPPORTED_CURRENCIES = frozenset({"INR", "USD", "EUR", "GBP"})
CACHE_TTL_SECONDS = 6 * 60 * 60
STALE_AFTER_DAYS = 4
MAX_RATE_AGE_DAYS = 10


class FxRateUnavailable(RuntimeError):
    """Raised when a safe currency conversion cannot be produced."""


@dataclass(frozen=True)
class FxRateSnapshot:
    rates_to_inr: dict[str, float]
    as_of: date
    provider: str
    source_url: str | None
    age_days: int
    stale: bool
    status: str
    rate_dates_to_inr: dict[str, date] | None = None

    def rate_to_inr(self, currency: str) -> float:
        normalized = currency.strip().upper()
        rate = self.rates_to_inr.get(normalized)
        if rate is None or not math.isfinite(rate) or rate <= 0:
            raise FxRateUnavailable(
                f"No verified {normalized} to INR exchange rate is available."
            )
        return rate

    def convert_to_inr(self, amount: float, currency: str) -> float:
        numeric_amount = float(amount)
        if not math.isfinite(numeric_amount):
            raise FxRateUnavailable("The amount cannot be converted safely.")
        return numeric_amount * self.rate_to_inr(currency)

    def metadata(self, currencies: Iterable[str] | None = None) -> dict:
        requested = sorted(
            {currency.strip().upper() for currency in (currencies or self.rates_to_inr)}
        )
        rates = {
            currency: self.rates_to_inr[currency]
            for currency in requested
            if currency in self.rates_to_inr
        }
        rate_dates = self.rate_dates_to_inr or {
            currency: self.as_of for currency in rates if currency != "INR"
        }
        return {
            "status": self.status,
            "provider": self.provider,
            "source_url": self.source_url,
            "as_of": self.as_of.isoformat(),
            "age_days": self.age_days,
            "stale": self.stale,
            "rate_direction": "INR per 1 unit of the listed currency",
            "rates_to_inr": rates,
            "rate_dates": {
                currency: value.isoformat()
                for currency, value in rate_dates.items()
                if currency in requested
            },
            "requested_currencies": requested,
            "privacy": "Currency codes only; no amounts or transaction data leave this computer.",
            "unavailable_reason": None,
        }


_cache: dict[frozenset[str], tuple[float, FxRateSnapshot]] = {}
_cache_lock = threading.Lock()


def clear_fx_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _normalize_currencies(currencies: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(currency.strip().upper() for currency in currencies)
    unsupported = normalized - SUPPORTED_CURRENCIES
    if unsupported:
        listed = ", ".join(sorted(unsupported))
        raise FxRateUnavailable(f"Unsupported currency: {listed}.")
    return normalized or frozenset({"INR"})


def _local_inr_snapshot(today: date) -> FxRateSnapshot:
    return FxRateSnapshot(
        rates_to_inr={"INR": 1.0},
        as_of=today,
        provider="No conversion required",
        source_url=None,
        age_days=0,
        stale=False,
        status="not_required",
    )


def _cached_snapshot(
    requested: frozenset[str], *, today: date
) -> FxRateSnapshot | None:
    now = time.monotonic()
    with _cache_lock:
        candidates = [
            (cached_at, snapshot)
            for currencies, (cached_at, snapshot) in _cache.items()
            if requested.issubset(currencies)
            and now - cached_at < CACHE_TTL_SECONDS
            and 0 <= (today - snapshot.as_of).days <= MAX_RATE_AGE_DAYS
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def get_inr_rates(
    currencies: Iterable[str],
    *,
    today: date | None = None,
    force_refresh: bool = False,
) -> FxRateSnapshot:
    """Return verified INR-per-unit rates without sending financial amounts."""

    reference_day = today or date.today()
    requested = _normalize_currencies(currencies)
    foreign = requested - {"INR"}
    if not foreign:
        return _local_inr_snapshot(reference_day)

    if not force_refresh:
        cached = _cached_snapshot(requested, today=reference_day)
        if cached is not None:
            return cached

    params = {
        "base": "INR",
        "quotes": ",".join(sorted(foreign)),
        "providers": "ECB",
    }
    try:
        response = httpx.get(
            FRANKFURTER_RATES_URL,
            params=params,
            timeout=httpx.Timeout(5.0, connect=2.0),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise FxRateUnavailable(
            "Live currency rates are temporarily unavailable. INR totals are hidden rather than estimated."
        ) from exc

    if not isinstance(payload, list) or not payload:
        raise FxRateUnavailable("The currency provider returned no usable rates.")

    rates_to_inr: dict[str, float] = {"INR": 1.0}
    provider_dates: set[date] = set()
    try:
        for row in payload:
            if not isinstance(row, dict) or row.get("base") != "INR":
                raise ValueError("unexpected base currency")
            quote = str(row.get("quote", "")).upper()
            if quote not in foreign:
                continue
            quoted_per_inr = float(row["rate"])
            if not math.isfinite(quoted_per_inr) or quoted_per_inr <= 0:
                raise ValueError("invalid rate")
            provider_dates.add(date.fromisoformat(str(row["date"])))
            rates_to_inr[quote] = 1.0 / quoted_per_inr
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FxRateUnavailable(
            "The currency provider returned an invalid rate."
        ) from exc

    missing = foreign - rates_to_inr.keys()
    if missing:
        listed = ", ".join(sorted(missing))
        raise FxRateUnavailable(f"No verified INR rate was returned for {listed}.")
    if len(provider_dates) != 1:
        raise FxRateUnavailable("The currency provider returned mismatched rate dates.")

    as_of = provider_dates.pop()
    age_days = (reference_day - as_of).days
    if age_days < 0:
        raise FxRateUnavailable("The currency provider returned a future-dated rate.")
    if age_days > MAX_RATE_AGE_DAYS:
        raise FxRateUnavailable(
            f"The latest verified currency rate is too old ({age_days} days)."
        )

    snapshot = FxRateSnapshot(
        rates_to_inr={key: rates_to_inr[key] for key in sorted(rates_to_inr)},
        as_of=as_of,
        provider=FX_PROVIDER,
        source_url=FRANKFURTER_RATES_URL,
        age_days=age_days,
        stale=age_days > STALE_AFTER_DAYS,
        status="stale" if age_days > STALE_AFTER_DAYS else "available",
        rate_dates_to_inr={currency: as_of for currency in foreign},
    )
    with _cache_lock:
        _cache[requested] = (time.monotonic(), snapshot)
    return snapshot


def unavailable_fx_metadata(reason: str, currencies: Iterable[str]) -> dict:
    return {
        "status": "unavailable",
        "provider": FX_PROVIDER,
        "source_url": FRANKFURTER_RATES_URL,
        "as_of": None,
        "age_days": None,
        "stale": None,
        "rate_direction": "INR per 1 unit of the listed currency",
        "rates_to_inr": {},
        "rate_dates": {},
        "requested_currencies": sorted(
            {currency.strip().upper() for currency in currencies}
        ),
        "privacy": "Currency codes only; no amounts or transaction data leave this computer.",
        "unavailable_reason": reason,
    }


def clear_subscription_fx(subscription) -> None:
    subscription.fx_rate_to_inr = None
    subscription.fx_rate_source = None
    subscription.fx_rate_source_url = None
    subscription.fx_rate_as_of = None
    subscription.fx_rate_fetched_at = None


def apply_snapshot_to_subscription(
    subscription,
    snapshot: FxRateSnapshot,
    *,
    fetched_at: datetime | None = None,
) -> None:
    currency = (subscription.currency or "INR").upper()
    if currency == "INR":
        clear_subscription_fx(subscription)
        return
    subscription.fx_rate_to_inr = Decimal(str(snapshot.rate_to_inr(currency)))
    subscription.fx_rate_source = snapshot.provider
    subscription.fx_rate_source_url = snapshot.source_url
    subscription.fx_rate_as_of = snapshot.as_of
    subscription.fx_rate_fetched_at = fetched_at or utcnow_naive()


def saved_subscription_snapshot(
    subscriptions: Iterable,
    *,
    today: date | None = None,
) -> FxRateSnapshot | None:
    reference_day = today or date.today()
    items = list(subscriptions)
    currencies = {(item.currency or "INR").upper() for item in items} or {"INR"}
    foreign = currencies - {"INR"}
    if not foreign:
        return _local_inr_snapshot(reference_day)

    newest_by_currency = {}
    for item in items:
        currency = (item.currency or "INR").upper()
        if currency not in foreign:
            continue
        rate = getattr(item, "fx_rate_to_inr", None)
        as_of = getattr(item, "fx_rate_as_of", None)
        source = getattr(item, "fx_rate_source", None)
        source_url = getattr(item, "fx_rate_source_url", None)
        fetched_at = getattr(item, "fx_rate_fetched_at", None)
        try:
            numeric_rate = float(rate)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            not math.isfinite(numeric_rate)
            or numeric_rate <= 0
            or not isinstance(as_of, date)
            or source != FX_PROVIDER
            or source_url != FRANKFURTER_RATES_URL
            or not isinstance(fetched_at, datetime)
        ):
            continue
        fetched_age_days = (reference_day - fetched_at.date()).days
        if (
            fetched_at.date() < as_of
            or fetched_age_days < 0
            or fetched_age_days > MAX_RATE_AGE_DAYS
        ):
            continue
        existing = newest_by_currency.get(currency)
        if existing is None or (as_of, fetched_at) > (existing[0], existing[1]):
            newest_by_currency[currency] = (as_of, fetched_at, numeric_rate)

    if foreign - newest_by_currency.keys():
        return None
    oldest_as_of = min(value[0] for value in newest_by_currency.values())
    age_days = (reference_day - oldest_as_of).days
    if age_days < 0 or age_days > MAX_RATE_AGE_DAYS:
        return None
    stale = age_days > STALE_AFTER_DAYS
    return FxRateSnapshot(
        rates_to_inr={
            "INR": 1.0,
            **{
                currency: newest_by_currency[currency][2]
                for currency in sorted(foreign)
            },
        },
        as_of=oldest_as_of,
        provider=FX_PROVIDER,
        source_url=FRANKFURTER_RATES_URL,
        age_days=age_days,
        stale=stale,
        status="stored",
        rate_dates_to_inr={
            currency: newest_by_currency[currency][0] for currency in sorted(foreign)
        },
    )
