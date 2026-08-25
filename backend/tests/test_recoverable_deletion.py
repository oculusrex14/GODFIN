from __future__ import annotations

from datetime import date

from app.models.net_worth import NetWorthItem
from app.models.subscription import Subscription
from tests.license_helpers import install_test_license


def test_subscription_delete_is_recoverable_and_excluded_from_totals(
    auth_client,
    db_session,
):
    created = auth_client.post(
        "/api/v1/subscriptions",
        json={
            "name": "Synthetic Music",
            "amount": 199,
            "currency": "INR",
            "frequency": "monthly",
        },
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]

    deleted = auth_client.delete(f"/api/v1/subscriptions/{subscription_id}")

    assert deleted.status_code == 200
    assert deleted.json()["affected_records"] == 1
    assert deleted.json()["status"] == "deleted"
    assert auth_client.get("/api/v1/subscriptions").json() == []
    assert auth_client.get("/api/v1/subscriptions/stats").json()["active_count"] == 0
    db_session.expire_all()
    stored = db_session.get(Subscription, subscription_id)
    assert stored is not None
    assert stored.deleted_at is not None

    restored = auth_client.post(f"/api/v1/subscriptions/{subscription_id}/restore")

    assert restored.status_code == 200
    assert restored.json()["status"] == "restored"
    assert auth_client.get("/api/v1/subscriptions").json()[0]["id"] == subscription_id
    db_session.expire_all()
    assert db_session.get(Subscription, subscription_id).deleted_at is None


def test_net_worth_delete_is_recoverable_and_excluded_from_summary(
    auth_client,
    db_session,
):
    install_test_license(db_session, "max")
    created = auth_client.post(
        "/api/v1/net-worth",
        json={
            "name": "Synthetic Cash",
            "item_type": "asset",
            "asset_class": "cash",
            "valuation_mode": "manual",
            "quantity": 1,
            "currency": "INR",
            "manual_value": 25000,
            "valuation_source": "Synthetic fixture",
        },
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    deleted = auth_client.delete(f"/api/v1/net-worth/{item_id}")

    assert deleted.status_code == 200
    assert deleted.json()["affected_records"] == 1
    assert auth_client.get(f"/api/v1/net-worth/{item_id}").status_code == 404
    summary = auth_client.get("/api/v1/net-worth").json()
    assert all(item["id"] != item_id for item in summary["items"])
    db_session.expire_all()
    stored = db_session.get(NetWorthItem, item_id)
    assert stored is not None
    assert stored.deleted_at is not None

    restored = auth_client.post(f"/api/v1/net-worth/{item_id}/restore")

    assert restored.status_code == 200
    assert restored.json()["status"] == "restored"
    assert auth_client.get(f"/api/v1/net-worth/{item_id}").status_code == 200
    db_session.expire_all()
    assert db_session.get(NetWorthItem, item_id).deleted_at is None


def test_deleted_subscription_is_not_returned_by_reminders(auth_client, db_session):
    subscription = Subscription(
        name="Synthetic reminder",
        amount=499,
        currency="INR",
        frequency="monthly",
        is_active=True,
        next_payment_date=date.today(),
    )
    db_session.add(subscription)
    db_session.commit()

    response = auth_client.delete(f"/api/v1/subscriptions/{subscription.id}")

    assert response.status_code == 200
    reminders = auth_client.get("/api/v1/subscriptions/reminders?days=90").json()
    assert all(item["id"] != subscription.id for item in reminders["reminders"])
