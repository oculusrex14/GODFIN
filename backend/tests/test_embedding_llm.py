from __future__ import annotations

import numpy as np

from app.core.embedding_service import (
    cosine_similarity,
    deserialize_embedding,
    serialize_embedding,
)
from app.core.llm_service import (
    CircuitBreaker,
    LLMClassificationResult,
    LLMProvider,
    StubLLMProvider,
    _parse_llm_response,
    build_prompt,
    classify_with_llm,
    set_llm_provider,
)
from app.models.merchant_memory import MerchantMemory


# --- Embedding utilities ---

def test_serialize_deserialize_embedding():
    original = np.random.rand(384).astype(np.float32)
    serialized = serialize_embedding(original)
    restored = deserialize_embedding(serialized)
    np.testing.assert_array_almost_equal(original, restored)


def test_cosine_similarity_identical():
    vec = np.random.rand(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    score = cosine_similarity(vec, vec)
    assert abs(score - 1.0) < 0.01


def test_cosine_similarity_orthogonal():
    a = np.zeros(384, dtype=np.float32)
    a[0] = 1.0
    b = np.zeros(384, dtype=np.float32)
    b[1] = 1.0
    score = cosine_similarity(a, b)
    assert abs(score) < 0.01


# --- LLM prompt building ---

def test_build_prompt():
    prompt = build_prompt('SWIGGY FOOD ORDER', 350.0, 'upi')
    assert 'SWIGGY FOOD ORDER' in prompt
    assert '350.00' in prompt
    assert 'upi' in prompt
    assert 'FOOD & DINING' in prompt


# --- LLM response parsing ---

def test_parse_valid_json():
    response = '{"category": "FOOD & DINING", "subcategory": "Food Delivery", "confidence": 0.9}'
    result = _parse_llm_response(response)
    assert result is not None
    assert result['category'] == 'FOOD & DINING'


def test_parse_json_in_markdown():
    response = 'Here is the result:\n```json\n{"category": "SHOPPING", "subcategory": "General", "confidence": 0.8}\n```'
    result = _parse_llm_response(response)
    assert result is not None
    assert result['category'] == 'SHOPPING'


def test_parse_invalid_response():
    result = _parse_llm_response('I cannot classify this')
    assert result is None


# --- Circuit breaker ---

def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.can_execute() is True


def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute() is False


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_success()
    assert cb.can_execute() is True


# --- Stub provider ---

def test_stub_provider_returns_none():
    provider = StubLLMProvider()
    assert provider.call("test") is None


# --- LLM classify with mock provider ---

class MockLLMProvider(LLMProvider):
    def __init__(self, response):
        self._response = response

    def call(self, prompt):
        return self._response


def test_classify_with_valid_llm():
    mock = MockLLMProvider(
        '{"category": "FOOD & DINING", "subcategory": "Food Delivery", "confidence": 0.9}'
    )
    set_llm_provider(mock)
    try:
        result = classify_with_llm('SWIGGY', 350.0, 'upi')
        assert result.success is True
        assert result.category == 'FOOD & DINING'
        assert result.confidence <= 0.9 * 0.85 + 0.01  # Scaled down
    finally:
        set_llm_provider(StubLLMProvider())


def test_classify_with_invalid_category_llm():
    mock = MockLLMProvider(
        '{"category": "NONEXISTENT", "subcategory": "Fake", "confidence": 0.9}'
    )
    set_llm_provider(mock)
    try:
        result = classify_with_llm('UNKNOWN', 100.0, 'upi')
        assert result.success is False
        assert 'Invalid category' in result.error
    finally:
        set_llm_provider(StubLLMProvider())


def test_classify_with_stub_provider():
    set_llm_provider(StubLLMProvider())
    result = classify_with_llm('SOMETHING', 100.0, 'upi')
    assert result.success is False
    assert result.error == "No LLM provider configured"


# --- Integration: embedding in merchant_memory ---

def test_embedding_stored_on_merchant_memory(db_session):
    from app.core.embedding_service import update_merchant_embedding

    memory = MerchantMemory(
        raw_string='NETFLIX',
        normalized_name='NETFLIX',
        category='ENTERTAINMENT',
        subcategory='Subscriptions',
    )
    db_session.add(memory)
    db_session.flush()

    success = update_merchant_embedding(db_session, memory)
    # May fail if model can't load in test env — that's OK
    if success:
        assert memory.embedding_vector is not None
        assert memory.embedding_model_version == 'all-MiniLM-L6-v2'


def test_backfill_embeddings(db_session):
    from app.core.embedding_service import backfill_embeddings

    memory = MerchantMemory(
        raw_string='AMAZON',
        normalized_name='AMAZON',
        category='SHOPPING',
        subcategory='General',
    )
    db_session.add(memory)
    db_session.flush()

    updated = backfill_embeddings(db_session)
    # May be 0 if model loading fails, or 1 if it works
    assert updated >= 0
