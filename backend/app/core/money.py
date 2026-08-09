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
from sqlalchemy.types import TypeDecorator

MONEY_SCALE = 100
MONEY_QUANTUM = Decimal("0.01")
MAX_MONEY = Decimal("1000000000000000.00")
MAX_MONEY_MINOR = int(MAX_MONEY * MONEY_SCALE)


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
