from __future__ import annotations

from app.models.audit_log import AuditLog
from app.models.audit_session import AuditSession
from app.models.income_source import IncomeMatchSuggestion, IncomeSource
from app.models.transaction import Transaction
from app.core.ingestion import run_ingestion
from app.seed import CC_ACCOUNT_ID, SAVINGS_ACCOUNT_ID


def _transaction(auth_client, **overrides):
    payload = {
        "date": "2026-02-01",
        "merchant_raw": "ACME PAYROLL",
        "amount": 100000,
        "type": "credit",
        "account_id": SAVINGS_ACCOUNT_ID,
    }
    payload.update(overrides)
    response = auth_client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _source(auth_client, **overrides):
    payload = {
        "source_name": "ACME PAYROLL",
        "expected_amount": 100000,
        "frequency": "monthly",
        "effective_from": "2026-01-01",
        "amount_tolerance": 0.10,
        "confirmed_merchant_alias": "ACME PAYROLL",
    }
    payload.update(overrides)
    response = auth_client.post("/api/v1/income", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_expected_income_is_effective_dated_and_never_fabricates_actual_income(
    auth_client,
):
    _source(
        auth_client,
        source_name="Future salary",
        confirmed_merchant_alias="FUTURE EMPLOYER",
        effective_from="2026-08-01",
        enforce_current_month=True,
    )

    january = auth_client.get("/api/v1/income/stats?month=2026-01").json()
    august = auth_client.get("/api/v1/income/stats?month=2026-08").json()

    assert january["total_expected_monthly"] == 0
    assert january["total_detected_this_month"] == 0
    assert august["total_expected_monthly"] == 100000
    assert august["total_detected_this_month"] == 0


def test_historical_match_review_excludes_refunds_transfers_and_amount_only_guesses(
    auth_client,
    db_session,
):
    source = _source(auth_client)
    salary = _transaction(auth_client)
    _transaction(
        auth_client,
        merchant_raw="ACME PAYROLL REFUND",
        category="INCOME",
        subcategory="Refund",
    )
    _transaction(
        auth_client,
        merchant_raw="ACME PAYROLL OWN ACCOUNT",
        category="TRANSFERS",
        subcategory="Own Account Transfer",
    )
    _transaction(auth_client, merchant_raw="UNRELATED CREDIT")

    scan = auth_client.post(
        f"/api/v1/income/{source['id']}/matches/scan"
    )

    assert scan.status_code == 200, scan.text
    scan_data = scan.json()
    assert scan_data["scanned"] == 4
    assert scan_data["candidates"] == 1
    assert scan_data["strong"] == 1
    assert scan_data["excluded_unsafe"] == 2

    matches = auth_client.get(
        f"/api/v1/income/{source['id']}/matches"
    ).json()
    assert matches["total"] == 1
    candidate = matches["items"][0]
    assert candidate["transaction_id"] == salary["id"]
    assert candidate["strength"] == "strong"
    assert candidate["evidence"]
    original_raw = (
        db_session.query(Transaction.raw_text).filter_by(id=salary["id"]).scalar()
    )

    confirmed = auth_client.post(
        f"/api/v1/income/{source['id']}/matches/confirm",
        json={"suggestion_ids": [candidate["id"]], "subcategory": "Salary"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["updated"] == 1

    db_session.expire_all()
    transaction = db_session.query(Transaction).filter_by(id=salary["id"]).one()
    assert transaction.raw_text == original_raw
    assert transaction.category == "INCOME"
    assert transaction.subcategory == "Salary"
    assert transaction.semantic_type == "income"
    assert transaction.is_income is True
    audit = (
        db_session.query(AuditLog)
        .filter_by(
            transaction_id=salary["id"],
            field_changed="income_source_confirmation",
        )
        .one()
    )
    assert '"semantic_type":"unknown"' in audit.old_value
    assert f'"income_source_id":"{source["id"]}"' in audit.new_value

    # A retry is idempotent and a rescan does not duplicate the relationship.
    retried = auth_client.post(
        f"/api/v1/income/{source['id']}/matches/confirm",
        json={"suggestion_ids": [candidate["id"]], "subcategory": "Salary"},
    )
    assert retried.status_code == 200
    assert retried.json()["updated"] == 0
    auth_client.post(f"/api/v1/income/{source['id']}/matches/scan")
    db_session.expire_all()
    assert (
        db_session.query(IncomeMatchSuggestion)
        .filter_by(income_source_id=source["id"], transaction_id=salary["id"])
        .count()
        == 1
    )


def test_matcher_respects_account_payment_method_and_finalized_lock(
    auth_client,
    db_session,
):
    source = _source(
        auth_client,
        account_id=SAVINGS_ACCOUNT_ID,
        payment_rail="bank",
    )
    matched = _transaction(auth_client, instrument="bank")
    _transaction(auth_client, account_id=CC_ACCOUNT_ID, instrument="bank")
    _transaction(auth_client, merchant_raw="ACME PAYROLL", instrument="upi")
    locked = _transaction(
        auth_client,
        merchant_raw="ACME PAYROLL LOCKED",
        instrument="bank",
    )
    db_session.query(Transaction).filter_by(id=locked["id"]).update(
        {"is_locked": True}
    )
    db_session.commit()

    result = auth_client.post(
        f"/api/v1/income/{source['id']}/matches/scan"
    ).json()
    matches = auth_client.get(
        f"/api/v1/income/{source['id']}/matches"
    ).json()

    assert result["scanned"] == 3
    assert [item["transaction_id"] for item in matches["items"]] == [matched["id"]]


def test_income_coverage_comes_from_local_transaction_horizon(auth_client):
    assert auth_client.get("/api/v1/income/coverage").json() == {
        "earliest_transaction_date": None,
        "latest_transaction_date": None,
    }
    _transaction(auth_client, date="2025-11-20")
    _transaction(auth_client, date="2026-03-10")

    assert auth_client.get("/api/v1/income/coverage").json() == {
        "earliest_transaction_date": "2025-11-20",
        "latest_transaction_date": "2026-03-10",
    }


def test_income_source_date_and_account_validation(auth_client):
    reversed_period = auth_client.post(
        "/api/v1/income",
        json={
            "source_name": "Invalid dates",
            "frequency": "monthly",
            "effective_from": "2026-08-01",
            "effective_to": "2026-07-31",
        },
    )
    invalid_account = auth_client.post(
        "/api/v1/income",
        json={
            "source_name": "Invalid account",
            "frequency": "monthly",
            "account_id": "00000000-0000-4000-8000-000000000000",
        },
    )

    assert reversed_period.status_code == 422
    assert invalid_account.status_code == 400


def test_income_source_model_defaults_to_a_bounded_match_window(db_session):
    source = IncomeSource(source_name="Synthetic source", expected_amount=1000)
    db_session.add(source)
    db_session.commit()

    assert source.effective_from is not None
    assert source.effective_to is None
    assert source.amount_tolerance == 0.20


def _actual_period_payload(**overrides):
    payload = {
        "source_name": "Synthetic salary",
        "amount": 34000.0,
        "account_id": SAVINGS_ACCOUNT_ID,
        "subcategory": "Salary",
        "start_month": "2026-01",
        "end_month": "2026-07",
        "payment_day": 28,
        "note": "Owner-confirmed historical salary",
    }
    payload.update(overrides)
    return payload


def test_historical_actual_income_preview_confirmation_and_new_rate(auth_client):
    preview = auth_client.post(
        "/api/v1/income/actual/period/preview",
        json=_actual_period_payload(),
    )
    assert preview.status_code == 200, preview.text
    reviewed = preview.json()
    assert len(reviewed["entries"]) == 7
    assert reviewed["entries"][0] == {"date": "2026-01-28", "amount": 34000.0}
    assert reviewed["entries"][-1] == {"date": "2026-07-28", "amount": 34000.0}
    assert reviewed["total_amount"] == 238000.0

    confirmed = auth_client.post(
        "/api/v1/income/actual/period/confirm",
        json={
            **_actual_period_payload(),
            "preview_fingerprint": reviewed["preview_fingerprint"],
            "confirm": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["created"] == 7
    assert confirmed.json()["skipped_existing"] == 0

    for month in range(1, 8):
        dashboard = auth_client.get(
            "/api/v1/dashboard/stats",
            params={"month": f"2026-{month:02d}"},
        ).json()
        assert dashboard["month_income"] == 34000.0

    august = auth_client.post(
        "/api/v1/income/actual",
        json={
            "source_name": "Synthetic salary",
            "amount": 42000.0,
            "date": "2026-08-01",
            "account_id": SAVINGS_ACCOUNT_ID,
            "subcategory": "Salary",
        },
    )
    assert august.status_code == 201, august.text
    assert august.json()["created"] == 1
    assert auth_client.get(
        "/api/v1/dashboard/stats",
        params={"month": "2026-08"},
    ).json()["month_income"] == 42000.0
    assert auth_client.get(
        "/api/v1/dashboard/stats",
        params={"month": "2026-01"},
    ).json()["month_income"] == 34000.0

    repeated = auth_client.post(
        "/api/v1/income/actual/period/confirm",
        json={
            **_actual_period_payload(),
            "preview_fingerprint": reviewed["preview_fingerprint"],
            "confirm": True,
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] == 0
    assert repeated.json()["skipped_existing"] == 7


def test_expected_income_change_does_not_rewrite_actual_history(auth_client):
    source = _source(
        auth_client,
        expected_amount=34000.0,
        account_id=SAVINGS_ACCOUNT_ID,
    )
    recorded = auth_client.post(
        "/api/v1/income/actual",
        json={
            "source_name": source["source_name"],
            "income_source_id": source["id"],
            "amount": 34000.55,
            "date": "2026-01-28",
            "account_id": SAVINGS_ACCOUNT_ID,
            "subcategory": "Salary",
            "reference": "SYNTHETIC-REF",
        },
    )
    assert recorded.status_code == 201, recorded.text

    changed = auth_client.put(
        f"/api/v1/income/{source['id']}",
        json={"expected_amount": 50000.0},
    )
    assert changed.status_code == 200
    dashboard = auth_client.get(
        "/api/v1/dashboard/stats",
        params={"month": "2026-01"},
    ).json()
    assert dashboard["month_income"] == 34000.55


def test_historical_actual_income_batch_is_atomic_across_finalized_months(
    auth_client,
    db_session,
):
    db_session.add(
        AuditSession(period_year=2026, period_month=3, status="finalized")
    )
    db_session.commit()
    preview = auth_client.post(
        "/api/v1/income/actual/period/preview",
        json=_actual_period_payload(end_month="2026-03"),
    ).json()

    response = auth_client.post(
        "/api/v1/income/actual/period/confirm",
        json={
            **_actual_period_payload(end_month="2026-03"),
            "preview_fingerprint": preview["preview_fingerprint"],
            "confirm": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "FINALIZED_PERIOD_READ_ONLY"
    assert db_session.query(Transaction).filter_by(source="manual_income").count() == 0


def test_matching_gmail_salary_links_manual_actual_instead_of_double_counting(
    auth_client,
    db_session,
):
    recorded = auth_client.post(
        "/api/v1/income/actual",
        json={
            "source_name": "Synthetic salary",
            "amount": 34000.0,
            "date": "2026-02-10",
            "account_id": SAVINGS_ACCOUNT_ID,
            "subcategory": "Salary",
        },
    )
    assert recorded.status_code == 201
    transaction_id = recorded.json()["transaction_ids"][0]

    result = run_ingestion(
        db_session,
        mock_messages=[
            {
                "id": "manual-income-match-1",
                "sender": "alerts@hdfcbank.bank.in",
                "subject": "Transaction Alert",
                "body": (
                    "Dear Customer, Rs. 34,000.00 is successfully credited to "
                    "your account **0000 by VPA salary@ybl ACME SALARY on "
                    "10-02-26. Your UPI transaction reference number is "
                    "504123456780."
                ),
            }
        ],
    )

    db_session.expire_all()
    linked = db_session.query(Transaction).filter_by(id=transaction_id).one()
    assert result.created == 0
    assert result.skipped_duplicate == 1
    assert db_session.query(Transaction).count() == 1
    assert linked.reconciled is True
    assert linked.email_message_id == "manual-income-match-1"
    assert "reconciled_gmail" in linked.extraction_evidence
