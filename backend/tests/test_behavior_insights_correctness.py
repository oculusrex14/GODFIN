from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.account import Account
from app.models.app_setting import AppSetting
from app.models.subscription import Subscription
from app.models.transaction import Transaction


TODAY = date(2026, 8, 15)


def _shift_month(month: date, offset: int) -> date:
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _account(db) -> Account:
    account = db.query(Account).first()
    assert account is not None
    return account


def _add_transaction(
    db,
    *,
    transaction_date: date,
    amount: float,
    transaction_type: str = "debit",
    category: str = "FOOD & DINING",
) -> Transaction:
    income = transaction_type == "credit"
    item = Transaction(
        date=transaction_date,
        raw_text="REDACTED BEHAVIOR FIXTURE",
        merchant_raw="REDACTED",
        merchant_normalized="REDACTED",
        amount=amount,
        type=transaction_type,
        instrument="bank",
        account_id=_account(db).id,
        category="INCOME" if income else category,
        classification_source="user",
        status="settled",
        is_income=income,
        semantic_type="income" if income else "expense",
        source="manual",
    )
    db.add(item)
    return item


def _add_complete_month(db, month: date, *, income: float = 10000, spend: float = 4000):
    _add_transaction(
        db,
        transaction_date=month.replace(day=5),
        amount=income,
        transaction_type="credit",
    )
    _add_transaction(
        db,
        transaction_date=month.replace(day=12),
        amount=spend,
    )


def _metric(payload: dict, key: str) -> dict:
    return next(item for item in payload["metrics"] if item["key"] == key)


@pytest.mark.parametrize(
    ("month_count", "available", "confidence"),
    [(1, False, "insufficient"), (2, True, "low"), (6, True, "high")],
)
def test_savings_consistency_has_explicit_month_thresholds(
    db_session, month_count, available, confidence
):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    for offset in range(1, month_count + 1):
        _add_complete_month(db_session, _shift_month(current_month, -offset))
    db_session.commit()

    result = _metric(
        compute_behavior_insights(db_session, today=TODAY), "savings_consistency"
    )

    assert result["available"] is available
    assert result["confidence"] == confidence
    assert result["sample_size"] == month_count
    assert result["minimum_sample"] == 2
    assert (result["value"] is not None) is available


def test_current_and_leading_partial_months_are_excluded(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1))
    _add_complete_month(db_session, _shift_month(current_month, -2))
    _add_complete_month(db_session, current_month, income=100, spend=100000)
    _add_complete_month(
        db_session, _shift_month(current_month, -7), income=100, spend=100000
    )
    db_session.commit()

    payload = compute_behavior_insights(db_session, today=TODAY)
    savings = _metric(payload, "savings_consistency")

    assert payload["period"] == "2026-02-01 through 2026-07-31"
    assert payload["coverage"]["current_month_excluded"] is True
    assert payload["coverage"]["calendar_months"] == 6
    assert payload["coverage"]["income_months"] == 2
    assert savings["value"] == 100.0
    assert savings["sample_size"] == 2


def test_transfer_only_month_is_not_reported_as_behavior_coverage(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1))
    _add_complete_month(db_session, _shift_month(current_month, -2))
    transfer = _add_transaction(
        db_session,
        transaction_date=_shift_month(current_month, -3).replace(day=10),
        amount=5000,
        transaction_type="credit",
    )
    transfer.category = "TRANSFER"
    transfer.is_income = False
    transfer.semantic_type = "internal_transfer"
    db_session.commit()

    payload = compute_behavior_insights(db_session, today=TODAY)

    assert payload["coverage"]["observed_months"] == 2
    assert payload["coverage"]["observed_month_keys"] == ["2026-06", "2026-07"]
    assert payload["coverage"]["included_transactions"] == 4


def test_mixed_currency_subscription_load_uses_ecb_rate_and_provenance(
    db_session, monkeypatch
):
    from app.core import behavior_insights
    from app.core.fx import FxRateSnapshot

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1), income=10000)
    _add_complete_month(db_session, _shift_month(current_month, -2), income=10000)
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
    monkeypatch.setattr(
        behavior_insights,
        "get_inr_rates",
        lambda _currencies, **_kwargs: snapshot,
    )

    payload = behavior_insights.compute_behavior_insights(db_session, today=TODAY)
    metric = _metric(payload, "subscription_load")

    assert metric["available"] is True
    assert metric["value"] == 80.0
    assert metric["currency_conversion"]["as_of"] == "2026-07-31"
    assert "European Central Bank" in metric["provenance"]
    assert "Currency codes only" in metric["currency_conversion"]["privacy"]


