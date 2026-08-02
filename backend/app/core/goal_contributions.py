from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.models.goal import Goal
from app.models.goal_contribution import (
    GoalContribution,
    GoalContributionSuggestion,
)
from app.models.transaction import Transaction

_FD_PATTERNS = (
    re.compile(r"\bFIXED\s+DEPOSIT\b", re.IGNORECASE),
    re.compile(r"\bTERM\s+DEPOSIT\b", re.IGNORECASE),
    re.compile(r"\bFD\s+(?:BOOK(?:ING|ED)?|OPEN(?:ING|ED)?|CREAT(?:E|ED|ION))\b", re.IGNORECASE),
)
_RD_PATTERNS = (
    re.compile(r"\bRECURRING\s+DEPOSIT\b", re.IGNORECASE),
    re.compile(r"\bRD\s+(?:INSTALLMENT|INSTALMENT|BOOK(?:ING|ED)?|OPEN(?:ING|ED)?)\b", re.IGNORECASE),
)
_EXCLUDED_DEPOSIT_PATTERNS = re.compile(
    r"\b(?:MATURITY|MATURED|PREMATURE|CLOSURE|CLOSED|REVERSAL|REVERSED|"
    r"REFUND|INTEREST\s+CREDIT|RENEWAL\s+PROCEEDS)\b",
    re.IGNORECASE,
)
_INVALID_SOURCE_STATUSES = {"deleted", "reversed", "reversal", "voided"}


def contribution_to_dict(entry: GoalContribution) -> dict:
    return {
        "id": entry.id,
        "goal_id": entry.goal_id,
        "amount": round(float(entry.amount), 2),
        "contribution_date": entry.contribution_date.isoformat(),
        "entry_type": entry.entry_type,
        "source_type": entry.source_type,
        "source_transaction_id": entry.source_transaction_id,
        "note": entry.note,
        "is_voided": entry.is_voided,
        "voided_at": entry.voided_at.isoformat() if entry.voided_at else None,
        "void_reason": entry.void_reason,
        "created_at": entry.created_at.isoformat(),
    }


def suggestion_to_dict(
    suggestion: GoalContributionSuggestion,
    transaction: Transaction | None = None,
) -> dict:
    return {
        "id": suggestion.id,
        "transaction_id": suggestion.transaction_id,
        "goal_id": suggestion.goal_id,
        "amount": round(float(suggestion.amount), 2),
        "deposit_type": suggestion.deposit_type,
        "evidence": suggestion.evidence,
        "confidence": round(float(suggestion.confidence), 3),
        "status": suggestion.status,
        "decision_note": suggestion.decision_note,
        "transaction_date": transaction.date.isoformat() if transaction else None,
        "merchant": (
            transaction.merchant_normalized or transaction.merchant_raw
            if transaction
            else None
        ),
    }


def calculate_goal_balance(db: Session, goal_id: str) -> float:
    total = (
        db.query(func.coalesce(func.sum(GoalContribution.amount), 0.0))
        .filter(
            GoalContribution.goal_id == goal_id,
            GoalContribution.is_voided.is_(False),
        )
        .scalar()
    )
    return round(max(0.0, float(total or 0.0)), 2)


def recompute_goal_balance(db: Session, goal: Goal) -> float:
    goal.current_saved = calculate_goal_balance(db, goal.id)
    return goal.current_saved


