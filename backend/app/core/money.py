"""Exact fixed-point helpers for authoritative local money values.

SQLite has no native fixed-scale decimal storage. GODFIN therefore stores
authoritative currency amounts as integer minor units and exposes Decimal
major-unit values to Python. Legacy REAL columns remain temporarily populated
only for downgrade/diagnostic compatibility during the private migration.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import BigInteger
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.types import TypeDecorator

MONEY_SCALE = 100
MONEY_QUANTUM = Decimal("0.01")
MAX_MONEY = Decimal("1000000000000000.00")
MAX_MONEY_MINOR = int(MAX_MONEY * MONEY_SCALE)

# Net-worth measurements need more precision than currency totals, but SQLite
# INTEGER and SQLite REAL compatibility shadows must still agree exactly.  Keep
# scaled values below 2**53 so the temporary REAL shadow can represent every
# integer unit without losing identity during private-build migrations.
EXACT_COMPATIBILITY_INTEGER_LIMIT = 9_000_000_000_000_000
QUANTITY_SCALE = 100_000_000
QUANTITY_QUANTUM = Decimal("0.00000001")
MAX_QUANTITY = Decimal("90000000.00000000")
UNIT_PRICE_SCALE = 100_000_000
UNIT_PRICE_QUANTUM = Decimal("0.00000001")
MAX_UNIT_PRICE = Decimal("90000000.00000000")
FX_RATE_SCALE = 1_000_000_000_000
FX_RATE_QUANTUM = Decimal("0.000000000001")
MAX_EXACT_FX_RATE = Decimal("9000.000000000000")
MAX_NET_WORTH_MONEY = Decimal("90000000000000.00")
MAX_NET_WORTH_MONEY_MINOR = int(MAX_NET_WORTH_MONEY * MONEY_SCALE)


class MoneyMinorUnits(TypeDecorator):
    """Store Decimal major units as exact SQLite INTEGER minor units."""

    impl = BigInteger
    cache_ok = True

    @property
    def python_type(self):
        return Decimal

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return money_to_minor(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return money_from_minor(value)


def money_decimal(value: Any) -> Decimal:
    """Normalize a finite major-unit value to two decimal places."""
    if isinstance(value, bool):
        raise ValueError("Money must be a finite number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Money must be a finite number") from exc
    if not amount.is_finite():
        raise ValueError("Money must be a finite number")
    normalized = amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if abs(normalized) > MAX_MONEY:
        raise ValueError("Money is outside GODFIN's supported range")
    return normalized


def money_to_minor(value: Any) -> int:
    """Convert a major-unit money value to exact integer minor units."""
    return int(money_decimal(value) * MONEY_SCALE)


def money_from_minor(value: int | None, legacy_value: Any = None) -> Decimal:
    """Read exact minor units, with a temporary legacy-value fallback."""
    if value is not None:
        return (Decimal(int(value)) / MONEY_SCALE).quantize(MONEY_QUANTUM)
    if legacy_value is None:
        raise ValueError("Money has no authoritative or legacy value")
    return money_decimal(legacy_value)


def set_money_columns(instance, value: Any, *, legacy_attr: str, exact_attr: str):
    """Populate exact and compatibility columns from one normalized value."""
    normalized = money_decimal(value)
    setattr(instance, legacy_attr, float(normalized))
    setattr(instance, exact_attr, normalized)


def exact_money_hybrid(legacy_attr: str, exact_attr: str):
    """Create a Decimal hybrid backed by exact and compatibility columns."""

    def getter(instance):
        exact_value = getattr(instance, exact_attr)
        if exact_value is not None:
            return money_decimal(exact_value)
        legacy_value = getattr(instance, legacy_attr)
        if legacy_value is None:
            return None
        return money_decimal(legacy_value)

    def setter(instance, value):
        if value is None:
            setattr(instance, legacy_attr, None)
            setattr(instance, exact_attr, None)
            return
        set_money_columns(
            instance,
            value,
            legacy_attr=legacy_attr,
            exact_attr=exact_attr,
        )

    def expression(owner):
        return getattr(owner, exact_attr)

    prop = hybrid_property(getter)
    prop = prop.setter(setter)
    return prop.expression(expression)


def exact_money_statement_values(table, values: dict[str, Any]) -> dict:
    """Build physical-column values for atomic Core inserts and upserts."""
    result = {}
    for field, value in values.items():
        legacy_column = table.c[field]
        exact_column = table.c[f"{field}_minor"]
        if value is None:
            result[legacy_column] = None
            result[exact_column] = None
            continue
        normalized = money_decimal(value)
        result[legacy_column] = float(normalized)
        result[exact_column] = normalized
    return result


def scaled_decimal(
    value: Any,
    *,
    scale: int,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
) -> Decimal:
    """Normalize a bounded finite value to an explicit fixed precision."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a finite number")
    quantum = Decimal(1) / Decimal(scale)
    normalized = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    if normalized < minimum or normalized > maximum:
        raise ValueError(f"{field_name} is outside GODFIN's supported range")
    return normalized


