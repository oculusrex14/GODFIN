"""Independent golden-ledger calculator.

This module intentionally imports only the Python standard library. It does not
reuse GODFIN models, queries, semantic predicates, money helpers, or report code.
That separation makes it a genuine acceptance oracle rather than another view
of the production calculation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")
MONTHLY_DIVISORS = {
    "monthly": Decimal("1"),
    "quarterly": Decimal("3"),
    "annual": Decimal("12"),
}


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _month_bounds(month: str) -> tuple[date, date]:
    year, month_number = (int(part) for part in month.split("-"))
    start = date(year, month_number, 1)
    end = (
        date(year + 1, 1, 1)
        if month_number == 12
        else date(year, month_number + 1, 1)
    )
    return start, end


def _applies_to_month(source: dict, start: date, end: date) -> bool:
    effective_from = date.fromisoformat(source["effective_from"])
    effective_to = (
        date.fromisoformat(source["effective_to"])
        if source.get("effective_to")
        else None
    )
    if effective_from >= end or (effective_to and effective_to < start):
        return False
    frequency = source["frequency"]
    offset = (start.year - effective_from.year) * 12 + start.month - effective_from.month
    if frequency == "monthly":
        return True
    if frequency == "quarterly":
        return offset >= 0 and offset % 3 == 0
    if frequency == "annual":
        return offset >= 0 and offset % 12 == 0
    expected = date.fromisoformat(
        source.get("next_expected_date") or source["effective_from"]
    )
    return start <= expected < end


def calculate_expected(fixture: dict) -> dict:
    month_start, month_end = _month_bounds(fixture["month"])
    month_rows = [
        row
        for row in fixture["transactions"]
        if month_start <= date.fromisoformat(row["date"]) < month_end
    ]
    active_rows = [row for row in month_rows if row["role"] != "excluded"]
    month_income = sum(
        (_money(row["amount"]) for row in month_rows if row["role"] == "verified_income"),
        Decimal("0.00"),
    )
    month_spend = sum(
        (_money(row["amount"]) for row in month_rows if row["role"] == "spend"),
        Decimal("0.00"),
    )
    savings_rate = (
        ((month_income - month_spend) / month_income * Decimal("100")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        if month_income
        else None
    )

    fy_start = date(fixture["financial_year_start"], 4, 1)
    fy_end = date(fixture["financial_year_start"] + 1, 4, 1)
    fy_rows = [
        row
        for row in fixture["transactions"]
        if fy_start <= date.fromisoformat(row["date"]) < fy_end
        and row.get("status", "settled") != "deleted"
    ]
    fy_income = sum(
        (_money(row["amount"]) for row in fy_rows if row["role"] == "verified_income"),
        Decimal("0.00"),
    )
    fy_spend = sum(
        (_money(row["amount"]) for row in fy_rows if row["role"] == "spend"),
        Decimal("0.00"),
    )

    def expected_sources(month: str) -> Decimal:
        start, end = _month_bounds(month)
        return sum(
            (
                _money(source["amount"])
                for source in fixture["income_sources"]
                if _applies_to_month(source, start, end)
            ),
            Decimal("0.00"),
        )

    subscription_monthly = sum(
        (
            _money(subscription["amount"])
            * _money(subscription["fx_to_inr"])
            / MONTHLY_DIVISORS[subscription["frequency"]]
            for subscription in fixture["subscriptions"]
        ),
        Decimal("0.00"),
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    goal_balance = sum(
        (_money(entry["amount"]) for entry in fixture["goal"]["entries"]),
        Decimal("0.00"),
    )

    assets = Decimal("0.00")
    liabilities = Decimal("0.00")
    for item in fixture["net_worth"]:
        if item["valuation_mode"] == "manual":
            value = _money(item["native_value"]) * _money(item["fx_to_base"])
        else:
            value = (
                Decimal(item["quantity"])
                * Decimal(item["unit_price"])
                * Decimal(item["fx_to_base"])
            )
        value = value.quantize(CENT, rounding=ROUND_HALF_UP)
        if item["item_type"] == "asset":
            assets += value
        else:
            liabilities += value

    return {
        "month": {
            "income": month_income,
            "spend": month_spend,
            "net": month_income - month_spend,
            "savings_rate": savings_rate,
            "spending_count": sum(row["role"] == "spend" for row in month_rows),
            "listed_transaction_count": len(month_rows),
            "active_transaction_count": len(active_rows),
        },
        "financial_year": {
            "income": fy_income,
            "spend": fy_spend,
            "transaction_count": len(fy_rows),
        },
        "income_sources": {
            "july_expected": expected_sources("2026-07"),
            "august_expected": expected_sources("2026-08"),
            "source_count": len(fixture["income_sources"]),
        },
        "subscriptions": {
            "monthly": subscription_monthly,
            "annual": subscription_monthly * Decimal("12"),
            "active_count": len(fixture["subscriptions"]),
        },
        "goal": {
            "balance": goal_balance,
            "entry_count": len(fixture["goal"]["entries"]),
        },
        "net_worth": {
            "assets": assets,
            "liabilities": liabilities,
            "net": assets - liabilities,
            "item_count": len(fixture["net_worth"]),
        },
        "audit": {
            "period": fixture["month"],
            "status": "finalized",
            "locked_transaction_count": len(month_rows),
        },
    }


def normalize_expected(value):
    """Convert Decimal output into JSON-comparable strings without floats."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: normalize_expected(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_expected(item) for item in value]
    return value
