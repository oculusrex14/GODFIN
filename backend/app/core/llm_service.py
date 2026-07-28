from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from app.core.classifier import validate_category, validate_subcategory
from app.core.taxonomy import TAXONOMY

logger = logging.getLogger(__name__)


# --- Token Estimation ---

def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


MODEL_TOKEN_LIMITS = {
    'gpt-4o': 128000, 'gpt-4o-mini': 128000, 'gpt-4.1': 128000,
    'claude-opus-4-6-20251101': 200000, 'claude-sonnet-4-6-20251101': 200000,
    'claude-haiku-4-5-20251001': 200000,
    'gemini-1.5-pro': 1000000, 'gemini-1.5-flash': 1000000,
}
DEFAULT_TOKEN_LIMIT = 8000


def get_token_limit(model: str = '') -> int:
    return MODEL_TOKEN_LIMITS.get(model, DEFAULT_TOKEN_LIMIT)


# --- Classification Cache (LRU with TTL) ---

class LRUCache:
    def __init__(self, max_size: int = 500, ttl_seconds: float = 86400):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[dict]:
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if time.time() - entry['time'] > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return entry['value']

    def put(self, key: str, value: dict) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = {'value': value, 'time': time.time()}
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._cache)


_classification_cache = LRUCache(max_size=500, ttl_seconds=86400)


def _cache_key(merchant: str, amount: float, instrument: str) -> str:
    if amount < 100:
        bucket = '<100'
    elif amount < 500:
        bucket = '100-500'
    elif amount < 2000:
        bucket = '500-2k'
    elif amount < 10000:
        bucket = '2k-10k'
    else:
        bucket = '10k+'
    return f"{merchant.upper().strip()}|{bucket}|{instrument}"

# --- LLM Classification Prompt ---

LLM_CLASSIFICATION_PROMPT = """You are a financial transaction classifier for an Indian user.

Given a transaction, classify it into EXACTLY one category and subcategory from the list below.

CATEGORIES AND SUBCATEGORIES:
{taxonomy_list}

TRANSACTION:
- Merchant: {merchant_name}
- Amount: \u20b9{amount}
- Payment Method: {instrument}

Respond with ONLY this JSON format, no other text:
{{"category": "...", "subcategory": "...", "confidence": 0.0-1.0}}

Rules:
- You MUST select from the provided categories and subcategories ONLY
- confidence should reflect how certain you are (0.5 = guess, 0.9 = very sure)
- If you cannot determine the category, use "MISCELLANEOUS" / "Other"
{web_search_instruction}
"""


def _build_taxonomy_list() -> str:
    lines = []
    for cat, info in TAXONOMY.items():
        subcats = ', '.join(info['subcategories'])
        lines.append(f"- {cat}: {subcats}")
    return '\n'.join(lines)


def build_prompt(merchant_name: str, amount: float, instrument: str, web_search_enabled: bool = False) -> str:
    if web_search_enabled:
        web_instruction = "- You may use web search to identify unfamiliar vendor names."
    else:
        web_instruction = "- Do NOT access the internet. Classify using only the vendor name provided."
    return LLM_CLASSIFICATION_PROMPT.format(
        taxonomy_list=_build_taxonomy_list(),
        merchant_name=merchant_name,
        amount=f"{amount:,.2f}",
        instrument=instrument,
        web_search_instruction=web_instruction,
    )


# --- Circuit Breaker ---

@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_timeout: float = 60.0  # seconds
    _failure_count: int = 0
    _last_failure_time: float = 0.0
    _state: str = 'closed'  # closed, open, half_open

    def can_execute(self) -> bool:
        if self._state == 'closed':
            return True
        if self._state == 'open':
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._state = 'half_open'
                return True
            return False
        return True  # half_open

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = 'closed'

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = 'open'
            logger.warning("Circuit breaker opened — LLM service unavailable")


_circuit_breaker = CircuitBreaker()


# --- LLM Service Interface ---

@dataclass
class LLMClassificationResult:
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: float = 0.0
    success: bool = False
    error: Optional[str] = None


class LLMProvider:
    """Base class for LLM providers. Override call() to implement."""

    def call(self, prompt: str) -> Optional[str]:
        raise NotImplementedError


class StubLLMProvider(LLMProvider):
    """Stub provider that returns None — used when no LLM is configured."""

    def call(self, prompt: str) -> Optional[str]:
        return None


# Active provider (can be swapped at runtime)
_provider: LLMProvider = StubLLMProvider()


def set_llm_provider(provider: LLMProvider) -> None:
    global _provider
    _provider = provider


def classify_with_llm(
    merchant_name: str,
    amount: float,
    instrument: str,
    web_search_enabled: bool = False,
) -> LLMClassificationResult:
    result = LLMClassificationResult()

    # Check cache first
    ck = _cache_key(merchant_name, amount, instrument)
    cached = _classification_cache.get(ck)
    if cached:
        result.category = cached['category']
        result.subcategory = cached.get('subcategory')
        result.confidence = cached.get('confidence', 0.7)
        result.success = True
        return result

    if not _circuit_breaker.can_execute():
        result.error = "Circuit breaker open"
        return result

    prompt = build_prompt(merchant_name, amount, instrument, web_search_enabled=web_search_enabled)

    # Check token limit — if prompt is too large, trim taxonomy
    prompt_tokens = estimate_tokens(prompt)
    token_limit = get_token_limit(getattr(_provider, 'model', ''))
    if prompt_tokens > token_limit * 0.9:
        logger.warning(f"Prompt too large ({prompt_tokens} tokens), trimming")
        max_chars = token_limit * 4
        prompt = prompt[:max_chars]  # Rough trim

    try:
        response = _provider.call(prompt)
        if response is None:
            result.error = "No LLM provider configured"
            return result

        # Parse JSON response
        parsed = _parse_llm_response(response)
        if parsed is None:
            _circuit_breaker.record_failure()
            result.error = "Invalid LLM response format"
            return result

        # Validate against taxonomy
        category = parsed.get('category')
        subcategory = parsed.get('subcategory')
        confidence = parsed.get('confidence', 0.5)

        if not category or not validate_category(category):
            _circuit_breaker.record_failure()
            result.error = f"Invalid category from LLM: {category}"
            return result

        if subcategory and not validate_subcategory(category, subcategory):
            subcategory = None  # Drop invalid subcategory but keep category

        _circuit_breaker.record_success()

        result.category = category
        result.subcategory = subcategory
        result.confidence = min(float(confidence) * 0.85, 1.0)  # Scale down LLM confidence
        result.success = True

        # Cache successful result
        _classification_cache.put(ck, {
            'category': category,
            'subcategory': subcategory,
            'confidence': result.confidence,
        })

    except Exception as e:
        _circuit_breaker.record_failure()
        result.error = str(e)
        logger.error(f"LLM classification error: {e}")

    return result


def call_llm(prompt: str, temperature: float = 0.3) -> Optional[str]:
    """General-purpose LLM call. Returns response text or None on failure.
    Never raises — always returns gracefully."""
    if not _circuit_breaker.can_execute():
        logger.warning("LLM circuit breaker open, skipping call")
        return None

    try:
        response = _provider.call(prompt)
        if response:
            _circuit_breaker.record_success()
        return response
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error(f"LLM call error: {e}")
        return None


def _parse_llm_response(response: str) -> Optional[dict]:
    try:
        # Try direct JSON parse
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    import re
    json_match = re.search(r'\{[^{}]+\}', response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None
