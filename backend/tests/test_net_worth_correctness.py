from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import event, text

from app.core.fx import (
    FRANKFURTER_RATES_URL,
    FX_PROVIDER,
    FxRateSnapshot,
    FxRateUnavailable,
)
from app.core.time import utcnow_naive
from app.models.app_setting import AppSetting
from app.models.net_worth import NetWorthItem, NetWorthQuote


def _set_setting(db, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting is None:
        db.add(AppSetting(key=key, value=value))
    else:
        setting.value = value


def _activate_max(db, *, base_currency: str = "INR") -> None:
    _set_setting(db, "license_tier", "max")
    _set_setting(db, "license_status", "active")
    _set_setting(db, "license_verified_at", datetime.now().isoformat())
    _set_setting(db, "net_worth_base_currency", base_currency)
    db.commit()


def _snapshot(**rates: float) -> FxRateSnapshot:
    normalized = {"INR": 1.0, **rates}
    return FxRateSnapshot(
        rates_to_inr=normalized,
        as_of=date.today(),
        provider=FX_PROVIDER,
        source_url=FRANKFURTER_RATES_URL,
        age_days=0,
        stale=False,
        status="available",
    )


def _manual_payload(*, currency: str = "INR", value: float = 100) -> dict:
    return {
        "name": f"{currency} manual asset",
        "item_type": "asset",
        "asset_class": "cash",
        "valuation_mode": "manual",
        "manual_value": value,
        "currency": currency,
        "valuation_source": "Redacted test statement",
        "valued_at": date.today().isoformat(),
        "expires_on": (date.today() + timedelta(days=30)).isoformat(),
    }


def _market_item(db, *, currency: str = "USD", quantity: float = 2) -> NetWorthItem:
    item = NetWorthItem(
        name="Market fixture",
        item_type="asset",
        asset_class="stock",
        valuation_mode="market",
        symbol="AAPL",
        quantity=quantity,
        currency=currency,
    )
    db.add(item)
    db.flush()
    return item


def _quote(
    db,
    item: NetWorthItem,
    *,
    unit_price: float = 100,
    rate: float = 80,
    base_currency: str = "INR",
    quote_currency: str | None = None,
    quoted_at: datetime | None = None,
    expires_at: datetime | None = None,
    with_fx_provenance: bool = True,
) -> NetWorthQuote:
    now = quoted_at or utcnow_naive()
    foreign = (quote_currency or item.currency) != base_currency
    quote = NetWorthQuote(
        item_id=item.id,
        unit_price=unit_price,
        quote_currency=quote_currency or item.currency,
        exchange_rate_to_base=rate,
        total_value_base=999999,
        base_currency=base_currency,
        source="Twelve Data",
        source_url="https://twelvedata.com/docs/advanced",
        fx_rate_source=FX_PROVIDER if foreign and with_fx_provenance else None,
        fx_rate_source_url=(
            FRANKFURTER_RATES_URL if foreign and with_fx_provenance else None
        ),
        fx_rate_as_of=date.today() if foreign and with_fx_provenance else None,
        fx_rate_fetched_at=now if foreign and with_fx_provenance else None,
        quoted_at=now,
        expires_at=expires_at or now + timedelta(hours=24),
    )
    db.add(quote)
    db.commit()
    return quote


def test_manual_foreign_value_uses_verified_cross_rate_and_persists_provenance(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session)
    snapshot = _snapshot(USD=80)
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: snapshot,
    )

    response = auth_client.post(
        "/api/v1/net-worth",
        json=_manual_payload(currency="USD", value=100),
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["value_base"] == 8000
    assert payload["native_value"] == 100
    assert payload["exchange_rate_to_base"] == 80
    assert payload["conversion"]["provider"] == FX_PROVIDER
    stored = db_session.query(NetWorthItem).filter_by(id=payload["id"]).one()
    assert stored.fx_source_currency == "USD"
    assert stored.fx_base_currency == "INR"
    assert stored.fx_rate_source == FX_PROVIDER
    assert stored.fx_rate_source_url == FRANKFURTER_RATES_URL
    assert stored.fx_rate_as_of == date.today()
    assert stored.fx_rate_fetched_at is not None


def test_unsupported_manual_currency_is_saved_but_never_assumed_one_to_one(
    auth_client,
    db_session,
):
    _activate_max(db_session)

    created = auth_client.post(
        "/api/v1/net-worth",
        json=_manual_payload(currency="JPY", value=1000),
    )

    assert created.status_code == 201, created.text
    assert created.json()["available"] is False
    assert created.json()["value_base"] is None
    assert "JPY" in created.json()["unavailable_reason"]
    summary = auth_client.get("/api/v1/net-worth")
    assert summary.status_code == 200
    assert summary.json()["valuation_status"] == "incomplete"
    assert summary.json()["total_assets"] is None
    assert summary.json()["net_worth"] is None


def test_base_change_never_relabels_an_old_market_quote(
    auth_client,
    db_session,
):
    _activate_max(db_session, base_currency="INR")
    item = _market_item(db_session, currency="USD")
    _quote(db_session, item, base_currency="INR")

    changed = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"base_currency": "USD"},
    )
    summary = auth_client.get("/api/v1/net-worth")

    assert changed.status_code == 200, changed.text
    assert changed.json()["base_currency_changed"] is True
    assert changed.json()["quotes_requiring_refresh"] == 1
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["base_currency"] == "USD"
    assert payload["net_worth"] is None
    assert payload["items"][0]["value_base"] is None
    assert "saved for INR" in payload["items"][0]["unavailable_reason"]


