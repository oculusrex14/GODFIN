from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest


class _Response:
    def __init__(self, payload, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.frankfurter.dev/v2/rates")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "provider failure", request=request, response=response
            )

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _empty_fx_cache():
    from app.core.fx import clear_fx_cache

    clear_fx_cache()
    yield
    clear_fx_cache()


def test_ecb_rates_are_inverted_to_inr_with_provenance(monkeypatch):
    from app.core import fx

    captured: dict = {}

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return _Response(
            [
                {"date": "2026-07-31", "base": "INR", "quote": "USD", "rate": 0.0125},
                {"date": "2026-07-31", "base": "INR", "quote": "EUR", "rate": 0.01},
            ]
        )

    monkeypatch.setattr(fx.httpx, "get", fake_get)
    snapshot = fx.get_inr_rates({"USD", "EUR"}, today=date(2026, 8, 2))

    assert snapshot.rates_to_inr == {"INR": 1.0, "EUR": 100.0, "USD": 80.0}
    assert snapshot.as_of == date(2026, 7, 31)
    assert snapshot.provider == "European Central Bank reference rates via Frankfurter"
    assert snapshot.source_url == "https://api.frankfurter.dev/v2/rates"
    assert snapshot.convert_to_inr(100, "USD") == 8000
    assert snapshot.rate_between("USD", "EUR") == pytest.approx(0.8)
    assert snapshot.convert(100, "USD", "EUR") == pytest.approx(80)
    assert snapshot.rate_between("USD", "USD") == 1
    assert captured["params"] == {
        "base": "INR",
        "quotes": "EUR,USD",
        "providers": "ECB",
    }
    assert set(captured["params"]) == {"base", "quotes", "providers"}


def test_weekend_reference_rate_is_accepted_and_marked_current(monkeypatch):
    from app.core import fx

    monkeypatch.setattr(
        fx.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(
            [{"date": "2026-07-31", "base": "INR", "quote": "USD", "rate": 0.0125}]
        ),
    )

    snapshot = fx.get_inr_rates({"USD"}, today=date(2026, 8, 3))

    assert snapshot.stale is False
    assert snapshot.age_days == 3


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [{"date": "2026-07-31", "base": "INR", "quote": "EUR", "rate": 0.01}],
        [{"date": "2026-07-31", "base": "USD", "quote": "USD", "rate": 1}],
        [{"date": "2026-07-31", "base": "INR", "quote": "USD", "rate": 0}],
        [{"date": "2026-07-31", "base": "INR", "quote": "USD", "rate": "NaN"}],
    ],
)
def test_incomplete_or_invalid_provider_payload_fails_closed(monkeypatch, payload):
    from app.core import fx

    monkeypatch.setattr(
        fx.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(payload),
    )

    with pytest.raises(fx.FxRateUnavailable):
        fx.get_inr_rates({"USD"}, today=date(2026, 8, 2))


