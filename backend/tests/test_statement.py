from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.reconciliation import (
    ReconciliationMatch,
    reconcile_statement,
    import_new_transactions,
)
from app.core.statement_parser import (
    StatementTransaction,
    ParsedTransaction,
    _parse_amount,
    _parse_statement_date,
)
from app.models.income_source import IncomeSource
from app.models.audit_session import AuditSession
from app.models.transaction import Transaction
from app.seed import CC_ACCOUNT_ID, SAVINGS_ACCOUNT_ID


# --- Statement parser utilities ---

def test_parse_statement_date_ddmmyyyy():
    assert _parse_statement_date('15/01/2025') == date(2025, 1, 15)


def test_parse_statement_date_ddmmyy():
    assert _parse_statement_date('15/01/25') == date(2025, 1, 15)


def test_parse_statement_date_invalid():
    assert _parse_statement_date('not-a-date') is None


def test_parse_statement_date_empty():
    assert _parse_statement_date('') is None


def test_parse_amount_simple():
    assert _parse_amount('350.00') == 350.00


def test_parse_amount_comma():
    assert _parse_amount('1,499.00') == 1499.00


def test_parse_amount_empty():
    assert _parse_amount('') is None


# --- Reconciliation ---

def test_reconcile_exact_match(db_session):
    # Create existing transaction
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2025, 1, 15),
        raw_text='Gmail: SWIGGY 350.00',
        merchant_raw='SWIGGY FOOD ORDER',
        merchant_normalized='SWIGGY FOOD ORDER',
        amount=350.00,
        type='debit',
        instrument='credit_card',
        account_id=CC_ACCOUNT_ID,
        source='gmail',
    )
    db_session.add(txn)
    db_session.flush()

    statement_txns = [
        StatementTransaction(
            date=date(2025, 1, 15),
            description='SWIGGY FOOD ORDER',
            amount=350.00,
            txn_type='debit',
        ),
    ]

    result = reconcile_statement(db_session, statement_txns, CC_ACCOUNT_ID)
    assert result.total_matched >= 1
    assert result.matches[0].existing_txn.id == txn.id
    assert result.matches[0].match_score >= 0.70


def test_reconcile_possible_match(db_session):
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2025, 1, 15),
        raw_text='Gmail: AMAZON 2499.00',
        merchant_raw='AMAZON PAY',
        merchant_normalized='AMAZON PAY',
        amount=2499.00,
        type='debit',
        instrument='credit_card',
        account_id=CC_ACCOUNT_ID,
        source='gmail',
    )
    db_session.add(txn)
    db_session.flush()

    # Different merchant name but same amount and close date
    statement_txns = [
        StatementTransaction(
            date=date(2025, 1, 16),
            description='AMAZON MARKETPLACE',
            amount=2499.00,
            txn_type='debit',
        ),
    ]

    result = reconcile_statement(db_session, statement_txns, CC_ACCOUNT_ID)
    # Could be matched or possible depending on fuzzy score
    assert result.total_matched + len(result.potential_duplicates) >= 1


def test_reconcile_new_transaction(db_session):
    statement_txns = [
        StatementTransaction(
            date=date(2025, 1, 20),
            description='NETFLIX SUBSCRIPTION',
            amount=199.00,
            txn_type='debit',
        ),
    ]

    result = reconcile_statement(db_session, statement_txns, CC_ACCOUNT_ID)
    assert result.total_new == 1
    assert len(result.new_transactions) == 1


def test_reconcile_income_detection(db_session):
    statement_txns = [
        StatementTransaction(
            date=date(2025, 1, 1),
            description='SALARY CREDIT',
            amount=75000.00,
            txn_type='credit',
            is_income=True,
        ),
        StatementTransaction(
            date=date(2025, 1, 5),
            description='SWIGGY',
            amount=350.00,
            txn_type='debit',
        ),
    ]

    result = reconcile_statement(db_session, statement_txns, SAVINGS_ACCOUNT_ID)
    # Income transactions appear as matches or new transactions with is_income=True
    income_txns = [t for t in result.new_transactions if t.is_income]
    assert len(income_txns) == 1
    assert income_txns[0].amount == 75000.00


def test_reconcile_empty(db_session):
    result = reconcile_statement(db_session, [], 'hdfc_savings')
    assert result.total_matched == 0
    assert result.total_new == 0
    assert len(result.matches) == 0
    assert len(result.new_transactions) == 0


# --- Import new transactions ---

def test_import_new_transactions(db_session):
    parsed = ParsedTransaction(
        date=date(2025, 1, 20),
        description='NETFLIX SUBSCRIPTION',
        amount=199.00,
        type='debit',
    )

    created = import_new_transactions(db_session, [parsed], CC_ACCOUNT_ID)
    assert len(created) == 1
    txn = db_session.query(Transaction).filter_by(source='statement_upload').first()
    assert txn is not None
    assert txn.amount == 199.00
    assert txn.instrument == 'statement'


