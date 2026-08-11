from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.account import Account
from app.models.app_setting import AppSetting
from tests.license_helpers import install_test_license


@pytest.fixture(autouse=True)
def _fixed_subscription_rates(monkeypatch):
    from app.api.v1.endpoints import subscriptions
    from app.core.fx import FxRateSnapshot

    async def fixed_rates(_currencies, **_kwargs):
        return FxRateSnapshot(
            rates_to_inr={"INR": 1.0, "USD": 85.0, "EUR": 92.0, "GBP": 107.0},
            as_of=date.today(),
            provider="Deterministic test provider",
            source_url="https://example.invalid/rates",
            age_days=0,
            stale=False,
            status="available",
        )

    monkeypatch.setattr(subscriptions, "_fetch_exchange_rates", fixed_rates)


def _raw_json_request(client, method: str, path: str, payload: dict):
    return client.request(
        method,
        path,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def _set_setting(db, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _activate_max(db) -> None:
    install_test_license(db, "max")


@pytest.mark.parametrize(
    "amount", [-1, 0, -0.0, float("nan"), float("inf"), float("-inf"), 1e16]
)
def test_subscription_rejects_unsafe_amounts(auth_client, amount):
    response = _raw_json_request(
        auth_client,
        "POST",
        "/api/v1/subscriptions",
        {
            "name": "Boundary fixture",
            "amount": amount,
            "currency": "INR",
            "frequency": "monthly",
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency", "ZZZ"),
        ("frequency", "whenever"),
        ("next_payment_date", "2026-02-30"),
    ],
)
def test_subscription_rejects_invalid_semantics(auth_client, field, value):
    payload = {
        "name": "Boundary fixture",
        "amount": 499,
        "currency": "INR",
        "frequency": "monthly",
    }
    payload[field] = value

    response = auth_client.post("/api/v1/subscriptions", json=payload)

    assert response.status_code == 422, response.text


def test_subscription_update_rejects_non_finite_amount(auth_client):
    created = auth_client.post(
        "/api/v1/subscriptions",
        json={"name": "Update fixture", "amount": 499},
    )
    assert created.status_code == 201, created.text

    response = _raw_json_request(
        auth_client,
        "PUT",
        f"/api/v1/subscriptions/{created.json()['id']}",
        {"amount": float("nan")},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "field", ["name", "amount", "currency", "frequency", "is_active"]
)
def test_subscription_update_rejects_null_required_fields(auth_client, field):
    created = auth_client.post(
        "/api/v1/subscriptions",
        json={"name": "Null update fixture", "amount": 499},
    )
    assert created.status_code == 201, created.text

    response = auth_client.put(
        f"/api/v1/subscriptions/{created.json()['id']}",
        json={field: None},
    )

    assert response.status_code == 422, response.text


def test_subscription_normalizes_supported_currency(auth_client):
    response = auth_client.post(
        "/api/v1/subscriptions",
        json={
            "name": "Currency normalization fixture",
            "amount": 499,
            "currency": " usd ",
            "frequency": "monthly",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["currency"] == "USD"


@pytest.mark.parametrize("path", ["/api/v1/income", "/api/v1/income-sources"])
@pytest.mark.parametrize("amount", [-1, 0, float("nan"), float("inf"), 1e16])
def test_income_sources_reject_unsafe_expected_amounts(auth_client, path, amount):
    response = _raw_json_request(
        auth_client,
        "POST",
        path,
        {
            "source_name": "Income boundary fixture",
            "expected_amount": amount,
            "frequency": "monthly",
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("frequency", "sometimes"),
        ("next_expected_date", "2026-02-30"),
    ],
)
def test_primary_income_source_rejects_invalid_semantics(auth_client, field, value):
    payload = {
        "source_name": "Income boundary fixture",
        "expected_amount": 1000,
        "frequency": "monthly",
    }
    payload[field] = value

    response = auth_client.post("/api/v1/income", json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("path", ["/api/v1/income", "/api/v1/income-sources"])
def test_income_source_update_rejects_non_finite_amount(auth_client, path):
    frequency = "monthly"
    created = auth_client.post(
        path,
        json={
            "source_name": "Update boundary fixture",
            "expected_amount": 1000,
            "frequency": frequency,
        },
    )
    assert created.status_code == 201, created.text

    response = _raw_json_request(
        auth_client,
        "PUT",
        f"{path}/{created.json()['id']}",
        {"expected_amount": float("nan")},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "field", ["source_name", "frequency", "enforce_current_month", "is_active"]
)
def test_income_source_update_rejects_null_required_fields(auth_client, field):
    created = auth_client.post(
        "/api/v1/income",
        json={
            "source_name": "Null update fixture",
            "expected_amount": 1000,
            "frequency": "monthly",
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.put(
        f"/api/v1/income/{created.json()['id']}",
        json={field: None},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_amount", float("nan")),
        ("target_amount", float("inf")),
        ("target_amount", 1e16),
        ("current_saved", -1),
        ("current_saved", float("nan")),
        ("annual_return_rate", float("nan")),
        ("minimum_flexible_floor", float("inf")),
        ("deadline_date", "2026-02-30"),
        ("pressure_level", "maximum"),
    ],
)
def test_goal_rejects_unsafe_values(auth_client, field, value):
    payload = {
        "name": "Goal boundary fixture",
        "target_amount": 100000,
        "current_saved": 0,
        "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
    }
    payload[field] = value

    response = _raw_json_request(auth_client, "POST", "/api/v1/goals", payload)

    assert response.status_code == 422, response.text


def test_goal_update_rejects_past_deadline(auth_client):
    created = auth_client.post(
        "/api/v1/goals",
        json={
            "name": "Goal update fixture",
            "target_amount": 100000,
            "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.put(
        f"/api/v1/goals/{created.json()['id']}",
        json={"deadline_date": (date.today() - timedelta(days=1)).isoformat()},
    )

    assert response.status_code == 400, response.text


def test_goal_contribution_rejects_future_date(auth_client):
    created = auth_client.post(
        "/api/v1/goals",
        json={
            "name": "Contribution date fixture",
            "target_amount": 100000,
            "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.post(
        f"/api/v1/goals/{created.json()['id']}/contributions",
        json={
            "amount": 1000,
            "entry_type": "deposit",
            "contribution_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("amount", [0, -1, float("nan"), float("inf"), 1e16])
def test_goal_contribution_rejects_unsafe_amount(auth_client, amount):
    created = auth_client.post(
        "/api/v1/goals",
        json={
            "name": "Contribution amount fixture",
            "target_amount": 100000,
            "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    response = _raw_json_request(
        auth_client,
        "POST",
        f"/api/v1/goals/{created.json()['id']}/contributions",
        {"amount": amount, "entry_type": "deposit"},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", float("nan")),
        ("quantity", float("inf")),
        ("quantity", 1e16),
        ("manual_value", float("nan")),
        ("manual_value", float("inf")),
        ("manual_value", 1e16),
        ("exchange_rate_to_base", 1),
        ("currency", "ZZZ"),
        ("asset_class", "made_up_asset"),
        ("valued_at", "2026-02-30"),
    ],
)
def test_net_worth_rejects_unsafe_values(auth_client, db_session, field, value):
    _activate_max(db_session)
    payload = {
        "name": "Net worth boundary fixture",
        "item_type": "asset",
        "asset_class": "cash",
        "valuation_mode": "manual",
        "quantity": 1,
        "manual_value": 1000,
        "currency": "INR",
    }
    payload[field] = value

    response = _raw_json_request(auth_client, "POST", "/api/v1/net-worth", payload)

    assert response.status_code == 422, response.text


def test_net_worth_rejects_expiry_before_valuation(auth_client, db_session):
    _activate_max(db_session)
    response = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Date order fixture",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "manual_value": 1000,
            "currency": "INR",
            "valued_at": "2026-08-02",
            "expires_on": "2026-08-01",
        },
    )

    assert response.status_code == 400, response.text


def test_net_worth_accepts_current_iso_currency(auth_client, db_session):
    _activate_max(db_session)
    response = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "JPY cash fixture",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "manual_value": 1000,
            "currency": "jpy",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["currency"] == "JPY"


def test_net_worth_update_rejects_non_finite_quantity(auth_client, db_session):
    _activate_max(db_session)
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Update quantity fixture",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "manual_value": 1000,
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text

    response = _raw_json_request(
        auth_client,
        "PUT",
        f"/api/v1/net-worth/{created.json()['id']}",
        {"quantity": float("nan")},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "item_type",
        "asset_class",
        "valuation_mode",
        "quantity",
        "currency",
        "is_active",
    ],
)
def test_net_worth_update_rejects_null_required_fields(auth_client, db_session, field):
    _activate_max(db_session)
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Null update fixture",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "manual_value": 1000,
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.put(
        f"/api/v1/net-worth/{created.json()['id']}",
        json={field: None},
    )

    assert response.status_code == 422, response.text


def test_net_worth_rejects_non_finite_provider_quote(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import net_worth as net_worth_endpoint
    from app.models.net_worth import NetWorthQuote

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"close": "NaN", "currency": "INR"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(net_worth_endpoint.httpx, "Client", FakeClient)
    _activate_max(db_session)
    configured = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"api_key": "td-boundary-fixture", "base_currency": "INR"},
    )
    assert configured.status_code == 200, configured.text
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Provider quote fixture",
            "item_type": "asset",
            "asset_class": "stock",
            "valuation_mode": "market",
            "symbol": "AAPL",
            "quantity": 1,
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.post(f"/api/v1/net-worth/{created.json()['id']}/refresh")

    assert response.status_code == 502, response.text
    assert db_session.query(NetWorthQuote).count() == 0


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), 0, -1, 1e16])
def test_manual_transaction_rejects_unsafe_amount(auth_client, db_session, amount):
    account = db_session.query(Account).first()
    assert account is not None
    response = _raw_json_request(
        auth_client,
        "POST",
        "/api/v1/transactions",
        {
            "date": date.today().isoformat(),
            "merchant_raw": "Boundary fixture",
            "amount": amount,
            "type": "debit",
            "account_id": account.id,
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/stats?month=2026-13",
        "/api/v1/dashboard/category-breakdown?month=2026-00",
        "/api/v1/dashboard/spending-trend?month=2026-13",
        "/api/v1/income/stats?month=2026-13",
        "/api/v1/reports/summary?month=2026-13",
        "/api/v1/reports/detailed?month=2026-13",
        "/api/v1/reports/pdf/summary?month=2026-13",
        "/api/v1/reports/csv?month=2026-13",
        "/api/v1/cash-flow/calendar?month=2026-13",
    ],
)
def test_invalid_calendar_month_is_validation_error(auth_client, path):
    response = auth_client.get(path)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"start_date": "2026-02-30", "end_date": "2026-03-01"},
        {"start_date": "2026-03-01", "end_date": "2026-02-28"},
        {
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    ],
)
def test_gmail_range_rejects_invalid_dates_before_connection_check(
    auth_client, payload
):
    response = auth_client.post("/api/v1/ingest/gmail/range", json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("monthly_budget", [0, -1, float("nan"), float("inf"), 1e16])
def test_behavior_budget_rejects_unsafe_amount(auth_client, db_session, monthly_budget):
    _activate_max(db_session)
    response = _raw_json_request(
        auth_client,
        "PUT",
        "/api/v1/behavior-insights/config",
        {"monthly_budget": monthly_budget},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/review/nonexistent/chat",
            {"message": "Help", "history": [{"role": "system", "content": "x"}]},
        ),
        (
            "/api/v1/review/batch-resolve",
            {
                "items": [
                    {"id": str(index), "category": "HOUSING"} for index in range(201)
                ]
            },
        ),
        (
            "/api/v1/subscriptions/suggestions/nonexistent/decision",
            {"decision": "maybe", "snooze_days": 7},
        ),
    ],
)
def test_semantic_enums_and_collection_bounds_reject_invalid_payloads(
    auth_client, db_session, path, payload
):
    # Reach paid request validation rather than stopping at the entitlement
    # dependency for the AI-review case.
    _activate_max(db_session)
    response = auth_client.post(path, json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/subscriptions",
            {"name": "x" * 101, "amount": 499},
        ),
        (
            "/api/v1/income",
            {"source_name": "x" * 101, "expected_amount": 1000},
        ),
    ],
)
def test_financial_text_bounds_reject_oversized_payloads(auth_client, path, payload):
    response = auth_client.post(path, json=payload)

    assert response.status_code == 422, response.text
