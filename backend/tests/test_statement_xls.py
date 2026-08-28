from __future__ import annotations

from datetime import date

import xlrd

from app.core import statement_parser


class _SyntheticSheet:
    def __init__(self, rows: list[list[xlrd.sheet.Cell]]):
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(row) for row in rows)

    def cell(self, row: int, column: int) -> xlrd.sheet.Cell:
        if column >= len(self._rows[row]):
            return xlrd.sheet.Cell(xlrd.XL_CELL_EMPTY, "")
        return self._rows[row][column]

    def cell_value(self, row: int, column: int):
        return self.cell(row, column).value


class _SyntheticWorkbook:
    datemode = 0

    def __init__(self, sheet: _SyntheticSheet):
        self._sheet = sheet

    def sheet_by_index(self, index: int) -> _SyntheticSheet:
        assert index == 0
        return self._sheet


def _text(value: str) -> xlrd.sheet.Cell:
    return xlrd.sheet.Cell(xlrd.XL_CELL_TEXT, value)


def _number(value: float) -> xlrd.sheet.Cell:
    return xlrd.sheet.Cell(xlrd.XL_CELL_NUMBER, value)


def _date_cell(value: date) -> xlrd.sheet.Cell:
    serial = (value - date(1899, 12, 30)).days
    return xlrd.sheet.Cell(xlrd.XL_CELL_DATE, float(serial))


def test_hdfc_legacy_xls_converts_serial_dates_and_verifies_controls(monkeypatch):
    blank = _text("")
    rows = [
        [_text("HDFC BANK"), blank, blank, blank, blank, blank, blank],
        [_text("Account No."), _text("5010000000002468"), blank, blank, blank, blank, blank],
        [_text("Statement From : 01/01/2026 To : 02/01/2026"), blank, blank, blank, blank, blank, blank],
        [
            _text("Date"),
            _text("Narration"),
            _text("Chq./Ref.No."),
            _text("Value Dt"),
            _text("Withdrawal Amt."),
            _text("Deposit Amt."),
            _text("Closing Balance"),
        ],
        [
            _date_cell(date(2026, 1, 1)),
            _text("NEFT CR-EMPLOYER-SALARY"),
            _text("REF00001"),
            _date_cell(date(2026, 1, 1)),
            blank,
            _number(100.0),
            _number(1100.0),
        ],
        [
            _date_cell(date(2026, 1, 2)),
            _text("SYNTHETIC STORE"),
            _text("REF00002"),
            _date_cell(date(2026, 1, 2)),
            _number(25.0),
            blank,
            _text("1,075.00"),
        ],
        [_text("********"), blank, blank, blank, blank, blank, blank],
    ]
    workbook = _SyntheticWorkbook(_SyntheticSheet(rows))
    monkeypatch.setattr(
        statement_parser.xlrd,
        "open_workbook",
        lambda **_kwargs: workbook,
    )

    result = statement_parser.parse_statement_xls(b"synthetic-xls")

    assert result.errors == []
    assert result.recognized is True
    assert result.reconciliation_status == "passed"
    assert result.account_last4 == "2468"
    assert result.period_start == date(2026, 1, 1)
    assert result.period_end == date(2026, 1, 2)
    assert result.opening_balance == 1000.0
    assert result.closing_balance == 1075.0
    assert len(result.transactions) == 2
    assert [item.date for item in result.transactions] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
    ]
    assert [item.value_date for item in result.transactions] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
    ]


def test_hdfc_billpay_narration_keeps_target_card_hint_private():
    parsed = statement_parser.parse_statement_narration(
        "IB BILLPAY DR-HDFC4U-123456XXXXXX2468"
    )

    assert parsed["is_transfer"] is True
    assert parsed["semantic_type"] == "internal_transfer"
    assert parsed["counterparty_candidate"] == "credit_card_last4:2468"
    assert parsed["merchant_name"] == "HDFC Credit Card Payment"
