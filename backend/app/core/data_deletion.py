from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.audit_session import AuditSession
from app.models.behavior_insight import BehaviorInsightPreference
from app.models.classification_learning import (
    ClassificationCorrection,
    ClassificationPattern,
)
from app.models.goal import Goal
from app.models.goal_contribution import (
    GoalContribution,
    GoalContributionSuggestion,
)
from app.models.income_source import IncomeSource
from app.models.merchant_memory import MerchantMemory
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.net_worth import NetWorthItem, NetWorthQuote
from app.models.recurring_pattern import RecurringPattern
from app.models.reward_pilot import RewardPilotSubmission
from app.models.subscription import Subscription
from app.models.subscription_suggestion import SubscriptionSuggestion
from app.models.system_log import SystemLog
from app.models.transaction import Transaction
from app.models.transaction_split import TransactionSplit
from app.models.transfer_match import TransferMatch


RESET_DYNAMIC_MODELS = (
    TransactionSplit,
    AuditLog,
    GoalContributionSuggestion,
    TransferMatch,
    ClassificationCorrection,
    GoalContribution,
    SubscriptionSuggestion,
    NetWorthQuote,
    Transaction,
    MonthlyAggregate,
    AuditSession,
    NetWorthItem,
    ClassificationPattern,
    MerchantMemory,
    RecurringPattern,
    Goal,
    IncomeSource,
    Subscription,
    SystemLog,
    BehaviorInsightPreference,
    RewardPilotSubmission,
)


def reset_dynamic_data(db: Session) -> dict[str, int]:
    """Delete user-created and derived data in explicit foreign-key order."""
    counts: dict[str, int] = {}
    for model in RESET_DYNAMIC_MODELS:
        deleted = db.query(model).delete(synchronize_session=False)
        counts[model.__tablename__] = int(deleted or 0)
    return counts


def delete_transactions_with_dependents(
    db: Session,
    transaction_ids: Iterable[str],
    *,
    void_reason: str,
) -> int:
    """Delete selected transactions without leaving dependent or goal state stale."""
    from app.core.goal_contributions import (
        recompute_goal_balance,
        void_goal_contribution,
    )

    unique_ids = tuple(dict.fromkeys(transaction_ids))
    if not unique_ids:
        return 0

    affected_goal_ids: set[str] = set()
    contributions = (
        db.query(GoalContribution)
        .filter(GoalContribution.source_transaction_id.in_(unique_ids))
        .all()
    )
    for contribution in contributions:
        affected_goal_ids.add(contribution.goal_id)
        if not contribution.is_voided:
            void_goal_contribution(db, contribution, reason=void_reason)
        contribution.source_transaction_id = None

    db.query(GoalContributionSuggestion).filter(
        GoalContributionSuggestion.transaction_id.in_(unique_ids)
    ).delete(synchronize_session=False)
    db.query(TransferMatch).filter(
        or_(
            TransferMatch.debit_transaction_id.in_(unique_ids),
            TransferMatch.credit_transaction_id.in_(unique_ids),
        )
    ).delete(synchronize_session=False)
    db.query(ClassificationCorrection).filter(
        ClassificationCorrection.transaction_id.in_(unique_ids)
    ).delete(synchronize_session=False)
    db.query(TransactionSplit).filter(
        TransactionSplit.parent_transaction_id.in_(unique_ids)
    ).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.transaction_id.in_(unique_ids)).delete(
        synchronize_session=False
    )
    deleted = db.query(Transaction).filter(Transaction.id.in_(unique_ids)).delete(
        synchronize_session=False
    )

    for goal in db.query(Goal).filter(Goal.id.in_(affected_goal_ids)).all():
        recompute_goal_balance(db, goal)
    return int(deleted or 0)
