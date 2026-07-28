from __future__ import annotations

from app.core.ingestion import run_ingestion
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
