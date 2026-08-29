"""Shared deterministic follow-up work for statement-like transaction imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from app.core.classifier import classify_transaction
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.transaction_semantics import apply_category_semantic
from app.core.transaction_enrichment import refresh_transaction_enrichment
from app.models.transaction import Transaction


@dataclass(frozen=True)
class ImportPostprocessResult:
    classified: int
    review_queue: int


def postprocess_imported_transactions(
    db: Session,
    imported: Sequence[Transaction],
    parsed_rows: Sequence[object],
) -> ImportPostprocessResult:
    classified = 0
    review_queue = 0
    for index, transaction in enumerate(imported):
        parsed = parsed_rows[index] if index < len(parsed_rows) else None
        try:
            classification = classify_transaction(
                db,
                transaction.merchant_normalized or transaction.merchant_raw or "",
                float(transaction.amount),
                transaction.instrument or "statement",
                vpa_handle=transaction.vpa_handle,
                allow_ai_fallbacks=False,
            )
            if classification.category:
                transaction.category = classification.category
                transaction.subcategory = classification.subcategory
                transaction.confidence = classification.confidence
                transaction.classification_source = classification.source
                apply_category_semantic(
                    transaction,
                    explicitly_classified=classification.source
                    in {"exact_match", "confirmed_pattern", "rule"},
                )
                upsert_merchant_memory(
                    db,
                    transaction.merchant_normalized
                    or transaction.merchant_raw
                    or "",
                    classification.category,
                    classification.subcategory,
                    classification.confidence,
                )
                classified += 1
            elif parsed is not None and getattr(parsed, "category_hint", None):
                transaction.category = parsed.category_hint
                transaction.subcategory = getattr(parsed, "subcategory_hint", None)
                transaction.confidence = 0.65
                transaction.classification_source = "narration_hint"
                apply_category_semantic(
                    transaction,
                    explicitly_classified=(
                        getattr(parsed, "semantic_type", None) == "income"
                    ),
                )
                classified += 1
            refresh_transaction_enrichment(transaction)
            if transaction.review_required:
                review_queue += 1
        except Exception:
            transaction.review_required = True
            review_queue += 1

    merchant_keys = {
        (transaction.merchant_normalized, transaction.account_id)
        for transaction in imported
        if transaction.merchant_normalized
    }
    if merchant_keys:
        from app.core.goal_contributions import detect_goal_contribution_suggestions
        from app.core.license import has_feature
        from app.core.product_depth import sync_subscription_suggestions
        from app.core.recurring import detect_recurring_patterns

        detect_recurring_patterns(db, merchant_keys=merchant_keys)
        sync_subscription_suggestions(db, run_detection=False)
        if has_feature(db, "fd_rd_goal_detection"):
            detect_goal_contribution_suggestions(db, transactions=list(imported))
    return ImportPostprocessResult(
        classified=classified,
        review_queue=review_queue,
    )