def scaled_to_units(
    value: Any,
    *,
    scale: int,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
) -> int:
    """Convert a fixed-precision major value to authoritative integer units."""
    normalized = scaled_decimal(
        value,
        scale=scale,
        minimum=minimum,
        maximum=maximum,
        field_name=field_name,
    )
    units = int(normalized * scale)
    if abs(units) > EXACT_COMPATIBILITY_INTEGER_LIMIT:
        raise ValueError(f"{field_name} is outside GODFIN's exact storage range")
    return units


def scaled_from_units(value: int, *, scale: int) -> Decimal:
    """Convert authoritative integer units back to their Decimal major value."""
    quantum = Decimal(1) / Decimal(scale)
    return (Decimal(int(value)) / Decimal(scale)).quantize(quantum)


class ScaledIntegerUnits(TypeDecorator):
    """Persist a bounded fixed-precision Decimal as a SQLite INTEGER."""

    impl = BigInteger
    cache_ok = True

    def __init__(
        self,
        *,
        scale: int,
        minimum: Decimal,
        maximum: Decimal,
        field_name: str,
    ):
        super().__init__()
        self.scale = scale
        self.minimum = minimum
        self.maximum = maximum
        self.field_name = field_name

    @property
    def python_type(self):
        return Decimal

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return scaled_to_units(
            value,
            scale=self.scale,
            minimum=self.minimum,
            maximum=self.maximum,
            field_name=self.field_name,
        )

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return scaled_from_units(value, scale=self.scale)


def set_scaled_columns(
    instance,
    value: Any,
    *,
    legacy_attr: str,
    exact_attr: str,
    scale: int,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
) -> None:
    """Populate one exact scaled column and its temporary REAL shadow."""
    normalized = scaled_decimal(
        value,
        scale=scale,
        minimum=minimum,
        maximum=maximum,
        field_name=field_name,
    )
    setattr(instance, legacy_attr, float(normalized))
    setattr(instance, exact_attr, normalized)


def exact_scaled_hybrid(
    legacy_attr: str,
    exact_attr: str,
    *,
    scale: int,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
):
    """Create a Decimal hybrid backed by scaled INTEGER and REAL columns."""

    def getter(instance):
        exact_value = getattr(instance, exact_attr)
        if exact_value is not None:
            return scaled_decimal(
                exact_value,
                scale=scale,
                minimum=minimum,
                maximum=maximum,
                field_name=field_name,
            )
        legacy_value = getattr(instance, legacy_attr)
        if legacy_value is None:
            return None
        return scaled_decimal(
            legacy_value,
            scale=scale,
            minimum=minimum,
            maximum=maximum,
            field_name=field_name,
        )

    def setter(instance, value):
        if value is None:
            setattr(instance, legacy_attr, None)
            setattr(instance, exact_attr, None)
            return
        set_scaled_columns(
            instance,
            value,
            legacy_attr=legacy_attr,
            exact_attr=exact_attr,
            scale=scale,
            minimum=minimum,
            maximum=maximum,
            field_name=field_name,
        )

    def expression(owner):
        return getattr(owner, exact_attr)

    prop = hybrid_property(getter)
    prop = prop.setter(setter)
    return prop.expression(expression)
