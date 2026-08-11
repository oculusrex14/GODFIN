from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, Protocol

from app.core.classifier import validate_category, validate_subcategory
from app.core.llm_privacy import redact_hosted_prompt, sanitize_untrusted_text
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
MAX_LLM_RESPONSE_CHARS = 1_000_000


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
        merchant_name=(
            "<UNTRUSTED_VENDOR_TEXT>"
            + sanitize_untrusted_text(merchant_name, max_length=160)
            + "</UNTRUSTED_VENDOR_TEXT>"
        ),
        amount=f"{amount:,.2f}",
        instrument=sanitize_untrusted_text(instrument, max_length=32),
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
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == 'closed':
                return True
            if self._state == 'open':
                if time.time() - self._last_failure_time >= self.reset_timeout:
                    self._state = 'half_open'
                    return True
                return False
            return True  # half_open

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = 'closed'

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = 'open'
                logger.warning("Circuit breaker opened — LLM service unavailable")


# --- LLM Service Interface ---

@dataclass
class LLMClassificationResult:
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: float = 0.0
    success: bool = False
    error: Optional[str] = None


class LLMProvider(Protocol):
    """Structural contract shared by every local and remote LLM provider."""

    model: str
    is_local: bool
    hosted_data_consent: bool

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]: ...


class StubLLMProvider(LLMProvider):
    """Stub provider that returns None — used when no LLM is configured."""

    model = "stub"
    is_local = True
    hosted_data_consent = False

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        del prompt, temperature
        return None


# Active provider (can be swapped at runtime)
_provider: LLMProvider = StubLLMProvider()
_provider_generation = 0
_circuit_breakers: dict[tuple[int, str], CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def _breaker_for(purpose: str) -> CircuitBreaker:
    normalized_purpose = (purpose or "general").strip().lower()[:64]
    key = (_provider_generation, normalized_purpose)
    with _circuit_breakers_lock:
        breaker = _circuit_breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker()
            _circuit_breakers[key] = breaker
        return breaker


def _call_active_provider(
    prompt: str,
    *,
    temperature: float,
    purpose: str,
) -> Optional[str]:
    if getattr(_provider, "is_local", False):
        prepared_prompt = prompt
    else:
        if not getattr(_provider, "hosted_data_consent", False):
            raise PermissionError(
                "Hosted AI data consent is missing or out of date"
            )
        prepared_prompt = redact_hosted_prompt(prompt)
        logger.info("Applied hosted AI redaction for purpose=%s", purpose)
    response = _provider.call(prepared_prompt, temperature=temperature)
    if response is not None and not isinstance(response, str):
        raise TypeError(
            f"LLM provider returned {type(response).__name__}; expected text or None"
        )
    if response is None:
        return None
    normalized = response.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_LLM_RESPONSE_CHARS:
        raise ValueError("LLM provider response exceeded the safe size limit")
    return normalized


def set_llm_provider(provider: LLMProvider) -> None:
    global _provider, _provider_generation
    if not callable(getattr(provider, "call", None)):
        raise TypeError("LLM provider must implement call(prompt, temperature)")
    _provider = provider
    with _circuit_breakers_lock:
        _provider_generation += 1
        _circuit_breakers.clear()


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

    breaker = _breaker_for("classification")
    if not breaker.can_execute():
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
        response = _call_active_provider(
            prompt,
            temperature=0.1,
            purpose="classification",
        )
        if response is None:
            if not isinstance(_provider, StubLLMProvider):
                breaker.record_failure()
            result.error = "No LLM provider configured"
            return result

        # Parse JSON response
        parsed = _parse_llm_response(response)
        if parsed is None:
            breaker.record_failure()
            result.error = "Invalid LLM response format"
            return result

        # Validate against taxonomy
        category = parsed.get('category')
        subcategory = parsed.get('subcategory')
        confidence = parsed.get('confidence', 0.5)

        if not category or not validate_category(category):
            breaker.record_failure()
            result.error = f"Invalid category from LLM: {category}"
            return result

        if subcategory and not validate_subcategory(category, subcategory):
            subcategory = None  # Drop invalid subcategory but keep category

        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            breaker.record_failure()
            result.error = "Invalid confidence from LLM"
            return result
        if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
            breaker.record_failure()
            result.error = "Invalid confidence from LLM"
            return result

        breaker.record_success()

        result.category = category
        result.subcategory = subcategory
        result.confidence = confidence_value * 0.85
        result.success = True

        # Cache successful result
        _classification_cache.put(ck, {
            'category': category,
            'subcategory': subcategory,
            'confidence': result.confidence,
        })

    except Exception as exc:
        breaker.record_failure()
        result.error = "The connected AI could not classify this transaction."
        logger.exception(
            "LLM classification failed",
            extra={
                "operation_id": "llm_classification",
                "error_code": "LLM_CLASSIFICATION_FAILED",
                "cause_type": type(exc).__name__,
            },
        )

    return result


def call_llm(
    prompt: str,
    temperature: float = 0.3,
    *,
    purpose: str = "general",
) -> Optional[str]:
    """General-purpose LLM call. Returns response text or None on failure.
    Never raises — always returns gracefully."""
    breaker = _breaker_for(purpose)
    if not breaker.can_execute():
        logger.warning("LLM circuit breaker open, skipping call")
        return None

    try:
        response = _call_active_provider(
            prompt,
            temperature=temperature,
            purpose=purpose,
        )
        if response:
            breaker.record_success()
        elif not isinstance(_provider, StubLLMProvider):
            breaker.record_failure()
        return response
    except Exception as exc:
        breaker.record_failure()
        logger.exception(
            "LLM call failed",
            extra={
                "operation_id": f"llm_{purpose}",
                "error_code": "LLM_CALL_FAILED",
                "cause_type": type(exc).__name__,
            },
        )
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