def test_provider_outage_never_uses_hardcoded_or_one_to_one_rates(monkeypatch):
    from app.core import fx

    def fail(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(fx.httpx, "get", fail)

    with pytest.raises(fx.FxRateUnavailable, match="temporarily unavailable"):
        fx.get_inr_rates({"USD"}, today=date(2026, 8, 2))


def test_provider_rate_older_than_safety_window_fails_closed(monkeypatch):
    from app.core import fx

    monkeypatch.setattr(
        fx.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(
            [{"date": "2026-07-01", "base": "INR", "quote": "USD", "rate": 0.0125}]
        ),
    )

    with pytest.raises(fx.FxRateUnavailable, match="too old"):
        fx.get_inr_rates({"USD"}, today=date(2026, 8, 2))


def test_inr_only_never_calls_network(monkeypatch):
    from app.core import fx

    monkeypatch.setattr(
        fx.httpx,
        "get",
        lambda *_args, **_kwargs: pytest.fail("INR-only conversion must remain local"),
    )

    snapshot = fx.get_inr_rates({"INR"}, today=date(2026, 8, 2))

    assert snapshot.rates_to_inr == {"INR": 1.0}
    assert snapshot.status == "not_required"
    assert snapshot.source_url is None


def test_force_refresh_bypasses_the_process_cache(monkeypatch):
    from app.core import fx

    calls = []

    def fake_get(*_args, **_kwargs):
        calls.append(1)
        quoted_per_inr = 0.0125 if len(calls) == 1 else 0.01
        return _Response(
            [
                {
                    "date": "2026-07-31",
                    "base": "INR",
                    "quote": "USD",
                    "rate": quoted_per_inr,
                }
            ]
        )

    monkeypatch.setattr(fx.httpx, "get", fake_get)

    first = fx.get_inr_rates({"USD"}, today=date(2026, 8, 2))
    cached = fx.get_inr_rates({"USD"}, today=date(2026, 8, 2))
    refreshed = fx.get_inr_rates({"USD"}, today=date(2026, 8, 2), force_refresh=True)

    assert len(calls) == 2
    assert first.rate_to_inr("USD") == cached.rate_to_inr("USD") == 80
    assert refreshed.rate_to_inr("USD") == 100


def test_subscription_api_exposes_verified_rate_provenance(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import subscriptions as endpoint
    from app.core.fx import FxRateSnapshot
    from app.models.subscription import Subscription

    db_session.add(
        Subscription(
            name="USD fixture",
            amount=100,
            currency="USD",
            frequency="monthly",
            is_active=True,
        )
    )
    db_session.commit()
    snapshot = FxRateSnapshot(
        rates_to_inr={"INR": 1.0, "USD": 80.0},
        as_of=date(2026, 7, 31),
        provider="European Central Bank reference rates via Frankfurter",
        source_url="https://api.frankfurter.dev/v2/rates",
        age_days=2,
        stale=False,
        status="available",
    )

    async def verified_rates(_currencies, **_kwargs):
        return snapshot

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", verified_rates)

    listing = auth_client.get("/api/v1/subscriptions")
    stats = auth_client.get("/api/v1/subscriptions/stats")

    assert listing.status_code == 200, listing.text
    subscription = next(
        item for item in listing.json() if item["name"] == "USD fixture"
    )
    assert subscription["amount_inr"] == 8000
    assert subscription["conversion_status"] == "available"
    assert subscription["conversion_as_of"] == "2026-07-31"
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_monthly_cost"] == 8000
    assert stats.json()["total_annual_projection"] == 96000
    assert stats.json()["fx"]["provider"].startswith("European Central Bank")
    assert stats.json()["fx"]["as_of"] == "2026-07-31"


def test_exchange_rate_endpoints_require_an_authenticated_session(client):
    current = client.get("/api/v1/subscriptions/exchange-rates")
    refresh = client.post("/api/v1/subscriptions/exchange-rates/refresh")

    assert current.status_code == 401
    assert refresh.status_code == 401


def test_subscription_api_hides_totals_when_verified_rate_is_unavailable(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import subscriptions as endpoint
    from app.core.fx import FxRateUnavailable
    from app.models.subscription import Subscription

    db_session.add(
        Subscription(
            name="USD fixture",
            amount=100,
            currency="USD",
            frequency="monthly",
            is_active=True,
        )
    )
    db_session.commit()

    async def unavailable(_currencies, **_kwargs):
        raise FxRateUnavailable("Live currency rates are temporarily unavailable.")

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", unavailable)

    listing = auth_client.get("/api/v1/subscriptions")
    stats = auth_client.get("/api/v1/subscriptions/stats")

    assert listing.status_code == 200, listing.text
    subscription = next(
        item for item in listing.json() if item["name"] == "USD fixture"
    )
    assert subscription["amount_inr"] is None
    assert subscription["conversion_status"] == "unavailable"
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_monthly_cost"] is None
    assert stats.json()["total_annual_projection"] is None
    assert stats.json()["by_category"] is None
    assert stats.json()["exchange_rates"] == {}
    assert stats.json()["fx"]["status"] == "unavailable"
    assert stats.json()["fx"]["unavailable_reason"]


def test_subscription_write_persists_rate_source_and_offline_reads_reuse_it(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import subscriptions as endpoint
    from app.core.fx import FxRateSnapshot, FxRateUnavailable
    from app.models.subscription import Subscription

    snapshot = FxRateSnapshot(
        rates_to_inr={"INR": 1.0, "USD": 80.0},
        as_of=date.today(),
        provider="European Central Bank reference rates via Frankfurter",
        source_url="https://api.frankfurter.dev/v2/rates",
        age_days=0,
        stale=False,
        status="available",
    )

    async def verified_rates(_currencies, **_kwargs):
        return snapshot

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", verified_rates)
    created = auth_client.post(
        "/api/v1/subscriptions",
        json={
            "name": "Persisted USD fixture",
            "amount": 100,
            "currency": "USD",
            "frequency": "monthly",
        },
    )
    assert created.status_code == 201, created.text

    stored = (
        db_session.query(Subscription).filter_by(name="Persisted USD fixture").one()
    )
    db_session.refresh(stored)
    assert float(stored.fx_rate_to_inr) == 80
    assert stored.fx_rate_source.startswith("European Central Bank")
    assert stored.fx_rate_source_url == "https://api.frankfurter.dev/v2/rates"
    assert stored.fx_rate_as_of == date.today()
    assert stored.fx_rate_fetched_at is not None

    async def unavailable(_currencies, **_kwargs):
        raise FxRateUnavailable("offline")

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", unavailable)
    listing = auth_client.get("/api/v1/subscriptions")
    stats = auth_client.get("/api/v1/subscriptions/stats")

    assert listing.status_code == 200, listing.text
    item = next(row for row in listing.json() if row["name"] == "Persisted USD fixture")
    assert item["amount_inr"] == 8000
    assert item["conversion_status"] == "stored"
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_monthly_cost"] == 8000
    assert stats.json()["fx"]["status"] == "stored"
    assert stats.json()["fx"]["as_of"] == date.today().isoformat()


def test_saved_rate_accepts_utc_fetch_from_previous_local_calendar_day():
    from app.core.fx import (
        FRANKFURTER_RATES_URL,
        FX_PROVIDER,
        saved_subscription_snapshot,
    )

    local_day = date(2026, 8, 16)
    subscription = SimpleNamespace(
        currency="USD",
        fx_rate_to_inr=80,
        fx_rate_as_of=local_day,
        fx_rate_source=FX_PROVIDER,
        fx_rate_source_url=FRANKFURTER_RATES_URL,
        # 01:30 in India is still the prior UTC calendar day.
        fx_rate_fetched_at=datetime(2026, 8, 15, 20, 0),
    )

    snapshot = saved_subscription_snapshot([subscription], today=local_day)

    assert snapshot is not None
    assert snapshot.rate_to_inr("USD") == 80
    assert snapshot.age_days == 0


def test_saved_rate_still_rejects_a_future_as_of_date():
    from app.core.fx import (
        FRANKFURTER_RATES_URL,
        FX_PROVIDER,
        saved_subscription_snapshot,
    )

    subscription = SimpleNamespace(
        currency="USD",
        fx_rate_to_inr=80,
        fx_rate_as_of=date(2026, 8, 17),
        fx_rate_source=FX_PROVIDER,
        fx_rate_source_url=FRANKFURTER_RATES_URL,
        fx_rate_fetched_at=datetime(2026, 8, 16, 20, 0),
    )

    assert (
        saved_subscription_snapshot([subscription], today=date(2026, 8, 16))
        is None
    )


def test_expired_persisted_rate_is_not_used_as_a_fallback(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import subscriptions as endpoint
    from app.core.fx import FxRateUnavailable
    from app.models.subscription import Subscription

    db_session.add(
        Subscription(
            name="Expired USD fixture",
            amount=100,
            currency="USD",
            frequency="monthly",
            is_active=True,
            fx_rate_to_inr=80,
            fx_rate_source="European Central Bank reference rates via Frankfurter",
            fx_rate_source_url="https://api.frankfurter.dev/v2/rates",
            fx_rate_as_of=date.today() - timedelta(days=11),
            fx_rate_fetched_at=datetime.now() - timedelta(days=11),
        )
    )
    db_session.commit()

    async def unavailable(_currencies, **_kwargs):
        raise FxRateUnavailable("offline")

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", unavailable)
    stats = auth_client.get("/api/v1/subscriptions/stats")

    assert stats.status_code == 200, stats.text
    assert stats.json()["total_monthly_cost"] is None
    assert stats.json()["fx"]["status"] == "unavailable"


def test_explicit_rate_refresh_persists_current_rates(
    auth_client, db_session, monkeypatch
):
    from app.api.v1.endpoints import subscriptions as endpoint
    from app.core.fx import FxRateSnapshot
    from app.models.subscription import Subscription

    subscription = Subscription(
        name="Refresh USD fixture",
        amount=25,
        currency="USD",
        frequency="monthly",
        is_active=True,
    )
    db_session.add(subscription)
    db_session.commit()
    snapshot = FxRateSnapshot(
        rates_to_inr={"INR": 1.0, "USD": 81.25},
        as_of=date.today(),
        provider="European Central Bank reference rates via Frankfurter",
        source_url="https://api.frankfurter.dev/v2/rates",
        age_days=0,
        stale=False,
        status="available",
    )

    async def verified_rates(_currencies, **_kwargs):
        return snapshot

    monkeypatch.setattr(endpoint, "_fetch_exchange_rates", verified_rates)
    response = auth_client.post("/api/v1/subscriptions/exchange-rates/refresh")

    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 1
    db_session.refresh(subscription)
    assert float(subscription.fx_rate_to_inr) == 81.25
    assert subscription.fx_rate_as_of == date.today()


def test_incomplete_persisted_rate_provenance_is_never_used():
    from types import SimpleNamespace

    from app.core.fx import saved_subscription_snapshot

    incomplete = SimpleNamespace(
        currency="USD",
        fx_rate_to_inr=80,
        fx_rate_source="European Central Bank reference rates via Frankfurter",
        fx_rate_source_url="https://api.frankfurter.dev/v2/rates",
        fx_rate_as_of=date.today(),
        fx_rate_fetched_at=None,
    )

    assert saved_subscription_snapshot([incomplete]) is None


def test_saved_rate_metadata_keeps_each_currency_date():
    from types import SimpleNamespace

    from app.core.fx import saved_subscription_snapshot

    reference_day = date(2026, 8, 2)
    fetched_at = datetime(2026, 8, 2, 8, 0)
    subscriptions = [
        SimpleNamespace(
            currency="USD",
            fx_rate_to_inr=80,
            fx_rate_source="European Central Bank reference rates via Frankfurter",
            fx_rate_source_url="https://api.frankfurter.dev/v2/rates",
            fx_rate_as_of=date(2026, 8, 1),
            fx_rate_fetched_at=fetched_at,
        ),
        SimpleNamespace(
            currency="EUR",
            fx_rate_to_inr=100,
            fx_rate_source="European Central Bank reference rates via Frankfurter",
            fx_rate_source_url="https://api.frankfurter.dev/v2/rates",
            fx_rate_as_of=date(2026, 7, 31),
            fx_rate_fetched_at=fetched_at,
        ),
    ]

    snapshot = saved_subscription_snapshot(subscriptions, today=reference_day)

    assert snapshot is not None
    assert snapshot.as_of == date(2026, 7, 31)
    assert snapshot.metadata({"USD", "EUR"})["rate_dates"] == {
        "USD": "2026-08-01",
        "EUR": "2026-07-31",
    }
