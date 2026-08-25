from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DocumentElement:
    element_type: str
    text: str
    page: int
    bounding_box: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedDocument:
    extractor: str
    page_count: int
    elements: tuple[DocumentElement, ...]
    warnings: tuple[str, ...] = ()
    elapsed_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransactionEnvelope:
    """Canonical, source-preserving transaction extraction record.

    This is an internal interchange object rather than a second ledger.  It
    keeps evidence discovered by a parser/enricher separate from the final
    user-visible category and from GODFIN's coarse financial semantics.
    """

    raw_text: str
    source_type: str
    source_bank: str | None
    source_account_id: str
    source_format_version: str | None
    booking_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    direction: str
    running_balance: Decimal | None
    payment_rail: str | None
    transaction_status: str
    instrument: str | None
    merchant_candidate: str | None
    counterparty_candidate: str | None
    processor_candidate: str | None
    vpa: str | None
    vpa_role: str | None
    reference: str | None
    semantic_detail: str
    parser_version: str | None
    extraction_evidence: tuple[str, ...] = ()
    review_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
