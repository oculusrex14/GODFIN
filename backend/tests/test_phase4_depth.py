from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from app.core.encryption import decrypt
from app.core.opendataloader_benchmark import (
    ExtractionBenchmarkCase,
    compare_extraction_results,
)
from app.core.reward_pilot import (
    projected_participant_payout,
    validate_redacted_payload,
)
from app.models.account import Account
from app.models.app_setting import AppSetting
from app.models.net_worth import NetWorthItem
from app.models.subscription import Subscription
from app.models.transaction import Transaction


def _set_setting(db, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _activate_tier(db, tier: str) -> None:
    _set_setting(db, "license_tier", tier)
    _set_setting(db, "license_status", "active")
    _set_setting(db, "license_verified_at", datetime.now(UTC).isoformat())
    db.commit()


def _account(db) -> Account:
    account = db.query(Account).first()
    assert account is not None
    return account


def _transaction(
    db,
    account: Account,
    *,
    transaction_date: date,
    amount: float,
    transaction_type: str = "debit",
    category: str = "FOOD & DINING",
    is_income: bool = False,
    is_recurring: bool = False,
) -> Transaction:
    item = Transaction(
        date=transaction_date,
        raw_text="REDACTED FIXTURE",
        merchant_raw="REDACTED",
        merchant_normalized="REDACTED",
        amount=amount,
        type=transaction_type,
        instrument="bank",
        account_id=account.id,
        category=category,
        is_income=is_income,
        is_recurring=is_recurring,
        source="manual",
    )
    db.add(item)
    return item


def test_net_worth_is_max_only_and_manual_values_are_local(
    auth_client, db_session
):
    _activate_tier(db_session, "pro")
    denied = auth_client.get("/api/v1/net-worth")
    assert denied.status_code == 403

    _activate_tier(db_session, "max")
    asset = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Emergency cash",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "manual_value": 250000,
            "currency": "INR",
            "valuation_source": "User-entered bank balance",
            "valued_at": date.today().isoformat(),
            "expires_on": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert asset.status_code == 201, asset.text
    liability = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Education loan",
            "item_type": "liability",
            "asset_class": "debt",
            "valuation_mode": "manual",
            "manual_value": 50000,
            "currency": "INR",
            "valuation_source": "Latest lender statement",
        },
    )
    assert liability.status_code == 201, liability.text

    summary = auth_client.get("/api/v1/net-worth")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_assets"] == 250000
    assert payload["total_liabilities"] == 50000
    assert payload["net_worth"] == 200000
    assert payload["base_currency"] == "INR"
    assert all("provenance" in item for item in payload["items"])


def test_market_data_key_is_encrypted_and_never_returned(
    auth_client, db_session
):
    _activate_tier(db_session, "max")
    response = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"api_key": "td-secret-value", "base_currency": "USD"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "provider": "Twelve Data",
        "configured": True,
        "base_currency": "USD",
        "key_storage": "encrypted_local",
    }
    stored = (
        db_session.query(AppSetting).filter_by(key="twelve_data_api_key").first()
    )
    assert stored is not None
    assert stored.value != "td-secret-value"
    assert decrypt(stored.value) == "td-secret-value"
    status = auth_client.get("/api/v1/net-worth/market-data/config/status")
    assert status.status_code == 200
    assert "td-secret-value" not in status.text


