"""Shared validation contracts for financial API inputs.

Persistence still uses legacy SQLite ``REAL`` columns.  These request types
therefore guard the existing boundary against non-finite and unreasonable
values without pretending to complete the separate exact-money migration.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field


MAX_FINANCIAL_VALUE = 1_000_000_000_000_000.0
MAX_EXCHANGE_RATE = 1_000_000_000.0

PositiveMoney = Annotated[
    float,
    Field(
        strict=True,
        gt=0,
        le=MAX_FINANCIAL_VALUE,
        allow_inf_nan=False,
    ),
]
NonNegativeMoney = Annotated[
    float,
    Field(
        strict=True,
        ge=0,
        le=MAX_FINANCIAL_VALUE,
        allow_inf_nan=False,
    ),
]
PositiveFiniteNumber = Annotated[
    float,
    Field(
        strict=True,
        gt=0,
        le=MAX_FINANCIAL_VALUE,
        allow_inf_nan=False,
    ),
]
PositiveExchangeRate = Annotated[
    float,
    Field(
        strict=True,
        gt=0,
        le=MAX_EXCHANGE_RATE,
        allow_inf_nan=False,
    ),
]
FiniteUnitInterval = Annotated[
    float,
    Field(strict=True, ge=0, le=1, allow_inf_nan=False),
]
ExpectedAnnualReturnRate = Annotated[
    float,
    Field(strict=True, ge=0, le=0.5, allow_inf_nan=False),
]

SubscriptionFrequency = Literal["monthly", "quarterly", "annual"]
IncomeFrequency = Literal["monthly", "quarterly", "annual", "one_time"]
LegacyIncomeFrequency = Literal["monthly", "biweekly", "irregular"]
GoalPressureLevel = Literal["minimal", "moderate", "aggressive"]
GoalContributionType = Literal["deposit", "withdrawal"]
SubscriptionDecision = Literal["confirm", "ignore", "snooze"]
TransactionType = Literal["debit", "credit"]
ManualTransactionInstrument = Literal[
    "manual",
    "cash",
    "bank",
    "upi",
    "debit_card",
    "credit_card",
    "rupay_credit_upi",
    "statement",
    "savings_account",
    "net_banking",
    "cheque",
    "wallet",
    "other",
]
ChatRole = Literal["user", "assistant"]
NetWorthItemType = Literal["asset", "liability"]
NetWorthValuationMode = Literal["manual", "market"]
NetWorthAssetClass = Literal[
    "cash",
    "stock",
    "etf",
    "mutual_fund",
    "crypto",
    "bond",
    "metal",
    "property",
    "land",
    "gem",
    "private_asset",
    "debt",
    "other",
]


def _normalize_upper(value):
    return value.strip().upper() if isinstance(value, str) else value


SupportedSubscriptionCurrency = Annotated[
    Literal["INR", "USD", "EUR", "GBP"],
    BeforeValidator(_normalize_upper),
]

# Current Currency & Funds codes from the ISO 4217 Maintenance Agency (SIX),
# snapshot 2026-08-02. BGN is intentionally absent after Bulgaria adopted EUR
# on 2026-01-01. Keep the source beside the allowlist so updates are auditable.
ISO_4217_SOURCE = (
    "https://www.six-group.com/dam/download/financial-information/"
    "data-center/iso-currrency/lists/list-one.xml"
)
ISO_4217_CODES = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV
    BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP
    CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF
    GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR
    KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT
    MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN
    PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE
    SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX
    USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC
    XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG
    """.split()
)


def _validate_iso_currency(value: str) -> str:
    if value not in ISO_4217_CODES:
        raise ValueError("Currency must be a current ISO 4217 code")
    return value


CurrencyCode = Annotated[
    str,
    BeforeValidator(_normalize_upper),
    Field(pattern=r"^[A-Z]{3}$"),
    AfterValidator(_validate_iso_currency),
]


def _validate_year_month(value: str) -> str:
    year_text, month_text = value.split("-")
    year = int(year_text)
    month = int(month_text)
    if not 1900 <= year <= 2200 or not 1 <= month <= 12:
        raise ValueError("Month must be a real calendar month between 1900 and 2200")
    return value


YearMonth = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}$"),
    AfterValidator(_validate_year_month),
]


def _not_in_future(value: date) -> date:
    if value > date.today():
        raise ValueError("Date cannot be in the future")
    return value


PastOrTodayDate = Annotated[date, AfterValidator(_not_in_future)]


def require_positive_finite(
    value: float,
    *,
    field_name: str,
    maximum: float = MAX_FINANCIAL_VALUE,
) -> float:
    """Validate numeric values returned by external providers before storage."""
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > maximum:
        raise ValueError(f"{field_name} must be finite, positive, and within range")
    return number


def reject_explicit_nulls(model, field_names: set[str]):
    """Reject JSON null for required fields in partial-update models."""
    invalid = sorted(
        field_name
        for field_name in field_names & model.model_fields_set
        if getattr(model, field_name) is None
    )
    if invalid:
        raise ValueError(f"{', '.join(invalid)} cannot be null")
    return model
