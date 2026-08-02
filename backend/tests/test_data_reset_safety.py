from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text

from app.models import (
    Account,
    AppSetting,
    AuditLog,
    AuditSession,
    BehaviorInsightPreference,
    ClassificationCorrection,
    ClassificationPattern,
    Goal,
    GoalContribution,
    GoalContributionSuggestion,
    IncomeSource,
    MerchantMemory,
    MonthlyAggregate,
    NetWorthItem,
    NetWorthQuote,
    RecurringPattern,
    RewardPilotSubmission,
    Subscription,
    SubscriptionSuggestion,
    SystemLog,
    Transaction,
    TransactionSplit,
    TransferMatch,
)


def _transaction(account_id: str, *, suffix: str, txn_type: str = "debit"):
    return Transaction(
        date=date(2026, 8, 1),
        raw_text=f"SYNTHETIC RESET {suffix}",
        merchant_raw=f"SYNTHETIC RESET {suffix}",
        merchant_normalized=f"SYNTHETIC RESET {suffix}",
        amount=100,
        type=txn_type,
        instrument="upi",
        account_id=account_id,
        category="FOOD & DINING",
        status="settled",
        semantic_type="expense" if txn_type == "debit" else "unknown",
        source="manual",
    )


def test_reset_stops_before_deletion_when_backup_fails(
    auth_client,
    db_session,
    monkeypatch,
):
    account = db_session.query(Account).first()
    transaction = _transaction(account.id, suffix="BACKUP FAILURE")
    db_session.add(transaction)
    db_session.commit()
    transaction_id = transaction.id

    def fail_backup(*_args, **_kwargs):
        raise RuntimeError("synthetic backup failure")

    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.create_backup",
        fail_backup,
    )
    response = auth_client.post(
        "/api/v1/settings/reset-data",
        json={"pin": "4826"},
    )

    assert response.status_code == 503
    assert "not reset" in response.json()["detail"].lower()
    db_session.expire_all()
    assert db_session.query(Transaction).filter_by(id=transaction_id).one_or_none()


def test_reset_cannot_skip_the_safety_backup(auth_client):
    response = auth_client.post(
        "/api/v1/settings/reset-data",
        json={"pin": "4826", "create_backup": False},
    )

    assert response.status_code == 422


def test_reset_rolls_back_if_dynamic_deletion_fails(
    auth_client,
    db_session,
    monkeypatch,
):
    account = db_session.query(Account).first()
    transaction = _transaction(account.id, suffix="DELETE FAILURE")
    db_session.add(transaction)
    db_session.commit()
    transaction_id = transaction.id

    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.create_backup",
        lambda *_args, **_kwargs: "godfin_backup_synthetic.db",
    )

    def fail_after_delete(db):
        db.query(Transaction).delete(synchronize_session=False)
        raise RuntimeError("synthetic delete failure")

    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.reset_dynamic_data",
        fail_after_delete,
    )
    response = auth_client.post(
        "/api/v1/settings/reset-data",
        json={"pin": "4826"},
    )

    assert response.status_code == 500
    assert "not reset" in response.json()["detail"].lower()
    assert "backup remains available" in response.json()["detail"].lower()
    db_session.expire_all()
    assert db_session.query(Transaction).filter_by(id=transaction_id).one_or_none()


