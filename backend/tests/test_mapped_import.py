from __future__ import annotations

import io
import json
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.models.account_balance import AccountStatementCoverage
from app.models.transaction import Transaction
from app.core.reconciliation import ReconciliationService
from app.seed import SAVINGS_ACCOUNT_ID
from tests.license_helpers import install_test_license


MAPPING = {
    "date_column": 0,
    "description_column": 1,
    "debit_column": 2,
    "credit_column": 3,
    "running_balance_column": 4,
    "account_identifier_column": 5,
}


def _csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def _inspect(auth_client, contents: bytes, filename: str = "statement.csv"):
    return auth_client.post(
        "/api/v1/ingest/mapped/inspect",
        files={"file": (filename, contents)},
    )


def _preview(
    auth_client,
    contents: bytes,
    *,
    mapping: dict = MAPPING,
    filename: str = "statement.csv",
):
    return auth_client.post(
        "/api/v1/ingest/mapped/preview",
        files={"file": (filename, contents)},
        data={
            "account_id": SAVINGS_ACCOUNT_ID,
            "mapping_json": json.dumps(mapping),
            "date_format": "dd/mm/yyyy",
        },
    )


def _install_pro(db_session):
    install_test_license(db_session, "pro")


def test_inspect_suggests_only_unambiguous_columns(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Date,Narration,Debit,Credit,Balance,Account Number",
        "01/01/2026,Coffee,100,,900,0000",
    )

    response = _inspect(auth_client, contents)

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_format"] == "csv"
    assert payload["header_row"] == 1
    assert payload["row_count"] == 1
    assert [column["label"] for column in payload["columns"]] == [
        "Date",
        "Narration",
        "Debit",
        "Credit",
        "Balance",
        "Account Number",
    ]
    assert payload["suggested_mapping"] == MAPPING | {
        "value_date_column": None,
        "reference_column": None,
    }
    assert len(payload["source_fingerprint"]) == 64
    assert len(payload["header_signature"]) == 64


def test_inspect_skips_metadata_rows_before_transaction_header(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Synthetic Bank Statement",
        "Account,0000",
        "Date,Narration,Debit,Credit",
        "01/01/2026,Coffee,100,",
    )

    response = _inspect(auth_client, contents)

    assert response.status_code == 200
    assert response.json()["header_row"] == 3
    assert response.json()["row_count"] == 1


def test_preview_and_import_verified_csv_mapping(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Date,Narration,Debit,Credit,Balance,Account Number",
        "01/01/2026,Synthetic purchase,100,,900,0000",
        "02/01/2026,Synthetic salary,,200,1100,0000",
    )

    preview = _preview(auth_client, contents)

    assert preview.status_code == 200
    reviewed = preview.json()
    assert reviewed["status"] == "ready"
    assert reviewed["total_rows"] == 2
    assert reviewed["new_count"] == 2
    assert reviewed["balance_controls_verified"] is True
    assert reviewed["opening_balance"] == 1000
    assert reviewed["closing_balance"] == 1100
    assert reviewed["account_identifiers"] == ["••••0000"]

    imported = auth_client.post(
        "/api/v1/ingest/mapped/import",
        files={"file": ("statement.csv", contents)},
        data={
            "account_id": SAVINGS_ACCOUNT_ID,
            "mapping_json": json.dumps(MAPPING),
            "date_format": "dd/mm/yyyy",
            "confirm_mapping": "true",
            "accepted_fingerprint": reviewed["source_fingerprint"],
            "accepted_mapping_fingerprint": reviewed["mapping_fingerprint"],
        },
    )

    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["imported"] == 2
    assert result["balance_controls_verified"] is True
    assert result["balance_status"] == "verified"
    assert result["coverage_complete"] is True
    assert (
        db_session.query(Transaction)
        .filter(Transaction.source == "mapped_import")
        .count()
        == 2
    )
    assert db_session.query(AccountStatementCoverage).count() == 1


def test_ambiguous_rows_are_previewed_but_never_imported(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Date,Narration,Debit,Credit,Balance,Account Number",
        "01/01/2026,Ambiguous row,100,100,1000,0000",
    )
    preview = _preview(auth_client, contents)

    assert preview.status_code == 200
    reviewed = preview.json()
    assert reviewed["status"] == "needs_review"
    assert reviewed["errors"][0]["row"] == 2
    assert "Exactly one" in reviewed["errors"][0]["message"]

    imported = auth_client.post(
        "/api/v1/ingest/mapped/import",
        files={"file": ("statement.csv", contents)},
        data={
            "account_id": SAVINGS_ACCOUNT_ID,
            "mapping_json": json.dumps(MAPPING),
            "date_format": "dd/mm/yyyy",
            "confirm_mapping": "true",
            "accepted_fingerprint": reviewed["source_fingerprint"],
            "accepted_mapping_fingerprint": reviewed["mapping_fingerprint"],
        },
    )
    assert imported.status_code == 422
    assert db_session.query(Transaction).filter_by(source="mapped_import").count() == 0


