from __future__ import annotations

from app.core.parsers.certified_savings_pdf import (
    _KOTAK_LAYOUT,
    _append_columnar_transactions,
    _collect_columnar_words,
)
from app.core.statement_parser import StatementParseResult, _validate_savings_controls


class _Table:
    def __init__(self, top, bottom, rows):
        self.bbox = (0.0, float(top), 70.0, float(bottom))
        row_height = (bottom - top) / len(rows)
        self.cells = [
            (
                float(column * 10),
                float(top + row * row_height),
                float((column + 1) * 10),
                float(top + (row + 1) * row_height),
            )
            for row in range(len(rows))
            for column in range(7)
        ]
        self._rows = rows

    def extract(self):
        return self._rows


def _word(text, x0, top):
    return {
        "text": text,
        "x0": float(x0),
        "x1": float(x0 + 2),
        "top": float(top),
        "bottom": float(top + 2),
    }


class _Page:
    height = 100

    def __init__(self):
        self._tables = [
            _Table(
                0,
                30,
                [
                    [
                        "#",
                        "Date",
                        "Description",
                        "Chq/Ref",
                        "Withdrawal",
                        "Deposit",
                        "Balance",
                    ],
                    ["1", "01 Jul 2026", "SYNTHETIC ONE", "REF1", "100", "", "900"],
                ],
            ),
            _Table(
                40,
                60,
                [["2", "02 Jul 2026", "SYNTHETIC TWO", "REF2", "50", "", "850"]],
            ),
        ]
        self._words = [
            _word("01", 11, 17),
            _word("Jul", 14, 17),
            _word("2026", 17, 17),
            _word("SYNTHETIC", 21, 17),
            _word("ONE", 24, 17),
            _word("REF1", 31, 17),
            _word("100.00", 41, 17),
            _word("900.00", 61, 17),
            _word("02", 11, 47),
            _word("Jul", 14, 47),
            _word("2026", 17, 47),
            _word("SYNTHETIC", 21, 47),
            _word("TWO", 24, 47),
            _word("REF2", 31, 47),
            _word("50.00", 41, 47),
            _word("850.00", 61, 47),
        ]

    def find_tables(self):
        return self._tables

    def extract_words(self, **_kwargs):
        return self._words


class _Document:
    pages = [_Page()]


def test_split_headerless_table_segment_is_not_silently_dropped():
    columns = _collect_columnar_words(
        _Document(),
        column_count=7,
        header_tokens=("DATE", "DESCRIPTION", "WITHDRAWAL", "DEPOSIT", "BALANCE"),
        allow_headerless_continuations=True,
    )
    result = StatementParseResult(recognized=True)

    controls = _append_columnar_transactions(
        result,
        columns,
        _KOTAK_LAYOUT,
        bank="kotak",
        source_format_version="synthetic",
        parser_version="synthetic",
    )
    _validate_savings_controls(result)

    assert controls.transaction_count == 2
    assert result.errors == []
    assert result.reconciliation_status == "passed"
    assert [(row.txn_type, row.amount) for row in result.transactions] == [
        ("debit", 100),
        ("debit", 50),
    ]
