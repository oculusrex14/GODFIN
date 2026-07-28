from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from thefuzz import fuzz

from app.core.taxonomy import TAXONOMY
from app.models.classification_rule import ClassificationRule
from app.models.merchant_memory import MerchantMemory

logger = logging.getLogger(__name__)


# --- Taxonomy (single source of truth) ---

VALID_CATEGORIES = set(TAXONOMY.keys())


def validate_category(category: str) -> bool:
    return category in VALID_CATEGORIES


def validate_subcategory(category: str, subcategory: str) -> bool:
    if category not in TAXONOMY:
        return False
    return subcategory in TAXONOMY[category]['subcategories']


# --- Transfer Detection ---

TRANSFER_KEYWORDS = [
    'HDFC CREDIT CARD', 'CREDIT CARD PAYMENT', 'CRED', 'BILLDESK',
    'HDFC BANK', 'NEFT SELF', 'SELF TRANSFER', 'OWN ACCOUNT',
    'CREDIT CARD BILL',
]


def detect_transfer(merchant_normalized: str, amount: float, instrument: str) -> bool:
    merchant = merchant_normalized.upper()
    for keyword in TRANSFER_KEYWORDS:
        if keyword in merchant:
            return True
    if instrument == 'upi' and amount >= 1000:
        if any(kw in merchant for kw in ['HDFC', 'CREDIT', 'CRED', 'BILL']):
            return True
    return False


# --- P2P Detection ---

P2P_VPA_PATTERN = re.compile(r'\d{10}@(ybl|paytm|okaxis|okicici|apl)')


def detect_p2p(vpa_handle: Optional[str]) -> bool:
    if not vpa_handle:
        return False
    return bool(P2P_VPA_PATTERN.match(vpa_handle))


# --- Classification Result ---

@dataclass
class ClassificationResult:
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: float = 0.0
    source: str = 'unclassified'
    is_transfer: bool = False
    is_p2p: bool = False


# --- Classification Engine ---

def classify_transaction(
    db: Session,
    merchant_normalized: str,
    amount: float,
    instrument: str,
    vpa_handle: Optional[str] = None,
) -> ClassificationResult:
    result = ClassificationResult()

    # Pre-check: transfer detection
    if detect_transfer(merchant_normalized, amount, instrument):
        result.is_transfer = True
        result.category = 'TRANSFERS'
        result.subcategory = 'Credit Card Payment'
        result.confidence = 0.95
        result.source = 'transfer_detect'
        return result

    # Pre-check: P2P detection
    result.is_p2p = detect_p2p(vpa_handle)

    # Layer 1: Exact match from merchant_memory
    layer1 = _layer_exact_match(db, merchant_normalized)
    if layer1:
        return layer1

    # Layer 2: Classification rules (regex/contains)
    layer2 = _layer_rules(db, merchant_normalized)
    if layer2:
        return layer2

    # Layer 3: Fuzzy string match against merchant_memory
    layer3 = _layer_fuzzy_match(db, merchant_normalized)
    if layer3:
        return layer3

    # Layer 4: Embedding similarity
    layer4 = _layer_embedding_match(db, merchant_normalized)
    if layer4:
        return layer4

    # Layer 5: LLM fallback
    layer5 = _layer_llm(db, merchant_normalized, amount, instrument)
    if layer5:
        return layer5

    return result  # unclassified → goes to review queue


def _layer_exact_match(db: Session, merchant_normalized: str) -> Optional[ClassificationResult]:
    memory = db.query(MerchantMemory).filter_by(normalized_name=merchant_normalized).first()
    if memory:
        # Use stored confidence, decayed over time if applicable
        base_confidence = max(memory.avg_confidence, 0.85)  # Floor at 0.85 for exact matches
        return ClassificationResult(
            category=memory.category,
            subcategory=memory.subcategory,
            confidence=base_confidence,
            source='exact_match',
        )
    return None


