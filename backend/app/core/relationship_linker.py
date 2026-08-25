"""Deterministic, reviewable links between economically related transactions."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session
from thefuzz import fuzz

from app.core.money import money_to_minor
from app.models.merchant_enrichment import TransactionRelationship
from app.models.transaction import Transaction


DETECTOR_VERSION = "1.0"
_INACTIVE = {"deleted", "reversed", "reversal", "voided"}


def _merchant_similarity(left: Transaction, right: Transaction) -> float:
    first = (left.merchant_normalized or left.merchant_raw or "").strip()
    second = (right.merchant_normalized or right.merchant_raw or "").strip()
    if not first or not second:
        return 0.0
    return fuzz.token_set_ratio(first, second) / 100.0


def _reference_match(left: Transaction, right: Transaction) -> bool:
    left_ref = left.reference_number or left.upi_ref_number
    right_ref = right.reference_number or right.upi_ref_number
    return bool(left_ref and right_ref and left_ref == right_ref)


def _relationship_kind(source: Transaction, target: Transaction) -> str | None:
    detail = source.semantic_detail or "unknown"
    if detail in {"refund", "chargeback", "tax_refund"}:
        return "refund_of"
    if detail == "reversal":
        return "reversal_of"
    if detail == "credit_card_payment" or target.semantic_detail == "credit_card_payment":
        return "credit_card_payment_pair"
    if detail == "wallet_topup" or target.semantic_detail == "wallet_topup":
        return "wallet_topup_pair"
    if source.type != target.type and source.account_id != target.account_id:
        return "internal_transfer_pair"
    if source.type == target.type and source.source != target.source:
        return "duplicate_of"
    return None


def suggest_transaction_relationships(
    db: Session,
    *,
    transaction_ids: set[str] | None = None,
) -> list[TransactionRelationship]:
    """Create non-destructive relationship evidence without changing totals."""

    query = db.query(Transaction).filter(Transaction.status.notin_(sorted(_INACTIVE)))
    sources = query.all()
    if transaction_ids is not None:
        sources = [transaction for transaction in sources if transaction.id in transaction_ids]
    if not sources:
        return []

    earliest = min(transaction.date for transaction in sources) - timedelta(days=45)
    latest = max(transaction.date for transaction in sources) + timedelta(days=45)
    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.status.notin_(sorted(_INACTIVE)),
            Transaction.date >= earliest,
            Transaction.date <= latest,
        )
        .all()
    )
    by_amount: dict[int, list[Transaction]] = defaultdict(list)
    for candidate in candidates:
        by_amount[money_to_minor(candidate.amount)].append(candidate)

    created: list[TransactionRelationship] = []
    for source in sources:
        for target in by_amount[money_to_minor(source.amount)]:
            if source.id == target.id:
                continue
            date_gap = abs((source.date - target.date).days)
            if date_gap > 45:
                continue
            kind = _relationship_kind(source, target)
            if not kind:
                continue
            if kind in {"refund_of", "reversal_of"}:
                if source.type == target.type or source.date < target.date:
                    continue
                if date_gap > (45 if kind == "refund_of" else 7):
                    continue
            elif kind in {
                "internal_transfer_pair",
                "credit_card_payment_pair",
                "wallet_topup_pair",
            }:
                if source.type == target.type or source.account_id == target.account_id or date_gap > 3:
                    continue
                # Store directional pairs once, from the outgoing debit to the
                # matching incoming credit. This prevents reciprocal evidence
                # rows for the same economic movement.
                if source.type != "debit":
                    continue
            elif kind == "duplicate_of":
                if date_gap > 1:
                    continue
                if source.id > target.id:
                    continue

            reference_match = _reference_match(source, target)
            merchant_similarity = _merchant_similarity(source, target)
            if not reference_match and merchant_similarity < (
                0.55 if kind in {"refund_of", "reversal_of"} else 0.80
            ):
                continue
            confidence = min(
                0.99,
                0.72
                + (0.20 if reference_match else 0.0)
                + (0.07 * merchant_similarity)
                + (0.03 if date_gap == 0 else 0.0),
            )
            existing = (
                db.query(TransactionRelationship)
                .filter_by(
                    from_transaction_id=source.id,
                    to_transaction_id=target.id,
                    relationship_type=kind,
                )
                .first()
            )
            if existing:
                continue
            evidence = ["amount:exact", f"date_gap_days:{date_gap}"]
            if reference_match:
                evidence.append("reference:exact")
            if merchant_similarity:
                evidence.append(f"merchant_similarity:{merchant_similarity:.2f}")
            relationship = TransactionRelationship(
                id=str(uuid.uuid4()),
                from_transaction_id=source.id,
                to_transaction_id=target.id,
                relationship_type=kind,
                confidence=confidence,
                status=("confirmed" if reference_match and confidence >= 0.98 else "pending"),
                date_gap_days=date_gap,
                reference_match=reference_match,
                evidence_json=json.dumps(evidence, separators=(",", ":")),
                detector_version=DETECTOR_VERSION,
            )
            db.add(relationship)
            created.append(relationship)
    db.flush()
    return created
