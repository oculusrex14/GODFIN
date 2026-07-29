from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.transaction import Transaction

PAYOUT_POLICY = {
    "aggregate_bundle_inr": 100,
    "new_template_family_inr": 25,
    "template_family_limit": 6,
    "material_variant_inr": 10,
    "material_variant_limit": 5,
    "participant_cap_inr": 300,
    "pilot_cap_inr": 50_000,
}
_BANNED_KEYS = {
    "name",
    "email",
    "phone",
    "address",
    "account",
    "card",
    "upi",
    "vpa",
    "description",
    "merchant",
    "raw_text",
    "date",
    "amount",
    "balance",
}
_PII_PATTERNS = [
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+?91[- ]?)?[6-9]\d{9}\b"),
    re.compile(r"\b\d{12,16}\b"),
    re.compile(r"\b[\w.-]+@[A-Za-z]{2,}\b"),
]


def _count_band(value: int) -> str:
    if value <= 0:
        return "0"
    bounds = (10, 25, 50, 100, 250, 500, 1000)
    lower = 1
    for upper in bounds:
        if value <= upper:
            return f"{lower}-{upper}"
        lower = upper + 1
    return "1001+"


def _round_share(value: float) -> int:
    return int(max(0, min(100, 5 * round(value / 5))))


def validate_redacted_payload(payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    def walk(value: Any, path: str = "payload") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = key.lower()
                if lowered in _BANNED_KEYS or any(
                    token in lowered for token in _BANNED_KEYS
                ):
                    problems.append(f"Forbidden field at {path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            if any(pattern.search(value) for pattern in _PII_PATTERNS):
                problems.append(f"Possible identifier at {path}")

    walk(payload)
    return sorted(set(problems))


def build_redacted_preview(
    db: Session,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=89)
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date <= today,
            Transaction.status != "deleted",
            Transaction.is_transfer.is_(False),
        )
        .all()
    )
    category_counts = Counter(
        (row.category or "UNCLASSIFIED") for row in rows if row.type == "debit"
    )
    debit_count = sum(category_counts.values())
    category_share_bands = {
        category: _round_share(count / debit_count * 100)
        for category, count in category_counts.most_common()
    } if debit_count else {}
    active_day_count = len({row.date for row in rows})
    income_count = sum(bool(row.is_income) for row in rows)
    recurring_count = sum(bool(row.is_recurring) for row in rows)
    payload = {
        "schema_version": 1,
        "window_days": 90,
        "transaction_count_band": _count_band(len(rows)),
        "debit_count_band": _count_band(debit_count),
        "income_count_band": _count_band(income_count),
        "recurring_count_band": _count_band(recurring_count),
        "active_day_count_band": _count_band(active_day_count),
        "category_share_bands_percent": category_share_bands,
        "classification_coverage_band_percent": (
            _round_share(
                sum(row.category is not None for row in rows) / len(rows) * 100
            )
            if rows
            else 0
        ),
        "policy": "coarse_aggregate_only_no_identifiers_dates_amounts_or_descriptions",
    }
    problems = validate_redacted_payload(payload)
    if problems:
        raise ValueError("; ".join(problems))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "payload": payload,
        "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "eligible": len(rows) > 0 and (max((row.date for row in rows), default=today) - min(
            (row.date for row in rows), default=today
        )).days >= 89,
        "redaction_checks": {
            "passed": True,
            "forbidden_field_count": 0,
            "possible_identifier_count": 0,
        },
        "payout_policy": PAYOUT_POLICY,
        "notice": (
            "Review this coarse local preview before any submission. Payout "
            "identity is collected separately and is never placed in this payload."
        ),
    }


def projected_participant_payout(
    *,
    accepted_bundle: bool,
    new_template_families: int = 0,
    material_variants: int = 0,
) -> int:
    total = PAYOUT_POLICY["aggregate_bundle_inr"] if accepted_bundle else 0
    total += min(
        max(0, new_template_families), PAYOUT_POLICY["template_family_limit"]
    ) * PAYOUT_POLICY["new_template_family_inr"]
    total += min(
        max(0, material_variants), PAYOUT_POLICY["material_variant_limit"]
    ) * PAYOUT_POLICY["material_variant_inr"]
    return min(total, PAYOUT_POLICY["participant_cap_inr"])
