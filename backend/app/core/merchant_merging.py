"""
Merchant merging and deduplication system.
Detects similar merchant names and suggests consolidations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from thefuzz import fuzz

from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class MergeSuggestion:
    """Suggested merchant merge."""
    primary_id: str
    primary_name: str
    duplicate_id: str
    duplicate_name: str
    similarity_score: float
    primary_category: str
    duplicate_category: str
    primary_times_seen: int
    duplicate_times_seen: int
    confidence: float


def find_similar_merchants(
    db: Session,
    threshold: int = 80,
    min_length: int = 4,
) -> list[MergeSuggestion]:
    """
    Find merchants with similar names that might be duplicates.

    Args:
        db: Database session
        threshold: Minimum similarity score (0-100)
        min_length: Minimum merchant name length to consider

    Returns:
        List of merge suggestions
    """
    memories = db.query(MerchantMemory).all()
    suggestions = []
    checked_pairs = set()

    for i, mem1 in enumerate(memories):
        # Skip short names
        if len(mem1.normalized_name) < min_length:
            continue

        for mem2 in memories[i + 1:]:
            # Skip short names
            if len(mem2.normalized_name) < min_length:
                continue

            # Create unique pair identifier
            pair = tuple(sorted([mem1.id, mem2.id]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)

            # Calculate similarity
            similarity = fuzz.ratio(
                mem1.normalized_name.upper(),
                mem2.normalized_name.upper()
            )

            if similarity >= threshold:
                # Determine which is primary (higher times_seen)
                if mem1.times_seen >= mem2.times_seen:
                    primary, duplicate = mem1, mem2
                else:
                    primary, duplicate = mem2, mem1

                suggestions.append(MergeSuggestion(
                    primary_id=primary.id,
                    primary_name=primary.normalized_name,
                    duplicate_id=duplicate.id,
                    duplicate_name=duplicate.normalized_name,
                    similarity_score=similarity,
                    primary_category=primary.category,
                    duplicate_category=duplicate.category,
                    primary_times_seen=primary.times_seen,
                    duplicate_times_seen=duplicate.times_seen,
                    confidence=similarity / 100.0,
                ))

    # Sort by confidence descending
    suggestions.sort(key=lambda x: x.similarity_score, reverse=True)

    return suggestions


def find_merging_candidates(
    db: Session,
    threshold: int = 80,
    max_results: int = 20,
) -> list[MergeSuggestion]:
    """
    Get top candidates for merging.

    Args:
        db: Database session
        threshold: Minimum similarity score
        max_results: Maximum number of results

    Returns:
        Top merge suggestions
    """
    suggestions = find_similar_merchants(db, threshold=threshold)

    # Filter out suggestions with category mismatches (higher risk)
    high_confidence = [s for s in suggestions if s.primary_category == s.duplicate_category]
    medium_confidence = [s for s in suggestions if s.primary_category != s.duplicate_category]

    # Prioritize same-category merges
    return (high_confidence + medium_confidence)[:max_results]


def merge_merchants(
    db: Session,
    primary_id: str,
    duplicate_id: str,
    update_transactions: bool = True,
) -> dict:
    """
    Merge two merchant entries.

    Args:
        db: Database session
        primary_id: ID of merchant to keep
        duplicate_id: ID of merchant to merge into primary
        update_transactions: Whether to update transaction references

    Returns:
        Merge result summary
    """
    primary = db.query(MerchantMemory).filter_by(id=primary_id).first()
    duplicate = db.query(MerchantMemory).filter_by(id=duplicate_id).first()

    if not primary or not duplicate:
        raise ValueError("One or both merchants not found")

    # Aggregate stats
    primary.times_seen += duplicate.times_seen
    primary.avg_confidence = max(primary.avg_confidence, duplicate.avg_confidence)

    # Update transactions if requested
    updated_count = 0
    if update_transactions:
        txns = db.query(Transaction).filter_by(
            merchant_normalized=duplicate.normalized_name
        ).all()
        for txn in txns:
            txn.merchant_normalized = primary.normalized_name
            txn.merchant_raw = primary.display_name or primary.normalized_name
            updated_count += 1

    # Delete duplicate
    db.delete(duplicate)
    db.flush()

    logger.info(
        f"Merged merchant '{duplicate.normalized_name}' into "
        f"'{primary.normalized_name}' - updated {updated_count} transactions"
    )

    return {
        "success": True,
        "primary": primary.normalized_name,
        "duplicate": duplicate.normalized_name,
        "transactions_updated": updated_count,
    }


def get_duplicate_groups(
    db: Session,
    threshold: int = 85,
) -> list[dict]:
    """
    Group similar merchants into clusters for bulk merging.

    Args:
        db: Database session
        threshold: Similarity threshold

    Returns:
        List of duplicate groups
    """
    suggestions = find_similar_merchants(db, threshold=threshold)

    # Group by primary
    groups = {}
    for s in suggestions:
        if s.primary_id not in groups:
            groups[s.primary_id] = {
                "primary": {
                    "id": s.primary_id,
                    "name": s.primary_name,
                    "category": s.primary_category,
                    "times_seen": s.primary_times_seen,
                },
                "duplicates": [],
            }
        groups[s.primary_id]["duplicates"].append({
            "id": s.duplicate_id,
            "name": s.duplicate_name,
            "category": s.duplicate_category,
            "similarity": s.similarity_score,
            "times_seen": s.duplicate_times_seen,
        })

    # Convert to list and sort by total times_seen
    group_list = list(groups.values())
    group_list.sort(
        key=lambda g: g["primary"]["times_seen"] + sum(
            d["times_seen"] for d in g["duplicates"]
        ),
        reverse=True,
    )

    return group_list


def normalize_merchant_name(name: str) -> str:
    """
    Normalize a merchant name for comparison.

    Args:
        name: Raw merchant name

    Returns:
        Normalized name
    """
    import re

    # Uppercase
    normalized = name.upper()

    # Remove common suffixes/prefixes
    patterns = [
        r'\s*PRIVATE\s*LIMITED\s*$',
        r'\s*PVT\s*LTD\s*$',
        r'\s*LIMITED\s*$',
        r'\s*LTD\s*$',
        r'^MERCHANT\s*',
        r'\s*MERCHANT\s*$',
    ]

    for pattern in patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Remove extra spaces
    normalized = ' '.join(normalized.split())

    return normalized.strip()


def suggest_merchant_consolidation(
    db: Session,
    merchant_id: str,
) -> list[MergeSuggestion]:
    """
    Find potential duplicates for a specific merchant.

    Args:
        db: Database session
        merchant_id: Merchant to check

    Returns:
        List of similar merchants
    """
    merchant = db.query(MerchantMemory).filter_by(id=merchant_id).first()
    if not merchant:
        return []

    all_memories = db.query(MerchantMemory).filter(
        MerchantMemory.id != merchant_id
    ).all()

    suggestions = []
    for other in all_memories:
        similarity = fuzz.ratio(
            merchant.normalized_name.upper(),
            other.normalized_name.upper()
        )

        if similarity >= 75:
            suggestions.append(MergeSuggestion(
                primary_id=merchant.id,
                primary_name=merchant.normalized_name,
                duplicate_id=other.id,
                duplicate_name=other.normalized_name,
                similarity_score=similarity,
                primary_category=merchant.category,
                duplicate_category=other.category,
                primary_times_seen=merchant.times_seen,
                duplicate_times_seen=other.times_seen,
                confidence=similarity / 100.0,
            ))

    suggestions.sort(key=lambda x: x.similarity_score, reverse=True)
    return suggestions