def test_statement_import_rejects_entire_batch_for_finalized_period(
    db_session,
):
    db_session.add(
        AuditSession(
            period_year=2025,
            period_month=1,
            status="finalized",
        )
    )
    db_session.commit()
    transactions = [
        ParsedTransaction(
            date=date(2025, 1, 20),
            description="BLOCKED JANUARY ROW",
            amount=199.00,
            type="debit",
        ),
        ParsedTransaction(
            date=date(2025, 2, 20),
            description="WRITABLE FEBRUARY ROW",
            amount=299.00,
            type="debit",
        ),
    ]

    with pytest.raises(
        Exception,
        match="(?i)finalized.*reopen|reopen.*finalized",
    ):
        import_new_transactions(db_session, transactions, CC_ACCOUNT_ID)

    assert (
        db_session.query(Transaction)
        .filter(Transaction.source == "statement_upload")
        .count()
        == 0
    )


def test_import_returns_structured_errors_instead_of_500(
    auth_client,
    monkeypatch,
):
    from app.api.v1.endpoints import statement as statement_endpoint

    async def fake_read_and_parse(file, password):
        return SimpleNamespace(
            statement_type="hdfc_savings",
            source_digest="a" * 64,
        )

    monkeypatch.setattr(statement_endpoint, "_read_and_parse", fake_read_and_parse)
    monkeypatch.setattr(
        statement_endpoint.ParsedStatement,
        "from_statement_result",
        lambda value: object(),
    )
    monkeypatch.setattr(
        statement_endpoint.ReconciliationService,
        "reconcile",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )

    response = auth_client.post(
        "/api/v1/ingest/upload/import",
        files={"file": ("statement.pdf", b"%PDF-test", "application/pdf")},
        data={
            "confirm_reconciled": "true",
            "accepted_fingerprint": "a" * 64,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] == 0
    assert data["skipped_dup"] == 0
    assert data["classified"] == 0
    assert data["review_queue"] == 0
    assert data["errors"] == ["Import could not be completed: simulated failure"]


def test_statement_import_endpoint_returns_409_for_finalized_period(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import statement as statement_endpoint

    db_session.add(
        AuditSession(
            period_year=2025,
            period_month=1,
            status="finalized",
        )
    )
    db_session.commit()
    parsed_transaction = ParsedTransaction(
        date=date(2025, 1, 20),
        description="BLOCKED JANUARY ROW",
        amount=199.00,
        type="debit",
    )

    async def fake_read_and_parse(file, password):
        return SimpleNamespace(
            statement_type="hdfc_savings",
            source_digest="b" * 64,
        )

    monkeypatch.setattr(
        statement_endpoint,
        "_read_and_parse",
        fake_read_and_parse,
    )
    monkeypatch.setattr(
        statement_endpoint.ParsedStatement,
        "from_statement_result",
        lambda value: object(),
    )
    monkeypatch.setattr(
        statement_endpoint.ReconciliationService,
        "reconcile",
        lambda *args, **kwargs: SimpleNamespace(
            new_transactions=[parsed_transaction],
            duplicate_transactions=[],
            potential_duplicates=[],
            total_parsed=1,
        ),
    )

    response = auth_client.post(
        "/api/v1/ingest/upload/import",
        files={"file": ("statement.pdf", b"%PDF-test", "application/pdf")},
        data={
            "confirm_reconciled": "true",
            "accepted_fingerprint": "b" * 64,
        },
    )

    assert response.status_code == 409
    assert "reopen" in response.json()["detail"].lower()
    assert (
        db_session.query(Transaction)
        .filter(Transaction.source == "statement_upload")
        .count()
        == 0
    )

# --- Income source CRUD ---

def test_create_income_source(auth_client):
    resp = auth_client.post("/api/v1/income-sources", json={
        "source_name": "Salary",
        "expected_amount": 75000,
        "frequency": "monthly",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_name"] == "Salary"
    assert data["expected_amount"] == 75000


def test_list_income_sources(auth_client):
    auth_client.post("/api/v1/income-sources", json={
        "source_name": "Freelance",
        "frequency": "irregular",
    })

    resp = auth_client.get("/api/v1/income-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_update_income_source(auth_client):
    resp = auth_client.post("/api/v1/income-sources", json={
        "source_name": "Side Gig",
        "frequency": "monthly",
    })
    source_id = resp.json()["id"]

    resp = auth_client.put(f"/api/v1/income-sources/{source_id}", json={
        "expected_amount": 10000,
    })
    assert resp.status_code == 200


def test_delete_income_source(auth_client):
    resp = auth_client.post("/api/v1/income-sources", json={
        "source_name": "Temp Job",
        "frequency": "irregular",
    })
    source_id = resp.json()["id"]

    resp = auth_client.delete(f"/api/v1/income-sources/{source_id}")
    assert resp.status_code == 204


def test_delete_income_source_not_found(auth_client):
    resp = auth_client.delete("/api/v1/income-sources/nonexistent")
    assert resp.status_code == 404


# --- Dashboard chart endpoints ---

def test_category_breakdown(auth_client):
    resp = auth_client.get("/api/v1/dashboard/category-breakdown?month=2025-01")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_spending_trend(auth_client):
    resp = auth_client.get("/api/v1/dashboard/spending-trend?months=6")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    assert "month" in data[0]
    assert "spend" in data[0]
    assert "income" in data[0]
