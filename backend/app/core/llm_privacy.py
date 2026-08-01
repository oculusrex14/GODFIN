"""Consent records and mandatory redaction for hosted AI providers."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


HOSTED_DATA_CONSENT_VERSION = "2026-08-02"
LOCAL_PROVIDER_IDS = frozenset({"ollama_local"})
MAX_HOSTED_PROMPT_CHARS = 60_000

_EMAIL_OR_UPI = re.compile(
    r"(?i)\b[a-z0-9._%+\-]{1,64}@[a-z0-9.\-]{2,80}\.[a-z]{2,20}\b"
    r"|\b[a-z0-9._\-]{2,64}@[a-z][a-z0-9]{1,30}\b"
)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{9}(?!\d)")
_MASKED_ACCOUNT = re.compile(r"(?i)(?:\*{2,}|x{2,})\s*\d{3,4}\b")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{8,19}(?!\d)")
_REFERENCE = re.compile(
    r"(?i)\b(?:ref(?:erence)?|utr|rrn|txn(?:id)?)\s*[:#\-]?\s*[a-z0-9\-]{6,}\b"
)
_EXACT_DATE = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
)
_AMOUNT = re.compile(
    r"(?i)(?:₹|\b(?:rs\.?|inr)\s*)[-+]?\s*\d[\d,]*(?:\.\d+)?"
)
_LABELED_AMOUNT = re.compile(
    r"(?i)\b(amount|spent|spend|paid|income|balance|saved|saving|budget|target|cost|price)"
    r"(\s*(?:is|was|of|:|=)?\s*)[-+]?\d[\d,]*(?:\.\d+)?"
)


def is_local_provider(provider_id: str | None) -> bool:
    return str(provider_id or "").strip().lower() in LOCAL_PROVIDER_IDS


def validate_provider_base_url(provider_id: str, base_url: str | None) -> None:
    """Prevent a 'local' provider or cloud credential from targeting an arbitrary host."""
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI provider URL contains unsupported components")
    if parsed.path not in {"", "/"}:
        raise ValueError("AI provider URL must not include a path")
    if provider_id == "ollama_local":
        if parsed.scheme != "http" or parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Ollama Local must use a loopback HTTP address")
    elif provider_id == "ollama_cloud":
        if parsed.scheme != "https" or parsed.hostname != "api.ollama.com":
            raise ValueError("Ollama Cloud must use the official HTTPS endpoint")


def _settings(config: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(config.settings_json or "{}")
    except (AttributeError, TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def has_hosted_data_consent(config: Any) -> bool:
    if is_local_provider(getattr(config, "provider", None)):
        return True
    consent = _settings(config).get("hosted_data_consent")
    return bool(
        isinstance(consent, dict)
        and consent.get("accepted") is True
        and consent.get("version") == HOSTED_DATA_CONSENT_VERSION
        and consent.get("accepted_at")
    )


def record_hosted_data_consent(config: Any, accepted: bool) -> None:
    settings = _settings(config)
    if accepted:
        settings["hosted_data_consent"] = {
            "accepted": True,
            "version": HOSTED_DATA_CONSENT_VERSION,
            "accepted_at": datetime.now(UTC).isoformat(),
        }
    else:
        settings.pop("hosted_data_consent", None)
    config.settings_json = json.dumps(settings, separators=(",", ":"), sort_keys=True)


def sanitize_untrusted_text(value: Any, *, max_length: int = 160) -> str:
    """Normalize imported/user text and remove prompt-control characters."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in text
    )
    return " ".join(text.split())[:max_length]


def _amount_band(match: re.Match[str]) -> str:
    raw = match.group(0)
    number_match = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
    if not number_match:
        return "Rs <amount removed>"
    try:
        amount = abs(float(number_match.group(0).replace(",", "")))
    except ValueError:
        return "Rs <amount removed>"
    thresholds = (
        (100, "under 100"),
        (500, "100-500"),
        (2_000, "500-2,000"),
        (10_000, "2,000-10,000"),
        (50_000, "10,000-50,000"),
        (200_000, "50,000-2 lakh"),
        (1_000_000, "2-10 lakh"),
    )
    for upper, label in thresholds:
        if amount < upper:
            return f"Rs <{label}>"
    return "Rs <10 lakh or more>"


def _labeled_amount_band(match: re.Match[str]) -> str:
    value = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", match.group(0))
    if value is None:
        return f"{match.group(1)} <amount removed>"
    synthetic = re.match(r".*", f"Rs {value.group(0)}")
    assert synthetic is not None
    return f"{match.group(1)} {_amount_band(synthetic)}"


def redact_hosted_prompt(prompt: str) -> str:
    """Remove direct identifiers and exact financial values before any network call."""
    if not isinstance(prompt, str):
        raise TypeError("LLM prompt must be text")
    text = unicodedata.normalize("NFKC", prompt)
    text = "".join(
        char if char in "\n\t" or not unicodedata.category(char).startswith("C") else " "
        for char in text
    )
    text = _EMAIL_OR_UPI.sub("<email-or-payment-address removed>", text)
    text = _PHONE.sub("<phone removed>", text)
    text = _MASKED_ACCOUNT.sub("<account fragment removed>", text)
    text = _REFERENCE.sub("<transaction reference removed>", text)
    text = _EXACT_DATE.sub("<exact date removed>", text)
    text = _AMOUNT.sub(_amount_band, text)
    text = _LABELED_AMOUNT.sub(_labeled_amount_band, text)
    text = _LONG_NUMBER.sub("<long number removed>", text)
    return text[:MAX_HOSTED_PROMPT_CHARS]