def test_expired_market_quote_is_excluded_from_all_headline_totals(
    auth_client,
    db_session,
):
    _activate_max(db_session)
    item = _market_item(db_session, currency="INR")
    _quote(
        db_session,
        item,
        rate=1,
        base_currency="INR",
        expires_at=utcnow_naive() - timedelta(seconds=1),
    )

    response = auth_client.get("/api/v1/net-worth")

    assert response.status_code == 200
    payload = response.json()
    assert payload["valuation_status"] == "incomplete"
    assert payload["total_assets"] is None
    assert payload["items"][0]["available"] is False
    assert "expired" in payload["items"][0]["unavailable_reason"].lower()


def test_offline_summary_uses_only_recent_matching_saved_manual_rate(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session)
    now = utcnow_naive()
    db_session.add(
        NetWorthItem(
            name="Saved USD fixture",
            item_type="asset",
            asset_class="cash",
            valuation_mode="manual",
            currency="USD",
            manual_value=100,
            exchange_rate_to_base=80,
            fx_source_currency="USD",
            fx_base_currency="INR",
            fx_rate_source=FX_PROVIDER,
            fx_rate_source_url=FRANKFURTER_RATES_URL,
            fx_rate_as_of=date.today() - timedelta(days=2),
            fx_rate_fetched_at=now - timedelta(days=2),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FxRateUnavailable("offline fixture")
        ),
    )

    response = auth_client.get("/api/v1/net-worth")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["value_base"] == 8000
    assert item["conversion"]["status"] == "stored"
    assert response.json()["net_worth"] == 8000


def test_expired_saved_manual_rate_is_rejected_offline(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session)
    old = utcnow_naive() - timedelta(days=11)
    db_session.add(
        NetWorthItem(
            name="Expired USD fixture",
            item_type="asset",
            asset_class="cash",
            valuation_mode="manual",
            currency="USD",
            manual_value=100,
            exchange_rate_to_base=80,
            fx_source_currency="USD",
            fx_base_currency="INR",
            fx_rate_source=FX_PROVIDER,
            fx_rate_source_url=FRANKFURTER_RATES_URL,
            fx_rate_as_of=old.date(),
            fx_rate_fetched_at=old,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FxRateUnavailable("offline fixture")
        ),
    )

    response = auth_client.get("/api/v1/net-worth")

    assert response.status_code == 200
    assert response.json()["net_worth"] is None
    assert response.json()["items"][0]["conversion"]["status"] == "unavailable"


