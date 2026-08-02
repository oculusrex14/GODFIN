from __future__ import annotations

from datetime import date

from app.core.gmail_service import GmailFetchResult
from app.core.ingestion import run_ingestion, run_initial_sync
from app.models.app_setting import AppSetting
from app.models.audit_session import AuditSession
from app.models.transaction import Transaction
from tests.fixtures.mock_emails import (
    ALL_MOCK_EMAILS,
    MOCK_BLACKLISTED_EMAIL,
    MOCK_CC_DEBIT_EMAIL,
    MOCK_NO_MATCH_EMAIL,
    MOCK_UNKNOWN_SENDER_EMAIL,
    MOCK_UPI_DEBIT_EMAIL,
    MOCK_UPI_P2P_EMAIL,
)


def test_ingestion_creates_transactions(db_session):
    messages = [MOCK_UPI_DEBIT_EMAIL, MOCK_CC_DEBIT_EMAIL]
    result = run_ingestion(db_session, mock_messages=messages)
    assert result.created == 2
    assert result.processed == 2


def test_ingestion_reports_and_retries_finalized_period_messages(
    db_session,
):
    db_session.add(
        AuditSession(
            period_year=2026,
            period_month=2,
            status="finalized",
        )
    )
    db_session.commit()

    result = run_ingestion(
        db_session,
        mock_messages=[MOCK_UPI_DEBIT_EMAIL],
    )

    assert result.created == 0
    assert result.skipped_finalized_period == 1
    assert result.source_status == "partial"
    assert result.retryable is True
    assert (
        db_session.query(Transaction)
        .filter_by(email_message_id=MOCK_UPI_DEBIT_EMAIL["id"])
        .first()
        is None
    )
    assert result.to_dict()["skipped_finalized_period"] == 1


def test_finalized_period_does_not_advance_gmail_cursor(
    db_session,
    monkeypatch,
):
    db_session.add(
        AuditSession(
            period_year=2026,
            period_month=2,
            status="finalized",
        )
    )
    db_session.commit()
    existing_history = (
        db_session.query(AppSetting)
        .filter_by(key="last_gmail_history_id")
        .first()
    )
    history_before = existing_history.value if existing_history else None
    existing_last_run = (
        db_session.query(AppSetting)
        .filter_by(key="last_ingestion_run")
        .first()
    )
    last_run_before = existing_last_run.value if existing_last_run else None
    monkeypatch.setattr(
        "app.core.ingestion.fetch_messages",
        lambda **kwargs: GmailFetchResult(
            messages=[MOCK_UPI_DEBIT_EMAIL],
            history_id="history-after-blocked-message",
        ),
    )

    result = run_ingestion(db_session)

    assert result.source_status == "partial"
    assert result.retryable is True
    history_after = (
        db_session.query(AppSetting)
        .filter_by(key="last_gmail_history_id")
        .first()
    )
    last_run_after = (
        db_session.query(AppSetting)
        .filter_by(key="last_ingestion_run")
        .first()
    )
    assert (history_after.value if history_after else None) == history_before
    assert (last_run_after.value if last_run_after else None) == last_run_before


