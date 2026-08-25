from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Optional

from app.core.statement_parser import (
    StatementParseResult,
    _append_strict_savings_txn,
    _parse_amount,
    _parse_statement_date,
    _validate_savings_controls,
)


@dataclass(frozen=True)
class _ColumnarLayout:
    date: int
    description: int
    reference: int
    withdrawal: int
    deposit: int
    balance: int
    value_date: Optional[int] = None


@dataclass(frozen=True)
class _SourceColumnControls:
    withdrawals: Decimal
    deposits: Decimal
    transaction_count: int


_HDFC_LAYOUT = _ColumnarLayout(
    date=0,
    description=1,
    reference=2,
    value_date=3,
    withdrawal=4,
    deposit=5,
    balance=6,
)
_KOTAK_LAYOUT = _ColumnarLayout(
    date=1,
    description=2,
    reference=3,
    withdrawal=4,
    deposit=5,
    balance=6,
)


def _column_edges(table: Any, column_count: int) -> Optional[list[float]]:
    cells = getattr(table, "cells", None) or []
    edges = sorted(
        {round(float(cell[0]), 3) for cell in cells}
        | {round(float(cell[2]), 3) for cell in cells}
    )
    return edges if len(edges) == column_count + 1 else None


def _column_for_word(word: dict[str, Any], edges: list[float]) -> int:
    x = float(word["x0"]) + 0.01
    return max(0, min(len(edges) - 2, sum(x >= edge for edge in edges[1:-1])))


