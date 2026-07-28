from __future__ import annotations

import io
import uuid
from datetime import date

from openpyxl import Workbook

from app.core.account_mapping import save_sender_mappings
from app.core.ingestion import run_ingestion
from app.core.parsers import parse_registered_statement
from app.models.account import Account
from app.models.transaction import Transaction


def _hdfc_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Account No", "XXXXXXXX0000"])
    sheet.append(["Statement From : 01/07/2026 To : 31/07/2026"])
    sheet.append(
        [
            "Date",
            "Narration",
            "Chq./Ref.No.",
            "Value Dt",
            "Withdrawal Amt.",
            "Deposit Amt.",
            "Closing Balance",
        ]
    )
    sheet.append(
        [
            "15/07/2026",
            "UPI-SYNTHETIC CAFE-cafe@ybl-HDFC0000001-123456789012",
            "123456789012",
            "15/07/2026",
            275.0,
            None,
            9725.0,
        ]
    )
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_registered_xlsx_parser_reads_hdfc_savings():
    result = parse_registered_statement(_hdfc_xlsx(), "xlsx")

    assert result.errors == []
    assert result.statement_type == "hdfc_savings"
    assert result.period_start == date(2026, 7, 1)
    assert result.period_end == date(2026, 7, 31)
    assert len(result.transactions) == 1
    assert result.transactions[0].amount == 275.0
    assert result.transactions[0].txn_type == "debit"


def test_account_crud_and_sender_mapping(auth_client):
    create = auth_client.post(
        "/api/v1/accounts",
        json={
            "bank": "hdfc",
            "account_type": "savings",
            "last_4_digits": "4321",
            "nickname": "Travel account",
        },
    )
    assert create.status_code == 201
    account = create.json()
    assert account["bank"] == "HDFC"

    update = auth_client.patch(
        f"/api/v1/accounts/{account['id']}",
        json={"nickname": "Travel savings"},
    )
    assert update.status_code == 200
    assert update.json()["nickname"] == "Travel savings"

    mappings = auth_client.get("/api/v1/accounts/sender-mappings").json()
    mappings.append(
        {
            "sender_pattern": "travel-alerts@example.test",
            "parser_profile": "hdfc_savings",
            "account_id": account["id"],
        }
    )
    replace = auth_client.put(
        "/api/v1/accounts/sender-mappings",
        json={"mappings": mappings},
    )
    assert replace.status_code == 200
    assert any(
        item["account_id"] == account["id"]
        for item in replace.json()
    )

    deactivate = auth_client.delete(f"/api/v1/accounts/{account['id']}")
    assert deactivate.status_code == 204
    all_accounts = auth_client.get(
        "/api/v1/accounts?include_inactive=true"
    ).json()
    assert next(
        item for item in all_accounts if item["id"] == account["id"]
    )["is_active"] is False
    assert all(
        item["account_id"] != account["id"]
        for item in auth_client.get("/api/v1/accounts/sender-mappings").json()
    )


def test_non_hdfc_account_requires_paid_license(auth_client):
    response = auth_client.post(
        "/api/v1/accounts",
        json={
            "bank": "ICICI",
            "account_type": "savings",
            "last_4_digits": "5678",
        },
    )
    assert response.status_code == 403


def test_parser_profiles_are_discoverable(auth_client):
    response = auth_client.get("/api/v1/accounts/parser-profiles")
    assert response.status_code == 200
    profiles = {item["profile"] for item in response.json()}
    assert profiles == {"hdfc_savings", "hdfc_credit"}


def test_gmail_sender_mapping_routes_to_configured_account(db_session):
    account = Account(
        id=str(uuid.uuid4()),
        bank="HDFC",
        account_type="savings",
        last_4_digits="4321",
        nickname="Mapped account",
        is_active=True,
    )
    db_session.add(account)
    db_session.flush()
    save_sender_mappings(
        db_session,
        [
            {
                "sender_pattern": "custom-alerts@example.test",
                "parser_profile": "hdfc_savings",
                "account_id": account.id,
            }
        ],
    )

    result = run_ingestion(
        db_session,
        mock_messages=[
            {
                "id": "mapped-email-1",
                "sender": "Custom Alerts <custom-alerts@example.test>",
                "subject": "Transaction Alert",
                "body": (
                    "Dear Customer, Rs.350.00 has been debited from account "
                    "4321 to VPA cafe@ybl Synthetic Cafe on 10-07-26. "
                    "Your UPI transaction reference number is 504123456789."
                ),
            }
        ],
    )

    assert result.created == 1
    transaction = (
        db_session.query(Transaction)
        .filter_by(email_message_id="mapped-email-1")
        .one()
    )
    assert transaction.account_id == account.id