def test_reset_deletes_complete_dynamic_graph_in_foreign_key_order(
    auth_client,
    db_session,
    monkeypatch,
):
    account = db_session.query(Account).first()
    audit = AuditSession(period_year=2026, period_month=8, status="draft")
    first = _transaction(account.id, suffix="ONE")
    second = _transaction(account.id, suffix="TWO", txn_type="credit")
    db_session.add_all([audit, first, second])
    db_session.flush()
    first.audit_session_id = audit.id

    goal = Goal(
        name="Synthetic reset goal",
        target_amount=10000,
        deadline_date=date(2027, 8, 1),
    )
    recurring = RecurringPattern(
        merchant_normalized="SYNTHETIC RESET",
        account_id=account.id,
        avg_amount=100,
        frequency="monthly",
        confidence=0.9,
        evidence_count=3,
    )
    subscription = Subscription(
        name="Synthetic subscription",
        amount=100,
        currency="INR",
        frequency="monthly",
    )
    net_worth_item = NetWorthItem(
        name="Synthetic asset",
        item_type="asset",
        asset_class="cash",
        valuation_mode="manual",
        quantity=1,
        currency="INR",
        manual_value=1000,
        valuation_source="Owner entry",
        valued_at=date(2026, 8, 1),
    )
    db_session.add_all([goal, recurring, subscription, net_worth_item])
    db_session.flush()

    db_session.add_all(
        [
            TransactionSplit(
                parent_transaction_id=first.id,
                amount=100,
                category="FOOD & DINING",
            ),
            AuditLog(
                transaction_id=first.id,
                field_changed="category",
                old_value="UNCATEGORIZED",
                new_value="FOOD & DINING",
            ),
            GoalContribution(
                goal_id=goal.id,
                amount=100,
                contribution_date=date(2026, 8, 1),
                entry_type="deposit",
                source_type="manual",
                source_transaction_id=first.id,
                idempotency_key="synthetic-reset-contribution",
            ),
            GoalContributionSuggestion(
                transaction_id=second.id,
                goal_id=goal.id,
                amount=100,
                deposit_type="FD",
                evidence="Synthetic FD evidence",
                confidence=0.9,
            ),
            TransferMatch(
                debit_transaction_id=first.id,
                credit_transaction_id=second.id,
                amount=100,
                date_gap_days=0,
                confidence=0.95,
            ),
            ClassificationCorrection(
                transaction_id=first.id,
                merchant_normalized="SYNTHETIC RESET ONE",
                pattern_key="synthetic-reset",
                old_category="UNCATEGORIZED",
                new_category="FOOD & DINING",
            ),
            ClassificationPattern(
                pattern_key="synthetic-reset",
                pattern_display="SYNTHETIC RESET",
                category="FOOD & DINING",
            ),
            SubscriptionSuggestion(
                recurring_pattern_id=recurring.id,
                merchant="SYNTHETIC RESET",
                avg_amount=100,
                frequency="monthly",
                status="pending",
                confirmed_subscription_id=subscription.id,
            ),
            MonthlyAggregate(
                month="2026-08",
                account_id=account.id,
                audit_session_id=audit.id,
            ),
            MerchantMemory(
                raw_string="SYNTHETIC RESET",
                normalized_name="SYNTHETIC RESET",
                category="FOOD & DINING",
            ),
            IncomeSource(source_name="Synthetic income", expected_amount=1000),
            SystemLog(
                level="INFO",
                component="reset-test",
                message="Synthetic log",
            ),
            NetWorthQuote(
                item_id=net_worth_item.id,
                unit_price=1000,
                quote_currency="INR",
                exchange_rate_to_base=1,
                total_value_base=1000,
                base_currency="INR",
                source="Synthetic quote",
                quoted_at=datetime(2026, 8, 1, 10, 0, 0),
                expires_at=datetime(2026, 8, 2, 10, 0, 0),
            ),
            BehaviorInsightPreference(
                metric_key="synthetic-reset",
                hidden=True,
            ),
            RewardPilotSubmission(
                payload_json='{"synthetic":true}',
                payload_digest="a" * 64,
            ),
        ]
    )
    db_session.commit()
    account_id = account.id

    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.create_backup",
        lambda *_args, **_kwargs: "godfin_backup_synthetic.db",
    )
    response = auth_client.post(
        "/api/v1/settings/reset-data",
        json={"pin": "4826"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["backup_filename"] == "godfin_backup_synthetic.db"
    assert response.json()["deleted_records"] > 0
    db_session.expire_all()
    dynamic_tables = [
        "transaction_splits",
        "audit_log",
        "goal_contribution_suggestions",
        "goal_contributions",
        "transfer_matches",
        "classification_corrections",
        "classification_patterns",
        "subscription_suggestions",
        "transactions",
        "monthly_aggregates",
        "audit_sessions",
        "merchant_memory",
        "recurring_patterns",
        "goals",
        "income_sources",
        "subscriptions",
        "system_log",
        "net_worth_quotes",
        "net_worth_items",
        "behavior_insight_preferences",
        "reward_pilot_submissions",
    ]
    for table_name in dynamic_tables:
        count = db_session.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}"')
        ).scalar_one()
        assert count == 0, table_name
    assert db_session.query(Account).filter_by(id=account_id).one_or_none()
    assert db_session.query(AppSetting).filter_by(key="pin_hash").one_or_none()
    assert db_session.execute(text("PRAGMA foreign_key_check")).all() == []