def _layer_rules(db: Session, merchant_normalized: str) -> Optional[ClassificationResult]:
    rules = (
        db.query(ClassificationRule)
        .filter_by(is_active=True)
        .order_by(ClassificationRule.priority)
        .all()
    )

    for rule in rules:
        matched = False
        if rule.rule_type == 'contains':
            matched = rule.pattern.upper() in merchant_normalized.upper()
        elif rule.rule_type == 'regex':
            matched = bool(re.search(rule.pattern, merchant_normalized, re.IGNORECASE))
        elif rule.rule_type == 'exact':
            matched = rule.pattern.upper() == merchant_normalized.upper()

        if matched:
            return ClassificationResult(
                category=rule.category,
                subcategory=rule.subcategory,
                confidence=0.95,
                source='rule',
            )

    return None


def _layer_fuzzy_match(
    db: Session, merchant_normalized: str, threshold: int = 85
) -> Optional[ClassificationResult]:
    memories = db.query(MerchantMemory).all()
    if not memories:
        return None

    best_score = 0
    best_memory = None

    for memory in memories:
        score = fuzz.ratio(merchant_normalized.upper(), memory.normalized_name.upper())
        if score > best_score:
            best_score = score
            best_memory = memory

    if best_memory and best_score >= threshold:
        # Factor in both fuzzy match score AND stored confidence
        fuzzy_confidence = 0.85 * (best_score / 100.0)
        stored_confidence = best_memory.avg_confidence
        # Combined confidence weighted toward the lower of the two
        final_confidence = min(fuzzy_confidence, fuzzy_confidence * stored_confidence)
        return ClassificationResult(
            category=best_memory.category,
            subcategory=best_memory.subcategory,
            confidence=final_confidence,
            source='fuzzy',
        )

    return None


def _layer_embedding_match(db: Session, merchant_normalized: str) -> Optional[ClassificationResult]:
    try:
        from app.core.license import has_feature
        from app.models.app_setting import AppSetting

        if not has_feature(db, "ai_classification"):
            return None
        enabled = db.query(AppSetting).filter_by(key="enable_embeddings").first()
        if not enabled or enabled.value != "true":
            return None

        from app.core.embedding_service import find_similar_merchant
        match = find_similar_merchant(db, merchant_normalized)
        if match:
            memory, score = match
            return ClassificationResult(
                category=memory.category,
                subcategory=memory.subcategory,
                confidence=score * 0.90,
                source='embedding',
            )
    except Exception:
        pass
    return None


def _sanitize_for_llm(text: str) -> str:
    """Strip PII before sending to any LLM provider."""
    # 10-digit phone numbers
    text = re.sub(r'\b\d{10}\b', '[REDACTED]', text)
    # 10-16 digit account/card numbers
    text = re.sub(r'\b\d{10,16}\b', '[REDACTED]', text)
    # UPI VPA handles (xxx@xxx)
    text = re.sub(r'\b[\w.+-]+@[\w]+\b', '[REDACTED]', text)
    # Balance/amount patterns (Rs./INR/₹ followed by numbers)
    text = re.sub(r'(?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d{2})?', '[REDACTED]', text)
    return text


def _layer_llm(
    db: Session, merchant_normalized: str, amount: float, instrument: str
) -> Optional[ClassificationResult]:
    try:
        from app.core.license import has_feature
        from app.core.llm_service import classify_with_llm
        from app.models.app_setting import AppSetting

        if not has_feature(db, "ai_classification"):
            return None
        # Read web search setting
        ws_setting = db.query(AppSetting).filter_by(key='llm_web_search').first()
        web_search_enabled = ws_setting and ws_setting.value == 'true'

        sanitized_merchant = _sanitize_for_llm(merchant_normalized)
        result = classify_with_llm(sanitized_merchant, amount, instrument, web_search_enabled=web_search_enabled)
        if result.success and result.category:
            return ClassificationResult(
                category=result.category,
                subcategory=result.subcategory,
                confidence=result.confidence,
                source='llm',
            )
    except Exception:
        pass
    return None


# --- Confidence Thresholds ---

def get_review_status(category: Optional[str], confidence: float) -> str:
    if not category:
        return 'needs_review'
    threshold = TAXONOMY.get(category, {}).get('confidence_threshold', 0.85)
    if confidence >= threshold:
        return 'auto_accepted'
    elif confidence >= 0.60:
        return 'soft_flagged'
    else:
        return 'needs_review'
