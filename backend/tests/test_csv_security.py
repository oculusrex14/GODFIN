from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime

import pytest

from app.core import behavior_insights as behavior_module
from app.core.behavior_insights import export_behavior_insights_csv
from app.core.classification_learning import export_learning_memory_csv
from app.core.csv_security import spreadsheet_safe_cell, spreadsheet_safe_row
from app.core.tax_pack import _csv_bytes
from app.models.account import Account
from app.models.app_setting import AppSetting
from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction
from tests.license_helpers import install_test_license


@pytest.mark.parametrize(
    "payload",
    [
        "=1+1",
        "+SUM(A1:A2)",
        "-2+3",
        "@SUM(A1:A2)",
        "\t=HYPERLINK(\"https://example.invalid\")",
        "\r+CMD|'/C calc'!A0",
        "\n-2+3",
        " \u00a0@SUM(A1:A2)",
        "\u200b=1+1",
    ],
)
def test_formula_like_csv_cells_are_forced_to_text(payload):
    assert spreadsheet_safe_cell(payload) == f"'{payload}"


def test_csv_safety_preserves_non_formula_types_and_round_trip_text():
    values = [
        "ordinary text",
        'quoted "text"',
        "line one\nline two",
        "₹ café 東京",
        "'already text",
        42,
        -42.5,
        True,
        None,
    ]
    output = io.StringIO(newline="")
    csv.writer(output).writerow(spreadsheet_safe_row(values))

    parsed = next(csv.reader(io.StringIO(output.getvalue())))

    assert parsed == [
        "ordinary text",
        'quoted "text"',
        "line one\nline two",
        "₹ café 東京",
        "'already text",
        "42",
        "-42.5",
        "True",
        "",
    ]


def _activate_pro(db_session) -> None:
    install_test_license(db_session, "pro")


def test_transaction_csv_exports_neutralize_every_user_controlled_formula_cell(
    auth_client,
    db_session,
):
    _activate_pro(db_session)
    account = db_session.query(Account).first()
    account.nickname = '=HYPERLINK("https://example.invalid")'
    transaction = Transaction(
        id=str(uuid.uuid4()),
        date=date(2026, 8, 1),
        raw_text="@SUM(A1:A2)",
        merchant_raw="+CMD|' /C calc'!A0",
        merchant_normalized="\t=1+1",
        amount=125.50,
        type="debit",
        instrument="bank",
        account_id=account.id,
        source="manual",
        tags="-2+3",
        notes="\r@SUM(A1:A2)",
    )
    db_session.add(transaction)
    db_session.commit()

    monthly = auth_client.get("/api/v1/reports/csv?month=2026-08")
    assert monthly.status_code == 200
    monthly_row = next(csv.DictReader(io.StringIO(monthly.text)))
    assert monthly_row["Merchant"] == "'\t=1+1"
    assert monthly_row["Account"] == "'=HYPERLINK(\"https://example.invalid\")"

    financial_year = auth_client.get(
        "/api/v1/reports/fy?start_year=2026&format=csv"
    )
    assert financial_year.status_code == 200
    fy_row = next(csv.DictReader(io.StringIO(financial_year.text)))
    assert fy_row["merchant_raw"] == "'+CMD|' /C calc'!A0"
    assert fy_row["merchant"] == "'\t=1+1"
    assert fy_row["raw_text"] == "'@SUM(A1:A2)"
    assert fy_row["account"] == "'=HYPERLINK(\"https://example.invalid\")"
    assert fy_row["tags"] == "'-2+3"
    assert fy_row["notes"] == "'\r@SUM(A1:A2)"


def test_learning_and_behavior_exports_apply_the_same_csv_policy(
    db_session,
    monkeypatch,
):
    db_session.add(
        MerchantMemory(
            raw_string="=1+1",
            normalized_name="=1+1",
            category="FOOD & DINING",
            subcategory="@SUM(A1:A2)",
            times_seen=2,
            avg_confidence=1.0,
        )
    )
    db_session.commit()

    learning_row = next(
        csv.DictReader(io.StringIO(export_learning_memory_csv(db_session)))
    )
    assert learning_row["merchant_or_pattern"] == "'=1+1"
    assert learning_row["subcategory"] == "'@SUM(A1:A2)"

    monkeypatch.setattr(
        behavior_module,
        "compute_behavior_insights",
        lambda _db: {
            "metrics": [
                {
                    "label": "=1+1",
                    "available": True,
                    "value": 10.5,
                    "unit": "%",
                    "period": "Finished months",
                    "confidence": "high",
                    "sample_size": 6,
                    "minimum_sample": 2,
                    "unavailable_reason": None,
                    "formula": "+SUM(A1:A2)",
                    "evidence": "Safe, quoted\nUnicode ₹",
                    "provenance": "local",
                    "correction_note": "\t@SUM(A1:A2)",
                }
            ]
        },
    )
    behavior_row = next(
        csv.DictReader(io.StringIO(export_behavior_insights_csv(db_session)))
    )
    assert behavior_row["metric"] == "'=1+1"
    assert behavior_row["formula"] == "'+SUM(A1:A2)"
    assert behavior_row["correction_note"] == "'\t@SUM(A1:A2)"
    assert behavior_row["evidence"] == "Safe, quoted\nUnicode ₹"


def test_tax_pack_csv_uses_shared_formula_neutralization():
    payload = _csv_bytes(
        [
            {
                "Merchant": "\u200b=1+1",
                "Notes": "+SUM(A1:A2)",
                "Amount (INR)": 125.50,
            }
        ]
    ).decode("utf-8-sig")
    row = next(csv.DictReader(io.StringIO(payload)))
    assert row["Merchant"] == "'\u200b=1+1"
    assert row["Notes"] == "'+SUM(A1:A2)"
    assert row["Amount (INR)"] == "125.5"
