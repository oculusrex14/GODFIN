"""Transparent supervised learning from explicit transaction corrections."""
from __future__ import annotations

import csv
import io
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.csv_security import spreadsheet_safe_row
from app.models.app_setting import AppSetting
from app.models.classification_learning import (
    ClassificationCorrection,
    ClassificationPattern,
)
from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction


PATTERN_STOP_WORDS = {
    "UPI",
    "POS",
    "PAYMENT",
    "PURCHASE",
    "DEBIT",
    "CREDIT",
    "BANK",
    "REF",
    "REFERENCE",
    "TXN",
    "TRANSACTION",
    "INDIA",
    "PVT",
    "LTD",
}
PERSONAL_MIN_CORRECTIONS = 200
PERSONAL_MIN_CATEGORIES = 5


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def merchant_tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^A-Z0-9]+", " ", (value or "").upper())
    tokens = []
    for token in normalized.split():
        if token in PATTERN_STOP_WORDS:
            continue
        if token.isdigit() or len(token) < 3:
            continue
        if sum(character.isdigit() for character in token) >= 3:
            continue
        tokens.append(token)
    return tokens[:8]


def build_pattern_key(merchant_normalized: str, instrument: str | None) -> tuple[str | None, str]:
    tokens = merchant_tokens(merchant_normalized)
    if not tokens:
        return None, ""
    display = " ".join(tokens)
    return f"{(instrument or 'unknown').lower()}|{display}", display


def record_explicit_correction(
    db: Session,
    transaction: Transaction,
    old_category: str | None,
    old_subcategory: str | None,
    new_category: str,
    new_subcategory: str | None,
) -> ClassificationCorrection | None:
    """Record one user-approved label and update the generalized pattern layer."""
    if transaction.is_locked or not transaction.merchant_normalized:
        return None

    pattern_key, pattern_display = build_pattern_key(
        transaction.merchant_normalized,
        transaction.instrument,
    )
    correction = ClassificationCorrection(
        id=str(uuid.uuid4()),
        transaction_id=transaction.id,
        merchant_normalized=transaction.merchant_normalized[:255],
        pattern_key=pattern_key,
        instrument=transaction.instrument,
        old_category=old_category,
        old_subcategory=old_subcategory,
        new_category=new_category,
        new_subcategory=new_subcategory,
    )
    db.add(correction)

    if pattern_key:
        seen = func.coalesce(ClassificationPattern.confirmations, 0)
        statement = sqlite_insert(ClassificationPattern).values(
            id=str(uuid.uuid4()),
            pattern_key=pattern_key[:255],
            pattern_display=pattern_display[:255],
            instrument=transaction.instrument,
            category=new_category,
            subcategory=new_subcategory,
            confirmations=1,
            confidence=0.75,
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ClassificationPattern.pattern_key],
            set_={
                "category": statement.excluded.category,
                "subcategory": statement.excluded.subcategory,
                "confirmations": seen + 1,
                "confidence": func.min(0.95, 0.70 + ((seen + 1) * 0.05)),
                "is_active": True,
                "updated_at": _now(),
            },
        )
        db.execute(statement)
    return correction


def match_confirmed_pattern(
    db: Session,
    merchant_normalized: str,
    instrument: str | None,
) -> ClassificationPattern | None:
    pattern_key, _ = build_pattern_key(merchant_normalized, instrument)
    if not pattern_key:
        return None
    return (
        db.query(ClassificationPattern)
        .filter_by(pattern_key=pattern_key[:255], is_active=True)
        .filter(ClassificationPattern.confirmations >= 2)
        .first()
    )