def _ordered_text(words: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(
        words,
        key=lambda word: (
            float(word.get("global_top", word.get("top", 0.0))),
            float(word.get("x0", 0.0)),
        ),
    )
    return " ".join(str(word.get("text", "")).strip() for word in ordered).strip()


def _money_tokens(words: Iterable[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for word in words:
        parsed = _parse_amount(str(word.get("text", "")).strip())
        if parsed is not None:
            values.append(parsed)
    return values


def _first_date(words: Iterable[dict[str, Any]]) -> Optional[date]:
    return _parse_statement_date(_ordered_text(words))


def _table_header_index(rows: list[list[object]], required: tuple[str, ...]) -> Optional[int]:
    for index, row in enumerate(rows):
        upper = " ".join(str(cell or "") for cell in row).upper()
        if all(token in upper for token in required):
            return index
    return None


def _collect_columnar_words(
    document: Any,
    *,
    column_count: int,
    header_tokens: tuple[str, ...],
    allow_headerless_continuations: bool = False,
) -> list[list[dict[str, Any]]]:
    columns: list[list[dict[str, Any]]] = [[] for _ in range(column_count)]
    previous_edges: Optional[list[float]] = None
    for page_index, page in enumerate(document.pages):
        candidates: list[tuple[Any, list[float], Optional[int]]] = []
        for table in page.find_tables():
            edges = _column_edges(table, column_count)
            if edges is None:
                continue
            extracted = table.extract() or []
            header_index = _table_header_index(extracted, header_tokens)
            candidates.append((table, edges, header_index))
        if not candidates:
            continue

        header_candidates = [candidate for candidate in candidates if candidate[2] is not None]
        if header_candidates:
            trusted = max(
                header_candidates,
                key=lambda candidate: (
                    candidate[0].bbox[2] - candidate[0].bbox[0]
                ) * (candidate[0].bbox[3] - candidate[0].bbox[1]),
            )
            trusted_edges = trusted[1]
        elif allow_headerless_continuations and previous_edges is not None:
            trusted_edges = previous_edges
        else:
            continue

        def matches_trusted(edges: list[float]) -> bool:
            return all(
                abs(actual - expected) <= 2.0
                for actual, expected in zip(edges, trusted_edges)
            )

        selected = [
            candidate
            for candidate in candidates
            if matches_trusted(candidate[1])
            and (candidate[2] is not None or allow_headerless_continuations)
        ]
        selected.sort(key=lambda candidate: float(candidate[0].bbox[1]))
        previous_edges = trusted_edges
        page_offset = page_index * (float(page.height) + 100.0)
        page_words = page.extract_words(
            x_tolerance=1,
            y_tolerance=2,
            keep_blank_chars=False,
        )
        seen_words: set[tuple[object, ...]] = set()
        for table, edges, header_index in selected:
            if header_index is None:
                data_top = float(table.bbox[1])
            else:
                horizontal_edges = sorted(
                    {round(float(cell[1]), 3) for cell in table.cells}
                    | {round(float(cell[3]), 3) for cell in table.cells}
                )
                if len(horizontal_edges) <= header_index + 1:
                    continue
                data_top = horizontal_edges[header_index + 1]
            for source_word in page_words:
                if (
                    float(source_word["top"]) < data_top
                    or float(source_word["bottom"]) > float(table.bbox[3]) + 1.0
                    or float(source_word["x0"]) < float(table.bbox[0]) - 1.0
                    or float(source_word["x1"]) > float(table.bbox[2]) + 1.0
                ):
                    continue
                identity = (
                    source_word.get("text"),
                    round(float(source_word["x0"]), 2),
                    round(float(source_word["x1"]), 2),
                    round(float(source_word["top"]), 2),
                    round(float(source_word["bottom"]), 2),
                )
                if identity in seen_words:
                    continue
                seen_words.add(identity)
                word = dict(source_word)
                word["global_top"] = page_offset + float(source_word["top"])
                word["page_number"] = page_index + 1
                columns[_column_for_word(word, edges)].append(word)
    return columns


def _append_columnar_transactions(
    result: StatementParseResult,
    columns: list[list[dict[str, Any]]],
    layout: _ColumnarLayout,
    *,
    bank: str,
    source_format_version: str,
    parser_version: str,
) -> _SourceColumnControls:
    anchors: list[tuple[float, date, int]] = []
    date_words = sorted(
        columns[layout.date],
        key=lambda word: (float(word["global_top"]), float(word["x0"])),
    )
    cursor = 0
    while cursor < len(date_words):
        matched = False
        for width in (1, 2, 3):
            window = date_words[cursor : cursor + width]
            if len(window) != width:
                continue
            page_number = int(window[0]["page_number"])
            if any(int(word["page_number"]) != page_number for word in window):
                continue
            if float(window[-1]["global_top"]) - float(window[0]["global_top"]) > 32.0:
                continue
            transaction_date = _parse_statement_date(_ordered_text(window))
            if transaction_date is None:
                continue
            anchors.append(
                (
                    min(float(word["global_top"]) for word in window),
                    transaction_date,
                    page_number,
                )
            )
            cursor += width
            matched = True
            break
        if not matched:
            cursor += 1
    anchors.sort(key=lambda item: item[0])
    source_withdrawals = Decimal("0.00")
    source_deposits = Decimal("0.00")
    transaction_count = 0

    for index, (top, transaction_date, page_number) in enumerate(anchors):
        bottom = anchors[index + 1][0] - 0.1 if index + 1 < len(anchors) else float("inf")

        def block(column: int) -> list[dict[str, Any]]:
            return [
                word
                for word in columns[column]
                if int(word["page_number"]) == page_number
                and top - 2.5 <= float(word["global_top"]) < bottom
            ]

        withdrawals = [value for value in _money_tokens(block(layout.withdrawal)) if value != 0]
        deposits = [value for value in _money_tokens(block(layout.deposit)) if value != 0]
        balances = _money_tokens(block(layout.balance))
        if len(withdrawals) > 1 or len(deposits) > 1 or len(balances) != 1:
            result.errors.append(
                f"PDF page {page_number} transaction {index + 1}: explicit amount columns are ambiguous"
            )
            continue

        description = _ordered_text(block(layout.description))
        reference = _ordered_text(block(layout.reference))
        value_date = (
            _first_date(block(layout.value_date))
            if layout.value_date is not None
            else None
        )
        before_count = len(result.transactions)
        _append_strict_savings_txn(
            {
                "date": transaction_date,
                "narration": description,
                "ref": reference,
                "value_date": value_date,
                "withdrawal": withdrawals[0] if withdrawals else None,
                "deposit": deposits[0] if deposits else None,
                "balance": balances[0] if balances else None,
                "source_bank": bank,
                "source_format_version": source_format_version,
                "parser_version": parser_version,
            },
            result.transactions,
            result.errors,
            row_label=f"PDF page {page_number} transaction {index + 1}",
        )
        if len(result.transactions) == before_count + 1:
            source_withdrawals += _decimal(str(withdrawals[0])) if withdrawals else Decimal("0.00")
            source_deposits += _decimal(str(deposits[0])) if deposits else Decimal("0.00")
            transaction_count += 1
    return _SourceColumnControls(
        withdrawals=source_withdrawals.quantize(Decimal("0.01")),
        deposits=source_deposits.quantize(Decimal("0.01")),
        transaction_count=transaction_count,
    )


def _decimal(value: str) -> Optional[Decimal]:
    normalized = value.replace("₹", "").replace(",", "").strip()
    try:
        parsed = Decimal(normalized)
    except Exception:
        return None
    return parsed.quantize(Decimal("0.01")) if parsed.is_finite() else None


def _last4(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return digits[-4:] if len(digits) >= 4 else None


def parse_hdfc_savings_pdf(
    document: Any,
    result: StatementParseResult,
    account_last4: Optional[str] = None,
) -> None:
    text = "\n".join(page.extract_text() or "" for page in document.pages)
    result.account_last4 = _last4(r"Account\s*No\s*:\s*([0-9 Xx*]{4,})", text)
    if result.account_last4:
        result.available_account_last4s = [result.account_last4]
    if account_last4 and account_last4 != result.account_last4:
        result.errors.append("The selected account does not match this HDFC statement")
        return
    period = re.search(
        r"From\s*:\s*(\d{2}/\d{2}/\d{2,4})\s+To\s*:\s*(\d{2}/\d{2}/\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if period:
        result.period_start = _parse_statement_date(period.group(1))
        result.period_end = _parse_statement_date(period.group(2))

    columns = _collect_columnar_words(
        document,
        column_count=7,
        header_tokens=("DATE", "NARRATION", "WITHDRAWAL", "DEPOSIT", "BALANCE"),
        allow_headerless_continuations=True,
    )
    source_controls = _append_columnar_transactions(
        result,
        columns,
        _HDFC_LAYOUT,
        bank="hdfc",
        source_format_version="hdfc-savings-column-geometry-v2",
        parser_version="hdfc-savings-v2",
    )

    header = re.compile(
        r"Opening\s*Balance\s+Dr\s*Count\s+Cr\s*Count\s+Debits\s+Credits\s+Closing\s*Bal",
        re.IGNORECASE,
    )
    lines = [" ".join(line.split()) for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        if not header.search(line):
            continue
        tokens = re.findall(r"-?\d[\d,]*\.\d{2}|\b\d+\b", lines[index + 1])
        if len(tokens) < 6:
            break
        opening, debit_count, credit_count, debits, credits, closing = tokens[:6]
        parsed = [_decimal(value) for value in (opening, debits, credits, closing)]
        if all(value is not None for value in parsed):
            result.declared_opening_balance = float(parsed[0])
            result.declared_closing_balance = float(parsed[3])
            result.declared_transaction_count = int(debit_count) + int(credit_count)
            if parsed[1] != source_controls.withdrawals:
                result.errors.append(
                    "Statement withdrawal summary does not match the extracted source column"
                )
            if parsed[2] != source_controls.deposits:
                result.errors.append(
                    "Statement deposit summary does not match the extracted source column"
                )
            declared_closing = (
                parsed[0] - source_controls.withdrawals + source_controls.deposits
            ).quantize(Decimal("0.01"))
            if declared_closing != parsed[3]:
                result.errors.append(
                    "Statement summary balances do not reconcile with its debit and credit controls"
                )
        break
    if not result.transactions and not result.errors:
        result.errors.append("No supported HDFC savings transaction rows were found")
    _validate_savings_controls(result)
    if result.reconciliation_status == "passed":
        result.reconciliation_method += "_and_declared_summary"


def parse_kotak_savings_pdf(
    document: Any,
    result: StatementParseResult,
    account_last4: Optional[str] = None,
) -> None:
    text = "\n".join(page.extract_text() or "" for page in document.pages)
    result.account_last4 = _last4(r"Account\s+No\.?\s*([0-9 Xx*]{4,})", text)
    if result.account_last4:
        result.available_account_last4s = [result.account_last4]
    if account_last4 and account_last4 != result.account_last4:
        result.errors.append("The selected account does not match this Kotak statement")
        return
    period = re.search(
        r"Account\s+Statement\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if period:
        result.period_start = _parse_statement_date(period.group(1))
        result.period_end = _parse_statement_date(period.group(2))

    columns = _collect_columnar_words(
        document,
        column_count=7,
        header_tokens=("DATE", "DESCRIPTION", "WITHDRAWAL", "DEPOSIT", "BALANCE"),
        allow_headerless_continuations=True,
    )
    _append_columnar_transactions(
        result,
        columns,
        _KOTAK_LAYOUT,
        bank="kotak",
        source_format_version="kotak-savings-explicit-columns-v1",
        parser_version="kotak-savings-v1",
    )

    summary = re.search(
        r"Savings\s+Account\s*\(SA\)\s*:\s*(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})",
        text,
        re.IGNORECASE,
    )
    if summary:
        opening = _decimal(summary.group(1))
        closing = _decimal(summary.group(2))
        if opening is not None and closing is not None:
            result.declared_opening_balance = float(opening)
            result.declared_closing_balance = float(closing)
    if not result.transactions and not result.errors:
        result.errors.append("No supported Kotak savings transaction rows were found")
    _validate_savings_controls(result)


def _cell_money(cell: object) -> Optional[float]:
    return _parse_amount(str(cell or "").replace("₹", "").strip())


def _control_amount(row: list[object]) -> Optional[float]:
    for cell in row[1:]:
        value = _cell_money(cell)
        if value is not None:
            return value
    return None


def parse_sbi_savings_pdf(
    document: Any,
    result: StatementParseResult,
    account_last4: Optional[str],
) -> None:
    page_texts = [page.extract_text() or "" for page in document.pages]
    section_pattern = re.compile(
        r"(SAVING|DL/TL)\s+ACCOUNT\s+X+(\d{4})",
        re.IGNORECASE,
    )
    sections: dict[str, str] = {}
    for text in page_texts:
        for kind, last4 in section_pattern.findall(text):
            sections[last4] = kind.upper()
    result.available_account_last4s = sorted(sections)
    supported = sorted(last4 for last4, kind in sections.items() if kind == "SAVING")
    if account_last4:
        selected = account_last4
        if selected not in sections:
            result.errors.append("The selected account does not appear in this SBI statement")
            return
        if sections[selected] != "SAVING":
            result.errors.append(
                "The selected SBI section is not a supported savings account statement"
            )
            return
    elif len(supported) == 1:
        selected = supported[0]
    elif len(supported) > 1:
        result.errors.append(
            "Multiple SBI savings accounts were found; select the matching account and try again"
        )
        return
    else:
        result.errors.append("No supported SBI savings account section was found")
        return

    result.account_last4 = selected
    current_section: Optional[str] = None
    for page_number, (page, text) in enumerate(zip(document.pages, page_texts), start=1):
        matches = section_pattern.findall(text)
        if matches:
            current_section = matches[-1][1]
        if current_section != selected:
            continue
        for table in page.extract_tables() or []:
            header_index = _table_header_index(
                table,
                ("DATE", "TRANSACTION REFERENCE", "CREDIT", "DEBIT", "BALANCE"),
            )
            if header_index is None:
                continue
            header = [str(cell or "").strip().upper() for cell in table[header_index]]

            def index_of(token: str) -> Optional[int]:
                return next((i for i, value in enumerate(header) if token in value), None)

            date_index = index_of("DATE")
            description_index = index_of("TRANSACTION REFERENCE")
            reference_index = index_of("REF.NO")
            credit_index = index_of("CREDIT")
            debit_index = index_of("DEBIT")
            balance_index = index_of("BALANCE")
            required = (
                date_index,
                description_index,
                reference_index,
                credit_index,
                debit_index,
                balance_index,
            )
            if any(index is None for index in required):
                result.errors.append(
                    f"PDF page {page_number}: SBI transaction columns are incomplete"
                )
                continue
            assert date_index is not None
            assert description_index is not None
            assert reference_index is not None
            assert credit_index is not None
            assert debit_index is not None
            assert balance_index is not None

            for row_number, row in enumerate(table[header_index + 1 :], start=header_index + 2):
                joined = " ".join(str(cell or "") for cell in row)
                upper = joined.upper()
                if "OPENING BALANCE" in upper:
                    amount = _control_amount(row)
                    if amount is not None:
                        result.declared_opening_balance = amount
                    match = re.search(r"(\d{2}-\d{2}-\d{2,4})", joined)
                    if match:
                        result.period_start = _parse_statement_date(match.group(1))
                    continue
                if "CLOSING BALANCE" in upper:
                    amount = _control_amount(row)
                    if amount is not None:
                        result.declared_closing_balance = amount
                    match = re.search(r"(\d{2}-\d{2}-\d{2,4})", joined)
                    if match:
                        result.period_end = _parse_statement_date(match.group(1))
                    continue
                transaction_date = _parse_statement_date(str(row[date_index] or "").strip())
                if transaction_date is None:
                    continue
                description = " ".join(
                    str(cell or "").strip()
                    for cell in row[description_index:reference_index]
                    if str(cell or "").strip()
                )
                _append_strict_savings_txn(
                    {
                        "date": transaction_date,
                        "narration": description,
                        "ref": str(row[reference_index] or "").strip(),
                        "withdrawal": _cell_money(row[debit_index]),
                        "deposit": _cell_money(row[credit_index]),
                        "balance": _cell_money(row[balance_index]),
                        "source_bank": "sbi",
                        "source_format_version": "sbi-relationship-summary-v1",
                        "parser_version": "sbi-savings-v1",
                    },
                    result.transactions,
                    result.errors,
                    row_label=f"PDF page {page_number} row {row_number}",
                )
    if not result.transactions and not result.errors:
        result.errors.append("No supported SBI savings transaction rows were found")
    _validate_savings_controls(result)