def test_live_quote_saves_price_exchange_rate_and_provenance(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import net_worth as net_worth_endpoint

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params):
            assert params["apikey"] == "td-fixture-key"
            if url.endswith("/price"):
                assert params["symbol"] == "AAPL"
                return FakeResponse({"price": "100"})
            assert url.endswith("/exchange_rate")
            assert params["symbol"] == "USD/INR"
            return FakeResponse({"rate": 80})

    monkeypatch.setattr(net_worth_endpoint.httpx, "Client", FakeClient)
    _activate_tier(db_session, "max")
    configured = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"api_key": "td-fixture-key", "base_currency": "INR"},
    )
    assert configured.status_code == 200
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Fixture shares",
            "item_type": "asset",
            "asset_class": "stock",
            "valuation_mode": "market",
            "symbol": "AAPL",
            "quantity": 2,
            "currency": "USD",
        },
    )
    assert created.status_code == 201, created.text
    refreshed = auth_client.post(
        f"/api/v1/net-worth/{created.json()['id']}/refresh"
    )
    assert refreshed.status_code == 200, refreshed.text
    payload = refreshed.json()
    assert payload["value_base"] == 16000
    assert payload["provenance"] == "live_quote"
    assert payload["source"] == "Twelve Data"
    assert payload["quote_history"][0]["unit_price"] == 100
    assert payload["quote_history"][0]["exchange_rate_to_base"] == 80


def test_illiquid_valuations_require_source_and_expiry(auth_client, db_session):
    _activate_tier(db_session, "max")
    rejected = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Land parcel",
            "item_type": "asset",
            "asset_class": "land",
            "valuation_mode": "manual",
            "manual_value": 1000000,
            "currency": "INR",
        },
    )
    assert rejected.status_code == 400
    accepted = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Land parcel",
            "item_type": "asset",
            "asset_class": "land",
            "valuation_mode": "manual",
            "manual_value": 1000000,
            "currency": "INR",
            "valuation_source": "Registered valuer report",
            "valued_at": date.today().isoformat(),
            "expires_on": (date.today() + timedelta(days=180)).isoformat(),
        },
    )
    assert accepted.status_code == 201, accepted.text


def test_behavior_insights_are_explainable_correctable_and_exportable(
    auth_client, db_session
):
    _activate_tier(db_session, "max")
    account = _account(db_session)
    today = date.today()
    for month_offset in range(6):
        month_date = today - timedelta(days=month_offset * 28)
        _transaction(
            db_session,
            account,
            transaction_date=month_date,
            amount=100000,
            transaction_type="credit",
            category="INCOME",
            is_income=True,
        )
        _transaction(
            db_session,
            account,
            transaction_date=month_date,
            amount=40000 + month_offset * 1000,
        )
    db_session.add(
        Subscription(
            name="Fixture subscription",
            amount=500,
            currency="INR",
            frequency="monthly",
            is_active=True,
        )
    )
    db_session.add(
        NetWorthItem(
            name="Cash buffer",
            item_type="asset",
            asset_class="cash",
            valuation_mode="manual",
            manual_value=120000,
            currency="INR",
            valued_at=today,
        )
    )
    db_session.commit()

    configured = auth_client.put(
        "/api/v1/behavior-insights/config",
        json={"monthly_budget": 50000},
    )
    assert configured.status_code == 200, configured.text
    payload = configured.json()
    assert len(payload["metrics"]) == 7
    assert {
        "savings_consistency",
        "cash_flow_volatility",
        "discretionary_ratio",
        "budget_adherence",
        "subscription_load",
        "buffer_coverage",
        "routine_stability",
    } == {metric["key"] for metric in payload["metrics"]}
    assert all(metric["formula"] and metric["evidence"] for metric in payload["metrics"])
    assert [metric["difficulty"] for metric in payload["metrics"]] == [
        "easy", "easy", "easy", "intermediate", "intermediate", "advanced", "advanced"
    ]
    assert len(payload["reflections"]) >= 4
    assert all(
        item["question"] and item["action"] and item["evidence"]
        for item in payload["reflections"]
    )
    assert "never used for advertising" in payload["policy"]

    corrected = auth_client.put(
        "/api/v1/behavior-insights/discretionary_ratio",
        json={"hidden": True, "correction_note": "One category is still being reviewed."},
    )
    assert corrected.status_code == 200
    metric = next(
        item
        for item in corrected.json()["metrics"]
        if item["key"] == "discretionary_ratio"
    )
    assert metric["hidden"] is True
    assert metric["correction_note"] == "One category is still being reviewed."

    exported = auth_client.get("/api/v1/behavior-insights/export")
    assert exported.status_code == 200
    assert "Months your income covered spending" in exported.text
    reset = auth_client.post("/api/v1/behavior-insights/reset")
    assert reset.status_code == 200
    assert all(not item["hidden"] for item in reset.json()["metrics"])