def test_initial_sync_remains_incomplete_when_finalized_rows_are_held(
    db_session,
    monkeypatch,
):
    db_session.add(
        AuditSession(
            period_year=2026,
            period_month=2,
            status="finalized",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.core.ingestion.fetch_messages",
        lambda **kwargs: GmailFetchResult(
            messages=[MOCK_UPI_DEBIT_EMAIL],
            history_id="history-after-blocked-message",
        ),
    )

    result = run_initial_sync(db_session)

    assert result.source_status == "partial"
    assert (
        db_session.query(AppSetting)
        .filter_by(key="initial_sync_completed")
        .one()
        .value
        == "false"
    )


def test_ingestion_skips_blacklisted(db_session):
    messages = [MOCK_BLACKLISTED_EMAIL]
    result = run_ingestion(db_session, mock_messages=messages)
    assert result.created == 0
    assert result.skipped_blacklist == 1


def test_ingestion_skips_unknown_sender(db_session):
    messages = [MOCK_UNKNOWN_SENDER_EMAIL]
    result = run_ingestion(db_session, mock_messages=messages)
    assert result.created == 0
    assert result.skipped_no_match == 1


def test_ingestion_skips_no_pattern_match(db_session):
    messages = [MOCK_NO_MATCH_EMAIL]
    result = run_ingestion(db_session, mock_messages=messages)
    assert result.created == 0
    assert result.skipped_no_match == 1


def test_ingestion_dedup_by_message_id(db_session):
    messages = [MOCK_UPI_DEBIT_EMAIL]
    result1 = run_ingestion(db_session, mock_messages=messages)
    assert result1.created == 1

    result2 = run_ingestion(db_session, mock_messages=messages)
    assert result2.created == 0
    assert result2.skipped_duplicate == 1


def test_ingestion_all_mock_emails(db_session):
    result = run_ingestion(db_session, mock_messages=ALL_MOCK_EMAILS)
    # UPI debit + UPI P2P + CC debit = 3 created
    assert result.created == 3
    # Blacklisted = 1
    assert result.skipped_blacklist == 1
    # Unknown sender (1) + no match (1) = 2
    assert result.skipped_no_match == 2
    assert result.processed == 6


def test_ingestion_p2p_detection(db_session):
    messages = [MOCK_UPI_P2P_EMAIL]
    result = run_ingestion(db_session, mock_messages=messages)
    assert result.created == 1

    from app.models.transaction import Transaction
    txn = db_session.query(Transaction).filter_by(source='gmail').first()
    assert txn is not None
    assert txn.vpa_handle == '9876543210@ybl'


def test_ingestion_stores_correct_fields(db_session):
    messages = [MOCK_UPI_DEBIT_EMAIL]
    run_ingestion(db_session, mock_messages=messages)

    from app.models.transaction import Transaction
    txn = db_session.query(Transaction).filter_by(email_message_id='mock_upi_001').first()
    assert txn is not None
    assert txn.amount == 350.00
    assert txn.merchant_normalized == 'SWIGGY FOOD ORDER'
    assert txn.instrument == 'upi'
    assert txn.source == 'gmail'
    assert txn.type == 'debit'
    assert txn.checksum_source is not None
    assert txn.checksum_canonical is not None


def test_ingestion_cc_stores_correct_fields(db_session):
    messages = [MOCK_CC_DEBIT_EMAIL]
    run_ingestion(db_session, mock_messages=messages)

    from app.models.transaction import Transaction
    txn = db_session.query(Transaction).filter_by(email_message_id='mock_cc_001').first()
    assert txn is not None
    assert txn.amount == 2499.00
    assert txn.merchant_normalized == 'AMAZON PAY'
    assert txn.instrument == 'credit_card'
    assert txn.source == 'gmail'


def test_ingestion_api_trigger(auth_client):
    """Test the ingest endpoint returns error when Gmail not connected."""
    # Ensure Gmail is disconnected first
    auth_client.post("/api/v1/auth/gmail/disconnect")
    resp = auth_client.post("/api/v1/ingest/gmail")
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


def test_ingestion_status_api(auth_client):
    resp = auth_client.get("/api/v1/ingest/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "gmail_connected" in data
    assert "last_run" in data


def test_gmail_setup_error_is_safe_and_nontechnical(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.client_config_available",
        lambda: False,
    )
    response = auth_client.get("/api/v1/auth/gmail/url")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "not configured" in detail
    assert "client_secret" not in detail
    assert "data/" not in detail


def _source_transaction(db_session, *, source: str, suffix: str):
    from app.models.account import Account
    from app.models.transaction import Transaction

    account = db_session.query(Account).first()
    transaction = Transaction(
        id=f"txn-{source}-{suffix}",
        date=date(2026, 1, 10),
        raw_text=f"Synthetic {source} transaction {suffix}",
        merchant_raw="SYNTHETIC MERCHANT",
        merchant_normalized="SYNTHETIC MERCHANT",
        amount=100,
        type="debit",
        instrument="upi",
        account_id=account.id,
        source=source,
    )
    db_session.add(transaction)
    db_session.commit()
    return transaction


def test_gmail_disconnect_without_deletion_needs_no_pin(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.gmail_service.disconnect",
        lambda: True,
    )
    response = auth_client.post("/api/v1/auth/gmail/disconnect", json={})
    assert response.status_code == 200
    assert response.json()["deleted_transactions"] == 0


def test_gmail_data_deletion_requires_current_pin_and_exact_confirmation(
    auth_client,
    db_session,
    monkeypatch,
):
    gmail_transaction = _source_transaction(db_session, source="gmail", suffix="1")
    statement_transaction = _source_transaction(
        db_session, source="statement", suffix="1"
    )
    gmail_transaction_id = gmail_transaction.id
    statement_transaction_id = statement_transaction.id
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.gmail_service.disconnect",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.create_backup",
        lambda db_path, backup_dir: "godfin_backup_test.db",
    )

    wrong_pin = auth_client.post(
        "/api/v1/auth/gmail/disconnect",
        json={
            "clear_data": True,
            "pin": "9999",
            "confirmation": "DELETE GMAIL DATA",
        },
    )
    assert wrong_pin.status_code == 403

    wrong_confirmation = auth_client.post(
        "/api/v1/auth/gmail/disconnect",
        json={
            "clear_data": True,
            "pin": "4826",
            "confirmation": "delete",
        },
    )
    assert wrong_confirmation.status_code == 400

    accepted = auth_client.post(
        "/api/v1/auth/gmail/disconnect",
        json={
            "clear_data": True,
            "pin": "4826",
            "confirmation": "DELETE GMAIL DATA",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["deleted_transactions"] == 1
    assert accepted.json()["backup_filename"] == "godfin_backup_test.db"

    from app.models.transaction import Transaction
    db_session.expire_all()
    assert db_session.query(Transaction).filter_by(id=gmail_transaction_id).first() is None
    assert db_session.query(Transaction).filter_by(id=statement_transaction_id).first() is not None


def test_retired_manual_oauth_endpoint_is_absent(auth_client):
    response = auth_client.post(
        "/api/v1/auth/gmail/manual-code",
        json={"code": "never-used"},
    )
    assert response.status_code == 404


def test_ingestion_status_rejects_legacy_python_repr(auth_client, db_session):
    for key, value in (
        ("ingest_now_status", "completed"),
        ("ingest_now_result", "{'created': 1}"),
    ):
        setting = db_session.query(AppSetting).filter_by(key=key).first()
        if setting is None:
            db_session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
    db_session.commit()

    response = auth_client.get("/api/v1/ingest/gmail/range/status")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["result"] is None
