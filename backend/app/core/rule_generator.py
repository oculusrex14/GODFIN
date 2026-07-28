"""
Rule auto-generation system.
Analyzes frequently corrected patterns and suggests new classification rules.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.classification_rule import ClassificationRule
from app.models.merchant_memory import MerchantMemory
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class PatternSuggestion:
    """Suggested rule pattern."""
    pattern: str
    rule_type: str  # 'contains', 'regex', 'exact'
    category: str
    subcategory: Optional[str]
    confidence: float
    occurrences: int
    example_merchants: list[str]


def extract_common_substrings(merchants: list[str], min_length: int = 4) -> list[tuple[str, int]]:
    """
    Extract common substrings from merchant names.
    Returns list of (substring, count) tuples.
    """
    substrings = Counter()

    for merchant in merchants:
        # Normalize
        clean = merchant.upper().replace(' ', '').replace('-', '').replace('_', '')
        # Generate all substrings
        for i in range(len(clean)):
            for j in range(i + min_length, min(i + 20, len(clean) + 1)):
                substrings[clean[i:j]] += 1

    # Return substrings that appear multiple times
    return [(s, c) for s, c in substrings.most_common() if c >= 2]


def analyze_category_patterns(
    db: Session,
    category: str,
    min_occurrences: int = 3,
) -> list[PatternSuggestion]:
    """
    Analyze merchants in a category to find common patterns.

    Args:
        db: Database session
        category: Category to analyze
        min_occurrences: Minimum times pattern must appear

       Returns:
        List of pattern suggestions
    """
    # Get merchants in this category
    memories = db.query(MerchantMemory).filter_by(category=category).all()

    if len(memories) < min_occurrences:
        return []

    merchant_names = [m.normalized_name for m in memories]

    # Find common substrings
    common = extract_common_substrings(merchant_names, min_length=4)

    suggestions = []
    for substring, count in common[:10]:  # Top 10 patterns
        if count >= min_occurrences:
            # Find example merchants containing this substring
            examples = [m for m in merchant_names if substring in m.upper().replace(' ', '')][:3]

            # Get most common subcategory for this pattern
            subcat_counter = Counter(
                m.subcategory for m in memories
                if substring in m.normalized_name.upper().replace(' ', '')
                and m.subcategory
            )
            most_common_subcat = subcat_counter.most_common(1)[0][0] if subcat_counter else None

            suggestions.append(PatternSuggestion(
                pattern=substring,
                rule_type='contains',
                category=category,
                subcategory=most_common_subcat,
                confidence=min(0.90, 0.70 + (count * 0.05)),  # Higher confidence with more occurrences
                occurrences=count,
                example_merchants=examples,
            ))

    return suggestions


def find_correction_patterns(
    db: Session,
    min_corrections: int = 3,
) -> list[PatternSuggestion]:
    """
    Analyze audit logs to find frequently corrected merchants.

    Args:
        db: Database session
        min_corrections: Minimum corrections to consider

    Returns:
        List of pattern suggestions from corrections
    """
    # Find transactions with multiple category corrections
    corrections = db.query(AuditLog).filter(
        AuditLog.field_changed == 'category'
    ).all()

    # Group by merchant
    merchant_corrections = {}
    for log in corrections:
        txn = db.query(Transaction).filter_by(id=log.transaction_id).first()
        if not txn or not txn.merchant_normalized:
            continue

        merchant = txn.merchant_normalized
        if merchant not in merchant_corrections:
            merchant_corrections[merchant] = []
        merchant_corrections[merchant].append({
            'old': log.old_value,
            'new': log.new_value,
        })

    suggestions = []
    for merchant, changes in merchant_corrections.items():
        if len(changes) >= min_corrections:
            # Find the most common correction target
            targets = Counter(c['new'] for c in changes if c['new'])
            if targets:
                most_common_cat, count = targets.most_common(1)[0]
                confidence = min(0.85, 0.60 + (count * 0.05))

                suggestions.append(PatternSuggestion(
                    pattern=merchant,
                    rule_type='exact',
                    category=most_common_cat,
                    subcategory=None,
                    confidence=confidence,
                    occurrences=len(changes),
                    example_merchants=[merchant],
                ))

    return suggestions


def generate_rule_from_suggestion(
    db: Session,
    suggestion: PatternSuggestion,
    priority: int = 50,
) -> Optional[ClassificationRule]:
    """
    Convert a pattern suggestion into a classification rule.

    Args:
        db: Database session
        suggestion: Pattern suggestion to convert
        priority: Rule priority (lower = higher priority)

    Returns:
        Created rule or None if creation failed
    """
    # Check if similar rule already exists
    existing = db.query(ClassificationRule).filter(
        ClassificationRule.pattern.ilike(suggestion.pattern),
        ClassificationRule.is_active == True,
    ).first()

    if existing:
        logger.debug(f"Rule already exists for pattern: {suggestion.pattern}")
        return None

    # Create the rule
    rule = ClassificationRule(
        rule_type=suggestion.rule_type,
        pattern=suggestion.pattern,
        category=suggestion.category,
        subcategory=suggestion.subcategory,
        priority=priority,
        is_active=True,
    )

    db.add(rule)
    db.flush()

    logger.info(
        f"Created rule: {suggestion.rule_type} '{suggestion.pattern}' "
        f"-> {suggestion.category}"
    )

    return rule


def auto_generate_rules(
    db: Session,
    min_occurrences: int = 3,
    max_rules: int = 10,
) -> dict:
    """
    Automatically generate rules from patterns and corrections.

    Args:
        db: Database session
        min_occurrences: Minimum pattern occurrences
        max_rules: Maximum rules to create

    Returns:
        Summary of created rules
    """
    from app.core.classifier import VALID_CATEGORIES

    created = []
    suggestions = []

    # Analyze each category for patterns
    for category in VALID_CATEGORIES:
        cat_suggestions = analyze_category_patterns(
            db, category, min_occurrences=min_occurrences
        )
        suggestions.extend(cat_suggestions)

    # Also analyze correction patterns
    correction_suggestions = find_correction_patterns(
        db, min_corrections=min_occurrences
    )
    suggestions.extend(correction_suggestions)

    # Sort by confidence and occurrences
    suggestions.sort(key=lambda s: (s.confidence * s.occurrences), reverse=True)

    # Create rules for top suggestions
    for suggestion in suggestions[:max_rules]:
        try:
            rule = generate_rule_from_suggestion(db, suggestion)
            if rule:
                created.append({
                    'pattern': suggestion.pattern,
                    'type': suggestion.rule_type,
                    'category': suggestion.category,
                    'confidence': suggestion.confidence,
                })
        except Exception as e:
            logger.error(f"Failed to create rule for {suggestion.pattern}: {e}")

    if created:
        db.commit()

    return {
        'created': len(created),
        'rules': created,
        'analyzed': len(suggestions),
    }


def get_suggested_rules(
    db: Session,
    min_occurrences: int = 3,
    limit: int = 20,
) -> list[dict]:
    """
    Get rule suggestions without creating them.
    For review before auto-creation.

    Args:
        db: Database session
        min_occurrences: Minimum pattern occurrences
        limit: Maximum suggestions to return

    Returns:
        List of suggestion dictionaries
    """
    from app.core.classifier import VALID_CATEGORIES

    suggestions = []

    # Analyze each category
    for category in VALID_CATEGORIES:
        cat_suggestions = analyze_category_patterns(
            db, category, min_occurrences=min_occurrences
        )
        suggestions.extend(cat_suggestions)

    # Analyze corrections
    correction_suggestions = find_correction_patterns(
        db, min_corrections=min_occurrences
    )
    suggestions.extend(correction_suggestions)

    # Sort by confidence
    suggestions.sort(key=lambda s: s.confidence, reverse=True)

    return [
        {
            'pattern': s.pattern,
            'rule_type': s.rule_type,
            'category': s.category,
            'subcategory': s.subcategory,
            'confidence': round(s.confidence, 2),
            'occurrences': s.occurrences,
            'examples': s.example_merchants,
        }
        for s in suggestions[:limit]
    ]
