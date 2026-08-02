from __future__ import annotations

from datetime import date

import pytest

from app.core.parsers.hdfc_savings import _amount_value
from app.core.statement_parser import (
    StatementParseResult,
    _parse_amount,
    _parse_statement_date,
    _process_cc_table,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("₹ 1,23,456.78", 123456.78),
        ("INR 1,234.50", 1234.50),
        ("-1,234.50", -1234.50),
        ("(1,23,456.78)", -123456.78),
        ("+350.00", 350.00),
    ],
)
def test_amount_parser_preserves_supported_value_semantics(raw, expected):
    assert _parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "12,34,56.78",
        "1.234,50",
        "1,234.5.0",
        "100 CR DR",
        "--100.00",
        "NaN",
        "Infinity",
    ],
)
def test_amount_parser_rejects_ambiguous_or_malformed_values(raw):
    assert _parse_amount(raw) is None


def test_spreadsheet_amount_parser_uses_the_same_strict_semantics():
    assert _amount_value("1,23,456.78") == 123456.78
    assert _amount_value("12,34,56.78") is None
    assert _amount_value("(500.00)") == -500.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("31 Jul 2026", date(2026, 7, 31)),
        ("31-Jul-2026", date(2026, 7, 31)),
        ("31.07.2026", date(2026, 7, 31)),
        ("31 JUL 26", date(2026, 7, 31)),
    ],
)
def test_statement_date_accepts_strict_common_hdfc_formats(raw, expected):
    assert _parse_statement_date(raw) == expected


def _credit_card_row(
    amount: str,
    *,
    description: str = "SYNTHETIC MERCHANT",
    direction: str | None = None,
) -> StatementParseResult:
    header = ["Date", "Transaction Description", "Amount"]
    row = ["31/07/2026", description, amount]
    if direction is not None:
        header.append("Debit/Credit")
        row.append(direction)
    result = StatementParseResult(
        statement_type="hdfc_credit_card",
        recognized=True,
    )
    _process_cc_table([header, row], result, table_label="synthetic table")
    return result


@pytest.mark.parametrize(
    ("raw", "expected_type", "expected_amount"),
    [
        ("1,23,456.78 Cr", "credit", 123456.78),
        ("1,234.50Cr", "credit", 1234.50),
        ("1,234.50 DR", "debit", 1234.50),
        ("-1,234.50", "credit", 1234.50),
        ("(1,234.50)", "credit", 1234.50),
        ("+1,234.50", "debit", 1234.50),
    ],
)
def test_credit_card_amount_semantics_are_preserved(
    raw,
    expected_type,
    expected_amount,
):
    result = _credit_card_row(raw)

    assert result.errors == []
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_type == expected_type
    assert result.transactions[0].amount == expected_amount


def test_credit_card_explicit_direction_column_is_honored():
    result = _credit_card_row("1,234.50", direction="Credit")

    assert result.errors == []
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_type == "credit"


def test_credit_card_conflicting_direction_markers_fail_closed():
    result = _credit_card_row("-1,234.50 DR")

    assert result.transactions == []
    assert any("conflicting" in error.lower() for error in result.errors)


def test_credit_card_description_never_changes_amount_direction():
    result = _credit_card_row("500.00", description="CRISIL SYNTHETIC SHOP")

    assert result.errors == []
    assert result.transactions[0].txn_type == "debit"


def test_credit_card_invalid_digit_grouping_fails_closed():
    result = _credit_card_row("12,34,56.78")

    assert result.transactions == []
    assert any("invalid amount" in error.lower() for error in result.errors)
