"""Conflict-safe merchant-memory writes shared by every ingestion path."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.merchant_memory import MerchantMemory

logger = logging.getLogger(__name__)


def upsert_merchant_memory(
    db: Session,
    normalized_name: str,
    category: str,
    subcategory: Optional[str] = None,
    confidence: float = 0.8,
    *,
    raw_string: Optional[str] = None,
) -> Optional[MerchantMemory]:
    """Insert or relearn a merchant without allowing a conflict to abort work.

    The nested transaction contains all merchant-memory-specific failures.
    A statement or Gmail import therefore remains committable even if this
    auxiliary learning write encounters an unexpected database problem.
    """
    normalized = (normalized_name or "").upper().strip()
    if not normalized or not category:
        return None

    seen = func.coalesce(MerchantMemory.times_seen, 0)
    previous_confidence = func.coalesce(MerchantMemory.avg_confidence, 0.0)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    statement = sqlite_insert(MerchantMemory).values(
        id=str(uuid.uuid4()),
        raw_string=(raw_string or normalized_name or normalized)[:255],
        normalized_name=normalized[:255],
        display_name=(raw_string or normalized_name or normalized).title()[:255],
        category=category,
        subcategory=subcategory,
        avg_confidence=float(confidence),
        times_seen=1,
        last_updated=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[MerchantMemory.normalized_name],
        set_={
            "category": statement.excluded.category,
            "subcategory": func.coalesce(
                statement.excluded.subcategory,
                MerchantMemory.subcategory,
            ),
            "times_seen": seen + 1,
            "avg_confidence": (
                (previous_confidence * seen) + float(confidence)
            ) / (seen + 1),
            "last_updated": now,
        },
    )

    try:
        with db.begin_nested():
            db.execute(statement)
        return (
            db.query(MerchantMemory)
            .filter_by(normalized_name=normalized[:255])
            .first()
        )
    except SQLAlchemyError as exc:
        logger.warning(
            "Merchant memory update skipped for %r: %s",
            normalized[:80],
            exc,
        )
        return None