def test_mapping_change_after_preview_is_rejected(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Date,Narration,Debit,Credit,Balance,Account Number",
        "01/01/2026,Coffee,100,,900,0000",
    )
    reviewed = _preview(auth_client, contents).json()
    changed = dict(MAPPING)
    changed["reference_column"] = 4

    response = auth_client.post(
        "/api/v1/ingest/mapped/import",
        files={"file": ("statement.csv", contents)},
        data={
            "account_id": SAVINGS_ACCOUNT_ID,
            "mapping_json": json.dumps(changed),
            "date_format": "dd/mm/yyyy",
            "confirm_mapping": "true",
            "accepted_fingerprint": reviewed["source_fingerprint"],
            "accepted_mapping_fingerprint": reviewed["mapping_fingerprint"],
        },
    )
    assert response.status_code == 409
    assert db_session.query(Transaction).filter_by(source="mapped_import").count() == 0


def test_mapping_without_running_balance_imports_without_balance_claim(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    contents = _csv(
        "Date,Narration,Debit,Credit",
        "01/01/2026,Coffee,100,",
    )
    mapping = {
        "date_column": 0,
        "description_column": 1,
        "debit_column": 2,
        "credit_column": 3,
    }
    reviewed = _preview(auth_client, contents, mapping=mapping).json()
    assert reviewed["status"] == "ready"
    assert reviewed["balance_controls_verified"] is False

    response = auth_client.post(
        "/api/v1/ingest/mapped/import",
        files={"file": ("statement.csv", contents)},
        data={
            "account_id": SAVINGS_ACCOUNT_ID,
            "mapping_json": json.dumps(mapping),
            "date_format": "dd/mm/yyyy",
            "confirm_mapping": "true",
            "accepted_fingerprint": reviewed["source_fingerprint"],
            "accepted_mapping_fingerprint": reviewed["mapping_fingerprint"],
        },
    )
    assert response.status_code == 200
    assert response.json()["balance_controls_verified"] is False
    assert response.json()["balance_status"] == "unverified_no_anchor"
    assert db_session.query(AccountStatementCoverage).count() == 0


def test_xlsx_and_account_identifier_mismatch_are_handled(
    auth_client,
    db_session,
):
    _install_pro(db_session)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Narration", "Debit", "Credit", "Balance", "Account"])
    sheet.append(["01/01/2026", "Coffee", 100, None, 900, "9999"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    contents = output.getvalue()

    inspection = _inspect(auth_client, contents, "statement.xlsx")
    assert inspection.status_code == 200
    assert inspection.json()["file_format"] == "xlsx"

    preview = _preview(
        auth_client,
        contents,
        filename="statement.xlsx",
    )
    assert preview.status_code == 409
    assert "last four" in preview.json()["detail"].lower()


def test_mapped_import_requires_multi_bank_entitlement(auth_client):
    response = _inspect(
        auth_client,
        _csv(
            "Date,Narration,Debit,Credit",
            "01/01/2026,Synthetic purchase,100,",
        ),
    )

    assert response.status_code == 403


def test_reconciliation_normalizes_float_and_decimal_money():
    assert ReconciliationService._match_amount(100.0, Decimal("100.00")) == 1.0
    assert ReconciliationService._match_amount(100.0, Decimal("100.50")) == 0.95
    assert ReconciliationService._match_amount(100.0, Decimal("104.00")) == 0.7


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_overlapping_mapped_files_are_order_independent(
    auth_client,
    db_session,
    order,
):
    _install_pro(db_session)
    mapping = {
        "date_column": 0,
        "description_column": 1,
        "debit_column": 2,
        "credit_column": 3,
    }
    files = {
        "a": _csv(
            "Date,Narration,Debit,Credit",
            "01/01/2026,Synthetic coffee,100,",
            "02/01/2026,Synthetic salary,,200",
        ),
        "b": _csv(
            "Date,Narration,Debit,Credit",
            "02/01/2026,Synthetic salary,,200",
            "03/01/2026,Synthetic groceries,50,",
        ),
    }

    import_counts = []
    for label in order:
        contents = files[label]
        reviewed = _preview(
            auth_client,
            contents,
            mapping=mapping,
            filename=f"{label}.csv",
        ).json()
        response = auth_client.post(
            "/api/v1/ingest/mapped/import",
            files={"file": (f"{label}.csv", contents)},
            data={
                "account_id": SAVINGS_ACCOUNT_ID,
                "mapping_json": json.dumps(mapping),
                "date_format": "dd/mm/yyyy",
                "confirm_mapping": "true",
                "accepted_fingerprint": reviewed["source_fingerprint"],
                "accepted_mapping_fingerprint": reviewed["mapping_fingerprint"],
            },
        )
        assert response.status_code == 200, response.text
        import_counts.append(response.json()["imported"])

    ledger = (
        db_session.query(Transaction)
        .filter(Transaction.source == "mapped_import")
        .order_by(Transaction.date, Transaction.amount)
        .all()
    )
    assert import_counts == [2, 1]
    assert [
        (str(item.date), item.type, float(item.amount), item.merchant_raw)
        for item in ledger
    ] == [
        ("2026-01-01", "debit", 100.0, "Synthetic coffee"),
        ("2026-01-02", "credit", 200.0, "Synthetic salary"),
        ("2026-01-03", "debit", 50.0, "Synthetic groceries"),
    ]
