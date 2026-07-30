from __future__ import annotations

import uuid
from datetime import date, datetime

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.transaction_split import TransactionSplit
from app.models.merchant_memory import MerchantMemory
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.income_source import IncomeSource
from app.models.classification_rule import ClassificationRule
from app.models.goal import Goal
from app.models.recurring_pattern import RecurringPattern
from app.models.app_setting import AppSetting
from app.models.audit_session import AuditSession
from app.models.audit_log import AuditLog
from app.models.system_log import SystemLog


def test_seed_accounts(db_session):
    accounts = db_session.query(Account).all()
    assert len(accounts) == 2
    types = {a.account_type for a in accounts}
    assert types == {"savings", "credit_card"}


def test_seed_app_settings(db_session):
    settings = db_session.query(AppSetting).all()
    assert len(settings) >= 2
    keys = {s.key for s in settings}
    assert "user_timezone" in keys
    assert "is_first_run" in keys


def test_create_transaction(db_session):
    account = db_session.query(Account).filter_by(account_type="savings").first()
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2026, 2, 27),
        raw_text="Rs.500.00 debited from account 0000",
        amount=500.00,
        type="debit",
        instrument="upi",
        account_id=account.id,
        source="gmail",
    )
    db_session.add(txn)
    db_session.commit()

    result = db_session.query(Transaction).filter_by(id=txn.id).first()
    assert result is not None
    assert result.amount == 500.00
    assert result.account_id == account.id
    assert result.is_locked is False


def test_transaction_account_relationship(db_session):
    account = db_session.query(Account).filter_by(account_type="savings").first()
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2026, 2, 27),
        raw_text="test",
        amount=100.00,
        type="debit",
        instrument="upi",
        account_id=account.id,
        source="manual",
    )
    db_session.add(txn)
    db_session.commit()

    result = db_session.query(Transaction).filter_by(id=txn.id).first()
    assert result.account.bank == "HDFC"


def test_create_transaction_split(db_session):
    account = db_session.query(Account).filter_by(account_type="savings").first()
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2026, 2, 27),
        raw_text="test split",
        amount=1000.00,
        type="debit",
        instrument="upi",
        account_id=account.id,
        source="manual",
        is_split=True,
    )
    db_session.add(txn)
    db_session.commit()

    split = TransactionSplit(
        id=str(uuid.uuid4()),
        parent_transaction_id=txn.id,
        amount=600.00,
        category="FOOD & DINING",
        subcategory="Groceries",
    )
    db_session.add(split)
    db_session.commit()

    result = db_session.query(TransactionSplit).filter_by(parent_transaction_id=txn.id).first()
    assert result.amount == 600.00
    assert result.parent_transaction.amount == 1000.00


def test_create_merchant_memory(db_session):
    merchant = MerchantMemory(
        id=str(uuid.uuid4()),
        raw_string="PYU*Swiggy Food",
        normalized_name="SWIGGY FOOD",
        category="FOOD & DINING",
        subcategory="Food Delivery",
    )
    db_session.add(merchant)
    db_session.commit()

    result = db_session.query(MerchantMemory).filter_by(normalized_name="SWIGGY FOOD").first()
    assert result is not None
    assert result.display_name is None
    assert result.times_seen == 1


def test_create_monthly_aggregate(db_session):
    account = db_session.query(Account).first()
    agg = MonthlyAggregate(
        id=str(uuid.uuid4()),
        month="2026-02",
        account_id=account.id,
        total_spend=45000.00,
        total_income=85000.00,
        is_finalized=False,
    )
    db_session.add(agg)
    db_session.commit()

    result = db_session.query(MonthlyAggregate).filter_by(month="2026-02").first()
    assert result.total_spend == 45000.00
    assert result.is_finalized is False


def test_create_audit_session(db_session):
    session = AuditSession(
        id=str(uuid.uuid4()),
        period_year=2026,
        period_month=2,
        status="draft",
    )
    db_session.add(session)
    db_session.commit()

    result = db_session.query(AuditSession).first()
    assert result.status == "draft"
    assert result.finalized_at is None


def test_create_audit_log(db_session):
    account = db_session.query(Account).filter_by(account_type="savings").first()
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=date(2026, 2, 27),
        raw_text="test",
        amount=100.00,
        type="debit",
        instrument="upi",
        account_id=account.id,
        source="manual",
    )
    db_session.add(txn)
    db_session.commit()

    log = AuditLog(
        id=str(uuid.uuid4()),
        transaction_id=txn.id,
        field_changed="category",
        old_value=None,
        new_value="FOOD & DINING",
        change_source="user",
    )
    db_session.add(log)
    db_session.commit()

    result = db_session.query(AuditLog).first()
    assert result.new_value == "FOOD & DINING"


def test_create_classification_rule(db_session):
    rule = ClassificationRule(
        id=str(uuid.uuid4()),
        rule_type="contains",
        pattern="SWIGGY",
        category="FOOD & DINING",
        subcategory="Food Delivery",
    )
    db_session.add(rule)
    db_session.commit()

    result = db_session.query(ClassificationRule).first()
    assert result.pattern == "SWIGGY"
    assert result.is_system is True


def test_create_goal(db_session):
    goal = Goal(
        id=str(uuid.uuid4()),
        name="Emergency Fund",
        target_amount=300000.00,
        deadline_date=date(2027, 12, 31),
    )
    db_session.add(goal)
    db_session.commit()

    result = db_session.query(Goal).first()
    assert result.pressure_level == "moderate"
    assert result.annual_return_rate == 0.0


def test_create_income_source(db_session):
    income = IncomeSource(
        id=str(uuid.uuid4()),
        source_name="Salary",
        expected_amount=85000.00,
        frequency="monthly",
    )
    db_session.add(income)
    db_session.commit()

    result = db_session.query(IncomeSource).first()
    assert result.source_name == "Salary"
    assert result.is_active is True


def test_create_recurring_pattern(db_session):
    account = db_session.query(Account).first()
    pattern = RecurringPattern(
        id=str(uuid.uuid4()),
        merchant_normalized="NETFLIX",
        account_id=account.id,
        avg_amount=649.00,
        frequency="monthly",
    )
    db_session.add(pattern)
    db_session.commit()

    result = db_session.query(RecurringPattern).first()
    assert result.merchant_normalized == "NETFLIX"
    assert result.times_detected == 2


def test_create_system_log(db_session):
    log = SystemLog(
        id=str(uuid.uuid4()),
        level="INFO",
        component="ingestion",
        message="Gmail sync completed",
    )
    db_session.add(log)
    db_session.commit()

    result = db_session.query(SystemLog).first()
    assert result.component == "ingestion"