def test_sponsor_card_is_static_free_only_and_financially_isolated(
    auth_client, db_session
):
    _set_setting(db_session, "feature_sponsor_card", "true")
    db_session.commit()
    free = auth_client.get("/api/v1/behavior-insights/sponsor/card")
    assert free.status_code == 200
    assert free.json()["visible"] is True
    assert free.json()["personalized"] is False
    assert free.json()["third_party_scripts"] is False
    assert free.json()["uses_financial_data"] is False

    _activate_tier(db_session, "max")
    paid = auth_client.get("/api/v1/behavior-insights/sponsor/card")
    assert paid.status_code == 200
    assert paid.json()["visible"] is False


def test_reward_pilot_preview_is_opt_in_coarse_and_redacted(
    auth_client, db_session
):
    _set_setting(db_session, "feature_reward_pilot", "true")
    account = _account(db_session)
    today = date.today()
    _transaction(
        db_session,
        account,
        transaction_date=today - timedelta(days=89),
        amount=1234.56,
    )
    _transaction(
        db_session,
        account,
        transaction_date=today,
        amount=9876.54,
        is_recurring=True,
    )
    db_session.commit()

    before_consent = auth_client.get("/api/v1/reward-pilot/preview")
    assert before_consent.status_code == 409
    consent = auth_client.put(
        "/api/v1/reward-pilot/consent", json={"consented": True}
    )
    assert consent.status_code == 200
    response = auth_client.get("/api/v1/reward-pilot/preview")
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["eligible"] is True
    assert preview["redaction_checks"]["passed"] is True
    serialized = json.dumps(preview["payload"]).lower()
    for forbidden in (
        "raw_text",
        "merchant",
        "account",
        "card",
        "email",
        "phone",
        '"date"',
        '"amount"',
        "balance",
        "1234.56",
        "9876.54",
    ):
        assert forbidden not in serialized
    assert validate_redacted_payload(preview["payload"]) == []

    unconfigured = auth_client.post("/api/v1/reward-pilot/submit")
    assert unconfigured.status_code == 503


def test_payout_policy_caps_value_and_keeps_identity_outside_payload():
    assert projected_participant_payout(
        accepted_bundle=True,
        new_template_families=100,
        material_variants=100,
    ) == 300
    assert validate_redacted_payload({"email": "someone@example.com"})


def test_opendataloader_requires_a_material_reconciliation_gain():
    insufficient = compare_extraction_results([])
    assert insufficient["decision"] == "insufficient_evidence"
    result = compare_extraction_results(
        [
            ExtractionBenchmarkCase(
                fixture_id=f"redacted-{index}",
                current_reconciled=index < 8,
                candidate_reconciled=index < 9,
                current_elapsed_ms=20,
                candidate_elapsed_ms=40,
            )
            for index in range(10)
        ],
        minimum_gain=0.05,
    )
    assert result["decisive_metric"] == (
        "complete_reconciliation_without_manual_correction"
    )
    assert result["ship_candidate"] is True


def test_phase4_feature_flags_expose_safe_defaults(auth_client):
    response = auth_client.get("/api/v1/system/feature-flags")
    assert response.status_code == 200
    features = response.json()["features"]
    assert features["net_worth"] is True
    assert features["behavior_insights"] is True
    assert features["reward_pilot"] is False
    assert features["sponsor_card"] is False
    assert response.json()["extractors"]["opendataloader"]["shipped"] is False
