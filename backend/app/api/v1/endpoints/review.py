from __future__ import annotations

import json
import logging
import math
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.classification_learning import (
    classification_reason,
    record_explicit_correction,
)
from app.core.classifier import validate_category, validate_subcategory
from app.core.database import get_db
from app.core.errors import LocalOperationError
from app.core.transaction_semantics import apply_category_semantic, semantic_type_for
from app.core.llm_privacy import sanitize_untrusted_text
from app.core.llm_service import call_llm
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.taxonomy import TAXONOMY
from app.models.audit_log import AuditLog
from app.models.transaction import Transaction
from app.schemas.review import BatchResolveRequest, ReviewResolve, ReviewStats
from app.schemas.financial import ChatRole, FiniteUnitInterval

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Review Chat models ---

class ReviewChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)


class ReviewChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: List[ReviewChatMessage] = Field(default_factory=list, max_length=20)


class ClassificationOption(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    subcategory: Optional[str] = Field(default=None, max_length=50)
    confidence: Optional[FiniteUnitInterval] = None


class ReviewChatResponse(BaseModel):
    reply: str
    options: List[ClassificationOption] = Field(default_factory=list, max_length=3)


def _build_taxonomy_list() -> str:
    lines = []
    for cat, info in TAXONOMY.items():
        subcats = ', '.join(info['subcategories'])
        lines.append(f"- {cat}: [{subcats}]")
    return '\n'.join(lines)


REVIEW_CHAT_SYSTEM = """You are a financial transaction classification assistant for an Indian HDFC Bank user.

You are helping the user classify one specific transaction. Here are the transaction details:

TRANSACTION:
- Vendor text: {merchant_normalized}
- Amount: Rs {amount}
- Type: {txn_type}
- Payment Method: {instrument}

AVAILABLE CATEGORIES AND SUBCATEGORIES:
{taxonomy}

YOUR ROLE:
- Help the user understand what this transaction might be and suggest the best classification
- Be conversational but concise (2-3 sentences per response)
- When you have enough context to suggest classifications, ALWAYS include a JSON block with your top suggestions
- Use Indian Rupees (Rs) for amounts
- If the user describes what the transaction is for, suggest matching categories immediately

IMPORTANT: When suggesting classifications, include this JSON block at the END of your response:
```json
[{{"category": "CATEGORY_NAME", "subcategory": "Subcategory Name", "confidence": 0.9}}, ...]
```
Provide 1-3 options ranked by confidence. Only use categories and subcategories from the list above."""


def _parse_classification_options(text: str) -> list[dict]:
    """Extract classification options from LLM response."""
    # Try to find JSON array in code block or raw
    patterns = [
        r'```json\s*(\[.*?\])\s*```',
        r'```\s*(\[.*?\])\s*```',
        r'(\[\s*\{[^}]*"category"[^]]*\])',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                arr = json.loads(match.group(1))
                if isinstance(arr, list):
                    valid = []
                    for item in arr:
                        cat = item.get('category')
                        sub = item.get('subcategory')
                        try:
                            conf = float(item.get('confidence', 0.7))
                        except (TypeError, ValueError):
                            continue
                        if not math.isfinite(conf) or not 0 <= conf <= 1:
                            continue
                        if cat and validate_category(cat):
                            if sub and not validate_subcategory(cat, sub):
                                sub = None
                            valid.append({'category': cat, 'subcategory': sub, 'confidence': conf})
                    return valid
            except (json.JSONDecodeError, TypeError):
                continue
    return []


@router.get("/review/categories")
def get_categories(
    _user: bool = Depends(get_current_user),
):
    """Get all available categories and subcategories from taxonomy."""
    # Return in format expected by frontend: { "CATEGORY": ["sub1", "sub2"], ... }
    return {
        category: data["subcategories"]
        for category, data in TAXONOMY.items()
    }


@router.get("/review")
def list_review_queue(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    source: Optional[str] = None,
):
    query = (
        db.query(Transaction)
        .filter(Transaction.category.is_(None))
        .filter(Transaction.status != "deleted")
        .order_by(Transaction.date.desc())
    )
    if source:
        query = query.filter(Transaction.source == source)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "id": t.id,
                "date": str(t.date),
                "merchant_raw": t.merchant_raw,
                "merchant_normalized": t.merchant_normalized,
                "amount": t.amount,
                "type": t.type,
                "instrument": t.instrument,
                "source": t.source,
                "is_income": t.is_income or False,
                "semantic_type": semantic_type_for(t),
                "confidence": t.confidence,
                "classification_source": t.classification_source,
                "classification_reason": classification_reason(
                    t.classification_source
                ),
            }
            for t in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/review/{transaction_id}/resolve")
def resolve_review(
    transaction_id: str,
    body: ReviewResolve,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        txn = db.query(Transaction).filter_by(id=transaction_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if txn.is_locked:
            raise HTTPException(
                status_code=409,
                detail="Finalized transactions are read-only. Reopen the month first.",
            )

        if not validate_category(body.category):
            raise HTTPException(status_code=400, detail=f"Invalid category: {body.category}")

        if body.subcategory and not validate_subcategory(body.category, body.subcategory):
            raise HTTPException(status_code=400, detail=f"Invalid subcategory: {body.subcategory}")

        old_category = txn.category
        old_subcategory = txn.subcategory

        txn.category = body.category
        txn.subcategory = body.subcategory
        txn.confidence = 1.0
        txn.classification_source = "user"

        apply_category_semantic(txn, explicitly_classified=True)

        # Audit log
        db.add(AuditLog(
            transaction_id=txn.id,
            field_changed="category",
            old_value=old_category,
            new_value=body.category,
            change_source="user_review",
        ))
        if old_subcategory != body.subcategory:
            db.add(AuditLog(
                transaction_id=txn.id,
                field_changed="subcategory",
                old_value=old_subcategory,
                new_value=body.subcategory,
                change_source="user_review",
            ))

        # Update merchant_memory for future exact matches
        if txn.merchant_normalized:
            _update_merchant_memory(db, txn.merchant_normalized, body.category, body.subcategory)
            record_explicit_correction(
                db,
                txn,
                old_category,
                old_subcategory,
                body.category,
                body.subcategory,
            )

        db.commit()
        return {
            "status": "resolved",
            "id": txn.id,
            "category": body.category,
            "learned": bool(txn.merchant_normalized),
            "reason": classification_reason("user"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="REVIEW_UPDATE_FAILED",
            message="GODFIN could not save this classification.",
            hint="No partial change was kept. Try again.",
        ) from exc


@router.post("/review/batch-resolve")
def batch_resolve(
    body: BatchResolveRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    resolved = 0
    errors = []

    try:
        for item in body.items:
            txn = db.query(Transaction).filter_by(id=item.id).first()
            if not txn:
                errors.append(f"{item.id}: not found")
                continue
            if txn.is_locked:
                errors.append(f"{item.id}: finalized transaction is read-only")
                continue

            if not validate_category(item.category):
                errors.append(f"{item.id}: invalid category {item.category}")
                continue
            if item.subcategory and not validate_subcategory(
                item.category, item.subcategory
            ):
                errors.append(
                    f"{item.id}: invalid subcategory {item.subcategory}"
                )
                continue

            old_category = txn.category
            old_subcategory = txn.subcategory
            txn.category = item.category
            txn.subcategory = item.subcategory
            txn.confidence = 1.0
            txn.classification_source = "user"

            apply_category_semantic(txn, explicitly_classified=True)

            db.add(AuditLog(
                transaction_id=txn.id,
                field_changed="category",
                old_value=old_category,
                new_value=item.category,
                change_source="user_review",
            ))

            if txn.merchant_normalized:
                _update_merchant_memory(db, txn.merchant_normalized, item.category, item.subcategory)
                record_explicit_correction(
                    db,
                    txn,
                    old_category,
                    old_subcategory,
                    item.category,
                    item.subcategory,
                )

            resolved += 1

        db.commit()
        return {"resolved": resolved, "errors": errors}
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="REVIEW_BATCH_FAILED",
            message="GODFIN could not save these classifications.",
            hint="No partial batch was kept. Try again.",
        ) from exc


@router.get("/review/stats", response_model=ReviewStats)
def review_stats(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    queue_size = (
        db.query(Transaction)
        .filter(Transaction.category.is_(None))
        .filter(Transaction.status != "deleted")
        .count()
    )

    auto_accepted = (
        db.query(Transaction)
        .filter(Transaction.classification_source.in_(["exact_match", "rule", "fuzzy"]))
        .filter(Transaction.status != "deleted")
        .count()
    )

    soft_flagged = (
        db.query(Transaction)
        .filter(Transaction.confidence.isnot(None))
        .filter(Transaction.confidence < 0.85)
        .filter(Transaction.confidence >= 0.60)
        .filter(Transaction.category.isnot(None))
        .filter(Transaction.status != "deleted")
        .count()
    )

    return ReviewStats(
        queue_size=queue_size,
        auto_accepted=auto_accepted,
        soft_flagged=soft_flagged,
    )


@router.post("/review/{transaction_id}/chat", response_model=ReviewChatResponse)
def review_chat(
    transaction_id: str,
    body: ReviewChatRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Chat with AI to classify a specific transaction."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "ai_classification")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    txn = db.query(Transaction).filter_by(id=transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    system_prompt = REVIEW_CHAT_SYSTEM.format(
        merchant_normalized=(
            "<UNTRUSTED_VENDOR_TEXT>"
            + sanitize_untrusted_text(txn.merchant_normalized or "Unknown")
            + "</UNTRUSTED_VENDOR_TEXT>"
        ),
        amount=f"{txn.amount:,.2f}" if txn.amount else "0",
        txn_type=txn.type or "debit",
        instrument=txn.instrument or "Unknown",
        taxonomy=_build_taxonomy_list(),
    )

    # Build full prompt with conversation context
    prompt_parts = [f"System: {system_prompt}\n"]
    for msg in body.history[-4:]:
        prompt_parts.append(f"{msg.role.capitalize()}: {msg.content}")
    prompt_parts.append(f"User: {body.message.strip()}")
    prompt_parts.append("Assistant:")

    full_prompt = '\n'.join(prompt_parts)

    response = call_llm(full_prompt, temperature=0.4, purpose="review")
    if response is None:
        raise HTTPException(
            status_code=503,
            detail="AI is unavailable. Please configure an LLM provider in Settings.",
        )

    reply = response.strip()
    options = _parse_classification_options(reply)

    # Clean the JSON block from the displayed reply for cleaner chat
    clean_reply = re.sub(r'```json\s*\[.*?\]\s*```', '', reply, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'```\s*\[.*?\]\s*```', '', clean_reply, flags=re.DOTALL).strip()

    return ReviewChatResponse(
        reply=clean_reply,
        options=[ClassificationOption(**o) for o in options],
    )


def _update_merchant_memory(
    db: Session, normalized_name: str, category: str, subcategory: str | None
) -> None:
    upsert_merchant_memory(
        db,
        normalized_name,
        category,
        subcategory,
        confidence=1.0,
    )