def test_offline_name_edit_preserves_rate_but_currency_edit_invalidates_it(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session)
    now = utcnow_naive()
    item = NetWorthItem(
        name="Original name",
        item_type="asset",
        asset_class="cash",
        valuation_mode="manual",
        currency="USD",
        manual_value=100,
        exchange_rate_to_base=80,
        fx_source_currency="USD",
        fx_base_currency="INR",
        fx_rate_source=FX_PROVIDER,
        fx_rate_source_url=FRANKFURTER_RATES_URL,
        fx_rate_as_of=date.today(),
        fx_rate_fetched_at=now,
    )
    db_session.add(item)
    db_session.commit()
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FxRateUnavailable("offline fixture")
        ),
    )

    renamed = auth_client.put(
        f"/api/v1/net-worth/{item.id}",
        json={"name": "Renamed safely"},
    )
    changed_currency = auth_client.put(
        f"/api/v1/net-worth/{item.id}",
        json={"currency": "EUR"},
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["value_base"] == 8000
    assert renamed.json()["conversion"]["status"] == "stored"
    assert changed_currency.status_code == 200, changed_currency.text
    assert changed_currency.json()["value_base"] is None
    db_session.refresh(item)
    assert item.fx_source_currency is None
    assert item.fx_base_currency is None
    assert item.fx_rate_source is None


def test_cross_rate_converts_usd_to_gbp_without_one_to_one_assumption(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session, base_currency="GBP")
    snapshot = _snapshot(USD=80, GBP=100)
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: snapshot,
    )

    response = auth_client.post(
        "/api/v1/net-worth",
        json=_manual_payload(currency="USD", value=100),
    )

    assert response.status_code == 201, response.text
    assert response.json()["exchange_rate_to_base"] == pytest.approx(0.8)
    assert response.json()["value_base"] == 80
    assert response.json()["base_currency"] == "GBP"


def test_refresh_rejects_market_instrument_currency_mismatch(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import net_worth as endpoint

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"close": "100", "currency": "INR"}

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, *, params, headers):
            assert params == {"symbol": "AAPL"}
            assert headers["Authorization"].startswith("apikey ")
            return FakeResponse()

    _activate_max(db_session)
    monkeypatch.setattr(endpoint.httpx, "Client", FakeClient)
    configured = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"api_key": "currency-mismatch-fixture", "base_currency": "INR"},
    )
    assert configured.status_code == 200
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Currency mismatch fixture",
            "item_type": "asset",
            "asset_class": "stock",
            "valuation_mode": "market",
            "symbol": "AAPL",
            "quantity": 1,
            "currency": "USD",
        },
    )
    response = auth_client.post(f"/api/v1/net-worth/{created.json()['id']}/refresh")

    assert response.status_code == 409, response.text
    assert "reports AAPL in INR" in response.text
    assert db_session.query(NetWorthQuote).count() == 0


