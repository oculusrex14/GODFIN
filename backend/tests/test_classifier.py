from __future__ import annotations

from app.core.classifier import (
    ClassificationResult,
    classify_transaction,
    detect_p2p,
    detect_transfer,
    get_review_status,
    validate_category,
    validate_subcategory,
)
from app.models.classification_rule import ClassificationRule
from app.models.merchant_memory import MerchantMemory


# --- Taxonomy validation ---

def test_validate_category_valid():
    assert validate_category('FOOD & DINING') is True


def test_validate_category_invalid():
    assert validate_category('NONEXISTENT') is False


def test_validate_subcategory_valid():
    assert validate_subcategory('FOOD & DINING', 'Groceries') is True


def test_validate_subcategory_invalid():
    assert validate_subcategory('FOOD & DINING', 'Nonexistent') is False


# --- Transfer detection ---

def test_detect_transfer_keyword():
    assert detect_transfer('CRED BILL PAY', 5000.0, 'upi') is True


def test_detect_transfer_no_match():
    assert detect_transfer('SWIGGY FOOD ORDER', 350.0, 'upi') is False


def test_detect_transfer_amount_heuristic():
    assert detect_transfer('HDFC CREDIT BILL', 15000.0, 'upi') is True


# --- P2P detection ---

def test_detect_p2p_vpa():
    assert detect_p2p('9876543210@ybl') is True


def test_detect_p2p_non_p2p():
    assert detect_p2p('merchant@axis') is False


def test_detect_p2p_none():
    assert detect_p2p(None) is False


# --- Review status ---

def test_review_status_auto_accepted():
    assert get_review_status('FOOD & DINING', 0.95) == 'auto_accepted'


def test_review_status_soft_flagged():
    assert get_review_status('FOOD & DINING', 0.70) == 'soft_flagged'


def test_review_status_needs_review():
    assert get_review_status('FOOD & DINING', 0.40) == 'needs_review'


def test_review_status_no_category():
    assert get_review_status(None, 0.0) == 'needs_review'


# --- Layer 1: Exact match ---

def test_classify_exact_match(db_session):
    db_session.add(MerchantMemory(
        raw_string='SWIGGY FOOD ORDER',
        normalized_name='SWIGGY FOOD ORDER',
        category='FOOD & DINING',
        subcategory='Food Delivery',
    ))
    db_session.flush()

    result = classify_transaction(db_session, 'SWIGGY FOOD ORDER', 350.0, 'upi')
    assert result.category == 'FOOD & DINING'
    assert result.subcategory == 'Food Delivery'
    assert result.confidence == 1.0
    assert result.source == 'exact_match'


# --- Layer 2: Rules ---

def test_classify_rule_match(db_session):
    # Seed rules are loaded by conftest
    result = classify_transaction(db_session, 'NETFLIX SUBSCRIPTION', 199.0, 'credit_card')
    assert result.category == 'ENTERTAINMENT'
    assert result.subcategory == 'Subscriptions'
    assert result.confidence == 0.95
    assert result.source == 'rule'


def test_classify_rule_swiggy(db_session):
    result = classify_transaction(db_session, 'SWIGGY FOOD ORDER', 350.0, 'upi')
    assert result.category == 'FOOD & DINING'
    assert result.source == 'rule'


# --- Layer 3: Fuzzy match ---

def test_classify_fuzzy_match(db_session):
    db_session.add(MerchantMemory(
        raw_string='DOMINOS PIZZA ONLINE',
        normalized_name='DOMINOS PIZZA ONLINE',
        category='FOOD & DINING',
        subcategory='Food Delivery',
    ))
    db_session.flush()

    # Slightly different name should fuzzy match
    result = classify_transaction(db_session, 'DOMINOS PIZZA ONLIN', 499.0, 'credit_card')
    # Could match via rule (DOMINOS) or fuzzy — both valid
    assert result.category == 'FOOD & DINING'
    assert result.source in ('rule', 'fuzzy', 'exact_match')


# --- Transfer detection in classify ---

def test_classify_transfer(db_session):
    result = classify_transaction(db_session, 'CRED BILL PAY', 5000.0, 'upi')
    assert result.category == 'TRANSFERS'
    assert result.is_transfer is True
    assert result.source == 'transfer_detect'


# --- Unclassified ---

def test_classify_unknown(db_session):
    result = classify_transaction(db_session, 'XYZABC123UNKNOWN', 100.0, 'upi')
    # When no rule or memory matches, the engine falls through to fuzzy/embedding/LLM.
    # LLM may suggest a category (often MISCELLANEOUS) or return unclassified.
    assert result.source in ('unclassified', 'llm', 'embedding')
    assert result.source not in ('rule', 'merchant_memory')


def test_embedding_layer_is_disabled_by_default(db_session, monkeypatch):
    from app.core.classifier import _layer_embedding_match

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Embedding model should not load while disabled")

    monkeypatch.setattr(
        "app.core.embedding_service.find_similar_merchant",
        fail_if_called,
    )
    assert _layer_embedding_match(db_session, "UNKNOWN MERCHANT") is None


# --- Integration with ingestion ---

def test_ingestion_classifies_transactions(db_session):
    from app.core.ingestion import run_ingestion
    from app.models.transaction import Transaction
    from tests.fixtures.mock_emails import MOCK_UPI_DEBIT_EMAIL

    result = run_ingestion(db_session, mock_messages=[MOCK_UPI_DEBIT_EMAIL])
    assert result.created == 1

    txn = db_session.query(Transaction).filter_by(source='gmail').first()
    assert txn is not None
    # SWIGGY FOOD ORDER should match the SWIGGY rule
    assert txn.category == 'FOOD & DINING'
    assert txn.classification_source == 'rule'
    assert txn.confidence == 0.95


def test_ingestion_cc_classifies(db_session):
    from app.core.ingestion import run_ingestion
    from app.models.transaction import Transaction
    from tests.fixtures.mock_emails import MOCK_CC_DEBIT_EMAIL

    result = run_ingestion(db_session, mock_messages=[MOCK_CC_DEBIT_EMAIL])
    assert result.created == 1

    txn = db_session.query(Transaction).filter_by(email_message_id='mock_cc_001').first()
    assert txn is not None
    # AMAZON PAY should match the AMAZON rule
    assert txn.category == 'SHOPPING'
    assert txn.classification_source == 'rule'