def personal_classifier_eligibility(db: Session) -> dict:
    active = db.query(ClassificationCorrection).filter(
        ClassificationCorrection.undone_at.is_(None)
    )
    confirmed = active.count()
    categories = (
        active.with_entities(ClassificationCorrection.new_category)
        .distinct()
        .count()
    )
    setting = db.query(AppSetting).filter_by(
        key="personal_classification_enabled"
    ).first()
    eligible = (
        confirmed >= PERSONAL_MIN_CORRECTIONS
        and categories >= PERSONAL_MIN_CATEGORIES
    )
    return {
        "eligible": eligible,
        "enabled": bool(setting and setting.value == "true" and eligible),
        "confirmed_corrections": confirmed,
        "required_corrections": PERSONAL_MIN_CORRECTIONS,
        "category_count": categories,
        "required_categories": PERSONAL_MIN_CATEGORIES,
    }


def match_personal_classifier(
    db: Session,
    merchant_normalized: str,
) -> Optional[dict]:
    eligibility = personal_classifier_eligibility(db)
    if not eligibility["enabled"]:
        return None
    target = set(merchant_tokens(merchant_normalized))
    if not target:
        return None

    corrections = (
        db.query(ClassificationCorrection)
        .filter(ClassificationCorrection.undone_at.is_(None))
        .order_by(ClassificationCorrection.created_at.desc())
        .limit(1000)
        .all()
    )
    category_scores: dict[tuple[str, str | None], list[float]] = defaultdict(list)
    for correction in corrections:
        tokens = set(merchant_tokens(correction.merchant_normalized))
        if not tokens:
            continue
        overlap = len(target & tokens) / len(target | tokens)
        if overlap:
            category_scores[
                (correction.new_category, correction.new_subcategory)
            ].append(overlap)
    if not category_scores:
        return None

    ranked = sorted(
        (
            (
                max(scores) * 0.7 + (sum(scores) / len(scores)) * 0.3,
                category,
                subcategory,
                len(scores),
            )
            for (category, subcategory), scores in category_scores.items()
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, category, subcategory, examples = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0
    if best_score < 0.62 or best_score - runner_up < 0.12:
        return None
    return {
        "category": category,
        "subcategory": subcategory,
        "confidence": min(0.88, 0.68 + best_score * 0.2),
        "examples": examples,
    }


def classification_reason(source: str | None) -> str:
    reasons = {
        "transfer_detect": "Detected as a transfer from payment and account clues.",
        "exact_match": "Matched an exact merchant label you previously confirmed.",
        "confirmed_pattern": "Matched a transaction-description pattern confirmed at least twice.",
        "rule": "Matched an active deterministic classification rule.",
        "fuzzy": "Matched a similar merchant name from local memory.",
        "embedding": "Matched similar local merchant text using optional embeddings.",
        "personal_model": "Matched your optional personal classifier after its minimum evidence threshold.",
        "llm": "Suggested by the configured AI provider; totals never depend on this suggestion.",
        "user": "Explicitly classified by you.",
        "user_undo": "Restored after you undid a learning correction.",
        "narration_hint": "Suggested by the deterministic statement parser.",
        "unclassified": "No reliable local rule or learned match was found.",
    }
    return reasons.get(source or "unclassified", "Classification source is unavailable.")


def list_learning_memory(db: Session, limit: int = 100) -> dict:
    patterns = (
        db.query(ClassificationPattern)
        .order_by(ClassificationPattern.updated_at.desc())
        .limit(limit)
        .all()
    )
    corrections = (
        db.query(ClassificationCorrection)
        .order_by(ClassificationCorrection.created_at.desc())
        .limit(limit)
        .all()
    )
    merchants = (
        db.query(MerchantMemory)
        .order_by(MerchantMemory.last_updated.desc())
        .limit(limit)
        .all()
    )
    return {
        "eligibility": personal_classifier_eligibility(db),
        "patterns": [
            {
                "id": item.id,
                "pattern": item.pattern_display,
                "instrument": item.instrument,
                "category": item.category,
                "subcategory": item.subcategory,
                "confirmations": item.confirmations,
                "confidence": item.confidence,
                "active": item.is_active,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in patterns
        ],
        "corrections": [
            {
                "id": item.id,
                "transaction_id": item.transaction_id,
                "merchant": item.merchant_normalized,
                "old_category": item.old_category,
                "new_category": item.new_category,
                "new_subcategory": item.new_subcategory,
                "undone": item.undone_at is not None,
                "created_at": item.created_at.isoformat(),
            }
            for item in corrections
        ],
        "merchants": [
            {
                "id": item.id,
                "merchant": item.normalized_name,
                "category": item.category,
                "subcategory": item.subcategory,
                "times_seen": item.times_seen,
                "confidence": item.avg_confidence,
            }
            for item in merchants
        ],
    }


def undo_correction(db: Session, correction_id: str) -> ClassificationCorrection:
    correction = db.query(ClassificationCorrection).filter_by(id=correction_id).first()
    if not correction:
        raise ValueError("Correction not found")
    if correction.undone_at:
        raise ValueError("Correction was already undone")
    transaction = db.query(Transaction).filter_by(id=correction.transaction_id).first()
    if not transaction:
        raise ValueError("Original transaction no longer exists")
    if transaction.is_locked:
        raise ValueError("Finalized transactions cannot be changed")

    transaction.category = correction.old_category
    transaction.subcategory = correction.old_subcategory
    transaction.classification_source = "user_undo"
    transaction.confidence = 1.0 if correction.old_category else None
    correction.undone_at = _now()

    if correction.pattern_key:
        remaining = (
            db.query(ClassificationCorrection)
            .filter_by(pattern_key=correction.pattern_key)
            .filter(ClassificationCorrection.undone_at.is_(None))
            .order_by(ClassificationCorrection.created_at.desc())
            .all()
        )
        pattern = (
            db.query(ClassificationPattern)
            .filter_by(pattern_key=correction.pattern_key)
            .first()
        )
        if pattern:
            if remaining:
                latest = remaining[0]
                pattern.category = latest.new_category
                pattern.subcategory = latest.new_subcategory
                pattern.confirmations = len(remaining)
                pattern.confidence = min(0.95, 0.70 + len(remaining) * 0.05)
                pattern.is_active = True
            else:
                pattern.is_active = False
                pattern.confirmations = 0
                pattern.confidence = 0

    memory = (
        db.query(MerchantMemory)
        .filter_by(normalized_name=correction.merchant_normalized)
        .first()
    )
    if memory:
        if correction.old_category:
            memory.category = correction.old_category
            memory.subcategory = correction.old_subcategory
            memory.avg_confidence = 1.0
        elif memory.times_seen <= 1:
            db.delete(memory)
    return correction


def reset_learning_memory(db: Session) -> dict:
    patterns = db.query(ClassificationPattern).delete()
    corrections = db.query(ClassificationCorrection).delete()
    merchants = db.query(MerchantMemory).delete()
    setting = db.query(AppSetting).filter_by(
        key="personal_classification_enabled"
    ).first()
    if setting:
        setting.value = "false"
    return {
        "patterns_removed": patterns,
        "corrections_removed": corrections,
        "merchant_memories_removed": merchants,
    }


def export_learning_memory_csv(db: Session) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "memory_type",
            "merchant_or_pattern",
            "category",
            "subcategory",
            "confirmations_or_times_seen",
            "confidence",
        ]
    )
    for merchant in db.query(MerchantMemory).order_by(MerchantMemory.normalized_name):
        writer.writerow(
            spreadsheet_safe_row(
                [
                    "exact_merchant",
                    merchant.normalized_name,
                    merchant.category,
                    merchant.subcategory or "",
                    merchant.times_seen,
                    merchant.avg_confidence,
                ]
            )
        )
    for pattern in db.query(ClassificationPattern).order_by(
        ClassificationPattern.pattern_display
    ):
        writer.writerow(
            spreadsheet_safe_row(
                [
                    "confirmed_pattern",
                    pattern.pattern_display,
                    pattern.category,
                    pattern.subcategory or "",
                    pattern.confirmations,
                    pattern.confidence,
                ]
            )
        )
    return output.getvalue()