def test_subscription_load_is_unavailable_when_rate_provider_fails(
    db_session, monkeypatch
):
    from app.core import behavior_insights
    from app.core.fx import FxRateUnavailable

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1))
    _add_complete_month(db_session, _shift_month(current_month, -2))
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

    def unavailable(_currencies, **_kwargs):
        raise FxRateUnavailable("Live currency rates are temporarily unavailable.")

    monkeypatch.setattr(behavior_insights, "get_inr_rates", unavailable)

    metric = _metric(
        behavior_insights.compute_behavior_insights(db_session, today=TODAY),
        "subscription_load",
    )

    assert metric["available"] is False
    assert metric["value"] is None
    assert metric["confidence"] == "insufficient"
    assert "currency" in metric["unavailable_reason"].lower()


def test_subscription_load_uses_recent_saved_verified_rate_when_offline(
    db_session, monkeypatch
):
    from app.core import behavior_insights
    from app.core.fx import FxRateUnavailable

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1), income=10000)
    _add_complete_month(db_session, _shift_month(current_month, -2), income=10000)
    db_session.add(
        Subscription(
            name="Saved USD fixture",
            amount=100,
            currency="USD",
            frequency="monthly",
            is_active=True,
            fx_rate_to_inr=80,
            fx_rate_source="European Central Bank reference rates via Frankfurter",
            fx_rate_source_url="https://api.frankfurter.dev/v2/rates",
            fx_rate_as_of=TODAY - timedelta(days=2),
            fx_rate_fetched_at=datetime.combine(
                TODAY - timedelta(days=2), datetime.min.time()
            ),
        )
    )
    db_session.commit()

    def unavailable(_currencies, **_kwargs):
        raise FxRateUnavailable("offline")

    monkeypatch.setattr(behavior_insights, "get_inr_rates", unavailable)

    metric = _metric(
        behavior_insights.compute_behavior_insights(db_session, today=TODAY),
        "subscription_load",
    )

    assert metric["available"] is True
    assert metric["value"] == 80.0
    assert metric["currency_conversion"]["status"] == "stored"
    assert (
        metric["currency_conversion"]["as_of"]
        == (TODAY - timedelta(days=2)).isoformat()
    )
    assert "saved verified" in metric["provenance"].lower()


def test_income_dependent_metrics_are_unavailable_without_verified_income(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    for offset in (1, 2, 3):
        _add_transaction(
            db_session,
            transaction_date=_shift_month(current_month, -offset).replace(day=10),
            amount=2000,
        )
    db_session.commit()

    payload = compute_behavior_insights(db_session, today=TODAY)

    for key in ("savings_consistency", "cash_flow_volatility", "subscription_load"):
        metric = _metric(payload, key)
        assert metric["available"] is False
        assert metric["value"] is None
        assert metric["unavailable_reason"]


def test_one_observed_full_week_never_produces_a_routine_score(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    monday = date(2026, 6, 1)
    for offset in (0, 2, 4):
        _add_transaction(
            db_session,
            transaction_date=monday + timedelta(days=offset),
            amount=200,
        )
    db_session.commit()

    metric = _metric(
        compute_behavior_insights(db_session, today=TODAY), "routine_stability"
    )

    assert metric["available"] is False
    assert metric["value"] is None
    assert metric["sample_size"] == 1
    assert metric["minimum_sample"] == 8
    assert "8" in metric["unavailable_reason"]


def test_eight_observed_full_weeks_can_produce_a_routine_score(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    monday = date(2026, 4, 6)
    for week in range(8):
        for day_offset in (0, 2):
            _add_transaction(
                db_session,
                transaction_date=monday + timedelta(weeks=week, days=day_offset),
                amount=200,
            )
    db_session.commit()

    metric = _metric(
        compute_behavior_insights(db_session, today=TODAY), "routine_stability"
    )

    assert metric["available"] is True
    assert metric["value"] == 100.0
    assert metric["sample_size"] == 8
    assert metric["confidence"] == "low"


def test_sparse_spending_does_not_create_a_precise_discretionary_ratio(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    for offset in (1, 2):
        month = _shift_month(current_month, -offset)
        _add_transaction(db_session, transaction_date=month.replace(day=8), amount=250)
        _add_transaction(db_session, transaction_date=month.replace(day=16), amount=250)
    db_session.commit()

    metric = _metric(
        compute_behavior_insights(db_session, today=TODAY), "discretionary_ratio"
    )

    assert metric["available"] is False
    assert metric["value"] is None
    assert metric["sample_size"] == 4
    assert metric["minimum_sample"] == 5


def test_non_inr_net_worth_base_never_gets_divided_by_inr_spending(db_session):
    from app.core.behavior_insights import compute_behavior_insights

    current_month = TODAY.replace(day=1)
    _add_complete_month(db_session, _shift_month(current_month, -1))
    _add_complete_month(db_session, _shift_month(current_month, -2))
    setting = (
        db_session.query(AppSetting).filter_by(key="net_worth_base_currency").first()
    )
    if setting:
        setting.value = "USD"
    else:
        db_session.add(AppSetting(key="net_worth_base_currency", value="USD"))
    db_session.commit()

    metric = _metric(
        compute_behavior_insights(db_session, today=TODAY), "buffer_coverage"
    )

    assert metric["available"] is False
    assert metric["value"] is None
    assert "INR" in metric["unavailable_reason"]
