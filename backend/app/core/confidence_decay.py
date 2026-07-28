"""
Confidence decay system for merchant memory.
Reduces confidence scores for merchants not seen in a long time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.merchant_memory import MerchantMemory

logger = logging.getLogger(__name__)

# Configuration
DECAY_DAYS = 180  # 6 months
DECAY_FACTOR = 0.95  # Reduce confidence by 5% every decay period
MIN_CONFIDENCE = 0.5  # Floor for decayed confidence


def apply_confidence_decay(
    db: Session,
    decay_days: int = DECAY_DAYS,
    decay_factor: float = DECAY_FACTOR,
    min_confidence: float = MIN_CONFIDENCE,
) -> int:
    """
    Apply confidence decay to merchants not seen recently.

    Args:
        db: Database session
        decay_days: Days before confidence starts decaying
        decay_factor: Multiplier for confidence (0.95 = 5% decay)
        min_confidence: Minimum confidence floor

    Returns:
        Number of merchants updated
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=decay_days)

    # Find merchants not updated since cutoff
    stale_merchants = db.query(MerchantMemory).filter(
        MerchantMemory.last_updated < cutoff_date,
        MerchantMemory.avg_confidence > min_confidence,
    ).all()

    updated = 0
    for merchant in stale_merchants:
        old_confidence = merchant.avg_confidence
        new_confidence = max(old_confidence * decay_factor, min_confidence)

        if new_confidence != old_confidence:
            merchant.avg_confidence = new_confidence
            updated += 1
            logger.debug(
                f"Decayed confidence for {merchant.normalized_name}: "
                f"{old_confidence:.3f} -> {new_confidence:.3f}"
            )

    if updated:
        db.commit()
        logger.info(f"Applied confidence decay to {updated} merchants")

    return updated


def get_stale_merchants(
    db: Session,
    days: int = DECAY_DAYS,
    limit: Optional[int] = None,
) -> list[MerchantMemory]:
    """
    Get list of merchants that haven't been seen recently.

    Args:
        db: Database session
        days: Days threshold
        limit: Optional limit on results

    Returns:
        List of stale merchant memories
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    query = db.query(MerchantMemory).filter(
        MerchantMemory.last_updated < cutoff_date
    ).order_by(MerchantMemory.last_updated)

    if limit:
        query = query.limit(limit)

    return query.all()


def refresh_merchant_confidence(
    db: Session,
    merchant_id: str,
    new_confidence: Optional[float] = None,
) -> bool:
    """
    Refresh confidence for a specific merchant (e.g., after seeing it again).

    Args:
        db: Database session
        merchant_id: Merchant memory ID
        new_confidence: Optional explicit confidence value, otherwise resets to 1.0

    Returns:
        True if updated, False if not found
    """
    merchant = db.query(MerchantMemory).filter_by(id=merchant_id).first()
    if not merchant:
        return False

    merchant.avg_confidence = new_confidence if new_confidence else 1.0
    merchant.last_updated = datetime.now(timezone.utc)
    db.commit()

    return True
