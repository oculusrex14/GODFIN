"""Authoritative transaction-domain semantics used by every financial surface.

Ledger direction (debit/credit) is deliberately separate from economic meaning.
A credit is not verified income merely because money moved into an account.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Iterable

from sqlalchemy import and_, func, or_


class TransactionSemantic(str, Enum):
    UNKNOWN = "unknown"
    EXPENSE = "expense"
    INCOME = "income"
    INTERNAL_TRANSFER = "internal_transfer"
    REFUND = "refund"
    REIMBURSEMENT = "reimbursement"
    REVERSAL = "reversal"
    CASHBACK = "cashback"
    ADJUSTMENT = "adjustment"
    EXCLUDED = "excluded"


VALID_SEMANTICS = frozenset(item.value for item in TransactionSemantic)
EXCLUDED_STATUSES = frozenset({"deleted", "reversed", "reversal", "voided"})
NON_INCOME_CREDIT_SEMANTICS = frozenset(
    {
        TransactionSemantic.INTERNAL_TRANSFER.value,
        TransactionSemantic.REFUND.value,
        TransactionSemantic.REIMBURSEMENT.value,
        TransactionSemantic.REVERSAL.value,
        TransactionSemantic.CASHBACK.value,
        TransactionSemantic.ADJUSTMENT.value,
        TransactionSemantic.EXCLUDED.value,
        TransactionSemantic.UNKNOWN.value,
    }
)
NON_INCOME_SUBCATEGORIES = frozenset({"refund", "cashback", "reimbursement", "reversal"})

_REFUND_TERMS = ("REFUND", "CHARGEBACK", "CRV POS")
_REVERSAL_TERMS = ("REVERSAL", "REVERSED", "RETURNED PAYMENT")
_CASHBACK_TERMS = ("CASHBACK", "CASH BACK")
_REIMBURSEMENT_TERMS = ("REIMBURSEMENT", "REIMBURSED")
_ADJUSTMENT_TERMS = ("ADJUSTMENT", "CORRECTION ENTRY")
_VERIFIED_INCOME_TERMS = (
    "SALARY",
    "WAGES",
    "PENSION",
    "INTEREST",
    "DIVIDEND",
    "BONUS",
    "INCENTIVE",
)


def _joined_text(parts: Iterable[Any]) -> str:
    return " ".join(str(part) for part in parts if part).upper()


def contains_semantic_term(text: str, terms: Iterable[str]) -> bool:
    upper = text.upper()
    return any(
        re.search(
            rf"(?<![A-Z0-9]){re.escape(term.upper())}(?![A-Z0-9])",
            upper,
        )
        is not None
        for term in terms
    )


def infer_semantic_type(
    *,
    transaction_type: str,
    category: str | None = None,
    subcategory: str | None = None,
    is_transfer: bool = False,
    status: str | None = None,
    text_parts: Iterable[Any] = (),
    explicitly_classified: bool = False,
) -> str:
    """Infer a conservative economic meaning from trusted evidence.

    This function never treats an otherwise-unclassified credit as income.
    Explicit user classification or deterministic income evidence is required.
    """
    normalized_status = (status or "settled").strip().lower()
    text = _joined_text(text_parts)
    normalized_category = (category or "").strip().upper()
    normalized_subcategory = (subcategory or "").strip().lower()

    if normalized_status == "deleted":
        return TransactionSemantic.EXCLUDED.value
    if normalized_status in EXCLUDED_STATUSES or contains_semantic_term(text, _REVERSAL_TERMS):
        return TransactionSemantic.REVERSAL.value
    if is_transfer or normalized_category == "TRANSFERS":
        return TransactionSemantic.INTERNAL_TRANSFER.value
    if contains_semantic_term(text, _REFUND_TERMS) or normalized_subcategory == "refund":
        return TransactionSemantic.REFUND.value
    if contains_semantic_term(text, _CASHBACK_TERMS) or normalized_subcategory == "cashback":
        return TransactionSemantic.CASHBACK.value
    if contains_semantic_term(text, _REIMBURSEMENT_TERMS) or normalized_subcategory == "reimbursement":
        return TransactionSemantic.REIMBURSEMENT.value
    if contains_semantic_term(text, _ADJUSTMENT_TERMS):
        return TransactionSemantic.ADJUSTMENT.value

    if transaction_type == "debit":
        return TransactionSemantic.EXPENSE.value
    if transaction_type != "credit":
        return TransactionSemantic.UNKNOWN.value

    category_is_verified_income = (
        normalized_category == "INCOME"
        and normalized_subcategory not in NON_INCOME_SUBCATEGORIES
    )
    if explicitly_classified and category_is_verified_income:
        return TransactionSemantic.INCOME.value
    if category_is_verified_income and contains_semantic_term(text, _VERIFIED_INCOME_TERMS):
        return TransactionSemantic.INCOME.value
    if contains_semantic_term(text, _VERIFIED_INCOME_TERMS):
        return TransactionSemantic.INCOME.value
    return TransactionSemantic.UNKNOWN.value


def semantic_type_for(transaction: Any) -> str:
    persisted = getattr(transaction, "semantic_type", None)
    if persisted in VALID_SEMANTICS and persisted != TransactionSemantic.UNKNOWN.value:
        return str(persisted)
    source = (getattr(transaction, "source", None) or "").lower()
    classification_source = (
        getattr(transaction, "classification_source", None) or ""
    ).lower()
    return infer_semantic_type(
        transaction_type=getattr(transaction, "type", ""),
        category=getattr(transaction, "category", None),
        subcategory=getattr(transaction, "subcategory", None),
        is_transfer=bool(getattr(transaction, "is_transfer", False)),
        status=getattr(transaction, "status", None),
        text_parts=(
            getattr(transaction, "raw_text", None),
            getattr(transaction, "merchant_raw", None),
            getattr(transaction, "merchant_normalized", None),
            getattr(transaction, "notes", None),
        ),
        explicitly_classified=(
            classification_source
            in {"user", "exact_match", "confirmed_pattern", "rule"}
            or source == "manual"
        ),
    )


def apply_transaction_semantic(transaction: Any, semantic_type: str) -> None:
    if semantic_type not in VALID_SEMANTICS:
        raise ValueError(f"Unsupported transaction semantic: {semantic_type}")
    transaction.semantic_type = semantic_type
    transaction.is_transfer = semantic_type == TransactionSemantic.INTERNAL_TRANSFER.value
    transaction.is_income = semantic_type == TransactionSemantic.INCOME.value


def apply_category_semantic(
    transaction: Any,
    *,
    explicitly_classified: bool,
) -> str:
    semantic_type = infer_semantic_type(
        transaction_type=getattr(transaction, "type", ""),
        category=getattr(transaction, "category", None),
        subcategory=getattr(transaction, "subcategory", None),
        is_transfer=(getattr(transaction, "category", None) == "TRANSFERS"),
        status=getattr(transaction, "status", None),
        text_parts=(
            getattr(transaction, "raw_text", None),
            getattr(transaction, "merchant_raw", None),
            getattr(transaction, "merchant_normalized", None),
            getattr(transaction, "notes", None),
        ),
        explicitly_classified=explicitly_classified,
    )
    apply_transaction_semantic(transaction, semantic_type)
    return semantic_type


def is_active_transaction(transaction: Any) -> bool:
    if (getattr(transaction, "status", None) or "settled").lower() in EXCLUDED_STATUSES:
        return False
    return semantic_type_for(transaction) != TransactionSemantic.EXCLUDED.value


def is_verified_income(transaction: Any) -> bool:
    return (
        is_active_transaction(transaction)
        and getattr(transaction, "type", None) == "credit"
        and not bool(getattr(transaction, "is_transfer", False))
        and semantic_type_for(transaction) == TransactionSemantic.INCOME.value
    )


def is_spending(transaction: Any) -> bool:
    return (
        is_active_transaction(transaction)
        and getattr(transaction, "type", None) == "debit"
        and not bool(getattr(transaction, "is_transfer", False))
        and semantic_type_for(transaction)
        not in {
            TransactionSemantic.INTERNAL_TRANSFER.value,
            TransactionSemantic.REVERSAL.value,
            TransactionSemantic.EXCLUDED.value,
        }
    )


def signed_ledger_amount(transaction: Any) -> float:
    """Return account-ledger movement; a matched transfer pair sums to zero."""
    if not is_active_transaction(transaction):
        return 0.0
    amount = float(getattr(transaction, "amount", 0.0) or 0.0)
    if getattr(transaction, "type", None) == "credit":
        return amount
    if getattr(transaction, "type", None) == "debit":
        return -amount
    return 0.0


def active_clause(model: Any):
    return and_(
        model.status.notin_(sorted(EXCLUDED_STATUSES)),
        model.semantic_type != TransactionSemantic.EXCLUDED.value,
    )


def verified_income_clause(model: Any):
    """SQL predicate matching the object-level verified-income invariant."""
    legacy_verified = and_(
        model.semantic_type == TransactionSemantic.UNKNOWN.value,
        model.is_income.is_(True),
        model.category == "INCOME",
        or_(
            model.subcategory.is_(None),
            ~func.lower(model.subcategory).in_(sorted(NON_INCOME_SUBCATEGORIES)),
        ),
    )
    return and_(
        active_clause(model),
        model.type == "credit",
        model.is_transfer.is_(False),
        or_(
            model.semantic_type == TransactionSemantic.INCOME.value,
            legacy_verified,
        ),
    )


def spending_clause(model: Any):
    return and_(
        active_clause(model),
        model.type == "debit",
        model.is_transfer.is_(False),
        ~model.semantic_type.in_(
            [
                TransactionSemantic.INTERNAL_TRANSFER.value,
                TransactionSemantic.REVERSAL.value,
                TransactionSemantic.EXCLUDED.value,
            ]
        ),
    )


def ledger_credit_clause(model: Any):
    return and_(active_clause(model), model.type == "credit")


def ledger_debit_clause(model: Any):
    return and_(active_clause(model), model.type == "debit")


def backfill_transaction_semantics(db: Any) -> int:
    """Conservatively repair old broad-credit flags after the additive migration."""
    from app.models.transaction import Transaction

    changed = 0
    transactions = db.query(Transaction).all()
    for transaction in transactions:
        inferred = semantic_type_for(transaction)
        old_state = (
            getattr(transaction, "semantic_type", None),
            bool(transaction.is_income),
            bool(transaction.is_transfer),
        )
        apply_transaction_semantic(transaction, inferred)
        new_state = (
            transaction.semantic_type,
            bool(transaction.is_income),
            bool(transaction.is_transfer),
        )
        if old_state != new_state:
            changed += 1
    return changed
