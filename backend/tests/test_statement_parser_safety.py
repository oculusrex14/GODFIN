from __future__ import annotations

import asyncio
import io
import threading
from datetime import date

import pytest
from openpyxl import Workbook

from app.core.parsers import parse_registered_statement
from app.core.statement_parser import (
    StatementParseResult,
    StatementTransaction,
    _validate_savings_controls,
    _parse_hdfc_savings_statement,
    _process_savings_table_v2,
)


def test_all_debit_statement_controls_keep_decimal_zero_for_credits():
    result = StatementParseResult(
        transactions=[
            StatementTransaction(
                date=date(2026, 7, 15),
                description="SYNTHETIC UNKNOWN MERCHANT",
                amount=450,
                txn_type="debit",
                closing_balance=9_550,
            ),
            StatementTransaction(
                date=date(2026, 7, 16),
                description="SYNTHETIC CAFE",
                amount=275,
                txn_type="debit",
                closing_balance=9_275,
            ),
        ]
    )

    _validate_savings_controls(result)

    assert result.errors == []
    assert result.reconciliation_status == "passed"
    assert result.total_debits == 725
    assert result.total_credits == 0


HEADER = [
    "Date",
    "Narration",
    "Chq./Ref.No.",
    "Value Dt",
    "Withdrawal Amt.",
    "Deposit Amt.",
    "Closing Balance",
]