def add_goal_contribution(
    db: Session,
    goal: Goal,
    *,
    amount: float,
    entry_type: str,
    contribution_date: date,
    note: str | None = None,
    source_type: str = "manual",
    source_transaction_id: str | None = None,
    idempotency_key: str | None = None,
) -> GoalContribution:
    if idempotency_key:
        existing = (
            db.query(GoalContribution)
            .filter_by(idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            return existing

    magnitude = round(abs(float(amount)), 2)
    if magnitude <= 0:
        raise ValueError("Contribution amount must be greater than zero.")
    signed_amount = -magnitude if entry_type == "withdrawal" else magnitude
    current_total = recompute_goal_balance(db, goal)
    if current_total + signed_amount < -0.005:
        raise ValueError("A withdrawal cannot reduce goal savings below zero.")

    entry = GoalContribution(
        goal_id=goal.id,
        amount=signed_amount,
        contribution_date=contribution_date,
        entry_type=entry_type,
        source_type=source_type,
        source_transaction_id=source_transaction_id,
        idempotency_key=idempotency_key,
        note=note,
    )
    db.add(entry)
    db.flush()
    recompute_goal_balance(db, goal)
    return entry


def void_goal_contribution(
    db: Session,
    entry: GoalContribution,
    *,
    reason: str,
) -> None:
    if entry.is_voided:
        return
    entry.is_voided = True
    entry.voided_at = utcnow_naive()
    entry.void_reason = reason[:255]
    goal = db.query(Goal).filter_by(id=entry.goal_id).first()
    if goal:
        recompute_goal_balance(db, goal)


def _deposit_evidence(transaction: Transaction) -> tuple[str, str, float] | None:
    if transaction.type != "debit" or transaction.is_transfer:
        return None
    if (transaction.status or "").lower() in _INVALID_SOURCE_STATUSES:
        return None
    if not transaction.reconciled:
        return None
    text = " ".join(
        part
        for part in (
            transaction.raw_text,
            transaction.merchant_raw,
            transaction.merchant_normalized,
            transaction.notes,
        )
        if part
    )
    if _EXCLUDED_DEPOSIT_PATTERNS.search(text):
        return None
    for pattern in _FD_PATTERNS:
        match = pattern.search(text)
        if match:
            return "fd", match.group(0), 0.96
    for pattern in _RD_PATTERNS:
        match = pattern.search(text)
        if match:
            return "rd", match.group(0), 0.96
    return None


def detect_goal_contribution_suggestions(
    db: Session,
    *,
    transactions: Iterable[Transaction] | None = None,
) -> int:
    candidates = list(transactions) if transactions is not None else (
        db.query(Transaction)
        .filter(
            Transaction.type == "debit",
            Transaction.status.notin_(_INVALID_SOURCE_STATUSES),
            Transaction.is_transfer.is_(False),
            Transaction.reconciled.is_(True),
        )
        .all()
    )
    existing_ids = {
        row[0]
        for row in db.query(GoalContributionSuggestion.transaction_id)
        .filter(
            GoalContributionSuggestion.transaction_id.in_(
                [transaction.id for transaction in candidates]
            )
        )
        .all()
    } if candidates else set()
    active_goals = db.query(Goal).filter_by(is_active=True).all()
    default_goal_id = active_goals[0].id if len(active_goals) == 1 else None

    created = 0
    for transaction in candidates:
        if transaction.id in existing_ids:
            continue
        evidence = _deposit_evidence(transaction)
        if not evidence:
            continue
        deposit_type, matched_text, confidence = evidence

        # Email and statement records with the same canonical checksum must
        # never produce two review items.
        if transaction.checksum_canonical:
            duplicate = (
                db.query(GoalContributionSuggestion)
                .join(
                    Transaction,
                    Transaction.id == GoalContributionSuggestion.transaction_id,
                )
                .filter(
                    Transaction.checksum_canonical == transaction.checksum_canonical
                )
                .first()
            )
            if duplicate:
                continue

        db.add(
            GoalContributionSuggestion(
                transaction_id=transaction.id,
                goal_id=default_goal_id,
                amount=round(float(transaction.amount), 2),
                deposit_type=deposit_type,
                evidence=f"Matched {matched_text[:180]} in a reconciled debit.",
                confidence=confidence,
                status="pending",
            )
        )
        created += 1
    db.flush()
    return created


def assign_goal_contribution_suggestion(
    db: Session,
    suggestion: GoalContributionSuggestion,
    *,
    goal: Goal | None,
) -> GoalContribution | None:
    if suggestion.status != "pending":
        raise ValueError("This suggestion has already been reviewed.")
    suggestion.decided_at = utcnow_naive()
    if goal is None:
        suggestion.status = "dismissed"
        suggestion.goal_id = None
        suggestion.decision_note = "User selected None."
        return None

    transaction = db.query(Transaction).filter_by(id=suggestion.transaction_id).first()
    if not transaction or _deposit_evidence(transaction) is None:
        suggestion.status = "voided"
        suggestion.decision_note = "Source transaction is no longer eligible."
        raise ValueError("The source transaction is no longer eligible.")

    contribution = add_goal_contribution(
        db,
        goal,
        amount=suggestion.amount,
        entry_type="deposit",
        contribution_date=transaction.date,
        note=f"{suggestion.deposit_type.upper()} contribution confirmed from transaction.",
        source_type="fd_rd_suggestion",
        source_transaction_id=transaction.id,
        idempotency_key=f"fd-rd:{transaction.id}",
    )
    suggestion.goal_id = goal.id
    suggestion.status = "assigned"
    suggestion.decision_note = "Confirmed by user."
    return contribution


def reconcile_goal_source_transactions(db: Session) -> int:
    entries = (
        db.query(GoalContribution)
        .filter(
            GoalContribution.source_transaction_id.isnot(None),
            GoalContribution.is_voided.is_(False),
        )
        .all()
    )
    if not entries:
        return 0
    transactions = {
        transaction.id: transaction
        for transaction in db.query(Transaction)
        .filter(
            Transaction.id.in_(
                [entry.source_transaction_id for entry in entries]
            )
        )
        .all()
    }
    voided = 0
    for entry in entries:
        transaction = transactions.get(entry.source_transaction_id)
        if transaction and _deposit_evidence(transaction) is not None:
            continue
        void_goal_contribution(
            db,
            entry,
            reason="Source transaction was deleted, reversed, or became ineligible.",
        )
        suggestion = (
            db.query(GoalContributionSuggestion)
            .filter_by(transaction_id=entry.source_transaction_id)
            .first()
        )
        if suggestion:
            suggestion.status = "voided"
            suggestion.decision_note = "Source transaction became ineligible."
            suggestion.decided_at = utcnow_naive()
        voided += 1
    return voided