def test_summary_recomputes_from_latest_native_quote_not_stored_total(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session)
    item = _market_item(db_session, currency="USD", quantity=2)
    old_time = utcnow_naive() - timedelta(hours=2)
    _quote(
        db_session,
        item,
        unit_price=50,
        quoted_at=old_time,
        expires_at=utcnow_naive() + timedelta(hours=1),
    )
    _quote(
        db_session,
        item,
        unit_price=100,
        quoted_at=utcnow_naive(),
        expires_at=utcnow_naive() + timedelta(hours=24),
    )
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: _snapshot(USD=80),
    )

    response = auth_client.get("/api/v1/net-worth")
    detail = auth_client.get(f"/api/v1/net-worth/{item.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["net_worth"] == 16000
    assert payload["items"][0]["value_base"] == 16000
    assert payload["items"][0]["value_base"] != 999999
    assert detail.status_code == 200
    assert [quote["unit_price"] for quote in detail.json()["quote_history"]] == [
        100,
        50,
    ]
    assert all(
        quote["fx_rate_source"] == FX_PROVIDER
        for quote in detail.json()["quote_history"]
    )


def test_summary_uses_bounded_latest_quote_queries_not_quote_history_n_plus_one(
    db_session,
):
    from app.core.net_worth import net_worth_summary

    _activate_max(db_session)
    now = utcnow_naive()
    for index in range(20):
        item = _market_item(db_session, currency="INR", quantity=1)
        item.name = f"Market fixture {index:02d}"
        db_session.add(
            NetWorthQuote(
                item_id=item.id,
                unit_price=100,
                quote_currency="INR",
                exchange_rate_to_base=1,
                total_value_base=999999,
                base_currency="INR",
                source="Twelve Data",
                source_url="https://twelvedata.com/docs/advanced",
                quoted_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
    db_session.commit()

    statements: list[str] = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_select)
    try:
        summary = net_worth_summary(db_session)
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert summary["net_worth"] == 2000
    assert len(statements) <= 2
    assert any(
        "net_worth_quotes" in statement and "LIMIT" in statement
        for statement in statements
    )


def test_decimal_cross_rate_result_uses_half_up_cent_rounding(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.core import net_worth as net_worth_core

    _activate_max(db_session, base_currency="GBP")
    monkeypatch.setattr(
        net_worth_core,
        "get_inr_rates",
        lambda *_args, **_kwargs: _snapshot(USD=1, GBP=3),
    )

    response = auth_client.post(
        "/api/v1/net-worth",
        json=_manual_payload(currency="USD", value=0.1),
    )

    assert response.status_code == 201, response.text
    assert response.json()["value_base"] == 0.03


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", 0.123456789),
        ("quantity", "0.12345678"),
        ("manual_value", 10.001),
        ("manual_value", "10.01"),
    ],
)
def test_net_worth_user_inputs_enforce_numeric_field_precision(
    auth_client,
    db_session,
    field,
    value,
):
    _activate_max(db_session)
    payload = _manual_payload(value=10.01)
    payload["quantity"] = 0.12345678
    payload[field] = value

    response = auth_client.post("/api/v1/net-worth", json=payload)

    assert response.status_code == 422, response.text


def test_market_refresh_rounds_provider_price_once_and_persists_exact_units(
    auth_client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import net_worth as endpoint

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"close": "100.123456789", "currency": "INR"}

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, *, params, headers):
            assert params == {"symbol": "TEST"}
            assert headers["Authorization"].startswith("apikey ")
            return FakeResponse()

    _activate_max(db_session)
    monkeypatch.setattr(endpoint.httpx, "Client", FakeClient)
    configured = auth_client.put(
        "/api/v1/net-worth/market-data/config",
        json={"api_key": "exact-provider-price-fixture", "base_currency": "INR"},
    )
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Exact provider quote",
            "item_type": "asset",
            "asset_class": "stock",
            "valuation_mode": "market",
            "symbol": "TEST",
            "quantity": 0.12345678,
            "currency": "INR",
        },
    )

    response = auth_client.post(
        f"/api/v1/net-worth/{created.json()['id']}/refresh"
    )

    assert configured.status_code == 200, configured.text
    assert created.status_code == 201, created.text
    assert response.status_code == 200, response.text
    assert response.json()["quote_history"][0]["unit_price"] == 100.12345679
    assert response.json()["value_base"] == 12.36
    stored = db_session.execute(
        text(
            "SELECT unit_price_units, total_value_base_minor "
            "FROM net_worth_quotes WHERE item_id=:item_id"
        ),
        {"item_id": created.json()["id"]},
    ).one()
    assert stored == (10_012_345_679, 1_236)