def _xlsx(
    rows: list[list[object]],
    *,
    bank_heading: str = "HDFC BANK Savings Account Statement",
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([bank_heading])
    sheet.append(["Statement From : 01/07/2026 To : 31/07/2026"])
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _valid_rows() -> list[list[object]]:
    return [
        [
            "14/07/2026",
            "NEFT CR-SYNTHETIC-SALARY",
            "REF-1",
            "14/07/2026",
            None,
            1000.0,
            10000.0,
        ],
        [
            "15/07/2026",
            "SYNTHETIC UNKNOWN MERCHANT",
            "REF-2",
            "15/07/2026",
            200.0,
            None,
            9800.0,
        ],
    ]


def test_salary_credit_and_unknown_merchant_debit_remain_separate_and_reconcile():
    result = parse_registered_statement(_xlsx(_valid_rows()), "xlsx")

    assert result.errors == []
    assert result.reconciliation_status == "passed"
    assert [(txn.txn_type, txn.amount) for txn in result.transactions] == [
        ("credit", 1000.0),
        ("debit", 200.0),
    ]
    assert result.transactions[0].description == "NEFT CR-SYNTHETIC-SALARY"
    assert result.transactions[1].description == "SYNTHETIC UNKNOWN MERCHANT"


def test_reverse_chronological_savings_rows_reconcile_without_inverting_direction():
    rows = list(reversed(_valid_rows()))
    result = parse_registered_statement(_xlsx(rows), "xlsx")

    assert result.errors == []
    assert result.reconciliation_status == "passed"
    assert [(txn.txn_type, txn.amount) for txn in result.transactions] == [
        ("debit", 200.0),
        ("credit", 1000.0),
    ]


def test_unsupported_spreadsheet_is_not_assumed_to_be_hdfc():
    result = parse_registered_statement(
        _xlsx(_valid_rows(), bank_heading="SYNTHETIC OTHER BANK"),
        "xlsx",
    )

    assert result.transactions == []
    assert result.recognized is False
    assert any("HDFC" in error and "fingerprint" in error for error in result.errors)


def test_savings_row_with_both_withdrawal_and_deposit_is_rejected():
    rows = _valid_rows()
    rows[1][5] = 200.0
    result = parse_registered_statement(_xlsx(rows), "xlsx")

    assert result.transactions == []
    assert result.reconciliation_status == "failed"
    assert any("both withdrawal and deposit" in error for error in result.errors)


def test_balance_control_mutation_rejects_entire_statement():
    rows = _valid_rows()
    rows[1][6] = 9700.0
    result = parse_registered_statement(_xlsx(rows), "xlsx")

    assert result.transactions == []
    assert result.reconciliation_status == "failed"
    assert any("balance continuity" in error for error in result.errors)


def test_single_unreconciled_row_is_rejected():
    result = parse_registered_statement(_xlsx(_valid_rows()[:1]), "xlsx")

    assert result.transactions == []
    assert result.reconciliation_status == "failed"
    assert any("at least two" in error for error in result.errors)


def test_packed_pdf_row_is_rejected_instead_of_guessing_amount_direction():
    table = [
        HEADER,
        [
            "14/07/2026\n15/07/2026",
            "NEFT CR-SYNTHETIC-SALARY\nSYNTHETIC UNKNOWN MERCHANT",
            "REF-1\nREF-2",
            "14/07/2026\n15/07/2026",
            "200.00",
            "1000.00",
            "10000.00\n9800.00",
        ],
    ]
    transactions = []
    errors: list[str] = []

    _process_savings_table_v2(table, transactions, errors=errors)

    assert transactions == []
    assert any("packed multi-line" in error.lower() for error in errors)


class _TextOnlyPage:
    def extract_tables(self):
        return []

    def extract_text(self):
        return "14/07/2026 SALARY CREDIT 1,000.00 10,000.00"


class _TextOnlyPdf:
    pages = [_TextOnlyPage()]


def test_text_only_savings_extraction_is_rejected_instead_of_assuming_debit():
    result = StatementParseResult(statement_type="hdfc_savings", recognized=True)

    _parse_hdfc_savings_statement(_TextOnlyPdf(), result)

    assert result.transactions == []
    assert result.reconciliation_status == "failed"
    assert any("text-only" in error.lower() for error in result.errors)


def test_unrecognized_pdf_does_not_fall_back_to_any_registered_parser(monkeypatch):
    from app.core.parsers import registry

    monkeypatch.setattr(
        registry,
        "_pdf_text",
        lambda contents, password: ("SYNTHETIC OTHER BANK STATEMENT", None),
    )

    result = parse_registered_statement(b"not-opened-after-detection", "pdf")

    assert result.transactions == []
    assert result.recognized is False
    assert result.errors == [
        "Unsupported or unrecognized PDF statement; select a supported HDFC profile",
    ]


def test_import_requires_review_confirmation_and_matching_file(auth_client):
    contents = _xlsx(_valid_rows())

    reconcile = auth_client.post(
        "/api/v1/ingest/upload/reconcile",
        files={
            "file": (
                "statement.xlsx",
                contents,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )
    assert reconcile.status_code == 200
    reviewed = reconcile.json()
    assert reviewed["reconciliation_status"] == "passed"
    assert reviewed["parse_fingerprint"]

    unconfirmed = auth_client.post(
        "/api/v1/ingest/upload/import",
        files={"file": ("statement.xlsx", contents)},
    )
    assert unconfirmed.status_code == 400
    assert "explicitly confirm" in unconfirmed.json()["detail"]

    changed = auth_client.post(
        "/api/v1/ingest/upload/import",
        files={"file": ("statement.xlsx", contents)},
        data={
            "confirm_reconciled": "true",
            "accepted_fingerprint": "0" * 64,
        },
    )
    assert changed.status_code == 409
    assert "changed after review" in changed.json()["detail"]

    accepted = auth_client.post(
        "/api/v1/ingest/upload/import",
        files={"file": ("statement.xlsx", contents)},
        data={
            "confirm_reconciled": "true",
            "accepted_fingerprint": reviewed["parse_fingerprint"],
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["imported"] == 2


def test_legacy_one_step_import_is_retired(auth_client):
    response = auth_client.post(
        "/api/v1/ingest/upload",
        files={"file": ("statement.xlsx", _xlsx(_valid_rows()))},
    )

    assert response.status_code == 410
    assert "preview, reconcile" in response.json()["detail"]


def test_upload_limit_is_enforced_while_streaming(auth_client):
    response = auth_client.post(
        "/api/v1/ingest/upload/preview",
        files={"file": ("too-large.xlsx", b"x" * (10 * 1024 * 1024 + 1))},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File too large (max 10MB)"


def test_parser_work_is_dispatched_through_the_worker_boundary(auth_client, monkeypatch):
    from app.api.v1.endpoints import statement

    calls: list[tuple[bytes, str, object]] = []

    async def recording_process(contents, file_format, password):
        calls.append((contents, file_format, password))
        return parse_registered_statement(contents, file_format, password)

    monkeypatch.setattr(statement, "_parse_in_isolated_process", recording_process)
    response = auth_client.post(
        "/api/v1/ingest/upload/preview",
        files={"file": ("statement.xlsx", _xlsx(_valid_rows()))},
    )

    assert response.status_code == 200
    assert calls
    assert calls[0][1] == "xlsx"


def test_real_parser_process_returns_a_reconciled_statement():
    from app.api.v1.endpoints import statement

    result = statement._run_parser_process(
        _xlsx(_valid_rows()),
        "xlsx",
        None,
        threading.Event(),
        timeout_seconds=15,
    )

    assert result.recognized is True
    assert result.reconciliation_status == "passed"
    assert len(result.transactions) == 2


def test_parser_timeout_is_reported_without_leaving_a_worker(monkeypatch):
    from app.api.v1.endpoints import statement

    class _NeverResponds:
        exitcode = None

        def start(self):
            return None

        def is_alive(self):
            return self.exitcode is None

        def terminate(self):
            self.exitcode = -15

        def join(self, timeout=None):
            return None

        def kill(self):
            self.exitcode = -9

    class _Connection:
        def close(self):
            return None

        def poll(self, timeout=0):
            return False

    class _Context:
        process = _NeverResponds()

        def Pipe(self, duplex=False):
            return _Connection(), _Connection()

        def Process(self, **kwargs):
            return self.process

    context = _Context()
    monkeypatch.setattr(statement.multiprocessing, "get_context", lambda _name: context)

    with pytest.raises(statement.StatementParserTimeout):
        statement._run_parser_process(
            b"synthetic",
            "pdf",
            None,
            threading.Event(),
            timeout_seconds=0,
        )

    assert context.process.exitcode == -15


def test_parser_cancellation_is_reported_and_terminates_worker(monkeypatch):
    from app.api.v1.endpoints import statement

    cancel_event = threading.Event()
    cancel_event.set()

    class _Process:
        exitcode = None

        def start(self):
            return None

        def is_alive(self):
            return self.exitcode is None

        def terminate(self):
            self.exitcode = -15

        def join(self, timeout=None):
            return None

    class _Connection:
        def close(self):
            return None

        def poll(self, timeout=0):
            return False

    process = _Process()
    context = type(
        "Context",
        (),
        {
            "Pipe": lambda self, duplex=False: (_Connection(), _Connection()),
            "Process": lambda self, **kwargs: process,
        },
    )()
    monkeypatch.setattr(statement.multiprocessing, "get_context", lambda _name: context)

    with pytest.raises(asyncio.CancelledError):
        statement._run_parser_process(
            b"synthetic",
            "pdf",
            None,
            cancel_event,
        )

    assert process.exitcode == -15


def test_parser_concurrency_limit_returns_retryable_busy_response(auth_client):
    from app.api.v1.endpoints import statement

    assert statement._PARSER_SLOTS.acquire(blocking=False)
    assert statement._PARSER_SLOTS.acquire(blocking=False)
    try:
        response = auth_client.post(
            "/api/v1/ingest/upload/preview",
            files={"file": ("statement.xlsx", _xlsx(_valid_rows()))},
        )
    finally:
        statement._PARSER_SLOTS.release()
        statement._PARSER_SLOTS.release()

    assert response.status_code == 429
    assert response.headers["retry-after"] == "3"
