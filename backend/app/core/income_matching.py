from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.core.transaction_semantics import TransactionSemantic, semantic_type_for
from app.models.income_source import IncomeMatchSuggestion, IncomeSource
from app.models.transaction import Transaction


UNSAFE_CREDIT_SEMANTICS = frozenset(
    {
        TransactionSemantic.INTERNAL_TRANSFER.value,
        TransactionSemantic.REFUND.value,
        TransactionSemantic.REIMBURSEMENT.value,
        TransactionSemantic.REVERSAL.value,
        TransactionSemantic.CASHBACK.value,
        TransactionSemantic.ADJUSTMENT.value,
        TransactionSemantic.EXCLUDED.value,
    }
)
UNSAFE_TEXT_TERMS = (
    "REFUND",
    "REVERSAL",
    "REVERSED",
    "CASHBACK",
    "REIMBURSEMENT",
    "OWN ACCOUNT",
    "SELF TRANSFER",
    "CREDIT CARD PAYMENT",
)


@dataclass(frozen=True)
class IncomeMatchScanResult:
    scanned: int
    candidates: int
    strong: int
    uncertain: int
    excluded_unsafe: int
    coverage_start: date | None
    coverage_end: date | None


def _normalized(value: str | None) -> str:
    return " ".join(re.findall(r"[A-Z0-9]+", str(value or "").upper()))


def _transaction_text(transaction: Transaction) -> str:
    return _normalized(
        " ".join(
            value
            for value in (
                transaction.raw_text,
                transaction.merchant_raw,
                transaction.merchant_normalized,
                transaction.notes,
            )
            if value
        )
    )


def eligible_income_credit(transaction: Transaction) -> bool:
    if transaction.type != "credit" or transaction.is_locked:
        return False
    if transaction.status in {"deleted", "reversed", "reversal", "voided"}:
        return False
    if transaction.is_transfer:
        return False
    semantic = semantic_type_for(transaction)
    if semantic in UNSAFE_CREDIT_SEMANTICS:
        return False
    text = _transaction_text(transaction)
    return not any(term in text for term in UNSAFE_TEXT_TERMS)


def _candidate_evidence(
    source: IncomeSource,
    transaction: Transaction,
) -> tuple[float, list[str]] | None:
    text = _transaction_text(transaction)
    semantic = semantic_type_for(transaction)
    evidence: list[str] = []
    score = 0.0

    alias = _normalized(source.confirmed_merchant_alias)
    alias_match = bool(alias and alias in text)
    if alias_match:
        evidence.append("Confirmed payer name appears in this credit")
        score += 0.45

    source_tokens = [
        token
        for token in _normalized(source.source_name).split()
        if len(token) >= 3
    ]
    name_match = bool(source_tokens and all(token in text for token in source_tokens))
    if name_match:
        evidence.append("Income source name appears in this credit")
        score += 0.30

    if semantic == TransactionSemantic.INCOME.value:
        evidence.append("This credit is already verified as income")
        score += 0.35

    expected = float(source.expected_amount or 0)
    amount_matches = False
    if expected > 0:
        tolerance = max(0.0, min(float(source.amount_tolerance or 0), 1.0))
        amount_matches = abs(float(transaction.amount) - expected) <= expected * tolerance
        if amount_matches:
            evidence.append("Amount is within the source's expected range")
            score += 0.20

    if source.account_id:
        if transaction.account_id != source.account_id:
            return None
        evidence.append("Credit arrived in the selected account")
        score += 0.05

    if source.payment_rail:
        if _normalized(transaction.instrument) != _normalized(source.payment_rail):
            return None
        evidence.append("Payment method matches the source")
        score += 0.05

    # Amount alone is never enough to convert an unknown credit into income.
    if not (alias_match or name_match or semantic == TransactionSemantic.INCOME.value):
        return None
    if expected > 0 and not amount_matches and not alias_match:
        return None
    if score < 0.45:
        return None
    return min(round(score, 4), 1.0), evidence


def scan_historical_income_matches(
    db: Session,
    source: IncomeSource,
) -> IncomeMatchScanResult:
    end = min(source.effective_to or date.today(), date.today())
    query = db.query(Transaction).filter(
        Transaction.date >= source.effective_from,
        Transaction.date <= end,
        Transaction.type == "credit",
        Transaction.status.notin_(("deleted", "reversed", "reversal", "voided")),
    )
    if source.account_id:
        query = query.filter(Transaction.account_id == source.account_id)
    transactions = query.order_by(Transaction.date.asc(), Transaction.id.asc()).all()

    existing = {
        item.transaction_id: item
        for item in db.query(IncomeMatchSuggestion)
        .filter(IncomeMatchSuggestion.income_source_id == source.id)
        .all()
    }
    candidate_ids: set[str] = set()
    excluded_unsafe = 0
    strong = 0
    uncertain = 0
    for transaction in transactions:
        if not eligible_income_credit(transaction):
            excluded_unsafe += 1
            continue
        match = _candidate_evidence(source, transaction)
        if match is None:
            continue
        confidence, evidence = match
        strength = "strong" if confidence >= 0.75 else "uncertain"
        strong += strength == "strong"
        uncertain += strength == "uncertain"
        candidate_ids.add(transaction.id)
        suggestion = existing.get(transaction.id)
        if suggestion is None:
            suggestion = IncomeMatchSuggestion(
                id=str(uuid.uuid4()),
                income_source_id=source.id,
                transaction_id=transaction.id,
                confidence=confidence,
                strength=strength,
                evidence_json=json.dumps(evidence, separators=(",", ":")),
                status="pending",
            )
            db.add(suggestion)
        elif suggestion.status in {"pending", "stale"}:
            suggestion.confidence = confidence
            suggestion.strength = strength
            suggestion.evidence_json = json.dumps(evidence, separators=(",", ":"))
            suggestion.status = "pending"
            suggestion.updated_at = utcnow_naive()

    for transaction_id, suggestion in existing.items():
        if suggestion.status == "pending" and transaction_id not in candidate_ids:
            suggestion.status = "stale"
            suggestion.updated_at = utcnow_naive()
    db.flush()
    return IncomeMatchScanResult(
        scanned=len(transactions),
        candidates=len(candidate_ids),
        strong=strong,
        uncertain=uncertain,
        excluded_unsafe=excluded_unsafe,
        coverage_start=source.effective_from,
        coverage_end=end,
    )


def suggestion_evidence(suggestion: IncomeMatchSuggestion) -> list[str]:
    try:
        evidence = json.loads(suggestion.evidence_json)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item)[:180] for item in evidence if isinstance(item, str)] if isinstance(evidence, list) else []
